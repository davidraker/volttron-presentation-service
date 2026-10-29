"""Alias references in the mapping engine: chains of aliases resolve to the canonical, cycles are refused at
ingest and at resolve, and a dangling alias is kept but reported."""
import logging

import pytest

from interoperability.mapping_engine import ResourceReferenceCycleError, UAITree


def canonical(uai, data_format='sunspec'):
    return {'uai': uai, 'resource_type': 'canonical',
            'resource': {'data_format': data_format, 'owner': 'platform.driver',
                         'publication_topic': f'devices/{"/".join(uai)}/all'}}


def alias(uai, references, data_format='61850', **extra):
    return {'uai': uai, 'resource_type': 'alias',
            'resource': {'data_format': data_format, 'owner': 'test', 'references': references, **extra}}


def test_alias_of_alias_resolves_to_the_canonical_with_every_hop_listed():
    tree = UAITree()
    tree.ingest_mappings([canonical(('site1', 'pv')),
                          alias(('site1', 'pv_61850'), ('site1', 'pv')),
                          alias(('remote', 'pv'), ('site1', 'pv_61850'), data_format='openfmb.solar.reading')])
    node, as_format, aliases = tree.resolve(('remote', 'pv'))
    assert node.is_canonical and node.uai == ('site1', 'pv')
    assert as_format == 'openfmb.solar.reading'                        # the outermost alias's format
    assert [a.uai for a in aliases] == [('remote', 'pv'), ('site1', 'pv_61850')]   # outermost first
    assert tree.check_references() == {'cycles': [], 'dangling': []}


def test_mutual_references_are_refused_at_ingest_and_removed():
    tree = UAITree()
    with pytest.raises(ResourceReferenceCycleError) as excinfo:
        tree.ingest_mappings([canonical(('site1', 'pv')),
                              alias(('x', 'a'), ('x', 'b')),
                              alias(('x', 'b'), ('x', 'a'))])
    assert 'x/a -> x/b -> x/a' in str(excinfo.value) or 'x/b -> x/a -> x/b' in str(excinfo.value)
    assert len(excinfo.value.cycles) == 1                               # one cycle, reported once
    # The cyclic aliases are gone; the rest of the batch survived and the tree is usable.
    assert tree.get_node_by_uai(('x', 'a')) is None and tree.get_node_by_uai(('x', 'b')) is None
    node, _, _ = tree.resolve(('site1', 'pv'))
    assert node.is_canonical
    assert tree.check_references() == {'cycles': [], 'dangling': []}


def test_self_reference_through_prefix_fallback_is_a_cycle():
    # ('x', 'a') references ('x', 'a', 'deeper'); nothing is there, so the non-strict lookup falls back to ('x', 'a').
    tree = UAITree()
    with pytest.raises(ResourceReferenceCycleError):
        tree.ingest_mappings([alias(('x', 'a'), ('x', 'a', 'deeper'))])
    assert tree.get_node_by_uai(('x', 'a')) is None


def test_resolve_raises_on_a_cycle_instead_of_recursing():
    tree = UAITree()
    tree.ingest_mappings([canonical(('site1', 'pv')), alias(('x', 'a'), ('site1', 'pv'))])
    # Rewire the alias behind the engine's back, as a direct store edit could.
    tree.get_node_by_uai(('x', 'a')).references = ('x', 'a')
    with pytest.raises(ResourceReferenceCycleError) as excinfo:
        tree.resolve(('x', 'a'))
    assert excinfo.value.cycles == [[('x', 'a'), ('x', 'a')]]
    assert tree.check_references()['cycles'] == [[('x', 'a'), ('x', 'a')]]


def test_dangling_alias_is_kept_and_reported(caplog):
    tree = UAITree()
    with caplog.at_level(logging.WARNING, logger='interoperability.mapping_engine'):
        tree.ingest_mappings([alias(('x', 'early'), ('site1', 'pv'))])      # its canonical is not here yet
    assert 'x/early does not lead to a canonical resource' in caplog.text
    assert tree.check_references() == {'cycles': [], 'dangling': [('x', 'early')]}
    node, _, aliases = tree.resolve(('x', 'early'))
    assert node is None and [a.uai for a in aliases] == [('x', 'early')]
    tree.ingest_mappings([canonical(('site1', 'pv'))])                   # the canonical arrives later
    assert tree.check_references() == {'cycles': [], 'dangling': []}
    assert tree.resolve(('x', 'early'))[0].is_canonical


def test_single_segment_uais_are_resources_too():
    # A one-segment UAI (a remote bus topic such as "status") sits directly under the root.
    tree = UAITree()
    tree.ingest_mappings([canonical(('status',)),
                          alias(('telemetry',), ('status',)),
                          canonical(('site1', 'pv'))])
    node, as_format, aliases = tree.resolve(('telemetry',))
    assert node.is_canonical and node.uai == ('status',) and as_format == '61850'
    assert [a.uai for a in aliases] == [('telemetry',)]
    assert tree.resolve(('site1', 'pv'))[0].uai == ('site1', 'pv')              # deeper resources are unaffected
    assert tree.check_references() == {'cycles': [], 'dangling': []}


def test_single_segment_cycle_is_refused_like_any_other():
    tree = UAITree()
    with pytest.raises(ResourceReferenceCycleError):
        tree.ingest_mappings([alias(('a',), ('b',)), alias(('b',), ('a',))])
    assert tree.get_node_by_uai(('a',)) is None and tree.get_node_by_uai(('b',)) is None


def test_prefix_fallback_reaches_a_single_segment_resource_only_when_not_strict():
    tree = UAITree()
    tree.ingest_mappings([canonical(('site1',))])
    assert tree.resolve(('site1', 'unknown'))[0].uai == ('site1',)              # non-strict: one level up
    assert tree.resolve(('site1', 'unknown'), strict=True)[0] is None            # strict: exact UAI only
