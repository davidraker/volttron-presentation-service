"""Extract the protobuf file descriptors of every OpenFMB edition from the ``psm-protobuf-python`` bindings.

Each edition of OpenFMB is a tag of the OpenFMB Users Group's ``psm-protobuf-python`` repository (``v1.0.0``,
``v2.0.0``, ``v2.1.0``, ``v2.2.0``; https://github.com/OpenFMB-Users-Group/psm-protobuf-python). Point the
``OPENFMB_PSM_PROTOBUF_PYTHON`` environment variable at a clone with its tags fetched, or pass ``--clone``. A generated ``*_pb2.py`` module is, essentially, one serialised ``FileDescriptorProto``: this script
reads that byte string out of each module's source at each tag (without importing the modules, which would
register every edition in protobuf's shared default pool and fail on the second), orders the files by dependency
and writes one binary ``FileDescriptorSet`` per edition into ``descriptors/<edition>.binpb``, plus
``descriptors/manifest.json`` with the tag, commit, date and module list behind each. Google's well-known types
(``wrappers.proto``, ``descriptor.proto``) are not stored: they come from the protobuf runtime.

At runtime ``descriptors.py`` builds one private ``DescriptorPool`` per edition from these sets, so the codec can
encode and decode any edition in one process (see ``interoperability.codecs.openfmb``).

Run from the ``interoperability_service`` directory::

    python src/interoperability/models/openfmb/generate_descriptors.py [--clone PATH] [--tags v2.1.0 v2.2.0] [--out DIR]
"""
from __future__ import annotations

import argparse
import ast
import json
import os
import re
import subprocess
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
CLONE_ENV = 'OPENFMB_PSM_PROTOBUF_PYTHON'
OUT = HERE / 'descriptors'


def git(clone: Path, *args: str) -> str:
    return subprocess.run(['git', '-C', str(clone), *args], check=True, capture_output=True, text=True).stdout


def edition_of(tag: str) -> str:
    """``v2.2.0`` -> ``2.2`` (OpenFMB releases are named by their first two components)."""
    m = re.fullmatch(r'v?(\d+)\.(\d+)(?:\.\d+)?', tag)
    if not m:
        raise ValueError(f'Tag {tag!r} is not a version tag')
    return f'{m.group(1)}.{m.group(2)}'


def serialized_descriptor(source: str) -> bytes:
    """The serialised FileDescriptorProto embedded in a generated ``*_pb2.py`` module, any protoc generation.

    New-style modules call ``_descriptor_pool.Default().AddSerializedFile(b'...')``; old-style ones pass
    ``serialized_pb=b'...'`` or ``serialized_pb=_b('...')`` (a latin-1 string for Python 2 compatibility) to
    ``FileDescriptor(...)``.
    """
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = ast.unparse(node.func)
            if func.endswith('AddSerializedFile') and node.args and isinstance(node.args[0], ast.Constant):
                return node.args[0].value
            if func.endswith('FileDescriptor'):
                for kw in node.keywords:
                    if kw.arg == 'serialized_pb':
                        value = kw.value
                        if isinstance(value, ast.Call) and isinstance(value.args[0], ast.Constant):
                            raw = value.args[0].value
                            return raw if isinstance(raw, bytes) else raw.encode('latin1')
                        if isinstance(value, ast.Constant):
                            raw = value.value
                            return raw if isinstance(raw, bytes) else raw.encode('latin1')
    raise ValueError('no serialised descriptor found in module')


def collect(clone: Path, tag: str) -> dict[str, bytes]:
    """``{proto file name: serialised FileDescriptorProto}`` for every generated module at ``tag``."""
    from google.protobuf import descriptor_pb2
    files: dict[str, bytes] = {}
    for path in git(clone, 'ls-tree', '-r', '--name-only', tag).split():
        if not path.endswith('_pb2.py'):
            continue
        raw = serialized_descriptor(git(clone, 'show', f'{tag}:{path}'))
        fd = descriptor_pb2.FileDescriptorProto()
        fd.ParseFromString(raw)
        files[fd.name] = raw
    return files


def ordered(files: dict[str, bytes]) -> list[bytes]:
    """The descriptors in dependency order (dependencies first), Google's own files left out."""
    from google.protobuf import descriptor_pb2
    protos = {}
    for name, raw in files.items():
        fd = descriptor_pb2.FileDescriptorProto()
        fd.ParseFromString(raw)
        protos[name] = fd
    out: list[bytes] = []
    done: set[str] = set()

    def visit(name: str) -> None:
        if name in done or name not in protos:
            return
        for dep in protos[name].dependency:
            visit(dep)
        done.add(name)
        out.append(files[name])

    for name in sorted(protos):
        visit(name)
    return out


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--clone', type=Path, default=None, help=f'clone of psm-protobuf-python (default: ${CLONE_ENV})')
    parser.add_argument('--tags', nargs='*', default=None, help='tags to extract (default: every v* tag)')
    parser.add_argument('--out', type=Path, default=OUT)
    args = parser.parse_args(argv)
    if args.clone is None:
        if not os.environ.get(CLONE_ENV):
            raise SystemExit(f'Set {CLONE_ENV} to a clone of https://github.com/OpenFMB-Users-Group/psm-protobuf-python or pass --clone.')
        args.clone = Path(os.environ[CLONE_ENV]).expanduser()
    from google.protobuf import descriptor_pb2
    tags = args.tags or [t for t in git(args.clone, 'tag', '-l').split() if re.fullmatch(r'v\d+\.\d+\.\d+', t)]
    args.out.mkdir(parents=True, exist_ok=True)
    collected = {tag: collect(args.clone, tag) for tag in tags}
    manifest: dict[str, dict] = {}
    for tag in sorted(tags, key=lambda t: tuple(int(x) for x in t[1:].split('.'))):
        files = dict(collected[tag])
        borrowed = []
        # A tag may ship modules whose dependency it does not ship (v1.0.0 lacks uml.proto): take the nearest later
        # tag's copy, since the custom options it defines are stable.
        for name, raw in list(files.items()):
            fd = descriptor_pb2.FileDescriptorProto()
            fd.ParseFromString(raw)
            for dep in fd.dependency:
                if dep not in files and not dep.startswith('google/protobuf/'):
                    donor = next((t for t in sorted(collected, key=lambda t: tuple(int(x) for x in t[1:].split('.')))
                                  if dep in collected[t]), None)
                    if donor is None:
                        raise SystemExit(f'{tag}: {name} depends on {dep}, found in no tag')
                    files[dep] = collected[donor][dep]
                    borrowed.append(f'{dep} from {donor}')
        fds = descriptor_pb2.FileDescriptorSet()
        for raw in ordered(files):
            fds.file.add().ParseFromString(raw)
        edition = edition_of(tag)
        (args.out / f'{edition}.binpb').write_bytes(fds.SerializeToString())
        manifest[edition] = {
            'tag': tag,
            'commit': git(args.clone, 'rev-list', '-n', '1', tag).strip(),
            'date': git(args.clone, 'log', '-1', '--format=%cs', tag).strip(),
            'files': [f.name for f in fds.file],
            'messages': sum(len(f.message_type) for f in fds.file),
            'borrowed': borrowed,
        }
        print(f'{edition}: {tag} ({manifest[edition]["date"]}), {len(fds.file)} files, {manifest[edition]["messages"]} messages'
              + (f', borrowed {borrowed}' if borrowed else ''))
    (args.out / 'manifest.json').write_text(json.dumps({'generated': date.today().isoformat(), 'source': 'psm-protobuf-python (OpenFMB Users Group)',
                                                         'editions': manifest}, indent=2) + '\n')


if __name__ == '__main__':
    main()
