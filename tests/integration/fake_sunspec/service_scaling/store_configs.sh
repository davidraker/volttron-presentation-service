#!/usr/bin/env bash
# Store the discovered SunSpec device (SunSpecTest Test-1547-1) into a running platform.
# Choose ONE driver interface: the fake one for simulation or the modbus one for the real device.
set -euo pipefail
cd "$(dirname "$0")"
DRIVER="${1:-fake}"
vctl config store platform.driver registry_configs/fake_sunspec_pv.$DRIVER.csv fake_sunspec_pv.$DRIVER.csv --csv
vctl config store platform.driver devices/site1/feeder1/pv_inverter fake_sunspec_pv.$DRIVER.device.json
vctl config store platform.presentation config presentation_config.json
