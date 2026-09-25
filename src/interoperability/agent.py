import json
import logging
import sys

from importlib import resources
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

        # Load bundled transforms and mappings as configuration defaults. Only JSON files directly
        # inside each package directory are loaded; subdirectories are not.
        package_root = resources.files('interoperability')
        known_transforms = self._load_bundled_definitions(package_root.joinpath('transforms'))
        known_mappings = self._load_bundled_definitions(package_root.joinpath('mappings'))

        self.vip.config.set_default({'mappings': known_mappings, 'transforms': known_transforms})
        self.mapping_engine = UAITree()
        self.transform_registry = TransformRegistry()

        self.vip.config.subscribe(self.configure_main, ['NEW', 'UPDATE'], 'config')

    @staticmethod
    def _load_bundled_definitions(directory) -> list[dict]:
        definitions = []
        if not directory.is_dir():
            return definitions
        for definition_file in sorted(directory.iterdir(), key=lambda f: f.name):
            if not (definition_file.is_file() and definition_file.name.endswith('.json')):
                continue
            with definition_file.open('r') as f:
                loaded = json.load(f)
            if isinstance(loaded, list):
                definitions.extend(loaded)
            elif isinstance(loaded, dict):
                definitions.append(loaded)
            else:
                _log.warning(f'Ignoring bundled definition file {definition_file.name}: expected a list or object.')
        return definitions

    def configure_main(self, _, __, contents):
        self.mapping_engine.ingest_mappings(contents.get('mappings', []))
        # Optional per-format declarations: {"acme_inverter": {"hub": false, "fields": ["W", "V.PhaseA", ...]}}
        for name, spec in (contents.get('formats') or {}).items():
            self.transform_registry.declare_format(name, hub=spec.get('hub'), fields=spec.get('fields'))
        self.transform_registry.update_registry(contents.get('transforms', []))

    @RPC.export
    def lookup_transform(self, input_format: str, output_format: str) -> list[dict]:
        """The transform chain between two formats: an empty list when they are the same format, or a
        TransformNotFoundError (delivered to the caller as an RPC error) when no chain exists."""
        return self.transform_registry.lookup(input_format, output_format)

    @RPC.export
    def score_transform(self, input_format: str, output_format: str, fields: list | None = None) -> dict:
        """How well the best chain between two formats preserves the source: the formats it passes through and
        the fraction of source fields (``fields`` if given, else all the chain could read) that reach the end."""
        _, retention, path = self.transform_registry.lookup_scored(input_format, output_format, fields)
        return {'path': path, 'retention': retention}

    @RPC.export
    def register_transform(self, input_format: str, output_format: str, pattern: dict | list,
                           update: bool = False, lossiness: float | None = None) -> bool:
        """Add a transform edge at runtime. An existing, different transform for the pair is kept (with a
        warning) unless ``update`` is true. ``lossiness`` (0 to 1) overrides the measured retention.
        Returns whether the registry changed."""
        return self.transform_registry.register(input_format, output_format, pattern, update=update,
                                                lossiness=lossiness)

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
                # Add the target data format & transform definition to the response. An empty chain means the
                # resource is already in that format; a missing chain raises TransformNotFoundError to the caller.
                resource_dict['target_format'] = as_format
                chain, retention, path = self.transform_registry.lookup_scored(resource_dict['data_format'], as_format)
                resource_dict['transform'] = chain
                _log.info(f'Transform {" -> ".join(path)} retains {retention:.0%} of the source fields.')
            _log.info(f'Returning canonical node: {node}, with transform {resource_dict["data_format"]} -> {as_format}')
            return resource_dict
        else:
            _log.info(f'Did not find canonical node for {uai}.')
            return {}

def main():
    vip_main(PresentationService, identity='platform.presentation', version=__version__)

if __name__ == '__main__':
    sys.exit(main())
