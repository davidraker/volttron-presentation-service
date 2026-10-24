"""Invariants of the bundled transform graph.

1. Every hub format reaches every other within MAX_HOPS, and every non-hub format reaches and is reached by every
   hub: a new format or version must bring its pair of edges to the ``61850`` hub (the one invariant of the
   loose graph), and the search does the rest.
2. Every direct transform between hub formats is classified against the alternative chains between the same
   formats (``TransformRegistry.edge_report``); the edges that carry nothing an alternative does not are listed
   here so that adding one is a conscious decision.
3. A direct transform and the best alternative chain produce the same values for the fields both deliver, on a
   typed sample message. Disagreements are convention conflicts between routes: the pairs known to disagree are
   recorded in KNOWN_CONFLICTS with the fields involved (see plans_and_analysis/SOURCES_AND_VERSIONS_PLAN.md,
   step 4) and expected to fail until the hub cleanup resolves them; resolving one must remove its entry.
"""
import itertools
import logging
import math
from pathlib import Path

import pytest

from interoperability.agent import PresentationService
from interoperability.transform_parser import TransformParser
from interoperability.transform_registry import MAX_HOPS, TransformRegistry

from graph_samples import MODEL_TYPED, Sampler, leaves, merge

PACKAGE = Path(__file__).resolve().parents[1] / 'src' / 'interoperability'

# Direct edges whose values disagree with their best alternative chain today (2026-10-24). Keys are the edge,
# values name the hub convention at issue. Each is a strict xfail: fixing the conflict makes the test pass and
# the entry must then be removed.
KNOWN_CONFLICTS = {
    ('1547', 'sunspec'): 'average line voltages: direct maps to 701.LLV/LNV, the 2030.5 route to one phase (VL2L3/VL2)',
    ('sunspec', '1547'): 'average line voltages: direct reads 701.LLV/LNV, the 2030.5 route one phase (VL2L3/VL2)',
    ('1815.2.inputs', '1547'): 'watt limit: the 1547 edge reads AI149 (DWMN), every other route AI148 (DWMX)',
    ('1815.2.inputs', '61850'): 'watt limit: DWMX.LimW from AI148 direct, AI149 through the 1547 edge',
    ('1815.2.inputs', 'sunspec'): 'watt limit: 704.WMaxLimPct from AI148 direct, AI149 through the 1547 edge',
    ('2030.5', 'sunspec'): 'hub folds DERSettings charge-rate settings into the DSTO ratings; setESRandomDelay versus '
                           'setESDelay; PF excitation polarity; 705 VRef from the curve versus rtgVNom',
    ('sunspec', '2030.5'): 'DSTO.VAMaxChaRtg fed from 702.WChaRteMaxRtg by sunspec_to_61850; rtgVNom versus curve VRef; '
                           'PF excitation polarity',
    ('sunspec', '61850'): 'sunspec_to_61850 writes DSTO.VAMaxChaRtg from the W rating and DFPF.PFLodTgt from PFWInj where the '
                          '2030.5 route uses PFWAbs; DECP.VRef from the 705 curve versus 702.VNomRtg; PFExtSet polarity',
    ('61850', 'sunspec'): 'PF excitation polarity (704.PFWInj.Ext) between 61850_to_sunspec and the 1547 route',
    ('61850', '1815.2.inputs'): 'the 1815.2 edge reads numbered or renamed hub keys (DHFW1, DLFW1, DCTE1, DGEN.IvarMaxRtg, '
                                'DVWC.OplTmsMax) that no other edge writes, so hub values from other sources never reach it',
    ('61850', '1815.2.outputs'): 'same numbered or renamed hub keys as the inputs edge (DCTE1, DVWC.OplTmsMax[1], ...)',
}


@pytest.fixture(scope='module')
def registry() -> TransformRegistry:
    logging.disable(logging.WARNING)
    reg = TransformRegistry()
    for name, spec in PresentationService._load_bundled_formats(PACKAGE / 'formats').items():
        reg.declare_format(name, **spec)
    reg.update_registry(PresentationService._load_bundled_definitions(PACKAGE / 'transforms'))
    return reg


def _hubs(reg):
    return sorted(reg.hubs & set(reg.registry.nodes))


def test_every_hub_pair_is_reachable(registry):
    missing = [(a, b) for a, b in itertools.permutations(_hubs(registry), 2) if not registry.candidate_paths(a, b)]
    assert missing == []


def test_every_other_format_reaches_and_is_reached_by_every_hub(registry):
    others = sorted(set(registry.registry.nodes) - registry.hubs)
    assert others, 'the bundled graph has profile and controller formats beside the hubs'
    missing = [(o, h) for o in others for h in _hubs(registry) if not registry.candidate_paths(o, h)]
    missing += [(h, o) for o in others for h in _hubs(registry) if not registry.candidate_paths(h, o)]
    assert missing == []


def test_hub_edges_are_classified_and_subset_edges_are_known(registry):
    reports = {(a, b): registry.edge_report(a, b) for a, b in registry.registry.edges
               if a in registry.hubs and b in registry.hubs}
    assert {r['classification'] for r in reports.values()} <= {'no alternative', 'adds coverage', 'subset of alternative'}
    subset = sorted(k for k, r in reports.items() if r['classification'] == 'subset of alternative')
    # The 1547 cross-reference drafts reach 1815.2 through SunSpec with more fields than they carry directly.
    assert subset == [('1547', '1815.2.inputs'), ('1547', '1815.2.outputs')]
    assert all(not reports[k]['needed_for_reachability'] for k in subset)
    assert [(r['input_format'], r['output_format']) for r in registry.prune_candidates()] == subset
    # The OpenFMB hubs are pure spokes of 61850.
    assert reports[('openfmb.ess', '61850')]['classification'] == 'no alternative'


def _samples(registry):
    sampler = Sampler()
    samples = {f: sampler.build(f, registry.field_universe(f)) for f in MODEL_TYPED if f in registry.registry.nodes}
    parser = TransformParser()
    for derived in ('61850', '1547'):
        message = {}
        for source in MODEL_TYPED:
            data = registry.registry.get_edge_data(source, derived)
            if data is not None:
                merge(message, parser.build_transform_from_schema([data['transform']]).execute(samples[source]))
        samples[derived] = message
    return sampler, samples


def _edges_with_alternatives():
    reg = TransformRegistry()
    for name, spec in PresentationService._load_bundled_formats(PACKAGE / 'formats').items():
        reg.declare_format(name, **spec)
    reg.update_registry(PresentationService._load_bundled_definitions(PACKAGE / 'transforms'))
    return [(a, b) for a, b in sorted(reg.registry.edges) if a in reg.hubs and b in reg.hubs
            and any(len(p) > 2 for p in reg.candidate_paths(a, b))]


@pytest.fixture(scope='module')
def samples(registry):
    return _samples(registry)


@pytest.mark.parametrize('edge', _edges_with_alternatives(), ids=lambda e: f'{e[0]}->{e[1]}')
def test_direct_and_alternative_routes_agree(registry, samples, edge, request):
    if edge in KNOWN_CONFLICTS:
        request.applymarker(pytest.mark.xfail(strict=True, reason=KNOWN_CONFLICTS[edge]))
    sampler, messages = samples
    source, target = edge
    report = registry.edge_report(source, target)
    parser = TransformParser()
    direct = parser.build_transform_from_schema([registry.registry[source][target]['transform']]).execute(messages[source])
    path = report['alternative']
    alternative = parser.build_transform_from_schema(
        [registry.registry[s][t]['transform'] for s, t in zip(path, path[1:])]).execute(messages[source])
    direct_leaves, alternative_leaves = dict(leaves(direct)), dict(leaves(alternative))
    shared = sorted(set(direct_leaves) & set(alternative_leaves), key=str)
    assert shared, 'the two routes deliver no common field, so nothing can be compared'

    def same(a, b):
        if isinstance(a, float) and isinstance(b, float):
            return math.isclose(a, b, rel_tol=1e-9)
        return a == b

    def origin(value):
        return sampler.origin.get(value, ('', ('const',)))[1] if isinstance(value, float) else repr(value)

    def comparable(a, b):
        # A leaf is compared when at least one route's value traces to a sampled source field, or when both are
        # flags or enumerations. Two untraced numbers are derived constants (point counts, defaults) whose values
        # depend on the sample's shape rather than on the routes.
        traced = any(isinstance(v, float) and v in sampler.origin for v in (a, b))
        return traced or all(isinstance(v, (bool, int)) and not isinstance(v, float) for v in (a, b)) and (isinstance(a, bool) or isinstance(b, bool))

    conflicts = [f'{".".join(map(str, k))}: direct <- {".".join(map(str, origin(direct_leaves[k])))}, '
                 f'{"->".join(path)} <- {".".join(map(str, origin(alternative_leaves[k])))}'
                 for k in shared if comparable(direct_leaves[k], alternative_leaves[k])
                 and not same(direct_leaves[k], alternative_leaves[k])]
    assert conflicts == []


def test_model_formats_can_be_registered():
    from interoperability import field_universe
    name = 'test-format@9'
    try:
        field_universe.register_model_format(name, lambda: {('a', 'b'), ('c',)})
        assert field_universe.models_provider(name) == {('a', 'b'), ('c',)}
        assert name in field_universe.model_formats()
        reg = TransformRegistry(hubs={name, 'x'})
        reg.register(name, 'x', {'b': 'transform[a, b]()'})
        assert reg.edge_info(name, 'x')['universe'] == 2
    finally:
        field_universe._MODEL_FORMATS.pop(name, None)
        field_universe._cache.pop(name, None)
