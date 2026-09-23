from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

class Breaker(BaseModel):
    breakerDiscreteControl: BreakerDiscreteControl | None = Field(default=None)
    breakerDiscreteControlProfile: Breaker | None = Field(default=None)
    breakerEvent: dict[str, Any] | None = Field(default=None)
    breakerEventProfile: Breaker | None = Field(default=None)
    breakerReadingProfile: Breaker | None = Field(default=None)
    breakerReadingValue: ReadingMMXU | None = Field(default=None)
    breakerStatus: dict[str, Any] | None = Field(default=None)
    breakerStatusProfile: Breaker | None = Field(default=None)
    conductingEquipmentTerminalReading: ConductingEquipmentTerminalReading | None = Field(default=None)
    measurementIED: ReadingMMTR | None = Field(default=None)
    recloserReading: RecloserReading | None = Field(default=None)
    recloserStatus: RecloserStatus | None = Field(default=None)
    resourceDiscreteControlProfile: ResourceDiscreteControlProfile | None = Field(default=None)
    resourceReading: MeterReading | None = Field(default=None)
    solarReading: SolarReading | None = Field(default=None)


class BreakerDiscreteControl(BaseModel):
    breakerDiscreteControl: BreakerDiscreteControl | None = Field(default=None)
    breakerDiscreteControlProfile: Breaker | None = Field(default=None)
    breakerEventProfile: BreakerEventProfile | None = Field(default=None)
    resourceDiscreteControlProfile: ResourceDiscreteControlProfile | None = Field(default=None)


class BreakerDiscreteControlProfile(BaseModel):
    breakerDiscreteControl: BreakerDiscreteControl | None = Field(default=None)
    breakerDiscreteControlProfile: Breaker | None = Field(default=None)
    breakerEventProfile: BreakerEventProfile | None = Field(default=None)
    resourceDiscreteControlProfile: ResourceDiscreteControlProfile | None = Field(default=None)


class BreakerDiscreteControlXCBR(BaseModel):
    breakerDiscreteControl: BreakerDiscreteControl | None = Field(default=None)
    breakerDiscreteControlProfile: BreakerDiscreteControlProfile | None = Field(default=None)


class BreakerEvent(BaseModel):
    breakerEvent: dict[str, Any] | None = Field(default=None)
    breakerEventProfile: Breaker | None = Field(default=None)
    recloserStatus: RecloserStatus | None = Field(default=None)
    resourceDiscreteControlProfile: ResourceDiscreteControlProfile | None = Field(default=None)


class BreakerEventProfile(BaseModel):
    breakerEvent: dict[str, Any] | None = Field(default=None)
    breakerEventProfile: Breaker | None = Field(default=None)
    recloserStatus: RecloserStatus | None = Field(default=None)
    resourceDiscreteControlProfile: ResourceDiscreteControlProfile | None = Field(default=None)


class BreakerReading(BaseModel):
    breakerEventProfile: BreakerEventProfile | None = Field(default=None)
    breakerReadingProfile: Breaker | None = Field(default=None)
    breakerReadingValue: ReadingMMXU | None = Field(default=None)
    conductingEquipmentTerminalReading: ConductingEquipmentTerminalReading | None = Field(default=None)
    measurementIED: ReadingMMTR | None = Field(default=None)
    recloserReading: RecloserReading | None = Field(default=None)
    resourceDiscreteControlProfile: ResourceDiscreteControlProfile | None = Field(default=None)
    resourceReading: MeterReading | None = Field(default=None)
    solarReading: SolarReading | None = Field(default=None)


class BreakerReadingProfile(BaseModel):
    breakerEventProfile: BreakerEventProfile | None = Field(default=None)
    breakerReadingProfile: Breaker | None = Field(default=None)
    conductingEquipmentTerminalReading: ConductingEquipmentTerminalReading | None = Field(default=None)
    measurementIED: ReadingMMTR | None = Field(default=None)
    recloserReading: RecloserReading | None = Field(default=None)
    resourceDiscreteControlProfile: ResourceDiscreteControlProfile | None = Field(default=None)
    resourceReading: MeterReading | None = Field(default=None)
    solarReading: SolarReading | None = Field(default=None)


class BreakerReadingValue(BaseModel):
    breakerReadingValue: ReadingMMXU | None = Field(default=None)
    recloserReading: RecloserReading | None = Field(default=None)
    solarReading: SolarReading | None = Field(default=None)


class BreakerStatus(BaseModel):
    breakerEventProfile: BreakerEventProfile | None = Field(default=None)
    breakerStatus: dict[str, Any] | None = Field(default=None)
    breakerStatusProfile: Breaker | None = Field(default=None)
    recloserStatus: RecloserStatus | None = Field(default=None)
    resourceDiscreteControlProfile: ResourceDiscreteControlProfile | None = Field(default=None)


class BreakerStatusProfile(BaseModel):
    breakerEventProfile: BreakerEventProfile | None = Field(default=None)
    breakerStatus: dict[str, Any] | None = Field(default=None)
    breakerStatusProfile: Breaker | None = Field(default=None)
    recloserStatus: RecloserStatus | None = Field(default=None)
    resourceDiscreteControlProfile: ResourceDiscreteControlProfile | None = Field(default=None)


from ..common_module.common_types import ConductingEquipmentTerminalReading
from ..common_module.common_types import ReadingMMTR
from ..common_module.common_types import ReadingMMXU
from ..meter_module.meter_module import MeterReading
from ..recloser_module.recloser_module import RecloserReading
from ..recloser_module.recloser_module import RecloserStatus
from ..resource_module.resource_module import ResourceDiscreteControlProfile
from ..solar_module.solar_models import SolarReading
