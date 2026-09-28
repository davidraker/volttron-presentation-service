"""Field universes: every field a format can carry, as normalized paths.

The transform registry needs to know how much of a format a transform covers. Where a model
package exists, the universe is derived from it; formats without models can declare their
fields in configuration, and anything else falls back to the fields the registered transforms
mention. Providers are callables ``(format_name) -> set[path] | None`` returning None for
formats they do not know; the registry consults them in order.
"""
import typing

from .transform_parser import WILDCARD


def _group_type(annotation, base):
    """(group class, is_list) if a pydantic annotation holds a subclass of ``base``, else None."""
    origin = typing.get_origin(annotation)
    if origin is list:
        inner = _group_type(typing.get_args(annotation)[0], base)
        return (inner[0], True) if inner else None
    if origin is typing.Union or (origin is not None and origin.__class__.__name__ == 'UnionType') \
            or type(annotation).__name__ == 'UnionType':
        for arg in typing.get_args(annotation):
            found = _group_type(arg, base)
            if found:
                return found
        return None
    if isinstance(annotation, type) and issubclass(annotation, base):
        return (annotation, False)
    return None


def _group_fields(cls, prefix: tuple, base=None, seen: frozenset = frozenset()):
    """Leaf field paths of a pydantic model, descending into nested models of ``base`` (lists as wildcards).
    Field aliases are used where present, since they are the wire names."""
    base = base or cls.__mro__[-2]
    for name, info in cls.model_fields.items():
        wire = info.alias or name
        group = _group_type(info.annotation, base)
        if group:
            sub, is_list = group
            if sub in seen:
                continue
            yield from _group_fields(sub, prefix + ((wire, WILDCARD) if is_list else (wire,)), base, seen | {cls})
        else:
            yield prefix + (wire,)


def sunspec_fields() -> set[tuple]:
    """Every point of every generated SunSpec model, keyed by model number; repeating groups as wildcards."""
    from .models.sunspec import MODEL_REGISTRY, SunSpecGroup
    return {(str(model_id),) + field for model_id, cls in MODEL_REGISTRY.items() for field in _group_fields(cls, (), SunSpecGroup)}


def openfmb_fields(prefix: str = '') -> set[tuple]:
    """Every leaf of every OpenFMB profile whose name starts with ``prefix`` (``ESS``, ``Solar``, or all), as
    published in protobuf JSON form; repeated fields as wildcards. Profiles do not share top-level names, so
    their paths are simply unioned."""
    from .models.openfmb import PROFILES, OpenFMBMessage
    universe = set()
    for name, cls in PROFILES.items():
        if name.startswith(prefix):
            universe |= set(_group_fields(cls, (), OpenFMBMessage))
    return universe


def ieee1815_2_fields(tables: tuple[str, ...]) -> set[tuple]:
    """Every defined point index of the given IEEE 1815.2 tables (``AI``, ``AO``, ``BI``, ``BO``, ``CTR``)."""
    from .models.ieee1815_2 import POINTS, PointType
    return {(table, str(index)) for table in tables for index in POINTS[PointType(table)]}


# The service's 2030.5 convention: resource name, then attribute; curves under DERCurve.<curveType>; readings
# under MirrorMeterReading.<unit> with voltages by phase (see the README's bundled-transform conventions).
_SEP2_RESOURCES = ('DERCapability', 'DERSettings', 'DERStatus', 'DefaultDERControl', 'DeviceInformation')
_SEP2_CURVE_TYPES = ('opModVoltVar', 'opModWattVar', 'opModVoltWatt', 'opModHVRTMustTrip', 'opModLVRTMustTrip',
                     'opModHVRTMomentaryCessation', 'opModLVRTMomentaryCessation', 'opModHFRTMustTrip', 'opModLFRTMustTrip',
                     'opModFreqWatt')
_SEP2_READINGS = ('W', 'var', 'VA', 'Hz', 'A', 'PF')
_SEP2_PHASES = ('PhaseA', 'PhaseB', 'PhaseC', 'PhaseAB', 'PhaseBC', 'PhaseCA')


def ieee2030_5_fields() -> set[tuple]:
    """Every attribute path of the 2030.5 convention, from the generated sep models."""
    from .models.ieee2030_5 import sep
    skip = {'href', 'mRID', 'description', 'version', 'creationTime', 'replyTo', 'responseRequired', 'subscribable'}

    def attributes(cls):
        return [n for n in cls.model_fields if n not in skip]

    def scalar_or_group(cls, prefix):
        for name in attributes(cls):
            info = cls.model_fields[name]
            sub = _group_type(info.annotation, sep.SepBase)
            # Quantities with a multiplier (FixedPointType and friends) are single values in the convention,
            # since multipliers are not applied; real sub-structures (displacement/excitation, droop settings)
            # keep their attributes.
            if sub and not sub[1] and sub[0].__name__ not in ('Link', 'ListLink') \
                    and not set(attributes(sub[0])) <= {'value', 'multiplier'}:
                for inner in attributes(sub[0]):
                    if inner != 'multiplier':
                        yield prefix + (name, inner)
            else:
                yield prefix + (name,)

    universe = set()
    for resource in _SEP2_RESOURCES:
        universe |= set(scalar_or_group(getattr(sep, resource), (resource,)))
    universe |= set(scalar_or_group(sep.DERControlBase, ('DERControl',)))
    universe |= set(scalar_or_group(sep.DERControlBase, ('DERControlList', WILDCARD, 'DERControl')))
    universe |= {('DERControlList', WILDCARD, 'interval', 'start'), ('DERControlList', WILDCARD, 'interval', 'duration')}
    for curve in _SEP2_CURVE_TYPES:
        for prefix in ((('DERCurve', curve),), (('DERControlList', WILDCARD, 'DERCurve', curve),)):
            base = prefix[0]
            universe |= {base + (a,) for a in attributes(sep.DERCurve) if a != 'CurveData'}
            universe |= {base + ('CurveData', WILDCARD, a) for a in attributes(sep.CurveData)}
    for reading in _SEP2_READINGS:
        universe.add(('MirrorMeterReading', reading))
    universe |= {('MirrorMeterReading', 'V', phase) for phase in _SEP2_PHASES}
    return universe


_MODEL_FORMATS = {
    '2030.5': ieee2030_5_fields,
    'sunspec': sunspec_fields,
    'openfmb': openfmb_fields,
    'openfmb.ess': lambda: openfmb_fields('ESS'),
    'openfmb.solar': lambda: openfmb_fields('Solar'),
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
