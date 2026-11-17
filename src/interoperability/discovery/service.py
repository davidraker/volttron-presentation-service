"""Discovery as a service call: run a generator and return the entries a device needs, without writing files.

The configuration UI's Discover dialog calls ``PresentationService.discover(protocol, options)`` through the
platform's web service; what comes back is the review step: the driver's device entry, the registry rows, the
service configuration fragment (format, transforms, canonical resource and aliases) and a summary with the device's
identity and remote id. The client stores them as one pending set.

Options common to every protocol: ``topic`` (the device topic; required), ``uai`` (the canonical resource's UAI,
default the topic's segments with ``devices`` in front), ``registry_name`` (default ``registry_configs/<last topic
segment>.csv``), ``format_name`` (default the last topic segment), ``interval``, ``publish`` (``all`` or ``multi``),
``aliases`` (``{alias name or UAI: format or spec}``, default none). Per protocol:

- ``sunspec``: ``host``, ``port``, ``unit`` for a reachable unit, or ``device_json`` (the text of a pysunspec2 device
  description) for an offline scan; ``scaling`` (``transform`` or ``driver``); ``role`` (``client`` or ``server``).
- ``dnp3``: ``profile_json`` (the text of an IEEE 1815.2 test-tool profile) or ``indexes`` (``{table: [index, …]}``), or
  neither, in which case the outstation at ``outstation_ip``/``port`` is scanned (an integrity poll lists its points);
  ``master_id``, ``outstation_id``; ``role``; for a served outstation ``bind_host``, ``conformance`` (``1815``, ``1547``, ``none``) and
  either ``compose`` (``{'functions': [key | {'key', 'optional'}], 'include_optional'}``, the point set composed from the
  standard by :mod:`interoperability.discovery.dnp3_builder`), ``registry_csv`` (a dnp3 registry's text) or ``profile_json``;
  a served point set is validated against the standard and the result is in ``notes``.
- ``ieee2030_5``: ``device_format`` (the format of the device to mirror), ``mirror_format``, ``server_url`` and the
  certificate paths; ``role``.
"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any

from . import dnp3 as dnp3_discovery
from .device_formats import scaling_mode
from . import ieee2030_5 as sep2_discovery
from . import sunspec as sunspec_discovery
from .device_formats import resource_mappings

from .sunspec import NAMEPLATE_MODELS


def _common(options: dict) -> dict:
    topic = str(options.get('topic') or '').strip('/')
    if not topic:
        raise ValueError('a device topic is required')
    stem = topic.split('/')[-1]
    uai = options.get('uai') or ['devices', *topic.split('/')]
    uai = [s for s in uai.split('/') if s] if isinstance(uai, str) else list(uai)
    publish = options.get('publish', 'multi')
    return {'topic': topic, 'stem': stem, 'uai': uai, 'registry_name': options.get('registry_name') or f'registry_configs/{stem}.csv',
            'format_name': options.get('format_name') or stem, 'interval': options.get('interval'),
            'publish': publish if publish in ('all', 'multi') else 'multi', 'aliases': options.get('aliases') or {}}


def _device_entry(config: dict, common: dict) -> dict:
    """A generator's device config with the client's publish mode and interval applied."""
    entry = dict(config)
    entry.pop('publish_depth_first_all', None)
    entry['publish_depth_first_all' if common['publish'] == 'all' else 'publish_depth_first_multi'] = True
    if common['interval'] is not None:
        entry['interval'] = common['interval']
    elif 'interval' in entry and entry['interval'] == 5:
        entry.pop('interval')       # the generators' sample interval; blank inherits the driver's default
    return entry


def _entries(driver_identity: str, service_identity: str, common: dict, device_entry: dict, rows: list[dict], fragment: dict) -> list[dict]:
    return [{'identity': driver_identity, 'name': common['registry_name'], 'type': 'csv', 'data': rows},
            {'identity': driver_identity, 'name': f"devices/{common['topic']}", 'type': 'json', 'data': device_entry},
            {'identity': service_identity, 'name': 'config', 'type': 'json', 'fragment': fragment}]


def discover(protocol: str, options: dict, registry, *, driver_identity: str = 'platform.driver',
             service_identity: str = 'platform.presentation') -> dict:
    protocol = (protocol or '').lower()
    common = _common(options)
    if protocol == 'sunspec':
        return _discover_sunspec(options, common, driver_identity, service_identity)
    if protocol == 'dnp3':
        return _discover_dnp3(options, common, driver_identity, service_identity)
    if protocol in ('ieee2030_5', '2030.5', 'sep2'):
        return _discover_sep2(options, common, registry, driver_identity, service_identity)
    raise ValueError(f'unknown discovery protocol {protocol!r}; one of sunspec, dnp3, ieee2030_5')


# ------------------------------------------------------------------------------------------------ SunSpec
def sunspec_data_source(point) -> str:
    """Scale factors and nameplate models are read once; everything else is polled."""
    return 'poll_once' if point.is_scale_factor or point.model_id in NAMEPLATE_MODELS else 'short_poll'


def _discover_sunspec(options: dict, common: dict, driver_identity: str, service_identity: str) -> dict:
    scaling = scaling_mode(options.get('scaling'))        # default: the driver applies the factors
    if options.get('device_json'):
        with tempfile.NamedTemporaryFile('w', suffix='.json', delete=False) as handle:
            handle.write(options['device_json'] if isinstance(options['device_json'], str) else json.dumps(options['device_json']))
        device = sunspec_discovery.discover_file(handle.name)
        Path(handle.name).unlink(missing_ok=True)
        source = 'scan file'
    else:
        host, port, unit = options.get('host'), int(options.get('port') or 502), int(options.get('unit') or 1)
        if not host:
            raise ValueError('sunspec discovery needs a host (or a device_json scan)')
        device = sunspec_discovery.discover_tcp(host, port, unit, timeout=float(options.get('timeout') or 5.0))
        source = f'{host}:{port} unit {unit}'
    rows = sunspec_discovery.modbus_registry_rows(device, scaling)
    device_config = sunspec_discovery.device_config('modbus', common['registry_name'], host=options.get('host'),
                                                   port=int(options.get('port') or 502), unit=int(options.get('unit') or 1))
    role = options.get('role', 'client')
    if role != 'client':
        # A served unit: the platform's Modbus slave listens where bind_host says; a unit address is nobody's to reach.
        remote = device_config['remote_config']
        remote['driver_role'] = 'slave'
        remote.pop('device_address', None)
        remote['bind_host'] = options.get('bind_host') or '0.0.0.0'
        for row in rows:
            row['data_source'] = 'server'
    fragment, notes = sunspec_discovery.presentation_config(device, common['format_name'], f"devices/{common['topic']}",
                                                            common['uai'], scaling, common['aliases'])
    fragment['mappings'] = resource_mappings(common['format_name'], f"devices/{common['topic']}", common['uai'], common['aliases'])
    _set_publication(fragment, common)
    remote = device_config['remote_config']
    remote_id = [remote.get('transport_protocol', 'tcp'), str(remote.get('device_address')), str(remote.get('port')), str(remote.get('unit_id'))]
    return {'protocol': 'sunspec', 'source': source, 'identity': device.identity, 'remote_id': remote_id,
            'models': sorted({p.model_id for p in device.points}), 'points': len(rows), 'notes': device.notes + notes,
            'entries': _entries(driver_identity, service_identity, common, _device_entry(device_config, common), rows, fragment)}


# ------------------------------------------------------------------------------------------------ DNP3
def _discover_dnp3(options: dict, common: dict, driver_identity: str, service_identity: str) -> dict:
    from . import dnp3_builder
    served = options.get('role', 'client') != 'client'
    conformance = options.get('conformance') or ('1815' if served else 'none')
    if options.get('compose') is not None:
        # A served outstation composed from the standard: the conformance core, the chosen function groups, their pairs.
        spec = options['compose'] or {}
        indexes = dnp3_builder.compose(conformance, spec.get('functions') or [], bool(spec.get('include_optional')))
        if not indexes:
            raise ValueError('nothing to serve: choose a conformance level or at least one function group')
        device = dnp3_discovery.discover_indexes(indexes, None, common['stem'])
        chosen = [c.get('key') if isinstance(c, dict) else c for c in spec.get('functions') or []]
        source = f'composed from IEEE 1815.2 ({dnp3_builder.CONFORMANCE_LABELS[conformance]}' + (f', function groups {", ".join(map(str, chosen))}' if chosen else '') + ')'
    elif options.get('registry_csv'):
        indexes = dnp3_builder.indexes_from_registry(options['registry_csv'])
        device = dnp3_discovery.discover_indexes(indexes, None, common['stem'])
        source = 'registry file'
    elif options.get('profile_json'):
        with tempfile.NamedTemporaryFile('w', suffix='.json', delete=False) as handle:
            handle.write(options['profile_json'] if isinstance(options['profile_json'], str) else json.dumps(options['profile_json']))
        device = dnp3_discovery.discover_profile(handle.name)
        Path(handle.name).unlink(missing_ok=True)
        source = 'device profile'
    elif options.get('indexes'):
        device = dnp3_discovery.discover_indexes(options['indexes'], options.get('values'), common['stem'])
        source = 'point indexes'
    elif options.get('outstation_ip'):
        # A reachable outstation: an integrity poll says which indexes it implements; 1815.2 says what they mean.
        from .dnp3_scan import scan_outstation_isolated
        host, port = options['outstation_ip'], int(options.get('port') or 20000)
        master_id, outstation_id = int(options.get('master_id') or 2), int(options.get('outstation_id') or 1)
        try:
            scanned = scan_outstation_isolated(host, port, master_id, outstation_id, timeout=float(options.get('timeout') or 10.0))
        except RuntimeError as e:
            raise ValueError(str(e)) from e
        if not scanned.indexes:
            raise ValueError(f'the outstation at {host}:{port} reported no points; ' + '; '.join(scanned.notes))
        device = dnp3_discovery.discover_indexes(scanned.indexes, scanned.values, common['stem'])
        device.notes.extend(scanned.notes)
        source = f'outstation {host}:{port} (master {master_id}, outstation {outstation_id})'
    else:
        raise ValueError('dnp3 discovery needs an outstation address to scan, a profile_json, a registry_csv, indexes, or a compose specification')
    if served or options.get('validate'):
        # The point set against the standard: what a served outstation claims, it should serve.
        listing: dict[str, list[int]] = {}
        for point in device.points:
            listing.setdefault(point.table, []).append(point.index)
        validation = dnp3_builder.validate(listing, conformance)
        device.notes.extend(validation.notes())
    scaling = scaling_mode(options.get('scaling'))        # default: the driver applies the factors
    rows = dnp3_discovery.dnp3_registry_rows(device, scaling)
    device_config = dnp3_discovery.device_config('dnp3', common['registry_name'], outstation_ip=options.get('outstation_ip', '127.0.0.1'),
                                                 port=int(options.get('port') or 20000), master_id=int(options.get('master_id') or 2),
                                                 outstation_id=int(options.get('outstation_id') or 1))
    if served:
        # A served outstation listens on bind_host:port for the external master; it has no outstation to reach.
        remote = device_config['remote_config']
        remote['driver_role'] = 'outstation'
        remote.pop('outstation_ip', None)
        remote['bind_host'] = options.get('bind_host') or '0.0.0.0'
        for row in rows:
            row['data_source'] = 'server'
    from .device_formats import dnp3_device_transforms, device_format_declaration
    names = [row.get('volttron_point_name') or row.get('point_name') for row in rows]
    built = dnp3_device_transforms(common['format_name'], names, scaling=scaling, served=served)
    fragment = {'formats': {common['format_name']: device_format_declaration(names, scaling)}, 'transforms': built.definitions,
                'mappings': resource_mappings(common['format_name'], f"devices/{common['topic']}", common['uai'], common['aliases'])}
    _set_publication(fragment, common)
    remote = device_config['remote_config']
    return {'protocol': 'dnp3', 'source': source, 'identity': {'name': device.name} if hasattr(device, 'name') else {},
            'remote_id': ['dnp3', str(remote.get('bind_host') if served else remote.get('outstation_ip')), str(remote.get('port')), str(remote.get('outstation_id'))],
            'points': len(rows), 'notes': getattr(device, 'notes', []),
            'entries': _entries(driver_identity, service_identity, common, _device_entry(device_config, common), rows, fragment)}


# ------------------------------------------------------------------------------------------------ IEEE 2030.5
def _discover_sep2(options: dict, common: dict, registry, driver_identity: str, service_identity: str) -> dict:
    device_format = options.get('device_format')
    if not device_format:
        raise ValueError('ieee2030_5 discovery mirrors an existing device: device_format is required')
    mirror = sep2_discovery.discover_mirror(registry, device_format, schedules=bool(options.get('schedules', True)))
    rows = sep2_discovery.registry_rows(mirror)
    served = options.get('role', 'client') != 'client'
    kwargs = {k: options[k] for k in ('server_url', 'cert_path', 'key_path', 'ca_path', 'pin', 'notify_host', 'notify_port') if k in options}
    device_config = sep2_discovery.device_config(common['registry_name'], **kwargs)
    if served:
        device_config['remote_config']['driver_role'] = 'server'
        for row in rows:
            row['data_source'] = 'server'
    fragment = sep2_discovery.presentation_fragment(common['format_name'], mirror, f"devices/{common['topic']}", common['uai'],
                                                    alias=options.get('alias') or None, served=served)     # default: <name>_2030_5
    _set_publication(fragment, common)
    remote = device_config['remote_config']
    notes = []
    if not served and not (remote.get('cert_path') and remote.get('key_path')):
        notes.append('no client certificate and key: the 2030.5 client cannot register with the server until cert_path and key_path (and the CA) are set on the device')
    return {'protocol': 'ieee2030_5', 'source': f'mirror of {device_format}', 'identity': {}, 'remote_id': ['2030.5', str(remote.get('server_url'))],
            'points': len(rows), 'notes': notes,
            'entries': _entries(driver_identity, service_identity, common, _device_entry(device_config, common), rows, fragment)}


def _set_publication(fragment: dict, common: dict) -> None:
    """The canonical resource publishes on the topic the client chose (all or multi)."""
    for mapping in fragment.get('mappings', []):
        if str(mapping.get('resource_type', '')).lower() in ('canon', 'canonical'):
            mapping['resource']['publication_topic'] = f"devices/{common['topic']}/{common['publish']}"
