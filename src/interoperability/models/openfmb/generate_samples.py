"""Write example OpenFMB profile messages, in the JSON form adapters publish, for tests and documentation.

Run from the ``interoperability_service`` directory::

    PYTHONPATH=src python -m interoperability.models.openfmb.generate_samples [--out ../solar_json_output]
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from . import profile_builders as pb

HERE = Path(__file__).resolve().parent
DEFAULT_OUT = HERE.parents[4] / 'solar_json_output'
SAMPLE_TIME = 1_700_000_000


def example_profiles() -> dict[str, Any]:
    """Profile name -> message dict, for one PV inverter and one battery."""
    pv = dict(mrid='pv-1', name='Solar Inverter 1', seconds=SAMPLE_TIME)
    bess = dict(mrid='bess-1', name='Battery 1', seconds=SAMPLE_TIME)
    volts = {'phsA': 240.1, 'phsB': 239.8, 'phsC': 240.4}
    schedule = [
        pb.control_point(start_seconds=SAMPLE_TIME, mode='GridConnectModeKind_VSI_PQ',
                         volt_var_curve=pb.volt_var([(0.92, 0.44), (0.98, 0.0), (1.02, 0.0), (1.08, -0.44)], vref=1.0),
                         freq_watt_droop=pb.freq_watt(over_deadband_hz=0.036, over_slope=0.05, under_deadband_hz=0.036, under_slope=0.05),
                         watt_limit_max=0.8),
        pb.control_point(start_seconds=SAMPLE_TIME + 3600, mode='GridConnectModeKind_VSI_PQ',
                         power_factor=0.95, power_factor_excitation=True, watt_limit_max=1.0),
    ]
    profiles = {
        'SolarReadingProfile': pb.build_solar_reading_profile(**pv, w=12480.0, var=-310.0, hz=60.01,
                                                              phase_voltages=volts, phase_currents={'phsA': 17.3, 'phsB': 17.1, 'phsC': 17.4}),
        'SolarStatusProfile': pb.build_solar_status_profile(**pv, operating_state='OperatingStateKind_connected_and_generating',
                                                            grid_connection_state='GridConnectionStateKind_connected'),
        'SolarControlProfile': pb.build_solar_control_profile(**pv, schedule=schedule),
        'ESSReadingProfile': pb.build_ess_reading_profile(**bess, w=-25000.0, var=0.0, hz=60.01, phase_voltages=volts),
        'ESSStatusProfile': pb.build_ess_status_profile(**bess, soc=63.5, soh=98.0, wh_available=127000.0,
                                                        grid_mode='GridConnectModeKind_VSI_PQ', standby=False, battery_ok=True),
        'ESSControlProfile': pb.build_ess_control_profile(**bess, schedule=schedule),
        'ESSCapabilityProfile': pb.build_ess_capability_profile(**bess, vendor='ACME', model='BESS-200', w_max=100000.0,
                                                                va_max=110000.0, v_nom=480.0, wh_rating=200000.0,
                                                                w_charge_max=100000.0, w_discharge_max=100000.0),
    }
    return {name: profile.model_dump(mode='json', by_alias=True, exclude_none=True) for name, profile in profiles.items()}


def write_example_payloads(output_dir: str | Path = DEFAULT_OUT) -> dict[str, Path]:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    written = {}
    for name, message in example_profiles().items():
        path = output_dir / f'{name}.json'
        path.write_text(json.dumps(message, indent=2) + '\n')
        written[name] = path
    return written


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--out', type=Path, default=DEFAULT_OUT)
    args = parser.parse_args(argv)
    for name, path in write_example_payloads(args.out).items():
        print(f'{name:<24} {path}')


if __name__ == '__main__':
    main()
