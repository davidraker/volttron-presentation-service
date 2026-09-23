from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

class ESSCSG(BaseModel):
    essControlFSCC: EssControlFSCC | None = Field(default=None)


class ESSCapability(BaseModel):
    pass


class ESSCapabilityConfiguration(BaseModel):
    pass


class ESSCapabilityOverride(BaseModel):
    pass


class ESSCapabilityOverrideProfile(BaseModel):
    pass


class ESSCapabilityProfile(BaseModel):
    pass


class ESSCapabilityRatings(BaseModel):
    pass


class ESSControl(BaseModel):
    controlFSCC: dict[str, Any] | None = Field(default=None)
    essControl: ESSControlProfile | None = Field(default=None)
    essControlFSCC: ESSControlScheduleFSCH | None = Field(default=None)
    essControlProfile: dict[str, Any] | None = Field(default=None)
    resourceDiscreteControlProfile: ResourceDiscreteControlProfile | None = Field(default=None)


class ESSControlProfile(BaseModel):
    controlFSCC: dict[str, Any] | None = Field(default=None)
    essControl: ESSControlProfile | None = Field(default=None)
    essControlFSCC: ESSControlScheduleFSCH | None = Field(default=None)
    essControlProfile: dict[str, Any] | None = Field(default=None)
    resourceDiscreteControlProfile: ResourceDiscreteControlProfile | None = Field(default=None)


class ESSControlScheduleFSCH(BaseModel):
    essControl: ESSControl | None = Field(default=None)
    essControlFSCC: ESSControlScheduleFSCH | None = Field(default=None)


class ESSCurvePoint(BaseModel):
    pass


class ESSDiscreteControl(BaseModel):
    pass


class ESSDiscreteControlDBAT(BaseModel):
    pass


class ESSDiscreteControlProfile(BaseModel):
    pass


class ESSEvent(BaseModel):
    essControlProfile: ESSControlProfile | None = Field(default=None)
    essEvent: ESSEvent | None = Field(default=None)
    essEventProfile: ESSEvent | None = Field(default=None)
    essStatus: ESSStatus | None = Field(default=None)
    resourceDiscreteControlProfile: ResourceDiscreteControlProfile | None = Field(default=None)


class ESSEventAndStatusZGEN(BaseModel):
    essEvent: ESSEvent | None = Field(default=None)
    essStatus: ESSStatus | None = Field(default=None)


class ESSEventProfile(BaseModel):
    essControlProfile: ESSControlProfile | None = Field(default=None)
    essEvent: ESSEvent | None = Field(default=None)
    essEventProfile: ESSEvent | None = Field(default=None)
    resourceDiscreteControlProfile: ResourceDiscreteControlProfile | None = Field(default=None)


class ESSEventZGEN(BaseModel):
    essEvent: EssEventZBAT | None = Field(default=None)
    essEventProfile: ESSEventProfile | None = Field(default=None)


class ESSFunction(BaseModel):
    pass


class ESSPoint(BaseModel):
    pass


class ESSPointStatus(BaseModel):
    pass


class ESSReading(BaseModel):
    conductingEquipmentTerminalReading: ConductingEquipmentTerminalReading | None = Field(default=None)
    essControlProfile: ESSControlProfile | None = Field(default=None)
    essReadingProfile: dict[str, Any] | None = Field(default=None)
    essReadingValue: ReadingMMTR | None = Field(default=None)
    recloserReading: RecloserReading | None = Field(default=None)
    resourceDiscreteControlProfile: ResourceDiscreteControlProfile | None = Field(default=None)
    resourceReading: MeterReading | None = Field(default=None)
    solarReading: SolarReading | None = Field(default=None)


class ESSReadingProfile(BaseModel):
    conductingEquipmentTerminalReading: ConductingEquipmentTerminalReading | None = Field(default=None)
    essControlProfile: ESSControlProfile | None = Field(default=None)
    essReadingProfile: dict[str, Any] | None = Field(default=None)
    essReadingValue: ReadingMMTR | None = Field(default=None)
    recloserReading: RecloserReading | None = Field(default=None)
    resourceDiscreteControlProfile: ResourceDiscreteControlProfile | None = Field(default=None)
    resourceReading: MeterReading | None = Field(default=None)
    solarReading: SolarReading | None = Field(default=None)


class ESSStatus(BaseModel):
    essControlProfile: ESSControlProfile | None = Field(default=None)
    essStatus: ESSStatus | None = Field(default=None)
    essStatusProfile: ESSStatus | None = Field(default=None)
    resourceDiscreteControlProfile: ResourceDiscreteControlProfile | None = Field(default=None)


class ESSStatusProfile(BaseModel):
    essControlProfile: ESSControlProfile | None = Field(default=None)
    essStatus: ESSStatus | None = Field(default=None)
    essStatusProfile: ESSStatus | None = Field(default=None)
    resourceDiscreteControlProfile: ResourceDiscreteControlProfile | None = Field(default=None)


class ESSStatusZGEN(BaseModel):
    essStatus: ESSStatus | None = Field(default=None)
    essStatusProfile: ESSStatusProfile | None = Field(default=None)


class EssControlFSCC(BaseModel):
    controlFSCC: dict[str, Any] | None = Field(default=None)
    essControl: ESSControlProfile | None = Field(default=None)
    essControlFSCC: ESSControlScheduleFSCH | None = Field(default=None)


class EssEventZBAT(BaseModel):
    essEvent: ESSEvent | None = Field(default=None)
    essEventProfile: ESSEventProfile | None = Field(default=None)


class EssStatusZBAT(BaseModel):
    essStatus: ESSStatus | None = Field(default=None)
    essStatusProfile: ESSStatusProfile | None = Field(default=None)


from ..common_module.common_types import ConductingEquipmentTerminalReading
from ..common_module.common_types import ReadingMMTR
from ..meter_module.meter_module import MeterReading
from ..recloser_module.recloser_module import RecloserReading
from ..resource_module.resource_module import ResourceDiscreteControlProfile
from ..solar_module.solar_models import SolarReading
