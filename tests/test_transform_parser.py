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


def test_agent_loads_bundled_definitions():
    pytest.importorskip('volttron')
    from interoperability.agent import PresentationService
    root = resources.files('interoperability')
    transforms = PresentationService._load_bundled_definitions(root.joinpath('transforms'))
    pairs = {(d['input_format'], d['output_format']) for d in transforms}
    assert ('61850', 'sunspec') in pairs and ('1815.2.inputs', '61850') in pairs
    assert ('1547', 'sunspec') in pairs and ('2030.5', '61850') in pairs
    # Drafts in transforms/unfinished/ must not be loaded.
    drafts = [d['pattern'] for f in root.joinpath('transforms', 'unfinished').iterdir()
              if f.name.endswith('.json') for d in json.loads(f.read_text())]
    assert drafts and not any(d['pattern'] in drafts for d in transforms)
    assert PresentationService._load_bundled_definitions(root.joinpath('does_not_exist')) == []
