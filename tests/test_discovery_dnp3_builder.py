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
    assert all(set(g) >= {'key', 'purpose', 'section', 'points', 'mandatory_1815', 'mandatory_1547', 'optional'} for g in as_json['groups'])


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
