from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

class AnalogControlGGIO(BaseModel):
    resourceDiscreteControl: IntegerControlGGIO | None = Field(default=None)
    resourceDiscreteControlProfile: ResourceDiscreteControlProfile | None = Field(default=None)


class BooleanControlGGIO(BaseModel):
    resourceDiscreteControl: IntegerControlGGIO | None = Field(default=None)
    resourceDiscreteControlProfile: ResourceDiscreteControlProfile | None = Field(default=None)


class IntegerControlGGIO(BaseModel):
    resourceDiscreteControl: IntegerControlGGIO | None = Field(default=None)
    resourceDiscreteControlProfile: ResourceDiscreteControlProfile | None = Field(default=None)


class ResourceDiscreteControl(BaseModel):
    resourceDiscreteControl: ResourceDiscreteControl | None = Field(default=None)
    resourceDiscreteControlProfile: ResourceDiscreteControlProfile | None = Field(default=None)


class ResourceDiscreteControlProfile(BaseModel):
    resourceDiscreteControl: ResourceDiscreteControl | None = Field(default=None)
    resourceDiscreteControlProfile: ResourceDiscreteControlProfile | None = Field(default=None)


class ResourceEvent(BaseModel):
    resourceDiscreteControlProfile: ResourceDiscreteControlProfile | None = Field(default=None)
    resourceEvent: dict[str, Any] | None = Field(default=None)
    resourceEventProfile: ResourceEvent | None = Field(default=None)
    resourceStatus: ResourceStatus | None = Field(default=None)
    stringEventAndStatusGGIO: ResourceStatus | None = Field(default=None)


class ResourceEventProfile(BaseModel):
    resourceDiscreteControlProfile: ResourceDiscreteControlProfile | None = Field(default=None)
    resourceEvent: dict[str, Any] | None = Field(default=None)
    resourceEventProfile: ResourceEvent | None = Field(default=None)
    resourceStatus: ResourceStatus | None = Field(default=None)
    stringEventAndStatusGGIO: ResourceStatus | None = Field(default=None)


class ResourceReading(BaseModel):
    conductingEquipmentTerminalReading: ConductingEquipmentTerminalReading | None = Field(default=None)
    recloserReading: RecloserReading | None = Field(default=None)
    resourceDiscreteControlProfile: ResourceDiscreteControlProfile | None = Field(default=None)
    resourceReading: MeterReading | None = Field(default=None)
    resourceReadingProfile: ResourceReading | None = Field(default=None)
    solarReading: SolarReading | None = Field(default=None)


class ResourceReadingProfile(BaseModel):
    conductingEquipmentTerminalReading: ConductingEquipmentTerminalReading | None = Field(default=None)
    recloserReading: RecloserReading | None = Field(default=None)
    resourceDiscreteControlProfile: ResourceDiscreteControlProfile | None = Field(default=None)
    resourceReading: MeterReading | None = Field(default=None)
    resourceReadingProfile: ResourceReading | None = Field(default=None)
    solarReading: SolarReading | None = Field(default=None)


class ResourceStatus(BaseModel):
    resourceDiscreteControlProfile: ResourceDiscreteControlProfile | None = Field(default=None)
    resourceStatus: ResourceStatus | None = Field(default=None)
    resourceStatusProfile: dict[str, Any] | None = Field(default=None)
    stringEventAndStatusGGIO: ResourceStatus | None = Field(default=None)


class ResourceStatusProfile(BaseModel):
    resourceDiscreteControlProfile: ResourceDiscreteControlProfile | None = Field(default=None)
    resourceStatus: ResourceStatus | None = Field(default=None)
    resourceStatusProfile: dict[str, Any] | None = Field(default=None)
    stringEventAndStatusGGIO: ResourceStatus | None = Field(default=None)


class StringControlGGIO(BaseModel):
    resourceDiscreteControl: ResourceDiscreteControl | None = Field(default=None)
    resourceDiscreteControlProfile: ResourceDiscreteControlProfile | None = Field(default=None)


from ..common_module.common_types import ConductingEquipmentTerminalReading
from ..meter_module.meter_module import MeterReading
from ..recloser_module.recloser_module import RecloserReading
from ..solar_module.solar_models import SolarReading
