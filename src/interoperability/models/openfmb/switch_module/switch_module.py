from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

class ProtectedSwitch(BaseModel):
    resourceDiscreteControlProfile: ResourceDiscreteControlProfile | None = Field(default=None)
    switchDiscreteControlProfile: ProtectedSwitch | None = Field(default=None)
    switchEventProfile: SwitchEvent | None = Field(default=None)
    switchReadingProfile: ProtectedSwitch | None = Field(default=None)
    switchStatusProfile: ProtectedSwitch | None = Field(default=None)


class SwitchDiscreteControl(BaseModel):
    resourceDiscreteControlProfile: ResourceDiscreteControlProfile | None = Field(default=None)
    switchDiscreteControl: SwitchDiscreteControl | None = Field(default=None)
    switchDiscreteControlProfile: ProtectedSwitch | None = Field(default=None)
    switchStatusProfile: SwitchStatusProfile | None = Field(default=None)


class SwitchDiscreteControlProfile(BaseModel):
    resourceDiscreteControlProfile: ResourceDiscreteControlProfile | None = Field(default=None)
    switchDiscreteControl: SwitchDiscreteControl | None = Field(default=None)
    switchDiscreteControlProfile: ProtectedSwitch | None = Field(default=None)
    switchStatusProfile: SwitchStatusProfile | None = Field(default=None)


class SwitchDiscreteControlXSWI(BaseModel):
    switchDiscreteControl: SwitchDiscreteControl | None = Field(default=None)
    switchDiscreteControlProfile: SwitchDiscreteControlProfile | None = Field(default=None)


class SwitchEvent(BaseModel):
    resourceDiscreteControlProfile: ResourceDiscreteControlProfile | None = Field(default=None)
    switchEvent: SwitchEvent | None = Field(default=None)
    switchEventProfile: SwitchEvent | None = Field(default=None)
    switchStatusProfile: SwitchStatusProfile | None = Field(default=None)


class SwitchEventProfile(BaseModel):
    resourceDiscreteControlProfile: ResourceDiscreteControlProfile | None = Field(default=None)
    switchEvent: SwitchEvent | None = Field(default=None)
    switchEventProfile: SwitchEvent | None = Field(default=None)
    switchStatusProfile: SwitchStatusProfile | None = Field(default=None)


class SwitchEventXSWI(BaseModel):
    switchEvent: SwitchEvent | None = Field(default=None)
    switchEventProfile: SwitchEventProfile | None = Field(default=None)


class SwitchReading(BaseModel):
    conductingEquipmentTerminalReading: ConductingEquipmentTerminalReading | None = Field(default=None)
    recloserReading: RecloserReading | None = Field(default=None)
    resourceDiscreteControlProfile: ResourceDiscreteControlProfile | None = Field(default=None)
    resourceReading: MeterReading | None = Field(default=None)
    solarReading: SolarReading | None = Field(default=None)
    switchReading: ReadingMMTR | None = Field(default=None)
    switchReadingProfile: ProtectedSwitch | None = Field(default=None)
    switchStatusProfile: SwitchStatusProfile | None = Field(default=None)


class SwitchReadingProfile(BaseModel):
    conductingEquipmentTerminalReading: ConductingEquipmentTerminalReading | None = Field(default=None)
    recloserReading: RecloserReading | None = Field(default=None)
    resourceDiscreteControlProfile: ResourceDiscreteControlProfile | None = Field(default=None)
    resourceReading: MeterReading | None = Field(default=None)
    solarReading: SolarReading | None = Field(default=None)
    switchReading: ReadingMMTR | None = Field(default=None)
    switchReadingProfile: ProtectedSwitch | None = Field(default=None)
    switchStatusProfile: SwitchStatusProfile | None = Field(default=None)


class SwitchStatus(BaseModel):
    resourceDiscreteControlProfile: ResourceDiscreteControlProfile | None = Field(default=None)
    switchStatus: SwitchStatus | None = Field(default=None)
    switchStatusProfile: ProtectedSwitch | None = Field(default=None)


class SwitchStatusProfile(BaseModel):
    resourceDiscreteControlProfile: ResourceDiscreteControlProfile | None = Field(default=None)
    switchStatus: SwitchStatus | None = Field(default=None)
    switchStatusProfile: ProtectedSwitch | None = Field(default=None)


class SwitchStatusXSWI(BaseModel):
    switchStatus: SwitchStatus | None = Field(default=None)
    switchStatusProfile: SwitchStatusProfile | None = Field(default=None)


from ..common_module.common_types import ConductingEquipmentTerminalReading
from ..common_module.common_types import ReadingMMTR
from ..meter_module.meter_module import MeterReading
from ..recloser_module.recloser_module import RecloserReading
from ..resource_module.resource_module import ResourceDiscreteControlProfile
from ..solar_module.solar_models import SolarReading
