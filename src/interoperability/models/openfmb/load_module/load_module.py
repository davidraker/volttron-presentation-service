from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

class LoadCSG(BaseModel):
    loadControlFSCC: LoadControlFSCC | None = Field(default=None)


class LoadControl(BaseModel):
    controlFSCC: dict[str, Any] | None = Field(default=None)
    loadControl: LoadControl | None = Field(default=None)
    loadControlFSCC: LoadControlFSCC | None = Field(default=None)
    loadEventProfile: LoadEventProfile | None = Field(default=None)
    resourceDiscreteControlProfile: ResourceDiscreteControlProfile | None = Field(default=None)


class LoadControlFSCC(BaseModel):
    controlFSCC: dict[str, Any] | None = Field(default=None)
    loadControl: LoadControl | None = Field(default=None)
    loadControlFSCC: LoadControlFSCC | None = Field(default=None)


class LoadControlProfile(BaseModel):
    controlFSCC: dict[str, Any] | None = Field(default=None)
    loadControl: LoadControl | None = Field(default=None)
    loadControlFSCC: LoadControlFSCC | None = Field(default=None)
    loadEventProfile: LoadEventProfile | None = Field(default=None)
    resourceDiscreteControlProfile: ResourceDiscreteControlProfile | None = Field(default=None)


class LoadControlScheduleFSCH(BaseModel):
    loadControl: LoadControl | None = Field(default=None)
    loadControlFSCC: LoadControlFSCC | None = Field(default=None)


class LoadEvent(BaseModel):
    loadEvent: LoadEvent | None = Field(default=None)
    loadEventProfile: LoadEvent | None = Field(default=None)
    loadStatus: LoadStatus | None = Field(default=None)
    resourceDiscreteControlProfile: ResourceDiscreteControlProfile | None = Field(default=None)


class LoadEventAndStatusZGLD(BaseModel):
    loadEvent: LoadEvent | None = Field(default=None)
    loadStatus: LoadStatus | None = Field(default=None)


class LoadEventProfile(BaseModel):
    loadEvent: LoadEvent | None = Field(default=None)
    loadEventProfile: LoadEvent | None = Field(default=None)
    resourceDiscreteControlProfile: ResourceDiscreteControlProfile | None = Field(default=None)


class LoadEventZGLD(BaseModel):
    loadEvent: LoadEvent | None = Field(default=None)
    loadEventProfile: LoadEventProfile | None = Field(default=None)


class LoadPoint(BaseModel):
    pass


class LoadPointStatus(BaseModel):
    pass


class LoadReading(BaseModel):
    conductingEquipmentTerminalReading: ConductingEquipmentTerminalReading | None = Field(default=None)
    loadEventProfile: LoadEventProfile | None = Field(default=None)
    loadReading: PhaseMMTN | None = Field(default=None)
    loadReadingProfile: LoadReading | None = Field(default=None)
    recloserReading: RecloserReading | None = Field(default=None)
    resourceDiscreteControlProfile: ResourceDiscreteControlProfile | None = Field(default=None)
    resourceReading: MeterReading | None = Field(default=None)
    solarReading: SolarReading | None = Field(default=None)


class LoadReadingProfile(BaseModel):
    conductingEquipmentTerminalReading: ConductingEquipmentTerminalReading | None = Field(default=None)
    loadEventProfile: LoadEventProfile | None = Field(default=None)
    loadReading: PhaseMMTN | None = Field(default=None)
    loadReadingProfile: LoadReading | None = Field(default=None)
    recloserReading: RecloserReading | None = Field(default=None)
    resourceDiscreteControlProfile: ResourceDiscreteControlProfile | None = Field(default=None)
    resourceReading: MeterReading | None = Field(default=None)
    solarReading: SolarReading | None = Field(default=None)


class LoadStatus(BaseModel):
    loadEventProfile: LoadEventProfile | None = Field(default=None)
    loadStatus: LoadStatus | None = Field(default=None)
    loadStatusProfile: dict[str, Any] | None = Field(default=None)
    resourceDiscreteControlProfile: ResourceDiscreteControlProfile | None = Field(default=None)


class LoadStatusProfile(BaseModel):
    loadEventProfile: LoadEventProfile | None = Field(default=None)
    loadStatus: LoadStatus | None = Field(default=None)
    loadStatusProfile: dict[str, Any] | None = Field(default=None)
    resourceDiscreteControlProfile: ResourceDiscreteControlProfile | None = Field(default=None)


class LoadStatusZGLD(BaseModel):
    loadStatus: LoadStatus | None = Field(default=None)
    loadStatusProfile: LoadStatusProfile | None = Field(default=None)


from ..common_module.common_types import ConductingEquipmentTerminalReading
from ..common_module.common_types import PhaseMMTN
from ..meter_module.meter_module import MeterReading
from ..recloser_module.recloser_module import RecloserReading
from ..resource_module.resource_module import ResourceDiscreteControlProfile
from ..solar_module.solar_models import SolarReading
