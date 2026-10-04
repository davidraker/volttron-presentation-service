"""End-to-end matrix: telemetry and control between every ordered pair of SunSpec, DNP3, IEEE 2030.5 and OpenFMB,
through the real driver interfaces and proxies in both roles and the interoperability service's chains.

Every protocol is stood up twice in this process, through one real proxy subprocess per protocol:

* SunSpec: a Modbus unit the platform serves (``driver_role: slave``, the fake_sunspec_pv registry with its default
  values) and a Modbus master reading it. The served unit plays the external SunSpec device when SunSpec is the source
  of telemetry or the target of control; the master plays the external SunSpec master when SunSpec is the source of
  control or the target of telemetry.
* DNP3: an outstation the platform serves (``driver_role: outstation``, the fake_dnp3_der registry) and a master.
* IEEE 2030.5: a CSIP server the platform serves (``driver_role: server``, over mutual TLS) and a DER client registered
  with it, both on the fake_sunspec_pv_sep2 mirror rows.
* OpenFMB: the MQTT proxy with paho mocked (no broker), the protobuf codecs and the service's profile transforms.

A served device and a client-role device of the same protocol are different devices to the service, with their own
device formats: the served ones are generated with ``served=True`` (an outstation's inputs and a server's downward
resources are then written by the platform), the client ones as the discovery tools write them today. The service
itself runs in-process (``PresentationService`` with VOLTTRON stubbed) on those formats, transforms and mappings.

For each path the message the source interface produced (a poll, or the pushes a served interface received) is turned
into the target's points and written through the target interface, then the value is checked at the external party:
the master reads the served unit, the served interface receives the master's write, the client interface receives the
server's control, the published protobuf decodes. Who does the transforming and writing is the *writer*:

* ``direct`` (default): the harness itself resolves the chain with ``lookup_scored`` (hinting the fields the message
  carries), executes it and calls ``set_multiple_points`` on the target interface.
* ``device_adapter`` (``E2E_WRITER=device_adapter``): a DeviceAdapterAgent (VOLTTRON stubbed; its RPCs reach the
  in-process service and the interfaces) is configured with one bridge per device-to-device path and the source's
  publication is delivered to it. OpenFMB paths stay with the harness: they are the message bus adapter's job.

Exit status is non-zero if any path fails. Run by test_e2e_matrix.py; ``E2E_LOG`` names the log file.
Arguments: [work dir] [paths], paths as ``telemetry:SunSpec>DNP3,control:OpenFMB>2030.5`` to run a subset."""
from gevent import monkey; monkey.patch_all()
import csv, json, logging, os, socket, sys, tempfile, time, traceback
from importlib import resources
from pathlib import Path
from types import SimpleNamespace
from unittest import mock
from uuid import uuid4

import gevent

logging.basicConfig(filename=os.environ.get('E2E_LOG', '/tmp/e2e_matrix.log'), level=logging.INFO,
                    format='%(asctime)s %(name)s %(levelname)s %(message)s')

import volttron.driver.interfaces.ieee2030_5 as sep2_package
from volttron.driver.base.config import RemoteConfig
from volttron.driver.interfaces.dnp3.dnp3 import Dnp3
from volttron.driver.interfaces.dnp3.config import Dnp3PointConfig
from volttron.driver.interfaces.ieee2030_5.ieee2030_5 import Ieee2030_5
from volttron.driver.interfaces.ieee2030_5.config import Ieee2030_5PointConfig
from volttron.driver.interfaces.modbus.modbus import Modbus
from volttron.driver.interfaces.modbus.config import ModbusPointConfig
from protocol_proxy.protocol.ieee2030_5.identity import lfdi_from_cert
from protocol_proxy.protocol.mqtt import mqtt_proxy as mqtt_module
from protocol_proxy.protocol.mqtt.mqtt_proxy import MQTTProxy

import interoperability.agent as service_module
from interoperability.codecs.openfmb import decode, encode
from interoperability.discovery import ieee2030_5 as mirror_gen
from interoperability.discovery.device_formats import dnp3_device_transforms, dnp3_scaling, resource_mappings
from interoperability.transform_parser import TransformParser

sys.path.insert(0, str(Path(os.environ.get('IEEE2030_5_DRIVER_REPO', Path(sep2_package.__file__).resolve().parents[5])) / 'tests' / 'e2e_loopback'))
from certs import generate_certs                                                      # noqa: E402

HERE = Path(__file__).resolve().parent
TESTS = HERE.parent
SUNSPEC_CASE = TESTS / 'integration' / 'fake_sunspec' / 'transform_scaling'
DNP3_CASE = TESTS / 'integration' / 'fake_dnp3' / 'transform_scaling'
WORK = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(tempfile.mkdtemp(prefix='e2e-matrix-'))
ONLY = set(sys.argv[2].split(',')) if len(sys.argv) > 2 else None
WRITER = os.environ.get('E2E_WRITER', 'direct')

PROTOCOLS = ('SunSpec', 'DNP3', '2030.5', 'OpenFMB')
DEVICES = ('SunSpec', 'DNP3', '2030.5')
CLIENT_FORMAT = {'SunSpec': 'fake_sunspec_pv', 'DNP3': 'fake_dnp3_der', '2030.5': 'fake_sunspec_pv_sep2'}
SERVED_FORMAT = {'SunSpec': 'fake_sunspec_pv', 'DNP3': 'fake_dnp3_der_served', '2030.5': 'fake_sunspec_pv_sep2_served'}
OPENFMB_FAMILY = {'SunSpec': 'solar', 'DNP3': 'ess', '2030.5': 'ess'}           # the OpenFMB profile family used with each partner
PROTO = {'solar': ('solarmodule.SolarReadingProfile', 'solarmodule.SolarControlProfile'),
         'ess': ('essmodule.ESSReadingProfile', 'essmodule.ESSControlProfile')}
MRID = '7d1a2b3c-0000-4000-8000-000000000001'
# The stimulus every path carries: a system meter reading (W, Hz) and an enabled active power limit (percent of WMax).
W, HZ = 4321, 60
LIMIT_PCT = 50
AO_87_RAW = round(LIMIT_PCT / dnp3_scaling('AO_87')[0])      # the 1815.2 profile gives AO_87 a 0.1 multiplier: tenths of a percent
PIN = 111115


def free_port():
    with socket.socket() as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]


class Core: spawn = staticmethod(gevent.spawn)
class Agent:
    core = Core()
    def __init__(self): self.pushed = []
    def publish_push(self, result): self.pushed.append(dict(result))
    def flat(self, prefix=None):
        out = {}
        for values in self.pushed: out.update(values)
        if prefix is None: return out
        return {t[len(prefix) + 1:]: v for t, v in out.items() if t.startswith(prefix + '/')}
    def clear(self): self.pushed.clear()


def wait_for(predicate, timeout=5.0, interval=0.05):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate(): return True
        gevent.sleep(interval)
    return predicate()


def rows_of(path):
    with Path(path).open(newline='') as f:
        return list(csv.DictReader(f))


def leaves(value, prefix=()):
    """Dotted leaf paths of a message (list indices as digits), the field hint for the chain scorer."""
    if isinstance(value, dict):
        for k, v in value.items():
            yield from leaves(v, prefix + (str(k),))
    elif isinstance(value, list):
        for i, v in enumerate(value):
            yield from leaves(v, prefix + (str(i),))
    else:
        yield '.'.join(prefix)


def strip(results, prefix):
    return {t[len(prefix) + 1:]: v for t, v in results.items() if t.startswith(prefix + '/')}


results = []     # (kind, src, dst, ok, path, detail)
def record(kind, src, dst, ok, path, detail):
    results.append((kind, src, dst, bool(ok), path, detail))
    print(f'{"PASS" if ok else "FAIL"} {kind:9} {src:>7} -> {dst:<7} via {path}  {detail}', flush=True)


def wanted(kind, src, dst):
    return ONLY is None or f'{kind}:{src}>{dst}' in ONLY


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


# =============================================================================================== the parties
class Party:
    """One protocol in both roles: ``client`` (master/DER client) and ``served`` (slave/outstation/server)."""
    def __init__(self, name):
        self.name = name
        self.client = self.served = None
        self.client_agent, self.served_agent = Agent(), Agent()
        self.client_prefix, self.served_prefix = device_topic(name, 'client'), device_topic(name, 'served')

    def interface(self, prefix):
        return self.client if prefix == self.client_prefix else self.served

    def write(self, iface, prefix, values):
        """Write a chain's output through an interface, skipping points it does not have (the direct writer)."""
        items = [(f'{prefix}/{k}', v) for k, v in values.items() if f'{prefix}/{k}' in iface.point_map]
        if not items:
            return {}, {}, 0
        r, e = iface.set_multiple_points(items)
        return r, e, len(items)

    def stop(self):
        for iface in (self.client, self.served):
            if iface is not None and iface.ppm is not None:
                for peer in list(getattr(iface.ppm, 'peers', {}).values()):
                    proc = getattr(peer, 'process', None)
                    if proc: proc.terminate()


def setup_sunspec():
    p = Party('SunSpec')
    port = free_port()
    rows = rows_of(SUNSPEC_CASE / 'fake_sunspec_pv.modbus.csv')
    Modbus.default_config = {}
    p.served = Modbus(RemoteConfig(driver_type='modbus', driver_role='slave', transport_protocol='tcp', bind_host='127.0.0.1',
                                   port=port, unit_id=1), driver_agent=p.served_agent)
    # Served rows: the platform writes every point (so no Writable column); the master may write the control points.
    served_rows = [{**{k: v for k, v in r.items() if k != 'Writable'}, 'remote_writable': r['Writable'].strip().upper() == 'TRUE'} for r in rows]
    for row in p.served.prepare_registry_config(served_rows, p.served.config):
        p.served.insert_register(p.served.create_register(ModbusPointConfig(**row)), p.served_prefix)
    p.served.finalize_setup(initial_setup=True)
    assert p.served.proxy_peer is not None and p.served.proxy_peer.socket_params is not None, 'modbus proxy'
    assert wait_for(lambda: f'{p.served_prefix}/701_W' in p.served_agent.flat(), 10), 'served Modbus unit never pushed its table'
    p.client = Modbus(RemoteConfig(driver_type='modbus', transport_protocol='tcp', device_address='127.0.0.1', port=port, unit_id=1,
                                   timeout=5), driver_agent=p.client_agent)
    for row in rows:
        p.client.insert_register(p.client.create_register(ModbusPointConfig(**row)), p.client_prefix)
    p.client.finalize_setup(initial_setup=True)
    assert p.client.proxy_peer is p.served.proxy_peer, 'modbus master on another proxy'
    return p


def setup_dnp3():
    p = Party('DNP3')
    port = free_port()
    rows = rows_of(DNP3_CASE / 'fake_dnp3_der.dnp3.csv')
    device = json.loads((DNP3_CASE / 'fake_dnp3_der.dnp3.device.json').read_text())['remote_config']
    Dnp3.default_config = {}
    p.served = Dnp3(RemoteConfig(driver_type='dnp3', driver_role='outstation', bind_host='127.0.0.1', port=port,
                                 master_id=device['master_id'], outstation_id=device['outstation_id']), driver_agent=p.served_agent)
    served_rows = [{k: v for k, v in r.items() if k != 'Writable'} for r in rows]
    for row in p.served.prepare_registry_config(served_rows, p.served.config):
        p.served.insert_register(p.served.create_register(Dnp3PointConfig(**row)), p.served_prefix)
    p.served.finalize_setup(initial_setup=True)
    assert p.served.proxy_peer is not None and p.served.proxy_peer.socket_params is not None, 'dnp3 proxy'
    p.client = Dnp3(RemoteConfig(**{**device, 'outstation_ip': '127.0.0.1', 'port': port, 'response_timeout': 5,
                                    'integrity_poll_interval': 0}), driver_agent=p.client_agent)
    for row in rows:
        p.client.insert_register(p.client.create_register(Dnp3PointConfig(**row)), p.client_prefix)
    p.client.finalize_setup(initial_setup=True)
    assert p.client.proxy_peer is p.served.proxy_peer, 'dnp3 master on another proxy'
    return p


def setup_sep2(rows):
    p = Party('2030.5')
    port, notify_port = free_port(), free_port()
    certs = generate_certs(WORK / 'tls')
    lfdi = lfdi_from_cert(certs['device_cert'])
    Ieee2030_5.default_config = {}
    p.served = Ieee2030_5(RemoteConfig(driver_type='ieee2030_5', driver_role='server', bind_host='127.0.0.1', port=port,
                                       cert_path=str(certs['server_cert']), key_path=str(certs['server_key']), ca_path=str(certs['ca']),
                                       client_lfdi=lfdi, client_pin=PIN, poll_rate=2, immediate_control_duration=300,
                                       state_dir=str(WORK / 'state')), driver_agent=p.served_agent)
    # In the server role 'writable' means written by the platform (the downward resources); the mirror rows' Writable
    # column describes the client role, so it is dropped and the server-role default applies.
    served_rows = [{k: v for k, v in r.items() if k != 'Writable'} for r in rows]
    for row in p.served.prepare_registry_config(served_rows, p.served.config):
        p.served.insert_register(p.served.create_register(Ieee2030_5PointConfig(**row)), p.served_prefix)
    p.served.finalize_setup(initial_setup=True)
    assert p.served.proxy_peer is not None and p.served.proxy_peer.socket_params is not None, '2030.5 proxy'
    p.client = Ieee2030_5(RemoteConfig(driver_type='ieee2030_5', server_url=f'https://127.0.0.1:{port}', cert_path=str(certs['device_cert']),
                                       key_path=str(certs['device_key']), ca_path=str(certs['ca']), pin=PIN, subscribe=True,
                                       notify_host='127.0.0.1', notify_bind_host='127.0.0.1', notify_port=notify_port,
                                       notify_cert_path=str(certs['notify_cert']), notify_key_path=str(certs['notify_key']),
                                       poll_rate_floor=1, poll_rate_ceiling=5, response_timeout=10), driver_agent=p.client_agent)
    for row in rows:
        p.client.insert_register(p.client.create_register(Ieee2030_5PointConfig(**row)), p.client_prefix)
    p.client.finalize_setup(initial_setup=True)
    assert p.client.proxy_peer is p.served.proxy_peer, '2030.5 client on another proxy'
    def describe(iface):
        result, errors = iface.parse_proxy_response(iface._send('DESCRIBE_SERVER', {}), ['server'])
        return result if not errors else {}
    assert wait_for(lambda: describe(p.client).get('ready') is True, 60), f'2030.5 client never ready: {describe(p.client)}'
    return p


class OpenFmb:
    """The MQTT proxy with paho mocked: publishes are captured, inbound broker messages are injected."""
    def __init__(self):
        manager_id = uuid4()
        with mock.patch.object(mqtt_module.mqtt, 'Client') as client_class:
            self.client = client_class.return_value
            self.client.publish.return_value = SimpleNamespace(rc=mqtt_module.mqtt.MQTT_ERR_SUCCESS)
            self.proxy = MQTTProxy(proxy_id=uuid4(), token=uuid4(), proxy_name='matrix', manager_address='127.0.0.1', manager_port=1,
                                   manager_id=manager_id, manager_token=uuid4(), host='broker', port=1883)
        self.proxy.send = mock.Mock(return_value=True)
        self.proxy.peers[self.proxy.manager] = mock.Mock()

    def publish(self, proto, payload, topic):
        """Our side publishes: the adapter's PUBLISH_REMOTE envelope -> proxy -> paho publish; returns what the broker got."""
        envelope = json.dumps({'topic': topic, 'payload': encode(proto, payload).hex(), 'encoding': 'hex'}).encode('utf8')
        self.proxy.handle_publish_remote.__wrapped__(self.proxy, SimpleNamespace(sender_id=self.proxy.manager), envelope)
        out_topic, out_payload = self.client.publish.call_args.args
        assert out_topic == topic
        return decode(proto, bytes(out_payload))

    def receive(self, proto, payload, topic):
        """The external party publishes: paho on_message -> PUBLISH_LOCAL to the manager; returns the decoded message."""
        self.proxy.on_message(self.client, None, SimpleNamespace(topic=topic, payload=encode(proto, payload), qos=0, retain=False, mid=1))
        message = self.proxy.send.call_args.args[1]
        local = json.loads(message.payload)
        assert local['topic'] == topic
        return decode(proto, bytes.fromhex(local['payload']))


# =============================================================================================== the service
def service_config(dnp3_names):
    """The presentation service's configuration for both cases plus the served devices as their own formats, with a
    canonical resource per device at the harness's topics. Returns the configuration and the 2030.5 mirror rows."""
    sunspec_case = json.loads((SUNSPEC_CASE / 'presentation_config.json').read_text())
    dnp3_case = json.loads((DNP3_CASE / 'presentation_config.json').read_text())
    formats = {**sunspec_case['formats'], **dnp3_case['formats'], SERVED_FORMAT['DNP3']: dnp3_case['formats'][CLIENT_FORMAT['DNP3']]}
    transforms = sunspec_case['transforms'] + dnp3_case['transforms'] + \
        dnp3_device_transforms(SERVED_FORMAT['DNP3'], dnp3_names, served=True).definitions
    mappings = []
    for protocol in ('SunSpec', 'DNP3'):
        for role, fmt in (('client', CLIENT_FORMAT[protocol]), ('served', SERVED_FORMAT[protocol])):
            mappings += resource_mappings(fmt, device_topic(protocol, role), uai(protocol, role), {})
    registry = mirror_gen.load_registry(SUNSPEC_CASE / 'presentation_config.json')
    mirror = mirror_gen.discover_mirror(registry, 'fake_sunspec_pv')
    for role, fmt, served in (('client', CLIENT_FORMAT['2030.5'], False), ('served', SERVED_FORMAT['2030.5'], True)):
        fragment = mirror_gen.presentation_fragment(fmt, mirror, device_topic('2030.5', role), uai('2030.5', role), served=served)
        formats.update(fragment['formats'])
        transforms += fragment['transforms']
        mappings += [m for m in fragment['mappings'] if m['resource_type'] == 'canonical']
    return {'formats': formats, 'transforms': transforms, 'mappings': mappings}, mirror_gen.registry_rows(mirror)


def start_service(config):
    """The interoperability service in-process, VOLTTRON stubbed, on the bundled plus the harness's definitions."""
    class FakeConfig:
        def set_default(self, *a): pass
        def subscribe(self, *a, **k): pass
    with mock.patch.object(service_module.Agent, '__init__', lambda self, **kw: setattr(self, 'vip', SimpleNamespace(config=FakeConfig()))):
        service = service_module.PresentationService()
    root = resources.files('interoperability')
    service.configure_main(None, 'NEW', {'formats': {**service._load_bundled_formats(root.joinpath('formats')), **config['formats']},
                                         'transforms': service._load_bundled_definitions(root.joinpath('transforms')) + config['transforms'],
                                         'mappings': config['mappings']})
    return service


# =============================================================================================== the writers
class DirectWriter:
    """The harness does the writing itself: lookup_scored with the message's fields, execute, set_multiple_points."""
    name = 'direct'

    def __init__(self, service, parties):
        self.registry, self.parties = service.transform_registry, parties

    def chain(self, src_fmt, dst_fmt, message):
        chain, retention, path = self.registry.lookup_scored(src_fmt, dst_fmt, fields=list(leaves(message)))
        parser = TransformParser(context={'mrid': MRID, 'name': 'DER 1'})
        return parser.build_transform_from_schema(chain).execute(message), retention, path

    def write(self, message, src_fmt, dst, prefix, **_):
        """Transform ``message`` for the device at ``prefix`` (a party's client or served device) and write it."""
        dst_fmt = SERVED_FORMAT[dst] if prefix.endswith('/served') else CLIENT_FORMAT[dst]
        out, retention, path = self.chain(src_fmt, dst_fmt, message)
        party = self.parties[dst]
        r, e, n = party.write(party.interface(prefix), prefix, out)
        return path, f'retention {retention:.2f}, {summary(out)}, {len(r)}/{n} written' + (f', errors {list(e.items())[:2]}' if e else '')


class AdapterWriter(DirectWriter):
    """A DeviceAdapterAgent does the writing: VOLTTRON is stubbed so that its RPCs reach the in-process service and
    the interfaces, and the source's publication is delivered to the bridge for the path."""
    name = 'device_adapter'

    def __init__(self, service, parties):
        super().__init__(service, parties)
        from device_adapter import agent as adapter_module
        from device_adapter.agent import DeviceAdapterAgent
        self.service, self.published = service, []
        with mock.patch.object(adapter_module.Agent, '__init__', return_value=None):
            self.agent = DeviceAdapterAgent.__new__(DeviceAdapterAgent)
            self.agent.vip, self.agent.core = mock.MagicMock(), mock.MagicMock()
            self.agent.core.connected = False
            self.agent.core.spawn.side_effect = lambda fn, *args: fn(*args)
            DeviceAdapterAgent.__init__(self.agent, config_path=None)
        self.agent.vip.rpc.call.side_effect = self.rpc
        self.agent.vip.pubsub.publish.side_effect = lambda peer, topic, message=None, **kw: self.published.append((topic, message))
        bridges = []
        for kind in ('telemetry', 'control'):
            for src in DEVICES:
                for dst in DEVICES:
                    if src != dst:
                        src_role, dst_role = roles(kind, src, dst)
                        bridges.append({'name': bridge_name(kind, src, dst), 'source': uai(src, src_role), 'target': uai(dst, dst_role),
                                        'write_unchanged': True})     # every path orders the same values; changes alone would hide repeats
        self.agent.configure_main(None, 'NEW', {'bridges': bridges})
        assert len(self.agent.bridges) == len(bridges), f'device adapter bridges: {self.agent.list_bridges()}'

    def rpc(self, peer, method, *args, **kwargs):
        reply = mock.Mock()
        if peer == 'platform.presentation':
            reply.get.return_value = getattr(self.service, method)(*args, **kwargs)
        elif peer == 'platform.driver' and method == 'set_multiple_points':
            path, items = args
            party = next(p for p in self.parties.values() if path in (p.client_prefix, p.served_prefix))
            iface = party.interface(path)
            known = [(f'{path}/{k}', v) for k, v in items if f'{path}/{k}' in iface.point_map]
            errors = {f'{path}/{k}': 'no such point on this device' for k, _ in items if f'{path}/{k}' not in iface.point_map}
            if known:
                _, e = iface.set_multiple_points(known)
                errors.update(e)
            reply.get.return_value = errors
        else:
            raise AssertionError(f'unexpected RPC {peer}.{method}')
        return reply

    def write(self, message, src_fmt, dst, prefix, *, kind=None, src=None):
        if kind is None:
            return super().write(message, src_fmt, dst, prefix)
        bridge = self.agent.bridges[bridge_name(kind, src, dst)]
        self.published.clear()
        result = self.agent.relay(bridge, bridge.source_topics[0], [message, {}])
        if result is None:
            return '?', 'the adapter wrote nothing (no change, an echo, or an empty chain output)'
        topic, report = self.published[-1]
        return report['path'], (f'retention {report["retention"]:.2f}, {len(result.written)}/{len(result.written) + len(result.errors)} written'
                                + (f', errors {list(result.errors.items())[:2]}' if result.errors else '') + f' [{topic}]')


def near(a, b, tol=1e-6):
    try:
        return abs(float(a) - float(b)) <= tol
    except (TypeError, ValueError):
        return a == b


def compare(view, expected):
    bad = {k: view.get(k) for k, v in expected.items() if not near(view.get(k), v)}
    return not bad, ('' if not bad else f'external party sees {bad}, expected {expected}')


def dig(d, *path):
    for p in path:
        d = d.get(p) if isinstance(d, dict) else (d[p] if isinstance(d, list) and isinstance(p, int) and p < len(d) else None)
    return d


def summary(out, n=6):
    keys = sorted(out) if isinstance(out, dict) else []
    return f'{len(keys)} fields out {keys[:n]}{"..." if len(keys) > n else ""}'


# =============================================================================================== the matrix
def main():
    parties = {}
    openfmb = OpenFmb()
    try:
        dnp3_rows = rows_of(DNP3_CASE / 'fake_dnp3_der.dnp3.csv')
        config, sep2_rows = service_config([r['Volttron Point Name'] for r in dnp3_rows])
        service = start_service(config)
        t0 = time.time()
        parties['SunSpec'] = setup_sunspec()
        parties['DNP3'] = setup_dnp3()
        parties['2030.5'] = setup_sep2(sep2_rows)
        writer = AdapterWriter(service, parties) if WRITER == 'device_adapter' else DirectWriter(service, parties)
        print(f'parties up in {time.time() - t0:.1f}s: modbus {len(parties["SunSpec"].client.point_map)} points, '
              f'dnp3 {len(parties["DNP3"].client.point_map)}, 2030.5 {len(parties["2030.5"].client.point_map)}; writer: {writer.name}', flush=True)
        S, D, E = parties['SunSpec'], parties['DNP3'], parties['2030.5']

        # ---- sources: what our side has in hand after the external party acted; (message, its format) ---------------
        def telemetry_source(src):
            """The external device reports W and Hz."""
            if src == 'SunSpec':
                # External device = the served unit (its state set by the harness); our master polls everything.
                r, e = S.served.set_multiple_points([(f'{S.served_prefix}/701_W', W), (f'{S.served_prefix}/701_Hz', HZ * 1000)])   # Hz_SF = -3
                assert not e, f'served unit state: {e}'
                r, e = S.client.get_multiple_points(list(S.client.point_map))
                assert not e, f'modbus poll errors: {list(e.items())[:3]}'
                return strip(r, S.client_prefix), CLIENT_FORMAT[src]
            if src == 'DNP3':
                r, e = D.served.set_multiple_points([(f'{D.served_prefix}/AI_537', W), (f'{D.served_prefix}/AI_536', HZ)])
                assert not e, f'served outstation state: {e}'
                r, e = D.client.get_multiple_points([f'{D.client_prefix}/{n}' for n in ('AI_536', 'AI_537')])
                assert not e, f'dnp3 poll errors: {e}'
                return strip(r, D.client_prefix), CLIENT_FORMAT[src]
            if src == '2030.5':
                # External DER client = our client interface posting upward; our served server receives the pushes.
                E.served_agent.clear()
                items = [(f'{E.client_prefix}/MirrorMeterReading_W', W), (f'{E.client_prefix}/MirrorMeterReading_Hz', HZ),
                         (f'{E.client_prefix}/DERSettings_setMaxW', 9000), (f'{E.client_prefix}/DERStatus_operationalModeStatus', 2)]
                r, e = E.client.set_multiple_points(items)
                assert not e, f'2030.5 client upward writes failed: {e}'
                names = {t.rsplit('/', 1)[-1] for t, _ in items}
                assert wait_for(lambda: names <= set(E.served_agent.flat(E.served_prefix)), 15), \
                    f'served server did not push the reports: {sorted(E.served_agent.flat(E.served_prefix))}'
                return E.served_agent.flat(E.served_prefix), SERVED_FORMAT[src]
            raise ValueError(src)

        RESET_PCT = 99

        def reset_sep2_control():
            """The DER client pushes a control topic only when its value changes, and every path orders the same limit:
            move the served control to a distinct value first and wait until the client has it, then clear the pushes."""
            r, e = E.served.set_multiple_points([(f'{E.served_prefix}/DERControl_opModMaxLimW', RESET_PCT)])
            assert not e, f'2030.5 served reset write failed: {e}'
            assert wait_for(lambda: E.client_agent.flat(E.client_prefix).get('DERControl_opModMaxLimW') == RESET_PCT, 20), \
                f'client never saw the reset control: {E.client_agent.flat(E.client_prefix)}'
            E.client_agent.clear()

        def control_source(src):
            """The external controller orders an enabled 50 % active power limit."""
            if src == 'SunSpec':
                S.served_agent.clear()
                r, e = S.client.set_multiple_points([(f'{S.client_prefix}/704_WMaxLimPct', LIMIT_PCT), (f'{S.client_prefix}/704_WMaxLimPctEna', 1)])
                assert not e, f'modbus master write failed: {e}'
                assert wait_for(lambda: len(S.served_agent.flat(S.served_prefix)) >= 2), 'served unit did not push the master write'
                return S.served_agent.flat(S.served_prefix), SERVED_FORMAT[src]
            if src == 'DNP3':
                D.served_agent.clear()
                r, e = D.client.set_multiple_points([(f'{D.client_prefix}/AO_87', AO_87_RAW), (f'{D.client_prefix}/BO_17', True)])
                assert not e, f'dnp3 master write failed: {e}'
                assert wait_for(lambda: len(D.served_agent.flat(D.served_prefix)) >= 2), 'served outstation did not push the operate'
                return D.served_agent.flat(D.served_prefix), SERVED_FORMAT[src]
            if src == '2030.5':
                reset_sep2_control()
                r, e = E.served.set_multiple_points([(f'{E.served_prefix}/DERControl_opModMaxLimW', LIMIT_PCT)])
                assert not e, f'2030.5 served control write failed: {e}'
                assert wait_for(lambda: E.client_agent.flat(E.client_prefix).get('DERControl_opModMaxLimW') == LIMIT_PCT, 20), \
                    f'client never received the control: {E.client_agent.flat(E.client_prefix)}'
                return E.client_agent.flat(E.client_prefix), CLIENT_FORMAT[src]
            raise ValueError(src)

        def openfmb_reading(family):
            key = 'solarReading' if family == 'solar' else 'essReading'
            return {key: {'readingMMXU': {'W': {'net': {'cVal': {'mag': W}}}, 'Hz': {'mag': HZ}}}}

        def openfmb_root(family):
            return ('solarControl', 'solarControlFSCC', 'SolarControlScheduleFSCH') if family == 'solar' else \
                   ('essControl', 'essControlFSCC', 'essControlScheduleFSCH')

        def openfmb_control(family):
            a, b, c = openfmb_root(family)
            entry = {'startTime': {'seconds': int(time.time())},
                     'control': {'limitWOperation': {'maxLimParameter': {'modEna': True}, 'wMaxSptVal': LIMIT_PCT}}}
            return {a: {b: {c: {'ValDCSG': {'crvPts': [entry]}}}}}

        # ---- targets: prepare, then (after the write) look at the external party; (view, expected) -------------------
        def before(kind, dst):
            if kind == 'telemetry':
                if dst == '2030.5':
                    E.served_agent.clear()
            elif dst == 'SunSpec':
                S.served_agent.clear()
            elif dst == 'DNP3':
                D.served_agent.clear()
            elif dst == '2030.5':
                reset_sep2_control()

        def after(kind, dst):
            if kind == 'telemetry':
                if dst == 'SunSpec':
                    view, _ = S.client.get_multiple_points([f'{S.client_prefix}/701_W', f'{S.client_prefix}/701_Hz'])
                    return strip(view, S.client_prefix), {'701_W': W, '701_Hz': HZ * 1000}
                if dst == 'DNP3':
                    view, _ = D.client.get_multiple_points([f'{D.client_prefix}/AI_537', f'{D.client_prefix}/AI_536'])
                    return strip(view, D.client_prefix), {'AI_537': W, 'AI_536': HZ}
                wait_for(lambda: {'MirrorMeterReading_W', 'MirrorMeterReading_Hz'} <= set(E.served_agent.flat(E.served_prefix)), 15)
                return E.served_agent.flat(E.served_prefix), {'MirrorMeterReading_W': W, 'MirrorMeterReading_Hz': HZ}
            if dst == 'SunSpec':
                wait_for(lambda: '704_WMaxLimPct' in S.served_agent.flat(S.served_prefix))
                return S.served_agent.flat(S.served_prefix), {'704_WMaxLimPct': LIMIT_PCT, '704_WMaxLimPctEna': 1}
            if dst == 'DNP3':
                wait_for(lambda: 'AO_87' in D.served_agent.flat(D.served_prefix))
                return D.served_agent.flat(D.served_prefix), {'AO_87': AO_87_RAW, 'BO_17': True}
            wait_for(lambda: E.client_agent.flat(E.client_prefix).get('DERControl_opModMaxLimW') is not None, 20)
            return E.client_agent.flat(E.client_prefix), {'DERControl_opModMaxLimW': LIMIT_PCT}

        def run(kind, src, dst, message, src_fmt):
            """Write the message for the path (the configured writer for device-to-device paths, the harness for
            OpenFMB sources) and check the external party; returns (ok, path, detail)."""
            before(kind, dst)
            prefix = device_topic(dst, roles(kind, src, dst)[1])
            if src == 'OpenFMB':
                path, wrote = DirectWriter.write(writer, message, src_fmt, dst, prefix)
            else:
                path, wrote = writer.write(message, src_fmt, dst, prefix, kind=kind, src=src)
            ok, why = compare(*after(kind, dst))
            return ok, path, f'{wrote}; {why}'

        # ---- telemetry ---------------------------------------------------------------------------------------------
        for src in PROTOCOLS:
            for dst in PROTOCOLS:
                if src == dst or not wanted('telemetry', src, dst):
                    continue
                path = detail = '?'
                try:
                    if src == 'OpenFMB':
                        family = OPENFMB_FAMILY[dst]
                        message = openfmb.receive(PROTO[family][0], openfmb_reading(family), f'openfmb/{family}module/reading/{MRID}')
                        src_fmt = f'openfmb.{family}.reading'
                    else:
                        message, src_fmt = telemetry_source(src)
                    if dst == 'OpenFMB':
                        family = OPENFMB_FAMILY[src]
                        out, retention, path = writer.chain(src_fmt, f'openfmb.{family}.reading', message)
                        got = openfmb.publish(PROTO[family][0], out, f'openfmb/{family}module/reading/{MRID}')
                        key = 'solarReading' if family == 'solar' else 'essReading'
                        view = {'W': dig(got, key, 'readingMMXU', 'W', 'net', 'cVal', 'mag'), 'Hz': dig(got, key, 'readingMMXU', 'Hz', 'mag')}
                        ok, why = compare(view, {'W': W, 'Hz': HZ})
                        detail = f'retention {retention:.2f}, {summary(out)}; {why}'
                    else:
                        ok, path, detail = run('telemetry', src, dst, message, src_fmt)
                except Exception as e:
                    ok, detail = False, f'{type(e).__name__}: {e}'
                    logging.exception('telemetry %s -> %s', src, dst)
                record('telemetry', src, dst, ok, path, detail)

        # ---- control -----------------------------------------------------------------------------------------------
        for src in PROTOCOLS:
            for dst in PROTOCOLS:
                if src == dst or not wanted('control', src, dst):
                    continue
                path = detail = '?'
                try:
                    if src == 'OpenFMB':
                        family = OPENFMB_FAMILY[dst]
                        message = openfmb.receive(PROTO[family][1], openfmb_control(family), f'openfmb/{family}module/control/{MRID}')
                        src_fmt = f'openfmb.{family}.control'
                    else:
                        message, src_fmt = control_source(src)
                    if dst == 'OpenFMB':
                        family = OPENFMB_FAMILY[src]
                        out, retention, path = writer.chain(src_fmt, f'openfmb.{family}.control', message)
                        got = openfmb.publish(PROTO[family][1], out, f'openfmb/{family}module/control/{MRID}')
                        points = dig(got, *openfmb_root(family), 'ValDCSG', 'crvPts') or []
                        now = [p for p in points if 'startTime' not in p or int(dig(p, 'startTime', 'seconds') or 0) <= time.time()]
                        view = {'wMaxSptVal': dig(now[0], 'control', 'limitWOperation', 'wMaxSptVal') if now else None,
                                'modEna': dig(now[0], 'control', 'limitWOperation', 'maxLimParameter', 'modEna') if now else None}
                        ok, why = compare(view, {'wMaxSptVal': LIMIT_PCT, 'modEna': True})
                        detail = f'retention {retention:.2f}, {len(points)} schedule entries; {why}'
                    else:
                        ok, path, detail = run('control', src, dst, message, src_fmt)
                except Exception as e:
                    ok, detail = False, f'{type(e).__name__}: {e}'
                    logging.exception('control %s -> %s', src, dst)
                record('control', src, dst, ok, path, detail)
    finally:
        for p in parties.values():
            p.stop()
    failed = [(k, s, d) for k, s, d, ok, *_ in results if not ok]
    print(f'\n{len(results) - len(failed)}/{len(results)} passed' + (f'; FAILED: {[f"{k} {s}>{d}" for k, s, d in failed]}' if failed else ''))
    return 1 if failed else 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except Exception:
        traceback.print_exc()
        sys.exit(2)
