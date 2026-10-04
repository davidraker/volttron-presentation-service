"""Field maps, lossiness weighting and hub-aware path selection in the transform registry."""
import json
import logging
import time
from importlib import resources

import pytest

from interoperability import field_universe
from interoperability.transform_parser import FieldMap, TransformParser, path_matches
from interoperability.transform_registry import DEFAULT_HUBS, TransformNotFoundError, TransformRegistry


@pytest.fixture
def parser():
    return TransformParser()


def _bundled_definitions():
    tdir = resources.files('interoperability').joinpath('transforms')
    return [d for f in sorted(tdir.iterdir(), key=lambda f: f.name)
            if f.is_file() and f.name.endswith('.json') for d in json.loads(f.read_text())]


# ---- field maps ----

def test_field_map_records_sources_targets_fidelity_and_nulls(parser):
    fm = parser.field_map({'a': 'transform[x, y]()',
                           'b': 'transform[x, z](scale_int(10))',
                           'c': 'transform[p](mean(q.r, q.s))',
                           'd': None,
                           'g': {'e': 'transform[x, y](approx(0.5))', 'f': None}})
    by_target = {m.target: m for m in fm.mappings}
    assert by_target[('a',)].source == ('x', 'y') and by_target[('a',)].fidelity == 1.0
    assert by_target[('b',)].fidelity == 0.9 and by_target[('b',)].functions == ('scale_int',)
    assert by_target[('c',)].fidelity == 0.5
    assert by_target[('g', 'e')].fidelity == 0.5
    assert fm.nulls == [('d',), ('g', 'f')]
    assert fm.sources() == {('x', 'y'), ('x', 'z'), ('p',)}


def test_field_map_of_repeated_groups_uses_wildcards_and_resolves_element_paths(parser):
    schema = {'DERCurve': {'opModVoltVar': {
                  'CurveData[#]': {'#': "transform(take('705.Crv.0.ActPt'))",
                                   'xvalue': 'transform[705, Crv, 0, Pt[#], V]()'}}},
              '705': {'Crv[#]': {'#': 'transform[DERCurve, opModVoltVar](as_list())',
                                 'ActPt': 'transform[#, CurveData](count())',
                                 'Pt[#]': {'V': 'transform[#, CurveData[#], xvalue]()'}}},
              'AO': {'*points': 'transform[pts](unpairs(249, x, y))'},
              'seq[#] a': {'#': 'transform[a](as_list())', 'v': 'transform[#, x]()'},
              'seq[#] b': {'#': 'transform[b](as_list())', 'v': 'transform[#, x]()'}}
    fm = parser.field_map(schema)
    got = {(m.source, m.target): round(m.fidelity, 2) for m in fm.mappings}
    assert got[(('705', 'Crv', '0', 'Pt', '*', 'V'), ('DERCurve', 'opModVoltVar', 'CurveData', '*', 'xvalue'))] == 0.9  # take()
    assert got[(('DERCurve', 'opModVoltVar', 'CurveData'), ('705', 'Crv', '*', 'ActPt'))] == 0.3            # count()
    assert got[(('DERCurve', 'opModVoltVar', 'CurveData', '*', 'xvalue'), ('705', 'Crv', '*', 'Pt', '*', 'V'))] == 1.0
    assert got[(('pts',), ('AO', '*'))] == 1.0                                                              # spread
    assert got[(('a', 'x'), ('seq', '*', 'v'))] == 1.0 and got[(('b', 'x'), ('seq', '*', 'v'))] == 1.0


def test_path_matching_treats_wildcards_and_list_indices_alike():
    assert path_matches(('705', 'Crv', '0', 'Pt', '*', 'V'), ('705', 'Crv', '*', 'Pt', '*', 'V'))
    assert path_matches(('AO', '*'), ('AO', '249'))
    assert not path_matches(('AO', '249'), ('AO', '250'))
    assert not path_matches(('a',), ('a', 'b'))


def test_field_maps_compose_and_score_retention(parser):
    first = parser.field_map({'m': 'transform[a]()', 'n': 'transform[b](scale_int(1))', 'dropped_here': 'transform[c]()'})
    second = parser.field_map({'x': 'transform[m]()', 'y': 'transform[n](scale_int(1))'})
    chain = first.compose(second)
    assert {(m.source, m.target, round(m.fidelity, 2)) for m in chain.mappings} == {
        (('a',), ('x',), 1.0), (('b',), ('y',), 0.81)}
    assert chain.retention({('a',), ('b',), ('c',)}) == pytest.approx((1 + 0.81 + 0) / 3)
    assert chain.retention() == pytest.approx((1 + 0.81) / 2)          # over its own sources
    assert FieldMap([], []).retention(set()) == 1.0
    # field_map() of a chain of patterns composes the stages itself.
    assert {m.target for m in parser.field_map([{'m': 'transform[a]()'}, {'x': 'transform[m]()'}]).mappings} == {('x',)}


def test_bundled_definitions_round_trip_mostly_intact(parser):
    definitions = {(d['input_format'], d['output_format']): d['pattern'] for d in _bundled_definitions()}
    there = parser.field_map(definitions[('sunspec', '2030.5')])
    back = parser.field_map(definitions[('2030.5', 'sunspec')])
    assert there.compose(back).retention(there.sources()) > 0.9


# ---- field universes ----

def test_model_backed_field_universes():
    sunspec = field_universe.models_provider('sunspec')
    assert ('705', 'Crv', '*', 'Pt', '*', 'V') in sunspec and ('701', 'W') in sunspec
    inputs = field_universe.models_provider('1815.2.inputs')
    assert ('AI', '297') in inputs and ('BI', '93') in inputs and ('AO', '217') not in inputs
    assert ('AO', '217') in field_universe.models_provider('1815.2.outputs')
    assert field_universe.models_provider('61850') is None
    assert field_universe.parse_declared_fields(['a.b', ['c', 1]]) == {('a', 'b'), ('c', '1')}


def test_registry_field_universe_prefers_declared_then_providers_then_referenced_fields():
    registry = TransformRegistry(hubs={'a', 'b', 'x'}, field_providers=[lambda f: {('p',)} if f == 'x' else None])
    registry.register('a', 'b', {'y': 'transform[q]()', 'z': 'transform[r]()'})
    registry.register('x', 'a', {'q': 'transform[p]()', 's': 'transform[t]()'})
    assert registry.field_universe('a') == {('q',), ('r',), ('s',)}  # fallback: fields transforms touching 'a' mention
    assert registry.field_universe('x') == {('p',)}                # provider
    registry.declare_format('a', fields=['q', 'r', 'u'])
    assert registry.field_universe('a') == {('q',), ('r',), ('u',)}  # declared wins
    assert registry.edge_info('a', 'b')['retention'] == pytest.approx(2 / 3)


# ---- weighting and path selection ----

def test_edge_weights_follow_retention_and_overrides():
    registry = TransformRegistry(hubs={'a', 'b', 'c'})
    registry.declare_format('a', fields=['x', 'y'])
    registry.register('a', 'b', {'x': 'transform[x]()', 'y': 'transform[y]()'})
    registry.register('a', 'c', {'x': 'transform[x]()', 'y': None})
    full, half = registry.edge_info('a', 'b'), registry.edge_info('a', 'c')
    assert full['retention'] == 1.0 and full['weight'] == pytest.approx(0.01)
    assert half['retention'] == 0.5 and half['weight'] > full['weight'] and half['unmapped_targets'] == 1
    registry.register('a', 'c', {'x': 'transform[x]()', 'y': None}, update=True, lossiness=0.1)
    assert registry.edge_info('a', 'c')['retention'] == pytest.approx(0.9)
    with pytest.raises(TransformNotFoundError):
        registry.edge_info('c', 'a')


def test_lookup_prefers_the_chain_that_retains_more_even_with_more_hops():
    registry = TransformRegistry(hubs={'a', 'b', 'c'})
    registry.register('a', 'c', {'x': 'transform[x]()'})                                   # direct but sparse
    registry.register('a', 'b', {'x': 'transform[x]()', 'y': 'transform[y]()', 'z': 'transform[z]()'})
    registry.register('b', 'c', {'x': 'transform[x]()', 'y': 'transform[y]()', 'z': 'transform[z]()'})
    chain, retention, path = registry.lookup_scored('a', 'c')
    assert path == ['a', 'b', 'c'] and retention == 1.0 and len(chain) == 2
    # Scoring only the fields a resource publishes can change the answer: for x alone the direct edge is as good
    # and has fewer hops.
    assert registry.lookup_scored('a', 'c', fields=['x'])[2] == ['a', 'c']
    assert registry.lookup('a', 'a') == []


def test_ties_go_to_fewer_hops_and_leaves_are_never_intermediates():
    registry = TransformRegistry(hubs={'a', 'b', 'c'})
    same = {'x': 'transform[x]()'}
    registry.register('a', 'c', same)
    registry.register('a', 'b', same)
    registry.register('b', 'c', same)
    assert registry.lookup_scored('a', 'c')[2] == ['a', 'c']
    # 'dev' is a leaf: it may start or end a chain but a -> dev -> c is never considered.
    registry.register('a', 'dev', {'x': 'transform[x]()', 'y': 'transform[y]()'})
    registry.register('dev', 'c', {'x': 'transform[x]()', 'y': 'transform[y]()'})
    registry.register('a', 'b', {'x': 'transform[x]()', 'y': 'transform[y]()'}, update=True)
    assert registry.lookup_scored('a', 'c')[2] == ['a', 'c']
    assert registry.lookup_scored('dev', 'c')[2] == ['dev', 'c']
    registry.declare_format('dev', hub=True)
    assert registry.lookup_scored('a', 'c')[2] == ['a', 'dev', 'c']


def test_leaf_chains_go_through_the_hub_core():
    registry = TransformRegistry()                              # default hubs are the bundled standard formats
    registry.update_registry(_bundled_definitions())
    registry.register('acme_inverter', 'sunspec', {'701': {'W': 'transform[watts]()'}, '705': {'Ena': 'transform[vv_on]()'}})
    chain, retention, path = registry.lookup_scored('acme_inverter', '61850')
    assert path[0] == 'acme_inverter' and path[-1] == '61850' and set(path[1:-1]) <= DEFAULT_HUBS
    assert len(chain) == len(path) - 1
    with pytest.raises(TransformNotFoundError):
        registry.lookup('61850', 'acme_inverter')               # nothing maps back to the device


def test_registration_rejects_malformed_patterns_early():
    registry = TransformRegistry(hubs={'a', 'b'})
    with pytest.raises(ValueError, match='outside of a repeated group'):
        registry.register('a', 'b', {'v': 'transform[x, Pt[#], V]()'})
    assert not registry.has_format('a')


def test_hundreds_of_leaf_formats_do_not_slow_lookups_down():
    registry = TransformRegistry()
    registry.update_registry(_bundled_definitions())
    baseline = len(registry.candidate_paths('sunspec', '2030.5'))
    for i in range(300):
        registry.register(f'dev{i}', 'sunspec', {'701': {'W': f'transform[p{i}]()'}})
        registry.register('2030.5', f'dev{i}', {'w': 'transform[DERCapability, rtgMaxW]()'})
    assert len(registry.candidate_paths('sunspec', '2030.5')) == baseline   # leaves add no candidate chains
    started = time.perf_counter()
    registry.lookup('dev7', '61850')                                          # includes the weight refresh
    for _ in range(20):
        registry.lookup('sunspec', '2030.5')
    assert time.perf_counter() - started < 5.0


def test_update_registry_reads_lossiness_override(caplog):
    registry = TransformRegistry(hubs={'a', 'b'})
    registry.update_registry([{'input_format': 'a', 'output_format': 'b', 'pattern': {'x': 'transform[x]()'}, 'lossiness': 0.25}])
    assert registry.edge_info('a', 'b')['retention'] == pytest.approx(0.75)
    assert registry.edge_info('a', 'b')['lossiness_override'] == 0.25


def test_group_copy_before_deep_mappings_keeps_the_fields():
    """A profile wrapper copies a whole group; the next stage reads beneath it. The composed map must still
    know the leaf fields, or every chain that starts at a wrapper scores zero retention."""
    from interoperability.transform_parser import TransformParser
    parser = TransformParser()
    wrapper = parser.field_map([{'essControl': 'transform[essControl]()'}])
    deep = parser.field_map([{'DWMX': {'LimW': 'transform[essControl, limitW, wMaxSptVal]()'}}])
    composed = wrapper.compose(deep)
    assert composed.retention({('essControl', 'limitW', 'wMaxSptVal')}) == 1.0
    assert composed.retention({('essControl', 'other')}) == 0.0
