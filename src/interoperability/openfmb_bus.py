"""OpenFMB on the VOLTTRON message bus: the convention the Device Adapter and the Message Bus Adapter share.

An OpenFMB profile travels on VOLTTRON's own bus on the topic it would have on the OpenFMB bus
(``openfmb/<module>/<Profile>/<mRID>``, which is also the alias UAI the presentation service knows it by), as the
protobuf-JSON dict the service's ``openfmb.*`` formats use, with headers naming the protobuf message and the agent
that put it there. Any OpenFMB-aware agent can publish a control profile or consume a reading profile this way; the
Message Bus Adapter (``mode: relay``) re-serialises them to and from the foreign bus, the Device Adapter translates
them to and from devices.
"""
from typing import Any

CONTENT_TYPE = 'application/openfmb+json'
HEADER_CONTENT_TYPE = 'Content-Type'
HEADER_PROTO = 'openfmb-proto'        #: the protobuf message name, e.g. ``essmodule.ESSControlProfile``
HEADER_ORIGIN = 'openfmb-origin'      #: VIP identity of the agent that put the message on the VOLTTRON bus
HEADER_REMOTE = 'openfmb-remote'      #: for a message relayed in from a foreign bus: that remote's id


def topic_of(uai) -> str:
    """The VOLTTRON topic of an OpenFMB alias: its UAI segments joined with ``/``."""
    return '/'.join(str(s) for s in uai)


def headers(proto: str | None, origin: str, remote: Any = None) -> dict[str, str]:
    result = {HEADER_CONTENT_TYPE: CONTENT_TYPE, HEADER_ORIGIN: str(origin)}
    if proto:
        result[HEADER_PROTO] = proto
    if remote is not None:
        result[HEADER_REMOTE] = str(remote)
    return result


def is_openfmb(message_headers: dict | None) -> bool:
    return bool(message_headers) and message_headers.get(HEADER_CONTENT_TYPE) == CONTENT_TYPE


def origin_of(message_headers: dict | None) -> str | None:
    return (message_headers or {}).get(HEADER_ORIGIN)


def proto_of(message_headers: dict | None) -> str | None:
    return (message_headers or {}).get(HEADER_PROTO)
