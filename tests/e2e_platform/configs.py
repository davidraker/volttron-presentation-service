"""Configuration of the platform under test, written as files for the config store.

Six devices for the platform driver (SunSpec, DNP3 and IEEE 2030.5, each in the client role towards an external
device and in the served role towards an external master), the presentation service's formats, transforms and
mappings (a canonical resource per device and an OpenFMB reading and control alias each), the Device Adapter's
bridges (device to device, plus device to OpenFMB topic in ``bus`` mode) and the Message Bus Adapter."""
import csv
import json
from dataclasses import dataclass, field
from pathlib import Path

from interoperability.discovery import ieee2030_5 as mirror_gen
from interoperability.discovery.device_formats import dnp3_device_transforms, resource_mappings
from interoperability.openfmb_bus import topic_of

TESTS = Path(__file__).resolve().parents[1]
SUNSPEC_CASE = TESTS / 'integration' / 'fake_sunspec' / 'transform_scaling'
DNP3_CASE = TESTS / 'integration' / 'fake_dnp3' / 'transform_scaling'

DEVICES = ('SunSpec', 'DNP3', '2030.5')
ROLES = ('client', 'served')
CLIENT_FORMAT = {'SunSpec': 'fake_sunspec_pv', 'DNP3': 'fake_dnp3_der', '2030.5': 'fake_sunspec_pv_sep2'}
SERVED_FORMAT = {'SunSpec': 'fake_sunspec_pv', 'DNP3': 'fake_dnp3_der_served', '2030.5': 'fake_sunspec_pv_sep2_served'}
OPENFMB_FAMILY = {'SunSpec': 'solar', 'DNP3': 'ess', '2030.5': 'ess'}
PROFILE = {'solar': 'Solar', 'ess': 'ESS'}
PROTO = {'solar': ('solarmodule.SolarReadingProfile', 'solarmodule.SolarControlProfile'),
         'ess': ('essmodule.ESSReadingProfile', 'essmodule.ESSControlProfile')}
MRID = {('SunSpec', 'client'): '7d1a2b3c-0000-4000-8000-000000000001', ('SunSpec', 'served'): '7d1a2b3c-0000-4000-8000-000000000011',
        ('DNP3', 'client'): '9c2e4f10-0000-4000-8000-000000000002', ('DNP3', 'served'): '9c2e4f10-0000-4000-8000-000000000012',
        ('2030.5', 'client'): '5e6f7a80-0000-4000-8000-000000000003', ('2030.5', 'served'): '5e6f7a80-0000-4000-8000-000000000013'}
DNP3_TELEMETRY_POINTS = ['AI_536', 'AI_537', 'AI_3', 'AI_2']
SUNSPEC_METER_POINTS = ['701_W', '701_W_SF', '701_Hz', '701_Hz_SF']           # the OpenFMB party feeds var and voltage
DEVICE_ADAPTER, BUS_ADAPTER, SERVICE, DRIVER = 'platform.device_adapter', 'platform.bus_adapter', 'platform.presentation', 'platform.driver'


def uai(protocol, role):
    return ['matrix', protocol, role]


def device_topic(protocol, role):
    return f'devices/matrix/{protocol}/{role}'


def roles(kind, src, dst):
    """Which role of each party a path uses: our side's device at the source and at the target."""
    if kind == 'telemetry':
        return ('served' if src == '2030.5' else 'client'), ('client' if dst == '2030.5' else 'served')
    return ('client' if src == '2030.5' else 'served'), ('served' if dst == '2030.5' else 'client')


def bridge_name(kind, src, dst):
    return f'{kind}_{src}_{dst}'.replace('.', '_')


def openfmb_alias(protocol, role, kind):
    family = OPENFMB_FAMILY[protocol]
    return ['openfmb', f'{family}module', f'{PROFILE[family]}{"Reading" if kind == "reading" else "Control"}Profile', MRID[(protocol, role)]]


def rows_of(path):
    with Path(path).open(newline='') as f:
        return list(csv.DictReader(f))


def write_csv(path: Path, rows: list[dict]):
    columns = []
    for row in rows:
        for key in row:
            if key not in columns:
                columns.append(key)
    with path.open('w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


@dataclass
class Endpoints:
    """Where the external parties are and where the platform's served devices listen (all on this host)."""
    sunspec_device: tuple[str, int]              # external SunSpec inverter (Modbus TCP slave)
    sunspec_served_port: int                     # the Modbus unit the platform serves
    dnp3_outstation: tuple[str, int]             # external outstation
    dnp3_served_port: int                        # the outstation the platform serves
    sep2_server_url: str                         # external 2030.5 server
    sep2_served_port: int                        # the 2030.5 server the platform serves
    sep2_notify_port: int
    mqtt: tuple[str, int]
    certs: dict                                  # device_cert, device_key, ca, notify_cert, notify_key, server_cert, server_key
    served_client_lfdi: str                      # LFDI of the external 2030.5 client registered with our served server
    served_client_pin: int
    client_pin: int
    dnp3_ids: dict = field(default_factory=lambda: {'master_id': 2, 'outstation_id': 1})
    poll_interval: float = 2.0


@dataclass
class StoreEntry:
    identity: str
    name: str
    path: Path
    kind: str = 'json'       # json | csv


@dataclass
class PlatformConfigs:
    entries: list[StoreEntry]
    bridges: list[dict]
    outbound_topics: list[str]
    inbound_topics: list[str]


def device_config(driver_type: str, registry_name: str, remote: dict, interval: float) -> dict:
    return {'driver_type': driver_type, 'remote_config': {'driver_type': driver_type, **remote},
            'registry_config': f'config://registry_configs/{registry_name}', 'interval': interval,
            'publish_depth_first_all': True, 'publish_depth_first_multi': True, 'timezone': 'UTC'}


def served_rows(rows: list[dict], remote_writable_from_writable: bool) -> list[dict]:
    """Rows of a served device: the platform writes every point, so the client-role Writable column goes; for a
    Modbus unit the master may write what the device's registry called writable."""
    out = []
    for row in rows:
        new = {k: v for k, v in row.items() if k != 'Writable'}
        if remote_writable_from_writable:
            new['Remote Writable'] = 'TRUE' if row.get('Writable', '').strip().upper() == 'TRUE' else 'FALSE'
        out.append(new)
    return out


def build(work: Path, ep: Endpoints, openfmb_mode: str) -> PlatformConfigs:
    """Write every configuration file under ``work`` and describe what to store where."""
    work.mkdir(parents=True, exist_ok=True)
    entries: list[StoreEntry] = []

    def store(identity, name, content, kind='json'):
        path = work / identity / name.replace('/', '__')
        path.parent.mkdir(parents=True, exist_ok=True)
        if kind == 'json':
            path.write_text(json.dumps(content, indent=2) + '\n')
        else:
            write_csv(path, content)
        entries.append(StoreEntry(identity, name, path, kind))

    # ---- platform driver: registries and devices --------------------------------------------------------------------
    sunspec_rows = rows_of(SUNSPEC_CASE / 'fake_sunspec_pv.modbus.csv')
    dnp3_rows = rows_of(DNP3_CASE / 'fake_dnp3_der.dnp3.csv')
    # The 1815.2 profile scales analog outputs with multipliers, so they travel as integers: the reference outstation
    # accepts g41v1/g41v2 commands only. The case's registry (variation 4, 32-bit float) is overridden to variation 1.
    for row in dnp3_rows:
        if str(row.get('Group')) == '40':
            row['Variation'] = '1'
    registry = mirror_gen.load_registry(SUNSPEC_CASE / 'presentation_config.json')
    mirror = mirror_gen.discover_mirror(registry, 'fake_sunspec_pv')
    sep2_rows = mirror_gen.registry_rows(mirror)
    store(DRIVER, 'registry_configs/sunspec_client.csv', sunspec_rows, 'csv')
    store(DRIVER, 'registry_configs/sunspec_served.csv', served_rows(sunspec_rows, True), 'csv')
    store(DRIVER, 'registry_configs/dnp3_client.csv', dnp3_rows, 'csv')
    store(DRIVER, 'registry_configs/dnp3_served.csv', served_rows(dnp3_rows, False), 'csv')
    store(DRIVER, 'registry_configs/sep2_client.csv', sep2_rows, 'csv')
    store(DRIVER, 'registry_configs/sep2_served.csv', served_rows(sep2_rows, False), 'csv')
    c = ep.certs
    store(DRIVER, device_topic('SunSpec', 'client'), device_config('modbus', 'sunspec_client.csv', {
        'transport_protocol': 'tcp', 'device_address': ep.sunspec_device[0], 'port': ep.sunspec_device[1], 'unit_id': 1, 'timeout': 5}, ep.poll_interval))
    store(DRIVER, device_topic('SunSpec', 'served'), device_config('modbus', 'sunspec_served.csv', {
        'driver_role': 'slave', 'transport_protocol': 'tcp', 'bind_host': '127.0.0.1', 'port': ep.sunspec_served_port, 'unit_id': 1}, ep.poll_interval))
    store(DRIVER, device_topic('DNP3', 'client'), device_config('dnp3', 'dnp3_client.csv', {
        'outstation_ip': ep.dnp3_outstation[0], 'port': ep.dnp3_outstation[1], 'response_timeout': 5, 'integrity_poll_interval': 0,
        **ep.dnp3_ids}, ep.poll_interval))
    store(DRIVER, device_topic('DNP3', 'served'), device_config('dnp3', 'dnp3_served.csv', {
        'driver_role': 'outstation', 'bind_host': '127.0.0.1', 'port': ep.dnp3_served_port, **ep.dnp3_ids}, ep.poll_interval))
    store(DRIVER, device_topic('2030.5', 'client'), device_config('ieee2030_5', 'sep2_client.csv', {
        'server_url': ep.sep2_server_url, 'cert_path': str(c['device_cert']), 'key_path': str(c['device_key']), 'ca_path': str(c['ca']),
        'subscribe': True, 'notify_host': '127.0.0.1', 'notify_bind_host': '127.0.0.1', 'notify_port': ep.sep2_notify_port,
        'notify_cert_path': str(c['notify_cert']), 'notify_key_path': str(c['notify_key']), 'poll_rate_floor': 1, 'poll_rate_ceiling': 5,
        'response_timeout': 10}, ep.poll_interval))
    store(DRIVER, device_topic('2030.5', 'served'), device_config('ieee2030_5', 'sep2_served.csv', {
        'driver_role': 'server', 'bind_host': '127.0.0.1', 'port': ep.sep2_served_port, 'cert_path': str(c['server_cert']),
        'key_path': str(c['server_key']), 'ca_path': str(c['ca']), 'client_lfdi': ep.served_client_lfdi, 'client_pin': ep.served_client_pin,
        'poll_rate': 2, 'immediate_control_duration': 300, 'state_dir': str(work / 'sep2_state')}, ep.poll_interval))

    # ---- presentation service: the cases, the served formats, the devices and their OpenFMB aliases -----------------------
    sunspec_case = json.loads((SUNSPEC_CASE / 'presentation_config.json').read_text())
    dnp3_case = json.loads((DNP3_CASE / 'presentation_config.json').read_text())
    formats = {**sunspec_case['formats'], **dnp3_case['formats'], SERVED_FORMAT['DNP3']: dnp3_case['formats'][CLIENT_FORMAT['DNP3']]}
    transforms = sunspec_case['transforms'] + dnp3_case['transforms'] + \
        dnp3_device_transforms(SERVED_FORMAT['DNP3'], [r['Volttron Point Name'] for r in dnp3_rows], served=True).definitions
    for fmt, served in ((CLIENT_FORMAT['2030.5'], False), (SERVED_FORMAT['2030.5'], True)):
        fragment = mirror_gen.presentation_fragment(fmt, mirror, 'unused', ['unused'], served=served)
        formats.update(fragment['formats'])
        transforms += fragment['transforms']
    mappings = []
    for protocol in DEVICES:
        family = OPENFMB_FAMILY[protocol]
        for role, fmt in (('client', CLIENT_FORMAT[protocol]), ('served', SERVED_FORMAT[protocol])):
            aliases = {f'openfmb_{kind}': {'format': f'openfmb.{family}.{kind}', 'encoding': 'protobuf',
                                           'parameters': {'mrid': MRID[(protocol, role)], 'name': f'{protocol} {role}'},
                                           'uai': openfmb_alias(protocol, role, kind)} for kind in ('reading', 'control')}
            mappings += resource_mappings(fmt, device_topic(protocol, role), uai(protocol, role), aliases)
    store(SERVICE, 'config', {'formats': formats, 'transforms': transforms, 'mappings': mappings})

    # ---- device adapter ---------------------------------------------------------------------------------------------
    bridges = []
    for kind in ('telemetry', 'control'):
        for src in DEVICES:
            for dst in DEVICES:
                if src != dst:
                    src_role, dst_role = roles(kind, src, dst)
                    bridge = {'name': bridge_name(kind, src, dst), 'source': uai(src, src_role), 'target': uai(dst, dst_role)}
                    if kind == 'telemetry' and src == 'DNP3':
                        # The reference outstation serves the whole DER profile with zeros; only the points it is given
                        # values for are bridged, as a deployment would choose which of a device's points to mirror.
                        bridge['points'] = DNP3_TELEMETRY_POINTS
                    if kind == 'telemetry' and src == 'SunSpec' and dst == 'DNP3':
                        # The inverter's meter only, so the ratings and settings the 2030.5 client reports have the
                        # served outstation's nameplate points to themselves (scale factors travel with the values).
                        bridge['points'] = SUNSPEC_METER_POINTS
                    bridges.append(bridge)
    outbound, inbound = [], []
    for protocol in DEVICES:
        tel_src, tel_dst = roles('telemetry', protocol, 'OpenFMB')[0], roles('telemetry', 'OpenFMB', protocol)[1]
        ctl_src, ctl_dst = roles('control', protocol, 'OpenFMB')[0], roles('control', 'OpenFMB', protocol)[1]
        outbound += [topic_of(openfmb_alias(protocol, tel_src, 'reading')), topic_of(openfmb_alias(protocol, ctl_src, 'control'))]
        inbound += [topic_of(openfmb_alias(protocol, tel_dst, 'reading')), topic_of(openfmb_alias(protocol, ctl_dst, 'control'))]
        if openfmb_mode == 'bus':
            bridges += [
                {'name': bridge_name('telemetry', protocol, 'OpenFMB'), 'source': uai(protocol, tel_src),
                 'target': {'uai': openfmb_alias(protocol, tel_src, 'reading'), 'bus': True}},
                {'name': bridge_name('telemetry', 'OpenFMB', protocol), 'source': {'uai': openfmb_alias(protocol, tel_dst, 'reading'), 'bus': True},
                 'target': uai(protocol, tel_dst)},
                {'name': bridge_name('control', protocol, 'OpenFMB'), 'source': uai(protocol, ctl_src),
                 'target': {'uai': openfmb_alias(protocol, ctl_src, 'control'), 'bus': True}},
                {'name': bridge_name('control', 'OpenFMB', protocol), 'source': {'uai': openfmb_alias(protocol, ctl_dst, 'control'), 'bus': True},
                 'target': uai(protocol, ctl_dst)}]
    store(DEVICE_ADAPTER, 'config', {'presentation_service': SERVICE, 'driver': DRIVER, 'bridges': bridges, 'echo_window': 5.0})

    # ---- message bus adapter ----------------------------------------------------------------------------------------
    store(BUS_ADAPTER, 'config', {'bus_type': 'mqtt', 'mode': 'relay' if openfmb_mode == 'bus' else 'translate',
                                  'device_adapter': DEVICE_ADAPTER, 'proxy_registration_timeout': 60,
                                  'adapters': [{'name': 'site', 'host': ep.mqtt[0], 'port': ep.mqtt[1],
                                                'local_subscriptions': outbound, 'remote_subscriptions': inbound}]})
    return PlatformConfigs(entries, bridges, outbound, inbound)
