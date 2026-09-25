"""Tests for the transform expression language and the bundled transform definitions."""
import json
from importlib import resources

import pytest

from interoperability.transform_parser import TransformParser
from interoperability.transform_registry import TransformRegistry


@pytest.fixture
def parser():
    return TransformParser()


def test_flat_pattern_with_explicit_paths(parser):
    schema = {'foo': 'transform[bar](multiple(7), add(9))',
              'bar': 'transform[foo, 0](add(9), multiple(7))'}
    result = parser.build_transform_from_schema(schema).execute({'foo': [5, 6], 'bar': 4})
    assert result == {'foo': 37, 'bar': 98}


def test_omitted_path_uses_output_key(parser):
    # A bare string key must be treated as one path segment, not split into characters.
    result = parser.build_transform_from_schema({'foo': 'transform(add(1))'}).execute({'foo': 4})
    assert result == {'foo': 5}


def test_nested_groups_produce_nested_output(parser):
    schema = {'702': {'WMaxRtg': 'transform[DGEN, WMaxRtg]()',
                      'X': 'transform(multiple(2))'}}
    result = parser.build_transform_from_schema(schema).execute(
        {'DGEN': {'WMaxRtg': 5000}, '702': {'X': 21}})
    assert result == {'702': {'WMaxRtg': 5000, 'X': 42}}


def test_quoted_segments_accept_either_quote_style_and_special_characters(parser):
    schema = {'AI': {'22': "transform['DGEN', 'RegClas[1]']()",
                     '23': 'transform["DGEN", "DateTgt[Date]"]()'}}
    result = parser.build_transform_from_schema(schema).execute(
        {'DGEN': {'RegClas[1]': 7, 'DateTgt[Date]': 'd'}})
    assert result == {'AI': {'22': 7, '23': 'd'}}


def test_quoted_string_function_argument(parser):
    result = parser.build_transform_from_schema({'b': 'transform[x](cast_value("bool"))'}).execute({'x': 'yes'})
    assert result == {'b': True}


def test_null_pattern_values_are_skipped(parser):
    schema = {'DGEN': {'WMax': 'transform[a]()', 'Vmax': None}}
    result = parser.build_transform_from_schema(schema).execute({'a': 1})
    assert result == {'DGEN': {'WMax': 1}}


def test_unsupported_pattern_value_type_raises(parser):
    with pytest.raises(TypeError):
        parser.build_transform_from_schema({'a': 5})


def test_mean_ignores_missing_and_none(parser):
    schema = {'LNV': 'transform[PNV](mean(phsA.mag, phsB.mag, phsC.mag, phsD.mag))'}
    result = parser.build_transform_from_schema(schema).execute(
        {'PNV': {'phsA': {'mag': 120.0}, 'phsB': {'mag': 122.0}, 'phsC': {'mag': None}}})
    assert result == {'LNV': 121.0}


def test_list_of_patterns_is_chained(parser):
    chain = [{'a': 'transform[x](multiple(2))'}, {'b': 'transform[a](add(1))'}]
    assert parser.build_transform_from_schema(chain).execute({'x': 10}) == {'b': 21}


def test_missing_source_field_is_omitted_from_output(parser):
    schema = {'a': 'transform[x](multiple(2))', 'b': 'transform[y]()'}
    assert parser.build_transform_from_schema(schema).execute({'x': 3}) == {'a': 6}


def test_missing_source_handles_deep_paths_list_indices_and_scalar_parents(parser):
    schema = {'deep': 'transform[p, q, r]()',
              'idx': 'transform[AI, 5]()',
              'ok': 'transform[AI, 0]()',
              'scalar_parent': 'transform[n, q]()'}
    result = parser.build_transform_from_schema(schema).execute({'p': {}, 'AI': [1], 'n': 7})
    assert result == {'ok': 1}


def test_group_emptied_by_missing_fields_is_pruned(parser):
    schema = {'702': {'W': 'transform[DGEN, WMax]()', 'V': 'transform[DGEN, VMax]()'},
              '701': {'Hz': 'transform[MMXU, Hz]()'}}
    result = parser.build_transform_from_schema(schema).execute({'DGEN': {'WMax': 5}})
    assert result == {'702': {'W': 5}}


def test_none_value_is_present_not_missing(parser):
    assert parser.build_transform_from_schema({'a': 'transform[x]()'}).execute({'x': None}) == {'a': None}


def test_missing_fields_propagate_through_chain(parser):
    chain = [{'a': 'transform[x](multiple(2))', 'b': 'transform[y]()'},
             {'c': 'transform[a](add(1))', 'd': 'transform[b]()'}]
    assert parser.build_transform_from_schema(chain).execute({'x': 10}) == {'c': 21}


def test_bundled_transform_runs_on_partial_message(parser):
    definitions = {(d['input_format'], d['output_format']): d
                   for f in _bundled_transform_files() for d in json.loads(f.read_text())}
    pipeline = parser.build_transform_from_schema(definitions[('61850', 'sunspec')]['pattern'])
    result = pipeline.execute({'DECP': {'MMXU': {'TotW': 12.5, 'Hz': 60.0}}})
    assert result == {'701': {'W': 12.5, 'Hz': 60.0}}


def _bundled_transform_files():
    tdir = resources.files('interoperability').joinpath('transforms')
    return sorted((f for f in tdir.iterdir() if f.is_file() and f.name.endswith('.json')),
                  key=lambda f: f.name)


def _bundled_definitions():
    for f in _bundled_transform_files():
        for d in json.loads(f.read_text()):
            yield pytest.param(d, id=f"{f.name}:{d['input_format']}->{d['output_format']}")


@pytest.mark.parametrize('definition', list(_bundled_definitions()))
def test_bundled_transform_definitions_compile(parser, definition):
    assert {'input_format', 'output_format', 'pattern'} <= definition.keys()
    pipeline = parser.build_transform_from_schema(definition['pattern'])
    assert pipeline is not None


def test_registry_finds_direct_chains_between_bundled_formats():
    registry = TransformRegistry()
    for f in _bundled_transform_files():
        registry.update_registry(json.loads(f.read_text()))
    # Every pairing ships as its own file now, so lookups are single hops.
    chain = registry.lookup('sunspec', '1815.2.outputs')
    assert len(chain) == 1
    assert registry.lookup('sunspec', 'no_such_format') == []


def test_registry_finds_multi_hop_chain():
    registry = TransformRegistry()
    registry.update_registry([
        {'input_format': 'a', 'output_format': 'b', 'pattern': {'y': 'transform[x]()'}},
        {'input_format': 'b', 'output_format': 'c', 'pattern': {'z': 'transform[y]()'}},
    ])
    chain = registry.lookup('a', 'c')
    assert [list(step) for step in chain] == [['y'], ['z']]      # a -> b -> c
    assert registry.lookup('c', 'a') == []


def test_agent_loads_bundled_definitions(tmp_path):
    pytest.importorskip('volttron')
    from interoperability.agent import PresentationService
    root = resources.files('interoperability')
    transforms = PresentationService._load_bundled_definitions(root.joinpath('transforms'))
    pairs = {(d['input_format'], d['output_format']) for d in transforms}
    assert ('61850', 'sunspec') in pairs and ('1815.2.inputs', '61850') in pairs
    assert ('1547', 'sunspec') in pairs and ('2030.5', '61850') in pairs
    # Only JSON files directly inside the directory are loaded; drafts in subdirectories are not.
    (tmp_path / 'a.json').write_text(json.dumps([{'input_format': 'a', 'output_format': 'b', 'pattern': {}}]))
    (tmp_path / 'drafts').mkdir()
    (tmp_path / 'drafts' / 'b.json').write_text(json.dumps([{'input_format': 'c', 'output_format': 'd', 'pattern': {}}]))
    loaded = PresentationService._load_bundled_definitions(tmp_path)
    assert [(d['input_format'], d['output_format']) for d in loaded] == [('a', 'b')]
    assert PresentationService._load_bundled_definitions(root.joinpath('does_not_exist')) == []


# ---- Repeated groups ("name[#]") and list functions ----

SUNSPEC_705 = {'705': {'Ena': 1, 'Crv': [
    {'ActPt': 2, 'VRef': 100, 'Pt': [{'V': 95, 'Var': 44}, {'V': 105, 'Var': -44}, {'V': 0, 'Var': 0}]},
    {'ActPt': 1, 'Pt': [{'V': 1, 'Var': 2}]}]}}


def test_repeated_group_iterates_marked_source_list(parser):
    schema = {'CurveData[#]': {'xvalue': 'transform[705, Crv, 0, Pt[#], V]()',
                               'yvalue': "transform[705, Crv, 0, 'Pt[#]', Var](multiple(10))"}}
    result = parser.build_transform_from_schema(schema).execute(SUNSPEC_705)
    assert result == {'CurveData': [{'xvalue': 95, 'yvalue': 440}, {'xvalue': 105, 'yvalue': -440},
                                    {'xvalue': 0, 'yvalue': 0}]}


def test_repeated_group_omitted_path_uses_output_keys(parser):
    schema = {'Crv[#]': {'ActPt': 'transform()', 'Pt[#]': {'V': 'transform()'}}}
    result = parser.build_transform_from_schema(schema).execute(SUNSPEC_705['705'])
    assert result == {'Crv': [{'ActPt': 2, 'Pt': [{'V': 95}, {'V': 105}, {'V': 0}]}, {'ActPt': 1, 'Pt': [{'V': 1}]}]}


def test_repeated_group_of_scalars(parser):
    schema = {'xs[#]': 'transform[705, Crv, 0, Pt[#], V]()'}
    assert parser.build_transform_from_schema(schema).execute(SUNSPEC_705) == {'xs': [95, 105, 0]}


def test_repeated_group_source_functions_and_take_by_path(parser):
    # A "#" entry without its own path applies functions to the implicitly named list. take() resolves
    # its path argument against the element enclosing the group (here the message root).
    schema = {'CurveData[#]': {'#': "transform(take('705.Crv.0.ActPt'))",
                               'xvalue': 'transform[705, Crv, 0, Pt[#], V]()'}}
    result = parser.build_transform_from_schema(schema).execute(SUNSPEC_705)
    assert result == {'CurveData': [{'xvalue': 95}, {'xvalue': 105}]}
    # Absent count field: list passes through untouched. Literal count: sliced.
    assert parser.build_transform_from_schema({'n[#]': {'#': "transform(take('nope'))", 'v': 'transform[705, Crv, 0, Pt[#], V]()'}}
                                              ).execute(SUNSPEC_705) == {'n': [{'v': 95}, {'v': 105}, {'v': 0}]}
    assert parser.build_transform_from_schema({'n[#]': {'#': 'transform(take(1))', 'v': 'transform[705, Crv, 0, Pt[#], V]()'}}
                                              ).execute(SUNSPEC_705) == {'n': [{'v': 95}]}


def test_repeated_group_explicit_source_with_as_list_and_count(parser):
    sep2 = {'DERCurve': {'opModVoltVar': {'vRef': 7, 'CurveData': [{'xvalue': 95, 'yvalue': 44}, {'xvalue': 105, 'yvalue': -44}]}}}
    schema = {'705': {'Crv[#]': {'#': 'transform[DERCurve, opModVoltVar](as_list())',
                                 'ActPt': 'transform[#, CurveData](count())',
                                 'VRef': 'transform[#, vRef]()',
                                 'Pt[#]': {'V': 'transform[#, CurveData[#], xvalue]()',
                                           'Var': 'transform[#, CurveData[#], yvalue]()'}}}}
    pipeline = parser.build_transform_from_schema(schema)
    assert pipeline.execute(sep2) == {'705': {'Crv': [{'ActPt': 2, 'VRef': 7,
                                                       'Pt': [{'V': 95, 'Var': 44}, {'V': 105, 'Var': -44}]}]}}
    assert pipeline.execute({'DERCurve': {}}) == {}


def test_nested_repeated_groups_and_enclosing_element_paths(parser):
    schema = {'curves[#]': {'act': 'transform[705, Crv[#], ActPt]()',
                            'ena': 'transform[705, Ena]()',                     # no marker: message root
                            'pts[#]': {'v': 'transform[705, Crv[#], Pt[#], V]()',
                                       'act': 'transform[705, Crv[#], ActPt]()'}}}  # one marker: the curve
    result = parser.build_transform_from_schema(schema).execute(SUNSPEC_705)
    assert result == {'curves': [{'act': 2, 'ena': 1, 'pts': [{'v': 95, 'act': 2}, {'v': 105, 'act': 2}, {'v': 0, 'act': 2}]},
                                 {'act': 1, 'ena': 1, 'pts': [{'v': 1, 'act': 1}]}]}


def test_repeated_group_missing_or_empty_list_is_omitted_and_empty_elements_dropped(parser):
    schema = {'ena': 'transform[705, Ena]()', 'pts[#]': {'v': 'transform[705, Crv, 0, Pt[#], V]()'}}
    pipeline = parser.build_transform_from_schema(schema)
    assert pipeline.execute({'705': {'Ena': 1}}) == {'ena': 1}
    assert pipeline.execute({'705': {'Ena': 1, 'Crv': [{'Pt': []}]}}) == {'ena': 1}
    assert pipeline.execute({'705': {'Ena': 1, 'Crv': [{'Pt': {'V': 1}}]}}) == {'ena': 1}          # not a list
    assert pipeline.execute({'705': {'Crv': [{'Pt': [{'V': 1}, {'Q': 3}]}]}}) == {'pts': [{'v': 1}]}


def test_paths_match_string_or_integer_keys(parser):
    pipeline = parser.build_transform_from_schema({'w': 'transform[701, W]()', 'ai': "transform[AI, '5']()"})
    assert pipeline.execute({'701': {'W': 1}, 'AI': {5: 2}}) == {'w': 1, 'ai': 2}
    assert pipeline.execute({701: {'W': 1}, 'AI': [0, 1, 2, 3, 4, 5]}) == {'w': 1}


def test_pairs_builds_points_from_flat_indexed_array(parser):
    schema = {'crvPts[#]': {'#': "transform[AO](pairs(249, 100, xVal, yVal), take('AO.246'))",
                            'xVal': 'transform[#, xVal]()', 'yVal': 'transform[#, yVal]()'}}
    ao = {'246': 2, '249': 1.0, '250': 2.0, '251': 3.0, '252': 4.0, '253': 0.0, '254': 0.0}
    assert parser.build_transform_from_schema(schema).execute({'AO': ao}) == {
        'crvPts': [{'xVal': 1.0, 'yVal': 2.0}, {'xVal': 3.0, 'yVal': 4.0}]}
    schema = {'p[#]': {'#': 'transform[AO](pairs(1, 3, x, y))', 'x': 'transform[#, x]()', 'y': 'transform[#, y]()'}}
    assert parser.build_transform_from_schema(schema).execute({'AO': [0, 5, 6, 7]}) == {'p': [{'x': 5, 'y': 6}, {'x': 7}]}


@pytest.mark.parametrize('schema, message', [
    ({'a': 'transform[705, Crv, 0, Pt[#], V]()'}, 'outside of a repeated group'),
    ({'a[#]': {'x': 'transform[705, Crv, 0, Pt[#], V]()', 'y': 'transform[706, Crv, 0, Pt[#], V]()'}}, 'disagree'),
    ({'a[#]': {'x': 'transform[705, Ena]()'}}, 'no source list'),
    ({'a[#]': {'#': 'transform[705, Crv]()', 'x': 'transform[705, Crv[#], ActPt]()'}}, 'must start with "#"'),
    ({'a[#]': {'x': 'transform[#, ActPt]()'}}, 'no "#" entry'),
    ({'a': {'#': 'transform[x]()'}}, 'only allowed directly inside a repeated group'),
    ({'[#]': {'x': 'transform[a[#], b]()'}}, 'Empty name'),
], ids=['stray-marker', 'disagreeing-lists', 'no-source', 'explicit-plus-named', 'bare-hash-no-source',
        'hash-outside-repeat', 'empty-name'])
def test_repeated_group_definition_errors(parser, schema, message):
    with pytest.raises(ValueError, match=message):
        parser.build_transform_from_schema(schema)


def test_repeated_group_element_source_wraps_enclosing_element(parser):
    # "#" with functions only and no list named by the siblings: the enclosing element is the source.
    schema = {'705': {'Crv[#]': {'#': 'transform(as_list())', 'VRef': 'transform[AI, 29]()', 'RspTms': 'transform[AI, 298]()'}}}
    pipeline = parser.build_transform_from_schema(schema)
    assert pipeline.execute({'AI': {'29': 100, '298': 5}}) == {'705': {'Crv': [{'VRef': 100, 'RspTms': 5}]}}
    assert pipeline.execute({'AI': {'1': 1}}) == {}


def test_leading_hash_refers_to_innermost_group_element(parser):
    # Inside Pt[#] (level 2) a path starting with "#" means the point, even though Crv[#] also uses "#".
    schema = {'Crv[#]': {'#': 'transform(as_list())', 'ActPt': 'transform[AI, 330]()',
                         'Pt[#]': {'#': 'transform[AI](pairs(333, 100, V, Var))',
                                   'V': 'transform[#, V]()', 'Var': 'transform[#, Var]()'}}}
    result = parser.build_transform_from_schema(schema).execute({'AI': {'330': 1, '333': 9, '334': 8}})
    assert result == {'Crv': [{'ActPt': 1, 'Pt': [{'V': 9, 'Var': 8}]}]}
    # A path with two markers written inside the inner group reaches both levels.
    schema = {'Crv[#]': {'#': 'transform[DERCurve, opModVoltVar](as_list())',
                         'Pt[#]': {'V': 'transform[#, CurveData[#], xvalue]()'}}}
    result = parser.build_transform_from_schema(schema).execute({'DERCurve': {'opModVoltVar': {'CurveData': [{'xvalue': 3}]}}})
    assert result == {'Crv': [{'Pt': [{'V': 3}]}]}
    with pytest.raises(ValueError, match='some paths start with "#"'):
        parser.build_transform_from_schema({'a[#]': {'x': 'transform[705, Crv, 0, Pt[#], V]()', 'y': 'transform[#, V]()'}})


def test_labelled_repeated_groups_concatenate_into_one_list(parser):
    schema = {'sequence[#] first': {'#': 'transform[a](as_list())', 'v': 'transform[#, x]()'},
              'sequence[#] second': {'#': 'transform[b](as_list())', 'v': 'transform[#, x](multiple(10))'}}
    pipeline = parser.build_transform_from_schema(schema)
    assert pipeline.execute({'a': {'x': 1}, 'b': {'x': 2}}) == {'sequence': [{'v': 1}, {'v': 20}]}
    assert pipeline.execute({'b': {'x': 2}}) == {'sequence': [{'v': 20}]}
    assert pipeline.execute({}) == {}
    with pytest.raises(ValueError, match='both as a field and as a repeated group'):
        parser.build_transform_from_schema({'s': 'transform[x]()', 's[#]': {'v': 'transform[y[#]]()'}})


def test_spread_entries_merge_groups_in_position(parser):
    schema = {'g': {'k': 'transform[x]()', '*more': 'transform[y]()', 'z': 'transform[x]()'}}
    result = parser.build_transform_from_schema(schema).execute({'x': 1, 'y': {'a': 2, 'b': 3}})
    assert list(result['g'].items()) == [('k', 1), ('a', 2), ('b', 3), ('z', 1)]
    assert parser.build_transform_from_schema(schema).execute({'x': 1}) == {'g': {'k': 1, 'z': 1}}
    # A spread that does not produce a group contributes nothing.
    assert parser.build_transform_from_schema({'g': {'*s': 'transform[x](const(5))'}}).execute({'x': 1}) == {}
    with pytest.raises(TypeError):
        parser.build_transform_from_schema({'g': {'*s': {'a': 'transform[x]()'}}})


def test_guards_and_const(parser):
    pipeline = parser.build_transform_from_schema({'v': "transform[x](when('mode', 2), multiple(10))",
                                                   'w': "transform[x](when_equal('sel', 'idx'))",
                                                   'c': 'transform[x](const(7))'})
    assert pipeline.execute({'x': 4, 'mode': 2.0, 'sel': 1, 'idx': 1}) == {'v': 40, 'w': 4, 'c': 7}
    assert pipeline.execute({'x': 4, 'mode': 3, 'sel': 1}) == {'c': 7}        # guard false; idx absent
    assert pipeline.execute({'mode': 2}) == {}                                # source absent: const not emitted


def test_unpairs_lays_points_out_as_numbered_values(parser):
    schema = {'AO': {'246': 'transform[pts](count())', '*points': 'transform[pts](unpairs(249, x, y))', '217': 'transform[pts](const(1))'}}
    result = parser.build_transform_from_schema(schema).execute({'pts': [{'x': 95, 'y': 44}, {'x': 105}]})
    assert list(result['AO'].items()) == [('246', 2), ('249', 95), ('250', 44), ('251', 105), ('217', 1)]


# ---- modbus_tk style register transforms ----

def test_numeric_literals_may_be_signed_or_fractional(parser):
    pipeline = parser.build_transform_from_schema({'a': 'transform[x](multiple(0.5))', 'b': 'transform[x](add(-3))',
                                                   'c': 'transform[x](multiple(1e-3))'})
    assert pipeline.execute({'x': 10}) == {'a': 5.0, 'b': 7, 'c': 0.01}


def test_scale_fixes_decimal_noise_and_inverts(parser):
    from interoperability import transforms
    assert parser.build_transform_from_schema({'v': 'transform[x](scale(0.001))'}).execute({'x': 12345}) == {'v': 12.345}
    assert 3 * 0.1 != 0.3                   # the noise scale() removes
    assert transforms.scale(0.1).execute(3) == 0.3
    conv = transforms.scale('0.001')          # string arguments as in the modbus_tk register maps
    assert conv.execute(12345) == 12.345
    assert conv.inverse.execute(12.345) == 12345.0
    assert transforms.scale(0).inverse.execute(5) is None
    assert transforms.scale(2).inverse.execute('abc') == 'abc'


def test_scale_reg_and_scale_reg_pow_10_use_a_sibling_register(parser):
    from interoperability import transforms
    schema = {'W': "transform[701, W](scale_reg_pow_10('701.W_SF'))",
              'V': "transform[701, V](scale_reg('701.V_DIV'))"}
    pipeline = parser.build_transform_from_schema(schema)
    assert pipeline.execute({'701': {'W': 12345, 'W_SF': -1, 'V': 2400, 'V_DIV': 10}}) == {'W': 1234.5, 'V': 240.0}
    assert pipeline.execute({'701': {'W': 12345, 'W_SF': 2}}) == {'W': 1234500.0}            # V_DIV absent: V omitted
    assert pipeline.execute({'701': {'W': 5, 'V': 2400, 'V_DIV': 0}}) == {'V': None}          # W_SF absent, /0 -> None
    # Inside a repeated group the register path is relative to the element.
    schema = {'pts[#]': {'v': "transform[705, Crv, 0, Pt[#], V](scale_reg_pow_10('sf'))"}}
    assert parser.build_transform_from_schema(schema).execute(
        {'705': {'Crv': [{'Pt': [{'V': 950, 'sf': -1}, {'V': 1050, 'sf': -1}]}]}}) == {'pts': [{'v': 95.0}, {'v': 105.0}]}
    # Inverses need the register too; they read it from the same enclosing element (labelled each0 at top level).
    from convtools import conversion as c
    def invert(conv, element, value):
        return c.this.pipe(c.naive(value).pipe(conv.inverse), label_input='each0').execute(element)
    assert invert(transforms.scale_reg_pow_10('sf'), {'sf': -1}, 95.0) == 950.0
    assert invert(transforms.scale_reg('d'), {'d': 10}, 240.0) == 2400.0
    assert invert(transforms.scale_reg('d'), {}, 240.0) is transforms.MISSING


def test_no_op_copies_and_is_its_own_inverse():
    from interoperability import transforms
    conv = transforms.no_op()
    assert conv.execute({'a': 1}) == {'a': 1} and conv.inverse.execute(7) == 7


@pytest.mark.parametrize('name, reverse, registers, expected', [
    # registers listed from the highest 16 bits of the packed integer to the lowest; values follow modbus_tk
    ('mod10k', False, [12, 3456], 12 * 10000 + 3456),
    ('mod10k', True, [12, 3456], 3456 * 10000 + 12),
    ('mod10k64', False, [4, 3, 2, 1], 1 * 10000 ** 3 + 2 * 10000 ** 2 + 3 * 10000 + 4),
    ('mod10k64', True, [4, 3, 2, 1], 4 * 10000 ** 3 + 3 * 10000 ** 2 + 2 * 10000 + 1),
    ('mod10k48', False, [4, 3, 2, 1], 2 * 10000 ** 2 + 3 * 10000 + 4),
    ('mod10k48', True, [4, 3, 2, 1], 1 * 10000 ** 2 + 2 * 10000 + 3),
])
def test_mod10k_family_matches_modbus_tk(parser, name, reverse, registers, expected):
    from interoperability import transforms
    packed = 0
    for word in registers:
        packed = (packed << 16) | word
    conv = getattr(transforms, name)(reverse)
    assert conv.execute(packed) == expected
    assert parser.build_transform_from_schema({'v': f'transform[x]({name}({"True" if reverse else "False"}))'}
                                              ).execute({'x': packed}) == {'v': expected}
    # The inverse packs the digit groups back into the registers the value came from.
    repacked = conv.inverse.execute(expected)
    used = {'mod10k': [1, 0], 'mod10k64': [0, 1, 2, 3], 'mod10k48': [1, 2, 3] if not reverse else [0, 1, 2]}[name]
    for index in used:
        assert (repacked >> (16 * index)) & 0xFFFF == (packed >> (16 * index)) & 0xFFFF


def test_all_null_repeated_group_is_skipped(parser):
    schema = {'705': {'Crv[#]': {'Pt[#]': {'V': None}}}, 'x': 'transform[a]()'}
    assert parser.build_transform_from_schema(schema).execute({'a': 1}) == {'x': 1}


def _bundled_pipeline(parser, source, target):
    definitions = {(d['input_format'], d['output_format']): d['pattern']
                   for f in _bundled_transform_files() for d in json.loads(f.read_text())}
    return parser.build_transform_from_schema(definitions[(source, target)])


def _apply_batch(output, table, step):
    """What a driver does with a 1815.2 write: the plain table first, then one batch of the sequence."""
    points = dict(output.get(table, {}))
    points.update(output['sequence'][step][table])
    return {table: points}


def test_bundled_curves_through_the_1815_2_edit_window(parser):
    sep2 = {'DERCurve': {'opModVoltVar': {'openLoopTms': 5, 'CurveData': [{'xvalue': 95, 'yvalue': 44}, {'xvalue': 105, 'yvalue': -44}]},
                         'opModHVRTMustTrip': {'CurveData': [{'xvalue': 120, 'yvalue': 0.16}]}}}
    out = _bundled_pipeline(parser, '2030.5', '1815.2.outputs').execute(sep2)
    # One batch per curve, keys in write order: select slot, curve type, count, points, assign to the mode.
    assert out['sequence'] == [
        {'AO': {'244': 1, '245': 2, '246': 2, '249': 95, '250': 44, '251': 105, '252': -44, '217': 1}},
        {'AO': {'244': 4, '245': 9, '246': 1, '249': 120, '250': 0.16, '23': 4}}]
    assert list(out['sequence'][0]['AO']) == ['244', '245', '246', '249', '250', '251', '252', '217']
    # Reading the window back only fills the mode whose curve index matches the selector.
    read = _bundled_pipeline(parser, '1815.2.outputs', '2030.5')
    assert read.execute(_apply_batch(out, 'AO', 0))['DERCurve'] == {
        'opModVoltVar': {'openLoopTms': 5, 'CurveData': [{'xvalue': 95, 'yvalue': 44}, {'xvalue': 105, 'yvalue': -44}]}}
    assert read.execute(_apply_batch(out, 'AO', 1))['DERCurve'] == {
        'opModVoltVar': {'openLoopTms': 5}, 'opModHVRTMustTrip': {'CurveData': [{'xvalue': 120, 'yvalue': 0.16}]}}
    # SunSpec: the active curve's points, trimmed to ActPt, and per-curve settings inside Crv.
    sunspec = {'705': {'Crv': [{'ActPt': 2, 'VRef': 100, 'Pt': [{'V': 95, 'Var': 44}, {'V': 105, 'Var': -44}, {'V': 0, 'Var': 0}]}]}}
    out = _bundled_pipeline(parser, 'sunspec', '1815.2.outputs').execute(sunspec)
    assert out['AO'] == {'0': 100}
    assert out['sequence'] == [{'AO': {'244': 1, '245': 2, '246': 2, '249': 95, '250': 44, '251': 105, '252': -44, '217': 1}}]
    assert _bundled_pipeline(parser, '1815.2.outputs', 'sunspec').execute(_apply_batch(out, 'AO', 0)) == {
        '705': {'Crv': [{'VRef': 100, 'ActPt': 2, 'Pt': [{'V': 95, 'Var': 44}, {'V': 105, 'Var': -44}]}]}}
    # 61850: mode curves feed the sequence; the generic FMARn window maps the window as is, unguarded.
    i61850 = {'DVVR': {'VVArCrv': {'crvPts': [{'xVal': 95, 'yVal': 44}]}},
              'DGSMn': {'InCrv': 7, 'ModTyp': 3}, 'FMARn': {'PairArr': {'NumPts': 1, 'CrvPts': [{'xVal': 1, 'yVal': 2}]}}}
    out = _bundled_pipeline(parser, '61850', '1815.2.inputs').execute(i61850)
    assert {k: out['AI'][k] for k in ('297', '328', '329', '330', '333', '334')} == {
        '297': 1, '328': 7, '329': 3, '330': 1, '333': 1, '334': 2}
    assert out['sequence'] == [{'AI': {'328': 1, '329': 2, '330': 1, '333': 95, '334': 44, '297': 1}}]
    back = _bundled_pipeline(parser, '1815.2.inputs', '61850').execute(_apply_batch(out, 'AI', 0))
    assert back['DVVR']['VVArCrv'] == {'numPts': 1, 'crvPts': [{'xVal': 95, 'yVal': 44}]}
    assert back['FMARn']['PairArr'] == {'NumPts': 1, 'CrvPts': [{'xVal': 95, 'yVal': 44}]}
    assert back['DGSMn'] == {'InCrv': 1, 'ModTyp': 2}


def test_bundled_curves_round_trip_sunspec_2030_5_and_61850(parser):
    sunspec = {'705': {'Ena': 1, 'Crv': [{'ActPt': 2, 'VRef': 100, 'VRefAutoEna': 1, 'VRefAutoTms': 300, 'RspTms': 5,
                                          'Pt': [{'V': 95, 'Var': 44}, {'V': 105, 'Var': -44}, {'V': 0, 'Var': 0}]}]},
               '708': {'Crv': [{'MustTrip': {'ActPt': 2, 'Pt': [{'V': 120, 'Tms': 0.16}, {'V': 110, 'Tms': 13}, {'V': 0, 'Tms': 0}]},
                                'MomCess': {'ActPt': 1, 'Pt': [{'V': 118, 'Tms': 1}]}}]},
               '710': {'Crv': [{'MustTrip': {'ActPt': 1, 'Pt': [{'Hz': 62, 'Tms': 0.16}]}}]}}
    sep2 = _bundled_pipeline(parser, 'sunspec', '2030.5').execute(sunspec)
    assert sep2['DERCurve']['opModVoltVar'] == {
        'vRef': 100, 'autonomousVRefEnable': 1, 'autonomousVRefTimeConstant': 300, 'openLoopTms': 5,
        'CurveData': [{'xvalue': 95, 'yvalue': 44}, {'xvalue': 105, 'yvalue': -44}]}   # only ActPt points
    assert sep2['DERCurve']['opModHVRTMomentaryCessation'] == {'CurveData': [{'xvalue': 118, 'yvalue': 1}]}
    assert sep2['DERCurve']['opModHFRTMustTrip'] == {'CurveData': [{'xvalue': 62, 'yvalue': 0.16}]}
    # Writing back emits the single active curve with its point count.
    expected_sunspec = {'705': {'Crv': [{'ActPt': 2, 'VRef': 100, 'VRefAutoEna': 1, 'VRefAutoTms': 300, 'RspTms': 5,
                                         'Pt': [{'V': 95, 'Var': 44}, {'V': 105, 'Var': -44}]}]},
                        '708': {'Crv': [{'MustTrip': {'ActPt': 2, 'Pt': [{'V': 120, 'Tms': 0.16}, {'V': 110, 'Tms': 13}]},
                                         'MomCess': {'ActPt': 1, 'Pt': [{'V': 118, 'Tms': 1}]}}]},
                        '710': {'Crv': [{'MustTrip': {'ActPt': 1, 'Pt': [{'Hz': 62, 'Tms': 0.16}]}}]}}
    assert _bundled_pipeline(parser, '2030.5', 'sunspec').execute(sep2) == expected_sunspec
    i61850 = _bundled_pipeline(parser, '2030.5', '61850').execute(sep2)
    assert i61850['DVVR']['VVArCrv'] == {'numPts': 2, 'crvPts': [{'xVal': 95, 'yVal': 44}, {'xVal': 105, 'yVal': -44}]}
    assert i61850['DHVT']['CeaZnSt']['PTOV']['TmVCrv'] == {'numPts': 1, 'crvPts': [{'xVal': 118, 'yVal': 1}]}
    assert _bundled_pipeline(parser, '61850', '2030.5').execute(i61850)['DERCurve'] == {
        k: {a: v for a, v in mode.items() if a != 'vRef'} for k, mode in sep2['DERCurve'].items()}
    from_sunspec = _bundled_pipeline(parser, 'sunspec', '61850').execute(sunspec)
    assert from_sunspec['DVVR']['VVArCrv'] == i61850['DVVR']['VVArCrv']
    assert from_sunspec['DHFT'] == i61850['DHFT']
    back = _bundled_pipeline(parser, '61850', 'sunspec').execute(from_sunspec)
    assert {k: back[k]['Crv'] for k in expected_sunspec} == {k: v['Crv'] for k, v in expected_sunspec.items()}
