"""The service's resolve RPC: alias parameters and encoding reach the caller, with the format's protobuf message."""
import json
from importlib import resources
from pathlib import Path

import pytest

import interoperability.agent as agent_module

CASE = Path(__file__).parent / 'integration' / 'fake_sunspec' / 'transform_scaling' / 'presentation_config.json'


@pytest.fixture
def service(monkeypatch):
    class FakeConfig:
        def set_default(self, name, value): pass
        def subscribe(self, callback, actions=None, pattern=None): pass

    monkeypatch.setattr(agent_module.Agent, '__init__', lambda self, **kwargs: setattr(self, 'vip', type('V', (), {'config': FakeConfig()})()))
    service = agent_module.PresentationService()
    package_root = resources.files('interoperability')
    case = json.loads(CASE.read_text())
    service.configure_main(None, 'NEW', {
        'formats': {**service._load_bundled_formats(package_root.joinpath('formats')), **case['formats']},
        'transforms': service._load_bundled_definitions(package_root.joinpath('transforms')) + case['transforms'],
        'mappings': case['mappings']})
    return service, case


def test_bundled_formats_declare_the_openfmb_profiles(service):
    svc, _ = service
    assert svc.transform_registry.format_spec('openfmb.ess.reading') == {'hub': False, 'proto': 'essmodule.ESSReadingProfile'}
    assert svc.transform_registry.format_spec('openfmb.solar.control')['proto'] == 'solarmodule.SolarControlProfile'
    assert svc.transform_registry.format_spec('fake_sunspec_pv')['scaling'] == 'transform'
    assert svc.transform_registry.format_spec('never.declared') == {}


def test_resolve_plain_alias(service):
    svc, _ = service
    result = svc.resolve(('site1', 'pv_sunspec'))
    assert result['target_format'] == 'sunspec' and result['publication_topic'] == 'devices/site1/feeder1/pv_inverter/all'
    assert result['parameters'] == {} and result['encoding'] == 'json' and 'codec' not in result
    assert result['transform'][0]['#'] == 'transform(device_values())'
    assert svc.resolve(('site1', 'pv_sunspec', 'W'))['target_format'] == 'sunspec'   # non-strict prefix fallback
    assert svc.resolve(('elsewhere',)) == {}


def test_resolve_openfmb_alias_carries_parameters_and_codec(service):
    svc, case = service
    alias = next(m for m in case['mappings'] if m['resource']['data_format'] == 'openfmb.solar.reading')
    result = svc.resolve(tuple(alias['uai']))
    assert result['data_format'] == 'fake_sunspec_pv' and result['target_format'] == 'openfmb.solar.reading'
    assert result['parameters'] == alias['resource']['parameters'] and result['encoding'] == 'protobuf'
    assert result['codec'] == {'encoding': 'protobuf', 'proto': 'solarmodule.SolarReadingProfile'}
    assert len(result['transform']) == 4


def test_resolve_protobuf_without_proto_declaration_is_an_error(service):
    svc, _ = service
    svc.mapping_engine.ingest_mappings([{'uai': ['site1', 'pv_binary'], 'resource_type': 'alias',
                                         'resource': {'data_format': 'sunspec', 'owner': 'x', 'encoding': 'protobuf',
                                                      'references': ['site1', 'pv_inverter']}}])
    with pytest.raises(ValueError, match='declares no "proto"'):
        svc.resolve(('site1', 'pv_binary'))
