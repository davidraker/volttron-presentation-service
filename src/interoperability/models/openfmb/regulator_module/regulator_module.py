from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

class DirectionalATCC(BaseModel):
    regulatorDiscreteControl: RegulatorDiscreteControl | None = Field(default=None)


class RegulatorCSG(BaseModel):
    regulatorControlFSCC: RegulatorControlFSCC | None = Field(default=None)


class RegulatorControl(BaseModel):
    controlFSCC: dict[str, Any] | None = Field(default=None)
    regulatorControl: RegulatorControl | None = Field(default=None)
    regulatorControlFSCC: RegulatorControlFSCC | None = Field(default=None)
    regulatorControlProfile: RegulatorSystem | None = Field(default=None)
    regulatorDiscreteControl: RegulatorControlATCC | None = Field(default=None)
    regulatorDiscreteControlProfile: RegulatorDiscreteControlProfile | None = Field(default=None)
    regulatorStatusProfile: RegulatorStatusProfile | None = Field(default=None)
    resourceDiscreteControlProfile: ResourceDiscreteControlProfile | None = Field(default=None)


class RegulatorControlATCC(BaseModel):
    regulatorDiscreteControl: RegulatorControlATCC | None = Field(default=None)
    regulatorDiscreteControlProfile: RegulatorDiscreteControlProfile | None = Field(default=None)


class RegulatorControlFSCC(BaseModel):
    controlFSCC: dict[str, Any] | None = Field(default=None)
    regulatorControl: RegulatorControl | None = Field(default=None)
    regulatorControlFSCC: RegulatorControlFSCC | None = Field(default=None)


class RegulatorControlProfile(BaseModel):
    controlFSCC: dict[str, Any] | None = Field(default=None)
    regulatorControl: RegulatorControl | None = Field(default=None)
    regulatorControlFSCC: RegulatorControlFSCC | None = Field(default=None)
    regulatorControlProfile: RegulatorSystem | None = Field(default=None)
    regulatorDiscreteControl: RegulatorDiscreteControl | None = Field(default=None)
    regulatorStatusProfile: RegulatorStatusProfile | None = Field(default=None)
    resourceDiscreteControlProfile: ResourceDiscreteControlProfile | None = Field(default=None)


class RegulatorControlScheduleFSCH(BaseModel):
    regulatorControl: RegulatorControl | None = Field(default=None)
    regulatorControlFSCC: RegulatorControlFSCC | None = Field(default=None)


class RegulatorDiscreteControl(BaseModel):
    regulatorDiscreteControl: RegulatorControlATCC | None = Field(default=None)
    regulatorDiscreteControlProfile: RegulatorDiscreteControl | None = Field(default=None)
    regulatorStatusProfile: RegulatorStatusProfile | None = Field(default=None)
    resourceDiscreteControlProfile: ResourceDiscreteControlProfile | None = Field(default=None)


class RegulatorDiscreteControlProfile(BaseModel):
    regulatorDiscreteControl: RegulatorControlATCC | None = Field(default=None)
    regulatorDiscreteControlProfile: RegulatorDiscreteControl | None = Field(default=None)
    regulatorStatusProfile: RegulatorStatusProfile | None = Field(default=None)
    resourceDiscreteControlProfile: ResourceDiscreteControlProfile | None = Field(default=None)


class RegulatorEvent(BaseModel):
    regulatorEvent: RegulatorEvent | None = Field(default=None)
    regulatorStatus: RegulatorEventAndStatusANCR | None = Field(default=None)
    regulatorStatusProfile: RegulatorStatusProfile | None = Field(default=None)
    resourceDiscreteControlProfile: ResourceDiscreteControlProfile | None = Field(default=None)


class RegulatorEventAndStatusANCR(BaseModel):
    regulatorEvent: RegulatorEvent | None = Field(default=None)
    regulatorStatus: RegulatorEventAndStatusANCR | None = Field(default=None)
    regulatorStatusProfile: RegulatorStatusProfile | None = Field(default=None)


class RegulatorEventAndStatusATCC(BaseModel):
    regulatorEvent: RegulatorEvent | None = Field(default=None)


class RegulatorEventProfile(BaseModel):
    regulatorEvent: RegulatorEvent | None = Field(default=None)
    regulatorStatusProfile: RegulatorStatusProfile | None = Field(default=None)
    resourceDiscreteControlProfile: ResourceDiscreteControlProfile | None = Field(default=None)


class RegulatorPoint(BaseModel):
    pass


class RegulatorReading(BaseModel):
    conductingEquipmentTerminalReading: ConductingEquipmentTerminalReading | None = Field(default=None)
    recloserReading: RecloserReading | None = Field(default=None)
    regulatorReading: ReadingMMXU | None = Field(default=None)
    regulatorReadingProfile: RegulatorReading | None = Field(default=None)
    regulatorStatusProfile: RegulatorStatusProfile | None = Field(default=None)
    resourceDiscreteControlProfile: ResourceDiscreteControlProfile | None = Field(default=None)
    resourceReading: MeterReading | None = Field(default=None)
    solarReading: SolarReading | None = Field(default=None)


class RegulatorReadingProfile(BaseModel):
    conductingEquipmentTerminalReading: ConductingEquipmentTerminalReading | None = Field(default=None)
    recloserReading: RecloserReading | None = Field(default=None)
    regulatorReading: ReadingMMXU | None = Field(default=None)
    regulatorReadingProfile: RegulatorReading | None = Field(default=None)
    regulatorStatusProfile: RegulatorStatusProfile | None = Field(default=None)
    resourceDiscreteControlProfile: ResourceDiscreteControlProfile | None = Field(default=None)
    resourceReading: MeterReading | None = Field(default=None)
    solarReading: SolarReading | None = Field(default=None)


class RegulatorStatus(BaseModel):
    regulatorEvent: RegulatorEvent | None = Field(default=None)
    regulatorStatus: RegulatorEventAndStatusANCR | None = Field(default=None)
    regulatorStatusProfile: RegulatorStatus | None = Field(default=None)
    resourceDiscreteControlProfile: ResourceDiscreteControlProfile | None = Field(default=None)


class RegulatorStatusProfile(BaseModel):
    regulatorEvent: RegulatorEvent | None = Field(default=None)
    regulatorStatus: RegulatorEventAndStatusANCR | None = Field(default=None)
    regulatorStatusProfile: RegulatorStatus | None = Field(default=None)
    resourceDiscreteControlProfile: ResourceDiscreteControlProfile | None = Field(default=None)


class RegulatorSystem(BaseModel):
    regulatorControlProfile: RegulatorSystem | None = Field(default=None)
    regulatorDiscreteControlProfile: RegulatorDiscreteControl | None = Field(default=None)
    regulatorEvent: RegulatorEvent | None = Field(default=None)
    regulatorReadingProfile: RegulatorReading | None = Field(default=None)
    regulatorStatusProfile: RegulatorStatus | None = Field(default=None)
    resourceDiscreteControlProfile: ResourceDiscreteControlProfile | None = Field(default=None)


from ..common_module.common_types import ConductingEquipmentTerminalReading
from ..common_module.common_types import ReadingMMXU
from ..meter_module.meter_module import MeterReading
from ..recloser_module.recloser_module import RecloserReading
from ..resource_module.resource_module import ResourceDiscreteControlProfile
from ..solar_module.solar_models import SolarReading
