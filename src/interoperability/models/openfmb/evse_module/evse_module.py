from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

class CapabilityConfigurationDEAO(BaseModel):
    pass


class CapabilityConfigurationDEDO(BaseModel):
    pass


class CapabilityConfigurationDESE(BaseModel):
    pass


class CapabilityRatingsDEAO(BaseModel):
    pass


class CapabilityRatingsDEDO(BaseModel):
    pass


class CapabilityRatingsDESE(BaseModel):
    pass


class CapabilityRatingsZCAB(BaseModel):
    pass


class ChargingState(Enum):
    UNDEFINED = "UNDEFINED"
    OTHER = "other"


class ControlDEAO(BaseModel):
    pass


class ControlDEDO(BaseModel):
    pass


class ControlDEEV(BaseModel):
    pass


class ControlDESE(BaseModel):
    pass


class DEEVControlScheduleFSCH(BaseModel):
    pass


class DESEControlScheduleFSCH(BaseModel):
    pass


class DiscreteControlDESE(BaseModel):
    pass


class ENS_EVACCableCapability(Enum):
    UNDEFINED = "UNDEFINED"
    OTHER = "other"


class ENS_EVACConnectionState(Enum):
    UNDEFINED = "UNDEFINED"
    OTHER = "other"


class ENS_EVACPlugState(Enum):
    UNDEFINED = "UNDEFINED"
    OTHER = "other"


class ENS_EVConnectionCharging(Enum):
    UNDEFINED = "UNDEFINED"
    OTHER = "other"


class ENS_EVDCCableCapability(Enum):
    UNDEFINED = "UNDEFINED"
    OTHER = "other"


class ENS_EVDCConnectionStateA(Enum):
    UNDEFINED = "UNDEFINED"
    OTHER = "other"


class ENS_EVDCConnectionStateC(Enum):
    UNDEFINED = "UNDEFINED"
    OTHER = "other"


class ENS_EVDCPlugState(Enum):
    UNDEFINED = "UNDEFINED"
    OTHER = "other"


class EVACCableCapability(Enum):
    UNDEFINED = "UNDEFINED"
    OTHER = "other"


class EVACConnectionState(Enum):
    UNDEFINED = "UNDEFINED"
    OTHER = "other"


class EVACPlugState(Enum):
    UNDEFINED = "UNDEFINED"
    OTHER = "other"


class EVConnectionCharging(Enum):
    UNDEFINED = "UNDEFINED"
    OTHER = "other"


class EVDCCableCapability(Enum):
    UNDEFINED = "UNDEFINED"
    OTHER = "other"


class EVDCConnectionStateA(Enum):
    UNDEFINED = "UNDEFINED"
    OTHER = "other"


class EVDCConnectionStateC(Enum):
    UNDEFINED = "UNDEFINED"
    OTHER = "other"


class EVDCPlugState(Enum):
    UNDEFINED = "UNDEFINED"
    OTHER = "other"


class EVSE(BaseModel):
    pass


class EVSECSG(BaseModel):
    pass


class EVSECapability(BaseModel):
    pass


class EVSECapabilityOverride(BaseModel):
    pass


class EVSECapabilityOverrideProfile(BaseModel):
    pass


class EVSECapabilityProfile(BaseModel):
    pass


class EVSEControl(BaseModel):
    pass


class EVSEControlProfile(BaseModel):
    pass


class EVSECurvePoint(BaseModel):
    pass


class EVSEDiscreteControl(BaseModel):
    pass


class EVSEDiscreteControlProfile(BaseModel):
    pass


class EVSEEvent(BaseModel):
    pass


class EVSEEventProfile(BaseModel):
    pass


class EVSEFunction(BaseModel):
    pass


class EVSEPoint(BaseModel):
    pass


class EVSEPointStatus(BaseModel):
    pass


class EVSEReading(BaseModel):
    pass


class EVSEReadingDESE(BaseModel):
    pass


class EVSEReadingProfile(BaseModel):
    pass


class EVSEStatus(BaseModel):
    pass


class EVSEStatusProfile(BaseModel):
    pass


class EventAndStatusDEAO(BaseModel):
    pass


class EventAndStatusDEDO(BaseModel):
    pass


class EventAndStatusDEEV(BaseModel):
    pass


class EventAndStatusDESE(BaseModel):
    pass


class ReadingDEAO(BaseModel):
    pass


class ReadingDEDO(BaseModel):
    pass


class ReadingDEEV(BaseModel):
    pass
