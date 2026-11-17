"""Composing a served IEEE 1815.2 outstation from the standard, and checking any point set against it."""
import json
from importlib import resources

import pytest

from interoperability.discovery import dnp3_builder as builder
from interoperability.discovery import service as discovery_service

pytest.importorskip('dnp3.mesa')
PROFILE_1547 = resources.files('dnp3.mesa') / 'data' / 'profiles' / 'mandatory_1547.json'


def profile_indexes(path):
    data = json.loads(path.read_text())
    return {t: sorted(int(p['point_index']) for p in (data[t].get('points', []) if isinstance(data[t], dict) else data[t])) for t in builder.TABLES if t in data}


def test_catalog_groups_the_point_list_by_function():
    groups = {g.purpose: g for g in builder.catalog()}
    volt_var = groups['Volt-Var']
    assert volt_var.key == 'volt_var' and volt_var.section == 'functions'
    assert len(volt_var.mandatory_1815) == 27 and len(volt_var.optional) == 15 and 'AI_297' in volt_var.points
    assert groups['Scheduling'].section == 'scheduling' and groups['Curve'].section == 'curves'
    sections = [g.section for g in builder.catalog()]
    assert sections == sorted(sections, key=['functions', 'scheduling', 'curves', 'equipment', 'extensions'].index), 'functions first, then the bulk'
    as_json = builder.catalog_json()
    assert {c['key'] for c in as_json['conformance']} == {'1815', '1547', 'none'} and as_json['conformance'][2]['points'] == 0
    assert all(set(g) >= {'key', 'purpose', 'section', 'points', 'mandatory_1815', 'mandatory_1547', 'optional', 'optional_points', 'references_curves'} for g in as_json['groups'])
    assert {g['section'] for g in as_json['groups']} == {'functions', 'extensions'}, 'curves, schedules and equipment are capabilities, not groups'
    vv = next(g for g in as_json['groups'] if g['key'] == 'volt_var')
    assert vv['references_curves'] and len(vv['optional_points']) == 15 and {'name', 'uid', 'description', 'pair'} <= set(vv['optional_points'][0])
    assert as_json['curves']['pairs_max'] == 100 and as_json['curves']['pairs_floor'] == {'1815': 20, '1547': 4, 'none': 0}
    assert set(as_json['curves']['referenced_by']) >= {'volt_var', 'volt_watt', 'watt_var', 'freq_watt_curve', 'volt_ride_through', 'freq_ride_through'}
    schedules = {s['key']: s for s in as_json['schedules']}
    assert schedules['schedules']['blocks_floor']['1815'] == 20 and schedules['schedules']['entries_floor']['1815'] == 20 and schedules['bc_schedules']['blocks_max'] == 100
    assert [e['key'] for e in as_json['equipment']] == ['meter', 'der_unit', 'inverter', 'battery'] and all(e['instances_defined'] == 1 for e in as_json['equipment'])


def test_compose_adds_the_core_the_groups_and_their_pairs():
    core = builder.compose('1815')
    assert sum(len(v) for v in core.values()) >= 952, 'every 1815.2 mandatory point, at least'
    nothing = builder.compose('none')
    assert nothing == {}
    one = builder.compose('none', ['volt_var'])
    volt_var = {g.key: g for g in builder.catalog()}['volt_var']
    names = {f'{t}_{i}' for t, v in one.items() for i in v}
    assert set(volt_var.mandatory_1815) <= names and not (set(volt_var.optional) <= names)
    assert 'AO_217' in names and 'AI_297' in names, 'the curve index AO and the AI that reads it back travel together'
    with_optional = builder.compose('none', [{'key': 'volt_var', 'optional': True}])
    assert sum(len(v) for v in with_optional.values()) > sum(len(v) for v in one.values())
    assert builder.compose('none', ['Volt-Var']) == one, 'the purpose label is accepted as the key'
    with pytest.raises(ValueError, match='unknown IEEE 1815.2 function group'):
        builder.compose('none', ['teleportation'])
    with pytest.raises(ValueError, match='conformance'):
        builder.compose('2030')


def test_compose_for_1547_covers_the_test_tools_1547_profile():
    """The test tool's mandatory_1547 profile is the showroom's served registry; the composition contains it (the
    library's reconciled point list adds the curve points the tool keeps implicit, and the read-back pairs)."""
    from icm.models.ieee1815_2 import POINTS, PointType
    composed = builder.compose('1547')
    expected = profile_indexes(PROFILE_1547)
    for table, indexes in expected.items():
        left_out = sorted(set(indexes) - set(composed.get(table, [])))
        # the profile adds points of its own choosing (system meter readings, counters); none of them is mandatory
        assert all(not POINTS[PointType(table)][i].mandatory_1547 for i in left_out if i in POINTS[PointType(table)]), f'{table}: {left_out[:8]}'
        assert all(i in composed.get(table, []) for i in indexes if i in POINTS[PointType(table)] and POINTS[PointType(table)][i].mandatory_1547)


def test_validate_reports_missing_mandatory_unknown_and_broken_pairs():
    ok = builder.validate(builder.compose('1547'), '1547')
    assert ok.conformant and ok.notes()[0].startswith('all IEEE 1547 mandatory')
    partial = builder.validate({'AI': [297, 9999], 'AO': []}, '1547')
    assert not partial.conformant and partial.unknown == {'AI': [9999]} and ('AI_297', 'AO_217') in partial.broken_pairs
    assert len(partial.missing_mandatory) > 100
    notes = ' '.join(partial.notes())
    assert 'by function group' in notes and 'not in the IEEE 1815.2 point list: 9999' in notes and 'AI_297 without AO_217' in notes
    assert any(g['purpose'] == 'Volt-Var' and g['present'] == 1 for g in partial.groups)
    free = builder.validate({'AI': [297]}, 'none')
    assert free.missing_mandatory == [] and 'mandatory' not in ' '.join(free.notes())


def test_indexes_from_registry_reads_the_point_names():
    text = 'point_name,volttron_point_name,object_group,variation,index\nDGEN.VMinRtg,AI_2,30,6,2\nDOPR.OutWSet,AO_87,40,1,87\nX,BO_17,10,2,17\n'
    assert builder.indexes_from_registry(text) == {'AI': [2], 'AO': [87], 'BO': [17]}
    with pytest.raises(ValueError, match='names no IEEE 1815.2 points'):
        builder.indexes_from_registry('Point Name,Address\nW,40084\n')


def test_discover_composes_and_validates_a_served_outstation():
    result = discovery_service.discover('dnp3', {'topic': 'site/served', 'role': 'server', 'bind_host': '127.0.0.1', 'port': 20001,
                                                 'conformance': '1547', 'compose': {'functions': ['volt_var', {'key': 'freq_watt', 'optional': True}]}}, None)
    assert result['source'].startswith('composed from IEEE 1815.2 (IEEE 1547 mandatory subset, function groups volt_var, freq_watt)')
    registry = next(e for e in result['entries'] if e['type'] == 'csv')
    names = {r['volttron_point_name'] for r in registry['data']}
    assert 'AI_297' in names and {r['data_source'] for r in registry['data']} == {'server'}
    device = next(e for e in result['entries'] if e['name'].startswith('devices/'))
    assert device['data']['remote_config']['driver_role'] == 'outstation' and device['data']['remote_config']['bind_host'] == '127.0.0.1'
    assert any(n.startswith('all IEEE 1547 mandatory') for n in result['notes'])
    assert any('complete function groups' in n and 'Freq-Watt' in n for n in result['notes'])
    fragment = next(e for e in result['entries'] if e.get('fragment'))['fragment']
    assert {(t['input_format'], t['output_format']) for t in fragment['transforms']} >= {('served', '1815.2.inputs'), ('1815.2.outputs', 'served')}


def test_discover_takes_a_registry_csv_and_validates_it():
    text = 'point_name,volttron_point_name\nDVVR.VVArCrv,AI_297\n'
    result = discovery_service.discover('dnp3', {'topic': 'site/served', 'role': 'server', 'registry_csv': text, 'conformance': 'none'}, None)
    assert result['source'] == 'registry file' and result['points'] == 1, 'a file is taken as given: the AO the AI reads back is not added, the note says it is missing'
    assert any('AI_297 without AO_217' in n for n in result['notes'])


def test_discover_without_a_point_set_is_a_clear_error():
    with pytest.raises(ValueError, match='compose'):
        discovery_service.discover('dnp3', {'topic': 'site/served', 'role': 'server'}, None)
    with pytest.raises(ValueError, match='nothing to serve'):
        discovery_service.discover('dnp3', {'topic': 'site/served', 'role': 'server', 'conformance': 'none', 'compose': {}}, None)


def test_compose_sizes_curves_schedules_and_equipment():
    n = lambda listing: sum(len(v) for v in listing.values())  # noqa: E731
    plain = builder.compose('none', ['volt_var'], curves=False)
    auto = builder.compose('none', ['volt_var'])                     # Volt-Var references a curve: the buffer comes along, 4 pairs when the level sets no floor
    names = {f'{t}_{i}' for t, v in auto.items() for i in v}
    assert 'AI_328' in names and 'AO_245' in names and 'AI_333' in names and 'AI_341' not in names, 'selector, first pair write and read-back; not the fifth pair'
    assert n(auto) > n(plain)
    twenty = builder.compose('none', ['volt_var'], curves={'pairs': 20})
    assert n(twenty) == n(auto) + 16 * 4
    assert builder.validate(builder.compose('1547', curves={'pairs': 1}), '1547').curve_pairs == 4, 'the conformance floor wins over a smaller request'
    no_curves_needed = builder.compose('none', ['constant_pf'])
    assert 'AI_328' not in {f'{t}_{i}' for t, v in no_curves_needed.items() for i in v}
    sched = builder.compose('none', schedules={'schedules': {'held': 3, 'entries': 5}})
    s_names = {f'{t}_{i}' for t, v in sched.items() for i in v}
    assert 'AI_3000' in s_names and 'AI_3506' in s_names and 'AI_3509' not in s_names, 'header, the third status block, not the fourth'
    assert 'AI_3012' in s_names and 'AI_3016' in s_names
    meter = builder.compose('none', equipment=['meter'])
    assert n(meter) == 66 and all(5000 <= i < 5037 for i in meter.get('AI', []))
    with pytest.raises(ValueError, match='unknown schedule area'):
        builder.compose('none', schedules={'weekly': {'held': 1}})
    with pytest.raises(ValueError, match='unknown equipment block'):
        builder.compose('none', equipment=['toaster'])


def test_compose_takes_a_list_of_optional_points_and_rejects_strangers():
    base = builder.compose('none', ['volt_var'], curves=False)
    some = builder.compose('none', [{'key': 'volt_var', 'optional': ['AI_291']}], curves=False)
    names = {f'{t}_{i}' for t, v in some.items() for i in v} - {f'{t}_{i}' for t, v in base.items() for i in v}
    assert names == {'AI_291', 'AO_213'}, 'the chosen optional point and the AO it reads back'
    with pytest.raises(ValueError, match='not among its optional points'):
        builder.compose('none', [{'key': 'volt_var', 'optional': ['AI_297']}])     # mandatory, not optional


def test_validate_flags_functions_that_reference_curves_without_a_buffer():
    v = builder.validate(builder.compose('none', ['volt_var'], curves=False), 'none')
    assert v.curves_unserved == ['Volt-Var'] and not v.conformant and 'no curve edit buffer is served' in ' '.join(v.notes())
    ok = builder.validate(builder.compose('none', ['volt_var']), 'none')
    assert ok.curves_unserved == [] and ok.curve_pairs == 4 and 'curve edit buffer with 4 X/Y pairs' in ' '.join(ok.notes())


def test_discover_records_stored_curves_and_schedules_on_the_device():
    result = discovery_service.discover('dnp3', {'topic': 'site/served', 'role': 'server', 'conformance': 'none',
                                                 'compose': {'functions': ['volt_var'], 'curves': {'pairs': 10, 'stored': 4}, 'schedules': {'schedules': {'held': 6, 'entries': 10}}, 'equipment': ['meter']}}, None)
    device = next(e for e in result['entries'] if e['name'].startswith('devices/'))
    assert device['data']['equipment_specific_fields'] == {'ieee1815_2': {'curves_stored': 4, 'schedules_held': 6}}
    registry = next(e for e in result['entries'] if e['type'] == 'csv')
    names = {r['volttron_point_name'] for r in registry['data']}
    assert 'AI_5000' in names and 'AI_3515' in names and 'AI_3518' not in names
