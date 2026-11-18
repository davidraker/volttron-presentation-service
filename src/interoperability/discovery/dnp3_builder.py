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
#: Function points that name a stored curve by index (Volt-VAr Curve Index, the ride-through Must Trip Curve Index ...).
_CURVE_REF = re.compile(r'\.(?:[A-Za-z]*Crv|BlkRef)$')
_PAIR = re.compile(r'CrvPts\.(\d+)\.[xy]Val$')
#: Schedule layouts: the point list's own schedules and the legacy "BC" area, each one edit buffer plus a status block per schedule.
SCHEDULE_AREAS = {'schedules': ('Scheduling', 'FSCH'), 'bc_schedules': ('BC Scheduling', 'BC.FSCH')}
_SCHEDULE_ENTRY = re.compile(r'(?:SchdIntv|SchdEntr|ValMV)\.(\d+)$')
_SCHEDULE_BLOCK = re.compile(r'(?:^|\.)FSCH(\d+)\.')
#: Equipment blocks: the point list defines instance 1 of each (the standard repeats them at POINTS_PER steps).
EQUIPMENT_BLOCKS = {'meter': 'Meter', 'der_unit': 'DERUnit', 'inverter': 'Inverter', 'battery': 'Battery'}
#: Registry columns of the multiplexed areas (DNP3_SERVED_CURVE_SCHEDULE_STORAGE_PLAN.md, 3.1): a store row is the value of
#: a buffer point for one stored instance; the selector row is the one wire point of an area with data of its own.
MUX_COLUMNS = ('mux_area', 'mux_slot', 'readback_object_group', 'readback_variation', 'readback_index')
SELECTOR = 'selector'
#: Buffer points that are the outstation's own doing for the selected instance (`MESA.CrvRef`, the selected schedule's
#: status and validation state): wire rows the proxy writes, not store rows.
_COMPUTED = re.compile(r'\.(CrvRef|SchdSt(\.\d+)?)$')
MUX_AREAS = {'curve': 'curve', 'schedules': 'schedule', 'bc_schedules': 'bc_schedule'}     # capability key -> mux_area label


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


def _floor(names: Iterable[str], numbered: re.Pattern, definitions: dict, conformance: str) -> int:
    """The highest number (pair, entry, block) among ``names`` that the conformance level makes mandatory."""
    best = 0
    for name in names:
        m = numbered.search(definitions[name].uid)
        if m and mandatory(definitions[name], conformance):
            best = max(best, int(m.group(1)))
    return best


def curve_capability(definitions: dict | None = None) -> dict:
    """The curve edit buffer: its header points, its X/Y pairs by number, how many pairs each conformance level makes
    mandatory, and which function groups reference a stored curve (and so need the buffer at all)."""
    definitions = definitions or _definitions()
    header, pairs, referenced = [], defaultdict(list), defaultdict(list)
    for name, d in definitions.items():
        if d.purpose == 'Curve':
            m = _PAIR.search(d.uid)
            if m:
                pairs[int(m.group(1))].append(name)
            else:
                header.append(name)
        elif d.purpose not in ('Discovery',) and _CURVE_REF.search(d.uid) and name.startswith(('AI_', 'AO_')):
            referenced[_key(d.purpose or 'Unassigned')].append(d.uid)
    all_pairs = [n for names in pairs.values() for n in names]
    return {'header': sorted(header, key=_split), 'pairs': {n: sorted(v, key=_split) for n, v in sorted(pairs.items())}, 'pairs_max': max(pairs) if pairs else 0,
            'pairs_floor': {c: _floor(all_pairs, _PAIR, definitions, c) for c in CONFORMANCE},
            'referenced_by': {k: sorted(set(v)) for k, v in sorted(referenced.items())}}


def schedule_capability(area: str, definitions: dict | None = None) -> dict:
    """A schedule area: the edit buffer's header, its entries by number, the status block of each stored schedule by
    number, and the floors each conformance level sets on entries and schedules."""
    definitions = definitions or _definitions()
    purpose, _ = SCHEDULE_AREAS[area]
    header, entries, blocks = [], defaultdict(list), defaultdict(list)
    for name, d in definitions.items():
        if d.purpose != purpose:
            continue
        block = _SCHEDULE_BLOCK.search(d.uid)
        entry = _SCHEDULE_ENTRY.search(d.uid)
        if block:
            blocks[int(block.group(1))].append(name)
        elif entry:
            entries[int(entry.group(1))].append(name)
        else:
            header.append(name)
    return {'header': sorted(header, key=_split), 'entries': {n: sorted(v, key=_split) for n, v in sorted(entries.items())},
            'blocks': {n: sorted(v, key=_split) for n, v in sorted(blocks.items())},
            'entries_max': max(entries) if entries else 0, 'blocks_max': max(blocks) if blocks else 0,
            'entries_floor': {c: _floor([n for v in entries.values() for n in v], _SCHEDULE_ENTRY, definitions, c) for c in CONFORMANCE},
            'blocks_floor': {c: _floor([n for v in blocks.values() for n in v], _SCHEDULE_BLOCK, definitions, c) for c in CONFORMANCE}}


def equipment_capability(definitions: dict | None = None) -> dict[str, dict]:
    """The equipment blocks (meter, DER unit, inverter, battery): the points of the one instance the point list defines."""
    from icm.models.ieee1815_2 import PointGroup, profiles
    definitions = definitions or _definitions()
    out = {}
    for key, class_name in EQUIPMENT_BLOCKS.items():
        cls = getattr(profiles, class_name)
        names = []
        for info in cls.model_fields.values():
            for ann in getattr(info.annotation, '__args__', (info.annotation,)):
                if isinstance(ann, type) and issubclass(ann, PointGroup):
                    names += [f'{ann.POINT_TYPE.value}_{i}' for _, idxs in ann.iter_points(1) for i in idxs if f'{ann.POINT_TYPE.value}_{i}' in definitions]
        out[key] = {'key': key, 'label': cls.PURPOSE.replace(' equipment block', '').replace('DERUnit', 'DER unit'), 'points': sorted(set(names), key=_split),
                    'start': cls.START, 'points_per_instance': cls.POINTS_PER, 'instances_defined': 1}
    return out


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
    """What a chooser needs: the conformance cores, the function groups (functions and extensions) with their optional
    points listed, and the capabilities that are sized rather than ticked: the curve buffer, the schedule areas and
    the equipment blocks."""
    definitions = _definitions()
    groups = catalog()
    curves = curve_capability(definitions)
    schedules = {area: schedule_capability(area, definitions) for area in SCHEDULE_AREAS}
    equipment = equipment_capability(definitions)

    def optional_points(g):
        out = []
        for name in g.optional:
            d = definitions[name]
            out.append({'name': name, 'uid': d.uid, 'description': (d.name or '').split('.')[0].strip()[:90], 'pair': _pair_of(d)})
        return out
    return {'conformance': [{'key': k, 'label': CONFORMANCE_LABELS[k], 'points': sum(1 for d in definitions.values() if mandatory(d, k))} for k in CONFORMANCE],
            'groups': [{**g.to_json(), 'optional_points': optional_points(g), 'references_curves': g.key in curves['referenced_by']}
                       for g in groups if g.section in ('functions', 'extensions')],
            'curves': {'header_points': len(curves['header']), 'pairs_max': curves['pairs_max'], 'pairs_floor': curves['pairs_floor'],
                       'points_per_pair': len(curves['pairs'].get(1, [])), 'referenced_by': curves['referenced_by']},
            'schedules': [{'key': area, 'label': 'Schedules' if area == 'schedules' else 'Legacy (BC) schedules', 'header_points': len(cap['header']),
                           'entries_max': cap['entries_max'], 'blocks_max': cap['blocks_max'], 'entries_floor': cap['entries_floor'], 'blocks_floor': cap['blocks_floor'],
                           'points_per_entry': len(cap['entries'].get(1, [])), 'points_per_block': len(cap['blocks'].get(1, []))}
                          for area, cap in schedules.items()],
            'equipment': [{'key': e['key'], 'label': e['label'], 'points': len(e['points']), 'instances_defined': e['instances_defined']} for e in equipment.values()]}


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


def compose(conformance: str = '1815', functions: Iterable[str | dict] = (), include_optional: bool = False,
            curves: dict | bool | None = None, schedules: dict | None = None, equipment: Iterable[str] = ()) -> dict[str, list[int]]:
    """The index listing of a served outstation: the conformance core, the chosen function groups, the sized
    capabilities, and every paired point.

    ``functions``: group keys or purposes, or dicts ``{'key', 'optional'}`` where ``optional`` is ``True`` (all of the
    group's optional points) or a list of optional point names. ``include_optional`` asks for every chosen group's
    optional points. A chosen group always brings its mandatory points for either conformance level (its core).

    ``curves``: ``{'pairs': N}`` serves the curve edit buffer with N X/Y pairs (never fewer than the conformance level
    makes mandatory); ``None`` serves it when a chosen function references a curve, at the conformance floor (4 pairs
    when the level sets none); ``False`` leaves it out. ``schedules``: ``{'schedules': {'held': K, 'entries': M},
    'bc_schedules': {...}}`` serves a schedule area with K status blocks and an M-entry edit buffer, floors applied.
    ``equipment``: keys of equipment blocks to serve (one instance each)."""
    if conformance not in CONFORMANCE:
        raise ValueError(f'conformance must be one of {", ".join(CONFORMANCE)}, not {conformance!r}')
    definitions = _definitions()
    groups = {g.key: g for g in catalog()}
    by_purpose = {g.purpose.lower(): g for g in groups.values()}
    chosen: set[str] = {name for name, d in definitions.items() if mandatory(d, conformance)}
    chosen_groups: list[FunctionGroup] = []
    for choice in functions:
        key, optional = (choice.get('key') or choice.get('purpose') or '', choice.get('optional', include_optional)) if isinstance(choice, dict) else (choice, include_optional)
        group = groups.get(_key(str(key))) or by_purpose.get(str(key).lower())
        if group is None:
            raise ValueError(f'unknown IEEE 1815.2 function group {key!r}; the catalog lists the keys')
        chosen_groups.append(group)
        chosen.update(group.mandatory_1815)
        chosen.update(group.mandatory_1547)
        if optional is True or include_optional:
            chosen.update(group.optional)
        elif optional:
            unknown = [n for n in optional if n not in group.optional]
            if unknown:
                raise ValueError(f'{group.purpose}: not among its optional points: {", ".join(map(str, unknown[:6]))}')
            chosen.update(optional)
    cap = curve_capability(definitions)
    references = [g.purpose for g in chosen_groups if g.key in cap['referenced_by']]
    if curves is None:
        curves = {'pairs': cap['pairs_floor'][conformance] or 4} if references else False
    if curves:
        pairs = max(int(curves.get('pairs', 0)), cap['pairs_floor'][conformance])
        chosen.update(cap['header'])
        for n in range(1, pairs + 1):
            chosen.update(cap['pairs'].get(n, []))
    for area, spec in (schedules or {}).items():
        if area not in SCHEDULE_AREAS:
            raise ValueError(f'unknown schedule area {area!r}; choose from {", ".join(SCHEDULE_AREAS)}')
        if not spec:
            continue
        s_cap = schedule_capability(area, definitions)
        held = max(int(spec.get('held', 0)), s_cap['blocks_floor'][conformance])
        entries = max(int(spec.get('entries', 0)), s_cap['entries_floor'][conformance])
        chosen.update(s_cap['header'])
        for n in range(1, entries + 1):
            chosen.update(s_cap['entries'].get(n, []))
        for n in range(1, held + 1):
            chosen.update(s_cap['blocks'].get(n, []))
    blocks = equipment_capability(definitions)
    for key in equipment:
        if key not in blocks:
            raise ValueError(f'unknown equipment block {key!r}; choose from {", ".join(blocks)}')
        chosen.update(blocks[key]['points'])
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
    curves_unserved: list[str] = field(default_factory=list)            # function groups present that reference curves, with no curve buffer served
    curve_pairs: int = 0                                                # X/Y pairs of the curve buffer present

    @property
    def conformant(self) -> bool:
        return not self.missing_mandatory and not self.unknown and not self.broken_pairs and not self.curves_unserved

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
        if self.curves_unserved:
            out.append(f'{", ".join(self.curves_unserved)} reference stored curves but no curve edit buffer is served; the master cannot define the curves those functions use')
        elif self.curve_pairs:
            out.append(f'curve edit buffer with {self.curve_pairs} X/Y pairs')
        partial = [g for g in self.groups if 0 < g['present'] < g['points']]
        complete = [g for g in self.groups if g['present'] == g['points']]
        if complete:
            out.append(f'complete function groups: {", ".join(g["purpose"] for g in complete)}')
        if partial:
            out.append('partial function groups: ' + ', '.join(f'{g["purpose"]} ({g["present"]} of {g["points"]}{", core complete" if g["core_complete"] else ""})' for g in partial))
        return out

    def to_json(self) -> dict:
        return {'conformance': self.conformance, 'conformant': self.conformant, 'points': self.points, 'unknown': self.unknown,
                'missing_mandatory': self.missing_mandatory, 'broken_pairs': [list(p) for p in self.broken_pairs], 'groups': self.groups,
                'curves_unserved': self.curves_unserved, 'curve_pairs': self.curve_pairs}


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
    cap = curve_capability(definitions)
    result.curve_pairs = sum(1 for n, names in cap['pairs'].items() if any(p in present for p in names))
    for group in catalog():
        here = [p for p in group.points if p in present]
        if here:
            core = set(group.mandatory_1815) | set(group.mandatory_1547)
            result.groups.append({'key': group.key, 'purpose': group.purpose, 'present': len(here), 'points': len(group.points),
                                  'core_complete': core <= present if core else True})
            if group.key in cap['referenced_by'] and not result.curve_pairs and any(definitions[p].uid in cap['referenced_by'][group.key] for p in here):
                result.curves_unserved.append(group.purpose)
    return result


def _short(uid: str) -> str:
    """A point name fragment from a 61850 identifier: ``FMARn.PairArr.CrvPts.4.yVal`` -> ``Y4``, ``DGSMn.ModTyp`` -> ``ModTyp``,
    ``FSCHn.SchdIntv.7`` -> ``SchdIntv7``, ``Type.FSCHn.SchdEntr.2`` -> ``Type_SchdEntr2``."""
    m = _PAIR.search(uid)
    if m:
        return f'{"X" if uid.endswith("xVal") else "Y"}{m.group(1)}'
    parts = [p for p in uid.split('.') if p not in ('BC', 'FSCC', 'FSCCn', 'FSCHn', 'FMARn', 'PairArr', 'DGSMn', 'MESAn')]
    leading = []
    while parts and parts[0] in ('Type', 'Point'):
        leading.append(parts.pop(0))
    return '_'.join(leading + [''.join(parts)])


@dataclass
class StoreRow:
    """One value of a multiplexed area for one stored instance, and the wire points it is presented through."""
    area: str                 # mux_area label: curve, schedule, bc_schedule
    slot: int | str           # 1-based, or SELECTOR
    name: str                 # volttron_point_name, free
    written: str              # the buffer point the master writes (AO_249) or, for an input-only buffer point, reads (AI_3010)
    readback: str | None      # the input that shows it back (AI_333), when the written point is an output
    uid: str
    description: str

    def columns(self) -> dict:
        from .device_formats import DNP3_GROUPS
        from .dnp3 import DEFAULT_VARIATIONS
        table, index = _split(self.written)
        out = {'mux_area': self.area, 'mux_slot': self.slot, 'readback_object_group': '', 'readback_variation': '', 'readback_index': ''}
        if self.readback:
            r_table, r_index = _split(self.readback)
            out.update({'readback_object_group': DNP3_GROUPS[r_table], 'readback_variation': DEFAULT_VARIATIONS[r_table], 'readback_index': r_index})
        return out


def mux_areas(indexes: dict[str, Iterable[int]], definitions: dict | None = None) -> dict[str, dict]:
    """The multiplexed areas a composed listing touches: for each, its selector (AO and read-back AI), the buffer points
    present (written point with its read-back), and the computed wire points. Keys are mux_area labels."""
    definitions = definitions or _definitions()
    present = {f'{t}_{int(i)}' for t, v in indexes.items() for i in v}
    areas: dict[str, dict] = {}
    caps = {'curve': curve_capability(definitions)}
    caps.update({MUX_AREAS[a]: schedule_capability(a, definitions) for a in SCHEDULE_AREAS})
    for label, cap in caps.items():
        buffer = set(cap['header']) | {n for names in (cap.get('pairs') or cap.get('entries') or {}).values() for n in names}
        here = buffer & present
        if not here:
            continue
        pairs: dict[str, str | None] = {}          # written -> readback
        selector_ao = selector_ai = None
        computed = []
        for name in sorted(here, key=_split):
            d = definitions[name]
            partner = _pair_of(d)
            if 'Selector' in (d.name or '') or d.uid.endswith(('.InCrv', 'FSCC.Schd')):
                if name.startswith(('AO_', 'BO_')):
                    selector_ao = name
                else:
                    selector_ai = name
                continue
            if _COMPUTED.search(d.uid):
                computed.append(name)
                continue
            if name.startswith(('AO_', 'BO_')):
                pairs[name] = partner if partner in here else None
            elif not (partner and partner in here and partner.startswith(('AO_', 'BO_'))):
                pairs[name] = None                    # an input-only buffer point: the outstation's view of the selected instance
        areas[label] = {'selector': selector_ao, 'selector_readback': selector_ai, 'buffer': pairs, 'computed': computed}
    return areas


def store_rows(indexes: dict[str, Iterable[int]], slots: dict[str, int], definitions: dict | None = None) -> tuple[dict[str, list[int]], list[StoreRow]]:
    """Split a composed listing into the wire points and the store rows of its multiplexed areas.

    ``slots`` gives the stored instances per mux_area label (``{'curve': 4, 'schedule': 20}``). The buffer points of
    each area leave the wire listing (the proxy derives them from the store rows); the selector and the computed points
    stay. Returns the remaining listing and the rows: one selector row per area, then one store row per buffer value
    per slot, named ``<area><slot>_<short uid>``."""
    definitions = definitions or _definitions()
    areas = mux_areas(indexes, definitions)
    drop: set[str] = set()
    rows: list[StoreRow] = []
    for label, area in areas.items():
        count = int(slots.get(label, 1) or 1)
        for written, readback in area['buffer'].items():
            drop.add(written)
            if readback:
                drop.add(readback)
        if area['selector']:
            d = definitions[area['selector']]
            rows.append(StoreRow(label, SELECTOR, f'{label}_Selector', area['selector'], area['selector_readback'], d.uid, (d.name or '').split('.')[0].strip()))
            drop.add(area['selector'])
            if area['selector_readback']:
                drop.add(area['selector_readback'])
        for slot in range(1, count + 1):
            used: set[str] = set()
            for written, readback in area['buffer'].items():
                d = definitions[written]
                name = f'{label}{slot}_{_short(d.uid)}'
                if name in used:                       # the point list reuses an identifier (start and stop dates): the address tells them apart
                    name = f'{name}_{_split(written)[1]}'
                used.add(name)
                rows.append(StoreRow(label, slot, name, written, readback, d.uid, (d.name or '').split('.')[0].strip()))
    remaining = {t: [i for i in v if f'{t}_{int(i)}' not in drop] for t, v in indexes.items()}
    return {t: v for t, v in remaining.items() if v}, rows


def validate_rows(rows: list[dict]) -> list[str]:
    """Shape checks on a registry's multiplexed rows: addresses inside the area's buffer, slots dense from 1, exactly one
    selector per area, read-back present where the written point is an output. Returns findings, empty when sound."""
    definitions = _definitions()
    caps = {'curve': curve_capability(definitions)}
    caps.update({MUX_AREAS[a]: schedule_capability(a, definitions) for a in SCHEDULE_AREAS})
    findings = []
    by_area: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        if str(row.get('mux_area') or '').strip():
            by_area[str(row['mux_area']).strip()].append(row)
    for label, area_rows in by_area.items():
        cap = caps.get(label)
        buffer = set(cap['header']) | {n for names in (cap.get('pairs') or cap.get('entries') or {}).values() for n in names} if cap else set()
        selectors = [r for r in area_rows if str(r.get('mux_slot')).strip() == SELECTOR]
        if len(selectors) != 1:
            findings.append(f'{label}: {len(selectors)} selector rows (exactly one expected)')
        slots = sorted({int(r['mux_slot']) for r in area_rows if str(r.get('mux_slot')).strip() not in ('', SELECTOR) and str(r['mux_slot']).strip().isdigit()})
        if slots and slots != list(range(1, slots[-1] + 1)):
            findings.append(f'{label}: slots are not dense from 1: {slots}')
        for r in area_rows:
            name = f'{ {30: "AI", 40: "AO", 1: "BI", 10: "BO", 20: "CTR"}.get(int(r["object_group"]), "?") }_{int(r["index"])}'
            if cap and name not in buffer and str(r.get('mux_slot')).strip() != SELECTOR:
                findings.append(f'{label}: {r.get("volttron_point_name")} at {name} is not a buffer point of the area')
            if name.startswith(('AO_', 'BO_')) and not str(r.get('readback_index') or '').strip():
                findings.append(f'{label}: {r.get("volttron_point_name")} writes {name} but names no read-back input')
    return findings


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
