"""Base class shared by every generated OpenFMB message class."""
from __future__ import annotations

from typing import ClassVar

from pydantic import BaseModel, ConfigDict


class OpenFMBMessage(BaseModel):
    """A protobuf message of the OpenFMB PSM in its JSON form.

    Unknown fields are rejected so that a message of the wrong shape fails validation instead of
    matching nothing. ``PROTO`` is the protobuf full name; ``PROFILE`` marks the top-level profile
    messages that adapters publish.
    """
    model_config = ConfigDict(extra='forbid', populate_by_name=True, protected_namespaces=())
    PROTO: ClassVar[str] = ''
    PROFILE: ClassVar[bool] = False
