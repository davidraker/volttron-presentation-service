"""The IEC 61850 vocabulary the ``61850`` hub format is checked against.

Read from the IEC name space definition (NSD) files of IEC 61850-7-420 Edition 2, 7-4 and 7-3: logical node classes
and their data objects (inherited through the abstract classes), common data classes with their attributes and
sub-data objects, constructed attribute types and enumerations. The files are IEC code components and are not
redistributed with this package; ``IEC61850_NSD`` names the directory holding them (any file names: each file is
recognised by the ``id`` of its root ``NS`` element).

``resolve(path)`` says whether one hub path is a 61850 name under the hub's flattening rules (HUB_61850_FORMAT.md §2.3):
``LN.DO`` is the flattened value, ``LN.DO.sub`` descends into sub-data objects and attributes of the data object's
common data class, ``[n]`` or ``[#]`` is allowed only where the standard declares an array. Groups prefixed ``x-``
are hub extensions outside the standard and are checked against an allowlist instead.
"""
from __future__ import annotations

import os
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

NSD_ENV = 'IEC61850_NSD'
EXTENSION_PREFIX = 'x-'
_NS = '{http://www.iec.ch/61850/2016/NSD}'


@dataclass
class DataObject:
    name: str
    cdc: str
    is_array: bool = False
    pres_cond: str = ''
    owner: str = ''     # the class that declares it (an abstract class for inherited objects)


@dataclass
class LNClass:
    name: str
    part: str
    base: str | None = None
    abstract: bool = False
    own: dict[str, DataObject] = field(default_factory=dict)


@dataclass
class CDC:
    name: str
    attributes: dict[str, str] = field(default_factory=dict)       # attribute name -> type name
    sub_objects: dict[str, str] = field(default_factory=dict)      # sub data object name -> CDC name
    arrays: set[str] = field(default_factory=set)


@dataclass
class Resolution:
    path: tuple
    status: str        # 'ok', 'extension' or a violation category
    detail: str = ''

    @property
    def ok(self) -> bool:
        return self.status in ('ok', 'extension')


class Vocabulary:
    def __init__(self):
        self.classes: dict[str, LNClass] = {}
        self.cdcs: dict[str, CDC] = {}
        self.constructed: dict[str, dict[str, str]] = {}
        self.enumerations: dict[str, dict[str, int]] = {}
        self.parts: dict[str, str] = {}       # part id -> version string
        self.extensions: dict[str, set[str]] = {}    # x- group -> allowed data object names ('*' = any)
        self.instances: dict[str, set[int]] = {}      # class -> instance numbers the hub documents (PTOV: {1, 2})
        self.extension_objects: dict[str, set[str]] = {}    # class -> x- data objects allowed on it ('*' = any)

    # ---- loading
    def read(self, path: Path) -> str | None:
        """Parse one NSD file; return the part it describes or None when it is not a name space file."""
        root = ET.parse(path).getroot()
        if root.tag != f'{_NS}NS':
            return None
        part = root.get('id', '')
        self.parts[part] = f"{root.get('version', '')}{root.get('revision', '')}{root.get('release', '')}"
        for tag, abstract in ((f'{_NS}LNClass', False), (f'{_NS}AbstractLNClass', True)):
            for el in root.iter(tag):
                # 7-420 extends some 7-4 classes (MMXU, LPHD) under the same name: merge rather than replace.
                cls = self.classes.get(el.get('name')) or LNClass(el.get('name'), part, el.get('base'), abstract)
                cls.base = cls.base or el.get('base')
                for do in el.findall(f'{_NS}DataObject'):
                    cls.own.setdefault(do.get('name'), DataObject(do.get('name'), do.get('type', ''), do.get('isArray') == 'true',
                                                                  do.get('presCond', ''), cls.name))
                self.classes[cls.name] = cls
        for el in root.iter(f'{_NS}CDC'):
            cdc = self.cdcs.setdefault(el.get('name'), CDC(el.get('name')))
            for a in el.findall(f'{_NS}DataAttribute'):
                cdc.attributes[a.get('name')] = a.get('type', '')
                if a.get('isArray') == 'true':
                    cdc.arrays.add(a.get('name'))
            for s in el.findall(f'{_NS}SubDataObject'):
                cdc.sub_objects[s.get('name')] = s.get('type', '')
        for el in root.iter(f'{_NS}ConstructedAttribute'):
            self.constructed[el.get('name')] = {a.get('name'): a.get('type', '') for a in el.findall(f'{_NS}SubDataAttribute')}
        for el in root.iter(f'{_NS}Enumeration'):
            self.enumerations[el.get('name')] = {l.get('name'): int(l.get('literalVal')) for l in el.findall(f'{_NS}Literal')
                                                 if l.get('literalVal') not in (None, '')}
        return part

    # ---- queries
    def data_objects(self, class_name: str) -> dict[str, DataObject]:
        """The class's data objects including those inherited through its base chain."""
        out: dict[str, DataObject] = {}
        seen = set()
        name = class_name
        while name and name in self.classes and name not in seen:
            seen.add(name)
            cls = self.classes[name]
            for k, v in cls.own.items():
                out.setdefault(k, v)
            name = cls.base
        return out

    def concrete_classes(self) -> set[str]:
        return {n for n, c in self.classes.items() if not c.abstract}

    def resolve(self, path: Iterable[str]) -> Resolution:
        path = tuple(str(p) for p in path)
        if not path:
            return Resolution(path, 'empty')
        group = path[0]
        if group.startswith(EXTENSION_PREFIX):
            allowed = self.extensions.get(group)
            if allowed is None:
                return Resolution(path, 'extension-unknown', f'{group} is not an allowed hub extension')
            if len(path) > 1 and '*' not in allowed and _strip_index(path[1]) not in allowed:
                return Resolution(path, 'extension-unknown', f'{path[1]} is not declared for {group}')
            return Resolution(path, 'extension')
        if ' ' in group:
            return Resolution(path, 'group-with-space', group)
        if re.search(r'\d$', group) and _strip_number(group) in self.classes:
            base, number = _strip_number(group), int(re.search(r'(\d+)$', group).group(1))
            if number not in self.instances.get(base, set()):
                return Resolution(path, 'numbered-instance', f'{group} is {base} with an instance number the hub does not document')
            group = base
        if group.endswith('n') and group[:-1] in self.classes:
            return Resolution(path, 'placeholder-instance', f'{group} is a placeholder for {group[:-1]} instances')
        cls = self.classes.get(group)
        if cls is None or cls.abstract:
            return Resolution(path, 'unknown-class', group)
        if len(path) == 1:
            return Resolution(path, 'ok')
        dos = self.data_objects(group)
        do_name, do_index = _split_index(path[1])
        if do_name.startswith(EXTENSION_PREFIX):
            allowed = self.extension_objects.get(group, set())
            if '*' in allowed or do_name in allowed:
                return Resolution(path, 'extension')
            return Resolution(path, 'extension-unknown', f'{group}.{do_name} is not a declared extension object')
        if do_name in self.classes and do_name not in dos:
            return Resolution(path, 'class-nested-under-class', f'{do_name} is a logical node class, not a data object of {group}')
        do = dos.get(do_name)
        if do is None:
            return Resolution(path, 'unknown-data-object', f'{group} has no data object {do_name}')
        if do_index and not do.is_array:
            return Resolution(path, 'array-on-scalar', f'{group}.{do_name} is not an array')
        return self._resolve_attributes(path, do.cdc, path[2:], f'{group}.{do_name}', in_array=do.is_array)

    def _resolve_attributes(self, path, cdc_name, rest, where, in_array=False) -> Resolution:
        if not rest:
            return Resolution(path, 'ok')
        if rest[0] == '*':      # a list element: allowed only directly under an array
            if not in_array:
                return Resolution(path, 'array-on-scalar', f'{where} is not an array')
            return self._resolve_attributes(path, cdc_name, rest[1:], where)
        seg, index = _split_index(rest[0])
        cdc = self.cdcs.get(cdc_name)
        if cdc is None:
            # A constructed attribute (AnalogueValue, Vector, Point): its sub-attributes end the path.
            sub = self.constructed.get(cdc_name)
            if sub is None:
                return Resolution(path, 'unknown-attribute', f'{where} ({cdc_name}) has no attribute {seg}')
            if seg not in sub:
                return Resolution(path, 'unknown-attribute', f'{where} ({cdc_name}) has no sub-attribute {seg}')
            return self._resolve_attributes(path, sub[seg], rest[1:], f'{where}.{seg}')
        if seg in cdc.sub_objects:
            return self._resolve_attributes(path, cdc.sub_objects[seg], rest[1:], f'{where}.{seg}')
        if cdc_name == 'CMV' and seg in ('mag', 'ang'):     # flattening rule: a complex value's cVal level is elided
            return self._resolve_attributes(path, 'AnalogueValue', rest[1:], f'{where}.{seg}')
        if seg in cdc.attributes:
            if index and seg not in cdc.arrays:
                return Resolution(path, 'array-on-scalar', f'{where}.{seg} is not an array')
            return self._resolve_attributes(path, cdc.attributes[seg], rest[1:], f'{where}.{seg}', in_array=seg in cdc.arrays)
        if ' ' in seg or seg[:1].islower() and any(seg in lits for lits in self.enumerations.values()):
            return Resolution(path, 'label-as-key', f'{where}: "{seg}" is an enumeration literal, not an attribute')
        return Resolution(path, 'unknown-attribute', f'{where} ({cdc_name}) has no attribute {seg}')


def _split_index(segment: str) -> tuple[str, str]:
    m = re.match(r'^([^\[]+)(\[.*\])?$', segment)
    return (m.group(1), m.group(2) or '') if m else (segment, '')


def _strip_index(segment: str) -> str:
    return _split_index(segment)[0]


def _strip_number(group: str) -> str:
    return re.sub(r'\d+$', '', group)


def load(directory: str | os.PathLike | None = None) -> Vocabulary | None:
    """The vocabulary from the NSD files in ``directory`` (default ``$IEC61850_NSD``), or None when there are none."""
    directory = directory or os.environ.get(NSD_ENV)
    if not directory or not Path(directory).is_dir():
        return None
    vocab = Vocabulary()
    for f in sorted(Path(directory).iterdir()):
        if f.suffix.lower() in ('.nsd', '.xml'):
            try:
                vocab.read(f)
            except ET.ParseError:
                continue
    return vocab if vocab.classes else None


def report(vocab: Vocabulary, paths: Iterable[tuple]) -> dict:
    """Resolve every path; group the violations by category and by hub group."""
    out = {'total': 0, 'ok': 0, 'extension': 0, 'violations': {}, 'by_group': {}}
    for p in sorted(paths, key=lambda x: tuple(str(s) for s in x)):
        r = vocab.resolve(p)
        out['total'] += 1
        if r.status in ('ok', 'extension'):
            out[r.status] += 1
            continue
        out['violations'].setdefault(r.status, []).append(r)
        out['by_group'].setdefault(str(p[0]), {}).setdefault(r.status, 0)
        out['by_group'][str(p[0])][r.status] += 1
    return out


def main(argv=None):
    import argparse
    import glob
    import json
    parser = argparse.ArgumentParser(description='Check the 61850 hub keys against the IEC 61850 NSD vocabulary.')
    parser.add_argument('--nsd', default=None, help=f'directory of NSD files (default ${NSD_ENV})')
    parser.add_argument('--transforms', default=str(Path(__file__).parent / 'transforms'))
    parser.add_argument('--examples', type=int, default=6, help='examples per category')
    args = parser.parse_args(argv)
    vocab = load(args.nsd)
    if vocab is None:
        parser.error(f'no NSD files found; set {NSD_ENV}')
    from .transform_registry import TransformRegistry
    reg = TransformRegistry()
    for f in sorted(glob.glob(os.path.join(args.transforms, '*.json'))):
        reg.update_registry(json.load(open(f)))
    paths = reg.field_universe('61850')
    rep = report(vocab, paths)
    print(f"parts: {', '.join(f'{k} {v}' for k, v in sorted(vocab.parts.items()))}")
    print(f"hub paths {rep['total']}: ok {rep['ok']}, extensions {rep['extension']}, violations {rep['total'] - rep['ok'] - rep['extension']}")
    for cat, items in sorted(rep['violations'].items(), key=lambda kv: -len(kv[1])):
        print(f'\n{cat}: {len(items)}')
        for r in items[:args.examples]:
            print(f"   {'.'.join(map(str, r.path))}  -- {r.detail}")
    print('\nby group (violations):')
    for g, cats in sorted(rep['by_group'].items(), key=lambda kv: -sum(kv[1].values())):
        print(f"   {g:<12} {sum(cats.values()):>4}  {', '.join(f'{c} {n}' for c, n in sorted(cats.items()))}")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
