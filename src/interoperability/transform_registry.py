import logging
import networkx as nx

_log = logging.getLogger(__name__)


class TransformRegistry:
    def __init__(self):
        self.registry = nx.DiGraph()

    def lookup(self, input_format: str, output_format: str) -> list[dict[str, str]]:
        try:
            transform_path = nx.shortest_path(self.registry, source=input_format, target=output_format, weight='weight')
            transform_edges = zip(transform_path, transform_path[1:])
            transform_chain = [self.registry[s][t].get('transform') for s, t in transform_edges]
            # TODO: What if we are missing a transform definition? Should this even be possible?
            return transform_chain
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            # NodeNotFound is raised when either format has never been registered at all.
            # TODO: What do we actually do where there is not a path? Is it OK to just return the empty list?
            _log.warning(f'No transform path found from format "{input_format}" to target format "{output_format}"')
            return []

    def register(self, input_format: str, output_format: str, pattern: dict[str, str], update=False):
        if self.registry.edges.get((input_format, output_format)) is not None and update:
            # TODO: We could test for equality before logging an error message.
            _log.warning(f'Attempted to register a transform from "{input_format}" to "{output_format}"'
                         f' that already exists. Use update=True to update the existing transform.')
        else:
            weight = 0 # TODO: How to weight graph based on lossiness of transform?
            self.registry.add_edge(input_format, output_format, transform=pattern, weight=weight)

    def update_registry(self, definitions: list[dict]):
        for definition in definitions:
            self.register(definition['input_format'], definition['output_format'], definition['pattern'])
        _log.debug(f'@@@@@@ TRANSFORM_REGISTRY: ')
        _log.debug(self.registry.edges(data=True))
