"""Discover with the server role: the platform serves the device (DNP3 outstation, Modbus slave) to an external master.
The result is the whole configuration, not just the driver entry: the registry with every point served, the device
entry in the served role listening on bind_host, the device format, the transforms to and from the 1815.2 hubs, and the
canonical resource. That is how a served device is set up from the UI without the demonstration tool."""
import json
from importlib import resources

import pytest

from interoperability.discovery import service as discovery_service

pytest.importorskip('dnp3.mesa')
PROFILE = resources.files('dnp3.mesa') / 'data' / 'profiles' / 'mandatory_1547.json'


def _by_kind(result):
    entries = result['entries']
    registry = next(e for e in entries if e['type'] == 'csv')
    device = next(e for e in entries if e['name'].startswith('devices/'))
    fragment = next(e for e in entries if e.get('fragment'))['fragment']
    return registry, device, fragment


def test_served_dnp3_outstation_from_a_profile_is_complete():
    result = discovery_service.discover('dnp3', {'topic': 'site/served', 'profile_json': json.loads(PROFILE.read_text()), 'role': 'server',
                                                 'bind_host': '127.0.0.1', 'port': 20001, 'master_id': 2, 'outstation_id': 1, 'publish': 'all'}, None)
    registry, device, fragment = _by_kind(result)
    remote = device['data']['remote_config']
    assert remote['driver_role'] == 'outstation' and remote['bind_host'] == '127.0.0.1' and remote['port'] == 20001
    assert 'outstation_ip' not in remote, 'a served outstation reaches no outstation'
    assert result['remote_id'] == ['dnp3', '127.0.0.1', '20001', '1']
    assert registry['data'] and {row['data_source'] for row in registry['data']} == {'server'}
    assert set(fragment['formats']) == {'served'}
    assert {(t['input_format'], t['output_format']) for t in fragment['transforms']} == {
        ('served', '1815.2.inputs'), ('1815.2.inputs', 'served'), ('served', '1815.2.outputs'), ('1815.2.outputs', 'served')}
    canonical = next(m for m in fragment['mappings'] if m['resource_type'] == 'canonical')
    assert canonical['uai'] == ['devices', 'site', 'served'] and canonical['resource']['data_format'] == 'served'
    assert canonical['resource']['publication_topic'] == 'devices/site/served/all'


def test_served_dnp3_defaults_to_every_interface():
    result = discovery_service.discover('dnp3', {'topic': 'site/served', 'profile_json': json.loads(PROFILE.read_text()), 'role': 'server'}, None)
    _, device, _ = _by_kind(result)
    assert device['data']['remote_config']['bind_host'] == '0.0.0.0'


def test_client_dnp3_keeps_the_outstation_address():
    result = discovery_service.discover('dnp3', {'topic': 'site/der', 'profile_json': json.loads(PROFILE.read_text()), 'outstation_ip': '10.0.0.9'}, None)
    _, device, _ = _by_kind(result)
    remote = device['data']['remote_config']
    assert remote['outstation_ip'] == '10.0.0.9' and 'bind_host' not in remote and 'driver_role' not in remote
