"""The service's resolve RPC: alias parameters and encoding reach the caller, with the format's protobuf message."""
import json
from importlib import resources
from pathlib import Path

import pytest

import interoperability.agent as agent_module
from interoperability.transform_parser import TransformParser

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


def test_resolve_write_direction_and_field_hint(service):
    """A caller about to write the device asks for the chain from its message's format into the device's own, scored on
    the fields the message carries; the path and retention come back with the chain."""
    svc, _ = service
    read = svc.resolve(('site1', 'pv_inverter'), as_format='2030.5')
    assert read['path'][0] == 'fake_sunspec_pv' and read['path'][-1] == '2030.5' and 0 < read['retention'] <= 1
    write = svc.resolve(('site1', 'pv_inverter'), as_format='2030.5', direction='write', fields=['DERControl.opModMaxLimW'])
    assert write['path'][0] == '2030.5' and write['path'][-1] == 'fake_sunspec_pv' and write['retention'] == 1.0
    assert write['rpc_topic'] == 'devices/site1/feeder1/pv_inverter'
    out = TransformParser().build_transform_from_schema(write['transform']).execute({'DERControl': {'opModMaxLimW': 50}})
    assert out == {'704_WMaxLimPct': 50, '704_WMaxLimPctEna': 1}
    with pytest.raises(ValueError):
        svc.resolve(('site1', 'pv_inverter'), as_format='2030.5', direction='sideways')


def test_resolve_reports_the_uais_and_transform_chain_scores_fields(service):
    svc, _ = service
    alias = svc.resolve(('openfmb', 'solarmodule', 'SolarReadingProfile', '7d1a2b3c-0000-4000-8000-000000000001'))
    assert alias['canonical_uai'] == ['site1', 'pv_inverter'] and alias['alias_uais'] == [['openfmb', 'solarmodule', 'SolarReadingProfile', '7d1a2b3c-0000-4000-8000-000000000001']]
    assert alias['codec'] == {'encoding': 'protobuf', 'proto': 'solarmodule.SolarReadingProfile'}
    canonical = svc.resolve(('site1', 'pv_inverter'), as_format='openfmb.solar.reading')
    assert canonical['alias_uais'] == [] and canonical['codec'] == {'encoding': 'json', 'proto': 'solarmodule.SolarReadingProfile'}
    chain = svc.transform_chain('fake_sunspec_pv', 'openfmb.solar.reading', fields=['701_W', '701_W_SF'])
    assert chain['path'][0] == 'fake_sunspec_pv' and chain['path'][-1] == 'openfmb.solar.reading' and chain['transform'] and 0 < chain['retention'] <= 1
    assert svc.transform_chain('sunspec', 'sunspec') == {'transform': [], 'path': ['sunspec'], 'retention': 1.0}


def test_a_stored_config_builds_on_the_bundled_definitions(monkeypatch):
    """A deployment's config entry carries only its device formats, transforms and mappings (what the discovery tools
    write); the bundled hub transforms and OpenFMB formats must still be there."""
    class FakeConfig:
        def set_default(self, name, value): self.default = (name, value)
        def subscribe(self, callback, actions=None, pattern=None): pass
    monkeypatch.setattr(agent_module.Agent, '__init__', lambda self, **kwargs: setattr(self, 'vip', type('V', (), {'config': FakeConfig()})()))
    svc = agent_module.PresentationService()
    assert svc.vip.config.default == ('config', {})
    svc.configure_main(None, 'NEW', json.loads(CASE.read_text()))
    chain, retention, path = svc.transform_registry.lookup_scored('fake_sunspec_pv', 'openfmb.solar.reading')
    assert path[0] == 'fake_sunspec_pv' and path[-1] == 'openfmb.solar.reading' and chain
    assert svc.transform_registry.format_spec('openfmb.ess.reading')['proto'] == 'essmodule.ESSReadingProfile'
    assert svc.resolve(('site1', 'pv_inverter'))['data_format'] == 'fake_sunspec_pv'
    svc.configure_main(None, 'UPDATE', {})                                   # an empty entry keeps the bundled base
    assert svc.transform_registry.lookup('sunspec', '61850')
