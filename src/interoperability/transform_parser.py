"""Parser for transform definitions.

A definition is a *pattern*: a dict whose keys are output fields and whose values are either
transform expressions (strings), nested groups (dicts) or ``null`` (field with no known source).

Expression syntax::

    transform[<source path>](<function>(<args>), ...)

The bracketed source path is a comma separated list of segments (bare words, integers or quoted
strings) locating the value in the input message. When it is omitted the output key path is used.
Functions from :mod:`interoperability.transforms` are applied to the value in order.

Repeated groups
---------------
An output key ending in ``[#]`` produces a list: the group beneath it is evaluated once per element
of a source list. Inside the group, a source segment ``Name[#]`` (quoted or bare) names the list and
marks the iteration point; the segments after it are looked up in each element::

    "CurveData[#]": {"xvalue": "transform[705, Crv, 0, Pt[#], V]()",
                     "yvalue": "transform[705, Crv, 0, Pt[#], Var]()"}

All expressions in the group must agree on the list. Alternatively the reserved ``"#"`` entry names
the list explicitly, and sibling paths then start with the bare segment ``#``::

    "Crv[#]": {"#": "transform[DERCurve, opModVoltVar](as_list())",
               "ActPt": "transform[#, CurveData](count())",
               "Pt[#]": {"V": "transform[#, CurveData[#], xvalue]()"}}

A ``"#"`` entry that omits its own source path (``"#": "transform(take(4))"``) applies its functions
to the implicitly named list; if no path in the group names a list either, it applies them to the
enclosing element itself (``"#": "transform(as_list())"`` turns the current message into a
one-element list). Expressions without a marker inside a repeated group are resolved against the
message root, so constants and shared fields can be repeated into every element. Groups nest: an
expression with several markers is relative to the innermost enclosing element. A repeated group
whose list is absent or empty is omitted from the output, and elements whose fields are all missing
are dropped.

Several repeated groups may feed one output list by adding a label after the marker; the lists are
concatenated in pattern order::

    "sequence[#] volt-var": {...},
    "sequence[#] volt-watt": {...}

Spread entries
--------------
A key starting with ``*`` (the rest of the key is a comment) holds an expression that produces a
group; its fields are merged into the enclosing group at that position. This is how a list of curve
points becomes numbered DNP3 point indices::

    "AO": {"246": "transform[DERCurve, opModVoltVar, CurveData](count())",
           "*points": "transform[DERCurve, opModVoltVar, CurveData](unpairs(249, xvalue, yvalue))"}
"""
import logging
import re

from convtools import conversion as c
from pyparsing import (alphas, alphanums, Combine, common, delimited_list, Forward, Group, Literal, Optional,
                       QuotedString, Suppress, Word)

from . import transforms
from .transforms import MISSING

_log = logging.getLogger(__name__)

REPEAT_SUFFIX = '[#]'
SOURCE_KEY = '#'
SPREAD_PREFIX = '*'
# "name[#]" optionally followed by a label that keeps keys unique when several groups feed one list.
_REPEAT_KEY = re.compile(r'^(?P<name>[^\[\]]*)\[#\](?:\s+(?P<label>.*\S))?\s*$')


class _Each:
    """Path segment marking "for each element of the list named by the preceding segments"."""
    __slots__ = ()

    def __repr__(self):
        return '<EACH>'


EACH = _Each()


def _level_label(level: int) -> str:
    """Name of the convtools label holding the element at a repetition depth (0 is the message root)."""
    return f'each{level}'


def _dotted(path) -> str:
    return '.'.join(str(p) for p in path)


def _normalize_segments(keys) -> tuple:
    """Expand ``Name[#]`` and bare ``#`` segments into (Name, EACH) / (EACH,) markers."""
    segments = []
    for key in keys:
        if isinstance(key, str):
            if key == SOURCE_KEY:
                segments.append(EACH)
                continue
            if key.endswith(REPEAT_SUFFIX):
                name = key[:-len(REPEAT_SUFFIX)]
                if not name:
                    raise ValueError(f'Empty name before {REPEAT_SUFFIX} in path {keys}.')
                segments.extend((name, EACH))
                continue
        segments.append(key)
    return tuple(segments)


class _Expr:
    """A parsed ``transform[...](...)`` expression: normalized source segments plus function conversions."""

    def __init__(self, segments: tuple, convs: list, where: tuple, depth: int = 0):
        self.segments = segments
        self.convs = convs
        self.where = where
        self.depth = depth          # number of repeated groups enclosing the expression
        parts, current = [], []
        for segment in segments:
            if segment is EACH:
                parts.append(tuple(current))
                current = []
            else:
                current.append(segment)
        parts.append(tuple(current))
        # parts[i] is the path between marker i-1 and marker i (parts[0] starts at the root); the
        # last entry is the path relative to the innermost element.
        self.parts = parts

    @property
    def markers(self) -> int:
        return len(self.parts) - 1

    @property
    def first_level(self) -> int:
        """Repetition level that the first marker refers to.

        A path that names its list from the root (``705, Crv[#], ...``) is anchored at the root: its
        first marker is level 1. A path that starts at an element (``#, ...``) is anchored at the
        innermost group: its last marker is the group's own level, so with fewer markers than
        enclosing groups the leading ``#`` still means "this group's element".
        """
        if self.markers and self.parts[0] == ():
            return self.depth - self.markers + 1
        return 1

    def prefix_at(self, level: int):
        """Path (relative to the element of ``level - 1``) naming the list iterated at ``level``, or None."""
        index = level - self.first_level
        return self.parts[index] if 0 <= index < self.markers else None

    def __repr__(self):
        return f'_Expr({self.segments!r} at {_dotted(self.where)})'


class _Repeat:
    """A parsed repeated group (output key ``name[#]``)."""

    def __init__(self, where: tuple, child, source: _Expr | None):
        self.where = where
        self.child = child      # dict node, or an _Expr for a list of scalars
        self.source = source    # the "#" entry, if any


class _Concat:
    """Several repeated groups (``name[#] label``) whose lists are concatenated into one output list."""

    def __init__(self, repeats: list):
        self.repeats = repeats


def _collect_expressions(node):
    if isinstance(node, _Expr):
        yield node
    elif isinstance(node, _Repeat):
        yield from _collect_expressions(node.child)
    elif isinstance(node, _Concat):
        for repeat in node.repeats:
            yield from _collect_expressions(repeat)
    elif isinstance(node, dict):
        for value in node.values():
            yield from _collect_expressions(value)


def _lookup(value, path: tuple):
    """Follow ``path`` through dicts and lists, yielding MISSING if any segment is absent.

    Integer segments index lists. On dicts a segment is tried as written and then as its string or
    integer form, since JSON transport turns the integer keys of SunSpec model numbers and DNP3 point
    indices into strings.
    """
    for segment in path:
        if isinstance(value, dict):
            if segment in value:
                value = value[segment]
                continue
            alternate = str(segment) if isinstance(segment, int) else None
            if alternate is None and isinstance(segment, str) and segment.isdigit():
                alternate = int(segment)
            if alternate is not None and alternate in value:
                value = value[alternate]
                continue
            return MISSING
        elif isinstance(value, (list, tuple)) and isinstance(segment, int):
            try:
                value = value[segment]
            except IndexError:
                return MISSING
        else:
            return MISSING
    return value


def _is_populated_list(value) -> bool:
    return isinstance(value, (list, tuple)) and len(value) > 0


def _expand_spreads(group: dict) -> dict:
    """Merge the fields of spread entries ("*...") into the group at their position."""
    expanded = {}
    for k, v in group.items():
        if isinstance(k, str) and k.startswith(SPREAD_PREFIX):
            if isinstance(v, dict):
                expanded.update(v)
            elif v is not MISSING:
                _log.warning(f'Spread entry "{k}" produced {type(v).__name__} instead of a group; ignored.')
        else:
            expanded[k] = v
    # A group whose only content was spreads that produced nothing is treated as absent.
    return expanded if expanded or not group else MISSING


def _concat(*lists):
    items = [item for lst in lists if isinstance(lst, list) for item in lst]
    return items if items else MISSING


def drop_missing(value):
    """Recursively remove MISSING fields from a transform result and prune groups and lists left empty."""
    if isinstance(value, dict):
        cleaned = {}
        for k, v in value.items():
            v = drop_missing(v)
            if v is MISSING or (isinstance(v, (dict, list)) and not v and value[k]):
                continue
            cleaned[k] = v
        return cleaned
    if isinstance(value, list):
        cleaned = []
        for original in value:
            v = drop_missing(original)
            if v is MISSING or (isinstance(v, (dict, list)) and not v and original):
                continue
            cleaned.append(v)
        return cleaned
    return value


class TransformParser:
    def __init__(self):
        self.function_call = self.setup_function_call()

    @staticmethod
    def setup_function_call():
        # Numbers become int or float (signed, decimal or scientific), so scale(0.001) and add(-5) parse.
        number = common.number
        # Quoted strings (either quote style) may contain any characters, so path segments such as
        # 'RegClas[1]' or "DateTgt[Date]" that are not valid bare identifiers can still be expressed.
        string_literal = QuotedString('"') | QuotedString("'")
        # A bare segment may carry the repetition marker (Pt[#]) or be the marker alone (#).
        variable = Combine(Word(alphanums + '_.') + Optional(Literal(REPEAT_SUFFIX))) | Literal(SOURCE_KEY)
        expression = Forward()

        argument = expression | number | string_literal | variable
        argument_list = delimited_list(argument)
        function_name = Word(alphas, alphanums + "_")
        function_call = (function_name
                         + Optional(Group(Suppress("[") + argument_list + Suppress("]")), default=[])
                         + Suppress("(") + Optional(argument_list) + Suppress(")"))
        # Define what an expression can be
        expression <<= function_call | number | string_literal | variable
        return function_call

    # TODO: Make inverse pipelines along these lines:
    #  pipeline = build_pipeline_from_conv_list(trans_conv_list)
    #  inverse_pipeline = build_pipeline_from_conv_list([t.inverse for t in reversed(trans_conv_list)])
    #  print(pipeline.execute(4))  # 37
    #  print(inverse_pipeline.execute(37))  # 4

    @staticmethod
    def _apply_functions(source, convs):
        """Pipe a source conversion through the function conversions, skipping them when the source is MISSING."""
        if not convs:
            return source
        pipeline = source
        for conv in convs:
            if isinstance(conv, _Expr):
                raise TypeError(f'Nested transform() calls are not supported ({conv!r}).')
            pipeline = pipeline.pipe(c.if_(c.this.is_(MISSING), c.this, conv))
        return pipeline

    def _make_parse_action(self, default_keys: tuple, where: tuple, depth: int):
        def handle_function_call(tokens):
            name, args = tokens[0], list(tokens[2:])
            keys = tuple(tokens[1]) if tokens[1] else default_keys
            if name == "transform":
                return _Expr(_normalize_segments(keys), args, where, depth)
            if not hasattr(transforms, name) or name.startswith('_'):
                _log.warning(f'Unknown transform: {name}.')
                return None
            # TODO: Probably also need a function to look up things like scale registers from outside the
            #  input (e.g., from the driver data model.) Library functions can already reach the enclosing
            #  element through transforms.scope().
            return getattr(transforms, name)(*args)
        return handle_function_call

    # ---- Phase 1: parse the pattern into a tree of dicts, _Expr and _Repeat nodes ----

    def _parse_expression(self, text: str, where: tuple, depth: int, default_keys: tuple | None = None):
        keys = where if default_keys is None else default_keys
        self.function_call.set_parse_action(self._make_parse_action(keys, where, depth))
        token = transforms.scope_label.set(_level_label(depth))
        try:
            result = self.function_call.parse_string(text, parse_all=True)[0]
        finally:
            transforms.scope_label.reset(token)
        if result is not None and not isinstance(result, _Expr):
            # A bare library function call applies to the whole current input.
            result = _Expr((), [result], where, depth)
        return result

    def _parse_repeat(self, value, where: tuple, depth: int, name: str) -> _Repeat | None:
        if not name:
            raise ValueError(f'Empty name before {REPEAT_SUFFIX} at {_dotted(where)}.')
        source = None
        if isinstance(value, str):
            child = self._parse_expression(value, where, depth + 1)
        elif isinstance(value, dict):
            value = dict(value)
            source_text = value.pop(SOURCE_KEY, None)
            if source_text is not None:
                if not isinstance(source_text, str):
                    raise TypeError(f'The "{SOURCE_KEY}" entry at {_dotted(where)} must be a transform expression.')
                source = self._parse_expression(source_text, where + (SOURCE_KEY,), depth, default_keys=())
            child = self._parse_pattern(value, where, depth + 1)
            if not child:
                _log.debug(f'Repeated group {_dotted(where)} has no mapped fields; it will not be produced.')
                return None
        else:
            raise TypeError(f'Repeated group values must be a transform expression (str) or a group (dict). '
                            f'Got {type(value).__name__} at {_dotted(where)}.')
        return _Repeat(where, child, source)

    def _parse_pattern(self, pattern: dict, path: tuple = (), depth: int = 0) -> dict:
        """Recursively parse a pattern (see the module docstring).

        Values that are strings are transform expressions. Values that are dicts are nested groups
        (e.g., 61850 logical nodes or SunSpec model numbers) and are parsed recursively, producing a
        nested output structure. Null values are skipped. When an expression omits the bracketed
        input path, the full path of output keys down to that expression is used as the input path.
        Keys ending in ``[#]`` are repeated groups; ``depth`` counts the enclosing repeated groups.
        """
        parsed = {}
        for k, v in pattern.items():
            key_path = path + (k,)
            if k == SOURCE_KEY:
                raise ValueError(f'"{SOURCE_KEY}" is only allowed directly inside a repeated group '
                                 f'("name{REPEAT_SUFFIX}"), at {_dotted(key_path)}.')
            if v is None:
                # A null marks an output field with no known source. It is omitted from the output.
                _log.debug(f'No transform defined for {_dotted(key_path)}; it will not be produced.')
                continue
            repeat_key = _REPEAT_KEY.match(k) if isinstance(k, str) else None
            if repeat_key:
                name = repeat_key.group('name')
                node = self._parse_repeat(v, key_path, depth, name)
                if node is None:
                    continue
                existing = parsed.get(name)
                if existing is None:
                    parsed[name] = node
                elif isinstance(existing, _Concat):
                    existing.repeats.append(node)
                elif isinstance(existing, _Repeat):
                    parsed[name] = _Concat([existing, node])
                else:
                    raise ValueError(f'{_dotted(path + (name,))} is defined both as a field and as a repeated group.')
            elif isinstance(k, str) and k.startswith(SPREAD_PREFIX):
                if not isinstance(v, str):
                    raise TypeError(f'Spread entries ("{SPREAD_PREFIX}...") must be transform expressions that '
                                    f'produce a group. Got {type(v).__name__} at {_dotted(key_path)}.')
                parsed[k] = self._parse_expression(v, key_path, depth, default_keys=())
            elif k in parsed and isinstance(parsed[k], (_Repeat, _Concat)):
                raise ValueError(f'{_dotted(key_path)} is defined both as a field and as a repeated group.')
            elif isinstance(v, dict):
                group = self._parse_pattern(v, key_path, depth)
                if group:
                    parsed[k] = group
                else:
                    _log.debug(f'Group {_dotted(key_path)} has no mapped fields; it will not be produced.')
            elif isinstance(v, str):
                parsed[k] = self._parse_expression(v, key_path, depth)
            else:
                raise TypeError(f'Pattern values must be transform expressions (str) or nested '
                                f'groups (dict). Got {type(v).__name__} at {_dotted(key_path)}.')
        return parsed

    # ---- Phase 2: build convtools conversions from the tree ----

    def _build_expression(self, expr: _Expr, depth: int):
        if expr.markers > depth:
            raise ValueError(f'{_dotted(expr.where)}: the path {expr.segments} uses an iteration marker '
                             f'outside of a repeated group ("name{REPEAT_SUFFIX}").')
        # After its last marker the path is relative to that level's element: the current input when
        # that is the group the expression sits in, or a labelled enclosing element otherwise.
        last_level = expr.first_level + expr.markers - 1 if expr.markers else 0
        base = c.this if last_level == depth else c.label(_level_label(last_level))
        suffix = expr.parts[-1]
        # If the source path is absent from the input, yield MISSING instead of raising. The functions
        # are only applied when a value was actually found. MISSING fields are removed from the result
        # by drop_missing() after each pattern stage.
        source = c.call_func(_lookup, base, suffix) if suffix else base
        return self._apply_functions(source, expr.convs)

    def _build_repeat(self, node: _Repeat, depth: int):
        level = depth + 1
        where = _dotted(node.where)
        prefixes = {prefix for prefix in (e.prefix_at(level) for e in _collect_expressions(node.child))
                    if prefix is not None}
        named = prefixes - {()}
        if node.source is not None and node.source.segments:
            # Explicit source path; sibling paths must start at the element ("#").
            if named:
                raise ValueError(f'{where}: the group has an explicit "{SOURCE_KEY}" source, so paths inside it '
                                 f'must start with "{SOURCE_KEY}" instead of naming the list; got {sorted(named)}.')
            source = self._build_expression(node.source, depth)
        elif named:
            # The list is named in the sibling paths ("Name[#]"); a "#" entry may add functions.
            if len(named) > 1:
                raise ValueError(f'{where}: expressions disagree about the list to iterate: {sorted(named)}.')
            if () in prefixes:
                raise ValueError(f'{where}: some paths start with "{SOURCE_KEY}" while others name the list '
                                 f'{sorted(named)}.')
            (prefix,) = named
            source = c.call_func(_lookup, c.this, prefix)
            if node.source is not None:
                source = self._apply_functions(source, node.source.convs)
        elif node.source is not None:
            # "#" with functions only and no named list: the enclosing element itself is the source.
            source = self._apply_functions(c.this, node.source.convs)
        elif prefixes:
            raise ValueError(f'{where}: paths start with "{SOURCE_KEY}" but the group has no "{SOURCE_KEY}" entry.')
        else:
            raise ValueError(f'{where}: repeated group has no source list. Mark the list in a path '
                             f'("Name{REPEAT_SUFFIX}") or add a "{SOURCE_KEY}" entry.')
        element = c.this.pipe(self._build(node.child, level), label_input=_level_label(level))
        return source.pipe(c.if_(c.call_func(_is_populated_list, c.this),
                                 c.this.iter(element).as_type(list),
                                 c.naive(MISSING)))

    def _build(self, node, depth: int):
        if isinstance(node, dict):
            group = c({k: self._build(v, depth) for k, v in node.items()})
            if any(isinstance(k, str) and k.startswith(SPREAD_PREFIX) for k in node):
                group = group.pipe(c.call_func(_expand_spreads, c.this))
            return group
        if isinstance(node, _Concat):
            return c.call_func(_concat, *[self._build_repeat(r, depth) for r in node.repeats])
        if isinstance(node, _Repeat):
            return self._build_repeat(node, depth)
        if isinstance(node, _Expr):
            return self._build_expression(node, depth)
        return c.naive(node)   # An unknown function parsed to None.

    def build_transform_from_schema(self, schemas):
        _log.debug(f'Building transform from schema: {schemas}')
        schemas = schemas if isinstance(schemas, list) else [schemas]
        pipeline = None
        for s in schemas:
            parsed_schema = self._parse_pattern(s)
            _log.debug(f'Placing in pipeline: {parsed_schema}')
            stage = (c.this.pipe(self._build(parsed_schema, 0), label_input=_level_label(0))
                     .pipe(c.call_func(drop_missing, c.this)))
            pipeline = pipeline.pipe(stage) if pipeline else stage
        return pipeline
