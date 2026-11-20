"""End-to-end telemetry from an IEEE 1815.2 outstation to an OpenFMB ESSReadingProfile on an MQTT topic.

Runs ``tests/e2e_dnp3_openfmb/harness.py`` in a subprocess: dnp3py outstation -> DNP3 driver interface through the
real DNP3 protocol proxy -> the driver's [values, meta] message -> a Resource Bridge whose chain this service resolves
-> the profile on the local OpenFMB topic -> message bus adapter relaying it as protobuf -> MQTT proxy publish (paho
mocked; no broker). Needs the modular driver stack, the DNP3 proxy, dnp3py, the Resource Bridge, the bus adapter and
protobuf importable, so it is skipped in a service-only environment.
"""
from pathlib import Path

import pytest

from volttrontesting.harness import free_port, run_harness

for module in ('volttron.driver.interfaces.dnp3.dnp3', 'protocol_proxy.protocol.dnp3', 'protocol_proxy.protocol.mqtt',
               'dnp3.outstation', 'bus_adapter.agent', 'resource_bridge.agent', 'google.protobuf'):
    pytest.importorskip(module)

HARNESS = Path(__file__).with_name('e2e_dnp3_openfmb') / 'harness.py'
EXPECTED_CHECKS = 14


def test_dnp3_to_openfmb_telemetry(tmp_path):
    run_harness(HARNESS, free_port(), log_path=tmp_path / 'e2e.log', timeout=240).assert_ok(
        f'{EXPECTED_CHECKS}/{EXPECTED_CHECKS} passed')
