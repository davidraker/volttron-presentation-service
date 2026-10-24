"""Sample messages for the bundled formats, typed from the model packages, for the graph invariant tests.

A sample carries one distinct value per leaf of the format's field universe so that, after a chain runs, every
output leaf can be traced back to the source field it came from. Booleans, enumerations and strings take values
of their own type (read from the pydantic models) so that transforms which cast or compare do not fail on a
number standing in for a flag. Formats without a model (the ``61850`` hub, ``1547``) are sampled by running every
model-typed neighbour's direct transform into them and merging the results.
"""
from __future__ import annotations

import enum
import typing

from interoperability.field_universe import _group_type
from interoperability.models.ieee2030_5 import sep
from interoperability.models.openfmb import PROFILES, OpenFMBMessage
from interoperability.models.sunspec import MODEL_REGISTRY, SunSpecGroup
from interoperability.transform_parser import WILDCARD

MODEL_TYPED = ('sunspec', '2030.5', '1815.2.inputs', '1815.2.outputs',
               'openfmb.ess', 'openfmb.solar', 'openfmb.ess.reading', 'openfmb.ess.status', 'openfmb.ess.capability',
               'openfmb.ess.control', 'openfmb.solar.reading', 'openfmb.solar.status', 'openfmb.solar.capability',
               'openfmb.solar.control')


def _scalar(annotation):
    """The scalar type of a pydantic field annotation (``bool``, ``int``, ``float``, ``str``, an Enum class) or None."""
    origin = typing.get_origin(annotation)
    if origin is list:
        return _scalar(typing.get_args(annotation)[0])
    if origin is typing.Union or (origin is not None and origin.__class__.__name__ == 'UnionType') \
            or type(annotation).__name__ == 'UnionType':
        for arg in typing.get_args(annotation):
            if arg is type(None):
                continue
            found = _scalar(arg)
            if found is not None:
                return found
        return None
    if isinstance(annotation, type):
        if issubclass(annotation, enum.Enum):
            return annotation
        if annotation in (bool, int, float, str):
            return annotation
    return None


class Sampler:
    """Builds one sample per format; every numeric leaf gets a distinct value and ``origin`` maps values back to
    the (format, path) they were created for."""

    def __init__(self):
        self.counter = 1000
        self.origin: dict[float, tuple[str, tuple]] = {}

    # Enumerations stand for a state; the sample is the "enabled" state where one exists, since the hub's implied
    # enable convention (a present setpoint means the mode is on) would otherwise disagree with a copied flag.
    ENABLED_NAMES = ('ENABLED', 'ENABLE', 'ON', 'TRUE', 'YES', 'ACTIVE')
    # Point counts of repeating groups match the one entry the sample lists hold.
    COUNT_NAMES = ('ActPt', 'NPt', 'numPts', 'NumPts', 'N', 'NCrv', 'NPts')

    def value(self, data_format: str, path: tuple, scalar):
        if scalar is bool:
            return True
        if isinstance(scalar, type) and issubclass(scalar, enum.Enum):
            for member in scalar:
                if member.name.upper() in self.ENABLED_NAMES:
                    return member.value
            return next(iter(scalar)).value
        if scalar is str:
            return f'{data_format}:{".".join(map(str, path))}'
        if str(path[-1]) in self.COUNT_NAMES:
            return 1
        self.counter += 1
        value = float(self.counter)
        self.origin[value] = (data_format, path)
        return value

    # -- typed leaf enumeration per format --

    def _model_leaves(self, cls, base, prefix: tuple = (), seen: frozenset = frozenset()):
        for name, info in cls.model_fields.items():
            wire = info.alias or name
            group = _group_type(info.annotation, base)
            if group:
                sub, is_list = group
                if sub in seen:
                    continue
                yield from self._model_leaves(sub, base, prefix + ((wire, WILDCARD) if is_list else (wire,)), seen | {cls})
            else:
                yield prefix + (wire,), _scalar(info.annotation)

    def leaves(self, data_format: str, universe: set[tuple]):
        """(path, scalar type) for every leaf of ``data_format``'s universe."""
        if data_format == 'sunspec':
            for model_id, cls in MODEL_REGISTRY.items():
                for path, scalar in self._model_leaves(cls, SunSpecGroup):
                    yield (str(model_id),) + path, scalar
        elif data_format.startswith('openfmb'):
            prefix = {'openfmb.ess': 'ESS', 'openfmb.solar': 'Solar'}.get(data_format.rsplit('.', 1)[0] if data_format.count('.') == 2 else data_format, '')
            suffix = 'Profile' if data_format.count('.') < 2 else data_format.rsplit('.', 1)[1].capitalize() + 'Profile'
            for name, cls in PROFILES.items():
                if name.startswith(prefix) and name.endswith(suffix):
                    yield from self._model_leaves(cls, OpenFMBMessage)
        elif data_format in ('1815.2.inputs', '1815.2.outputs'):
            for path in universe:
                yield path, (bool if path[0] in ('BI', 'BO') else float)
        elif data_format == '2030.5':
            for path in universe:
                yield path, self._sep2_type(path)
        else:
            for path in universe:
                yield path, float

    @staticmethod
    def _sep2_type(path: tuple):
        """Leaf type of a path in the service's flat 2030.5 convention (see field_universe.ieee2030_5_fields)."""
        resource, rest = path[0], path[1:]
        if resource == 'MirrorMeterReading':
            return float
        if resource == 'DERControlList':
            rest = rest[1:]                       # the wildcard
            if rest and rest[0] == 'interval':
                return int
            resource, rest = rest[0], rest[1:]
        if resource == 'DERControl':
            cls = sep.DERControlBase
        elif resource == 'DERCurve':
            rest = rest[1:]                       # the curve type
            if rest and rest[0] == 'CurveData':
                cls, rest = sep.CurveData, rest[2:]
            else:
                cls = sep.DERCurve
        else:
            cls = getattr(sep, resource, None)
        for segment in rest:
            if cls is None or segment == WILDCARD:
                return float
            info = cls.model_fields.get(segment)
            if info is None:
                return float
            group = _group_type(info.annotation, sep.SepBase)
            if group:
                cls = group[0]
            else:
                return _scalar(info.annotation) or float
        return float

    # -- assembly --

    def build(self, data_format: str, universe: set[tuple]) -> dict:
        message: dict = {}
        # Longest paths first so that a path that is a prefix of another cannot be both a leaf and a group.
        for path, scalar in sorted(self.leaves(data_format, universe), key=lambda item: (-len(item[0]), item[0])):
            node = message
            for index, segment in enumerate(path):
                if segment == WILDCARD:
                    continue
                if not isinstance(node, dict):
                    break
                if index == len(path) - 1:
                    node.setdefault(segment, self.value(data_format, path, scalar))
                else:
                    following = path[index + 1]
                    node = node.setdefault(segment, [{}] if following == WILDCARD else {})
                    if isinstance(node, list):
                        node = node[0]
        return message


def merge(into: dict, other: dict) -> dict:
    """Deep merge, first value wins."""
    for key, value in other.items():
        if isinstance(value, dict) and isinstance(into.get(key), dict):
            merge(into[key], value)
        else:
            into.setdefault(key, value)
    return into


def leaves(data, prefix: tuple = ()):
    if isinstance(data, dict):
        for key, value in data.items():
            yield from leaves(value, prefix + (key,))
    elif isinstance(data, list):
        for index, value in enumerate(data):
            yield from leaves(value, prefix + (index,))
    else:
        yield prefix, data
