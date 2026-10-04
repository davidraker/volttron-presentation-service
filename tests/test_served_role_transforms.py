"""Transform-level support for the driver's server roles and the hub conventions the end-to-end matrix relies on."""
import json
import time
from importlib import resources
from pathlib import Path

from interoperability.discovery import ieee2030_5 as mirror_gen
from interoperability.discovery.device_formats import dnp3_device_transforms
from interoperability.transform_parser import TransformParser
from interoperability.transforms import immediate, MISSING

TRANSFORMS = resources.files('interoperability').joinpath('transforms')
SUNSPEC_CASE = Path(__file__).parent / 'integration' / 'fake_sunspec' / 'transform_scaling'


def _stage(name, index=0):
    data = json.loads(TRANSFORMS.joinpath(name).read_text())
    return (data if isinstance(data, list) else [data])[index]


def _run(stage, message):
    return TransformParser().build_transform_from_schema([stage['pattern']]).execute(message)


def test_sunspec_watt_limit_and_enter_service_land_on_the_hub_flat():
    out = _run(_stage('sunspec_to_61850.json'), {'704': {'WMaxLimPct': 50, 'WMaxLimPctEna': 1}, '703': {'ES': 1}})
    assert out['DWMX'] == {'ModEna': 1, 'LimW': 50}
    assert out['DCTE'] == {'RtnSrvAuth': 1}


def test_1815_2_outputs_use_the_hub_names_for_limits_and_enables():
    out = _run(_stage('1815.2_to_61850.json', 1), {'AO': {'87': 50, '88': 10, '203': -20}, 'BO': {'17': 1, '27': 1}})
    assert out['DWMX'] == {'LimW': 50, 'ModEna': 1}
    assert out['DWMN'] == {'LimW': 10}
    assert out['DVAR'] == {'VArTgt': -20, 'ModEna': 1}
    back = _run(_stage('61850_to_1815.2.json', 1), {'DWMX': {'LimW': 50, 'ModEna': 1}, 'DVAR': {'VArTgt': -20, 'ModEna': 1}})
    assert back['AO'] == {'87': 50, '203': -20} and back['BO'] == {'17': 1, '27': 1}


def test_1815_2_tables_have_no_nameless_data_objects():
    for name in ('61850_to_1815.2.json', '1815.2_to_61850.json'):
        text = TRANSFORMS.joinpath(name).read_text()
        assert '"": ' not in text and ", '']" not in text


def test_immediate_picks_the_due_schedule_entry():
    due = {'startTime': {'seconds': int(time.time()) - 5}, 'control': {'limitWOperation': {'wMaxSptVal': 40}}}
    later = {'startTime': {'seconds': int(time.time()) + 3600}, 'control': {'limitWOperation': {'wMaxSptVal': 70}}}
    pick = immediate('control', 'limitWOperation', 'wMaxSptVal')
    assert pick.execute([later, due]) == 40
    assert pick.execute([{'control': {'limitWOperation': {'wMaxSptVal': 55}}}]) == 55          # no start time: now
    assert pick.execute([later]) is MISSING
    assert pick.execute([{**due, 'startTime': {'seconds': str(due['startTime']['seconds'])}}]) == 40   # protobuf JSON int64
    assert pick.execute({'not': 'a list'}) is MISSING


def test_openfmb_immediate_control_reaches_the_hub_top_level():
    entry = {'control': {'limitWOperation': {'maxLimParameter': {'modEna': True}, 'wMaxSptVal': 50},
                         'voltVarOperation': {'vVarParameter': {'modEna': True}, 'crvPts': [{'voltVal': 0.95, 'varVal': 0.44}]}}}
    message = {'essControl': {'essControlFSCC': {'essControlScheduleFSCH': {'ValDCSG': {'crvPts': [entry]}}}}}
    out = _run(_stage('openfmb_to_61850.json', 0), message)
    assert out['DWMX'] == {'ModEna': True, 'LimW': 50}
    assert out['DVVR']['ModEna'] is True and out['DVVR']['VVArCrv']['crvPts'] == [{'xVal': 0.95, 'yVal': 0.44}]
    assert out['FSCH']['SchdEntr'][0]['DWMX'] == {'ModEna': True, 'LimW': 50}         # the schedule view is kept
    future = {'startTime': {'seconds': int(time.time()) + 3600}, **entry}
    out = _run(_stage('openfmb_to_61850.json', 0), {'essControl': {'essControlFSCC': {'essControlScheduleFSCH': {'ValDCSG': {'crvPts': [future]}}}}})
    assert 'DWMX' not in out and out['FSCH']['SchdEntr'][0]['DWMX'] == {'ModEna': True, 'LimW': 50}


def test_served_outstation_gets_an_inputs_edge():
    names = ['AI_537', 'AO_87', 'BI_0']
    plain = dnp3_device_transforms('dev', names)
    served = dnp3_device_transforms('dev', names, served=True)
    assert [(d['input_format'], d['output_format']) for d in plain.definitions] == [
        ('dev', '1815.2.inputs'), ('dev', '1815.2.outputs'), ('1815.2.outputs', 'dev')]
    assert ('1815.2.inputs', 'dev') in [(d['input_format'], d['output_format']) for d in served.definitions]
    edge = next(d for d in served.definitions if d['input_format'] == '1815.2.inputs' and d['output_format'] == 'dev')
    out = TransformParser().build_transform_from_schema([edge['pattern']]).execute({'AI': {'537': 4321}, 'BI': {'0': True}})
    assert out == {'AI_537': 4321, 'BI_0': True}


def test_served_mirror_writes_the_downward_points_too():
    registry = mirror_gen.load_registry(SUNSPEC_CASE / 'presentation_config.json')
    mirror = mirror_gen.discover_mirror(registry, 'fake_sunspec_pv')
    plain = mirror_gen.mirror_transforms('m', mirror).definitions[1]
    served = mirror_gen.mirror_transforms('m', mirror, served=True).definitions[1]
    assert plain['input_format'] == served['input_format'] == '2030.5'
    assert 'DERControl_opModMaxLimW' not in plain['pattern'] and 'DERControl_opModMaxLimW' in served['pattern']
    assert set(plain['pattern']) < set(served['pattern'])
    fragment = mirror_gen.presentation_fragment('m', mirror, 'devices/x', ['x', 'm'], served=True)
    assert 'DERControl_opModMaxLimW' in fragment['transforms'][1]['pattern']


def test_immediate_reads_count_as_fields_beneath_the_list():
    parser = TransformParser()
    fm = parser.field_map([{'DWMX': {'LimW': "transform[sched, crvPts](immediate('control', 'wMaxSptVal'))"}}])
    assert fm.retention({('sched', 'crvPts', '0', 'control', 'wMaxSptVal')}) == 1.0
    assert fm.retention({('sched', 'crvPts')}) == 0.0


def test_discovery_tools_write_served_cases(tmp_path):
    from interoperability.discovery import dnp3 as dnp3_gen
    profile = next(Path(__file__).parent.glob('integration/fake_dnp3/**/discovery.json'))
    case = json.loads(profile.read_text())
    device = dnp3_gen.DiscoveredDnp3Device(profile_name='fake', points=[dnp3_gen.DiscoveredDnp3Point(**p) for p in case['points']], notes=[])
    written = dnp3_gen.write_case(device, tmp_path / 'dnp3', device_format='os', device_topic='devices/os', uai=['s', 'os'],
                                  scaling='transform', served=True)
    config = json.loads(written['presentation_config'].read_text())
    assert ('1815.2.inputs', 'os') in {(t['input_format'], t['output_format']) for t in config['transforms']}
    registry = mirror_gen.load_registry(SUNSPEC_CASE / 'presentation_config.json')
    written = mirror_gen.write_case(registry, 'fake_sunspec_pv', tmp_path / 'sep2', mirror_format='srv', device_topic='devices/srv',
                                    uai=['s', 'srv'], served=True)
    fragment = json.loads(written['presentation'].read_text())
    assert 'DERControl_opModMaxLimW' in fragment['transforms'][1]['pattern']
