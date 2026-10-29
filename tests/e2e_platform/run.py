"""Outside-in end-to-end matrix on a real VOLTTRON platform with independent external parties.

The platform (volttron-core, ZMQ bus, auth on) runs from this venv in a fresh VOLTTRON_HOME with the platform driver,
the presentation service, the Resource Bridge and the Message Bus Adapter installed as agents and configured through the
config store (``configs.py``). Around it, nothing of ours:

* a SunSpec inverter and a Modbus master on uModbus (``external/sunspec_device.py``);
* the IEEE 1815.2 test tool's reference outstation and reference control station, Rust on the Step Function dnp3 crate
  (``external/dnp3_tool.py``);
* the GridAPPS-D Go ``sep2server`` as the utility and the Go ``inverterclient`` as a DER client (``external/sep2.py``);
* mosquitto as the OpenFMB broker and a paho/protobuf participant (``external/openfmb_party.py``).

Every path is stimulated at one external party and observed at another; the platform is a black box. The OpenFMB paths
run through the Message Bus Adapter (OpenFMB on the VOLTTRON bus) and the Resource Bridge's bus ends (``--openfmb bus``,
the only mode since translate mode was removed on 2026-10-29).

    python tests/e2e_platform/run.py --openfmb bus [--work DIR] [--keep] [--only telemetry:SunSpec>DNP3,...]

Exit status is non-zero if any path fails. Takes several minutes (the first platform start builds its poetry project).
"""
from concurrent.futures import ThreadPoolExecutor
import argparse
import ast
import copy
import json
import logging
import os
import re
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / 'external'))

import configs                                                                     # noqa: E402
from configs import DEVICES, MRID, OPENFMB_FAMILY, PROTO, device_topic, openfmb_alias, roles   # noqa: E402
from volttron_platform import Platform                                                      # noqa: E402
import dnp3_tool                                                                   # noqa: E402
import sep2                                                                        # noqa: E402
from openfmb_party import OpenFmbParty                                             # noqa: E402
from sunspec_device import ModbusMaster, SunSpecDevice                             # noqa: E402
from interoperability.openfmb_bus import topic_of                                  # noqa: E402
from interoperability.codecs.openfmb import decode as decode_profile                # noqa: E402

PROTOCOLS = ('SunSpec', 'DNP3', '2030.5', 'OpenFMB')
W, HZ = 4321, 60
VAR, V_PHASE = -120, 240        # what the OpenFMB party reports (the other sources report W and Hz)
# Each source orders its own limit, so a write that merely repeats the last value (which the bridges skip) is never
# mistaken for a new one at a target several sources share. DNP3 carries it in tenths of a percent (AO_87, multiplier 0.1).
LIMIT = {'SunSpec': 50, 'DNP3': 40, '2030.5': 30, 'OpenFMB': 20}
TARGET_OFFSET = {'SunSpec': 0, 'DNP3': 1, '2030.5': 2, 'OpenFMB': 3, 'RTC': 4}     # ... and a different one for each of its targets
WMAX = 9876                     # a SunSpec WMax the platform carries up as DERSettings.setMaxW
RTG_MAX_V_RAW = 2640            # DNP3 AI_3 (0.1 V): 264 V, carried up as DERCapability.rtgMaxV
PIN = 111115
SUNSPEC_CSV = configs.SUNSPEC_CASE / 'fake_sunspec_pv.modbus.csv'


def free_port():
    with socket.socket() as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]


def wait_for(predicate, timeout, interval=1.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            value = predicate()
        except Exception:
            value = None
        if value:
            return value
        time.sleep(interval)
    try:
        return predicate()
    except Exception:
        return None


def port_open(host, port):
    try:
        socket.create_connection((host, port), timeout=0.5).close()
        return True
    except OSError:
        return False


class Mosquitto:
    def __init__(self, port, name='e2e-mosquitto'):
        self.port, self.name = port, name

    def start(self):
        subprocess.run(['docker', 'rm', '-f', self.name], capture_output=True)
        subprocess.run(['docker', 'run', '-d', '--name', self.name, '-p', f'127.0.0.1:{self.port}:1883', 'eclipse-mosquitto:2', 'sh', '-c',
                        'printf "listener 1883\\nallow_anonymous true\\n" > /mosquitto/config/mosquitto.conf && exec mosquitto -c /mosquitto/config/mosquitto.conf'],
                       check=True, capture_output=True)
        if not wait_for(lambda: port_open('127.0.0.1', self.port), 20, 0.3):
            raise RuntimeError('mosquitto did not start')
        return self

    def stop(self):
        subprocess.run(['docker', 'rm', '-f', self.name], capture_output=True)


def dig(d, *path):
    for p in path:
        d = d.get(p) if isinstance(d, dict) else (d[p] if isinstance(d, list) and isinstance(p, int) and p < len(d) else None)
    return d


def near(a, b, tol=1e-6):
    try:
        return abs(float(a) - float(b)) <= tol
    except (TypeError, ValueError):
        return a == b


class Matrix:
    def __init__(self, args):
        self.args = args
        self.work = Path(args.work)
        if self.work.exists() and not args.keep_work:
            shutil.rmtree(self.work)
        self.work.mkdir(parents=True, exist_ok=True)
        self.results = []
        self.parties = {}
        self.platform = None
        self.log = logging.getLogger('e2e')

    # ---- lifecycle ----------------------------------------------------------------------------------------------
    def start_external(self):
        ports = {name: free_port() for name in ('mqtt', 'sunspec_served', 'dnp3_outstation', 'dnp3_served', 'sep2_server', 'sep2_admin',
                                                  'sep2_served', 'sep2_notify', 'goclient_notify')}
        self.ports = ports
        certs = sep2.generate_certs(self.work / 'tls')
        self.certs = certs
        self.mosquitto = Mosquitto(ports['mqtt']).start()
        self.sunspec_device = SunSpecDevice(SUNSPEC_CSV, '127.0.0.1', 0).start()
        self.sunspec_device.set_point('701_W', W)
        self.sunspec_device.set_point('701_Hz', HZ * 1000)
        self.sunspec_device.set_point('702_WMax', WMAX)
        self.sunspec_master = ModbusMaster(SUNSPEC_CSV, '127.0.0.1', ports['sunspec_served'])
        profile = dnp3_tool.load_profile()
        self.dnp3_profile = profile
        self.outstation = dnp3_tool.ReferenceOutstation(self.work / 'dnp3', ports['dnp3_outstation'],
                                                        dnp3_tool.with_stimulus(profile, analog_values={537: W, 536: HZ, 3: RTG_MAX_V_RAW / 10})).start()
        self.go_server = sep2.GoServer(self.work, certs, ports['sep2_server'], ports['sep2_admin']).start()
        self.go_client = sep2.GoClient(certs, f'https://127.0.0.1:{ports["sep2_served"]}', PIN, ports['goclient_notify'])
        self.openfmb = OpenFmbParty(port=ports['mqtt'])
        outbound = [topic_of(openfmb_alias(p, roles(k, p, 'OpenFMB')[0], 'reading' if k == 'telemetry' else 'control'))
                    for p in DEVICES for k in ('telemetry', 'control')]
        if self.args.rtc:
            outbound.append(topic_of(openfmb_alias('RTC', 'rtc', 'reading')))
        self.openfmb.start(outbound)
        self.endpoints = configs.Endpoints(
            sunspec_device=(self.sunspec_device.host, self.sunspec_device.port), sunspec_served_port=ports['sunspec_served'],
            dnp3_outstation=('127.0.0.1', ports['dnp3_outstation']), dnp3_served_port=ports['dnp3_served'],
            sep2_server_url=self.go_server.url, sep2_served_port=ports['sep2_served'], sep2_notify_port=ports['sep2_notify'],
            mqtt=('127.0.0.1', ports['mqtt']), certs=certs, served_client_lfdi=self.go_client.lfdi, served_client_pin=PIN, client_pin=PIN,
            poll_interval=self.args.poll_interval)
        self.log.info('external parties up: %s', ports)

    def start_platform(self):
        built = configs.build(self.work / 'configs', self.endpoints, self.args.openfmb, rtc=self.args.rtc,
                              persistent=True if self.args.persistent else (False if self.args.per_message else None))
        self.configs = built
        self.platform = Platform(self.work / 'volttron_home', 'der-e2e')
        t0 = time.time()
        self.platform.start()
        self.log.info('platform up in %.0fs', time.time() - t0)
        self.platform.store_all(built.entries, self.log.info)
        self.platform.install_all(self.log.info, include_rtc=self.args.rtc)
        status = self.platform.vctl('status')
        self.log.info('vctl status:\n%s', status)
        if not wait_for(lambda: port_open('127.0.0.1', self.ports['sep2_served']), 120, 2):
            raise RuntimeError('the platform never served its 2030.5 server port:\n' + self.platform.log_tail(60))
        if not wait_for(lambda: port_open('127.0.0.1', self.ports['sunspec_served']) and port_open('127.0.0.1', self.ports['dnp3_served']), 60, 2):
            raise RuntimeError('the platform never served its Modbus unit or outstation:\n' + self.platform.log_tail(60))
        self.reports = open(self.work / 'resource_bridge_reports.log', 'w')
        self.subscriber = subprocess.Popen([str(self.platform.bin / 'vctl'), 'subscribe', 'resource_bridge/'], env=self.platform.env,
                                           stdout=self.reports, stderr=subprocess.STDOUT)
        self.go_client.start()
        ready = self.go_client.wait_for_log(r'DER capability and settings reported|Phase 4|MirrorUsagePoint', 180)
        self.log.info('go client: %s', ready)
        if not ready:
            raise RuntimeError('the Go DER client never completed its DER setup against the served server:\n' + self.go_client.logs()[-3000:])
        # The bus adapter serves the SunSpec device's reading profile from every poll: the first one shows the chain is live.
        # That bridge is a matrix bridge, so it is activated here for the readiness check; the first round reconfigures.
        self.activate_bridges([configs.bridge_name('telemetry', 'SunSpec', 'OpenFMB')])
        family = OPENFMB_FAMILY['SunSpec']
        topic = topic_of(openfmb_alias('SunSpec', 'client', 'reading'))
        first = self.openfmb.wait_for(topic, PROTO[family][0], timeout=120)
        self.log.info('first reading profile at the broker: %s', 'yes' if first else 'no')
        if not first:
            raise RuntimeError('no reading profile reached the broker within 120 s:\n' + self.platform.log_tail(80))
        if self.args.rtc:
            # The agent's modes reach the served outstation (DWMX.LimW read-back as AI 148) through the Resource Bridge;
            # an independent 1815.2 master reads it there, as for every other observation of the platform's black box.
            # Devices re-assert their standing limits on start-up (the SunSpec unit's register default is 10000), so the
            # first read-back is whatever the last source said; its presence is what proves the chain, and rtc_reset
            # restores a known state before each control path.
            view = wait_for(lambda: (lambda v: v if v.get('LimWMax') is not None else None)(self.rtc_limit_view()), 240, 5)
            self.log.info('RTC agent limit read-back at the served outstation: %s', view)
            if not view:
                raise RuntimeError('the RTC agent\'s limit never reached the served outstation (Julia start-up or install failure):\n'
                                   + self.platform.log_tail(80))

    def stop(self):
        logs = self.work / 'logs'
        logs.mkdir(exist_ok=True)
        if getattr(self, 'subscriber', None) is not None:
            self.subscriber.terminate()
            self.reports.close()
        for name, fn in (('go client', lambda: self.go_client.stop(logs / 'go_client.log')), ('platform', lambda: self.platform and self.platform.shutdown()),
                         ('go server', lambda: (logs / 'go_server.log').write_text(self.go_server.logs()) and self.go_server.stop()),
                         ('outstation', lambda: (logs / 'outstation.log').write_text(self.outstation.logs()) and self.outstation.stop()),
                         ('sunspec device', lambda: self.sunspec_device.stop()), ('openfmb', lambda: self.openfmb.stop()),
                         ('mosquitto', lambda: self.mosquitto.stop())):
            try:
                if not (self.args.keep and name in ('platform', 'go server', 'outstation', 'mosquitto')):
                    fn()
            except Exception as e:
                self.log.warning('stopping %s: %r', name, e)

    # ---- the matrix -----------------------------------------------------------------------------------------------
    def record(self, kind, src, dst, ok, detail):
        self.results.append((kind, src, dst, bool(ok), detail))
        print(f'{"PASS" if ok else "FAIL"} {kind:9} {src:>7} -> {dst:<7} {detail}', flush=True)

    # ---- the RTC agent: observed through its status topic, commanded through its hub topic ----------------------
    def rtc_limit_view(self):
        """The agent's Active Power Limit as an independent 1815.2 master reads it from the served outstation: AI 148 is
        the DWMX.LimW read-back (raw tenths... per the profile's multiplier). The enable (BI 69) is a binary input the
        reference control station does not report, so it is not observable this way."""
        from interoperability.discovery.device_formats import dnp3_scaling
        raw = self.dnp3_read([148], 30).get(148)
        return {'LimWMax': None if raw is None else raw * dnp3_scaling('AI_148')[0]}

    def rtc_reset(self):
        """Back to an unlimited, disabled limit so that the next control path has a change to make."""
        self.platform.vctl('publish', configs.RTC_CONTROL_TOPIC, json.dumps({'DWMX': {'LimW': 100, 'ModEna': False}}), timeout=60)
        wait_for(lambda: near(self.rtc_limit_view().get('LimWMax'), 100), 90, 2)

    def telemetry_rtc(self, dst):
        """The RTC agent's status (its power and state of charge) reaches the external party at ``dst``."""
        from protocol_proxy.protocol.ieee2030_5.models import sep
        soc = configs.RTC_SOC
        if dst == 'OpenFMB':
            topic = topic_of(openfmb_alias('RTC', 'rtc', 'reading'))
            got = self.openfmb.wait_for(topic, PROTO['ess'][0],
                                        lambda m: near(dig(m, 'essReading', 'readingMMXU', 'W', 'net', 'cVal', 'mag'), configs.RTC_W), timeout=60)
            return self.expect({'W': dig(got or {}, 'essReading', 'readingMMXU', 'W', 'net', 'cVal', 'mag')}, {'W': configs.RTC_W})
        if dst == 'SunSpec':
            def read():
                sf = self.sunspec_master.read_point('713_Pct_SF') or 0
                raw = self.sunspec_master.read_point('713_SoC')
                return {'713_SoC_pct': None if raw is None else raw * 10 ** sf}
            got = wait_for(lambda: (lambda g: g if near(g['713_SoC_pct'], soc) else None)(read()), 60, 2) or read()
            return self.expect(got, {'713_SoC_pct': soc})
        if dst == 'DNP3':
            # DSTO.UseSocPct (AI 48) as the raw integer the profile's multiplier gives; the limit read-back (AI 148) is
            # what the control paths into the agent observe.
            from interoperability.discovery.device_formats import dnp3_scaling
            return self.observe_telemetry(dst, expected_dnp3={48: round(soc / dnp3_scaling('AI_48')[0])}, timeout=90)
        if dst == '2030.5':
            def read():
                status = self.go_server.fetch('/edev/1/der/1/ders', sep.DERStatus)
                value = getattr(getattr(status, 'stateOfChargeStatus', None), 'value', None)
                return {'stateOfChargeStatus': value}
            def ok(v):
                return v is not None and (near(v, soc) or near(v, soc * 100))      # percent, or 2030.5's hundredths of a percent
            got = wait_for(lambda: (lambda g: g if ok(g['stateOfChargeStatus']) else None)(read()), 90, 3) or read()
            return ok(got['stateOfChargeStatus']), f'observed {got}, expected {soc} % (as percent or hundredths)'
        raise ValueError(dst)

    def wanted(self, kind, src, dst):
        only = self.args.only
        return not only or f'{kind}:{src}>{dst}' in only

    def dnp3_read(self, indices, timeout=40):
        """What an independent master reads from the outstation the platform serves (one integrity poll)."""
        reader = dnp3_tool.ReferenceControlStation(self.work / 'dnp3', self.ports['dnp3_served'],
                                                   dnp3_tool.impossible(dnp3_tool.trimmed(self.dnp3_profile, ai=indices), indices),
                                                   control_loop_interval=3600, name=f'e2e-dnp3-reader-{int(time.time())}')
        try:
            reader.start()
            wait_for(lambda: all(i in dnp3_tool.read_values(reader.logs()) for i in indices), timeout, 1)
            return {i: v[-1] for i, v in dnp3_tool.read_values(reader.logs()).items()}
        finally:
            reader.stop()

    def expect(self, observed: dict, expected: dict):
        bad = {k: observed.get(k) for k, v in expected.items() if not near(observed.get(k), v)}
        return not bad, f'observed {observed}' + (f', expected {expected}' if bad else '')

    # telemetry targets: observe the external party on the target side
    def observe_telemetry(self, dst, expected_sunspec=None, expected_dnp3=None, expected_sep2=None, source_profile=None, timeout=45):
        if dst == 'SunSpec':
            def read():
                return {name: self.sunspec_master.read_point(name) for name in expected_sunspec}
            got = wait_for(lambda: read() if all(near(read()[k], v) for k, v in expected_sunspec.items()) else None, timeout, 2) or read()
            return self.expect(got, expected_sunspec)
        if dst == 'DNP3':
            indices = list(expected_dnp3)
            got = {}
            deadline = time.time() + timeout
            while time.time() < deadline:
                got = self.dnp3_read(indices, 25)
                if all(near(got.get(i), v) for i, v in expected_dnp3.items()):
                    break
            return self.expect(got, expected_dnp3)
        if dst == '2030.5':
            from protocol_proxy.protocol.ieee2030_5.models import sep
            def quantity(v):
                return None if v is None else v.value * 10 ** (v.multiplier or 0)
            def read():
                out = {}
                if 'setMaxW' in expected_sep2:
                    out['setMaxW'] = quantity(self.go_server.fetch('/edev/1/der/1/derg', sep.DERSettings).setMaxW)
                if 'rtgMaxV' in expected_sep2:
                    out['rtgMaxV'] = quantity(self.go_server.fetch('/edev/1/der/1/dercap', sep.DERCapability).rtgMaxV)
                if 'readings' in expected_sep2:
                    out['readings'] = self.go_server.readings_accepted()
                return out
            def satisfied(got):
                return all((got.get(k, 0) > v if k == 'readings' else near(got.get(k), v)) for k, v in expected_sep2.items())
            got = wait_for(lambda: (lambda g: g if satisfied(g) else None)(read()), timeout, 3) or read()
            return satisfied(got), f'observed {got}, expected {expected_sep2}'
        raise ValueError(dst)

    def observe_control(self, dst, since, limit, timeout=45, enable=True):
        if dst == 'SunSpec':
            def read():
                return {'704_WMaxLimPct': self.sunspec_device.get_point('704_WMaxLimPct'), '704_WMaxLimPctEna': self.sunspec_device.get_point('704_WMaxLimPctEna')}
            expected = {'704_WMaxLimPct': limit, **({'704_WMaxLimPctEna': 1} if enable else {})}
            got = wait_for(lambda: (lambda g: g if all(near(g[k], v) for k, v in expected.items()) else None)(read()), timeout, 1) or read()
            return self.expect(got, expected)
        if dst == 'DNP3':
            # The reference outstation logs analog operates; it logs nothing for binary ones, so BO_17 (the enable) is
            # verified through the driver's report of the outstation's DNP3 response (see resource_bridge_reports.log).
            raw = limit * 10
            def read():
                return [int(v) for v in re.findall(r'Outstation received Direct Operate AO87 = (-?\d+)', self.outstation.logs()[since:])]
            wait_for(lambda: raw in read(), timeout, 1)
            ao = read()
            return raw in ao, f'outstation received AO87 {ao[-4:]} (expected {raw}); BO17 operates are not logged by the outstation'
        if dst == 'RTC':
            # The limit's value at the agent, read back at the served outstation; the enable is not readable there.
            read = self.rtc_limit_view
            expected = {'LimWMax': limit}
            got = wait_for(lambda: (lambda g: g if all(near(g.get(k), v) for k, v in expected.items()) else None)(read()), timeout, 2) or read()
            return self.expect(got, expected)
        if dst == '2030.5':
            # The Go client applies opModMaxLimW as hundredths of a percent of its 10 kW rating, so a limit of N (our
            # convention: percent) caps its reported P at about N W: the value is visible in its report lines.
            def read():
                text = self.go_client.logs()[since:]
                events = re.findall(r'statemachine: .*?→ (EVENT_\w+)|DERControlList (?:poll|refreshed).*\+(\d+) new', text)
                reports = [float(p) for p in re.findall(r'P=(-?[\d.]+)W', text)]
                return events, reports
            def satisfied():
                events, reports = read()
                return bool(events) and any(abs(p - limit) <= 2 for p in reports)
            wait_for(satisfied, timeout, 2)
            events, reports = read()
            ok = satisfied()
            return ok, (f'Go client events {events[:3]}; reported P {sorted(set(reports))[:4]} W (a limit of {limit} read as {limit / 100:.2f} %'
                        f' of 10 kW: the hundredths-of-percent convention of opModMaxLimW)')
        raise ValueError(dst)

    def rounds(self, kind):
        """The paths of one kind grouped so that no target has two sources at once: a Latin square over the devices
        pairs every target with a different source in each round, so a round's paths run side by side and the rounds
        run in sequence. A target fed by two sources at once would hold whichever wrote last, and a check would be a
        coin toss (seen with the 2030.5 rating both SunSpec's nameplate and DNP3 carried)."""
        n = len(PROTOCOLS)
        for shift in range(1, n):
            pairs = [(PROTOCOLS[(i + shift) % n], PROTOCOLS[i]) for i in range(n)]
            pairs = [(src, dst) for src, dst in pairs if self.wanted(kind, src, dst)]
            if pairs:
                yield pairs

    def activate_bridges(self, names, timeout=30):
        """Store the Resource Bridge's configuration with these matrix bridges (the permanent ones, the RTC's, stay)
        and wait until the adapter has reported each of them started."""
        log_path = self.work / 'volttron.log'
        offset = log_path.stat().st_size if log_path.exists() else 0
        bridges = [b for b in self.configs.bridges if not configs.is_matrix_bridge(b) or b['name'] in names]
        path = configs.write_adapter_config(self.work / 'configs', bridges)
        self.platform.store_config(configs.RESOURCE_BRIDGE, 'config', path)

        def started():
            with open(log_path, errors='replace') as f:
                f.seek(offset)
                text = f.read()
            return all(f'Bridge {name}:' in text for name in names)
        if wait_for(started, timeout, 0.5):
            self.log.info('bridges active: %s', ', '.join(names))
        else:
            self.log.warning('not every bridge of %s reported started within %ss', names, timeout)
        time.sleep(self.BRIDGE_SETTLE)     # let the bus register the new subscriptions before any stimulus

    BRIDGE_SETTLE = 3.0

    def run_paths(self, kind, pairs):
        """Run these paths, side by side unless --sequential, recording each result."""
        def one(pair):
            src, dst = pair
            try:
                ok, detail = (self.telemetry if kind == 'telemetry' else self.control)(src, dst)
            except Exception as e:
                ok, detail = False, f'{type(e).__name__}: {e}'
                self.log.exception('%s %s -> %s', kind, src, dst)
            self.record(kind, src, dst, ok, detail)
        if self.args.sequential or len(pairs) == 1:
            for pair in pairs:
                one(pair)
        else:
            with ThreadPoolExecutor(max_workers=len(pairs), thread_name_prefix=kind) as pool:
                list(pool.map(one, pairs))

    def run(self):
        if self.args.sequential:
            # Every matrix bridge at once and one path at a time: the pre-2026-10-23 behaviour, kept for comparison.
            self.activate_bridges(sorted(configs.MATRIX_BRIDGE_NAMES))
            for kind in ('telemetry', 'control'):
                for src in PROTOCOLS:
                    for dst in PROTOCOLS:
                        if src != dst and self.wanted(kind, src, dst):
                            self.run_paths(kind, [(src, dst)])
        else:
            for kind in ('telemetry', 'control'):
                for pairs in self.rounds(kind):
                    self.activate_bridges([configs.bridge_name(kind, src, dst) for src, dst in pairs])
                    if kind == 'telemetry' and any(src == '2030.5' and dst in ('DNP3', 'SunSpec') for src, dst in pairs):
                        self.refresh_go_client()
                    self.run_paths(kind, pairs)
        # ---- the RTC agent: controls into its modes, its status out ----
        if self.args.rtc:
            for src in PROTOCOLS:
                if not self.wanted('control', src, 'RTC'):
                    continue
                try:
                    self.rtc_reset()
                    ok, detail = self.control(src, 'RTC')
                except Exception as e:
                    ok, detail = False, f'{type(e).__name__}: {e}'
                    self.log.exception('control %s -> RTC', src)
                self.record('control', src, 'RTC', ok, detail)
            for dst in PROTOCOLS:
                if not self.wanted('telemetry', 'RTC', dst):
                    continue
                try:
                    ok, detail = self.telemetry_rtc(dst)
                except Exception as e:
                    ok, detail = False, f'{type(e).__name__}: {e}'
                    self.log.exception('telemetry RTC -> %s', dst)
                self.record('telemetry', 'RTC', dst, ok, detail)

    def refresh_go_client(self):
        """Make the 2030.5 client report its capability and settings again. It does so once, when it registers, so a
        bridge from the served 2030.5 device activated after that would never see them; the polled sources republish
        every interval and need nothing of the kind."""
        self.go_client.stop()                   # removes the container, so its log starts afresh
        self.go_client.start()
        if self.go_client.wait_for_log(r'DER capability and settings reported', 120) is None:
            self.log.warning('the 2030.5 client did not report its settings again within 120 s')
        else:
            self.log.info('2030.5 client restarted and reported')

    def wait_go_client_idle(self, timeout=180):
        """Wait until the 2030.5 client has no control event running: the simulator executes one event at a time and
        drops a new one that arrives while another runs ("multi-event primacy arbitration" is a TODO in its log)."""
        def idle():
            transitions = re.findall(r'statemachine: \S+ → (EVENT_\w+|DEFAULT)', self.go_client.logs())
            return not transitions or transitions[-1] in ('DEFAULT', 'EVENT_COMPLETED', 'EVENT_CANCELLED')
        if not wait_for(idle, timeout, 2):
            self.log.warning('the 2030.5 client still has a control event running after %ss', timeout)

    def clear_openfmb(self, kind, src, dst):
        """Forget the party's received messages on this path's topic only; a path whose target is not OpenFMB has no
        topic and clears nothing (clear(None) would wipe every concurrent path's messages)."""
        topic = self.openfmb_topic(kind, src, dst)
        if topic is not None:
            self.openfmb.clear(topic)

    def openfmb_topic(self, kind, src, dst):
        """The broker topic a path with an OpenFMB target is observed on (None for other targets)."""
        if dst != 'OpenFMB':
            return None
        role = roles(kind, src, 'OpenFMB')[0]
        return topic_of(openfmb_alias(src, role, 'reading' if kind == 'telemetry' else 'control'))

    def telemetry(self, src, dst):
        """Telemetry is standing state at the external source; the check is that the external target sees it."""
        if src == 'OpenFMB':
            family = OPENFMB_FAMILY[dst]
            role = roles('telemetry', 'OpenFMB', dst)[1]
            key = 'solarReading' if family == 'solar' else 'essReading'
            # The OpenFMB party reports quantities the other sources do not (reactive power, a phase voltage), so what
            # arrives at the target is attributable to it; the bridges write changes only, so the values move each time.
            self.openfmb_var = getattr(self, 'openfmb_var', VAR) - 1
            before = self.go_server.readings_accepted()
            self.openfmb.publish(topic_of(openfmb_alias(dst, role, 'reading')), PROTO[family][0],
                                 {key: {'readingMMXU': {'VAr': {'net': {'cVal': {'mag': self.openfmb_var}}}, 'PhV': {'phsA': {'cVal': {'mag': V_PHASE}}}}}})
            if dst == '2030.5':
                return self.observe_telemetry(dst, expected_sep2={'readings': before})
            if dst == 'SunSpec':
                return self.observe_telemetry(dst, expected_sunspec={'701_Var': self.openfmb_var, '701_VL1': V_PHASE * 10})      # V_SF -1
            return self.observe_telemetry(dst, expected_dnp3={541: self.openfmb_var, 547: V_PHASE}, timeout=60)
        if dst == 'OpenFMB':
            family = OPENFMB_FAMILY[src]
            role = roles('telemetry', src, 'OpenFMB')[0]
            key = 'solarReading' if family == 'solar' else 'essReading'
            self.clear_openfmb('telemetry', src, dst)
            if src == '2030.5':
                # The Go client's readings follow its PV simulator; the profile at the broker must carry one of them.
                reports = [r['P'] for r in self.go_client.reports()[-20:]]
                got = self.openfmb.wait_for(topic_of(openfmb_alias(src, role, 'reading')), PROTO[family][0],
                                            lambda m: dig(m, key, 'readingMMXU', 'W', 'net', 'cVal', 'mag') is not None, timeout=60)
                w = dig(got or {}, key, 'readingMMXU', 'W', 'net', 'cVal', 'mag')
                reports += [r['P'] for r in self.go_client.reports()[-20:]]
                ok = got is not None and any(near(w, p, 1.0) for p in reports)
                return ok, f'ESSReadingProfile W={w}; Go client reported P in {sorted(set(reports))[-4:]}'
            got = self.openfmb.wait_for(topic_of(openfmb_alias(src, role, 'reading')), PROTO[family][0],
                                        lambda m: near(dig(m, key, 'readingMMXU', 'W', 'net', 'cVal', 'mag'), W), timeout=60)
            view = {'W': dig(got or {}, key, 'readingMMXU', 'W', 'net', 'cVal', 'mag'), 'Hz': dig(got or {}, key, 'readingMMXU', 'Hz', 'mag')}
            return self.expect(view, {'W': W, 'Hz': HZ})
        if dst == 'SunSpec':
            if src == '2030.5':
                return self.observe_telemetry(dst, expected_sunspec={'702_WMax': 10000})      # the Go client's DERSettings.setMaxW
            return self.observe_telemetry(dst, expected_sunspec={'701_W': W, '701_Hz': HZ * 1000})
        if dst == 'DNP3':
            if src == '2030.5':
                return self.observe_telemetry(dst, expected_dnp3={32: 10000}, timeout=60)         # DERSettings.setMaxW -> AI_32
            return self.observe_telemetry(dst, expected_dnp3={537: W, 536: HZ}, timeout=60)
        if dst == '2030.5':
            if src == 'SunSpec':
                return self.observe_telemetry(dst, expected_sep2={'setMaxW': WMAX})
            if src == 'DNP3':
                return self.observe_telemetry(dst, expected_sep2={'rtgMaxV': RTG_MAX_V_RAW / 10})
        raise ValueError((src, dst))

    def control(self, src, dst):
        """Control is an order given at the external source; the check is that the external target device received it.
        Sources that can toggle the enable (SunSpec, OpenFMB) first disable with another value, so the enable is a
        change the bridges carry; DNP3's reference control station only latches on, and 2030.5 has no enable."""
        limit = LIMIT[src] + TARGET_OFFSET[dst]
        if dst == '2030.5':
            self.wait_go_client_idle()
        since_out = len(self.outstation.logs())
        since_go = len(self.go_client.logs())
        self.clear_openfmb('control', src, dst)
        master = None
        try:
            if src == 'SunSpec':
                self.sunspec_master.write_point('704_WMaxLimPctEna', 0)
                self.sunspec_master.write_point('704_WMaxLimPct', limit + 1)
                time.sleep(3)
                since_out, since_go = len(self.outstation.logs()), len(self.go_client.logs())
                self.clear_openfmb('control', src, dst)
                self.sunspec_master.write_point('704_WMaxLimPct', limit)
                self.sunspec_master.write_point('704_WMaxLimPctEna', 1)
            elif src == 'DNP3':
                master = dnp3_tool.ReferenceControlStation(self.work / 'dnp3', self.ports['dnp3_served'],
                                                           dnp3_tool.with_stimulus(dnp3_tool.trimmed(self.dnp3_profile, ai=(148, 69), ao=(87,), bi=(69,), bo=(17,)),
                                                                                   ao_targets={87: limit}),
                                                           control_loop_interval=5, name=f'e2e-dnp3-master-{int(time.time())}').start()
                wrote = master.wait_for_log(rf'wrote AO87 = {limit * 10}', 30)
                if not wrote:
                    return False, 'the reference control station never wrote AO87 to the served outstation: ' + master.logs()[-500:]
                if dst == 'RTC':
                    # The agent's read-back is observed by another master on the same single-connection outstation.
                    master.stop()
                    master = None
            elif src == '2030.5':
                created = self.go_server.create_control(limit)
                self.log.info('go server control %s: opModMaxLimW %s', created, limit)
            elif src == 'OpenFMB':
                family = OPENFMB_FAMILY[dst]
                role = roles('control', 'OpenFMB', dst)[1]
                a, b, c = (('solarControl', 'solarControlFSCC', 'SolarControlScheduleFSCH') if family == 'solar'
                           else ('essControl', 'essControlFSCC', 'essControlScheduleFSCH'))
                def profile(value, enabled):
                    entry = {'startTime': {'seconds': int(time.time())},
                             'control': {'limitWOperation': {'maxLimParameter': {'modEna': enabled}, 'wMaxSptVal': value}}}
                    return {a: {b: {c: {'ValDCSG': {'crvPts': [entry]}}}}}
                topic = topic_of(openfmb_alias(dst, role, 'control'))
                self.openfmb.publish(topic, PROTO[family][1], profile(limit + 1, False))
                time.sleep(3)
                since_out, since_go = len(self.outstation.logs()), len(self.go_client.logs())
                self.openfmb.publish(topic, PROTO[family][1], profile(limit, True))
            if dst == 'OpenFMB':
                family = OPENFMB_FAMILY[src]
                role = roles('control', src, 'OpenFMB')[0]
                a, b, c = (('solarControl', 'solarControlFSCC', 'SolarControlScheduleFSCH') if family == 'solar'
                           else ('essControl', 'essControlFSCC', 'essControlScheduleFSCH'))
                # The source device pushes the limit and its enable as it receives them, possibly as separate writes, so
                # the broker may see them in separate control profiles: both must have arrived since the stimulus.
                topic, proto = topic_of(openfmb_alias(src, role, 'control')), PROTO[family][1]
                def seen():
                    limits, enables = [], []
                    for payload in self.openfmb.messages_on(topic):
                        try:
                            m = decode_profile(proto, payload)
                        except Exception:
                            continue
                        for pt in dig(m, a, b, c, 'ValDCSG', 'crvPts') or []:
                            limits.append(dig(pt, 'control', 'limitWOperation', 'wMaxSptVal'))
                            enables.append(dig(pt, 'control', 'limitWOperation', 'maxLimParameter', 'modEna'))
                    return limits, enables
                need_enable = src != 'DNP3'            # the reference control station cannot toggle BO_17, so no change to carry
                def satisfied():
                    limits, enables = seen()
                    return any(near(v, limit) for v in limits) and (not need_enable or any(e is True for e in enables))
                ok = bool(wait_for(satisfied, 150 if src == '2030.5' else 60, 1))
                limits, enables = seen()
                return ok, f'control profiles at the broker: wMaxSptVal {limits[-4:]}, modEna {enables[-4:]}'
            return self.observe_control(dst, since_out if dst == 'DNP3' else since_go, limit,
                                        # the Go client polls and ticks its event state machine every 60 s
                                        timeout=300 if dst == '2030.5' else (180 if src == '2030.5' else 60), enable=src != 'DNP3')
        finally:
            if master is not None:
                master.stop()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--openfmb', choices=('bus',), default='bus', help='OpenFMB on the VOLTTRON bus (the only mode; translate mode was removed 2026-10-29)')
    parser.add_argument('--rtc', action='store_true', help='also install the real-time control agent and run its eight paths')
    parser.add_argument('--work', default=os.environ.get('E2E_PLATFORM_WORK', '/tmp/e2e-platform'))
    parser.add_argument('--keep', action='store_true', help='leave the platform and the containers running afterwards')
    parser.add_argument('--keep-work', action='store_true', help='do not wipe the work directory first')
    parser.add_argument('--only', help='comma-separated paths, e.g. telemetry:SunSpec>DNP3,control:OpenFMB>2030.5')
    parser.add_argument('--poll-interval', type=float, default=2.0)
    parser.add_argument('--persistent', action='store_true',
                        help='force persistent IPC connections to every proxy (the interfaces default to this)')
    parser.add_argument('--sequential', action='store_true',
                        help='all matrix bridges at once and one path at a time (the pre-2026-10-23 behaviour)')
    parser.add_argument('--per-message', action='store_true',
                        help='force one IPC connection per message to every proxy (the pre-2026-10-22 behaviour)')
    args = parser.parse_args(argv)
    args.only = set(args.only.split(',')) if args.only else None
    Path(args.work).mkdir(parents=True, exist_ok=True)
    logging.basicConfig(filename=os.environ.get('E2E_LOG', str(Path(args.work) / 'e2e.log')), level=logging.INFO,
                        format='%(asctime)s %(name)s %(levelname)s %(message)s')
    logging.getLogger('e2e').addHandler(logging.StreamHandler(sys.stdout))
    matrix = Matrix(args)
    code = 2
    try:
        t0 = time.time()
        matrix.start_external()
        matrix.start_platform()
        print(f'stack up in {time.time() - t0:.0f}s; openfmb mode {args.openfmb}', flush=True)
        matrix.run()
        failed = [(k, s, d) for k, s, d, ok, _ in matrix.results if not ok]
        print(f'\n{len(matrix.results) - len(failed)}/{len(matrix.results)} passed' + (f'; FAILED: {[f"{k} {s}>{d}" for k, s, d in failed]}' if failed else ''))
        code = 1 if failed else 0
    except Exception:
        import traceback
        traceback.print_exc()
        if matrix.platform is not None:
            print(matrix.platform.log_tail(60))
    finally:
        # Teardown in a thread with a deadline: a stuck client library must not keep the run alive.
        import threading
        stopper = threading.Thread(target=matrix.stop, daemon=True)
        stopper.start()
        stopper.join(120)
        if stopper.is_alive():
            print('teardown did not finish within 120 s; exiting anyway', flush=True)
    sys.stdout.flush()
    os._exit(code)


if __name__ == '__main__':
    sys.exit(main())
