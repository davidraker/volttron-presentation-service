from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

class CapBankCSG(BaseModel):
    capBankControlFSCC: CapBankControlFSCC | None = Field(default=None)


class CapBankControl(BaseModel):
    capBankControl: CapBankControl | None = Field(default=None)
    capBankControlFSCC: CapBankControlFSCC | None = Field(default=None)
    capBankControlProfile: CapBankControl | None = Field(default=None)
    capBankDiscreteControl: CapBankDiscreteControl | None = Field(default=None)
    capBankReadingProfile: CapBankReadingProfile | None = Field(default=None)
    controlFSCC: dict[str, Any] | None = Field(default=None)
    resourceDiscreteControlProfile: ResourceDiscreteControlProfile | None = Field(default=None)


class CapBankControlFSCC(BaseModel):
    capBankControl: CapBankControl | None = Field(default=None)
    capBankControlFSCC: CapBankControlFSCC | None = Field(default=None)
    capBankControlProfile: CapBankControlProfile | None = Field(default=None)
    controlFSCC: dict[str, Any] | None = Field(default=None)


class CapBankControlProfile(BaseModel):
    capBankControl: CapBankControl | None = Field(default=None)
    capBankControlFSCC: CapBankControlFSCC | None = Field(default=None)
    capBankControlProfile: CapBankControl | None = Field(default=None)
    capBankReadingProfile: CapBankReadingProfile | None = Field(default=None)
    controlFSCC: dict[str, Any] | None = Field(default=None)
    resourceDiscreteControlProfile: ResourceDiscreteControlProfile | None = Field(default=None)


class CapBankControlScheduleFSCH(BaseModel):
    capBankControl: CapBankControl | None = Field(default=None)
    capBankControlFSCC: CapBankControlFSCC | None = Field(default=None)


class CapBankControlYPSH(BaseModel):
    capBankDiscreteControl: CapBankDiscreteControl | None = Field(default=None)


class CapBankDiscreteControl(BaseModel):
    capBankDiscreteControl: CapBankDiscreteControl | None = Field(default=None)
    capBankDiscreteControlProfile: CapBankSystem | None = Field(default=None)
    capBankReadingProfile: CapBankReadingProfile | None = Field(default=None)
    resourceDiscreteControlProfile: ResourceDiscreteControlProfile | None = Field(default=None)


class CapBankDiscreteControlProfile(BaseModel):
    capBankDiscreteControl: CapBankDiscreteControl | None = Field(default=None)
    capBankDiscreteControlProfile: CapBankSystem | None = Field(default=None)
    capBankReadingProfile: CapBankReadingProfile | None = Field(default=None)
    resourceDiscreteControlProfile: ResourceDiscreteControlProfile | None = Field(default=None)


class CapBankDiscreteControlYPSH(BaseModel):
    capBankDiscreteControl: CapBankDiscreteControl | None = Field(default=None)
    capBankDiscreteControlProfile: CapBankDiscreteControlProfile | None = Field(default=None)


class CapBankEvent(BaseModel):
    capBankEvent: CapBankEvent | None = Field(default=None)
    capBankEventProfile: CapBankEvent | None = Field(default=None)
    capBankReadingProfile: CapBankReadingProfile | None = Field(default=None)
    capBankStatus: CapBankEventAndStatusYPSH | None = Field(default=None)
    capBankStatusProfile: CapBankStatusProfile | None = Field(default=None)
    resourceDiscreteControlProfile: ResourceDiscreteControlProfile | None = Field(default=None)


class CapBankEventAndStatusYPSH(BaseModel):
    capBankEvent: CapBankEvent | None = Field(default=None)
    capBankEventProfile: CapBankEventProfile | None = Field(default=None)
    capBankStatus: CapBankEventAndStatusYPSH | None = Field(default=None)
    capBankStatusProfile: CapBankStatusProfile | None = Field(default=None)


class CapBankEventProfile(BaseModel):
    capBankEvent: CapBankEvent | None = Field(default=None)
    capBankEventProfile: CapBankEvent | None = Field(default=None)
    capBankReadingProfile: CapBankReadingProfile | None = Field(default=None)
    resourceDiscreteControlProfile: ResourceDiscreteControlProfile | None = Field(default=None)


class CapBankPoint(BaseModel):
    pass


class CapBankReading(BaseModel):
    capBankReading: ReadingMMTR | None = Field(default=None)
    capBankReadingProfile: CapBankReadingProfile | None = Field(default=None)
    conductingEquipmentTerminalReading: ConductingEquipmentTerminalReading | None = Field(default=None)
    recloserReading: RecloserReading | None = Field(default=None)
    resourceDiscreteControlProfile: ResourceDiscreteControlProfile | None = Field(default=None)
    resourceReading: MeterReading | None = Field(default=None)
    solarReading: SolarReading | None = Field(default=None)


class CapBankReadingProfile(BaseModel):
    capBankReading: ReadingMMTR | None = Field(default=None)
    capBankReadingProfile: CapBankReadingProfile | None = Field(default=None)
    conductingEquipmentTerminalReading: ConductingEquipmentTerminalReading | None = Field(default=None)
    recloserReading: RecloserReading | None = Field(default=None)
    resourceDiscreteControlProfile: ResourceDiscreteControlProfile | None = Field(default=None)
    resourceReading: MeterReading | None = Field(default=None)
    solarReading: SolarReading | None = Field(default=None)


class CapBankStatus(BaseModel):
    capBankEvent: CapBankEvent | None = Field(default=None)
    capBankReadingProfile: CapBankReadingProfile | None = Field(default=None)
    capBankStatus: CapBankEventAndStatusYPSH | None = Field(default=None)
    capBankStatusProfile: CapBankStatus | None = Field(default=None)
    resourceDiscreteControlProfile: ResourceDiscreteControlProfile | None = Field(default=None)


class CapBankStatusProfile(BaseModel):
    capBankEvent: CapBankEvent | None = Field(default=None)
    capBankReadingProfile: CapBankReadingProfile | None = Field(default=None)
    capBankStatus: CapBankEventAndStatusYPSH | None = Field(default=None)
    capBankStatusProfile: CapBankStatus | None = Field(default=None)
    resourceDiscreteControlProfile: ResourceDiscreteControlProfile | None = Field(default=None)


class CapBankSystem(BaseModel):
    capBankControlProfile: CapBankControl | None = Field(default=None)
    capBankDiscreteControlProfile: CapBankSystem | None = Field(default=None)
    capBankEventProfile: CapBankEvent | None = Field(default=None)
    capBankReadingProfile: CapBankReadingProfile | None = Field(default=None)
    capBankStatusProfile: CapBankStatus | None = Field(default=None)
    resourceDiscreteControlProfile: ResourceDiscreteControlProfile | None = Field(default=None)


from ..common_module.common_types import ConductingEquipmentTerminalReading
from ..common_module.common_types import ReadingMMTR
from ..meter_module.meter_module import MeterReading
from ..recloser_module.recloser_module import RecloserReading
from ..resource_module.resource_module import ResourceDiscreteControlProfile
from ..solar_module.solar_models import SolarReading
