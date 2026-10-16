"""Helpers shared by the tests that read the generated integration cases under ``tests/integration``.

A plain module beside the tests (pytest puts this directory on ``sys.path``): importing a sibling as
``tests.<module>`` resolves to an unrelated ``tests`` package installed in the environment.
"""
from __future__ import annotations

import csv
from pathlib import Path


def rows_of(path: Path) -> list[dict]:
    with Path(path).open(newline='') as f:
        return list(csv.DictReader(f))


def fake_driver_all_message(case: Path, mode: str, registry: str = 'fake_sunspec_pv.fake.csv') -> dict:
    """What the fake driver publishes on the device's ``all`` topic: the case registry's starting values."""
    def value(row):
        raw, kind = row['starting_value'], row['type']
        if kind == 'float':
            return float(raw)
        if kind == 'int':
            return int(raw)
        if kind in ('boolean', 'bool'):               # the fake driver's "boolean" type publishes Python bools
            return str(raw).strip().lower() in ('true', 't', '1', 'yes')
        return raw
    return {row['volttron_point_name']: value(row) for row in rows_of(Path(case) / f'{mode}_scaling' / registry)
            if row['starting_value'] != ''}
