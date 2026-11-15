#!/usr/bin/env bash
# Store the IEEE 1815.2 device (profile_mandatory_1547) into a running platform. Pass "fake" (default) or "dnp3".
set -euo pipefail
cd "$(dirname "$0")"
DRIVER="${1:-fake}"
vctl config store platform.driver registry_configs/fake_dnp3_der.$DRIVER.csv fake_dnp3_der.$DRIVER.csv --csv
vctl config store platform.driver devices/site1/feeder1/der fake_dnp3_der.$DRIVER.device.json
vctl config store platform.presentation config presentation_config.json
