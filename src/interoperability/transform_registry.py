import logging
import math
from typing import Callable, Iterable

import networkx as nx

from .field_universe import models_provider, parse_declared_fields
from .transform_parser import FieldMap, TransformParser

_log = logging.getLogger(__name__)

#: Formats that may be used as intermediate steps of a transform chain. Everything else (device
#: specific formats, for example) is a leaf: it can start or end a chain but never sits in the middle.
DEFAULT_HUBS = frozenset({'61850', 'sunspec', '2030.5', '1547', '1815.2.inputs', '1815.2.outputs'})
#: Longest chain considered; retention is poor by construction beyond this.
MAX_HOPS = 4
#: Added to every edge weight so that, at equal retention, fewer hops win.
HOP_COST = 0.01
_MIN_RETENTION = 1e-6


class TransformNotFoundError(LookupError):
    """No chain of transforms leads from ``input_format`` to ``output_format``.

    ``reason`` says why: one of the formats has never been registered, or both exist but no
    sequence of registered transforms connects them.
    """

    def __init__(self, input_format: str, output_format: str, reason: str):
        self.input_format = input_format
        self.output_format = output_format
        self.reason = reason
        super().__init__(f'No transform from "{input_format}" to "{output_format}": {reason}.')


class TransformRegistry:
    """Directed graph of transforms between formats, weighted by how much meaning each preserves.

    Every registered pattern is analysed into a :class:`FieldMap` (which source fields reach which
    target fields, at what fidelity). Lookups enumerate the candidate chains through hub formats and
    pick the one whose composed field map retains the most of the source fields; ties go to fewer
    hops. Each edge also carries an informational ``weight``, ``-ln(retention) + HOP_COST``, where
    retention is measured against the source format's field universe (see :mod:`field_universe`).
    """

    def __init__(self, hubs: Iterable[str] | None = None,
                 field_providers: Iterable[Callable[[str], set | None]] | None = None):
        self.registry = nx.DiGraph()
        self.hubs = set(DEFAULT_HUBS if hubs is None else hubs)
        self.field_providers = list(field_providers) if field_providers is not None else [models_provider]
        self.declared_fields: dict[str, set[tuple]] = {}
        self._parser = TransformParser()
        self._universe_cache: dict[str, set[tuple]] = {}
        self._weights_stale = True

    # ---- formats ----

    def declare_format(self, name: str, *, hub: bool | None = None, fields: Iterable | None = None) -> None:
        """Describe a format: whether chains may pass through it, and the fields it can carry (for formats
        without a model package, e.g. from a platform driver's registry configuration)."""
        if hub is True:
            self.hubs.add(name)
        elif hub is False:
            self.hubs.discard(name)
        if fields is not None:
            self.declared_fields[name] = parse_declared_fields(fields)
        self._invalidate()

    def has_format(self, data_format: str) -> bool:
        return data_format in self.registry

    def field_universe(self, data_format: str) -> set[tuple]:
        """Every field the format can carry: declared fields, else the first provider that knows the format,
        else the fields the registered transforms touching it mention."""
        if data_format in self._universe_cache:
            return self._universe_cache[data_format]
        universe = self.declared_fields.get(data_format)
        if universe is None:
            for provider in self.field_providers:
                universe = provider(data_format)
                if universe is not None:
                    break
        if universe is None:
            universe = set()
            for _, _, data in self.registry.out_edges(data_format, data=True):
                universe |= data['field_map'].sources()
            for _, _, data in self.registry.in_edges(data_format, data=True):
                universe |= data['field_map'].targets()
        self._universe_cache[data_format] = universe
        return universe

    def _invalidate(self):
        self._universe_cache.clear()
        self._weights_stale = True

    # ---- registration ----

    def register(self, input_format: str, output_format: str, pattern: dict | list, update: bool = False,
                 lossiness: float | None = None) -> bool:
        """Add the transform for one pair of formats.

        The pattern is analysed on registration, so a malformed definition is rejected here rather than
        when a client compiles it. ``lossiness`` (0 to 1) overrides the measured retention of the edge,
        for example from an empirical round trip. Re-registering a pair that already has a transform
        keeps the existing one and logs a warning, unless ``update`` is true, in which case it is
        replaced. Registering the same pattern again is a silent no-op. Returns whether the registry
        changed.
        """
        existing = self.registry.get_edge_data(input_format, output_format)
        if existing is not None:
            if existing['transform'] == pattern and existing.get('lossiness') == lossiness:
                _log.debug(f'Transform from "{input_format}" to "{output_format}" is already registered unchanged.')
                return False
            if not update:
                _log.warning(f'A different transform from "{input_format}" to "{output_format}" is already '
                             f'registered; keeping it. Pass update=True to replace it.')
                return False
        field_map = self._parser.field_map(pattern)
        self.registry.add_edge(input_format, output_format, transform=pattern, field_map=field_map,
                               lossiness=lossiness, weight=HOP_COST, retention=None)
        self._invalidate()
        return True

    def update_registry(self, definitions: list[dict]) -> int:
        """Apply the transform definitions of a configuration.

        The configuration is authoritative for the pairs it defines, so its definitions replace any
        earlier ones for the same pair. A pair defined more than once within the same configuration
        is a mistake: it is logged and the first definition is kept. Returns the number of pairs
        that were added or changed.
        """
        seen = set()
        changed = 0
        for definition in definitions:
            pair = (definition['input_format'], definition['output_format'])
            if pair in seen:
                _log.warning(f'Transform from "{pair[0]}" to "{pair[1]}" is defined more than once in the '
                             f'configuration; keeping the first definition.')
                continue
            seen.add(pair)
            changed += self.register(*pair, definition['pattern'], update=True, lossiness=definition.get('lossiness'))
        _log.debug(f'Transform registry edges: {list(self.registry.edges)}')
        return changed

    # ---- weights ----

    def _refresh_weights(self):
        """Recompute every edge's retention against its source format's universe and the derived weight."""
        if not self._weights_stale:
            return
        for source, _, data in self.registry.edges(data=True):
            if data.get('lossiness') is not None:
                retention = 1.0 - float(data['lossiness'])
            else:
                retention = data['field_map'].retention(self.field_universe(source))
            data['retention'] = retention
            data['weight'] = -math.log(max(retention, _MIN_RETENTION)) + HOP_COST
        self._weights_stale = False

    def edge_info(self, input_format: str, output_format: str) -> dict:
        """Measured properties of one registered transform."""
        data = self.registry.get_edge_data(input_format, output_format)
        if data is None:
            raise TransformNotFoundError(input_format, output_format, 'no transform is registered for the pair')
        self._refresh_weights()
        field_map: FieldMap = data['field_map']
        return {'retention': data['retention'], 'weight': data['weight'], 'fields': len(field_map.mappings),
                'unmapped_targets': len(field_map.nulls), 'lossiness_override': data.get('lossiness'),
                'universe': len(self.field_universe(input_format))}

    # ---- lookup ----

    def candidate_paths(self, input_format: str, output_format: str) -> list[list[str]]:
        """Every simple chain of at most MAX_HOPS transforms whose intermediate formats are hubs."""
        nodes = (self.hubs & set(self.registry.nodes)) | {input_format, output_format}
        subgraph = self.registry.subgraph(nodes)
        return list(nx.all_simple_paths(subgraph, input_format, output_format, cutoff=MAX_HOPS))

    def _chain_map(self, path: list[str]) -> FieldMap:
        composed = None
        for source, target in zip(path, path[1:]):
            step = self.registry[source][target]['field_map']
            composed = step if composed is None else composed.compose(step)
        return composed

    def lookup_scored(self, input_format: str, output_format: str,
                      fields: Iterable | None = None) -> tuple[list, float, list[str]]:
        """The best chain of transform patterns from ``input_format`` to ``output_format``, with the
        fraction of source fields it retains and the formats it passes through.

        Candidates are scored on the same set of source fields: ``fields`` if given (the fields a
        resource actually publishes), otherwise every source field any candidate's first step reads.
        Higher retention wins; ties go to fewer hops, then to the lower summed edge weight. Same input
        and output format is the identity: an empty chain retaining everything. When no chain exists,
        :class:`TransformNotFoundError` is raised rather than returning an empty list.
        """
        if input_format == output_format:
            return [], 1.0, [input_format]
        for data_format in (input_format, output_format):
            if data_format not in self.registry:
                raise TransformNotFoundError(input_format, output_format,
                                             f'format "{data_format}" has no registered transforms')
        paths = self.candidate_paths(input_format, output_format)
        if not paths:
            raise TransformNotFoundError(input_format, output_format,
                                         'no sequence of registered transforms connects them')
        self._refresh_weights()
        maps = {tuple(path): self._chain_map(path) for path in paths}
        if fields is not None:
            start = parse_declared_fields(fields)
        else:
            start = set()
            for path in paths:
                start |= self.registry[path[0]][path[1]]['field_map'].sources()
        scored = []
        for path in paths:
            retention = maps[tuple(path)].retention(start)
            weight = sum(self.registry[s][t]['weight'] for s, t in zip(path, path[1:]))
            scored.append((-retention, len(path), weight, path))
        _, _, _, best = min(scored)
        chain = [self.registry[s][t]['transform'] for s, t in zip(best, best[1:])]
        return chain, -scored[[p for *_, p in scored].index(best)][0], best

    def lookup(self, input_format: str, output_format: str, fields: Iterable | None = None) -> list:
        """The ordered list of transform patterns that converts ``input_format`` into ``output_format``.
        See :meth:`lookup_scored`; an empty list means no transform is needed."""
        return self.lookup_scored(input_format, output_format, fields)[0]
