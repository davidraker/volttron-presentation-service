"""Shared base types for the generated SunSpec Modbus pydantic models.

The SunSpec information model is organised as numbered *models* (1, 701, 702, ...).
Each model is a group of *points* (registers) and optional nested, possibly repeating,
sub-groups. The generated classes in :mod:`.models` mirror that structure one-to-one; this
module holds the pieces they share.
"""
from __future__ import annotations

import enum
from typing import Any, ClassVar

from pydantic import BaseModel, ConfigDict, Field, RootModel, SerializeAsAny, model_validator

#: SunSpec point ``type`` values that carry an integer register value.
INTEGER_TYPES = frozenset({
    'int16', 'int32', 'int64', 'uint16', 'uint32', 'uint64', 'acc16', 'acc32', 'acc64',
    'raw16', 'pad', 'count', 'sunssf',
})
#: SunSpec point ``type`` values that carry a floating point value.
FLOAT_TYPES = frozenset({'float32', 'float64'})
#: SunSpec point ``type`` values that carry a string value.
STRING_TYPES = frozenset({'string', 'ipaddr', 'ipv6addr', 'eui48'})
#: SunSpec point ``type`` values whose symbols form an enumeration.
ENUM_TYPES = frozenset({'enum16', 'enum32'})
#: SunSpec point ``type`` values whose symbols are bit positions.
BITFIELD_TYPES = frozenset({'bitfield16', 'bitfield32', 'bitfield64'})


class SunSpecEnum(enum.IntEnum):
    """Base class for enumerated (``enum16`` / ``enum32``) point values."""


class SunSpecFlags(enum.IntFlag):
    """Base class for bitfield point values. Member values are ``1 << bit``."""


class SunSpecGroup(BaseModel):
    """A SunSpec group: a set of points plus optional nested groups.

    Every field carries SunSpec metadata in ``json_schema_extra``: the register ``type``,
    ``size``, ``units``, ``sf`` (scale factor point name or fixed exponent), ``access``,
    ``mandatory`` and ``static`` flags, exactly as they appear in the model definition.
    """

    model_config = ConfigDict(protected_namespaces=(), validate_assignment=True, populate_by_name=True)

    #: SunSpec group name (``name`` in the model definition).
    GROUP_NAME: ClassVar[str] = ''

    @classmethod
    def point_metadata(cls, name: str) -> dict[str, Any]:
        """Return the SunSpec metadata recorded for point ``name``."""
        info = cls.model_fields[name]
        extra = info.json_schema_extra
        return dict(extra) if isinstance(extra, dict) else {}

    def scaled_value(self, name: str, scale_factors: SunSpecGroup | None = None) -> float | None:
        """Return the value of point ``name`` with its SunSpec scale factor applied.

        The scale factor is read from the ``sf`` metadata of the point. A string ``sf``
        names a ``sunssf`` point in this group, or in ``scale_factors`` when the scale
        factor lives in an enclosing group (SunSpec allows repeating groups to reference
        scale factors of their parent). An integer ``sf`` is a fixed exponent.
        """
        value = getattr(self, name)
        if value is None:
            return None
        sf = self.point_metadata(name).get('sf')
        if sf is None:
            return float(value)
        if isinstance(sf, int):
            exponent = sf
        else:
            owner = self if sf in type(self).model_fields else scale_factors
            if owner is None:
                raise KeyError(f'Scale factor point {sf!r} is not in {type(self).__name__}; pass scale_factors=')
            exponent = getattr(owner, sf)
            if exponent is None:
                return float(value)
        return float(value) * 10 ** exponent


class SunSpecModel(SunSpecGroup):
    """A top-level SunSpec model (the group that starts with the ``ID`` and ``L`` points)."""

    #: SunSpec model identifier, for example ``701``.
    MODEL_ID: ClassVar[int] = 0
    #: Human readable label from the model definition.
    MODEL_LABEL: ClassVar[str] = ''

    ID: int | None = Field(default=None, description='Model ID')
    L: int | None = Field(default=None, description='Model length in registers')


#: Registry of every generated model class keyed by SunSpec model id. Filled in by the
#: generated ``models`` package on import.
MODEL_REGISTRY: dict[int, type[SunSpecModel]] = {}


def register_model(cls: type[SunSpecModel]) -> type[SunSpecModel]:
    """Class decorator that adds ``cls`` to :data:`MODEL_REGISTRY`."""
    MODEL_REGISTRY[cls.MODEL_ID] = cls
    return cls


def model_class(model_id: int | str) -> type[SunSpecModel]:
    """Return the generated class for SunSpec model ``model_id``."""
    try:
        return MODEL_REGISTRY[int(model_id)]
    except (KeyError, ValueError) as e:
        raise KeyError(f'No SunSpec model class registered for id {model_id!r}') from e


class SunSpecDevice(RootModel[dict[int, SerializeAsAny[SunSpecModel]]]):
    """A SunSpec device: the set of models it exposes, keyed by model id.

    This is the shape the ``sunspec`` transform format uses (``{"701": {"W": 1000, ...}}``).
    Each value is validated into the concrete model class from :data:`MODEL_REGISTRY`,
    falling back to a plain :class:`SunSpecModel` for unknown (vendor) model ids.
    Repeated models (for example several model 160 blocks) are not representable in a
    single mapping; use a list of devices for that case.
    """

    @model_validator(mode='before')
    @classmethod
    def _dispatch_models(cls, data: Any) -> Any:
        if isinstance(data, SunSpecDevice):
            return data.root
        if not isinstance(data, dict):
            return data
        out: dict[int, SunSpecModel] = {}
        for key, value in data.items():
            model_id = int(key)
            if isinstance(value, SunSpecModel):
                out[model_id] = value
                continue
            target = MODEL_REGISTRY.get(model_id, SunSpecModel)
            payload = dict(value) if isinstance(value, dict) else value
            if isinstance(payload, dict):
                payload.setdefault('ID', model_id)
            out[model_id] = target.model_validate(payload)
        return out

    def __getitem__(self, model_id: int | str) -> SunSpecModel:
        return self.root[int(model_id)]

    def __contains__(self, model_id: object) -> bool:
        try:
            return int(model_id) in self.root  # type: ignore[call-overload]
        except (TypeError, ValueError):
            return False

    def get(self, model_id: int | str, default: SunSpecModel | None = None) -> SunSpecModel | None:
        return self.root.get(int(model_id), default)

    def model_ids(self) -> list[int]:
        return list(self.root)

    def add(self, model: SunSpecModel) -> None:
        self.root[model.MODEL_ID if model.ID is None else model.ID] = model
