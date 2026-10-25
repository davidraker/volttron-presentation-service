"""OpenFMB protobuf descriptors per edition, each in its own descriptor pool.

protobuf keeps one process-wide registry of file descriptors keyed by proto file and message names, so two
editions of ``essmodule/essmodule.proto`` cannot both be imported as generated modules. Instead the serialised
``FileDescriptorSet`` of each edition (``descriptors/<edition>.binpb``, written by ``generate_descriptors.py``) is
loaded into a private :class:`DescriptorPool`, and message classes are built from it on demand. Every edition the
project knows is then available at once, and a message class is selected by ``(proto name, edition)``.

Needs the ``protobuf`` runtime (the service's ``openfmb`` extra); importing this module does not.
"""
from __future__ import annotations

import json
from functools import lru_cache
from importlib import resources
from typing import Any

from ...transform_parser import WILDCARD

_DESCRIPTORS = resources.files(__package__).joinpath('descriptors')
#: Google's own files are loaded from the runtime, not from the stored sets.
_RUNTIME_FILES = ('google/protobuf/descriptor.proto', 'google/protobuf/wrappers.proto', 'google/protobuf/timestamp.proto',
                  'google/protobuf/any.proto', 'google/protobuf/struct.proto')


@lru_cache(maxsize=None)
def manifest() -> dict[str, Any]:
    """What ``generate_descriptors.py`` recorded: ``{'editions': {edition: {tag, commit, date, files, messages}}}``."""
    return json.loads(_DESCRIPTORS.joinpath('manifest.json').read_text(encoding='utf-8'))


def editions() -> tuple[str, ...]:
    """Known editions, oldest first (``'1.0'``, ``'2.0'``, ``'2.1'``, ``'2.2'``)."""
    return tuple(sorted(manifest()['editions'], key=lambda e: tuple(int(x) for x in e.split('.'))))


def latest_edition() -> str:
    return editions()[-1]


def _runtime():
    try:
        from google.protobuf import descriptor_pb2, descriptor_pool, json_format, message_factory
    except ImportError as e:
        raise ImportError('OpenFMB protobuf support needs the "protobuf" package: install the interoperability service '
                          'with its "openfmb" extra (pip install "interoperability-service[openfmb]").') from e
    return descriptor_pb2, descriptor_pool, json_format, message_factory


@lru_cache(maxsize=None)
def pool(edition: str | None = None):
    """The private descriptor pool holding one edition (default: the newest)."""
    edition = edition or latest_edition()
    if edition not in manifest()['editions']:
        raise LookupError(f'No OpenFMB edition {edition!r}; known: {", ".join(editions())}')
    descriptor_pb2, descriptor_pool, _, _ = _runtime()
    fds = descriptor_pb2.FileDescriptorSet()
    fds.ParseFromString(_DESCRIPTORS.joinpath(f'{edition}.binpb').read_bytes())
    private = descriptor_pool.DescriptorPool()
    default = descriptor_pool.Default()
    loaded: set[str] = set()

    def load_runtime_file(name: str) -> None:
        if name in loaded:
            return
        # The default pool knows a well-known file once its generated module is imported.
        import importlib
        importlib.import_module('google.protobuf.' + name.rsplit('/', 1)[-1][:-len('.proto')] + '_pb2')
        fd = descriptor_pb2.FileDescriptorProto()
        default.FindFileByName(name).CopyToProto(fd)
        for dep in fd.dependency:
            load_runtime_file(dep)
        private.Add(fd)
        loaded.add(name)

    for fd in fds.file:
        for dep in fd.dependency:
            if dep.startswith('google/protobuf/'):
                load_runtime_file(dep)
        private.Add(fd)
        loaded.add(fd.name)
    return private


@lru_cache(maxsize=None)
def message_class(proto: str, edition: str | None = None):
    """The message class for ``proto`` (``essmodule.ESSReadingProfile``) in ``edition`` (default: the newest)."""
    _, _, _, message_factory = _runtime()
    p = pool(edition)
    try:
        descriptor = p.FindMessageTypeByName(proto)
    except KeyError as e:
        raise LookupError(f'No OpenFMB protobuf message {proto!r} in edition {edition or latest_edition()}') from e
    return message_factory.GetMessageClass(descriptor)


def profiles(edition: str | None = None, prefix: str = '', suffix: str = 'Profile') -> dict[str, str]:
    """``{message name: full name}`` of the profiles an edition defines (top-level messages named ``*Profile``)."""
    found: dict[str, str] = {}
    descriptor_pb2, _, _, _ = _runtime()
    p = pool(edition)
    for name in manifest()['editions'][edition or latest_edition()]['files']:
        for message in p.FindFileByName(name).message_types_by_name.values():
            if message.name.startswith(prefix) and message.name.endswith(suffix):
                found[message.name] = message.full_name
    return found


def profile_fields(edition: str | None = None, prefix: str = '', suffix: str = 'Profile') -> set[tuple]:
    """Leaf field paths of the matching profiles of an edition, in the protobuf JSON shape the codec produces:
    proto field names, repeated fields as wildcards, Google's wrapper types collapsed to their scalar."""
    from google.protobuf.descriptor import FieldDescriptor as FD
    universe: set[tuple] = set()

    def walk(message, prefix_path: tuple, seen: frozenset) -> None:
        for field in message.fields:
            repeated = field.is_repeated if hasattr(field, 'is_repeated') else field.label == FD.LABEL_REPEATED
            segment = (field.name, WILDCARD) if repeated else (field.name,)
            if field.type == FD.TYPE_MESSAGE and not field.message_type.full_name.startswith('google.protobuf.'):
                if field.message_type.full_name in seen:
                    continue
                walk(field.message_type, prefix_path + segment, seen | {message.full_name})
            else:
                universe.add(prefix_path + segment)

    p = pool(edition)
    for full_name in profiles(edition, prefix, suffix).values():
        walk(p.FindMessageTypeByName(full_name), (), frozenset())
    return universe
