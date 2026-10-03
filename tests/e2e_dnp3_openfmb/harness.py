"""End-to-end telemetry: IEEE 1815.2 outstation -> DNP3 driver interface (real proxy subprocess) -> the driver's
[values, meta] message -> interoperability service (fake_dnp3_der -> 1815.2.inputs -> 61850 -> openfmb.ess ->
openfmb.ess.reading, protobuf) -> message bus adapter -> MQTT proxy publish.

Everything is the shipped code except the broker and the VOLTTRON bus: the adapter's VIP subscription callback is
invoked directly with the message the driver would publish, and the MQTT proxy's paho client is a mock whose
publish() call is inspected. Run by test_e2e_dnp3_to_openfmb.py in its own process (gevent monkey patching first).
Exit status is non-zero if any check fails."""
from gevent import monkey; monkey.patch_all()
import csv, json, logging, os, socket, subprocess, sys, time
from importlib import resources
from pathlib import Path
from types import SimpleNamespace
from unittest import mock
from uuid import uuid4

import gevent

logging.basicConfig(filename=os.environ.get('E2E_LOG', '/tmp/dnp3_openfmb_e2e.log'), level=logging.INFO,
                    format='%(asctime)s %(name)s %(levelname)s %(message)s')

from volttron.driver.base.config import RemoteConfig
from volttron.driver.interfaces.dnp3.dnp3 import Dnp3
from volttron.driver.interfaces.dnp3.config import Dnp3PointConfig

import interoperability.agent as service_module
from interoperability.codecs.openfmb import message_class
from bus_adapter import agent as adapter_module
from bus_adapter.agent import MessageBusAdapter
from bus_adapter.config import MessageBusAdapterConfig
from protocol_proxy.ipc import SocketParams
from protocol_proxy.manager.gevent import GeventProtocolProxyManager
from protocol_proxy.protocol.mqtt import mqtt_proxy as mqtt_module
from protocol_proxy.protocol.mqtt.mqtt_proxy import MQTTProxy

HERE = Path(__file__).resolve().parent
CASE = HERE.parent / 'integration' / 'fake_dnp3' / 'transform_scaling'
DEVICE_TOPIC = 'devices/site1/feeder1/der'
PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 20020
# Raw outstation values (profile multiplier 1 for the system meter; AI_2 has multiplier 0.1).
METER = {'AI_536': 60, 'AI_537': 12500, 'AI_541': -300, 'AI_547': 2400, 'AI_549': 2410, 'AI_551': 2390, 'AI_554': 52, 'AI_2': 2110}

sim = subprocess.Popen([sys.executable, str(HERE / 'outstation_sim.py'), str(PORT), str(CASE / 'fake_dnp3_der.fake.csv'),
                        json.dumps(METER)])
for _ in range(100):
    try: socket.create_connection(('127.0.0.1', PORT), timeout=0.2).close(); break
    except OSError: time.sleep(0.1)
else: sys.exit('outstation did not start')

checks = []
def check(name, cond, detail=''):
    checks.append((name, bool(cond))); print(('PASS ' if cond else 'FAIL ') + name + (f'  {detail}' if detail else ''))

iface = None
try:
    # ---- 1. The DNP3 driver interface, through the real proxy, polls the outstation ------------------------------
    class Core: spawn = staticmethod(gevent.spawn)
    class DriverAgentStub:
        core = Core()
        def __init__(self): self.pushed = []
        def publish_push(self, result): self.pushed.append(result)
    Dnp3.default_config = {}
    device = json.loads((CASE / 'fake_dnp3_der.dnp3.device.json').read_text())
    remote = {**device['remote_config'], 'outstation_ip': '127.0.0.1', 'port': PORT, 'response_timeout': 5, 'read_mode': 'class'}
    iface = Dnp3(RemoteConfig(**remote), driver_agent=DriverAgentStub())
    with (CASE / 'fake_dnp3_der.dnp3.csv').open(newline='') as f:
        rows = list(csv.DictReader(f))
    for row in rows:
        iface.insert_register(iface.create_register(Dnp3PointConfig(**row)), DEVICE_TOPIC)
    iface.finalize_setup(initial_setup=True)
    check('1. DNP3 proxy launched and outstation registered', iface.proxy_peer is not None and iface.proxy_peer.socket_params is not None)
    t0 = time.time(); results, errors = iface.get_multiple_points(list(iface.point_map)); t_poll = time.time() - t0
    check('1. poll returns the whole 1815.2 point set', len(results) == len(rows) and not errors,
          f'{len(results)} values, {len(errors)} errors, {t_poll:.2f}s' + (f' {list(errors.items())[:2]}' if errors else ''))
    check('1. system meter values read (AI_537 W, AI_536 Hz)', results.get(f'{DEVICE_TOPIC}/AI_537') == 12500.0 and results.get(f'{DEVICE_TOPIC}/AI_536') == 60.0)

    # ---- 2. The message the Platform Driver publishes on devices/.../all: [values, meta] keyed by point name --------
    values = {topic.rsplit('/', 1)[-1]: value for topic, value in results.items()}
    def ts_type(register):
        return 'boolean' if register.register_type == 'bit' or register.python_type is bool else \
               'integer' if register.python_type is int else 'float' if register.python_type is float else 'string'
    meta = {topic.rsplit('/', 1)[-1]: {'units': register.get_units(), 'type': ts_type(register), 'tz': 'UTC'}
            for topic, register in iface.point_map.items()}
    driver_message = [values, meta]
    check('2. driver message shaped [values, meta]', isinstance(driver_message[0], dict) and meta['AI_537']['units'] == 'Watts')

    # ---- 3. The interoperability service resolves the OpenFMB alias to the device and its chain -----------------------
    class FakeConfig:
        def set_default(self, *a): pass
        def subscribe(self, *a, **k): pass
    with mock.patch.object(service_module.Agent, '__init__', lambda self, **kw: setattr(self, 'vip', SimpleNamespace(config=FakeConfig()))):
        service = service_module.PresentationService()
    root = resources.files('interoperability')
    case = json.loads((CASE / 'presentation_config.json').read_text())
    service.configure_main(None, 'NEW', {'formats': {**service._load_bundled_formats(root.joinpath('formats')), **case['formats']},
                                         'transforms': service._load_bundled_definitions(root.joinpath('transforms')) + case['transforms'],
                                         'mappings': case['mappings']})
    alias = next(m for m in case['mappings'] if m['resource']['data_format'] == 'openfmb.ess.reading')
    remote_topic = '/'.join(alias['uai'])
    resolved = service.resolve(tuple(alias['uai']))
    check('3. resolve: device, chain, parameters and protobuf codec', resolved.get('publication_topic') == f'{DEVICE_TOPIC}/all'
          and len(resolved.get('transform', [])) == 4 and resolved.get('parameters') == alias['resource']['parameters']
          and resolved.get('codec') == {'encoding': 'protobuf', 'proto': 'essmodule.ESSReadingProfile'}, str({k: resolved.get(k) for k in ('target_format', 'encoding', 'codec')}))

    # ---- 4. The message bus adapter, configured to serve the OpenFMB topic, subscribes and relays ------------------------
    with mock.patch.object(adapter_module.Agent, '__init__', return_value=None):
        adapter = MessageBusAdapter.__new__(MessageBusAdapter); adapter.vip = mock.MagicMock(); adapter.core = mock.MagicMock()
        MessageBusAdapter.__init__(adapter)
    def rpc_call(peer, method, uai):
        reply = mock.MagicMock(); reply.get.return_value = service.resolve(tuple(uai)); return reply
    adapter.vip.rpc.call.side_effect = rpc_call
    adapter.config = MessageBusAdapterConfig(bus_type='mqtt', adapters=[{'name': 'site_broker', 'host': 'broker', 'local_subscriptions': [remote_topic]}])
    manager = mock.MagicMock(spec=GeventProtocolProxyManager); manager.send.return_value = True
    manager.proxy_class = mock.MagicMock(topic_delimiter=mock.Mock(return_value='/'))
    adapter.ppm = manager
    peer = mock.MagicMock(proxy_id=uuid4(), socket_params=SocketParams('127.0.0.1', 1))
    with mock.patch.object(adapter, '_get_peer', return_value=peer):
        adapter._start_remote(('mqtt', 'site_broker'))
    subscription = adapter.vip.pubsub.subscribe.call_args.kwargs
    check('4. adapter subscribed to the device publication topic', subscription.get('prefix') == f'{DEVICE_TOPIC}/all', str(subscription.get('prefix')))
    subscription['callback']('pubsub', 'platform.driver', 'bus', f'{DEVICE_TOPIC}/all', {}, driver_message)
    envelope = json.loads(manager.send.call_args.kwargs['message'].payload)
    check('4. PUBLISH_REMOTE carries hex protobuf to the OpenFMB topic', envelope.get('topic') == remote_topic and envelope.get('encoding') == 'hex', str({k: envelope.get(k) for k in ('topic', 'encoding')}))

    # ---- 5. The MQTT proxy publishes the raw bytes; they decode as an ESSReadingProfile ------------------------------
    manager_id, manager_token = uuid4(), uuid4()
    with mock.patch.object(mqtt_module.mqtt, 'Client') as client_class:
        client = client_class.return_value
        client.publish.return_value = SimpleNamespace(rc=mqtt_module.mqtt.MQTT_ERR_SUCCESS)
        proxy = MQTTProxy(proxy_id=uuid4(), token=uuid4(), proxy_name='test', manager_address='127.0.0.1', manager_port=1,
                          manager_id=manager_id, manager_token=manager_token, host='broker', port=1883)
    proxy.handle_publish_remote.__wrapped__(proxy, SimpleNamespace(sender_id=manager_id), manager.send.call_args.kwargs['message'].payload)
    topic, payload = client.publish.call_args.args
    check('5. MQTT proxy publishes bytes on the OpenFMB topic', topic == remote_topic and isinstance(payload, (bytes, bytearray)), f'{len(payload)} bytes')
    profile = message_class('essmodule.ESSReadingProfile').FromString(bytes(payload))
    mmxu = profile.essReading.readingMMXU
    check('5. ESSReadingProfile: W, VAr, Hz from the system meter', mmxu.W.net.cVal.mag == 12500.0 and mmxu.VAr.net.cVal.mag == -300.0 and mmxu.Hz.mag == 60.0,
          f'W={mmxu.W.net.cVal.mag} VAr={mmxu.VAr.net.cVal.mag} Hz={mmxu.Hz.mag}')
    check('5. ESSReadingProfile: phase voltages and current', mmxu.PhV.phsA.cVal.mag == 2400.0 and mmxu.PhV.phsB.cVal.mag == 2410.0 and mmxu.A.phsA.cVal.mag == 52.0)
    check('5. ESSReadingProfile: header and equipment identity', profile.ess.conductingEquipment.mRID == alias['resource']['parameters']['mrid']
          and profile.ess.conductingEquipment.namedObject.name.value == 'DER 1' and len(profile.readingMessageInfo.messageInfo.identifiedObject.mRID.value) == 36
          and profile.readingMessageInfo.messageInfo.messageTimeStamp.seconds > 1_700_000_000)
finally:
    if iface is not None:
        for p in list(getattr(iface.ppm, 'peers', {}).values()):
            proc = getattr(p, 'process', None)
            if proc: proc.terminate()
    sim.terminate()
failed = [n for n, ok in checks if not ok]
print(f'\n{len(checks) - len(failed)}/{len(checks)} passed' + (f'; FAILED: {failed}' if failed else ''))
sys.exit(1 if failed else 0)
