"""Build platform driver registries and service configuration from SunSpec discovery.

pysunspec2 scans a SunSpec device (Modbus TCP or RTU, or a JSON device description for offline work)
and reports every model instance, group and point with its address, type, access, units and scale
factor. From that this module writes:

* a registry for the ``modbus`` platform driver interface, with absolute addresses and register types;
* a registry for the ``fake`` interface with the discovered values as starting values, for simulation;
* the device configs for both interfaces;
* the presentation service configuration (device format, transforms, mappings) through
  :mod:`interoperability.discovery.device_formats`.

Point names follow the ``device_formats`` convention (``705_Crv1_Pt1_V``). Only the first instance of a
repeated model is used; further instances are reported. Requires the ``discovery`` extra (pysunspec2)::

    PYTHONPATH=src python -m interoperability.discovery.sunspec --file device.json --out build/
    PYTHONPATH=src python -m interoperability.discovery.sunspec --host 10.0.0.21 --unit 1 --scaling driver --out build/
"""
from __future__ import annotations

import argparse
import csv
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .device_formats import SCALING_MODES, device_format_declaration, resource_mappings, sunspec_device_transforms

# SunSpec point type -> data type name of the modbus platform driver interface (pymodbus names).
REGISTER_TYPES = {
    'int16': 'INT16', 'uint16': 'UINT16', 'count': 'UINT16', 'enum16': 'UINT16', 'bitfield16': 'UINT16',
    'sunssf': 'INT16', 'int32': 'INT32', 'uint32': 'UINT32', 'acc32': 'UINT32', 'enum32': 'UINT32',
    'bitfield32': 'UINT32', 'ipaddr': 'UINT32', 'int64': 'INT64', 'uint64': 'UINT64', 'acc64': 'UINT64',
    'bitfield64': 'UINT64', 'float32': 'FLOAT32', 'float64': 'FLOAT64',
}
FLOAT_TYPES = {'float32', 'float64'}


@dataclass
class DiscoveredPoint:
    name: str                      # registry point name, e.g. 705_Crv1_Pt1_V
    model_id: int
    address: int                   # zero-based protocol address of the first register
    size: int                      # registers
    type: str                      # SunSpec type
    writable: bool
    units: str
    description: str
    value: Any
    scale_factor: str | int | None  # registry name of the SF point, a fixed exponent, or None
    mandatory: bool

    @property
    def is_scale_factor(self) -> bool:
        return self.type == 'sunssf'

    @property
    def is_string(self) -> bool:
        return self.type in ('string', 'eui48', 'ipv6addr')


@dataclass
class DiscoveredDevice:
    points: list[DiscoveredPoint]
    scale_factors: dict[str, int]          # SF point name -> discovered value
    identity: dict[str, Any]               # Mn, Md, SN, Vr from model 1
    notes: list[str] = field(default_factory=list)

    @property
    def point_names(self) -> list[str]:
        return [p.name for p in self.points]

    def scaled_value(self, point: DiscoveredPoint) -> Any:
        """The point's value with its scale factor applied, as a driver that scales would publish it."""
        if not isinstance(point.value, (int, float)) or isinstance(point.value, bool) or point.is_scale_factor:
            return point.value
        sf = point.scale_factor
        exponent = sf if isinstance(sf, int) else self.scale_factors.get(sf) if sf else None
        if exponent is None:
            return point.value
        return round(point.value * 10.0 ** exponent, max(0, -exponent))


# ------------------------------------------------------------------------------------------- discovery
def _walk(group, prefix: str, model_id: int, model_addr: int, points: list[DiscoveredPoint], sf_names: dict):
    """Collect the points of a pysunspec2 group and its subgroups, naming them by the convention."""
    for name, point in group.points.items():
        pdef = point.pdef
        if name in ('ID', 'L') or pdef['type'] == 'pad':
            continue
        full = f'{prefix}_{name}'
        sf = pdef.get('sf')
        points.append(DiscoveredPoint(
            name=full, model_id=model_id, address=model_addr + point.offset, size=pdef.get('size', point.len),
            type=pdef['type'], writable=pdef.get('access') == 'RW', units=pdef.get('units', '') or '',
            description=(pdef.get('label') or pdef.get('desc') or '').strip(), value=point.value,
            scale_factor=sf if isinstance(sf, int) or sf is None else sf, mandatory=pdef.get('mandatory') == 'M'))
        if pdef['type'] == 'sunssf':
            sf_names.setdefault(name, []).append(full)
    for gname, sub in group.groups.items():
        instances = sub if isinstance(sub, list) else [sub]
        for i, instance in enumerate(instances):
            label = f'{prefix}_{gname}{i + 1}' if isinstance(sub, list) else f'{prefix}_{gname}'
            _walk(instance, label, model_id, model_addr, points, sf_names)


def discover(device) -> DiscoveredDevice:
    """Walk a scanned pysunspec2 device (``device.scan()`` already called)."""
    from .device_formats import sunspec_scale_factor
    points: list[DiscoveredPoint] = []
    notes: list[str] = []
    identity: dict[str, Any] = {}
    for model_id, instances in device.models.items():
        if not isinstance(model_id, int):
            continue
        if len(instances) > 1:
            notes.append(f'model {model_id} occurs {len(instances)} times; only the first instance is used')
        model = instances[0]
        if model_id == 1:
            identity = {k: model.points[k].value for k in ('Mn', 'Md', 'SN', 'Vr') if k in model.points}
        _walk(model, str(model_id), model_id, model.model_addr, points, {})
    # Resolve each point's scale factor to the registry name of the SF point, via the model classes.
    for point in points:
        if isinstance(point.scale_factor, str):
            try:
                point.scale_factor = sunspec_scale_factor(point.name)
            except ValueError as e:
                notes.append(str(e))
                point.scale_factor = None
    scale_factors = {p.name: int(p.value) for p in points if p.is_scale_factor and isinstance(p.value, int)}
    return DiscoveredDevice(points, scale_factors, identity, notes)


def discover_file(path: str | Path) -> DiscoveredDevice:
    """Offline discovery from a pysunspec2 JSON device description."""
    import sunspec2.file.client as client
    device = client.FileClientDevice(str(path))
    device.scan()
    return discover(device)


def discover_tcp(host: str, port: int = 502, unit: int = 1, timeout: float = 5.0) -> DiscoveredDevice:
    import sunspec2.modbus.client as client
    device = client.SunSpecModbusClientDeviceTCP(slave_id=unit, ipaddr=host, ipport=port, timeout=timeout)
    device.scan()
    try:
        return discover(device)
    finally:
        device.close()


def discover_rtu(port: str, unit: int = 1, baudrate: int = 9600, parity: str = 'N', timeout: float = 5.0) -> DiscoveredDevice:
    import sunspec2.modbus.client as client
    device = client.SunSpecModbusClientDeviceRTU(slave_id=unit, name=port, baudrate=baudrate, parity=parity, timeout=timeout)
    device.scan()
    try:
        return discover(device)
    finally:
        device.close()


# ------------------------------------------------------------------------------------------- registries
def _included(device: DiscoveredDevice, scaling: str):
    return [p for p in device.points if not (scaling == 'driver' and p.is_scale_factor)]


def modbus_registry_rows(device: DiscoveredDevice, scaling: str) -> list[dict]:
    """Rows for the ``modbus`` interface. In ``driver`` mode each scaled point carries a ``Transform`` entry."""
    rows = []
    for p in _included(device, scaling):
        if p.is_string:
            data_type = f'string[{p.size * 2}]'
        else:
            data_type = REGISTER_TYPES.get(p.type)
            if data_type is None:
                device.notes.append(f'{p.name}: SunSpec type {p.type} has no register type mapping; skipped')
                continue
        transform = ''
        if scaling == 'driver' and p.scale_factor is not None and not p.is_scale_factor:
            transform = f'scale({10.0 ** p.scale_factor!r})' if isinstance(p.scale_factor, int) else f'scale_reg_pow_10({p.scale_factor})'
        rows.append({'Volttron Point Name': p.name, 'Point Address': p.address, 'Data Type': data_type, 'Table': 'holding',
                     'Writable': 'TRUE' if p.writable else 'FALSE', 'Units': p.units, 'Transform': transform,
                     'Register Name': p.name, 'Default Value': '' if p.value is None else p.value,
                     'Description': p.description})
    return rows


def fake_registry_rows(device: DiscoveredDevice, scaling: str) -> list[dict]:
    """Rows for the ``fake`` interface: starting values are raw registers (``transform`` scaling) or the
    values a scaling driver would publish (``driver`` scaling)."""
    rows = []
    for p in _included(device, scaling):
        value = p.value if scaling == 'transform' else device.scaled_value(p)
        if p.is_string:
            kind = 'str'
        elif isinstance(value, float) or p.type in FLOAT_TYPES:
            kind = 'float'
        else:
            kind = 'int'
        rows.append({'Point Name': p.name, 'Volttron Point Name': p.name, 'Units': p.units, 'Units Details': p.description,
                     'Writable': 'TRUE' if p.writable else 'FALSE', 'Starting Value': '' if value is None else value,
                     'Type': kind, 'Notes': f'SunSpec {p.type} at {p.address}' + (f', scale factor {p.scale_factor}' if p.scale_factor is not None else '')})
    return rows


def write_csv(path: Path, rows: list[dict]) -> None:
    with path.open('w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def device_config(driver: str, registry_name: str, *, interval: float = 5, host: str | None = None, port: int = 502,
                  unit: int = 1) -> dict:
    remote: dict[str, Any] = {'driver_type': driver}
    if driver == 'modbus':
        # pysunspec2 addresses are zero-based protocol addresses, which is the driver's 'offset' addressing.
        remote.update({'device_address': host or '127.0.0.1', 'port': port, 'unit_id': unit, 'addressing': 'offset',
                       'word_order': 'big'})
    return {'driver_type': driver, 'remote_config': remote, 'registry_config': f'config://{registry_name}',
            'interval': interval, 'publish_depth_first_all': True, 'timezone': 'UTC'}


def presentation_config(device: DiscoveredDevice, device_format: str, device_topic: str, uai: list[str],
                        scaling: str, alias_formats: dict[str, str | dict]) -> tuple[dict, list[str]]:
    """Service configuration: format, transforms, the canonical resource and one alias per requested format
    (see :func:`~interoperability.discovery.device_formats.resource_mappings` for the alias specs)."""
    names = [p.name for p in _included(device, scaling)]
    built = sunspec_device_transforms(device_format, names, scaling=scaling, scale_factors=device.scale_factors)
    return ({'formats': {device_format: device_format_declaration(names, scaling)},
             'transforms': built.definitions,
             'mappings': resource_mappings(device_format, device_topic, uai, alias_formats)}, built.notes)


def write_case(device: DiscoveredDevice, out: Path, *, device_format: str, device_topic: str, uai: list[str],
               scaling: str, host: str | None = None, port: int = 502, unit: int = 1,
               alias_formats: dict[str, str] | None = None) -> dict[str, Path]:
    """Write registries, device configs, the presentation config and a vctl script for one scaling mode."""
    out.mkdir(parents=True, exist_ok=True)
    alias_formats = alias_formats or {'pv_sunspec': 'sunspec', 'pv_2030_5': '2030.5', 'pv_dnp3': '1815.2.inputs'}
    stem = device_format
    written = {}
    fake_name, modbus_name = f'registry_configs/{stem}.fake.csv', f'registry_configs/{stem}.modbus.csv'
    written['fake_registry'] = out / f'{stem}.fake.csv'
    write_csv(written['fake_registry'], fake_registry_rows(device, scaling))
    written['modbus_registry'] = out / f'{stem}.modbus.csv'
    write_csv(written['modbus_registry'], modbus_registry_rows(device, scaling))
    written['fake_device'] = out / f'{stem}.fake.device.json'
    written['fake_device'].write_text(json.dumps(device_config('fake', fake_name), indent=2) + '\n')
    written['modbus_device'] = out / f'{stem}.modbus.device.json'
    written['modbus_device'].write_text(json.dumps(device_config('modbus', modbus_name, host=host, port=port, unit=unit), indent=2) + '\n')
    config, notes = presentation_config(device, device_format, device_topic, uai, scaling, alias_formats)
    written['presentation_config'] = out / 'presentation_config.json'
    written['presentation_config'].write_text(json.dumps(config, indent=2) + '\n')
    written['discovery'] = out / 'discovery.json'
    written['discovery'].write_text(json.dumps({
        'identity': device.identity, 'scaling': scaling, 'scale_factors': device.scale_factors,
        'points': [vars(p) for p in device.points], 'notes': device.notes + notes}, indent=2, default=str) + '\n')
    written['store_script'] = out / 'store_configs.sh'
    written['store_script'].write_text(f'''#!/usr/bin/env bash
# Store the discovered SunSpec device ({device.identity.get('Mn', '?')} {device.identity.get('Md', '?')}) into a running platform.
# Choose ONE driver interface: the fake one for simulation or the modbus one for the real device.
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
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument('--file', type=Path, help='pysunspec2 JSON device description (offline)')
    source.add_argument('--host', help='Modbus TCP host of the device')
    source.add_argument('--serial', help='serial port of a Modbus RTU device')
    parser.add_argument('--port', type=int, default=502)
    parser.add_argument('--unit', type=int, default=1, help='Modbus unit (slave) id')
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--scaling', choices=SCALING_MODES, default='transform')
    parser.add_argument('--format-name', default='sunspec_device')
    parser.add_argument('--device-topic', default='devices/site1/feeder1/inverter')
    parser.add_argument('--uai', default='site1/inverter', help='UAI of the canonical resource, "/"-separated')
    args = parser.parse_args(argv)
    if args.file:
        device = discover_file(args.file)
    elif args.host:
        device = discover_tcp(args.host, args.port, args.unit)
    else:
        device = discover_rtu(args.serial, args.unit)
    written = write_case(device, args.out, device_format=args.format_name, device_topic=args.device_topic,
                         uai=args.uai.split('/'), scaling=args.scaling, host=args.host, port=args.port, unit=args.unit)
    print(f"{device.identity.get('Mn', '?')} {device.identity.get('Md', '?')}: {len(device.points)} points, "
          f"{len(device.scale_factors)} scale factors, scaling by {args.scaling}")
    for name, path in written.items():
        print(f'  {name:<20} {path}')
    for note in device.notes:
        print(f'  note: {note}')


if __name__ == '__main__':
    main()
