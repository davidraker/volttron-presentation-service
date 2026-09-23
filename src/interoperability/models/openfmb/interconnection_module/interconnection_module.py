from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

class InterconnectionCSG(BaseModel):
    interconnectionScheduleFSCC: InterconnectionScheduleFSCC | None = Field(default=None)


class InterconnectionControlScheduleFSCH(BaseModel):
    interconnectionSchedule: InterconnectionSchedule | None = Field(default=None)
    interconnectionScheduleFSCC: InterconnectionControlScheduleFSCH | None = Field(default=None)


class InterconnectionPlannedScheduleProfile(BaseModel):
    pass


class InterconnectionPoint(BaseModel):
    pass


class InterconnectionRequestedScheduleProfile(BaseModel):
    pass


class InterconnectionSchedule(BaseModel):
    controlFSCC: dict[str, Any] | None = Field(default=None)
    interconnectionSchedule: InterconnectionSchedule | None = Field(default=None)
    interconnectionScheduleFSCC: InterconnectionControlScheduleFSCH | None = Field(default=None)
    plannedInterconnectionScheduleProfile: dict[str, Any] | None = Field(default=None)
    reserveRequestProfile: ReserveRequestProfile | None = Field(default=None)
    resourceDiscreteControlProfile: ResourceDiscreteControlProfile | None = Field(default=None)


class InterconnectionScheduleFSCC(BaseModel):
    controlFSCC: dict[str, Any] | None = Field(default=None)
    interconnectionSchedule: dict[str, Any] | None = Field(default=None)
    interconnectionScheduleFSCC: InterconnectionControlScheduleFSCH | None = Field(default=None)


from ..reserve_module.reserve_module import ReserveRequestProfile
from ..resource_module.resource_module import ResourceDiscreteControlProfile
