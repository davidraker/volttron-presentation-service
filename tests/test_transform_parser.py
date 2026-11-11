"""Tests for the transform registry and the bundled transform definitions (the expression language itself is tested
in icm-lib-transforms)."""
import json
import logging
from importlib import resources

import pytest

from icm.transforms.parser import TransformParser
from interoperability.transform_registry import TransformNotFoundError, TransformRegistry


@pytest.fixture
def parser():
    return TransformParser()


def test_bundled_transform_runs_on_partial_message(parser):
    definitions = {(d['input_format'], d['output_format']): d
                   for f in _bundled_transform_files() for d in json.loads(f.read_text())}
    pipeline = parser.build_transform_from_schema(definitions[('61850', 'sunspec')]['pattern'])
    result = pipeline.execute({'MMXU': {'TotW': 12.5, 'Hz': 60.0}})
    assert result == {'701': {'W': 12.5, 'Hz': 60.0}}


def _bundled_transform_files():
    tdir = resources.files('interoperability').joinpath('transforms')
    return sorted((f for f in tdir.iterdir() if f.is_file() and f.name.endswith('.json')),
                  key=lambda f: f.name)


def _bundled_definitions():
    for f in _bundled_transform_files():
        for d in json.loads(f.read_text()):
            yield pytest.param(d, id=f"{f.name}:{d['input_format']}->{d['output_format']}")


@pytest.mark.parametrize('definition', list(_bundled_definitions()))
def test_bundled_transform_definitions_compile(parser, definition):
    assert {'input_format', 'output_format', 'pattern'} <= definition.keys()
    pipeline = parser.build_transform_from_schema(definition['pattern'])
    assert pipeline is not None


def test_registry_finds_direct_chains_between_bundled_formats():
    registry = TransformRegistry()
    for f in _bundled_transform_files():
        registry.update_registry(json.loads(f.read_text()))
    # Every pairing ships as its own file now, so lookups are single hops.
    chain = registry.lookup('sunspec', '1815.2.outputs')
    assert len(chain) == 1
    with pytest.raises(TransformNotFoundError, match='"no_such_format" has no registered transforms'):
        registry.lookup('sunspec', 'no_such_format')


def test_registry_finds_multi_hop_chain():
    registry = TransformRegistry(hubs={'a', 'b', 'c'})
    registry.update_registry([
        {'input_format': 'a', 'output_format': 'b', 'pattern': {'y': 'transform[x]()'}},
        {'input_format': 'b', 'output_format': 'c', 'pattern': {'z': 'transform[y]()'}},
    ])
    chain = registry.lookup('a', 'c')
    assert [list(step) for step in chain] == [['y'], ['z']]      # a -> b -> c
    with pytest.raises(TransformNotFoundError, match='no sequence of registered transforms connects them') as info:
        registry.lookup('c', 'a')
    assert (info.value.input_format, info.value.output_format) == ('c', 'a')


def test_registry_distinguishes_no_transform_needed_from_none_existing(parser):
    registry = TransformRegistry()
    registry.register('a', 'b', {'y': 'transform[x]()'})
    assert registry.lookup('a', 'a') == []                       # same format: nothing to do
    assert registry.lookup('never_seen', 'never_seen') == []     # identity needs no registration
    with pytest.raises(TransformNotFoundError, match='"never_seen" has no registered transforms'):
        registry.lookup('a', 'never_seen')
    assert isinstance(TransformNotFoundError('a', 'b', 'why'), LookupError)
    # An empty chain compiles to the identity, so a resource already in the wanted format passes through.
    assert parser.build_transform_from_schema([]).execute({'x': 1}) == {'x': 1}


def test_registry_keeps_existing_transform_unless_told_to_update(caplog):
    registry = TransformRegistry()
    first, second = {'y': 'transform[x]()'}, {'y': 'transform[x](add(1))'}
    assert registry.register('a', 'b', first) is True
    assert registry.register('a', 'b', first) is False           # same pattern again: silent no-op
    with caplog.at_level(logging.WARNING, logger='interoperability.transform_registry'):
        assert registry.register('a', 'b', second) is False
    assert 'already registered; keeping it' in caplog.text
    assert registry.lookup('a', 'b') == [first]
    assert registry.register('a', 'b', second, update=True) is True
    assert registry.lookup('a', 'b') == [second]


def test_update_registry_replaces_earlier_configuration_but_reports_duplicates_within_one(caplog):
    registry = TransformRegistry(hubs={'a', 'b', 'c'})
    v1, v2, v3, v4 = ({'v': f'transform[{src}]()'} for src in 'wxyz')
    assert registry.update_registry([{'input_format': 'a', 'output_format': 'b', 'pattern': v1}]) == 1
    with caplog.at_level(logging.WARNING, logger='interoperability.transform_registry'):
        changed = registry.update_registry([
            {'input_format': 'a', 'output_format': 'b', 'pattern': v2},   # reload: replaces v1
            {'input_format': 'a', 'output_format': 'b', 'pattern': v3},   # duplicate within the config
            {'input_format': 'b', 'output_format': 'c', 'pattern': v4},
        ])
    assert changed == 2
    assert 'defined more than once' in caplog.text
    assert registry.lookup('a', 'c') == [v2, v4]


def test_agent_loads_bundled_definitions(tmp_path):
    pytest.importorskip('volttron')
    from interoperability.agent import PresentationService
    root = resources.files('interoperability')
    transforms = PresentationService._load_bundled_definitions(root.joinpath('transforms'))
    pairs = {(d['input_format'], d['output_format']) for d in transforms}
    assert ('61850', 'sunspec') in pairs and ('1815.2.inputs', '61850') in pairs
    assert ('1547', 'sunspec') in pairs and ('2030.5', '61850') in pairs
    # Only JSON files directly inside the directory are loaded; drafts in subdirectories are not.
    (tmp_path / 'a.json').write_text(json.dumps([{'input_format': 'a', 'output_format': 'b', 'pattern': {}}]))
    (tmp_path / 'drafts').mkdir()
    (tmp_path / 'drafts' / 'b.json').write_text(json.dumps([{'input_format': 'c', 'output_format': 'd', 'pattern': {}}]))
    loaded = PresentationService._load_bundled_definitions(tmp_path)
    assert [(d['input_format'], d['output_format']) for d in loaded] == [('a', 'b')]
    assert PresentationService._load_bundled_definitions(root.joinpath('does_not_exist')) == []


# ---- Repeated groups ("name[#]") and list functions ----

def _apply_batch(output, table, step):
    """What a driver does with a 1815.2 write: the plain table first, then one batch of the sequence."""
    points = dict(output.get(table, {}))
    points.update(output['sequence'][step][table])
    return {table: points}


def _bundled_pipeline(parser, source, target):
    definitions = {(d['input_format'], d['output_format']): d['pattern']
                   for f in _bundled_transform_files() for d in json.loads(f.read_text())}
    return parser.build_transform_from_schema(definitions[(source, target)])


def test_bundled_curves_through_the_1815_2_edit_window(parser):
    sep2 = {'DERCurve': {'opModVoltVar': {'openLoopTms': 5, 'CurveData': [{'xvalue': 95, 'yvalue': 44}, {'xvalue': 105, 'yvalue': -44}]},
                         'opModHVRTMustTrip': {'CurveData': [{'xvalue': 120, 'yvalue': 0.16}]}}}
    out = _bundled_pipeline(parser, '2030.5', '1815.2.outputs').execute(sep2)
    # One batch per curve, keys in write order: select slot, curve type, count, points, assign to the mode.
    assert out['sequence'] == [
        {'AO': {'244': 1, '245': 2, '246': 2, '249': 95, '250': 44, '251': 105, '252': -44, '217': 1}},
        {'AO': {'244': 4, '245': 9, '246': 1, '249': 120, '250': 0.16, '23': 4}}]
    assert list(out['sequence'][0]['AO']) == ['244', '245', '246', '249', '250', '251', '252', '217']
    # Reading the window back only fills the mode whose curve index matches the selector.
    read = _bundled_pipeline(parser, '1815.2.outputs', '2030.5')
    assert read.execute(_apply_batch(out, 'AO', 0))['DERCurve'] == {
        'opModVoltVar': {'openLoopTms': 5, 'CurveData': [{'xvalue': 95, 'yvalue': 44}, {'xvalue': 105, 'yvalue': -44}]}}
    assert read.execute(_apply_batch(out, 'AO', 1))['DERCurve'] == {
        'opModVoltVar': {'openLoopTms': 5}, 'opModHVRTMustTrip': {'CurveData': [{'xvalue': 120, 'yvalue': 0.16}]}}
    # SunSpec: the active curve's points, trimmed to ActPt, and per-curve settings inside Crv.
    sunspec = {'705': {'Crv': [{'ActPt': 2, 'VRef': 100, 'Pt': [{'V': 95, 'Var': 44}, {'V': 105, 'Var': -44}, {'V': 0, 'Var': 0}]}]}}
    out = _bundled_pipeline(parser, 'sunspec', '1815.2.outputs').execute(sunspec)
    assert out['AO'] == {'0': 100}
    assert out['sequence'] == [{'AO': {'244': 1, '245': 2, '246': 2, '249': 95, '250': 44, '251': 105, '252': -44, '217': 1}}]
    assert _bundled_pipeline(parser, '1815.2.outputs', 'sunspec').execute(_apply_batch(out, 'AO', 0)) == {
        '705': {'Crv': [{'VRef': 100, 'ActPt': 2, 'Pt': [{'V': 95, 'Var': 44}, {'V': 105, 'Var': -44}]}]}}
    # 61850: mode curves feed the sequence. The DNP3 curve store (selector, type, pair array) is the profile's own
    # mechanics and no longer a hub group (the Edition 2 rename of 2026-11-11); only the mode curves cross the hub.
    i61850 = {'DVVR': {'VVArCrv': {'crvPts': [{'xVal': 95, 'yVal': 44}]}}}
    out = _bundled_pipeline(parser, '61850', '1815.2.inputs').execute(i61850)
    assert out['sequence'] == [{'AI': {'328': 1, '329': 2, '330': 1, '333': 95, '334': 44, '297': 1}}]
    back = _bundled_pipeline(parser, '1815.2.inputs', '61850').execute(_apply_batch(out, 'AI', 0))
    assert back['DVVR']['VVArCrv'] == {'numPts': 1, 'crvPts': [{'xVal': 95, 'yVal': 44}]}
    assert 'FMARn' not in back and 'DGSMn' not in back


def test_bundled_schedules_carry_every_entry_between_2030_5_and_61850(parser):
    sep2 = {'DERControl': {'opModFixedPFInjectW': {'displacement': 0.95, 'excitation': 1}},
            'DERControlList': [
                {'interval': {'start': 1700000000, 'duration': 3600},
                 'DERControl': {'opModMaxLimW': 80, 'opModFreqDroop': {'dBOF': 0.036, 'kOF': 5}},
                 'DERCurve': {'opModVoltVar': {'openLoopTms': 5, 'CurveData': [{'xvalue': 95, 'yvalue': 44}, {'xvalue': 105, 'yvalue': -44}]}}},
                {'interval': {'start': 1700003600, 'duration': 3600},
                 'DERControl': {'opModMaxLimW': 100}}]}
    i61850 = _bundled_pipeline(parser, '2030.5', '61850').execute(sep2)
    entries = i61850['FSCH']['x-SchdEntr']
    assert len(entries) == 2
    assert entries[0]['StrTm'] == 1700000000 and entries[0]['SchdIntv'] == 3600
    assert entries[0]['DWMX'] == {'WMaxSpt': 80, 'Mod': True}                  # an active control implies its mode enable
    assert entries[0]['DHFW'] == {'HzStr': 0.036, 'WGra': 5}
    assert entries[0]['DVVR'] == {'VVArCrv': {'numPts': 2, 'crvPts': [{'xVal': 95, 'yVal': 44}, {'xVal': 105, 'yVal': -44}]},
                                  'OplTmsMax': 5}
    assert entries[1] == {'StrTm': 1700003600, 'SchdIntv': 3600, 'DWMX': {'WMaxSpt': 100, 'Mod': True}}
    # The immediate settings still map at the top level, and schedule content does not leak into it.
    # 2030.5's excitation is true for under-excited; the hub's PFGnExtQud is true for over-excited (equals(0)).
    assert i61850['DFPF'] == {'Mod': True, 'PFGnTgtSpt': 0.95, 'PFGnExtQud': False}
    assert 'DWMX' not in i61850 and 'DVVR' not in i61850
    back = _bundled_pipeline(parser, '61850', '2030.5').execute(i61850)
    assert back['DERControlList'] == [
        {'interval': {'start': 1700000000, 'duration': 3600},
         'DERControl': {'opModMaxLimW': 80, 'opModFreqDroop': {'dBOF': 0.036, 'kOF': 5}},
         'DERCurve': {'opModVoltVar': {'CurveData': [{'xvalue': 95, 'yvalue': 44}, {'xvalue': 105, 'yvalue': -44}], 'openLoopTms': 5}}},
        {'interval': {'start': 1700003600, 'duration': 3600}, 'DERControl': {'opModMaxLimW': 100}}]
    assert 'DERControlList' not in _bundled_pipeline(parser, '61850', '2030.5').execute({'DFPF': {'PFGnExtQud': 1}})
    # Formats without a schedule container simply do not carry it.
    assert 'FSCH' not in _bundled_pipeline(parser, '61850', 'sunspec').execute(i61850)


def test_bundled_openfmb_profiles_round_trip_through_61850_and_stay_valid(parser):
    from icm.models.openfmb import PROFILES
    from icm.models.openfmb.generate_samples import example_profiles
    examples = example_profiles()
    to_61850 = _bundled_pipeline(parser, 'openfmb.ess', '61850')
    reading = to_61850.execute(examples['ESSReadingProfile'])
    assert reading['MMXU']['TotW'] == -25000.0 and reading['MMXU']['PhV']['phsB']['mag'] == 239.8
    status = to_61850.execute(examples['ESSStatusProfile'])
    assert status['DSTO']['UseSocPct'] == 63.5 and status['DINV']['GriMod'] == 'GridConnectModeKind_VSI_PQ'
    capability = to_61850.execute(examples['ESSCapabilityProfile'])
    assert capability['DGEN']['WMaxRtg'] == 100000.0 and capability['DSTO']['WhRtg'] == 200000.0
    assert capability['LPHD']['PhyNam'] == {'vendor': 'ACME', 'model': 'BESS-200'}
    control = to_61850.execute(examples['ESSControlProfile'])
    entries = control['FSCH']['x-SchdEntr']
    assert [e['StrTm'] for e in entries] == [1700000000, 1700003600]
    assert entries[0]['DVVR']['VVArCrv']['numPts'] == 4 and entries[0]['DVVR']['VVArCrv']['crvPts'][0] == {'xVal': 0.92, 'yVal': 0.44}
    assert entries[0]['DHFW'] == {'HzStr': 0.036, 'WGra': 0.05, 'Mod': True}
    assert entries[1]['DFPF'] == {'Mod': True, 'PFGnTgtSpt': 0.95, 'PFGnExtQud': True}
    # The entry in effect now (the latest start time already reached) is also lifted to the hub's top level.
    assert all(control[ln] == value for ln, value in entries[1].items() if ln != 'StrTm')
    assert 'DVVR' not in control                                   # the superseded first entry stays in FSCH only
    # Back to OpenFMB: each part validates as its profile, and the schedule points survive.
    back = _bundled_pipeline(parser, '61850', 'openfmb.ess')
    merged = {}
    for out in (reading, status, capability, control):
        for k, v in out.items():
            merged.setdefault(k, {}).update(v)
    result = back.execute(merged)
    for profile, key in [('ESSReadingProfile', 'essReading'), ('ESSStatusProfile', 'essStatus'),
                         ('ESSCapabilityProfile', 'essCapability'), ('ESSControlProfile', 'essControl')]:
        PROFILES[profile].model_validate({key: result[key]})
    all_points = result['essControl']['essControlFSCC']['essControlScheduleFSCH']['ValDCSG']['crvPts']
    points = [p for p in all_points if 'startTime' in p]
    immediate = [p for p in all_points if 'startTime' not in p]
    assert [p['startTime']['seconds'] for p in points] == [1700000000, 1700003600]
    assert len(immediate) == 1 and immediate[0]['control']['pFOperation'] == points[1]['control']['pFOperation']
    assert points[0]['control']['voltVarOperation']['crvPts'] == examples['ESSControlProfile']['essControl'][
        'essControlFSCC']['essControlScheduleFSCH']['ValDCSG']['crvPts'][0]['control']['voltVarOperation']['crvPts']
    assert result['essReading']['readingMMXU']['W']['net']['cVal']['mag'] == -25000.0
    # 61850 top-level controls become an immediate point (no start time) ahead of the scheduled ones.
    immediate = back.execute({'DFPF': {'PFGnTgtSpt': 0.9}, 'FSCH': {'x-SchdEntr': [{'StrTm': 5, 'DWMX': {'WMaxSpt': 0.5}}]}})
    points = immediate['essControl']['essControlFSCC']['essControlScheduleFSCH']['ValDCSG']['crvPts']
    assert points == [{'control': {'pFOperation': {'pFParameter': {'pFGnTgtMxVal': 0.9}}}},
                      {'startTime': {'seconds': 5}, 'control': {'limitWOperation': {'wMaxSptVal': 0.5}}}]
    # Solar uses its own keys, including the capitalised schedule field.
    solar = _bundled_pipeline(parser, 'openfmb.solar', '61850').execute(examples['SolarControlProfile'])
    assert len(solar['FSCH']['x-SchdEntr']) == 2
    solar_back = _bundled_pipeline(parser, '61850', 'openfmb.solar').execute(solar)
    PROFILES['SolarControlProfile'].model_validate({'solarControl': solar_back['solarControl']})
    assert 'SolarControlScheduleFSCH' in solar_back['solarControl']['solarControlFSCC']


def test_bundled_openfmb_profile_formats_add_headers_and_split_profiles():
    """openfmb.<device>.<profile> formats: one profile with its header, as an adapter publishes it on one topic."""
    from icm.models.openfmb import PROFILES
    from icm.models.openfmb.generate_samples import example_profiles
    from interoperability.transform_registry import MAX_HOPS
    registry = TransformRegistry()
    registry.update_registry([d for f in _bundled_transform_files() for d in json.loads(f.read_text())])
    examples = example_profiles()
    device = {'mrid': 'ess-mrid-1', 'name': 'ESS 1'}
    for hub, profile, header, equipment, body in [
            ('openfmb.ess', 'ESSReadingProfile', 'readingMessageInfo', 'ess', 'essReading'),
            ('openfmb.ess', 'ESSStatusProfile', 'statusMessageInfo', 'ess', 'essStatus'),
            ('openfmb.ess', 'ESSCapabilityProfile', 'capabilityMessageInfo', 'ess', 'essCapability'),
            ('openfmb.ess', 'ESSControlProfile', 'controlMessageInfo', 'ess', 'essControl'),
            ('openfmb.solar', 'SolarReadingProfile', 'readingMessageInfo', 'solarInverter', 'solarReading'),
            ('openfmb.solar', 'SolarControlProfile', 'controlMessageInfo', 'solarInverter', 'solarControl')]:
        leaf = f"{hub}.{profile[len(hub.split('.')[1]):-len('Profile')].lower()}"      # openfmb.ess.reading
        # The whole device dict (every profile's body at once) narrows to one profile plus a fresh header.
        chain, retention, path = registry.lookup_scored('61850', leaf)
        assert path[-2:] == [hub, leaf] and len(path) - 1 <= MAX_HOPS
        assert retention > 0            # the whole-group copy of the profile body counts the fields beneath it
        chain, _, _ = registry.lookup_scored(hub, leaf)
        pipeline = TransformParser(context=device).build_transform_from_schema(chain)
        combined = {k: v for name in examples if name.startswith(hub.split('.')[1].upper() if hub == 'openfmb.ess' else 'Solar')
                    for k, v in examples[name].items() if not k.endswith('MessageInfo') and k not in ('ess', 'solarInverter')}
        result = pipeline.execute(combined)
        assert set(result) == {header, equipment, body} and result[body] == examples[profile][body]
        assert result[equipment] == {'conductingEquipment': {'mRID': 'ess-mrid-1', 'namedObject': {'name': 'ESS 1'}}}
        info = result[header]['messageInfo']
        assert len(info['identifiedObject']['mRID']) == 36 and info['messageTimeStamp']['seconds'] > 1_700_000_000
        PROFILES[profile].model_validate(result)
        # Back to the combined format drops the header, so inbound profiles reach openfmb_to_61850.json.
        back, _, _ = registry.lookup_scored(leaf, hub)
        assert TransformParser().build_transform_from_schema(back).execute(result) == {body: examples[profile][body]}
    # The device path an adapter resolves fits the hop budget: device -> sunspec -> 61850 -> openfmb.ess -> leaf.
    registry.register('dev', 'sunspec', {'#': 'transform(device_values())', '701': {'W': 'transform[701_W]()'}})
    chain, _, path = registry.lookup_scored('dev', 'openfmb.ess.reading')
    assert path == ['dev', 'sunspec', '61850', 'openfmb.ess', 'openfmb.ess.reading']
    result = TransformParser(context={'mrid': 'm'}).build_transform_from_schema(chain).execute([{'701_W': 5}, {}])
    assert result['essReading']['readingMMXU']['W']['net']['cVal']['mag'] == 5 and result['ess']['conductingEquipment']['mRID'] == 'm'


def test_openfmb_reaches_other_protocols_through_the_61850_hub():
    from icm.models.openfmb.generate_samples import example_profiles
    registry = TransformRegistry()
    registry.update_registry([d for f in _bundled_transform_files() for d in json.loads(f.read_text())])
    chain, retention, path = registry.lookup_scored('openfmb.ess', 'sunspec')
    # The only OpenFMB edges lead to 61850; from there the scorer picks the route retaining the most fields,
    # which may legitimately pass through another hub.
    assert path[:2] == ['openfmb.ess', '61850'] and path[-1] == 'sunspec' and retention > 0
    parser = TransformParser()
    reading = parser.build_transform_from_schema(chain).execute(example_profiles()['ESSReadingProfile'])
    assert reading['701']['W'] == -25000.0 and reading['701']['Hz'] == 60.01
    assert registry.lookup_scored('2030.5', 'openfmb.solar')[2][-2:] == ['61850', 'openfmb.solar']
    assert len(registry.field_universe('openfmb.ess')) < len(registry.field_universe('openfmb'))


def test_bundled_curves_round_trip_sunspec_2030_5_and_61850(parser):
    sunspec = {'705': {'Ena': 1, 'Crv': [{'ActPt': 2, 'VRef': 100, 'VRefAutoEna': 1, 'VRefAutoTms': 300, 'RspTms': 5,
                                          'Pt': [{'V': 95, 'Var': 44}, {'V': 105, 'Var': -44}, {'V': 0, 'Var': 0}]}]},
               '708': {'Crv': [{'MustTrip': {'ActPt': 2, 'Pt': [{'V': 120, 'Tms': 0.16}, {'V': 110, 'Tms': 13}, {'V': 0, 'Tms': 0}]},
                                'MomCess': {'ActPt': 1, 'Pt': [{'V': 118, 'Tms': 1}]}}]},
               '710': {'Crv': [{'MustTrip': {'ActPt': 1, 'Pt': [{'Hz': 62, 'Tms': 0.16}]}}]}}
    sep2 = _bundled_pipeline(parser, 'sunspec', '2030.5').execute(sunspec)
    assert sep2['DERCurve']['opModVoltVar'] == {
        'vRef': 100, 'autonomousVRefEnable': 1, 'autonomousVRefTimeConstant': 300, 'openLoopTms': 5,
        'CurveData': [{'xvalue': 95, 'yvalue': 44}, {'xvalue': 105, 'yvalue': -44}]}   # only ActPt points
    assert sep2['DERCurve']['opModHVRTMomentaryCessation'] == {'CurveData': [{'xvalue': 118, 'yvalue': 1}]}
    assert sep2['DERCurve']['opModHFRTMustTrip'] == {'CurveData': [{'xvalue': 62, 'yvalue': 0.16}]}
    # Writing back emits the single active curve with its point count.
    expected_sunspec = {'705': {'Crv': [{'ActPt': 2, 'VRef': 100, 'VRefAutoEna': 1, 'VRefAutoTms': 300, 'RspTms': 5,
                                         'Pt': [{'V': 95, 'Var': 44}, {'V': 105, 'Var': -44}]}]},
                        '708': {'Crv': [{'MustTrip': {'ActPt': 2, 'Pt': [{'V': 120, 'Tms': 0.16}, {'V': 110, 'Tms': 13}]},
                                         'MomCess': {'ActPt': 1, 'Pt': [{'V': 118, 'Tms': 1}]}}]},
                        '710': {'Crv': [{'MustTrip': {'ActPt': 1, 'Pt': [{'Hz': 62, 'Tms': 0.16}]}}]}}
    assert _bundled_pipeline(parser, '2030.5', 'sunspec').execute(sep2) == expected_sunspec
    i61850 = _bundled_pipeline(parser, '2030.5', '61850').execute(sep2)
    assert i61850['DVVR']['VVArCrv'] == {'numPts': 2, 'crvPts': [{'xVal': 95, 'yVal': 44}, {'xVal': 105, 'yVal': -44}]}
    assert i61850['PTOV2']['TmVChr'] == {'numPts': 1, 'crvPts': [{'xVal': 118, 'yVal': 1}]}
    assert _bundled_pipeline(parser, '61850', '2030.5').execute(i61850)['DERCurve'] == {
        k: {a: v for a, v in mode.items() if a != 'vRef'} for k, mode in sep2['DERCurve'].items()}
    from_sunspec = _bundled_pipeline(parser, 'sunspec', '61850').execute(sunspec)
    assert from_sunspec['DVVR']['VVArCrv'] == i61850['DVVR']['VVArCrv']
    assert from_sunspec['PTOF1'] == i61850['PTOF1']
    back = _bundled_pipeline(parser, '61850', 'sunspec').execute(from_sunspec)
    assert {k: back[k]['Crv'] for k in expected_sunspec} == {k: v['Crv'] for k, v in expected_sunspec.items()}
