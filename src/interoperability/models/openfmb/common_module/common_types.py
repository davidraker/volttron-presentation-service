from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class Phase(str, Enum):
    A = 'A'
    B = 'B'
    C = 'C'
    N = 'N'
    AB = 'AB'
    BC = 'BC'
    CA = 'CA'
    ABC = 'ABC'
    ABCN = 'ABCN'
    AN = 'AN'
    BN = 'BN'
    CN = 'CN'
    NONE = 'none'


class PhaseMMTN(BaseModel):
    phase: Phase | None = None
    n: str | None = None


class TimeAccuracy(str, Enum):
    MICROSECONDS = 'microseconds'
    MILLISECONDS = 'milliseconds'
    SECONDS = 'seconds'
    MINUTES = 'minutes'
    UNDEFINED = 'UNDEFINED'


class GridConnectMode(str, Enum):
    GRID_CONNECTED = 'GRID_CONNECTED'
    ISLANDED = 'ISLANDED'
    DEENERGIZED = 'DEENERGIZED'
    UNKNOWN = 'UNKNOWN'


class OperatingState(str, Enum):
    ON = 'ON'
    OFF = 'OFF'
    STANDBY = 'STANDBY'
    UNKNOWN = 'UNKNOWN'


class StatusValue(BaseModel):
    value: str | None = Field(default=None, description='Status value')
    quality: str | None = Field(default=None, description='Quality string')


class ReadingMMTR(BaseModel):
    value: float | None = Field(default=None, description='Value for MMTR reading')
    unit: str | None = Field(default='W', description='unit')


class ReadingMMXU(BaseModel):
    value: float | None = Field(default=None, description='Value for MMXU reading')
    unit: str | None = Field(default='W', description='unit')


class ReadingMMDC(BaseModel):
    value: float | None = Field(default=None, description='DC measurement value')
    unit: str | None = Field(default='V', description='unit')


class ConductingEquipmentTerminalReading(BaseModel):
    terminal: str | None = None
    value: float | None = None
    quality: str | None = None
    mRID: dict[str, Any] | None = None
