"""Compose and check the point set of an IEEE 1815.2 outstation the platform serves.

Nothing is discovered about a served device: its points are whatever we decide to serve, and IEEE 1815.2 fixes
what every index means, so the decision is which indexes to include. The point list carries what that decision
needs: each point's function group (``purpose``: Volt-Var, Freq-Watt, Scheduling, ...), whether it is mandatory
for 1815.2 conformance or for the IEEE 1547 subset, and the paired point an output is reflected by (an AO and the
AI that reads it back), which must be included or left out together.

:func:`catalog` lists the function groups with their counts, for a chooser. :func:`compose` turns a conformance
level, a choice of function groups and the points they bring into an index listing. :func:`validate` checks an
index listing from any source (a profile file, a registry, a scan) against the standard: unknown indexes, the
mandatory points missing for the claimed conformance, pairs with one end missing, and how much of each function
group is present. Both feed :func:`interoperability.discovery.dnp3.discover_indexes`, which does the rest.
"""
from __future__ import annotations

import csv
import io
import re
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Iterable

#: Conformance the served device claims: which points are always included and checked for.
CONFORMANCE = ('1815', '1547', 'none')
CONFORMANCE_LABELS = {'1815': 'IEEE 1815.2 mandatory points', '1547': 'IEEE 1547 mandatory subset', 'none': 'no conformance claimed'}
TABLES = ('AI', 'AO', 'BI', 'BO', 'CTR')
_ASSOCIATED = re.compile(r'^(AI|AO|BI|BO|CTR)[ _]?(\d+)$')
_POINT_NAME = re.compile(r'^\s*(AI|AO|BI|BO|CTR)_(\d+)\s*$')


def _points():
    from icm.models.ieee1815_2 import POINTS
    for table, definitions in POINTS.items():
        for index, definition in definitions.items():
            yield table.value, int(index), definition


def _section(purpose: str) -> str:
    """Where a function group sits in a chooser: the standard's sections, by what the purpose says."""
    lower = purpose.lower()
    if 'schedul' in lower:
        return 'scheduling'
    if 'curve' in lower:
        return 'curves'
    if 'equipment' in lower or lower in ('meters', 'inverters', 'batteries', 'der_units', 'number of units', 'system meter'):
        return 'equipment'
    if lower in ('vendor', 'experimental', 'gap #1', 'gap #2', 'functions', 'curves', 'scada, config', 'config'):
        return 'extensions'
    return 'functions'


def mandatory(definition, conformance: str) -> bool:
    if conformance == '1815':
        return bool(definition.mandatory_1815)
    if conformance == '1547':
        return bool(definition.mandatory_1547)
    return False


@dataclass
class FunctionGroup:
    key: str                      # 'volt_var'
    purpose: str                  # 'Volt-Var', as the point list names it
    section: str                  # functions | scheduling | curves | equipment | extensions
    points: list[str]             # every point name of the group, AI_290 ...
    mandatory_1815: list[str]
    mandatory_1547: list[str]
    description: str = ''

    @property
    def optional(self) -> list[str]:
        core = set(self.mandatory_1815) | set(self.mandatory_1547)
        return [p for p in self.points if p not in core]

    def to_json(self) -> dict:
        return {'key': self.key, 'purpose': self.purpose, 'section': self.section, 'points': len(self.points),
                'mandatory_1815': len(self.mandatory_1815), 'mandatory_1547': len(self.mandatory_1547), 'optional': len(self.optional),
                'description': self.description}


def _key(purpose: str) -> str:
    return re.sub(r'[^a-z0-9]+', '_', purpose.lower()).strip('_')


def catalog() -> list[FunctionGroup]:
    """The function groups of the IEEE 1815.2 point list, with the points each brings, in the order of a chooser:
    functions first, then scheduling, curves, equipment blocks and the extension areas."""
    groups: dict[str, FunctionGroup] = {}
    examples: dict[str, list[str]] = defaultdict(list)
    for table, index, definition in _points():
        purpose = definition.purpose or 'Unassigned'
        group = groups.get(purpose)
        if group is None:
            group = groups[purpose] = FunctionGroup(_key(purpose), purpose, _section(purpose), [], [], [])
        name = f'{table}_{index}'
        group.points.append(name)
        if definition.mandatory_1815:
            group.mandatory_1815.append(name)
        if definition.mandatory_1547:
            group.mandatory_1547.append(name)
        if len(examples[purpose]) < 3 and definition.uid:
            examples[purpose].append(definition.uid.split('.')[0])
    order = {'functions': 0, 'scheduling': 1, 'curves': 2, 'equipment': 3, 'extensions': 4}
    for group in groups.values():
        nodes = sorted(set(examples[group.purpose]))
        group.description = f'logical node{"s" if len(nodes) != 1 else ""} {", ".join(nodes)}' if nodes else ''
    return sorted(groups.values(), key=lambda g: (order[g.section], -len(g.mandatory_1815), g.purpose))


def catalog_json() -> dict:
    """What a chooser needs: the groups and the size of each conformance core."""
    groups = catalog()
    return {'conformance': [{'key': k, 'label': CONFORMANCE_LABELS[k], 'points': sum(len(g.mandatory_1815) if k == '1815' else len(g.mandatory_1547) if k == '1547' else 0 for g in groups)}
                            for k in CONFORMANCE],
            'groups': [g.to_json() for g in groups]}


def _split(name: str) -> tuple[str, int]:
    table, index = name.split('_')
    return table, int(index)


def _pair_of(definition) -> str | None:
    """The point an output is reflected by, as a point name (``AO0`` in the list becomes ``AO_0``)."""
    if not definition.associated:
        return None
    m = _ASSOCIATED.match(definition.associated.strip())
    return f'{m.group(1)}_{int(m.group(2))}' if m else None


def _definitions() -> dict[str, Any]:
    return {f'{table}_{index}': definition for table, index, definition in _points()}


def with_pairs(names: Iterable[str], definitions: dict[str, Any] | None = None) -> set[str]:
    """``names`` plus the paired point of every one that has one: an output and its read-back travel together."""
    definitions = definitions or _definitions()
    chosen = set(names)
    for name in list(chosen):
        definition = definitions.get(name)
        pair = _pair_of(definition) if definition else None
        if pair and pair in definitions:
            chosen.add(pair)
    return chosen


def compose(conformance: str = '1815', functions: Iterable[str | dict] = (), include_optional: bool = False) -> dict[str, list[int]]:
    """The index listing of a served outstation: the conformance core, plus the chosen function groups (by key or
    purpose; a dict ``{'key', 'optional'}`` chooses the group's optional points too), plus every paired point.

    A chosen group brings its mandatory points for either conformance level (its core) and, when asked, its
    optional points. ``include_optional`` asks for the optional points of every chosen group."""
    if conformance not in CONFORMANCE:
        raise ValueError(f'conformance must be one of {", ".join(CONFORMANCE)}, not {conformance!r}')
    definitions = _definitions()
    groups = {g.key: g for g in catalog()}
    by_purpose = {g.purpose.lower(): g for g in groups.values()}
    chosen: set[str] = {name for name, d in definitions.items() if mandatory(d, conformance)}
    for choice in functions:
        key, optional = (choice.get('key') or choice.get('purpose') or '', bool(choice.get('optional', include_optional))) if isinstance(choice, dict) else (choice, include_optional)
        group = groups.get(_key(str(key))) or by_purpose.get(str(key).lower())
        if group is None:
            raise ValueError(f'unknown IEEE 1815.2 function group {key!r}; the catalog lists the keys')
        chosen.update(group.mandatory_1815)
        chosen.update(group.mandatory_1547)
        if optional:
            chosen.update(group.optional)
    chosen = with_pairs(chosen, definitions)
    listing: dict[str, list[int]] = defaultdict(list)
    for name in chosen:
        table, index = _split(name)
        listing[table].append(index)
    return {table: sorted(listing[table]) for table in TABLES if listing.get(table)}


@dataclass
class Validation:
    conformance: str
    points: int = 0
    unknown: dict[str, list[int]] = field(default_factory=dict)         # indexes not in the standard, per table
    missing_mandatory: list[str] = field(default_factory=list)          # of the claimed conformance
    broken_pairs: list[tuple[str, str]] = field(default_factory=list)   # (present, missing partner)
    groups: list[dict] = field(default_factory=list)                    # per function group: present of total, core covered

    @property
    def conformant(self) -> bool:
        return not self.missing_mandatory and not self.unknown and not self.broken_pairs

    def notes(self) -> list[str]:
        """What the review step should say, one line per finding kind, nothing when all is well."""
        from .dnp3 import index_ranges
        out = []
        label = CONFORMANCE_LABELS[self.conformance]
        if self.conformance != 'none':
            if self.missing_mandatory:
                definitions = _definitions()
                by_group: dict[str, list[str]] = defaultdict(list)
                for name in self.missing_mandatory:
                    by_group[definitions[name].purpose or 'Unassigned'].append(name)
                shown = '; '.join(f'{purpose}: {len(names)} ({", ".join(names[:4])}{" …" if len(names) > 4 else ""})' for purpose, names in by_group.items())
                out.append(f'{len(self.missing_mandatory)} of the {label} are missing, by function group: {shown}; the outstation will not conform until they are served')
            else:
                out.append(f'all {label} are present')
        for table, indexes in self.unknown.items():
            out.append(f'{table}: {len(indexes)} index{"es" if len(indexes) != 1 else ""} not in the IEEE 1815.2 point list: {index_ranges(indexes)}')
        if self.broken_pairs:
            shown = ', '.join(f'{a} without {b}' for a, b in self.broken_pairs[:6]) + (' …' if len(self.broken_pairs) > 6 else '')
            out.append(f'{len(self.broken_pairs)} output/read-back pair{"s" if len(self.broken_pairs) != 1 else ""} with one end missing ({shown})')
        partial = [g for g in self.groups if 0 < g['present'] < g['points']]
        complete = [g for g in self.groups if g['present'] == g['points']]
        if complete:
            out.append(f'complete function groups: {", ".join(g["purpose"] for g in complete)}')
        if partial:
            out.append('partial function groups: ' + ', '.join(f'{g["purpose"]} ({g["present"]} of {g["points"]}{", core complete" if g["core_complete"] else ""})' for g in partial))
        return out

    def to_json(self) -> dict:
        return {'conformance': self.conformance, 'conformant': self.conformant, 'points': self.points, 'unknown': self.unknown,
                'missing_mandatory': self.missing_mandatory, 'broken_pairs': [list(p) for p in self.broken_pairs], 'groups': self.groups}


def validate(indexes: dict[str, Iterable[int]], conformance: str = '1815') -> Validation:
    """Check an index listing against the standard and the claimed conformance."""
    if conformance not in CONFORMANCE:
        raise ValueError(f'conformance must be one of {", ".join(CONFORMANCE)}, not {conformance!r}')
    definitions = _definitions()
    present: set[str] = set()
    result = Validation(conformance)
    for table, values in indexes.items():
        for index in values:
            name = f'{table}_{int(index)}'
            if name in definitions:
                present.add(name)
            else:
                result.unknown.setdefault(table, []).append(int(index))
    result.points = len(present) + sum(len(v) for v in result.unknown.values())
    result.missing_mandatory = sorted((name for name, d in definitions.items() if mandatory(d, conformance) and name not in present), key=_split)
    for name in sorted(present, key=_split):
        pair = _pair_of(definitions[name])
        if pair and pair in definitions and pair not in present:
            result.broken_pairs.append((name, pair))
    for group in catalog():
        here = [p for p in group.points if p in present]
        if here:
            core = set(group.mandatory_1815) | set(group.mandatory_1547)
            result.groups.append({'key': group.key, 'purpose': group.purpose, 'present': len(here), 'points': len(group.points),
                                  'core_complete': core <= present if core else True})
    return result


def indexes_from_registry(text: str) -> dict[str, list[int]]:
    """The index listing of a registry CSV whose point names are ``AI_537``, ``BO_17`` ... (the dnp3 driver's registries,
    including those this service writes). The first column that carries such names is read."""
    rows = list(csv.reader(io.StringIO(text)))
    listing: dict[str, set[int]] = defaultdict(set)
    for row in rows[1:] if rows else []:
        for cell in row:
            m = _POINT_NAME.match(cell or '')
            if m:
                listing[m.group(1)].add(int(m.group(2)))
                break
    if not listing:
        raise ValueError('the registry names no IEEE 1815.2 points (AI_<n>, AO_<n>, BI_<n>, BO_<n>, CTR_<n>)')
    return {table: sorted(listing[table]) for table in TABLES if listing.get(table)}
