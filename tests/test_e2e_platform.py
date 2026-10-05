"""The outside-in matrix on a real VOLTTRON platform with independent external parties (see e2e_platform/run.py).

Needs Docker with the sep2server:e2e, inverterclient:e2e, eclipse-mosquitto:2 and IEEE 1815.2 test tool images, the
driver stack in this venv and the platform's command-line tools; skipped otherwise. Takes several minutes per mode, so
it is opt-in: set E2E_PLATFORM=1.
"""
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

if os.environ.get('E2E_PLATFORM') != '1':
    pytest.skip('set E2E_PLATFORM=1 to run the real-platform matrix', allow_module_level=True)
for module in ('volttron.driver.interfaces.modbus.modbus', 'volttron.driver.interfaces.dnp3.dnp3', 'volttron.driver.interfaces.ieee2030_5.ieee2030_5',
               'protocol_proxy.protocol.mqtt', 'device_adapter.agent', 'bus_adapter.agent', 'umodbus', 'paho.mqtt.client', 'google.protobuf'):
    pytest.importorskip(module)
if not shutil.which('docker') or not all((Path(sys.executable).parent / exe).exists() for exe in ('volttron', 'vctl')):
    pytest.skip('docker and the VOLTTRON platform tools are required', allow_module_level=True)
for image in ('sep2server:e2e', 'inverterclient:e2e', 'eclipse-mosquitto:2', 'ieee-std-1815-2-test-tool-backend-dev:latest'):
    if subprocess.run(['docker', 'image', 'inspect', image], capture_output=True).returncode != 0:
        pytest.skip(f'docker image {image} is missing', allow_module_level=True)

RUN = Path(__file__).with_name('e2e_platform') / 'run.py'


@pytest.mark.parametrize('openfmb_mode', ['bus', 'rpc'])
def test_real_platform_matrix(tmp_path, openfmb_mode):
    proc = subprocess.run([sys.executable, str(RUN), '--openfmb', openfmb_mode, '--work', str(tmp_path / 'work')],
                          capture_output=True, text=True, timeout=3600)
    report = proc.stdout + proc.stderr
    assert proc.returncode == 0, report
    assert '24/24 passed' in proc.stdout, report
