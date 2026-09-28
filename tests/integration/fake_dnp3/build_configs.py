"""Build the configuration sets for the IEEE 1815.2 (DNP3) integration case from a MESA-DER profile.

Input (this directory):
  profile_mandatory_1547.json   the IEEE 1815.2 test tool's "mandatory for 1547" profile: the point set a
                                conformant outstation implements, the offline stand-in for an integrity poll

Outputs (this directory, overwritten), one sub-directory per scaling mode:
  transform_scaling/   the driver publishes raw counts; the transforms apply the profile multipliers
  driver_scaling/      the driver applies them (registry Transform / Scaling columns); the transforms do not

Each holds the fake and dnp3 driver registries, device configs for both interfaces, the presentation service
configuration (device format, transforms, canonical resource and sunspec / 2030.5 / 61850 aliases), the
discovery record and a vctl script. Run from the ``interoperability_service`` directory::

    PYTHONPATH=src python tests/integration/fake_dnp3/build_configs.py
"""
from __future__ import annotations

from pathlib import Path

from interoperability.discovery.dnp3 import discover_profile, write_case

HERE = Path(__file__).resolve().parent
DEVICE_FORMAT = 'fake_dnp3_der'
DEVICE_TOPIC = 'devices/site1/feeder1/der'
UAI = ['site1', 'der']


def main() -> None:
    device = discover_profile(HERE / 'profile_mandatory_1547.json')
    for scaling in ('transform', 'driver'):
        written = write_case(device, HERE / f'{scaling}_scaling', device_format=DEVICE_FORMAT, device_topic=DEVICE_TOPIC,
                             uai=UAI, scaling=scaling)
        print(f'{scaling} scaling: {len(written)} files under {written["presentation_config"].parent}')
    print(f'{device.profile_name}: {len(device.points)} points')
    for note in device.notes:
        print('note:', note)


if __name__ == '__main__':
    main()
