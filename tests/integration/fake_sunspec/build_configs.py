"""Build the configuration sets for the SunSpec inverter integration case from SunSpec discovery.

Input (this directory):
  device_1547.json     pysunspec2 JSON description of a SunSpec 1547 device (models 1, 701-713), the offline
                       stand-in for scanning a real inverter over Modbus

Outputs (this directory, overwritten), one sub-directory per scaling mode:
  transform_scaling/   the driver publishes raw registers and scale factors; the transforms scale
  driver_scaling/      the driver applies scale factors (registry Transform column); the transforms do not

Each holds the fake and modbus driver registries, the device configs for both interfaces, the presentation
service configuration (device format, transforms, canonical resource and sunspec / 2030.5 / 1815.2 aliases),
the discovery record and a vctl script. Run from the ``interoperability_service`` directory::

    PYTHONPATH=src python tests/integration/fake_sunspec/build_configs.py
"""
from __future__ import annotations

from pathlib import Path

from interoperability.discovery.sunspec import discover_file, write_case

HERE = Path(__file__).resolve().parent
DEVICE_FORMAT = 'fake_sunspec_pv'
DEVICE_TOPIC = 'devices/site1/feeder1/pv_inverter'
UAI = ['site1', 'pv_inverter']
#: The device's OpenFMB identity, carried in the profile headers the OpenFMB alias publishes.
OPENFMB_MRID = '7d1a2b3c-0000-4000-8000-000000000001'
ALIASES = {
    'pv_sunspec': 'sunspec', 'pv_2030_5': '2030.5', 'pv_dnp3': '1815.2.inputs',
    # One OpenFMB profile, protobuf on the wire, under the topic an OpenFMB adapter would subscribe to.
    'pv_openfmb': {'format': 'openfmb.solar.reading', 'encoding': 'protobuf',
                   'parameters': {'mrid': OPENFMB_MRID, 'name': 'PV inverter 1'},
                   'uai': ['openfmb', 'solarmodule', 'SolarReadingProfile', OPENFMB_MRID]},
}


def main() -> None:
    device = discover_file(HERE / 'device_1547.json')
    for scaling in ('transform', 'driver'):
        written = write_case(device, HERE / f'{scaling}_scaling', device_format=DEVICE_FORMAT, device_topic=DEVICE_TOPIC,
                             uai=UAI, scaling=scaling, alias_formats=ALIASES)
        print(f'{scaling} scaling: {len(written)} files under {written["presentation_config"].parent}')
    print(f"{device.identity}: {len(device.points)} points, scale factors {device.scale_factors}")
    for note in device.notes:
        print('note:', note)


if __name__ == '__main__':
    main()
