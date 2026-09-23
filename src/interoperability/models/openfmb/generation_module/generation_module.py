from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

class DroopParameter(BaseModel):
    generationDiscreteControl: GenerationDiscreteControl | None = Field(default=None)


class GeneratingUnit(BaseModel):
    generationControlProfile: GeneratingUnit | None = Field(default=None)
    generationDiscreteControlProfile: GeneratingUnit | None = Field(default=None)
    generationEventProfile: GenerationEventProfile | None = Field(default=None)
    generationReadingProfile: GeneratingUnit | None = Field(default=None)
    generationStatusProfile: GenerationStatus | None = Field(default=None)
    resourceDiscreteControlProfile: ResourceDiscreteControlProfile | None = Field(default=None)


class GenerationCSG(BaseModel):
    generationControlFSCC: GenerationControlFSCC | None = Field(default=None)


class GenerationCapability(BaseModel):
    pass


class GenerationCapabilityConfiguration(BaseModel):
    pass


class GenerationCapabilityOverride(BaseModel):
    pass


class GenerationCapabilityOverrideProfile(BaseModel):
    pass


class GenerationCapabilityProfile(BaseModel):
    pass


class GenerationCapabilityRatings(BaseModel):
    pass


class GenerationControl(BaseModel):
    controlFSCC: dict[str, Any] | None = Field(default=None)
    generationControl: GenerationControl | None = Field(default=None)
    generationControlFSCC: GenerationControlScheduleFSCH | None = Field(default=None)
    generationControlProfile: GeneratingUnit | None = Field(default=None)
    generationEventProfile: GenerationEventProfile | None = Field(default=None)
    resourceDiscreteControlProfile: ResourceDiscreteControlProfile | None = Field(default=None)


class GenerationControlFSCC(BaseModel):
    controlFSCC: dict[str, Any] | None = Field(default=None)
    generationControl: GenerationControl | None = Field(default=None)
    generationControlFSCC: GenerationControlScheduleFSCH | None = Field(default=None)


class GenerationControlProfile(BaseModel):
    controlFSCC: dict[str, Any] | None = Field(default=None)
    generationControl: GenerationControl | None = Field(default=None)
    generationControlFSCC: GenerationControlScheduleFSCH | None = Field(default=None)
    generationControlProfile: GeneratingUnit | None = Field(default=None)
    generationEventProfile: GenerationEventProfile | None = Field(default=None)
    resourceDiscreteControlProfile: ResourceDiscreteControlProfile | None = Field(default=None)


class GenerationControlScheduleFSCH(BaseModel):
    generationControl: GenerationControl | None = Field(default=None)
    generationControlFSCC: GenerationControlScheduleFSCH | None = Field(default=None)


class GenerationDiscreteControl(BaseModel):
    generationDiscreteControl: GenerationDiscreteControl | None = Field(default=None)
    generationDiscreteControlProfile: GeneratingUnit | None = Field(default=None)
    generationEventProfile: GenerationEventProfile | None = Field(default=None)
    resourceDiscreteControlProfile: ResourceDiscreteControlProfile | None = Field(default=None)


class GenerationDiscreteControlProfile(BaseModel):
    generationDiscreteControl: GenerationDiscreteControl | None = Field(default=None)
    generationDiscreteControlProfile: GeneratingUnit | None = Field(default=None)
    generationEventProfile: GenerationEventProfile | None = Field(default=None)
    resourceDiscreteControlProfile: ResourceDiscreteControlProfile | None = Field(default=None)


class GenerationEvent(BaseModel):
    generationEvent: GenerationEventZGEN | None = Field(default=None)
    generationEventProfile: GenerationEventProfile | None = Field(default=None)
    generationStatus: GenerationStatus | None = Field(default=None)
    resourceDiscreteControlProfile: ResourceDiscreteControlProfile | None = Field(default=None)


class GenerationEventAndStatusZGEN(BaseModel):
    generationEvent: GenerationEvent | None = Field(default=None)
    generationStatus: GenerationStatus | None = Field(default=None)


class GenerationEventProfile(BaseModel):
    generationEvent: GenerationEventZGEN | None = Field(default=None)
    generationEventProfile: GenerationEventProfile | None = Field(default=None)
    resourceDiscreteControlProfile: ResourceDiscreteControlProfile | None = Field(default=None)


class GenerationEventZGEN(BaseModel):
    generationEvent: GenerationEventZGEN | None = Field(default=None)
    generationEventProfile: GenerationEventProfile | None = Field(default=None)


class GenerationPoint(BaseModel):
    pass


class GenerationPointStatus(BaseModel):
    pass


class GenerationReading(BaseModel):
    conductingEquipmentTerminalReading: ConductingEquipmentTerminalReading | None = Field(default=None)
    generationEventProfile: GenerationEventProfile | None = Field(default=None)
    generationReading: PhaseMMTN | None = Field(default=None)
    generationReadingProfile: GeneratingUnit | None = Field(default=None)
    recloserReading: RecloserReading | None = Field(default=None)
    resourceDiscreteControlProfile: ResourceDiscreteControlProfile | None = Field(default=None)
    resourceReading: MeterReading | None = Field(default=None)
    solarReading: SolarReading | None = Field(default=None)


class GenerationReadingProfile(BaseModel):
    conductingEquipmentTerminalReading: ConductingEquipmentTerminalReading | None = Field(default=None)
    generationEventProfile: GenerationEventProfile | None = Field(default=None)
    generationReading: PhaseMMTN | None = Field(default=None)
    generationReadingProfile: GeneratingUnit | None = Field(default=None)
    recloserReading: RecloserReading | None = Field(default=None)
    resourceDiscreteControlProfile: ResourceDiscreteControlProfile | None = Field(default=None)
    resourceReading: MeterReading | None = Field(default=None)
    solarReading: SolarReading | None = Field(default=None)


class GenerationStatus(BaseModel):
    generationEventProfile: GenerationEventProfile | None = Field(default=None)
    generationStatus: GenerationStatusZGEN | None = Field(default=None)
    generationStatusProfile: GenerationStatus | None = Field(default=None)
    resourceDiscreteControlProfile: ResourceDiscreteControlProfile | None = Field(default=None)


class GenerationStatusProfile(BaseModel):
    generationEventProfile: GenerationEventProfile | None = Field(default=None)
    generationStatus: GenerationStatusZGEN | None = Field(default=None)
    generationStatusProfile: GenerationStatus | None = Field(default=None)
    resourceDiscreteControlProfile: ResourceDiscreteControlProfile | None = Field(default=None)


class GenerationStatusZGEN(BaseModel):
    generationStatus: GenerationStatusZGEN | None = Field(default=None)
    generationStatusProfile: GenerationStatusProfile | None = Field(default=None)


class ReactivePowerControl(BaseModel):
    generationDiscreteControl: GenerationDiscreteControl | None = Field(default=None)
    generationDiscreteControlProfile: GenerationDiscreteControlProfile | None = Field(default=None)


class RealPowerControl(BaseModel):
    generationDiscreteControl: GenerationDiscreteControl | None = Field(default=None)
    generationDiscreteControlProfile: GenerationDiscreteControlProfile | None = Field(default=None)


from ..common_module.common_types import ConductingEquipmentTerminalReading
from ..common_module.common_types import PhaseMMTN
from ..meter_module.meter_module import MeterReading
from ..recloser_module.recloser_module import RecloserReading
from ..resource_module.resource_module import ResourceDiscreteControlProfile
from ..solar_module.solar_models import SolarReading
