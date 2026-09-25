import logging
import networkx as nx

_log = logging.getLogger(__name__)


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
    def __init__(self):
        self.registry = nx.DiGraph()

    def has_format(self, data_format: str) -> bool:
        return data_format in self.registry

    def lookup(self, input_format: str, output_format: str) -> list[dict]:
        """The ordered list of transform patterns that converts ``input_format`` into ``output_format``.

        An empty list means no transform is needed because the formats are the same. When no
        transform exists, :class:`TransformNotFoundError` is raised rather than returning an
        empty list, so callers can tell the two cases apart.
        """
        if input_format == output_format:
            return []
        for data_format in (input_format, output_format):
            if data_format not in self.registry:
                raise TransformNotFoundError(input_format, output_format,
                                             f'format "{data_format}" has no registered transforms')
        try:
            transform_path = nx.shortest_path(self.registry, source=input_format, target=output_format, weight='weight')
        except nx.NetworkXNoPath:
            raise TransformNotFoundError(input_format, output_format,
                                         'no sequence of registered transforms connects them') from None
        return [self.registry[s][t]['transform'] for s, t in zip(transform_path, transform_path[1:])]

    def register(self, input_format: str, output_format: str, pattern: dict | list, update: bool = False) -> bool:
        """Add the transform for one pair of formats.

        Re-registering a pair that already has a transform keeps the existing one and logs a warning,
        unless ``update`` is true, in which case it is replaced. Registering the same pattern again is
        a silent no-op. Returns whether the registry changed.
        """
        existing = self.registry.get_edge_data(input_format, output_format)
        if existing is not None:
            if existing['transform'] == pattern:
                _log.debug(f'Transform from "{input_format}" to "{output_format}" is already registered unchanged.')
                return False
            if not update:
                _log.warning(f'A different transform from "{input_format}" to "{output_format}" is already '
                             f'registered; keeping it. Pass update=True to replace it.')
                return False
        weight = 0  # TODO: How to weight graph based on lossiness of transform?
        self.registry.add_edge(input_format, output_format, transform=pattern, weight=weight)
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
            changed += self.register(*pair, definition['pattern'], update=True)
        _log.debug(f'Transform registry edges: {list(self.registry.edges)}')
        return changed
