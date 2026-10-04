"""Generate the IEEE 2030.5 driver's registry, device configuration and device format for a mirrored device.

The ``ieee2030_5`` platform driver interface is a 2030.5 *client*: the remote it talks to is a utility or aggregator
server, its writable points are what the client reports upward (DERStatus, DERSettings, DERCapability,
DERAvailability, DeviceInformation, MirrorMeterReading) and its read-only points are the controls it receives
(DERControl, DefaultDERControl, DERCurve, DERControlList, DERProgram). For a physical device whose format reaches
``2030.5`` in the transform graph, the composed field maps of the two chains say exactly which 2030.5 attributes the
device can fill and which controls it can take, so the mirror's registry can be generated instead of written by hand.

The mirror is a device of its own in the platform: its point names are the convention paths joined with
underscores (``DERSettings_setMaxW``, ``MirrorMeterReading_V_PhaseA``, ``DERCurve_opModVoltVar_CurveData``), and its
device format converts to and from ``2030.5`` with plain copies, so a message from the mirror is already in the
service's ``2030.5`` convention and a ``2030.5`` message written to it becomes flat points for the driver.

    PYTHONPATH=src python -m interoperability.discovery.ieee2030_5 --config presentation_config.json \\
        --device-format fake_sunspec_pv --out build/
"""
from __future__ import annotations

import argparse
import csv
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..transform_registry import TransformRegistry
from .device_formats import DEVICE_STAGE_INPUT, DeviceTransforms, device_format_declaration, resource_mappings

UPWARD_RESOURCES = ('DERCapability', 'DERSettings', 'DERStatus', 'DERAvailability', 'DeviceInformation', 'MirrorMeterReading')
DOWNWARD_RESOURCES = ('DERControl', 'DefaultDERControl', 'DERCurve', 'DERControlList', 'DERProgram')
#: Attributes carried as one list-valued point: the path is cut at the list.
LIST_ATTRIBUTES = {'CurveData', 'DERControlList'}
COLUMNS = ['Volttron Point Name', 'Path', 'Writable', 'Multiplier', 'Scaling', 'Units', 'Starting Value', 'Notes']
#: Schema-required attributes of the upward resources that the device may not supply; given starting values so the
#: first PUT is complete (the proxy would otherwise send zeros with a warning).
REQUIRED_STARTING_VALUES = {('DERCapability', 'type'): 83, ('DERCapability', 'rtgMaxW'): 0, ('DERCapability', 'modesSupported'): '0',
                            ('DERSettings', 'setGradW'): 100, ('DERSettings', 'setMaxW'): 0}
UNIT_SUFFIXES = (('Wh', 'Wh'), ('VarNeg', 'var'), ('Var', 'var'), ('VA', 'VA'), ('W', 'W'), ('V', 'V'), ('A', 'A'), ('Hz', 'Hz'),
                 ('PF', 'PF'), ('Tms', 'ms'))


@dataclass
class MirrorPoint:
    path: tuple[str, ...]
    writable: bool
    via: str
    fidelity: float = 1.0

    @property
    def name(self) -> str:
        return '_'.join(self.path)

    @property
    def dotted(self) -> str:
        return '.'.join(self.path)

    @property
    def resource(self) -> str:
        return self.path[0]


@dataclass
class DiscoveredMirror:
    device_format: str
    points: list[MirrorPoint]
    notes: list[str] = field(default_factory=list)

    @property
    def point_names(self) -> list[str]:
        return [p.name for p in self.points]

    def upward(self) -> list[MirrorPoint]:
        return [p for p in self.points if p.writable]

    def downward(self) -> list[MirrorPoint]:
        return [p for p in self.points if not p.writable]


def _cut_at_list(path: tuple) -> tuple[str, ...] | None:
    """``DERCurve.opModVoltVar.CurveData.*.xvalue`` -> ``DERCurve.opModVoltVar.CurveData``; None when a wildcard
    sits where no list attribute is known."""
    for i, segment in enumerate(path):
        if segment in LIST_ATTRIBUTES:
            return tuple(path[:i + 1])
    if '*' in path:
        return None
    return tuple(path)


def discover_mirror(registry: TransformRegistry, device_format: str, *, schedules: bool = True) -> DiscoveredMirror:
    """The 2030.5 attributes a device can report and the controls it can take, from the transform graph."""
    points: dict[tuple, MirrorPoint] = {}
    notes: list[str] = []

    def add(path, writable, via, fidelity):
        cut = _cut_at_list(path)
        if cut is None:
            notes.append(f'{".".join(path)}: list data without a known list attribute is not expressible as a point')
            return
        if cut[0] not in UPWARD_RESOURCES + DOWNWARD_RESOURCES:
            notes.append(f'{".".join(cut)}: {cut[0]} is not a resource the 2030.5 driver handles')
            return
        if (cut[0] in UPWARD_RESOURCES) != writable:
            # The device publishes its own control settings (reads of DERControl) and takes settings writes
            # (writes into DERSettings); in the client those directions are the server's, not the device's.
            return
        if cut not in points:
            points[cut] = MirrorPoint(cut, writable, via, fidelity)

    try:
        chain, _, path = registry.lookup_scored(device_format, '2030.5')
        for mapping in registry._chain_map(path).mappings:
            if mapping.fidelity > 0 and mapping.target:
                add(mapping.target, True, ' > '.join(path[1:]), mapping.fidelity)
    except Exception as e:                                  # TransformNotFoundError: the device reaches no 2030.5
        notes.append(f'{device_format} -> 2030.5: {e}')
    try:
        chain, _, path = registry.lookup_scored('2030.5', device_format)
        for mapping in registry._chain_map(path).mappings:
            if mapping.fidelity > 0 and mapping.source:
                add(mapping.source, False, ' > '.join(path[:-1]), mapping.fidelity)
    except Exception as e:
        notes.append(f'2030.5 -> {device_format}: {e}')
    if schedules and ('DERControlList',) not in points:
        points[('DERControlList',)] = MirrorPoint(('DERControlList',), False, 'schedules of the server programs')
    ordered = sorted(points.values(), key=lambda p: (not p.writable, p.path))
    return DiscoveredMirror(device_format, ordered, sorted(set(notes)))


# ------------------------------------------------------------------------------------------- outputs
def _units(point: MirrorPoint) -> str:
    if point.resource == 'MirrorMeterReading' and len(point.path) > 1:
        return point.path[1]
    leaf = point.path[-1]
    if leaf in LIST_ATTRIBUTES or leaf in ('displacement', 'excitation'):
        return ''
    if leaf in ('setGradW', 'setSoftGradW'):
        return '% x100/s'
    if 'Lim' in leaf or leaf.endswith('Pct') or leaf.startswith('opModFixedW'):
        return '% x100'
    for suffix, unit in UNIT_SUFFIXES:
        if leaf.endswith(suffix):
            return unit
    return ''


def registry_rows(mirror: DiscoveredMirror) -> list[dict]:
    rows = []
    for p in mirror.points:
        starting = REQUIRED_STARTING_VALUES.get(p.path, '') if p.writable else ''
        rows.append({'Volttron Point Name': p.name, 'Path': p.dotted, 'Writable': 'TRUE' if p.writable else 'FALSE',
                     'Multiplier': 0 if p.writable and p.path[0] != 'MirrorMeterReading' else '', 'Scaling': 1,
                     'Units': _units(p), 'Starting Value': starting,
                     'Notes': f'via {p.via}' + ('' if p.fidelity == 1 else f', fidelity {p.fidelity:.2f}')})
    for path, value in REQUIRED_STARTING_VALUES.items():
        if not any(p.path == path for p in mirror.points):
            rows.append({'Volttron Point Name': '_'.join(path), 'Path': '.'.join(path), 'Writable': 'TRUE', 'Multiplier': 0,
                         'Scaling': 1, 'Units': _units(MirrorPoint(path, True, '')), 'Starting Value': value,
                         'Notes': 'required by the schema; not supplied by the device'})
    return rows


def write_csv(path: Path, rows: list[dict]) -> None:
    with Path(path).open('w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def device_config(registry_name: str, *, server_url: str = 'https://127.0.0.1:8443', cert_path: str = '/etc/volttron/sep2/device.pem',
                  key_path: str = '/etc/volttron/sep2/device.key', ca_path: str | None = '/etc/volttron/sep2/ca.pem',
                  pin: int | None = None, notify_host: str | None = None, notify_port: int = 8444, interval: float = 60,
                  **extra) -> dict:
    remote: dict[str, Any] = {'driver_type': 'ieee2030_5', 'server_url': server_url, 'cert_path': cert_path,
                              'key_path': key_path, 'ca_path': ca_path, 'subscribe': notify_host is not None}
    if pin is not None:
        remote['pin'] = pin
    if notify_host is not None:
        remote.update(notify_host=notify_host, notify_port=notify_port)
    remote.update(extra)
    return {'driver_type': 'ieee2030_5', 'remote_config': remote, 'registry_config': f'config://{registry_name}',
            'interval': interval, 'publish_depth_first_all': True, 'timezone': 'UTC'}


def mirror_transforms(mirror_format: str, mirror: DiscoveredMirror, *, served: bool = False) -> DeviceTransforms:
    """Plain copies between the mirror's flat points and ``2030.5``: every point when reading the mirror, only the
    upward (writable) points when writing to it. A ``served`` mirror is a 2030.5 server the platform itself serves
    (the ieee2030_5 driver's server role): the platform writes the downward points too, so every point is written."""
    to_protocol: dict = {}
    rows = registry_rows(mirror)
    for row in rows:
        path = tuple(row['Path'].split('.'))
        node = to_protocol
        for segment in path[:-1]:
            node = node.setdefault(segment, {})
        node[path[-1]] = f'transform[{row["Volttron Point Name"]}]()'
    from_protocol = {row['Volttron Point Name']: f'transform[{", ".join(row["Path"].split("."))}]()'
                     for row in rows if served or row['Writable'] == 'TRUE'}
    return DeviceTransforms([{'input_format': mirror_format, 'output_format': '2030.5', 'pattern': {**DEVICE_STAGE_INPUT, **to_protocol}},
                             {'input_format': '2030.5', 'output_format': mirror_format, 'pattern': from_protocol}],
                            'driver', list(mirror.notes))


def presentation_fragment(mirror_format: str, mirror: DiscoveredMirror, device_topic: str, uai: list[str],
                          alias: str = 'sep2', *, served: bool = False) -> dict:
    """``formats``, ``transforms`` and ``mappings`` entries for the mirror, to merge into the service configuration."""
    rows = registry_rows(mirror)
    names = [row['Volttron Point Name'] for row in rows]
    built = mirror_transforms(mirror_format, mirror, served=served)
    return {'formats': {mirror_format: device_format_declaration(names, 'driver')},
            'transforms': built.definitions,
            'mappings': resource_mappings(mirror_format, device_topic, uai, {alias: '2030.5'})}


def write_case(registry: TransformRegistry, device_format: str, out: Path, *, mirror_format: str, device_topic: str,
               uai: list[str], alias: str = 'sep2', served: bool = False, **server) -> dict[str, Path]:
    """Write the mirror's registry, device config, presentation fragment and discovery record. A ``served`` mirror is a
    2030.5 server the platform itself serves (the ieee2030_5 driver's server role), whose downward points the platform writes."""
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    mirror = discover_mirror(registry, device_format)
    rows = registry_rows(mirror)
    written: dict[str, Path] = {}
    written['registry'] = out / f'{mirror_format}.ieee2030_5.csv'
    write_csv(written['registry'], rows)
    written['device'] = out / f'{mirror_format}.ieee2030_5.device.json'
    written['device'].write_text(json.dumps(device_config(f'registry_configs/{mirror_format}.ieee2030_5.csv', **server), indent=2) + '\n')
    written['presentation'] = out / f'{mirror_format}.presentation.json'
    written['presentation'].write_text(json.dumps(presentation_fragment(mirror_format, mirror, device_topic, uai, alias, served=served), indent=2) + '\n')
    written['discovery'] = out / f'{mirror_format}.discovery.json'
    written['discovery'].write_text(json.dumps({'device_format': device_format, 'mirror_format': mirror_format,
                                                'points': [{'name': p.name, 'path': p.dotted, 'writable': p.writable,
                                                            'via': p.via, 'fidelity': p.fidelity} for p in mirror.points],
                                                'notes': mirror.notes}, indent=2) + '\n')
    return written


def load_registry(config_path: Path) -> TransformRegistry:
    from importlib import resources
    config = json.loads(Path(config_path).read_text())
    registry = TransformRegistry()
    for name, spec in config.get('formats', {}).items():
        registry.declare_format(name, **spec)
    bundled = resources.files('interoperability').joinpath('transforms')
    registry.update_registry([d for f in sorted(bundled.iterdir(), key=lambda f: f.name)
                              if f.is_file() and f.name.endswith('.json') for d in json.loads(f.read_text())]
                             + config.get('transforms', []))
    return registry


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--config', type=Path, required=True, help='presentation service configuration declaring the device format')
    parser.add_argument('--device-format', required=True)
    parser.add_argument('--mirror-format', help='name of the mirror device format (default: <device format>_sep2)')
    parser.add_argument('--device-topic', default='devices/site1/der_sep2')
    parser.add_argument('--uai', nargs='+', default=['site1', 'der_sep2'])
    parser.add_argument('--server-url', default='https://127.0.0.1:8443')
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--served', action='store_true', help='the platform serves this 2030.5 server (driver_role server): its downward points are written by the platform')
    args = parser.parse_args(argv)
    registry = load_registry(args.config)
    written = write_case(registry, args.device_format, args.out, mirror_format=args.mirror_format or f'{args.device_format}_sep2',
                         device_topic=args.device_topic, uai=args.uai, server_url=args.server_url, served=args.served)
    for kind, path in written.items():
        print(f'{kind}: {path}')


if __name__ == '__main__':
    main()
