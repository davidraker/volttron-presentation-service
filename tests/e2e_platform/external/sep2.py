"""The GridAPPS-D Go IEEE 2030.5 implementations as independent external parties: ``sep2server`` as the utility server
our platform's DER client talks to, ``inverterclient`` as the DER client that registers with the server our platform
serves. Both run in Docker on the host network; certificates come from the server image's ``certs`` commands (one CA
for every party, as a CSIP deployment would have)."""
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

import volttron.driver.interfaces.ieee2030_5 as sep2_package

E2E_DIR = Path(os.environ.get('IEEE2030_5_DRIVER_REPO', Path(sep2_package.__file__).resolve().parents[5])) / 'tests' / 'e2e_sep2server'
sys.path.insert(0, str(E2E_DIR))
from sep2server import ADMIN_KEY, IMAGE as SERVER_IMAGE, PEN, Sep2Server, _run_certs, ensure_image, write_fixture   # noqa: E402
from protocol_proxy.protocol.ieee2030_5.identity import lfdi_from_cert, sfdi_from_lfdi                               # noqa: E402

CLIENT_IMAGE = os.environ.get('SEP2CLIENT_IMAGE', 'inverterclient:e2e')


def client_image_present() -> bool:
    return subprocess.run(['docker', 'image', 'inspect', CLIENT_IMAGE], capture_output=True).returncode == 0


def generate_certs(cert_dir: Path) -> dict[str, Path]:
    """One CA; a server certificate for 127.0.0.1 (used by the Go server and by the server our platform serves); a
    device certificate for our platform's DER client; a device certificate for the Go client; a receiver certificate
    for our client's notification listener."""
    cert_dir.mkdir(parents=True, exist_ok=True)
    cert_dir.chmod(0o755)
    _run_certs(cert_dir, 'generate-ca', '-out', '/tls')
    _run_certs(cert_dir, 'generate-server', '-out', '/tls', '-ca', '/tls/ca.crt', '-ca-key', '/tls/ca.key', '-hosts', '127.0.0.1,localhost')
    _run_certs(cert_dir, 'generate-device', '-out', '/tls', '-ca', '/tls/ca.crt', '-ca-key', '/tls/ca.key', '-name', 'volttron',
               '-hw-serial', 'VT0001', '-hw-type', f'1.3.6.1.4.1.{PEN}.1')
    _run_certs(cert_dir, 'generate-device', '-out', '/tls', '-ca', '/tls/ca.crt', '-ca-key', '/tls/ca.key', '-name', 'goclient',
               '-hw-serial', 'GO0001', '-hw-type', f'1.3.6.1.4.1.{PEN}.1')
    (cert_dir / 'notify').mkdir(exist_ok=True)
    _run_certs(cert_dir, 'generate-server', '-out', '/tls/notify', '-ca', '/tls/ca.crt', '-ca-key', '/tls/ca.key',
               '-hosts', '127.0.0.1,localhost', '-cn', 'VOLTTRON notify')
    for key in cert_dir.rglob('*.key'):
        key.chmod(0o644)
    return {'ca': cert_dir / 'ca.crt', 'server_cert': cert_dir / 'server.crt', 'server_key': cert_dir / 'server.key',
            'device_cert': cert_dir / 'volttron.crt', 'device_key': cert_dir / 'volttron.key',
            'goclient_cert': cert_dir / 'goclient.crt', 'goclient_key': cert_dir / 'goclient.key',
            'notify_cert': cert_dir / 'notify' / 'server.crt', 'notify_key': cert_dir / 'notify' / 'server.key'}


class CapturingSep2Server(Sep2Server):
    """sep2server with its traffic capture on (SEP2_TRAFFIC_CAPTURE=true, SEP2_TRAFFIC_DIR): every request it serves is
    recorded under ``capture_dir``, the only outside view of the MirrorMeterReadings it accepts but never exposes."""
    def __init__(self, cert_dir: Path, fixture: Path, port: int, admin_port: int, capture_dir: Path, name: str = 'sep2e2e'):
        super().__init__(cert_dir, fixture, port, admin_port, name=name)
        self.capture_dir = Path(capture_dir)
        self.capture_dir.mkdir(parents=True, exist_ok=True)
        self.capture_dir.chmod(0o777)

    def start(self, timeout: float = 20.0) -> None:
        subprocess.run(['docker', 'rm', '-f', self.name], capture_output=True)
        user = f'{os.getuid()}:{os.getgid()}'
        cmd = ['docker', 'run', '-d', '--name', self.name, '--network', 'host', '-u', user, '-e', 'HOME=/tmp',
               '-e', 'SSL_CERT_FILE=/tls/ca.crt', '-v', f'{self.cert_dir}:/tls:ro', '-v', f'{self.fixture.parent}:/fix:ro',
               '-v', f'{self.capture_dir}:/cap', '-e', 'SEP2_TRAFFIC_CAPTURE=true', '-e', 'SEP2_TRAFFIC_DIR=/cap',
               '-e', 'SEP2_CERT_DIR=/tls', '-e', f'SEP2_ADDR=127.0.0.1:{self.port}', '-e', f'SEP2_ADMIN_LISTEN=127.0.0.1:{self.admin_port}',
               '-e', f'SEP2_ADMIN_KEY={ADMIN_KEY}', '-e', f'SEP2_PEN={PEN}', '-e', 'SEP2_NOTIFICATION_ALLOW_LOOPBACK=true',
               '-e', f'SEP2_BOOT_FIXTURE=/fix/{self.fixture.name}', SERVER_IMAGE, 'serve']
        subprocess.run(cmd, check=True, capture_output=True)
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                self.admin('GET', '/api/der/controls?device=1')
                return
            except Exception:
                time.sleep(0.3)
        raise RuntimeError(f'sep2server did not come up:\n{self.logs()[-3000:]}')

    def captured(self, needle: str) -> int:
        """How many captured request records mention ``needle`` (a path fragment or element name)."""
        count = 0
        for path in self.capture_dir.rglob('*'):
            if path.is_file():
                try:
                    count += path.read_text(errors='replace').count(needle)
                except OSError:
                    pass
        return count


class GoServer:
    """The Go sep2server seeded with our platform's DER client (LFDI from its device certificate)."""
    def __init__(self, work: Path, certs: dict, port: int, admin_port: int, name='e2e-sep2server'):
        self.certs = certs
        self.lfdi = lfdi_from_cert(certs['device_cert'])
        fixture = work / 'fixture' / 'boot.yaml'
        fixture.parent.mkdir(parents=True, exist_ok=True)
        write_fixture(fixture, self.lfdi, sfdi_from_lfdi(self.lfdi))
        self.server = CapturingSep2Server(certs['ca'].parent, fixture, port, admin_port, work / 'sep2_capture', name=name)
        self.url = self.server.url

    def readings_accepted(self) -> int:
        """MirrorMeterReadings the server has accepted from our client, from its traffic capture."""
        return self.server.captured('MirrorMeterReading')

    def start(self):
        ensure_image()
        self.server.start()
        return self

    def stop(self):
        self.server.stop()

    def admin(self, method, path, body=None):
        return self.server.admin(method, path, body)

    def logs(self):
        return self.server.logs()

    def create_control(self, max_lim_w: int, duration: int = 120) -> str:
        """An opModMaxLimW DERControl for our client, starting now (the server wants >= 60 s); returns its mRID."""
        return self.server.create_control(int(time.time()) + 2, duration, max_lim_w=max_lim_w)

    def controls(self) -> list[dict]:
        return self.server.controls()

    def fetch(self, href: str, cls):
        """GET a resource as our client would (its certificate)."""
        import asyncio
        from protocol_proxy.protocol.ieee2030_5.transport import Sep2Http

        async def go():
            http = Sep2Http(self.url, cert_path=str(self.certs['device_cert']), key_path=str(self.certs['device_key']),
                            ca_path=str(self.certs['ca']), retries=1)
            try:
                return await http.get(href, cls)
            finally:
                await http.aclose()
        return asyncio.run(go())


class GoClient:
    """The Go inverterclient (a DER client with a built-in PV simulator) registered with the server our platform serves.

    Its upward reports are fixed by its simulator: DERCapability rtgMaxW 10000, DERSettings setMaxW 10000, DERStatus
    every report interval (operationalModeStatus 2 while operating), MirrorMeterReading W from a synthetic PV curve
    (sim clock from 06:00, ``--timescale`` sim seconds per real second). Received DERControls show in its log as state
    machine transitions and in the applied ``mode``/``P`` of its periodic report lines."""
    def __init__(self, certs: dict, server_url: str, pin: int, notify_port: int, timescale: int = 30, report_interval: int = 5,
                 name='e2e-sep2client'):
        self.certs, self.server_url, self.pin, self.notify_port, self.name = certs, server_url, pin, notify_port, name
        self.timescale, self.report_interval = timescale, report_interval
        self.lfdi = lfdi_from_cert(certs['goclient_cert'])
        self.sfdi = sfdi_from_lfdi(self.lfdi)

    def start(self):
        subprocess.run(['docker', 'rm', '-f', self.name], capture_output=True)
        tls = self.certs['ca'].parent
        cmd = ['docker', 'run', '-d', '--name', self.name, '--network', 'host', '-u', f'{os.getuid()}:{os.getgid()}',
               '-v', f'{tls}:/tls:ro', CLIENT_IMAGE, '--server', self.server_url, '--cert', '/tls/goclient.crt', '--key', '/tls/goclient.key',
               '--ca', '/tls/ca.crt', '--csip', '--pin', str(self.pin), '--scenario', 'normal', '--timescale', str(self.timescale),
               '--tick', '1s', '--report-interval', f'{self.report_interval}s', '--notify-listen', f'127.0.0.1:{self.notify_port}']
        subprocess.run(cmd, check=True, capture_output=True)
        return self

    def stop(self, dump_to: Path | None = None):
        if dump_to is not None:
            try:
                Path(dump_to).write_text(self.logs())
            except Exception:
                pass
        subprocess.run(['docker', 'rm', '-f', self.name], capture_output=True)

    def logs(self) -> str:
        done = subprocess.run(['docker', 'logs', self.name], capture_output=True, text=True)
        return done.stdout + done.stderr

    def wait_for_log(self, pattern: str, timeout: float = 60.0, since: int = 0) -> str | None:
        deadline = time.time() + timeout
        while time.time() < deadline:
            for line in self.logs()[since:].splitlines():
                if re.search(pattern, line):
                    return line
            time.sleep(1)
        return None

    def reports(self) -> list[dict]:
        """The periodic ``sim=HH:MM P=...W ... mode=...`` lines, parsed."""
        out = []
        for line in self.logs().splitlines():
            m = re.search(r'sim=(\S+)\s+P=(-?[\d.]+)W.*?mode=(\S+)', line)
            if m:
                out.append({'sim': m.group(1), 'P': float(m.group(2)), 'mode': m.group(3), 'line': line})
        return out
