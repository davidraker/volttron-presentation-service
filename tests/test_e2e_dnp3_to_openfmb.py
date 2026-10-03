"""End-to-end telemetry from an IEEE 1815.2 outstation to an OpenFMB ESSReadingProfile on an MQTT topic.

Runs ``tests/e2e_dnp3_openfmb/harness.py`` in a subprocess: dnp3py outstation -> DNP3 driver interface through the
real DNP3 protocol proxy -> the driver's [values, meta] message -> this service's resolve and transform chain ->
protobuf -> message bus adapter -> MQTT proxy publish (paho mocked; no broker). Needs the modular driver stack, the
DNP3 proxy, dnp3py, the bus adapter and protobuf importable, so it is skipped in a service-only environment.
"""
import os
import socket
import subprocess
import sys

from pathlib import Path

import pytest

for module in ('volttron.driver.interfaces.dnp3.dnp3', 'protocol_proxy.protocol.dnp3', 'protocol_proxy.protocol.mqtt',
               'dnp3.outstation', 'bus_adapter.agent', 'google.protobuf'):
    pytest.importorskip(module)

HARNESS = Path(__file__).with_name('e2e_dnp3_openfmb') / 'harness.py'
EXPECTED_CHECKS = 11


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]


def test_dnp3_to_openfmb_telemetry(tmp_path):
    log = tmp_path / 'e2e.log'
    proc = subprocess.run([sys.executable, str(HARNESS), str(_free_port())], capture_output=True, text=True, timeout=240,
                          env={**os.environ, 'E2E_LOG': str(log)})
    report = proc.stdout + proc.stderr
    if proc.returncode != 0 and log.exists():
        report += '\n--- log ---\n' + log.read_text()[-4000:]
    assert proc.returncode == 0, report
    assert f'{EXPECTED_CHECKS}/{EXPECTED_CHECKS} passed' in proc.stdout, report
