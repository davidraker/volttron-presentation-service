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

        # Load bundled transforms, mappings and format declarations as configuration defaults. Only JSON
        # files directly inside each package directory are loaded; subdirectories are not.
        package_root = resources.files('interoperability')
        known_transforms = self._load_bundled_definitions(package_root.joinpath('transforms'))
        known_mappings = self._load_bundled_definitions(package_root.joinpath('mappings'))
        known_formats = self._load_bundled_formats(package_root.joinpath('formats'))

        # Both the fastlib compatibility layer and upstream VOLTTRON key their
        # config store by name and match a subscription pattern against that
        # same name with fnmatch, so the default must be stored under the
        # name subscribed to below.
        self.vip.config.set_default('config', {'mappings': known_mappings, 'transforms': known_transforms,
                                               'formats': known_formats})
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

    @staticmethod
    def _load_bundled_formats(directory) -> dict[str, dict]:
        """Format declarations, ``{name: {"hub": ..., "proto": ...}}``, merged from the JSON objects in a directory."""
        formats: dict[str, dict] = {}
        if not directory.is_dir():
            return formats
        for definition_file in sorted(directory.iterdir(), key=lambda f: f.name):
            if not (definition_file.is_file() and definition_file.name.endswith('.json')):
                continue
            with definition_file.open('r') as f:
                loaded = json.load(f)
            if isinstance(loaded, dict) and all(isinstance(v, dict) for v in loaded.values()):
                formats.update(loaded)
            else:
                _log.warning(f'Ignoring bundled format file {definition_file.name}: expected an object of objects.')
        return formats

    def configure_main(self, _, __, contents):
        self.mapping_engine.ingest_mappings(contents.get('mappings', []))
        # Optional per-format declarations: {"acme_inverter": {"hub": false, "fields": ["W", "V.PhaseA", ...]},
        #                                    "openfmb.ess.reading": {"proto": "essmodule.ESSReadingProfile"}}
        for name, spec in (contents.get('formats') or {}).items():
            self.transform_registry.declare_format(name, **spec)
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
    def resolve(self, uai: tuple, as_format: str | None = None, strict: bool = False, fields: list | None = None,
                direction: str = 'read') -> dict[str, str]:
        """The canonical resource a UAI leads to, as a dict, plus what a caller needs to present it in
        ``as_format`` (or the outermost alias's format): ``target_format``, the ``transform`` chain with the
        ``path`` of formats it passes through and the ``retention`` it scored, ``parameters`` (the canonical
        resource's, overridden by each alias's, outermost winning) and, when the presenting alias declares a
        non-JSON ``encoding``, a ``codec`` naming it and the format's protobuf message. Returns ``{}`` when nothing
        canonical is found.

        ``direction`` is ``read`` (the chain presents the resource's publications in ``as_format``) or ``write``
        (the chain turns a message in ``as_format`` into the resource's own format, for a caller about to write the
        device). ``fields`` are the fields the message actually carries (dotted leaf paths, list indices as
        digits): the chain is then chosen for how many of *those* it retains rather than of every field it could."""
        _log.info(f'Resolving UAI: {uai}, AS FORMAT: {as_format}, STRICT: {strict}, DIRECTION: {direction}')
        if direction not in ('read', 'write'):
            raise ValueError(f"direction must be 'read' or 'write', not {direction!r}.")
        node, as_format, aliases = self.mapping_engine.resolve(uai, as_format, strict)
        if node and node.is_canonical:
            resource_dict = cast(ResourceNode, node).resource.model_dump()
            parameters = dict(resource_dict.get('parameters') or {})
            for alias in reversed(aliases):
                parameters.update(alias.resource.parameters)
            resource_dict['parameters'] = parameters
            encoding = next((a.resource.encoding for a in aliases if a.resource.encoding), None) or 'json'
            resource_dict['encoding'] = encoding
            if as_format:
                # Add the target data format & transform definition to the response. An empty chain means the
                # resource is already in that format; a missing chain raises TransformNotFoundError to the caller.
                resource_dict['target_format'] = as_format
                source, target = ((resource_dict['data_format'], as_format) if direction == 'read'
                                  else (as_format, resource_dict['data_format']))
                chain, retention, path = self.transform_registry.lookup_scored(source, target, fields)
                resource_dict['transform'] = chain
                resource_dict['path'], resource_dict['retention'] = path, retention
                _log.info(f'Transform {" -> ".join(path)} retains {retention:.0%} of the source fields.')
                if encoding != 'json':
                    proto = self.transform_registry.format_spec(as_format).get('proto')
                    if encoding == 'protobuf' and not proto:
                        raise ValueError(f'Alias for {uai} asks for protobuf, but format "{as_format}" declares no'
                                         f' "proto" message name in its formats entry.')
                    resource_dict['codec'] = {'encoding': encoding, 'proto': proto}
            _log.info(f'Returning canonical node: {node}, with transform {resource_dict["data_format"]} -> {as_format}')
            return resource_dict
        else:
            _log.info(f'Did not find canonical node for {uai}.')
            return {}

def main():
    vip_main(PresentationService, identity='platform.presentation', version=__version__)

if __name__ == '__main__':
    sys.exit(main())
