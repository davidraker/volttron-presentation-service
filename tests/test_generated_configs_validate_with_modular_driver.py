"""The generated device configs and registries must validate with the modular volttron-platform-driver.

That package (and its interface libraries) is the platform driver this framework targets. It is not a
dependency of the service, so this test looks for a checkout, by default
``/home/dmr/Projects/volttron/modular/drivers`` or the ``VOLTTRON_MODULAR_DRIVERS`` environment variable,
and skips when none is present.
"""
from __future__ import annotations

import csv
import importlib
import json
import os
import sys
from pathlib import Path

import pytest

CASES = Path(__file__).parent / 'integration'
DRIVERS = Path(os.environ.get('VOLTTRON_MODULAR_DRIVERS', '/home/dmr/Projects/volttron/modular/drivers'))
if not DRIVERS.is_dir():
    pytest.skip('modular volttron-platform-driver checkout not found', allow_module_level=True)
for sub in ('base-driver/src', 'interfaces/fake/src', 'interfaces/pymodbus/src'):
    path = str(DRIVERS / sub)
    if path not in sys.path:
        sys.path.append(path)
base = pytest.importorskip('volttron.driver.base.config')


def _classes(driver: str):
    if driver == 'fake':
        fake = importlib.import_module('volttron.driver.interfaces.fake.fake')
        return fake.FakePointConfig, fake.FakeRemoteConfig
    if driver == 'modbus':
        modbus = importlib.import_module('volttron.driver.interfaces.modbus.config')
        return modbus.ModbusPointConfig, modbus.ModbusRemoteConfig
    return base.PointConfig, base.RemoteConfig      # the dnp3 interface reads plain dict rows


@pytest.mark.parametrize('case, stem, driver', [
    ('fake_sunspec', 'fake_sunspec_pv', 'fake'), ('fake_sunspec', 'fake_sunspec_pv', 'modbus'),
    ('fake_dnp3', 'fake_dnp3_der', 'fake'), ('fake_dnp3', 'fake_dnp3_der', 'dnp3')])
@pytest.mark.parametrize('mode', ['transform', 'driver'])
def test_generated_configs_validate(case, stem, driver, mode):
    out = CASES / case / f'{mode}_scaling'
    point_cls, remote_cls = _classes(driver)
    device = json.loads((out / f'{stem}.{driver}.device.json').read_text())
    remote = device.pop('remote_config')
    device.pop('driver_type')
    remote_cls(**remote)                                              # the interface's connection settings
    with (out / f'{stem}.{driver}.csv').open() as f:
        rows = list(csv.DictReader(f))
    assert rows
    for row in rows:
        point_cls(**row)                                              # every registry row as the driver parses it
    device['registry_config'] = rows                                  # what the config store inlines for config://
    base.DeviceConfig(**device)
