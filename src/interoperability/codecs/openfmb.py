"""Protobuf encoding of OpenFMB profiles, using the vendored ``psm-protobuf-python`` bindings.

``proto`` names are the fully qualified protobuf message, ``<module>.<Message>`` (``essmodule.ESSReadingProfile``),
which is also the ``PROTO`` attribute of the generated pydantic classes in :mod:`interoperability.models.openfmb`.
The dicts encoded here follow protobuf's JSON mapping, exactly what the transforms produce and the pydantic models
validate: wrapper types as bare scalars, enumerations by name or number, 64 bit integers as numbers or strings.
Requires the ``protobuf`` runtime (the service's ``openfmb`` extra).
"""
from __future__ import annotations

import sys
from functools import lru_cache
from importlib import import_module, resources
from typing import Any

def _bindings_path() -> str:
    return str(resources.files('interoperability.models.openfmb').joinpath('proto'))


@lru_cache(maxsize=None)
def message_class(proto: str):
    """The generated protobuf class for ``proto`` (``essmodule.ESSReadingProfile``)."""
    try:
        module_name, _, message_name = proto.rpartition('.')
        if not module_name or not message_name:
            raise ValueError(f'Expected "<module>.<Message>", got {proto!r}.')
        try:
            import google.protobuf  # noqa: F401
        except ImportError as e:
            raise ImportError('Protobuf encoding needs the "protobuf" package: install the interoperability service '
                              'with its "openfmb" extra (pip install "interoperability-service[openfmb]").') from e
        path = _bindings_path()
        if path not in sys.path:
            # The bindings import each other by top-level name (see proto/SOURCE.md).
            sys.path.append(path)
        module = import_module(f'{module_name}.{module_name}_pb2')
        return getattr(module, message_name)
    except (ImportError, AttributeError) as e:
        raise LookupError(f'No OpenFMB protobuf message {proto!r}: {e}') from e


def encode(proto: str, payload: dict) -> bytes:
    """Serialize a protobuf-JSON shaped dict as the ``proto`` message. Unknown fields are an error."""
    from google.protobuf import json_format
    return json_format.ParseDict(payload, message_class(proto)()).SerializeToString()


def decode(proto: str, data: bytes) -> dict:
    """Parse ``proto`` message bytes into the protobuf-JSON shaped dict the transforms and models use."""
    from google.protobuf import json_format
    message = message_class(proto).FromString(bytes(data))
    return json_format.MessageToDict(message, preserving_proto_field_name=True)


def validate(proto: str, payload: dict) -> Any:
    """Validate a dict against the ``proto`` message without serializing; returns the message."""
    from google.protobuf import json_format
    return json_format.ParseDict(payload, message_class(proto)())
