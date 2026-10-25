"""Protobuf encoding of OpenFMB profiles, for every edition the project knows.

``proto`` names are the fully qualified protobuf message, ``<module>.<Message>`` (``essmodule.ESSReadingProfile``),
as the format declaration's ``proto`` entry gives them; ``edition`` (``'2.1'``, ``'2.2'``; default the newest) is the
OpenFMB release the peer speaks, from the alias declaration. Each edition's descriptors live in their own pool (see
:mod:`interoperability.models.openfmb.descriptors`), so a 2.1 participant and a 2.2 participant can be served from one
process; nothing on the wire names the edition, so the alias has to.

The dicts encoded here follow protobuf's JSON mapping, exactly what the transforms produce and the pydantic models
validate: proto field names, enumerations by name, wrapper types collapsed to scalars.

Requires the ``protobuf`` runtime (the service's ``openfmb`` extra).
"""
from __future__ import annotations

from typing import Any

from ..models.openfmb import descriptors

editions = descriptors.editions
latest_edition = descriptors.latest_edition


def message_class(proto: str, edition: str | None = None):
    """The generated protobuf class for ``proto`` in ``edition``; ``LookupError`` when either is unknown."""
    return descriptors.message_class(proto, edition)


def encode(proto: str, payload: dict, edition: str | None = None) -> bytes:
    """Serialize a protobuf-JSON shaped dict as the ``proto`` message of ``edition``. Unknown fields are an error."""
    from google.protobuf import json_format
    return json_format.ParseDict(payload, message_class(proto, edition)()).SerializeToString()


def decode(proto: str, data: bytes, edition: str | None = None) -> dict:
    """Parse ``proto`` message bytes of ``edition`` into the protobuf-JSON shaped dict the transforms and models use."""
    from google.protobuf import json_format
    message = message_class(proto, edition).FromString(bytes(data))
    return json_format.MessageToDict(message, preserving_proto_field_name=True)


def validate(proto: str, payload: dict, edition: str | None = None) -> Any:
    """Validate a dict against the ``proto`` message of ``edition`` without serializing; returns the message."""
    from google.protobuf import json_format
    return json_format.ParseDict(payload, message_class(proto, edition)())
