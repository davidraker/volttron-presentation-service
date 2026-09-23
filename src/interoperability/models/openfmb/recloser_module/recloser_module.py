from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

class Recloser(BaseModel):
    conductingEquipmentTerminalReading: ConductingEquipmentTerminalReading | None = Field(default=None)
    recloserDiscreteControl: RecloserDiscreteControl | None = Field(default=None)
    recloserDiscreteControlProfile: Recloser | None = Field(default=None)
    recloserEvent: dict[str, Any] | None = Field(default=None)
    recloserEventProfile: RecloserEvent | None = Field(default=None)
    recloserReading: RecloserReading | None = Field(default=None)
    recloserReadingProfile: Recloser | None = Field(default=None)
    recloserStatus: RecloserStatus | None = Field(default=None)
    recloserStatusProfile: RecloserStatus | None = Field(default=None)
    reclosetStatusProfile: RecloserStatusProfile | None = Field(default=None)
    resourceDiscreteControlProfile: ResourceDiscreteControlProfile | None = Field(default=None)
    resourceReading: MeterReading | None = Field(default=None)
    solarReading: SolarReading | None = Field(default=None)


class RecloserDiscreteControl(BaseModel):
    recloserDiscreteControl: RecloserDiscreteControl | None = Field(default=None)
    recloserDiscreteControlProfile: Recloser | None = Field(default=None)
    reclosetStatusProfile: RecloserStatusProfile | None = Field(default=None)
    resourceDiscreteControlProfile: ResourceDiscreteControlProfile | None = Field(default=None)


class RecloserDiscreteControlProfile(BaseModel):
    recloserDiscreteControl: RecloserDiscreteControl | None = Field(default=None)
    recloserDiscreteControlProfile: Recloser | None = Field(default=None)
    reclosetStatusProfile: RecloserStatusProfile | None = Field(default=None)
    resourceDiscreteControlProfile: ResourceDiscreteControlProfile | None = Field(default=None)


class RecloserDiscreteControlXCBR(BaseModel):
    recloserDiscreteControl: RecloserDiscreteControl | None = Field(default=None)
    recloserDiscreteControlProfile: RecloserDiscreteControlProfile | None = Field(default=None)


class RecloserEvent(BaseModel):
    recloserEvent: dict[str, Any] | None = Field(default=None)
    recloserEventProfile: RecloserEvent | None = Field(default=None)
    recloserStatus: RecloserStatus | None = Field(default=None)
    reclosetStatusProfile: RecloserStatusProfile | None = Field(default=None)
    resourceDiscreteControlProfile: ResourceDiscreteControlProfile | None = Field(default=None)


class RecloserEventProfile(BaseModel):
    recloserEvent: dict[str, Any] | None = Field(default=None)
    recloserEventProfile: RecloserEvent | None = Field(default=None)
    recloserStatus: RecloserStatus | None = Field(default=None)
    reclosetStatusProfile: RecloserStatusProfile | None = Field(default=None)
    resourceDiscreteControlProfile: ResourceDiscreteControlProfile | None = Field(default=None)


class RecloserReading(BaseModel):
    conductingEquipmentTerminalReading: ConductingEquipmentTerminalReading | None = Field(default=None)
    recloserReading: RecloserReading | None = Field(default=None)
    recloserReadingProfile: Recloser | None = Field(default=None)
    reclosetStatusProfile: RecloserStatusProfile | None = Field(default=None)
    resourceDiscreteControlProfile: ResourceDiscreteControlProfile | None = Field(default=None)
    resourceReading: MeterReading | None = Field(default=None)
    solarReading: SolarReading | None = Field(default=None)


class RecloserReadingProfile(BaseModel):
    conductingEquipmentTerminalReading: ConductingEquipmentTerminalReading | None = Field(default=None)
    recloserReading: RecloserReading | None = Field(default=None)
    recloserReadingProfile: Recloser | None = Field(default=None)
    reclosetStatusProfile: RecloserStatusProfile | None = Field(default=None)
    resourceDiscreteControlProfile: ResourceDiscreteControlProfile | None = Field(default=None)
    resourceReading: MeterReading | None = Field(default=None)
    solarReading: SolarReading | None = Field(default=None)


class RecloserStatus(BaseModel):
    recloserStatus: RecloserStatus | None = Field(default=None)
    recloserStatusProfile: RecloserStatus | None = Field(default=None)
    reclosetStatusProfile: RecloserStatusProfile | None = Field(default=None)
    resourceDiscreteControlProfile: ResourceDiscreteControlProfile | None = Field(default=None)


class RecloserStatusProfile(BaseModel):
    recloserStatus: RecloserStatus | None = Field(default=None)
    recloserStatusProfile: RecloserStatus | None = Field(default=None)
    reclosetStatusProfile: RecloserStatusProfile | None = Field(default=None)
    resourceDiscreteControlProfile: ResourceDiscreteControlProfile | None = Field(default=None)


from ..common_module.common_types import ConductingEquipmentTerminalReading
from ..meter_module.meter_module import MeterReading
from ..resource_module.resource_module import ResourceDiscreteControlProfile
from ..solar_module.solar_models import SolarReading
