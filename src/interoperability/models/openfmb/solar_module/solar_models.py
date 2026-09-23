from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from openfmb.openfmb_information_model_regen.common_module.common_types import (
    ConductingEquipmentTerminalReading,
    GridConnectMode as GridConnectModeEnum,
    OperatingState as OperatingStateEnum,
    PhaseMMTN,
    ReadingMMDC,
    ReadingMMTR,
    ReadingMMXU,
    StatusValue,
)


class SolarStatus(BaseModel):
    statusValue: StatusValue | None = Field(default=None, description='Status value payload')
    solarStatusZGEN: dict[str, Any] | None = Field(default=None, description='ZGEN status payload')


class SolarReading(BaseModel):
    conductingEquipmentTerminalReading: ConductingEquipmentTerminalReading | None = None
    phaseMMTN: PhaseMMTN | None = None
    readingMMTR: ReadingMMTR | None = None
    readingMMXU: ReadingMMXU | None = None
    readingMMDC: ReadingMMDC | None = None


class SolarReadingProfile(BaseModel):
    readingMessageInfo: dict[str, Any] | None = Field(default=None, description='Reading message metadata')
    solarInverter: dict[str, Any] | None = Field(default=None, description='Owning inverter reference')
    solarReading: SolarReading | None = Field(default=None, description='Solar reading payload')


class SolarStatusProfile(BaseModel):
    statusMessageInfo: dict[str, Any] | None = Field(default=None, description='Status message metadata')
    solarInverter: dict[str, Any] | None = Field(default=None, description='Owning inverter reference')
    solarStatus: SolarStatus | None = Field(default=None, description='Solar status payload')


class SolarEventAndStatusZGEN(BaseModel):
    logicalNodeForEventAndStatus: dict[str, Any] | None = None
    AuxPwrSt: StatusValue | None = None
    DynamicTest: str | None = None
    EmgStop: StatusValue | None = None
    PointStatus: dict[str, Any] | None = None
    Alrm: str | None = None
    GnSynSt: StatusValue | None = None
    GridConnectionState: str | None = None
    ManAlrmInfo: str | None = None
    OperatingState: OperatingStateEnum | None = None


class SolarEventZGEN(BaseModel):
    solarEventAndStatusZGEN: SolarEventAndStatusZGEN | None = None
    GriMod: GridConnectModeEnum | None = None


class SolarEvent(BaseModel):
    eventValue: dict[str, Any] | None = None
    solarEventZGEN: SolarEventZGEN | None = None


class SolarEventProfile(BaseModel):
    eventMessageInfo: dict[str, Any] | None = None
    solarEvent: SolarEvent | None = None
    solarInverter: dict[str, Any] | None = None


class SolarInverter(BaseModel):
    ReserveAvailabilityProfile: list[dict[str, Any]] | None = Field(default=None, min_items=1)
    ReserveRequestProfile: list[dict[str, Any]] | None = Field(default=None, min_items=1)
    description: str | None = None
    interconnectionPlannedScheduleProfile: list[dict[str, Any]] | None = Field(default=None, min_items=1)
    interconnectionRequestedScheduleProfile: list[dict[str, Any]] | None = Field(default=None, min_items=1)
    mRID: dict[str, Any] | None = None
    name: str | None = None
    resourceDiscreteControlProfile: list[dict[str, Any]] | None = Field(default=None, min_items=1)
    resourceEventProfile: list[dict[str, Any]] | None = Field(default=None, min_items=1)
    resourceReadingProfile: list[dict[str, Any]] | None = Field(default=None, min_items=1)
    resourceStatusProfile: list[dict[str, Any]] | None = Field(default=None, min_items=1)
    solarCapabilityOverrideProfile: list[dict[str, Any]] | None = Field(default=None, min_items=1)
    solarCapabilityProfile: list[dict[str, Any]] | None = Field(default=None, min_items=1)
    solarControlProfile: list[dict[str, Any]] | None = Field(default=None, min_items=1)
    solarDiscreteControlProfile: list[dict[str, Any]] | None = Field(default=None, min_items=1)
    solarEventProfile: list[dict[str, Any]] | None = Field(default=None, min_items=1)
    solarReadingProfile: list[SolarReadingProfile] | None = Field(default=None, min_items=1)
    solarStatusProfile: list[SolarStatusProfile] | None = Field(default=None, min_items=1)
