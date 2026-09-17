import logging
import sys

from importlib.metadata import distribution, PackageNotFoundError
from typing import cast

try:
    distribution('volttron-core')
    from volttron.client.vip.agent import Agent, PubSub, RPC
    from volttron.utils import vip_main
except PackageNotFoundError:
    # noinspection PyUnresolvedReferences
    from volttron.platform.agent.utils import vip_main
    # noinspection PyUnresolvedReferences
    from volttron.platform.vip.agent import Agent, PubSub, RPC

from .transform_registry import TransformRegistry
from .mapping_engine import  ResourceNode, UAITree

_log = logging.getLogger(__name__)
__version__ = '1.0'


class PresentationService(Agent):
    def __init__(self, **kwargs):
        super(PresentationService, self).__init__(**kwargs)

        self.mapping_engine = UAITree()
        self.transform_registry = TransformRegistry()

        self.vip.config.subscribe(self.configure_main, ['NEW', 'UPDATE'], 'config')

    def configure_main(self, _, __, contents):
        self.mapping_engine.ingest_mappings(contents.get('mappings', []))
        self.transform_registry.update_registry(contents.get('transforms', []))

    @RPC.export
    def lookup_transform(self, input_format: str, output_format: str) -> dict[str, str]:
        return self.transform_registry.lookup(input_format, output_format)

    @RPC.export
    def register_transform(self, input_format: str, output_format: str, pattern: dict[str, str]):
        self.transform_registry.register(input_format, output_format, pattern)

    @PubSub.subscribe('pubsub', 'mapper/update')
    def ingest_mappings(self, _, __, ___, ____, _____, message):
        if not isinstance(message, list) or not all(isinstance(m, dict) for m in message):
            _log.warning(f'Ingest mappings expects a list of dictionaries. '
                         f'Received improperly formatted message: {message}')
        self.mapping_engine.ingest_mappings(message)

    @RPC.export
    def resolve(self, uai: tuple, as_format: str | None = None, strict: bool = False) -> dict[str, str]:
        _log.info(f'Resolving UAI: {uai}, AS FORMAT: {as_format}, STRICT: {strict}')
        node, as_format = self.mapping_engine.resolve(uai, as_format, strict)
        if node and node.is_canonical:
            resource_dict = cast(ResourceNode, node).resource.model_dump()
            if as_format:
                # Add the target data format & transform definition to the response.
                resource_dict['target_format'] = as_format
                resource_dict['transform'] = self.transform_registry.lookup(resource_dict['data_format'], as_format)
            _log.info(f'Returning canonical node: {node}, with transform {resource_dict["data_format"]} -> {as_format}')
            return resource_dict
        else:
            _log.info(f'Did not find canonical node for {uai}.')
            return {}

def main():
    vip_main(PresentationService, identity='platform.presentation', version=__version__)

if __name__ == '__main__':
    sys.exit(main())
