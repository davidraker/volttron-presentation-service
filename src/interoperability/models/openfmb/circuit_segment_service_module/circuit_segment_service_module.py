from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

class CircuitSegmentControl(BaseModel):
    circuitSegmentControl: CircuitSegmentControl | None = Field(default=None)
    circuitSegmentControlProfile: CircuitSegmentControl | None = Field(default=None)
    reserveRequestProfile: ReserveRequestProfile | None = Field(default=None)


class CircuitSegmentControlDCSC(BaseModel):
    circuitSegmentControl: CircuitSegmentControl | None = Field(default=None)
    circuitSegmentControlProfile: CircuitSegmentControlProfile | None = Field(default=None)


class CircuitSegmentControlProfile(BaseModel):
    circuitSegmentControl: CircuitSegmentControl | None = Field(default=None)
    circuitSegmentControlProfile: CircuitSegmentControl | None = Field(default=None)
    reserveRequestProfile: ReserveRequestProfile | None = Field(default=None)


class CircuitSegmentEvent(BaseModel):
    circuitSegmentEvent: CircuitSegmentEvent | None = Field(default=None)
    circuitSegmentEventProfile: CircuitSegmentEvent | None = Field(default=None)
    reserveRequestProfile: ReserveRequestProfile | None = Field(default=None)


class CircuitSegmentEventDCSC(BaseModel):
    circuitSegmentEvent: CircuitSegmentEvent | None = Field(default=None)
    circuitSegmentEventProfile: CircuitSegmentEventProfile | None = Field(default=None)


class CircuitSegmentEventProfile(BaseModel):
    circuitSegmentEvent: CircuitSegmentEvent | None = Field(default=None)
    circuitSegmentEventProfile: CircuitSegmentEvent | None = Field(default=None)
    reserveRequestProfile: ReserveRequestProfile | None = Field(default=None)


class CircuitSegmentServiceMode(Enum):
    UNDEFINED = "UNDEFINED"
    OTHER = "other"


class CircuitSegmentStatus(BaseModel):
    circuitSegmentStatus: CircuitSegmentStatus | None = Field(default=None)
    circuitSegmentStatusProfile: CircuitSegmentStatus | None = Field(default=None)
    reserveRequestProfile: ReserveRequestProfile | None = Field(default=None)


class CircuitSegmentStatusDCSC(BaseModel):
    circuitSegmentStatus: CircuitSegmentStatus | None = Field(default=None)
    circuitSegmentStatusProfile: CircuitSegmentStatusProfile | None = Field(default=None)


class CircuitSegmentStatusProfile(BaseModel):
    circuitSegmentStatus: CircuitSegmentStatus | None = Field(default=None)
    circuitSegmentStatusProfile: CircuitSegmentStatus | None = Field(default=None)
    reserveRequestProfile: ReserveRequestProfile | None = Field(default=None)


class ENG_CircuitSegmentServiceMode(Enum):
    UNDEFINED = "UNDEFINED"
    OTHER = "other"


from ..reserve_module.reserve_module import ReserveRequestProfile
