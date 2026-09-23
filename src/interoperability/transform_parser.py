import logging

from convtools import conversion as c
from pyparsing import alphas, alphanums, common, delimited_list, Forward, Group, Optional, QuotedString, Suppress, Word

from . import transforms

_log = logging.getLogger(__name__)


class _Missing:
    """Sentinel for a source field that is absent from the input message."""
    __slots__ = ()

    def __repr__(self):
        return '<MISSING>'


MISSING = _Missing()


def drop_missing(value):
    """Recursively remove MISSING fields from a transform result and prune groups left empty."""
    if isinstance(value, dict):
        cleaned = {}
        for k, v in value.items():
            v = drop_missing(v)
            if v is MISSING or (isinstance(v, dict) and not v and value[k]):
                continue
            cleaned[k] = v
        return cleaned
    return value


class TransformParser:
    def __init__(self):
        self.function_call = self.setup_function_call()

    @staticmethod
    def setup_function_call():
        integer = Word("1234567890")
        integer.set_parse_action(common.convert_to_integer)
        # Quoted strings (either quote style) may contain any characters, so path segments such as
        # 'RegClas[1]' or "DateTgt[Date]" that are not valid bare identifiers can still be expressed.
        string_literal = QuotedString('"') | QuotedString("'")
        variable = Word(alphanums + '_.')
        expression = Forward()

        argument = expression | integer | string_literal | variable  # | integer
        argument_list = delimited_list(argument)
        function_name = Word(alphas, alphanums + "_")
        function_call = (function_name
                         + Optional(Group(Suppress("[") + argument_list + Suppress("]")), default=[])
                         + Suppress("(") + Optional(argument_list) + Suppress(")"))
        # Define what an expression can be
        expression <<= function_call | integer | string_literal | variable  # | integer
        return function_call

    @staticmethod
    def _build_pipeline_from_conv_list(conv_list, item_name: str | list | tuple | None = None):
        pipeline = c.this
        for conv in conv_list:
            pipeline = pipeline.pipe(conv)
        if not item_name:
            return pipeline
        # If the source path is absent from the input, yield MISSING instead of raising. The
        # functions are only applied when a value was actually found. MISSING fields are removed
        # from the result by drop_missing() after each pattern stage.
        path = tuple(item_name) if isinstance(item_name, (tuple, list)) else (item_name,)
        source = c.item(*path, default=MISSING)
        return source.pipe(c.if_(c.this.is_(MISSING), c.naive(MISSING), pipeline))

    # TODO: Make inverse pipelines along these lines:
    #  pipeline = build_pipeline_from_conv_list(trans_conv_list)
    #  inverse_pipeline = build_pipeline_from_conv_list([t.inverse for t in reversed(trans_conv_list)])
    #  print(pipeline.execute(4))  # 37
    #  print(inverse_pipeline.execute(37))  # 4

    def _make_parse_action(self, key: str | list | tuple | None = None):
        # A bare string key is a single path segment, not a sequence of characters.
        default_keys = (key,) if isinstance(key, str) else key

        def handle_function_call(tokens):
            # print(f'tokens: is {tokens}')
            name, args = tokens[0], tokens[2:]
            keys = tokens[1] if tokens[1] else default_keys
            # _log.debug(f'name: {name}, keys: {keys}, args: {args}')
            if name == "transform":
                return self._build_pipeline_from_conv_list(args, tuple(keys))
            else:
                if not hasattr(transforms, name):
                    _log.warning(f'Unknown transform: {name}.')
                    return None
                else:
                    # TODO: Need to save keys of this function as labels to be used in transform creation.
                    # TODO: Probably also need a function to look up things like scale registers
                    #  from outside the input (e.g., from the driver data model.)
                    #  A "lookup" function might be useful to fill in extra values to the input array that can
                    #  be used as keys by other functions. This might also be enclosed in braces on the transform
                    #  rather than being a separate function: {label: topic, ...} for instance in the driver context.
                    #  Note: labels can be used in transforms without calling add_label, so long as the pipeline
                    #  they are used in calls add_label before the pipe in which tey are called.
                    return getattr(transforms, name)(*args)
        return handle_function_call

    def _parse_pattern(self, pattern: dict, path: tuple = ()) -> dict:
        """Recursively parse a pattern into a dict of convtools conversions.

        Values that are strings are transform expressions. Values that are dicts are nested
        groups (e.g., 61850 logical nodes or SunSpec model numbers) and are parsed recursively,
        producing a nested output structure. Null values are skipped. When an expression omits
        the bracketed input path, the full path of output keys down to that expression is used
        as the input path.
        """
        parsed = {}
        for k, v in pattern.items():
            key_path = path + (k,)
            if v is None:
                # A null marks an output field with no known source. It is omitted from the output.
                _log.debug(f'No transform defined for {".".join(key_path)}; it will not be produced.')
                continue
            if isinstance(v, dict):
                parsed[k] = self._parse_pattern(v, key_path)
            elif isinstance(v, str):
                self.function_call.set_parse_action(self._make_parse_action(key_path))
                parsed[k] = self.function_call.parse_string(v, parse_all=True)[0]
            else:
                raise TypeError(f'Pattern values must be transform expressions (str) or nested '
                                f'groups (dict). Got {type(v).__name__} at {".".join(key_path)}.')
        return parsed

    def build_transform_from_schema(self, schemas):
        _log.debug('IN BUILD_TRANSFORM_FROM_SCHEMA')
        _log.debug(f'schema: {schemas}')
        schemas = schemas if isinstance(schemas, list) else [schemas]
        pipeline = None
        for s in schemas:
            parsed_schema = self._parse_pattern(s)
            _log.debug(f'Placing in pipeline: {parsed_schema}')
            stage = c(parsed_schema).pipe(c.call_func(drop_missing, c.this))
            pipeline = pipeline.pipe(stage) if pipeline else stage
        return pipeline


# #trans_schema = {'foo': 'transform(multiple(7), add(9))', 'bar': 'transform(add(9), multiple(7))'}
# trans_schema = {'foo': 'transform[bar](multiple(7), add(9))', 'bar': 'transform[foo, 0](add(9), multiple(7))'}
# tp = TransformParser()
# print(tp.build_transform_from_schema(trans_schema).execute({'foo': [5,6], 'bar': 4}))  # {'foo': 37, 'bar': 98}



