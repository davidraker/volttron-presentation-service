"""Field universes: every field a format can carry, as normalized paths.

The transform registry needs to know how much of a format a transform covers. Where a model
package exists, the universe is derived from it; formats without models can declare their
fields in configuration, and anything else falls back to the fields the registered transforms
mention. Providers are callables ``(format_name) -> set[path] | None`` returning None for
formats they do not know; the registry consults them in order.
"""
import typing

from .transform_parser import WILDCARD


def _group_type(annotation):
    """(group class, is_list) if a pydantic annotation holds a SunSpec group, else None."""
    from .models.sunspec import SunSpecGroup
    origin = typing.get_origin(annotation)
    if origin is list:
        inner = _group_type(typing.get_args(annotation)[0])
        return (inner[0], True) if inner else None
    if origin is typing.Union or (origin is not None and origin.__class__.__name__ == 'UnionType') \
            or type(annotation).__name__ == 'UnionType':
        for arg in typing.get_args(annotation):
            found = _group_type(arg)
            if found:
                return found
        return None
    if isinstance(annotation, type) and issubclass(annotation, SunSpecGroup):
        return (annotation, False)
    return None


def _group_fields(cls, prefix: tuple):
    for name, info in cls.model_fields.items():
        group = _group_type(info.annotation)
        if group:
            sub, is_list = group
            yield from _group_fields(sub, prefix + ((name, WILDCARD) if is_list else (name,)))
        else:
            yield prefix + (name,)


def sunspec_fields() -> set[tuple]:
    """Every point of every generated SunSpec model, keyed by model number; repeating groups as wildcards."""
    from .models.sunspec import MODEL_REGISTRY
    return {(str(model_id),) + field for model_id, cls in MODEL_REGISTRY.items() for field in _group_fields(cls, ())}


def ieee1815_2_fields(tables: tuple[str, ...]) -> set[tuple]:
    """Every defined point index of the given IEEE 1815.2 tables (``AI``, ``AO``, ``BI``, ``BO``, ``CTR``)."""
    from .models.ieee1815_2 import POINTS, PointType
    return {(table, str(index)) for table in tables for index in POINTS[PointType(table)]}


_MODEL_FORMATS = {
    'sunspec': sunspec_fields,
    '1815.2.inputs': lambda: ieee1815_2_fields(('AI', 'BI', 'CTR')),
    '1815.2.outputs': lambda: ieee1815_2_fields(('AO', 'BO')),
}
_cache: dict[str, set[tuple]] = {}


def models_provider(data_format: str) -> set[tuple] | None:
    """Field universe provider backed by the bundled model packages. Extend ``_MODEL_FORMATS`` as models for
    further formats (61850, 1547, ...) are added."""
    builder = _MODEL_FORMATS.get(data_format)
    if builder is None:
        return None
    if data_format not in _cache:
        _cache[data_format] = builder()
    return _cache[data_format]


def parse_declared_fields(fields) -> set[tuple]:
    """Fields declared in configuration: dotted strings (``705.Crv.*.Pt.*.V``) or lists of segments."""
    universe = set()
    for field in fields:
        if isinstance(field, str):
            universe.add(tuple(field.split('.')))
        else:
            universe.add(tuple(str(seg) for seg in field))
    return universe
