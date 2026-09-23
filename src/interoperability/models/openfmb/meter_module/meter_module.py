from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

class MeterReading(BaseModel):
    conductingEquipmentTerminalReading: ConductingEquipmentTerminalReading | None = Field(default=None)
    meterReadingProfile: dict[str, Any] | None = Field(default=None)
    recloserReading: RecloserReading | None = Field(default=None)
    resourceDiscreteControlProfile: ResourceDiscreteControlProfile | None = Field(default=None)
    resourceReading: PhaseMMTN | None = Field(default=None)
    solarReading: SolarReading | None = Field(default=None)


class MeterReadingProfile(BaseModel):
    conductingEquipmentTerminalReading: ConductingEquipmentTerminalReading | None = Field(default=None)
    meterReadingProfile: dict[str, Any] | None = Field(default=None)
    recloserReading: RecloserReading | None = Field(default=None)
    resourceDiscreteControlProfile: ResourceDiscreteControlProfile | None = Field(default=None)
    resourceReading: PhaseMMTN | None = Field(default=None)
    solarReading: SolarReading | None = Field(default=None)


from ..common_module.common_types import ConductingEquipmentTerminalReading
from ..common_module.common_types import PhaseMMTN
from ..recloser_module.recloser_module import RecloserReading
from ..resource_module.resource_module import ResourceDiscreteControlProfile
from ..solar_module.solar_models import SolarReading
