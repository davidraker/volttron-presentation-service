"""End-to-end telemetry from a SunSpec inverter and an IEEE 1815.2 outstation into an IEEE 2030.5 server.

Runs ``tests/e2e_to_2030_5/harness.py`` in a subprocess: the fake driver's SunSpec publish and a dnp3py outstation
polled through the real DNP3 proxy -> this service's chains (sunspec / 1815.2.inputs -> 2030.5 -> mirror points) ->
the ieee2030_5 driver interface through the real IEEE 2030.5 proxy -> the GridAPPS-D Go sep2server in Docker, whose
copies are read back over mutual TLS. Needs the modular driver stack, both proxies, dnp3py and Docker; skipped otherwise.
"""
import shutil
import subprocess

from pathlib import Path

import pytest

from volttrontesting.harness import free_port, run_harness

for module in ('volttron.driver.interfaces.dnp3.dnp3', 'volttron.driver.interfaces.ieee2030_5.ieee2030_5',
               'protocol_proxy.protocol.dnp3', 'protocol_proxy.protocol.ieee2030_5', 'dnp3.outstation'):
    pytest.importorskip(module)
if shutil.which('docker') is None or subprocess.run(['docker', 'version'], capture_output=True).returncode != 0:
    pytest.skip('Docker is not available', allow_module_level=True)

HARNESS = Path(__file__).with_name('e2e_to_2030_5') / 'harness.py'
EXPECTED_CHECKS = 12


def test_telemetry_to_2030_5(tmp_path):
    ports = [free_port() for _ in range(4)]
    run_harness(HARNESS, *ports, tmp_path / 'work', log_path=tmp_path / 'e2e.log', timeout=600).assert_ok(
        f'{EXPECTED_CHECKS}/{EXPECTED_CHECKS} passed')
