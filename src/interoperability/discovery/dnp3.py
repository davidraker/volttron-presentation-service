"""Build platform driver registries and service configuration for an IEEE 1815.2 (MESA-DER) outstation.

DNP3 has no self-description: an integrity poll says which indexes exist in each table, and the MESA-DER
profile says what they mean. This module takes the point set from a profile file (the JSON profiles of
the IEEE 1815.2 test tool, ``data/profiles/*.json``) or from any index listing, looks each point up in
the service's IEEE 1815.2 point registry, and writes:

* a registry for the ``dnp3`` platform driver interface (group, variation, index, scaling);
* a registry for the ``fake`` interface with the profile's values as starting values, for simulation;
* the device configs for both interfaces;
* the presentation service configuration (device format, transforms, mappings) through
  :mod:`interoperability.discovery.device_formats`.

Point names are ``<table>_<index>`` (``AI_297``). Scaling: the profile's multipliers are fixed, so either
the transforms apply them (``transform``) or the driver will, once it applies registry transforms with
their inverses (``driver``); in that mode the registry carries ``Transform`` entries (``scale(0.001)``) and
the same value in the driver's ``Scaling`` column. The current dnp3 driver applies neither.

    PYTHONPATH=src python -m interoperability.discovery.dnp3 --profile mandatory_1547.json --out build/
"""
from __future__ import annotations

import argparse
import csv
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .device_formats import (DNP3_GROUPS, SCALING_MODES, device_format_declaration, dnp3_device_transforms,
                             dnp3_point_definition, dnp3_scaling, resource_mappings)

#: Default DNP3 variation requested per table: doubles for analogs, with-flags for binaries and counters.
DEFAULT_VARIATIONS = {'AI': 6, 'AO': 4, 'BI': 2, 'BO': 2, 'CTR': 1}
TABLE_TYPES = {'AI': 'float', 'AO': 'float', 'BI': 'boolean', 'BO': 'boolean', 'CTR': 'int'}


@dataclass
class DiscoveredDnp3Point:
    name: str                # AI_297
    table: str
    index: int
    uid: str                 # IEC 61850 style identifier from the profile
    description: str
    units: str
    multiplier: float
    offset: float
    writable: bool
    value: Any               # profile value or default, raw (unscaled)
    mandatory: bool


@dataclass
class DiscoveredDnp3Device:
    points: list[DiscoveredDnp3Point]
    profile_name: str
    notes: list[str] = field(default_factory=list)

    @property
    def point_names(self) -> list[str]:
        return [p.name for p in self.points]

    def scaled_value(self, point: DiscoveredDnp3Point) -> Any:
        if isinstance(point.value, bool) or not isinstance(point.value, (int, float)):
            return point.value
        return round(point.value * point.multiplier + point.offset, 6)


def discover_indexes(indexes_by_table: dict[str, list[int]], values: dict[str, Any] | None = None,
                     profile_name: str = 'indexes') -> DiscoveredDnp3Device:
    """Describe a point set given as ``{'AI': [2, 3, ...], 'BI': [...]}``, e.g. the result of an integrity poll,
    using the IEEE 1815.2 point registry for meaning. Unknown indexes are reported and skipped."""
    values = values or {}
    points, notes = [], []
    for table, indexes in indexes_by_table.items():
        for index in sorted(set(indexes)):
            name = f'{table}_{index}'
            try:
                definition = dnp3_point_definition(name)
            except ValueError as e:
                notes.append(str(e))
                continue
            multiplier, offset = dnp3_scaling(name)
            value = values.get(name, definition.default)
            if table in ('BI', 'BO'):
                value = bool(value) if value is not None else False
            elif value is None:
                value = 0
            points.append(DiscoveredDnp3Point(
                name=name, table=table, index=index, uid=definition.uid, description=definition.name.split('.')[0].strip(),
                units=definition.units or '', multiplier=multiplier, offset=offset, writable=table in ('AO', 'BO'),
                value=value, mandatory=bool(definition.mandatory_1547 or definition.mandatory_1815)))
    return DiscoveredDnp3Device(points, profile_name, notes)


def discover_profile(path: str | Path) -> DiscoveredDnp3Device:
    """Point set of an IEEE 1815.2 test-tool profile file."""
    data = json.loads(Path(path).read_text())
    indexes: dict[str, list[int]] = {}
    values: dict[str, Any] = {}
    for table in DNP3_GROUPS:
        entries = data.get(table)
        if entries is None:
            continue
        rows = entries.get('points', []) if isinstance(entries, dict) else entries
        for row in rows:
            index = int(row['point_index'])
            indexes.setdefault(table, []).append(index)
            if row.get('value') is not None:
                values[f'{table}_{index}'] = row['value']
    return discover_indexes(indexes, values, Path(path).stem)


# ------------------------------------------------------------------------------------------- registries
def dnp3_registry_rows(device: DiscoveredDnp3Device, scaling: str, variations: dict[str, int] | None = None) -> list[dict]:
    variations = {**DEFAULT_VARIATIONS, **(variations or {})}
    rows = []
    for p in device.points:
        transform = ''
        if scaling == 'driver' and (p.multiplier != 1 or p.offset):
            transform = ', '.join(([f'scale({p.multiplier!r})'] if p.multiplier != 1 else []) + ([f'add({p.offset!r})'] if p.offset else []))
        rows.append({'Point Name': p.uid, 'Volttron Point Name': p.name, 'Group': DNP3_GROUPS[p.table],
                     'Variation': variations[p.table], 'Index': p.index,
                     'Scaling': p.multiplier if scaling == 'driver' else 1, 'Units': p.units,
                     'Writable': 'TRUE' if p.writable else 'FALSE', 'Transform': transform, 'Notes': p.description})
    return rows


def fake_registry_rows(device: DiscoveredDnp3Device, scaling: str) -> list[dict]:
    rows = []
    for p in device.points:
        value = p.value if scaling == 'transform' else device.scaled_value(p)
        kind = TABLE_TYPES[p.table]
        if kind == 'boolean':
            value = bool(value)
        elif kind == 'int' and isinstance(value, (int, float)):
            value = int(value)
        elif kind == 'float' and scaling == 'transform' and isinstance(value, (int, float)) and float(value).is_integer():
            value, kind = int(value), 'int'                 # raw DNP3 analogs are integers
        rows.append({'Point Name': p.uid, 'Volttron Point Name': p.name, 'Units': p.units, 'Units Details': p.description,
                     'Writable': 'TRUE' if p.writable else 'FALSE', 'Starting Value': value, 'Type': kind,
                     'Notes': f'DNP3 {p.table} {p.index}' + (f', multiplier {p.multiplier}' if p.multiplier != 1 else '')})
    return rows


def write_csv(path: Path, rows: list[dict]) -> None:
    with path.open('w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def device_config(driver: str, registry_name: str, *, interval: float = 5, outstation_ip: str = '127.0.0.1',
                  port: int = 20000, master_id: int = 2, outstation_id: int = 1) -> dict:
    remote: dict[str, Any] = {'driver_type': driver}
    if driver == 'dnp3':
        remote.update({'master_ip': '0.0.0.0', 'outstation_ip': outstation_ip, 'port': port,
                       'master_id': master_id, 'outstation_id': outstation_id})
    return {'driver_type': driver, 'remote_config': remote, 'registry_config': f'config://{registry_name}',
            'interval': interval, 'publish_depth_first_all': True, 'timezone': 'UTC'}


def write_case(device: DiscoveredDnp3Device, out: Path, *, device_format: str, device_topic: str, uai: list[str],
               scaling: str, outstation_ip: str = '127.0.0.1', port: int = 20000, master_id: int = 2,
               outstation_id: int = 1, alias_formats: dict[str, str] | None = None) -> dict[str, Path]:
    out.mkdir(parents=True, exist_ok=True)
    alias_formats = alias_formats or {'der_sunspec': 'sunspec', 'der_2030_5': '2030.5', 'der_61850': '61850'}
    stem = device_format
    written: dict[str, Path] = {}
    written['fake_registry'] = out / f'{stem}.fake.csv'
    write_csv(written['fake_registry'], fake_registry_rows(device, scaling))
    written['dnp3_registry'] = out / f'{stem}.dnp3.csv'
    write_csv(written['dnp3_registry'], dnp3_registry_rows(device, scaling))
    written['fake_device'] = out / f'{stem}.fake.device.json'
    written['fake_device'].write_text(json.dumps(device_config('fake', f'registry_configs/{stem}.fake.csv'), indent=2) + '\n')
    written['dnp3_device'] = out / f'{stem}.dnp3.device.json'
    written['dnp3_device'].write_text(json.dumps(device_config(
        'dnp3', f'registry_configs/{stem}.dnp3.csv', outstation_ip=outstation_ip, port=port, master_id=master_id,
        outstation_id=outstation_id), indent=2) + '\n')
    built = dnp3_device_transforms(device_format, device.point_names, scaling=scaling)
    config = {'formats': {device_format: device_format_declaration(device.point_names, scaling)},
              'transforms': built.definitions,
              'mappings': resource_mappings(device_format, device_topic, uai, alias_formats)}
    written['presentation_config'] = out / 'presentation_config.json'
    written['presentation_config'].write_text(json.dumps(config, indent=2) + '\n')
    written['discovery'] = out / 'discovery.json'
    written['discovery'].write_text(json.dumps({'profile': device.profile_name, 'scaling': scaling,
                                                'points': [vars(p) for p in device.points],
                                                'notes': device.notes + built.notes}, indent=2, default=str) + '\n')
    written['store_script'] = out / 'store_configs.sh'
    written['store_script'].write_text(f'''#!/usr/bin/env bash
# Store the IEEE 1815.2 device ({device.profile_name}) into a running platform. Pass "fake" (default) or "dnp3".
set -euo pipefail
cd "$(dirname "$0")"
DRIVER="${{1:-fake}}"
vctl config store platform.driver registry_configs/{stem}.$DRIVER.csv {stem}.$DRIVER.csv --csv
vctl config store platform.driver {device_topic} {stem}.$DRIVER.device.json
vctl config store platform.presentation config presentation_config.json
''')
    return written


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--profile', type=Path, required=True, help='IEEE 1815.2 test-tool profile JSON')
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--scaling', choices=SCALING_MODES, default='transform')
    parser.add_argument('--format-name', default='dnp3_device')
    parser.add_argument('--device-topic', default='devices/site1/feeder1/der')
    parser.add_argument('--uai', default='site1/der')
    parser.add_argument('--outstation-ip', default='127.0.0.1')
    parser.add_argument('--port', type=int, default=20000)
    args = parser.parse_args(argv)
    device = discover_profile(args.profile)
    written = write_case(device, args.out, device_format=args.format_name, device_topic=args.device_topic,
                         uai=args.uai.split('/'), scaling=args.scaling, outstation_ip=args.outstation_ip, port=args.port)
    print(f'{device.profile_name}: {len(device.points)} points, scaling by {args.scaling}')
    for name, path in written.items():
        print(f'  {name:<20} {path}')
    for note in device.notes:
        print(f'  note: {note}')


if __name__ == '__main__':
    main()
