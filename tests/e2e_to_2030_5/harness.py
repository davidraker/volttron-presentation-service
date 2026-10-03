"""End-to-end telemetry into IEEE 2030.5: a SunSpec inverter and an IEEE 1815.2 outstation -> the interoperability
service's transform chains -> the ieee2030_5 driver interface (real proxy subprocess) -> the GridAPPS-D Go sep2server.

Sources: the SunSpec inverter is the fake driver's publish of the generated fake_sunspec case (registry starting values,
the case's premise); the 1815.2 outstation is a real dnp3py outstation polled through the DNP3 driver interface and the
real DNP3 proxy. Each driver message ([values, meta]) goes through the chain the service would use for a write to the
2030.5 mirror (device format -> protocol -> 2030.5 -> mirror points), the mirror points are written through the
ieee2030_5 interface, and the server's copies are read back over mutual TLS. Run by test_e2e_telemetry_to_2030_5.py in
its own process (gevent monkey patching first). Exit status is non-zero if any check fails.

Arguments: <dnp3 port> <sep2 port> <sep2 admin port> <notify port> [work dir]."""
from gevent import monkey; monkey.patch_all()
import asyncio, csv, json, logging, os, socket, subprocess, sys, tempfile, time
from pathlib import Path

import gevent

logging.basicConfig(filename=os.environ.get('E2E_LOG', '/tmp/telemetry_2030_5_e2e.log'), level=logging.INFO,
                    format='%(asctime)s %(name)s %(levelname)s %(message)s')

import volttron.driver.interfaces.ieee2030_5 as sep2_package
from volttron.driver.base.config import RemoteConfig
from volttron.driver.interfaces.dnp3.dnp3 import Dnp3
from volttron.driver.interfaces.dnp3.config import Dnp3PointConfig
from volttron.driver.interfaces.ieee2030_5.ieee2030_5 import Ieee2030_5
from volttron.driver.interfaces.ieee2030_5.config import Ieee2030_5PointConfig
from protocol_proxy.protocol.ieee2030_5.identity import lfdi_from_cert, sfdi_from_lfdi
from protocol_proxy.protocol.ieee2030_5.models import sep
from protocol_proxy.protocol.ieee2030_5.transport import Sep2Http

from interoperability.discovery import ieee2030_5 as mirror_gen
from interoperability.transform_parser import TransformParser

E2E_DIR = Path(os.environ.get('IEEE2030_5_DRIVER_REPO', Path(sep2_package.__file__).resolve().parents[5])) / 'tests' / 'e2e_sep2server'
sys.path.insert(0, str(E2E_DIR))
from sep2server import Sep2Server, ensure_image, generate_certs, write_fixture      # noqa: E402

HERE = Path(__file__).resolve().parent
TESTS = HERE.parent
SUNSPEC_CASE = TESTS / 'integration' / 'fake_sunspec' / 'transform_scaling'
DNP3_CASE = TESTS / 'integration' / 'fake_dnp3' / 'transform_scaling'
DNP3_PORT, SEP2_PORT, ADMIN_PORT, NOTIFY_PORT = (int(a) for a in sys.argv[1:5])
WORK = Path(sys.argv[5]) if len(sys.argv) > 5 else Path(tempfile.mkdtemp(prefix='sep2tele-'))
DNP3_TOPIC, SEP2_TOPIC = 'devices/site1/feeder1/der', 'devices/site1/feeder1/der_sep2'
# Raw outstation values: system meter (multiplier 1) and the nameplate voltages AI_2/AI_3 (multiplier 0.1).
METER = {'AI_536': 60, 'AI_537': 12500, 'AI_541': -300, 'AI_547': 2400, 'AI_549': 2410, 'AI_551': 2390, 'AI_554': 52, 'AI_2': 2110, 'AI_3': 2640}

checks = []
def check(name, cond, detail=''):
    checks.append((name, bool(cond))); print(('PASS ' if cond else 'FAIL ') + name + (f'  {detail}' if detail else ''))

def rows_of(path):
    with Path(path).open(newline='') as f:
        return list(csv.DictReader(f))

def fake_driver_message(registry_csv):
    """What the fake driver publishes: [values, meta] from the registry's starting values."""
    values, meta = {}, {}
    for row in rows_of(registry_csv):
        raw, kind = row['Starting Value'], row['Type']
        if raw == '':
            continue
        values[row['Volttron Point Name']] = float(raw) if kind == 'float' else int(raw) if kind == 'int' else \
            raw.strip().lower() == 'true' if kind == 'boolean' else raw
        meta[row['Volttron Point Name']] = {'units': row.get('Units', ''), 'type': kind, 'tz': 'UTC'}
    return [values, meta]

def driver_message(iface, results):
    values = {topic.rsplit('/', 1)[-1]: value for topic, value in results.items()}
    def ts_type(register):
        return 'boolean' if register.python_type is bool else 'integer' if register.python_type is int else 'float'
    meta = {topic.rsplit('/', 1)[-1]: {'units': register.get_units(), 'type': ts_type(register), 'tz': 'UTC'}
            for topic, register in iface.point_map.items()}
    return [values, meta]

def fetch(server, certs, href, cls):
    async def go():
        http = Sep2Http(server.url, cert_path=str(certs['device_cert']), key_path=str(certs['device_key']), ca_path=str(certs['ca']), retries=1)
        try:
            return await http.get(href, cls)
        finally:
            await http.aclose()
    return asyncio.run(go())

def quantity(value):
    return None if value is None else value.value * 10 ** (value.multiplier or 0)

# ---- the 2030.5 server ---------------------------------------------------------------------------------------------
ensure_image()
certs = generate_certs(WORK / 'tls')
LFDI = lfdi_from_cert(certs['device_cert'])
fixture = WORK / 'fixture' / 'boot.yaml'
fixture.parent.mkdir(exist_ok=True)
write_fixture(fixture, LFDI, sfdi_from_lfdi(LFDI))
server = Sep2Server(WORK / 'tls', fixture, SEP2_PORT, ADMIN_PORT, name=f'sep2tele-{SEP2_PORT}')
server.start()

# ---- the 1815.2 outstation -----------------------------------------------------------------------------------------
sim = subprocess.Popen([sys.executable, str(TESTS / 'e2e_dnp3_openfmb' / 'outstation_sim.py'), str(DNP3_PORT),
                        str(DNP3_CASE / 'fake_dnp3_der.fake.csv'), json.dumps(METER)])
for _ in range(100):
    try: socket.create_connection(('127.0.0.1', DNP3_PORT), timeout=0.2).close(); break
    except OSError: time.sleep(0.1)
else: sys.exit('outstation did not start')

class Core: spawn = staticmethod(gevent.spawn)
class DriverAgentStub:
    core = Core()
    def __init__(self): self.pushed = []
    def publish_push(self, result): self.pushed.append(result)

dnp3 = sep2 = None
try:
    # ---- 1. The service's registries and the two mirrors ---------------------------------------------------------------
    sunspec_registry = mirror_gen.load_registry(SUNSPEC_CASE / 'presentation_config.json')
    sunspec_fragment = json.loads((SUNSPEC_CASE / 'fake_sunspec_pv_sep2.presentation.json').read_text())
    sunspec_registry.declare_format('fake_sunspec_pv_sep2', **sunspec_fragment['formats']['fake_sunspec_pv_sep2'])
    sunspec_registry.update_registry(sunspec_fragment['transforms'])
    dnp3_registry = mirror_gen.load_registry(DNP3_CASE / 'presentation_config.json')
    dnp3_mirror = mirror_gen.discover_mirror(dnp3_registry, 'fake_dnp3_der')
    dnp3_fragment = mirror_gen.presentation_fragment('fake_dnp3_der_sep2', dnp3_mirror, SEP2_TOPIC, ['site1', 'der_sep2'])
    dnp3_registry.declare_format('fake_dnp3_der_sep2', **dnp3_fragment['formats']['fake_dnp3_der_sep2'])
    dnp3_registry.update_registry(dnp3_fragment['transforms'])
    sunspec_chain, sunspec_ret, sunspec_path = sunspec_registry.lookup_scored('fake_sunspec_pv', 'fake_sunspec_pv_sep2')
    dnp3_chain, dnp3_ret, dnp3_path = dnp3_registry.lookup_scored('fake_dnp3_der', 'fake_dnp3_der_sep2')
    check('1. service chains: sunspec and 1815.2 devices reach their 2030.5 mirrors',
          sunspec_path == ['fake_sunspec_pv', 'sunspec', '2030.5', 'fake_sunspec_pv_sep2']
          and dnp3_path == ['fake_dnp3_der', '1815.2.inputs', '2030.5', 'fake_dnp3_der_sep2'], f'{sunspec_path} {dnp3_path}')

    # ---- 2. The ieee2030_5 interface for the mirror, registry = union of both mirrors' rows ---------------------------
    rows = {r['Volttron Point Name']: r for r in rows_of(SUNSPEC_CASE / 'fake_sunspec_pv_sep2.ieee2030_5.csv')}
    for r in mirror_gen.registry_rows(dnp3_mirror):
        rows.setdefault(r['Volttron Point Name'], r)
    Ieee2030_5.default_config = {}
    sep2 = Ieee2030_5(RemoteConfig(driver_type='ieee2030_5', server_url=server.url, cert_path=str(certs['device_cert']),
                                   key_path=str(certs['device_key']), ca_path=str(certs['ca']), subscribe=True,
                                   notify_host='127.0.0.1', notify_bind_host='127.0.0.1', notify_port=NOTIFY_PORT,
                                   notify_cert_path=str(certs['notify_cert']), notify_key_path=str(certs['notify_key']),
                                   poll_rate_ceiling=600, response_timeout=10), driver_agent=DriverAgentStub())
    for row in rows.values():
        sep2.insert_register(sep2.create_register(Ieee2030_5PointConfig(**row)), SEP2_TOPIC)
    sep2.finalize_setup(initial_setup=True)
    def describe():
        result, errors = sep2.parse_proxy_response(sep2._send('DESCRIBE_SERVER', sep2.config.identity_fields()), ['server'])
        return result if not errors else {}
    deadline = time.time() + 30
    while time.time() < deadline and describe().get('ready') is not True:
        gevent.sleep(0.25)
    d = describe()
    check('2. ieee2030_5 interface registered the mirror with the server', d.get('ready') is True and d.get('der') == '/edev/1/der/1'
          and d.get('mup'), f"{len(rows)} rows, {json.dumps({k: d.get(k) for k in ('end_device', 'der', 'mup', 'subscriptions')})}")

    # ---- 3. SunSpec inverter -> sunspec -> 2030.5 -> mirror points -> server ---------------------------------------------
    sunspec_message = fake_driver_message(SUNSPEC_CASE / 'fake_sunspec_pv.fake.csv')
    sunspec_points = TransformParser().build_transform_from_schema(sunspec_chain).execute(sunspec_message)
    sunspec_2030_5 = TransformParser().build_transform_from_schema(sunspec_registry.lookup('fake_sunspec_pv', '2030.5')).execute(sunspec_message)
    check('3. sunspec chain yields upward mirror points only, matching the 2030.5 message',
          sunspec_points and all(not k.startswith(('DERControl', 'DERCurve')) for k in sunspec_points)
          and sunspec_points['DERSettings_setMaxW'] == sunspec_2030_5['DERSettings']['setMaxW']
          and sunspec_points['MirrorMeterReading_W'] == sunspec_2030_5['MirrorMeterReading']['W'],
          f'{len(sunspec_points)} points, setMaxW={sunspec_points.get("DERSettings_setMaxW")} W={sunspec_points.get("MirrorMeterReading_W")}')
    # Known convention gap, not a transport one: sunspec maps the manufacturer *name* (1_Mn) onto DeviceInformation.mfID,
    # which the schema types as the manufacturer's PEN (an integer); the proxy rightly refuses the string.
    # sep2server implements no DeviceInformation resource (no /edev/{id}/di route), so those rows cannot land anywhere.
    SKIP = {'DeviceInformation_mfID'}
    def writable_here(name):
        return f'{SEP2_TOPIC}/{name}' in sep2.point_map and name not in SKIP and not name.startswith('DeviceInformation_')
    items = [(f'{SEP2_TOPIC}/{name}', value) for name, value in sunspec_points.items() if writable_here(name)]
    results, errors = sep2.set_multiple_points(items)
    check('3. mirror points written through the ieee2030_5 interface (PUTs and reading POSTs)', len(results) == len(items) and not errors,
          f'{len(results)} written' + (f', errors {list(errors.items())[:3]}' if errors else ''))
    settings = fetch(server, certs, '/edev/1/der/1/derg', sep.DERSettings)
    capability = fetch(server, certs, '/edev/1/der/1/dercap', sep.DERCapability)
    status = fetch(server, certs, '/edev/1/der/1/ders', sep.DERStatus)
    check('3. server holds the inverter\'s settings, capability and status',
          quantity(settings.setMaxW) == sunspec_2030_5['DERSettings']['setMaxW']
          and quantity(capability.rtgMaxW) == sunspec_2030_5['DERCapability']['rtgMaxW']
          and status.operationalModeStatus is not None and status.operationalModeStatus.value == sunspec_2030_5['DERStatus']['operationalModeStatus'],
          f'setMaxW={quantity(settings.setMaxW)} rtgMaxW={quantity(capability.rtgMaxW)} opMode={getattr(status.operationalModeStatus, "value", None)}')
    # sep2server accepts MirrorMeterReading POSTs (201 + Location) but exposes neither them nor a UsagePoint for them, so
    # the server-side evidence is the MirrorUsagePoint under our LFDI plus the Locations it returned for each reading.
    mups = fetch(server, certs, '/mup', sep.MirrorUsagePointList)
    mine = [m for m in mups.MirrorUsagePoint if m.deviceLFDI and m.deviceLFDI.hex().upper() == LFDI]
    reading_topics = [t for t, _ in items if '/MirrorMeterReading_' in t]
    raw, raw_errors = sep2.parse_proxy_response(sep2._send('WRITE_RESOURCES', {**sep2.config.identity_fields(), 'values': dict(
        (t, v) for t, v in items if t in reading_topics)}), reading_topics)
    posted = {t: raw.get(t, {}).get('href', '') for t in reading_topics}
    check('3. server accepted the inverter\'s meter readings (W, var, Hz, V) under our MirrorUsagePoint', bool(mine) and not raw_errors
          and len(posted) >= 8 and all(h.startswith(mine[0].href + '/mr/') for h in posted.values()),
          f'{len(posted)} readings, e.g. {list(posted.items())[:1]}')
    readback = sep2.get_multiple_points([f'{SEP2_TOPIC}/MirrorMeterReading_W', f'{SEP2_TOPIC}/DERSettings_setMaxW'])[0]
    check('3. driver reads back what it sent', readback.get(f'{SEP2_TOPIC}/MirrorMeterReading_W') == sunspec_points['MirrorMeterReading_W']
          and readback.get(f'{SEP2_TOPIC}/DERSettings_setMaxW') == sunspec_points['DERSettings_setMaxW'], str(readback))

    # ---- 4. 1815.2 outstation -> DNP3 proxy -> driver message -> 1815.2.inputs -> 2030.5 -> mirror points -> server -----
    Dnp3.default_config = {}
    device = json.loads((DNP3_CASE / 'fake_dnp3_der.dnp3.device.json').read_text())
    dnp3 = Dnp3(RemoteConfig(**{**device['remote_config'], 'outstation_ip': '127.0.0.1', 'port': DNP3_PORT, 'response_timeout': 5,
                                'read_mode': 'class'}), driver_agent=DriverAgentStub())
    dnp3_rows = rows_of(DNP3_CASE / 'fake_dnp3_der.dnp3.csv')
    for row in dnp3_rows:
        dnp3.insert_register(dnp3.create_register(Dnp3PointConfig(**row)), DNP3_TOPIC)
    dnp3.finalize_setup(initial_setup=True)
    results, errors = dnp3.get_multiple_points(list(dnp3.point_map))
    check('4. DNP3 proxy polls the outstation (system meter W, Hz)', len(results) == len(dnp3_rows) and not errors
          and results.get(f'{DNP3_TOPIC}/AI_537') == 12500.0 and results.get(f'{DNP3_TOPIC}/AI_536') == 60.0,
          f'{len(results)} values, {len(errors)} errors')
    dnp3_message = driver_message(dnp3, results)
    dnp3_points = TransformParser().build_transform_from_schema(dnp3_chain).execute(dnp3_message)
    dnp3_2030_5 = TransformParser().build_transform_from_schema(dnp3_registry.lookup('fake_dnp3_der', '2030.5')).execute(dnp3_message)
    check('4. 1815.2 chain yields the meter readings and nameplate as mirror points',
          dnp3_points.get('MirrorMeterReading_W') == 12500 and dnp3_points.get('MirrorMeterReading_var') == -300
          and dnp3_points.get('MirrorMeterReading_Hz') == 60 and dnp3_points.get('MirrorMeterReading_V_PhaseA') == 2400
          and abs(dnp3_points.get('DERCapability_rtgMinV', 0) - 211.0) < 1e-6 and abs(dnp3_points.get('DERCapability_rtgMaxV', 0) - 264.0) < 1e-6
          and dnp3_points['MirrorMeterReading_W'] == dnp3_2030_5['MirrorMeterReading']['W'],
          f'{len(dnp3_points)} points, W={dnp3_points.get("MirrorMeterReading_W")} rtgMinV={dnp3_points.get("DERCapability_rtgMinV")}')
    items = [(f'{SEP2_TOPIC}/{name}', value) for name, value in dnp3_points.items() if writable_here(name)]
    results, errors = sep2.set_multiple_points(items)
    check('4. mirror points written through the ieee2030_5 interface', len(results) == len(items) and not errors,
          f'{len(results)} written' + (f', errors {list(errors.items())[:3]}' if errors else ''))
    # sep2server's DERCapability keeps rtgMaxV but drops rtgMinV (and rtgVNom, rtgOverExcitedPF): its model is a subset.
    capability = fetch(server, certs, '/edev/1/der/1/dercap', sep.DERCapability)
    check('4. server holds the outstation\'s nameplate voltage (0.1 multiplier applied by the transform)',
          quantity(capability.rtgMaxV) == 264 and quantity(capability.rtgMaxW) == 0,
          f'rtgMaxV={quantity(capability.rtgMaxV)} rtgMaxW={quantity(capability.rtgMaxW)} (rtgMinV not stored by this server)')
    readback = sep2.get_multiple_points([f'{SEP2_TOPIC}/MirrorMeterReading_W', f'{SEP2_TOPIC}/MirrorMeterReading_var'])[0]
    check('4. driver reads back the outstation\'s readings', readback.get(f'{SEP2_TOPIC}/MirrorMeterReading_W') == 12500
          and readback.get(f'{SEP2_TOPIC}/MirrorMeterReading_var') == -300, str(readback))
finally:
    for iface in (dnp3, sep2):
        for p in list(getattr(iface.ppm, 'peers', {}).values()) if iface is not None else []:
            proc = getattr(p, 'process', None)
            if proc: proc.terminate()
    sim.terminate()
    if os.environ.get('SEP2_E2E_KEEP') != '1':
        server.stop()
failed = [n for n, ok in checks if not ok]
print(f'\n{len(checks) - len(failed)}/{len(checks)} passed' + (f'; FAILED: {failed}' if failed else ''))
sys.exit(1 if failed else 0)
