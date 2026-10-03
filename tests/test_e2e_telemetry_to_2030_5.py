"""End-to-end telemetry from a SunSpec inverter and an IEEE 1815.2 outstation into an IEEE 2030.5 server.

Runs ``tests/e2e_to_2030_5/harness.py`` in a subprocess: the fake driver's SunSpec publish and a dnp3py outstation
polled through the real DNP3 proxy -> this service's chains (sunspec / 1815.2.inputs -> 2030.5 -> mirror points) ->
the ieee2030_5 driver interface through the real IEEE 2030.5 proxy -> the GridAPPS-D Go sep2server in Docker, whose
copies are read back over mutual TLS. Needs the modular driver stack, both proxies, dnp3py and Docker; skipped otherwise.
"""
import os
import shutil
import socket
import subprocess
import sys

from pathlib import Path

import pytest

for module in ('volttron.driver.interfaces.dnp3.dnp3', 'volttron.driver.interfaces.ieee2030_5.ieee2030_5',
               'protocol_proxy.protocol.dnp3', 'protocol_proxy.protocol.ieee2030_5', 'dnp3.outstation'):
    pytest.importorskip(module)
if shutil.which('docker') is None or subprocess.run(['docker', 'version'], capture_output=True).returncode != 0:
    pytest.skip('Docker is not available', allow_module_level=True)

HARNESS = Path(__file__).with_name('e2e_to_2030_5') / 'harness.py'
EXPECTED_CHECKS = 12


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]


def test_telemetry_to_2030_5(tmp_path):
    log = tmp_path / 'e2e.log'
    proc = subprocess.run([sys.executable, str(HARNESS), *(str(_free_port()) for _ in range(4)), str(tmp_path / 'work')],
                          capture_output=True, text=True, timeout=600, env={**os.environ, 'E2E_LOG': str(log)})
    report = proc.stdout + proc.stderr
    if proc.returncode != 0 and log.exists():
        report += '\n--- log ---\n' + log.read_text()[-5000:]
    assert proc.returncode == 0, report
    assert f'{EXPECTED_CHECKS}/{EXPECTED_CHECKS} passed' in proc.stdout, report
