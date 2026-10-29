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

from .transform_parser import TransformParser
from .transform_registry import TransformNotFoundError, TransformRegistry
from .mapping_engine import  ResourceNode, UAITree

_log = logging.getLogger(__name__)
__version__ = '1.0'


def _field_map_rows(field_map) -> list[dict]:
    """A field map as the UI shows it: dotted paths, fidelity, the functions applied."""
    return [{'target': '.'.join(map(str, m.target)), 'source': '.'.join(map(str, m.source)), 'fidelity': m.fidelity,
             'functions': [str(f) for f in (m.functions or ())]} for m in field_map.mappings]


class PresentationService(Agent):
    def __init__(self, **kwargs):
        super(PresentationService, self).__init__(**kwargs)

        # Load bundled transforms, mappings and format declarations as configuration defaults. Only JSON
        # files directly inside each package directory are loaded; subdirectories are not.
        package_root = resources.files('interoperability')
        known_transforms = self._load_bundled_definitions(package_root.joinpath('transforms'))
        known_mappings = self._load_bundled_definitions(package_root.joinpath('mappings'))
        known_formats = self._load_bundled_formats(package_root.joinpath('formats'))

        # The bundled definitions are the base every configuration builds on: a stored "config" entry adds the
        # deployment's device formats, transforms and mappings (a transform for a pair already bundled replaces
        # it), so the hub-to-hub transforms stay available whatever the entry declares.
        self._bundled = {'mappings': known_mappings, 'transforms': known_transforms, 'formats': known_formats}
        # Both the fastlib compatibility layer and upstream VOLTTRON key their
        # config store by name and match a subscription pattern against that
        # same name with fnmatch, so the default must be stored under the
        # name subscribed to below.
        self.vip.config.set_default('config', {})
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
        contents = contents or {}
        self.mapping_engine.ingest_mappings(self._bundled['mappings'] + list(contents.get('mappings') or []))
        # Optional per-format declarations: {"acme_inverter": {"hub": false, "fields": ["W", "V.PhaseA", ...]},
        #                                    "openfmb.ess.reading": {"proto": "essmodule.ESSReadingProfile"}}
        for name, spec in {**self._bundled['formats'], **(contents.get('formats') or {})}.items():
            self.transform_registry.declare_format(name, **spec)
        self.transform_registry.update_registry(self._bundled['transforms'])
        self.transform_registry.update_registry(list(contents.get('transforms') or []))

    @RPC.export
    def lookup_transform(self, input_format: str, output_format: str) -> list[dict]:
        """The transform chain between two formats: an empty list when they are the same format, or a
        TransformNotFoundError (delivered to the caller as an RPC error) when no chain exists."""
        return self.transform_registry.lookup(input_format, output_format)

    @RPC.export
    def transform_chain(self, input_format: str, output_format: str, fields: list | None = None) -> dict:
        """The best chain between two formats with the formats it passes through and the fraction of ``fields``
        (dotted leaf paths; else every field it could read) it retains: ``{'transform', 'path', 'retention'}``.
        Same formats give an empty chain; no chain raises TransformNotFoundError to the caller."""
        chain, retention, path = self.transform_registry.lookup_scored(input_format, output_format, fields)
        return {'transform': chain, 'path': path, 'retention': retention}

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

    # ---- what the configuration UI needs: the graph described, a pattern compiled, a message previewed ----

    @RPC.export
    def list_formats(self) -> dict:
        """Every format the registry knows, with what the UI shows of it: whether it is a hub, whether a declaration
        exists (and its ``proto``/``scaling`` when so), the size of its field universe, and the edges leaving and
        entering it. Formats that only appear as an end of a transform are listed too."""
        registry = self.transform_registry
        declared = {**{name: {} for name in registry.declared_fields}, **registry.format_specs}
        formats: dict[str, dict] = {}
        for name in sorted(set(registry.registry.nodes) | set(declared)):
            spec = declared.get(name) or {}
            formats[name] = {'hub': name in registry.hubs, 'declared': name in declared,
                             'proto': spec.get('proto'), 'scaling': spec.get('scaling'),
                             'universe': len(registry.field_universe(name)),
                             'edges_out': sorted(registry.registry.successors(name)) if name in registry.registry else [],
                             'edges_in': sorted(registry.registry.predecessors(name)) if name in registry.registry else []}
        return formats

    @RPC.export
    def list_transforms(self) -> list[dict]:
        """Every registered edge with its measured properties and whether it is bundled, replaces a bundled edge, or is
        local to this deployment's configuration."""
        bundled = {(t.get('input_format'), t.get('output_format')): t.get('pattern') for t in self._bundled['transforms']}
        edges = []
        for source, target, data in self.transform_registry.registry.edges(data=True):
            pair = (source, target)
            if pair not in bundled:
                origin = 'local'
            elif bundled[pair] == data.get('transform'):
                origin = 'bundled'
            else:
                origin = 'replaces bundled'
            edges.append({'input': source, 'output': target, 'origin': origin, 'retention': data.get('retention'),
                          'lossiness_override': data.get('lossiness'), 'fields': len(data['field_map'].mappings),
                          'unmapped_targets': len(data['field_map'].nulls)})
        return sorted(edges, key=lambda e: (e['input'], e['output']))

    @RPC.export
    def describe_transform(self, input_format: str, output_format: str) -> dict:
        """One edge in full: its pattern, every field mapping (target, source, fidelity, functions), the targets
        nothing fills, the measured retention and the source universe it is measured against."""
        data = self.transform_registry.registry.get_edge_data(input_format, output_format)
        if data is None:
            raise TransformNotFoundError(input_format, output_format, 'no transform is registered for the pair')
        info = self.transform_registry.edge_info(input_format, output_format)
        return {'input': input_format, 'output': output_format, 'pattern': data.get('transform'),
                **info, 'mappings': _field_map_rows(data['field_map']),
                'unmapped_targets': ['.'.join(map(str, n)) for n in data['field_map'].nulls],
                'source_universe': sorted('.'.join(map(str, f)) for f in self.transform_registry.field_universe(input_format))}

    @RPC.export
    def edge_report(self, input_format: str, output_format: str) -> dict:
        """What a direct transform contributes beside the alternative chains between the same formats."""
        report = self.transform_registry.edge_report(input_format, output_format)
        return {k: (sorted('.'.join(map(str, f)) for f in v) if isinstance(v, set) else v) for k, v in report.items()}

    @RPC.export
    def chain_report(self, input_format: str, output_format: str, fields: list | None = None) -> dict:
        """The chain the service would pick between two formats, hop by hop: what each hop keeps and loses, and for
        every target field of the result where it comes from, or at which hop an unfilled target is lost."""
        registry = self.transform_registry
        chain, retention, path = registry.lookup_scored(input_format, output_format, fields)
        hops, carried = [], None
        for source, target in zip(path, path[1:]):
            step = registry.registry[source][target]['field_map']
            universe = registry.field_universe(source)
            before = set(carried) if carried is not None else (set(universe) or set(step.sources()))
            kept = {f for f in before if step.fidelity_of(f) > 0}
            lost = sorted('.'.join(map(str, f)) for f in before - kept)
            hops.append({'input': source, 'output': target, 'in': len(before), 'kept': len(kept), 'lost': len(lost),
                         'lost_fields': lost[:40], 'retention': registry.registry[source][target].get('retention')})
            carried = {m.target for m in step.mappings if m.source in before or not before}
        composed = registry._chain_map(path) if len(path) > 1 else None
        targets = _field_map_rows(composed) if composed is not None else []
        unmapped = []
        if composed is not None:
            for null in composed.nulls:
                lost_at = next((f'{s} → {t}' for s, t in reversed(list(zip(path, path[1:])))
                                if null in registry.registry[s][t]['field_map'].nulls), None)
                unmapped.append({'target': '.'.join(map(str, null)), 'lost_at': lost_at})
        return {'path': path, 'retention': retention, 'hops': hops, 'targets': targets, 'unmapped_targets': unmapped}

    @RPC.export
    def compile_pattern(self, pattern: dict | list, input_format: str | None = None) -> dict:
        """Validate a transform pattern as the registry would compile it: ``ok`` with its field mappings and the
        targets nothing fills, or ``ok: false`` with the error. ``input_format`` adds the fields of that universe
        the pattern reads that the format does not have."""
        parser = TransformParser()
        # The parser reports an unknown function with a warning and skips it, which at runtime drops the field
        # silently; a client validating a pattern wants that as a refusal, so the warnings are captured.
        warnings: list[str] = []

        class _Capture(logging.Handler):
            def emit(self, record):
                warnings.append(record.getMessage())
        capture = _Capture(level=logging.WARNING)
        parser_log = logging.getLogger('interoperability.transform_parser')
        parser_log.addHandler(capture)
        try:
            field_map = parser.field_map(pattern)
            parser.build_transform_from_schema(pattern)
        except Exception as e:
            return {'ok': False, 'error': f'{type(e).__name__}: {e}', 'warnings': warnings}
        finally:
            parser_log.removeHandler(capture)
        unknown_functions = sorted({w.split('Unknown transform:')[1].strip().rstrip('.') for w in warnings if 'Unknown transform:' in w})
        result = {'ok': not unknown_functions, 'mappings': _field_map_rows(field_map),
                  'unmapped_targets': ['.'.join(map(str, n)) for n in field_map.nulls],
                  'unknown_functions': unknown_functions, 'warnings': sorted(set(warnings))}
        if unknown_functions:
            result['error'] = f"unknown function{'s' if len(unknown_functions) > 1 else ''}: {', '.join(unknown_functions)}"
        if input_format and self.transform_registry.field_universe(input_format):
            universe = self.transform_registry.field_universe(input_format)
            result['unknown_sources'] = sorted('.'.join(map(str, s)) for s in field_map.sources()
                                               if s not in universe and not any(seg == '#' for seg in s))
        return result

    @RPC.export
    def preview(self, input_format: str, output_format: str, message, fields: list | None = None) -> dict:
        """Run the chain the service would pick over one message, without writing or publishing anything."""
        chain, retention, path = self.transform_registry.lookup_scored(input_format, output_format, fields)
        transform = TransformParser().build_transform_from_schema(chain)
        return {'path': path, 'retention': retention, 'output': transform.execute(message)}

    @RPC.export
    def check_references(self) -> dict:
        """Alias reference cycles and dangling aliases, as the mapping engine finds them."""
        return self.mapping_engine.check_references()

    @RPC.export
    def discover(self, protocol: str, options: dict | None = None) -> dict:
        """Run a discovery generator and return the entries a device needs, for a client to review and store:
        the driver's device entry and registry rows, and the service configuration fragment (format, transforms,
        canonical resource and aliases). Nothing is stored here. See :mod:`interoperability.discovery.service`."""
        from .discovery.service import discover as run_discovery
        return run_discovery(protocol, options or {}, self.transform_registry)

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
            edition = next((a.resource.edition for a in aliases if a.resource.edition), None)
            resource_dict['canonical_uai'] = list(node.uai)
            resource_dict['alias_uais'] = [list(a.uai) for a in aliases]        # outermost first; empty for a canonical UAI
            if not as_format and not aliases:
                as_format = None
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
                proto = self.transform_registry.format_spec(as_format).get('proto')
                if encoding == 'json' and proto:
                    resource_dict['codec'] = {'encoding': 'json', 'proto': proto}        # the format is an OpenFMB profile
                if encoding != 'json':
                    if encoding == 'protobuf' and not proto:
                        raise ValueError(f'Alias for {uai} asks for protobuf, but format "{as_format}" declares no'
                                         f' "proto" message name in its formats entry.')
                    resource_dict['codec'] = {'encoding': encoding, 'proto': proto}
                if edition and 'codec' in resource_dict:
                    resource_dict['codec']['edition'] = edition
            _log.info(f'Returning canonical node: {node}, with transform {resource_dict["data_format"]} -> {as_format}')
            return resource_dict
        else:
            _log.info(f'Did not find canonical node for {uai}.')
            return {}

def main():
    vip_main(PresentationService, identity='platform.presentation', version=__version__)

if __name__ == '__main__':
    sys.exit(main())
