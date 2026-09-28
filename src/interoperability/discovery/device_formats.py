"""Device formats: a platform driver's flat point list as a format of its own, and the transforms that
turn it into a protocol's nested shape and back.

A platform driver publishes ``devices/<campus>/<building>/<device>/all`` as a flat ``{point name: value}``
message. When the device speaks SunSpec, its registry can name each point after the SunSpec path it
holds, and from those names alone the transforms between the device format and ``sunspec`` can be
generated: this is the "derive a format from a registry" step of the configuration workflow.

Point naming: ``<model>_<segment>_...`` where a repeating group carries a 1-based index, e.g.
``701_W``, ``704_PFWInj_PF``, ``705_Crv1_ActPt``, ``705_Crv1_Pt3_Var``, ``708_Crv1_MustTrip_Pt1_V``.
Names are validated against the generated SunSpec model classes.

Scale factors. SunSpec values are integers scaled by a companion ``_SF`` register. Where the scaling
happens is a build-time choice, ``scaling``:

* ``'transform'``: the driver publishes raw registers, including the ``_SF`` points. Reads apply
  ``scale_reg_pow_10`` against the published factor; writes bake the factor in as a constant, which
  requires the discovered values (``scale_factors``), since a write arriving from another protocol
  carries none.
* ``'driver'``: the driver applies the factors (its registry carries a ``Transform`` column) and the
  ``_SF`` points are not published. Values pass through unscaled in both directions.
"""
from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field

from ..field_universe import _group_type
from ..models.sunspec import MODEL_REGISTRY, SunSpecGroup

_INDEXED = re.compile(r'^([A-Za-z_][A-Za-z0-9_]*?)(\d+)$')
#: SunSpec point that counts the valid entries of a sibling ``Pt`` list.
ACTIVE_COUNT = 'ActPt'
SCALING_MODES = ('transform', 'driver')


def _levels(point_name: str) -> list[tuple[type, tuple[str, ...]]]:
    """(group class, name prefix) for the model and every group enclosing the point, outermost first,
    followed by the point's own (None, full prefix) entry. Raises ValueError for anything not in the model."""
    segments = point_name.split('_')
    model_id, rest = segments[0], segments[1:]
    try:
        cls = MODEL_REGISTRY[int(model_id)]
    except (ValueError, KeyError):
        raise ValueError(f'{point_name!r}: {model_id!r} is not a SunSpec model number') from None
    levels: list = [(cls, (model_id,))]
    prefix = (model_id,)
    position = 0
    while position < len(rest):
        if cls is None:
            raise ValueError(f'{point_name!r}: {rest[position]!r} follows a point, which has no members')
        by_name = cls.model_fields
        # SunSpec names may themselves contain underscores (W_SF, TotWh_SF): take the longest run of
        # segments that names a point or group.
        for width in range(len(rest) - position, 0, -1):
            segment = '_'.join(rest[position:position + width])
            if segment in by_name:
                name, index = segment, None
                break
            match = _INDEXED.match(segment)
            if match and match.group(1) in by_name:
                name, index = match.group(1), int(match.group(2)) - 1
                break
        else:
            raise ValueError(f'{point_name!r}: {rest[position]!r} is not a point or group of SunSpec model {model_id}')
        position += width
        group = _group_type(by_name[name].annotation, SunSpecGroup)
        prefix = prefix + (segment,)
        if group is None:
            if index is not None:
                raise ValueError(f'{point_name!r}: {name} is a point, not a repeating group')
            levels.append((None, prefix))
            cls = None
        else:
            sub, is_list = group
            if is_list and index is None:
                raise ValueError(f'{point_name!r}: {name} is a repeating group and needs an index (e.g. {name}1)')
            if not is_list and index is not None:
                raise ValueError(f'{point_name!r}: {name} does not repeat')
            cls = sub
            levels.append((cls, prefix))
    if cls is not None:
        raise ValueError(f'{point_name!r} names a group, not a point')
    return levels


def sunspec_point_path(point_name: str) -> tuple:
    """Path of a named SunSpec point, e.g. ``705_Crv1_Pt3_Var`` -> ``('705', 'Crv', 0, 'Pt', 2, 'Var')``."""
    levels = _levels(point_name)
    path: list = [levels[0][1][0]]
    for cls, prefix in levels[1:]:
        segment = prefix[-1]
        if segment in _owner(levels, prefix).model_fields:
            path.append(segment)
        else:
            match = _INDEXED.match(segment)
            path.extend([match.group(1), int(match.group(2)) - 1])
    return tuple(path)


def _owner(levels, prefix):
    """Class owning the segment ``prefix[-1]``: the level whose prefix is ``prefix[:-1]``."""
    return next(cls for cls, p in levels if p == prefix[:-1])


def sunspec_point_metadata(point_name: str) -> dict:
    levels = _levels(point_name)
    return _owner(levels, levels[-1][1]).point_metadata(levels[-1][1][-1])


def sunspec_scale_factor(point_name: str) -> str | int | None:
    """How a point is scaled: the registry name of its scale factor point (found in the point's own group or
    an enclosing one, e.g. ``705_V_SF`` for ``705_Crv1_Pt1_V``), a fixed exponent, or None."""
    levels = _levels(point_name)
    sf = _owner(levels, levels[-1][1]).point_metadata(levels[-1][1][-1]).get('sf')
    if sf is None or isinstance(sf, int):
        return sf
    for cls, prefix in reversed(levels[:-1]):
        if cls is not None and sf in cls.model_fields:
            return '_'.join(prefix + (sf,))
    raise ValueError(f'{point_name!r}: scale factor point {sf!r} not found in its model')


def is_scale_factor_point(point_name: str) -> bool:
    return sunspec_point_metadata(point_name).get('type') == 'sunssf'


def infer_scaling(rows: list[dict]) -> str:
    """Which side scales, from an existing registry: rows with a ``Transform`` entry mean the driver does;
    ``_SF`` points present with no transforms mean the transform must."""
    if any((row.get('Transform') or '').strip() for row in rows):
        return 'driver'
    names = [row.get('Volttron Point Name', '') for row in rows]
    if any(is_scale_factor_point(n) for n in names if n):
        return 'transform'
    raise ValueError('cannot infer scaling: the registry has neither Transform entries nor scale factor points')


@dataclass
class DeviceTransforms:
    definitions: list[dict]
    scaling: str
    notes: list[str] = field(default_factory=list)


class _Builder:
    def __init__(self, point_names: list[str], scaling: str, scale_factors: dict[str, int] | None):
        if scaling not in SCALING_MODES:
            raise ValueError(f'scaling must be one of {SCALING_MODES}, got {scaling!r}')
        self.scaling = scaling
        self.scale_factors = scale_factors or {}
        self.names = set(point_names)
        self.notes: list[str] = []
        self.points = [n for n in point_names if not (scaling == 'driver' and is_scale_factor_point(n))]

    # --- scaling decisions -------------------------------------------------------------------------------
    def read_functions(self, point: str) -> str:
        """Functions applied when reading a point from the device (device -> sunspec)."""
        if self.scaling != 'transform':
            return ''
        sf = sunspec_scale_factor(point)
        if sf is None or is_scale_factor_point(point):
            return ''
        if isinstance(sf, int):
            return f'scale({10.0 ** sf!r})'
        if sf in self.names:
            return f"scale_reg_pow_10('/{sf}')"
        if sf in self.scale_factors:
            return f'scale({10.0 ** self.scale_factors[sf]!r})'
        self.notes.append(f'{point}: scale factor {sf} is neither in the registry nor discovered; read left unscaled')
        return ''

    def write_factor(self, point: str) -> float | None:
        """Constant multiplier applied when writing a point to the device (sunspec -> device), if known."""
        if self.scaling != 'transform':
            return None
        sf = sunspec_scale_factor(point)
        if sf is None or is_scale_factor_point(point):
            return None
        if isinstance(sf, int):
            return 10.0 ** -sf
        if sf in self.scale_factors:
            return 10.0 ** -self.scale_factors[sf]
        self.notes.append(f'{point}: scale factor {sf} was not discovered; write left unscaled')
        return None

    # --- tree ---------------------------------------------------------------------------------------------
    def tree(self) -> dict:
        tree: dict = {}
        for name in self.points:
            node = tree
            path = sunspec_point_path(name)
            for segment in path[:-1]:
                node = node.setdefault(segment, {})
            node[path[-1]] = name
        return tree

    @staticmethod
    def _is_point_table(indexed: dict) -> bool:
        if set(indexed) != set(range(len(indexed))):
            return False
        shapes = {tuple(sorted(entry)) for entry in indexed.values()}
        return len(shapes) == 1 and all(isinstance(v, str) for entry in indexed.values() for v in entry.values())

    @staticmethod
    def _template(point_name: str, group: str) -> str:
        segments = point_name.split('_')
        index = max(i for i, seg in enumerate(segments) if seg == f'{group}1')
        segments[index] = group + '{}'
        return '_'.join(segments)

    def _specs(self, first_entry: dict, group: str) -> str:
        return ', '.join(f"'{f}:{self._template(first_entry[f], group)}'" for f in sorted(first_entry))

    def to_protocol(self, node: dict, anchored: bool) -> dict:
        prefix = '#, ' if anchored else ''
        pattern: dict = {}
        for key, child in node.items():
            if isinstance(child, str):
                pattern[key] = f'transform[{prefix}{child}]({self.read_functions(child)})'
            elif all(isinstance(k, int) for k in child):
                if self._is_point_table(child):
                    first = child[0]
                    functions = f'series({len(child)}, 1, {self._specs(first, key)})'
                    counter = node.get(ACTIVE_COUNT)
                    if isinstance(counter, str):
                        functions += f", take('/{counter}')"
                    pattern[f'{key}[#]'] = {'#': f'transform({functions})',
                                           **{f: f'transform[#, {f}]({self.read_functions(first[f])})' for f in sorted(first)}}
                else:
                    for index in sorted(child):
                        pattern[f'{key}[#] {index + 1}'] = {'#': 'transform(as_list())', **self.to_protocol(child[index], True)}
            else:
                pattern[key] = self.to_protocol(child, anchored)
        return pattern

    def from_protocol(self, node: dict, path: tuple) -> dict:
        pattern: dict = {}
        for key, child in node.items():
            here = path + (key,)
            source = ', '.join(str(p) for p in here)
            if isinstance(child, str):
                factor = self.write_factor(child)
                pattern[child] = f'transform[{source}]({"" if factor is None else f"scale({factor!r})"})'
            elif all(isinstance(k, int) for k in child):
                if self._is_point_table(child):
                    first = child[0]
                    factors = {f: self.write_factor(first[f]) for f in sorted(first)}
                    functions = []
                    if any(v is not None for v in factors.values()):
                        functions.append('scale_fields(' + ', '.join(f"'{f}:{v!r}'" for f, v in factors.items() if v is not None) + ')')
                    functions.append(f'unseries(1, {self._specs(first, key)})')
                    pattern[f'*{"_".join(str(p) for p in here)}'] = f'transform[{source}]({", ".join(functions)})'
                else:
                    for index in sorted(child):
                        pattern.update(self.from_protocol(child[index], here + (index,)))
            else:
                pattern.update(self.from_protocol(child, here))
        return pattern


def sunspec_device_transforms(device_format: str, point_names: list[str], *, scaling: str = 'transform',
                              scale_factors: dict[str, int] | None = None) -> DeviceTransforms:
    """Transform definitions between a device format (flat SunSpec-named points) and ``sunspec``.

    ``scale_factors`` maps scale factor point names (``705_V_SF``) to their discovered values; in
    ``transform`` mode they make write-side scaling possible. Points whose scaling could not be
    arranged are listed in ``notes``.
    """
    builder = _Builder(point_names, scaling, scale_factors)
    tree = builder.tree()
    definitions = [{'input_format': device_format, 'output_format': 'sunspec', 'pattern': builder.to_protocol(tree, False)},
                   {'input_format': 'sunspec', 'output_format': device_format, 'pattern': builder.from_protocol(tree, ())}]
    return DeviceTransforms(definitions, scaling, sorted(set(builder.notes)))


def device_format_declaration(point_names: list[str], scaling: str = 'transform') -> dict:
    """The ``formats`` entry for a device: a leaf whose fields are its point names, recording who scales."""
    return {'hub': False, 'scaling': scaling, 'fields': sorted(point_names)}


def sunspec_points_by_model(point_names: list[str]) -> dict[str, list[str]]:
    grouped: dict[str, list[str]] = defaultdict(list)
    for name in point_names:
        grouped[str(sunspec_point_path(name)[0])].append(name)
    return dict(grouped)


# ================================================================================================= DNP3
# IEEE 1815.2 (MESA-DER) devices behind the dnp3 platform driver. Point names are table and index, e.g.
# ``AI_297``; the tables map onto the ``1815.2.inputs`` (AI, BI, CTR) and ``1815.2.outputs`` (AO, BO) formats.

DNP3_GROUPS = {'AI': 30, 'BI': 1, 'AO': 40, 'BO': 10, 'CTR': 20}
DNP3_INPUT_TABLES = ('AI', 'BI', 'CTR')
DNP3_OUTPUT_TABLES = ('AO', 'BO')
_DNP3_NAME = re.compile(r'^(AI|AO|BI|BO|CTR)_(\d+)$')


def dnp3_point_path(point_name: str) -> tuple[str, str]:
    """``AI_297`` -> ``('AI', '297')``, validated against the IEEE 1815.2 point registry."""
    from ..models.ieee1815_2 import POINTS, PointType
    match = _DNP3_NAME.match(point_name)
    if not match:
        raise ValueError(f'{point_name!r}: DNP3 point names are <table>_<index>, e.g. AI_297')
    table, index = match.group(1), int(match.group(2))
    if index not in POINTS[PointType(table)]:
        raise ValueError(f'{point_name!r}: {table} index {index} is not in the IEEE 1815.2 point list')
    return table, str(index)


def dnp3_point_definition(point_name: str):
    from ..models.ieee1815_2 import POINTS, PointType
    table, index = dnp3_point_path(point_name)
    return POINTS[PointType(table)][int(index)]


def dnp3_scaling(point_name: str) -> tuple[float, float]:
    """(multiplier, offset) that turn the raw DNP3 value into engineering units; (1, 0) when none."""
    definition = dnp3_point_definition(point_name)
    return (definition.multiplier if definition.multiplier is not None else 1.0,
            definition.offset if definition.offset is not None else 0.0)


def _dnp3_functions(multiplier: float, offset: float, inverse: bool) -> str:
    """``scale``/``add`` calls applying (or undoing) a profile multiplier and offset."""
    steps = []
    if not inverse:
        if multiplier != 1:
            steps.append(f'scale({multiplier!r})')
        if offset:
            steps.append(f'add({offset!r})')
    else:
        if offset:
            steps.append(f'add({-offset!r})')
        if multiplier != 1:
            steps.append(f'scale({1 / multiplier!r})')
    return ', '.join(steps)


def dnp3_device_transforms(device_format: str, point_names: list[str], *, scaling: str = 'transform') -> DeviceTransforms:
    """Transform definitions between a DNP3 device format and the ``1815.2.inputs`` / ``1815.2.outputs`` formats.

    Multipliers and offsets come from the IEEE 1815.2 profile, so both directions can be scaled without
    discovery. In ``transform`` scaling the device edge applies them (raw counts in, engineering units out,
    and the inverse on writes); in ``driver`` scaling the driver does and values pass through. Reads produce
    both ``1815.2.inputs`` and ``1815.2.outputs`` (the read-back of AO and BO); writes come only from
    ``1815.2.outputs``, with curve write batches (``sequence``) carried to the device as lists of flat points.
    """
    if scaling not in SCALING_MODES:
        raise ValueError(f'scaling must be one of {SCALING_MODES}, got {scaling!r}')
    by_table: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for name in point_names:
        table, index = dnp3_point_path(name)
        by_table[table].append((index, name))
    definitions = []
    for fmt, tables in (('1815.2.inputs', DNP3_INPUT_TABLES), ('1815.2.outputs', DNP3_OUTPUT_TABLES)):
        to_protocol: dict = {}
        from_protocol: dict = {}
        for table in tables:
            if not by_table.get(table):
                continue
            group: dict = {}
            for index, name in sorted(by_table[table], key=lambda t: int(t[0])):
                multiplier, offset = dnp3_scaling(name) if scaling == 'transform' else (1.0, 0.0)
                group[index] = f'transform[{name}]({_dnp3_functions(multiplier, offset, inverse=False)})'
                from_protocol[name] = f'transform[{table}, {index}]({_dnp3_functions(multiplier, offset, inverse=True)})'
            to_protocol[table] = group
        if fmt == '1815.2.outputs' and any(by_table.get(t) for t in tables):
            # Curve writes arrive as ordered batches; keep them ordered, as flat points, for the driver.
            batch: dict = {'#': 'transform[sequence]()'}
            for table in tables:
                if not by_table.get(table):
                    continue
                factors = []
                if scaling == 'transform':
                    for index, name in by_table[table]:
                        multiplier, offset = dnp3_scaling(name)
                        if multiplier != 1:
                            factors.append(f"'{index}:{1 / multiplier!r}'")
                functions = ([f'scale_fields({", ".join(factors)})'] if factors else []) + [f"prefix_keys('{table}_')"]
                batch[f'*{table}'] = f'transform[#, {table}]({", ".join(functions)})'
            from_protocol['sequence[#]'] = batch
        if to_protocol:
            definitions.append({'input_format': device_format, 'output_format': fmt, 'pattern': to_protocol})
            # Inputs (AI, BI, counters) are read-only on the device, so nothing is written back to them; writes
            # reach the device only through the outputs format, which also carries the ordered curve batches.
            if fmt == '1815.2.outputs':
                definitions.append({'input_format': fmt, 'output_format': device_format, 'pattern': from_protocol})
    return DeviceTransforms(definitions, scaling, [])


# ============================================================================================ shared
def resource_mappings(device_format: str, device_topic: str, uai: list[str], alias_formats: dict[str, str]) -> list[dict]:
    """A canonical resource for the device plus one alias per requested format, for the service's ``mappings``."""
    mappings = [{'uai': uai, 'resource_type': 'canonical',
                 'resource': {'data_format': device_format, 'owner': 'platform.driver',
                              'publication_topic': f'{device_topic}/all', 'rpc_topic': device_topic}}]
    for alias, fmt in alias_formats.items():
        mappings.append({'uai': uai[:-1] + [alias], 'resource_type': 'alias',
                         'resource': {'data_format': fmt, 'owner': 'platform.driver', 'references': uai}})
    return mappings
