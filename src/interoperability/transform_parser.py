import logging

from convtools import conversion as c
from pyparsing import alphas, alphanums, common, delimited_list, Forward, Group, Optional, Suppress, Word

from . import transforms

_log = logging.getLogger(__name__)

class TransformParser:
    def __init__(self):
        self.function_call = self.setup_function_call()

    @staticmethod
    def setup_function_call():
        integer = Word("1234567890")
        integer.set_parse_action(common.convert_to_integer)
        string_literal = Suppress('"') + Word(alphanums + " ") + Suppress('"')
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
        if item_name:
            # _log.debug(f'item_name is a {type(item_name)}')
            converter = c.item(*item_name) if isinstance(item_name, (tuple, list)) else c.item(item_name)
        else:
            converter = c.this
        for conv in conv_list:
            converter = converter.pipe(conv)
        return converter

    # TODO: Make inverse pipelines along these lines:
    #  pipeline = build_pipeline_from_conv_list(trans_conv_list)
    #  inverse_pipeline = build_pipeline_from_conv_list([t.inverse for t in reversed(trans_conv_list)])
    #  print(pipeline.execute(4))  # 37
    #  print(inverse_pipeline.execute(37))  # 4

    def _make_parse_action(self, key: str | list | None = None):
        def handle_function_call(tokens):
            # print(f'tokens: is {tokens}')
            name, args = tokens[0], tokens[2:]
            keys = tokens[1] if tokens[1] else key
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

    def build_transform_from_schema(self, schemas):
        _log.debug('IN BUILD_TRANSFORM_FROM_SCHEMA')
        _log.debug(f'schema: {schemas}')
        schemas = schemas if isinstance(schemas, list) else [schemas]
        pipeline = None
        for s in schemas:
            parsed_schema = {}
            for k, v in s.items():
                self.function_call.set_parse_action(self._make_parse_action(k))
                parsed_schema[k] = self.function_call.parse_string(v)[0]
            _log.debug(f'Placing in pipeline: {parsed_schema}')
            pipeline = pipeline.pipe(c(parsed_schema)) if pipeline else c(parsed_schema)
        return pipeline


# #trans_schema = {'foo': 'transform(multiple(7), add(9))', 'bar': 'transform(add(9), multiple(7))'}
# trans_schema = {'foo': 'transform[bar](multiple(7), add(9))', 'bar': 'transform[foo, 0](add(9), multiple(7))'}
# tp = TransformParser()
# print(tp.build_transform_from_schema(trans_schema).execute({'foo': [5,6], 'bar': 4}))  # {'foo': 37, 'bar': 91}



