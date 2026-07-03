import logging

from collections import defaultdict

_log = logging.getLogger(__name__)


class TransformRegistry:
    def __init__(self):
        self.registry = defaultdict(dict)  # TODO: This should become a weighted, directed graph with stackable nodes.

    def lookup(self, input_format: str, output_format: str) -> dict[str, str]:
        # TODO: This function should find the optimal path through a weighted graph and chain the nodes of the path.
        return self.registry[output_format].get(input_format) if self.registry.get(output_format) else {}

    def register(self, input_format: str, output_format: str, pattern: dict[str, str]):
        # TODO: This should store the pattern in a weighted graph where weight is based on lossiness of transform.
        self.registry[output_format][input_format] = pattern

    def update_registry(self, definitions: list[dict[str, str | dict]]):
        for definition in definitions:
            self.register(definition['input_format'], definition['output_format'], definition['pattern'])
        _log.debug(f'@@@@@@ TRANSFORM_REGISTRY: ')
        _log.debug(self.registry)
