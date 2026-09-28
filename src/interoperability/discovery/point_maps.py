"""Generate the IEEE 2030.5 agent's point map from the transform graph.

The VOLTTRON IEEE 2030.5 agent mirrors a platform driver device to a 2030.5 server through a CSV point
map whose rows pair a driver point with a 2030.5 attribute written ``Object::property`` (for example
``DERCapability::rtgMaxW``). For any device whose format reaches ``2030.5`` in the transform graph, the
composed field map of that chain is exactly the list of (device point, 2030.5 attribute) pairs the map
needs, so it can be generated instead of written by hand.

Only scalar attributes of the objects the agent understands are emitted; curve points and meter readings
are configured through other parts of the agent's configuration and are reported in the notes.
"""
from __future__ import annotations

import csv
from pathlib import Path

from ..transform_registry import TransformRegistry

#: 2030.5 resources the agent's point map accepts, and the object name it expects for each.
POINT_MAP_OBJECTS = {'DERCapability': 'DERCapability', 'DERSettings': 'DERSettings', 'DERStatus': 'DERStatus',
                     'DefaultDERControl': 'DefaultDERControl', 'DERControl': 'DERControlBase'}
COLUMNS = ['Point Name', 'Description', 'Multiplier', 'MRID', 'Offset', 'Parameter Type', 'Notes']


def ieee2030_5_point_map(registry: TransformRegistry, device_format: str) -> tuple[list[dict], list[str]]:
    """Rows of the agent's point map for a device format, and notes about what could not be expressed."""
    chain, retention, path = registry.lookup_scored(device_format, '2030.5')
    field_map = registry._chain_map(path)
    rows, notes, seen = [], [], set()
    for mapping in sorted(field_map.mappings, key=lambda m: (m.target, m.source)):
        if len(mapping.source) != 1 or mapping.fidelity <= 0:
            continue                                        # only flat device points map to a row
        point = mapping.source[0]
        target = mapping.target
        if '*' in target or '*' in point:
            notes.append(f'{point} -> {".".join(target)}: list data (curve points) is not expressible in the point map')
            continue
        if target[0] not in POINT_MAP_OBJECTS:
            notes.append(f'{point} -> {".".join(target)}: {target[0]} is configured elsewhere in the 2030.5 agent')
            continue
        if len(target) != 2:
            notes.append(f'{point} -> {".".join(target)}: nested attribute is not expressible as Object::property')
            continue
        key = (point, target)
        if key in seen:
            continue
        seen.add(key)
        rows.append({'Point Name': point, 'Description': '', 'Multiplier': '', 'MRID': '', 'Offset': '',
                     'Parameter Type': f'{POINT_MAP_OBJECTS[target[0]]}::{target[1]}',
                     'Notes': f'via {" > ".join(path[1:])}' + ('' if mapping.fidelity == 1 else f', fidelity {mapping.fidelity:.2f}')})
    return rows, notes


def write_point_map(path: Path, rows: list[dict]) -> None:
    with Path(path).open('w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
