"""The RPCs the configuration UI calls: formats and transforms described, chains reported hop by hop, patterns
compiled, messages previewed, references checked, and discovery run as a call."""
import json
from importlib import resources
from pathlib import Path

import pytest

import interoperability.agent as agent_module
from interoperability.transform_registry import TransformNotFoundError

CASE = Path(__file__).parent / 'integration' / 'fake_sunspec' / 'transform_scaling' / 'presentation_config.json'
SCAN = Path(__file__).parent / 'integration' / 'fake_sunspec' / 'transform_scaling' / 'discovery.json'


@pytest.fixture
def service(monkeypatch):
    class FakeConfig:
        def set_default(self, name, value): pass
        def subscribe(self, callback, actions=None, pattern=None): pass
    monkeypatch.setattr(agent_module.Agent, '__init__', lambda self, **kwargs: setattr(self, 'vip', type('V', (), {'config': FakeConfig()})()))
    svc = agent_module.PresentationService()
    package_root = resources.files('interoperability')
    case = json.loads(CASE.read_text())
    svc.configure_main(None, 'NEW', {
        'formats': {**svc._load_bundled_formats(package_root.joinpath('formats')), **case['formats']},
        'transforms': svc._load_bundled_definitions(package_root.joinpath('transforms')) + case['transforms'],
        'mappings': case['mappings']})
    return svc


def test_list_formats_marks_hubs_declarations_and_edges(service):
    formats = service.list_formats()
    assert formats['61850']['hub'] and formats['61850']['universe'] > 100 and 'sunspec' in formats['61850']['edges_out']
    assert formats['openfmb.solar.reading']['declared'] and formats['openfmb.solar.reading']['proto'] == 'solarmodule.SolarReadingProfile'
    assert formats['fake_sunspec_pv']['declared'] and formats['fake_sunspec_pv']['scaling'] == 'transform' and not formats['fake_sunspec_pv']['hub']


def test_list_transforms_tells_bundled_from_local(service):
    edges = {(e['input'], e['output']): e for e in service.list_transforms()}
    assert edges[('sunspec', '61850')]['origin'] == 'bundled' and edges[('sunspec', '61850')]['fields'] > 20
    assert edges[('fake_sunspec_pv', 'sunspec')]['origin'] == 'local'
    assert all(0 <= e['retention'] <= 1 for e in edges.values() if e['retention'] is not None)


def test_describe_transform_has_dotted_mappings_and_the_pattern(service):
    described = service.describe_transform('sunspec', '61850')
    assert described['input'] == 'sunspec' and isinstance(described['pattern'], dict)
    assert any(m['source'].startswith('705.') for m in described['mappings']) and all('.' in m['target'] or m['target'] for m in described['mappings'])
    assert all(0 <= m['fidelity'] <= 1 for m in described['mappings'])
    assert isinstance(described['unmapped_targets'], list) and described['source_universe']
    with pytest.raises(TransformNotFoundError):
        service.describe_transform('sunspec', 'nowhere')


def test_edge_report_is_json_friendly(service):
    report = service.edge_report('sunspec', '2030.5')
    assert report['classification'] in ('no alternative', 'adds coverage', 'subset of alternative')
    assert all(isinstance(v, (list, str, bool, int, float, type(None))) for v in report.values())


def test_chain_report_walks_the_hops(service):
    report = service.chain_report('fake_sunspec_pv', 'openfmb.solar.reading')
    assert report['path'][0] == 'fake_sunspec_pv' and report['path'][-1] == 'openfmb.solar.reading'
    assert len(report['hops']) == len(report['path']) - 1
    first = report['hops'][0]
    assert first['input'] == 'fake_sunspec_pv' and first['in'] >= first['kept'] >= 0 and first['lost'] == len(first['lost_fields']) or first['lost'] > 40
    assert report['targets'] and all('target' in t and 'source' in t for t in report['targets'])
    assert all(set(u) == {'target', 'lost_at'} for u in report['unmapped_targets'])
    assert 0 <= report['retention'] <= 1


def test_compile_pattern_reports_mappings_or_the_error(service):
    good = service.compile_pattern({'DVVR': {'ModEna': 'transform[705, Ena](cast_value(bool))'}}, 'sunspec')
    assert good['ok'] and good['mappings'][0]['target'] == 'DVVR.ModEna' and good['mappings'][0]['source'] == '705.Ena'
    assert good['unknown_sources'] == []
    unknown = service.compile_pattern({'X': 'transform[999, Nope]()'}, 'sunspec')
    assert unknown['ok'] and unknown['unknown_sources'] == ['999.Nope']
    bad = service.compile_pattern({'X': 'transform[705, Ena](no_such_function())'})
    assert bad['ok'] is False and bad['unknown_functions'] == ['no_such_function'] and 'no_such_function' in bad['error']


def test_preview_runs_the_chain_without_side_effects(service):
    scan = json.loads(SCAN.read_text())
    values = {p['name']: p['value'] for p in scan['points'] if p['value'] is not None}
    out = service.preview('fake_sunspec_pv', 'sunspec', values)
    assert out['path'] == ['fake_sunspec_pv', 'sunspec'] and isinstance(out['output'], dict) and out['output']


def test_check_references_is_exported(service):
    result = service.check_references()
    assert set(result) == {'cycles', 'dangling'} and result['cycles'] == []


def test_discover_sunspec_from_a_scan_returns_the_pending_entries(service):
    source = Path(__file__).parent / 'integration' / 'fake_sunspec' / 'device_1547.json'
    result = service.discover('sunspec', {'device_json': source.read_text(), 'topic': 'site1/feeder1/pv', 'host': '10.0.0.21', 'port': 1502})
    assert result['remote_id'] == ['tcp', '10.0.0.21', '1502', '1'] and result['points'] > 50
    names = [e['name'] for e in result['entries']]
    assert names == ['registry_configs/pv.csv', 'devices/site1/feeder1/pv', 'config']
    registry, device, fragment = result['entries']
    assert registry['type'] == 'csv' and any(r['data_source'] == 'poll_once' for r in registry['data']) and any(r['data_source'] == 'short_poll' for r in registry['data'])
    assert device['data']['publish_depth_first_multi'] is True and 'publish_depth_first_all' not in device['data'] and 'interval' not in device['data']
    canonical = next(m for m in fragment['fragment']['mappings'] if m['resource_type'] == 'canonical')
    assert canonical['uai'] == ['devices', 'site1', 'feeder1', 'pv'] and canonical['resource']['publication_topic'] == 'devices/site1/feeder1/pv/multi'
    assert fragment['fragment']['formats'] == {'pv': fragment['fragment']['formats']['pv']}


def test_discover_dnp3_from_indexes(service):
    result = service.discover('dnp3', {'indexes': {'AI': [1, 2], 'AO': [87]}, 'topic': 'site1/outstation', 'role': 'server', 'publish': 'all'})
    registry, device, fragment = result['entries']
    assert all(r['data_source'] == 'server' for r in registry['data']) and device['data']['remote_config']['driver_role'] == 'outstation'
    assert device['data']['publish_depth_first_all'] is True
    assert next(m for m in fragment['fragment']['mappings'] if m['resource_type'] == 'canonical')['resource']['publication_topic'] == 'devices/site1/outstation/all'


def test_discover_rejects_unknown_protocol_and_missing_topic(service):
    with pytest.raises(ValueError):
        service.discover('zigbee', {'topic': 'x'})
    with pytest.raises(ValueError):
        service.discover('sunspec', {'host': 'h'})
