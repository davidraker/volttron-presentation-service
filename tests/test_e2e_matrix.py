"""Telemetry and control between every ordered pair of SunSpec, DNP3, IEEE 2030.5 and OpenFMB, end to end.

Runs ``tests/e2e_matrix/harness.py`` in a subprocess: the Modbus, DNP3 and 2030.5 driver interfaces in both roles
(each pair through one real proxy subprocess), the MQTT proxy with paho mocked, this service's registry and chains,
and the harness standing in for the service's DeviceWriter. Needs the modular driver stack, the three proxies and
protobuf importable, so it is skipped in a service-only environment. Takes a few minutes.
"""
from pathlib import Path

import pytest

from volttrontesting.harness import run_harness

for module in ('volttron.driver.interfaces.modbus.modbus', 'volttron.driver.interfaces.dnp3.dnp3',
               'volttron.driver.interfaces.ieee2030_5.ieee2030_5', 'protocol_proxy.protocol.modbus',
               'protocol_proxy.protocol.dnp3', 'protocol_proxy.protocol.ieee2030_5', 'protocol_proxy.protocol.mqtt',
               'dnp3.outstation', 'google.protobuf', 'cryptography'):
    pytest.importorskip(module)

HARNESS = Path(__file__).with_name('e2e_matrix') / 'harness.py'
EXPECTED_PATHS = 24


def test_every_protocol_pair_carries_telemetry_and_control(tmp_path):
    run_harness(HARNESS, tmp_path / 'work', log_path=tmp_path / 'e2e.log', timeout=1200).assert_ok(
        f'{EXPECTED_PATHS}/{EXPECTED_PATHS} passed')
