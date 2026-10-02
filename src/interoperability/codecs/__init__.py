"""Wire codecs for resource payloads.

A transform chain produces a plain dict. Whether that dict travels as JSON text (the default) or as
protobuf bytes is the presenting alias's ``encoding``; ``resolve`` returns it as a ``codec`` block,
``{"encoding": "protobuf", "proto": "essmodule.ESSReadingProfile"}``, and :class:`~interoperability.resource.ResourceData`
applies the matching encoder after the chain (and decoder before it, for inbound bytes).
"""
from __future__ import annotations

from functools import partial
from typing import Any, Callable


def _identity(value: Any) -> Any:
    return value


def encoder_for(codec: dict | None) -> Callable[[Any], Any]:
    """The function turning a transform result into the wire payload for ``codec``; identity for JSON/None."""
    encoding = (codec or {}).get('encoding') or 'json'
    if encoding == 'json':
        return _identity
    if encoding == 'protobuf':
        from .openfmb import encode
        return partial(encode, _require_proto(codec))
    raise ValueError(f'Unknown encoding {encoding!r}; expected "json" or "protobuf".')


def decoder_for(codec: dict | None) -> Callable[[Any], Any]:
    """The function turning an inbound wire payload into the dict a transform reads; identity for JSON/None.
    The protobuf decoder passes anything that is not ``bytes`` through unchanged."""
    encoding = (codec or {}).get('encoding') or 'json'
    if encoding == 'json':
        return _identity
    if encoding == 'protobuf':
        from .openfmb import decode
        proto = _require_proto(codec)

        def decode_bytes(payload: Any) -> Any:
            return decode(proto, payload) if isinstance(payload, (bytes, bytearray)) else payload
        return decode_bytes
    raise ValueError(f'Unknown encoding {encoding!r}; expected "json" or "protobuf".')


def _require_proto(codec: dict) -> str:
    proto = codec.get('proto')
    if not proto:
        raise ValueError('A protobuf codec needs "proto", the fully qualified message name '
                         '(e.g. "essmodule.ESSReadingProfile") from the format declaration.')
    return proto
