from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

class AllocatedMargin(BaseModel):
    allocatedMargin: ReserveMargin | None = Field(default=None)
    reserveAvailabilityProfile: ReserveAvailability | None = Field(default=None)


class ReserveAvailability(BaseModel):
    allocatedMargin: ReserveMargin | None = Field(default=None)
    reserveAvailability: ReserveMargin | None = Field(default=None)
    reserveAvailabilityProfile: ReserveAvailability | None = Field(default=None)
    reserveRequestProfile: ReserveRequestProfile | None = Field(default=None)
    resourceDiscreteControlProfile: ResourceDiscreteControlProfile | None = Field(default=None)


class ReserveAvailabilityProfile(BaseModel):
    allocatedMargin: ReserveMargin | None = Field(default=None)
    reserveAvailability: ReserveMargin | None = Field(default=None)
    reserveAvailabilityProfile: ReserveAvailability | None = Field(default=None)
    reserveRequestProfile: ReserveRequestProfile | None = Field(default=None)
    resourceDiscreteControlProfile: ResourceDiscreteControlProfile | None = Field(default=None)


class ReserveMargin(BaseModel):
    allocatedMargin: ReserveMargin | None = Field(default=None)
    reserveAvailability: ReserveMargin | None = Field(default=None)
    reserveAvailabilityProfile: ReserveAvailabilityProfile | None = Field(default=None)
    reserveRequestProfile: ReserveRequestProfile | None = Field(default=None)


class ReserveRequest(BaseModel):
    allocatedMargin: AllocatedMargin | None = Field(default=None)
    reserveAvailability: ReserveMargin | None = Field(default=None)
    reserveRequestProfile: ReserveRequestProfile | None = Field(default=None)
    resourceDiscreteControlProfile: ResourceDiscreteControlProfile | None = Field(default=None)


class ReserveRequestProfile(BaseModel):
    allocatedMargin: AllocatedMargin | None = Field(default=None)
    reserveAvailability: ReserveMargin | None = Field(default=None)
    reserveRequestProfile: ReserveRequestProfile | None = Field(default=None)
    resourceDiscreteControlProfile: ResourceDiscreteControlProfile | None = Field(default=None)


from ..resource_module.resource_module import ResourceDiscreteControlProfile
