"""Shared base types for the IEEE 1815.2 (MESA-DER / DNP3) pydantic models.

IEEE 1815.2 describes a DER as a flat list of DNP3 points: analog inputs (AI), analog
outputs (AO), binary inputs (BI), binary outputs (BO) and counters (CTR), each identified
by a point index. The standard groups those points by the function they support
(nameplate, monitoring, volt-var, scheduling, ...). The generated modules mirror that:

* :mod:`.points` holds one ``IntEnum`` per point type (``AI.DGEN_WMaxRtg == 4``) and a
  :class:`PointDefinition` registry with the metadata of every point.
* :mod:`.profiles` holds one pydantic class per function group (``Nameplate``, ``VoltVar``
  ...), each split into ``AI`` / ``AO`` / ``BI`` / ``BO`` / ``CTR`` sub-models whose fields
  are the individual points, and template classes for repeated equipment blocks (meters,
  inverters, batteries, DER units).
* :class:`PointDatabase` is the flat ``{"AI": {index: value}, ...}`` view used by the
  ``1815.2.inputs`` / ``1815.2.outputs`` transform formats.
"""
from __future__ import annotations

import enum
from typing import Any, ClassVar, Iterator

from pydantic import BaseModel, ConfigDict, Field


class PointType(str, enum.Enum):
    AI = 'AI'
    AO = 'AO'
    BI = 'BI'
    BO = 'BO'
    CTR = 'CTR'


class EventClass(str, enum.Enum):
    NONE = 'None'
    CLASS1 = 'Class1'
    CLASS2 = 'Class2'
    CLASS3 = 'Class3'


class PointDefinition(BaseModel):
    """Metadata for one DNP3 point as listed in the IEEE 1815.2 point list."""

    model_config = ConfigDict(frozen=True)

    point_type: PointType
    index: int
    uid: str = Field(description='IEC 61850-7-420 style identifier, e.g. DGEN.WMaxRtg')
    name: str = Field(description='Description text from the point list')
    purpose: str = Field(default='', description='Function group the point belongs to')
    mandatory_1815: bool = False
    mandatory_1547: bool = False
    event_class: EventClass | None = None
    units: str | None = None
    minimum: float | None = None
    maximum: float | None = None
    multiplier: float | None = None
    offset: float | None = None
    default: float | None = Field(default=None, description='Default value listed in the profile')
    state_0: str | None = Field(default=None, description='Meaning of a binary 0')
    state_1: str | None = Field(default=None, description='Meaning of a binary 1')
    associated: str | None = Field(default=None, description='Paired point, e.g. the AI reflecting an AO')
    counter_event_class: EventClass | None = None
    frozen_counter_exists: bool | None = None
    frozen_counter_event_class: EventClass | None = None


class PointDatabase(BaseModel):
    """Flat point-index view of an outstation: ``{"AI": {4: 5000.0}, "BI": {0: False}, ...}``.

    Keys are point indexes (accepted as ``int`` or numeric ``str``). ``inputs()`` and
    ``outputs()`` give the subsets that the ``1815.2.inputs`` and ``1815.2.outputs``
    transform formats expect.
    """

    model_config = ConfigDict(protected_namespaces=(), validate_assignment=True)

    AI: dict[int, float | None] = Field(default_factory=dict)
    AO: dict[int, float | None] = Field(default_factory=dict)
    BI: dict[int, bool | None] = Field(default_factory=dict)
    BO: dict[int, bool | None] = Field(default_factory=dict)
    CTR: dict[int, int | None] = Field(default_factory=dict)

    def table(self, point_type: PointType | str) -> dict[int, Any]:
        return getattr(self, PointType(point_type).value)

    def set(self, point_type: PointType | str, index: int, value: Any) -> None:
        self.table(point_type)[int(index)] = value

    def get(self, point_type: PointType | str, index: int, default: Any = None) -> Any:
        return self.table(point_type).get(int(index), default)

    def merge(self, other: PointDatabase) -> PointDatabase:
        """Return a new database with ``other``'s points layered over this one."""
        merged = self.model_copy(deep=True)
        for pt in PointType:
            merged.table(pt).update(other.table(pt))
        return merged

    def inputs(self) -> dict[str, dict[int, Any]]:
        """Payload for the ``1815.2.inputs`` format (AI, BI and counters)."""
        return {'AI': dict(self.AI), 'BI': dict(self.BI), 'CTR': dict(self.CTR)}

    def outputs(self) -> dict[str, dict[int, Any]]:
        """Payload for the ``1815.2.outputs`` format (AO and BO)."""
        return {'AO': dict(self.AO), 'BO': dict(self.BO)}

    def __len__(self) -> int:
        return sum(len(self.table(pt)) for pt in PointType)


class PointGroup(BaseModel):
    """Base for generated classes whose fields are individual DNP3 points of one type.

    Each field records its point in ``json_schema_extra``: ``point_type`` plus either
    ``index`` (a fixed point), ``indexes`` (an array point such as curve x-values, one
    index per element) or ``offset`` (a point inside a repeated equipment block, resolved
    against ``START`` / ``POINTS_PER`` and the instance number).
    """

    model_config = ConfigDict(protected_namespaces=(), validate_assignment=True, populate_by_name=True)

    POINT_TYPE: ClassVar[PointType] = PointType.AI
    #: First index of instance 1 for repeated equipment blocks; ``None`` for fixed groups.
    START: ClassVar[int | None] = None
    #: Number of points per instance for repeated equipment blocks.
    POINTS_PER: ClassVar[int | None] = None

    @classmethod
    def point_metadata(cls, name: str) -> dict[str, Any]:
        extra = cls.model_fields[name].json_schema_extra
        return dict(extra) if isinstance(extra, dict) else {}

    @classmethod
    def _base(cls, instance: int | None) -> int:
        if cls.START is None:
            return 0
        n = 1 if instance is None else int(instance)
        if n < 1:
            raise ValueError('instance numbers start at 1')
        return cls.START + (n - 1) * (cls.POINTS_PER or 0)

    @classmethod
    def iter_points(cls, instance: int | None = None) -> Iterator[tuple[str, list[int]]]:
        """Yield ``(field_name, [point indexes])`` for every field of this group."""
        base = cls._base(instance)
        for name in cls.model_fields:
            meta = cls.point_metadata(name)
            if 'index' in meta:
                yield name, [meta['index']]
            elif 'indexes' in meta:
                yield name, list(meta['indexes'])
            elif 'offset' in meta:
                yield name, [base + meta['offset']]
            elif 'offsets' in meta:
                yield name, [base + o for o in meta['offsets']]

    @classmethod
    def index_of(cls, name: str, instance: int | None = None) -> int | list[int]:
        """Point index of field ``name`` (a list for array fields)."""
        meta = cls.point_metadata(name)
        for field_name, indexes in cls.iter_points(instance):
            if field_name == name:
                return indexes if ('indexes' in meta or 'offsets' in meta) else indexes[0]
        raise KeyError(name)

    def to_points(self, instance: int | None = None, database: PointDatabase | None = None) -> PointDatabase:
        """Write the non-``None`` fields of this group into a :class:`PointDatabase`."""
        db = database if database is not None else PointDatabase()
        table = db.table(self.POINT_TYPE)
        for name, indexes in self.iter_points(instance):
            value = getattr(self, name)
            if value is None:
                continue
            if isinstance(value, (list, tuple)):
                for idx, item in zip(indexes, value):
                    if item is not None:
                        table[idx] = _plain(item)
            else:
                table[indexes[0]] = _plain(value)
        return db

    @classmethod
    def from_points(cls, database: PointDatabase | dict[str, Any], instance: int | None = None):
        """Build this group from the points present in ``database``; absent points stay ``None``."""
        db = database if isinstance(database, PointDatabase) else PointDatabase.model_validate(database)
        table = db.table(cls.POINT_TYPE)
        values: dict[str, Any] = {}
        for name, indexes in cls.iter_points(instance):
            meta = cls.point_metadata(name)
            if 'indexes' in meta or 'offsets' in meta:
                items = [table.get(i) for i in indexes]
                while items and items[-1] is None:
                    items.pop()
                if items:
                    values[name] = items
            elif indexes[0] in table:
                values[name] = table[indexes[0]]
        return cls.model_validate(values)


class Profile(BaseModel):
    """Base for generated function-group classes holding one :class:`PointGroup` per point type."""

    model_config = ConfigDict(protected_namespaces=(), validate_assignment=True)

    #: Purpose label from the IEEE 1815.2 point list, e.g. ``'Volt-Var'``.
    PURPOSE: ClassVar[str] = ''
    START: ClassVar[int | None] = None
    POINTS_PER: ClassVar[int | None] = None

    def groups(self) -> Iterator[PointGroup]:
        for name in type(self).model_fields:
            value = getattr(self, name)
            if isinstance(value, PointGroup):
                yield value

    def to_points(self, instance: int | None = None, database: PointDatabase | None = None) -> PointDatabase:
        db = database if database is not None else PointDatabase()
        for group in self.groups():
            group.to_points(instance, db)
        return db

    @classmethod
    def from_points(cls, database: PointDatabase | dict[str, Any], instance: int | None = None):
        db = database if isinstance(database, PointDatabase) else PointDatabase.model_validate(database)
        values: dict[str, Any] = {}
        for name, info in cls.model_fields.items():
            group_cls = _point_group_class(info.annotation)
            if group_cls is None:
                continue
            group = group_cls.from_points(db, instance)
            if any(getattr(group, f) is not None for f in group_cls.model_fields):
                values[name] = group
        return cls.model_validate(values)


def _plain(value: Any) -> Any:
    if isinstance(value, enum.Enum):
        return value.value
    return value


def _point_group_class(annotation: Any) -> type[PointGroup] | None:
    import types, typing
    if isinstance(annotation, type) and issubclass(annotation, PointGroup):
        return annotation
    if isinstance(annotation, (types.UnionType, typing._UnionGenericAlias)):  # type: ignore[attr-defined]
        for arg in typing.get_args(annotation):
            found = _point_group_class(arg)
            if found is not None:
                return found
    return None
