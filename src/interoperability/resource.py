import logging
import time

from datetime import datetime, timezone
from pydantic import BaseModel, ConfigDict, Field
from typing import Any, Callable, Iterable

from .codecs import decoder_for, encoder_for
from .transform_parser import TransformParser

try:
    from volttron.utils.jsonrpc import RemoteError
except ImportError:  # pragma: no cover - the parser and models are usable without a VOLTTRON client.
    class RemoteError(Exception):
        """Stand-in so ResourceData.lookup can be imported without VOLTTRON; never raised."""
        exc_info: dict = {}

_log = logging.getLogger(__name__)


def _is_transform_not_found(error: RemoteError) -> bool:
    """Whether a RemoteError from the presentation service reports a TransformNotFoundError."""
    exc_info = getattr(error, 'exc_info', None) or {}
    return 'TransformNotFoundError' in str(exc_info.get('exc_type', '')) or 'TransformNotFoundError' in str(error)


#: The key under which a device-format message carries ordered write batches (curve writes); see the service's
#: ``dnp3_device_transforms``. Each batch is a flat ``{point: value}`` mapping whose key order is the write order.
SEQUENCE = 'sequence'

ALL, MULTI = 'all', 'multi'


def publication_topics(topic: str) -> list[str]:
    """The topics a canonical resource's values arrive on: its publication topic and, when that is a device's
    ``/all`` topic, the device's ``/multi`` topic too (pushed values are published there)."""
    topic = str(topic).rstrip('/')
    if topic.endswith(f'/{ALL}'):
        return [topic, topic[:-len(ALL)] + MULTI]
    return [topic]


def message_values(message) -> dict | None:
    """The point values of a device publication: ``[values, meta]`` (the platform driver) or a bare ``{point: value}``."""
    if isinstance(message, (list, tuple)) and message and isinstance(message[0], dict):
        return dict(message[0])
    if isinstance(message, dict):
        return dict(message)
    return None


def same_value(a, b) -> bool:
    """Equality as a device would see it: exact, or within a relative 1e-9 for numbers (not booleans)."""
    if a == b:
        return True
    if isinstance(a, (int, float)) and isinstance(b, (int, float)) and not isinstance(a, bool) and not isinstance(b, bool):
        return abs(a - b) <= 1e-9 * max(1.0, abs(a), abs(b))
    return False


def _epoch(stamp) -> float | None:
    """Seconds since the epoch for an ISO 8601 string as the driver's ``last`` RPC reports (naive means UTC)."""
    if not stamp:
        return None
    try:
        parsed = datetime.fromisoformat(str(stamp))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.timestamp()

class Resource(BaseModel):
    model_config = ConfigDict(validate_assignment=True, populate_by_name=True)
    data_format: str
    owner: str
    #: Wire encoding of the resource's messages: ``json`` (the default when unset) or ``protobuf``. For an alias it
    #: is the encoding its remote topic carries; the format declaration names the protobuf message (``proto``).
    encoding: str | None = None
    #: The edition of the wire format's standard the remote speaks, when the codec depends on it: the OpenFMB release
    #: (``'2.1'``, ``'2.2'``) whose protobuf descriptors encode and decode this alias. Unset means the newest known.
    edition: str | None = None
    #: Per-resource values transform expressions reach with ``param('name')``, e.g. ``{"mrid": "..."}`` for the
    #: device mRID an OpenFMB header carries. An alias's parameters are merged over the canonical resource's.
    parameters: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def create(cls, resource_config):
        try:
            match resource_config['resource_type'].lower():
                case 'canon' | 'canonical':
                    return CanonicalResource(**resource_config['resource'])
                case 'alias' | 'aliased':
                    return AliasedResource(**resource_config['resource'])
                case _:
                    raise TypeError(f"Resource type {resource_config['resource_type']} is not supported")
        except KeyError:
            raise TypeError(f"Malformed resource definition {resource_config['resource']}.")

class CanonicalResource(Resource):
    model_config = ConfigDict(validate_assignment=True, populate_by_name=True)
    publication_topic: str | None = None
    rpc_topic: str | None = None


class AliasedResource(Resource):
    model_config = ConfigDict(validate_assignment=True, populate_by_name=True)
    references: tuple

class ResourceData:
    def __init__(self, agent, local_topic, resource_def):
        self.agent = agent
        self.local_topic = local_topic
        self.resource_def = resource_def
        # No 'transform' (resolved without a target format) or an empty chain means the resource is already
        # in the wanted format; both compile to the identity. The resource's parameters bind param() expressions.
        parser = TransformParser(context=self.resource_def.get('parameters') or {})
        self.transform = parser.build_transform_from_schema(self.resource_def.get('transform') or [])
        # The wire codec of the target format (``codec`` from resolve): identity for JSON, else e.g. protobuf.
        codec = self.resource_def.get('codec')
        self.encode: Callable[[Any], Any] = encoder_for(codec)
        self.decode: Callable[[Any], Any] = decoder_for(codec)
        # TODO: One step further, make actual Resource (or include all this in Resource?).
        #   This version, however, does not contain all the fields of canonical nor aliased resources.
        # self.resource = Resource(**resource_def)

    def subscribe(self, callback: Callable):
        """Subscribe to the canonical resource's publications and hand ``callback`` each one, transformed and encoded:
        the device's ``.../all`` polls and, for a served device, the ``.../multi`` pushes its peer's writes arrive on."""
        def handle_incoming(peer, sender, bus, topic, headers, message):
            _log.debug(f'@@@@@ CANONICAL MESSAGE ({topic}): {message}')
            transformed_payload = self.encode(self.transform.execute(message))
            callback(peer, sender, bus, self.local_topic, headers, transformed_payload)
        results = [self.agent.vip.pubsub.subscribe(peer='pubsub', prefix=topic, callback=handle_incoming).get()
                   for topic in self.publication_topics()]
        return results[0] if results else None

    def publication_topics(self) -> list[str]:
        """The topics a canonical resource's values arrive on: its publication topic and, when that is a device's
        ``/all`` topic, the device's ``/multi`` topic too (pushed values are published there)."""
        return publication_topics(self.resource_def['publication_topic'])

    @classmethod
    def lookup(cls, agent, local_topic: tuple | list | str, delimiter='/', strict: bool = False):
        """The resource behind ``local_topic``, resolved through the presentation service. ``strict`` requires the
        UAI to name a resource exactly; without it the service falls back to the longest registered prefix, which
        suits point-level lookups but not deciding where a message that arrived on a topic belongs."""
        # Find the resource to subscribe:
        if isinstance(local_topic, list):
            uai = tuple(local_topic)
        elif isinstance(local_topic, str):
            uai = local_topic.split(delimiter)
        elif not isinstance(local_topic, tuple):
            _log.warning(f'Invalid topic received: {local_topic}')
            return None
        else:
            uai = local_topic
        try:
            resource_def = agent.vip.rpc.call('platform.presentation', 'resolve', uai, strict=strict).get()
        except RemoteError as e:
            if not _is_transform_not_found(e):
                raise
            # The topic resolves to a resource, but nothing can convert it into the format the alias asks
            # for. Treat it like an unknown resource so the caller drops the message with a warning.
            _log.warning(f'Resource {local_topic} cannot be provided in the requested format: {e.message}')
            return None
        _log.debug(f'@@@@@@@@ RESOURCE DEF: {resource_def}')
        return cls(agent, local_topic, resource_def) if resource_def else None


class ResourceWriter:
    """The points an agent means a canonical resource (a device) to hold, against what the device last reported.

    A bridge, or any other writer, asks ``select`` which of a message's points need writing: a point is written unless
    the device's last known value equals it. Knowledge of the device comes from three places, the newest winning: the
    device's own publications (``subscribe``, or ``observe`` for a caller that already receives them); this writer's
    successful writes (``record``), held as provisional knowledge until the device reports; and the platform driver's
    ``last`` RPC, asked for the points whose knowledge is missing or older than ``stale_after`` seconds (``None``, the
    default, never asks).

    Comparing with the device rather than with our own last write is what keeps a mirrored device from drifting: when
    another writer changes a point, the device's publication replaces the provisional knowledge, and the next message
    carrying the intended value writes it again. ``drifted`` lists such points for a caller that wants to re-assert
    without waiting for a message. Ordered ``sequence`` batches are always written; they are not point values.
    """

    def __init__(self, agent, rpc_topic: str, publication_topic: str | None = None, *, driver: str = 'platform.driver',
                 stale_after: float | None = None, rpc_timeout: float | None = None, clock: Callable[[], float] = time.time):
        self.agent = agent
        self.rpc_topic = str(rpc_topic).rstrip('/')
        self.publication_topic = publication_topic
        self.driver = driver
        self.stale_after = stale_after
        self.rpc_timeout = rpc_timeout
        self.clock = clock
        self.observed: dict[str, tuple[Any, float]] = {}      # point -> (value the device is known to hold, when known)
        self.intended: dict[str, Any] = {}                    # point -> value this writer last wrote successfully
        self._callbacks: list[tuple[str, Callable]] = []

    def subscribe(self) -> list[str]:
        """Follow the device's own publications (its ``/all`` polls and ``/multi`` pushes); returns the topics."""
        if not self.publication_topic or self._callbacks:
            return [t for t, _ in self._callbacks]

        def handle(peer, sender, bus, topic, headers, message):
            self.observe(message)

        for topic in publication_topics(self.publication_topic):
            self.agent.vip.pubsub.subscribe(peer='pubsub', prefix=topic, callback=handle)
            self._callbacks.append((topic, handle))
        return [t for t, _ in self._callbacks]

    def unsubscribe(self) -> None:
        for topic, handle in self._callbacks:
            try:
                self.agent.vip.pubsub.unsubscribe(peer='pubsub', prefix=topic, callback=handle)
            except Exception as e:                                                    # pragma: no cover
                _log.warning(f'{self.rpc_topic}: unable to unsubscribe from {topic}: {e!r}')
        self._callbacks.clear()

    def observe(self, message, when: float | None = None) -> None:
        """Take a publication of the device as its current values."""
        values = message_values(message)
        if values is None:
            return
        when = self.clock() if when is None else when
        for point, value in values.items():
            self.observed[point] = (value, when)

    def refresh(self, points: Iterable[str]) -> None:
        """Ask the driver what it last saw for ``points`` (its ``last`` RPC: value and update time per point topic).
        A point the driver has never seen stays unknown; a failed call is logged and leaves knowledge as it was."""
        points = [p for p in points if p != SEQUENCE]
        if not points:
            return
        topics = [f'{self.rpc_topic}/{point}' for point in points]
        try:
            pending = self.agent.vip.rpc.call(self.driver, 'last', topics)
            reported = pending.get(timeout=self.rpc_timeout) if self.rpc_timeout else pending.get()
        except Exception as e:
            _log.warning(f'{self.rpc_topic}: the driver did not report last values for {len(points)} point(s): {e!r}')
            return
        for topic, entry in (reported or {}).items():
            point = str(topic).rstrip('/').rsplit('/', 1)[-1]
            value, updated = (entry.get('value'), entry.get('updated')) if isinstance(entry, dict) else (entry, None)
            if value is None and not updated:
                continue                                                  # never read or written: still unknown
            when = _epoch(updated)
            self.observed[point] = (value, self.clock() if when is None else when)

    def select(self, values: dict, *, force: bool = False) -> dict:
        """The subset of ``values`` worth writing: every point whose value the device is not known to hold already.
        ``force`` writes everything (a caller re-asserting on purpose). Points unknown or stale are refreshed from the
        driver first when ``stale_after`` is set."""
        if force:
            return dict(values)
        if self.stale_after is not None:
            now = self.clock()
            stale = [p for p in values if p != SEQUENCE
                     and (p not in self.observed or now - self.observed[p][1] > self.stale_after)]
            if stale:
                self.refresh(stale)
        return {p: v for p, v in values.items()
                if p == SEQUENCE or p not in self.observed or not same_value(self.observed[p][0], v)}

    def record(self, written: dict, when: float | None = None) -> None:
        """What was just written successfully: intended from now on, and provisionally what the device holds."""
        when = self.clock() if when is None else when
        for point, value in (written or {}).items():
            if point == SEQUENCE:
                continue
            self.intended[point] = value
            self.observed[point] = (value, when)

    def drifted(self) -> dict[str, tuple[Any, Any]]:
        """Points the device is known to hold at a value other than the one this writer last wrote:
        ``{point: (intended, observed)}``."""
        return {p: (v, self.observed[p][0]) for p, v in self.intended.items()
                if p in self.observed and not same_value(self.observed[p][0], v)}
