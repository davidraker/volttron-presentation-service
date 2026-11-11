"""The ``61850`` hub format speaks IEC 61850-7-420 Edition 2.

Every key the hub transforms read or write must be a logical node class, data object and attribute path that the IEC
name space definitions (7-420 Ed2, 7-4, 7-3) define, flattened as HUB_61850_FORMAT.md §2.3 describes, or a declared
``x-`` extension group for a function the standard does not model. The NSD files are IEC code components and are not
in the repository: ``IEC61850_NSD`` names their directory, and the checks are skipped without it.

A second rule guards the wire: a transform from the hub to a real IEC 61850 device format (any format whose name
starts with ``iec61850``) may not read an extension group, since nothing on an MMS or GOOSE link can receive it.
"""
import logging
from pathlib import Path

import pytest

from interoperability.agent import PresentationService
from interoperability.iec61850_vocabulary import EXTENSION_PREFIX, load, report
from interoperability.transform_registry import TransformRegistry

PACKAGE = Path(__file__).resolve().parents[1] / 'src' / 'interoperability'
HUB = '61850'
WIRE_PREFIX = 'iec61850'

# The hub's conventions beyond the plain class vocabulary (HUB_61850_FORMAT.md §2.2). Extension groups are functions the
# standard does not model; each names the standard that defines it. Instances are the numbered logical nodes the hub
# keeps, with their roles. Extension objects are x- data objects on standard classes where Edition 2 has no object.
EXTENSIONS = {
    'x-DVWD': 'IEEE 1815.2-2025 Volt-Watt (Dynamic) function',
    'x-DWSM': 'IEEE 1815.2-2025 Watt (Active Power) Smoothing function',
    'x-DPFC': 'IEEE 1815.2-2025 Power Factor Correction function',
    'x-DPRG': 'IEEE 1815.2-2025 Pricing Signal (Generation) function',
    'x-MESA': 'IEEE 1815.2-2025 system block: profile version, counts, freeze interval, selected schedule and curve',
}
INSTANCES = {
    'PTOV': {1: 'high-voltage must-trip curve', 2: 'high-voltage momentary-cessation curve'},
    'PTUV': {1: 'low-voltage must-trip curve', 2: 'low-voltage momentary-cessation curve'},
    'PTOF': {1: 'high-frequency must-trip curve', 2: 'high-frequency momentary-cessation curve'},
    'PTUF': {1: 'low-frequency must-trip curve', 2: 'low-frequency momentary-cessation curve'},
    'DHFW': {2: 'curve-based high-frequency-watt (the profile\'s "Frequency-Watt Curve" mode)'},
    'DLFW': {2: 'curve-based low-frequency-watt'},
    'DWFL': {2: 'active power response mode 2', 3: 'active power response mode 3'},
    'LCCH': {1: 'system communication channel', 2: 'meter communication channel'},
    'FSCH': {n: f'schedule {n} of the profile\'s 100' for n in range(1, 101)},
}
# x- data objects on standard classes are accepted on any class; tools/hub_edition2_rename.py is the list of them.


@pytest.fixture(scope='module')
def vocabulary():
    vocab = load()
    if vocab is None:
        pytest.skip('IEC61850_NSD does not point at the IEC 61850 NSD files')
    vocab.extensions = {name: {'*'} for name in EXTENSIONS}
    vocab.instances = {cls: set(roles) for cls, roles in INSTANCES.items()}
    vocab.extension_objects = {cls: {'*'} for cls in vocab.classes}
    return vocab


@pytest.fixture(scope='module')
def registry() -> TransformRegistry:
    logging.disable(logging.WARNING)
    reg = TransformRegistry()
    for name, spec in PresentationService._load_bundled_formats(PACKAGE / 'formats').items():
        reg.declare_format(name, **spec)
    reg.update_registry(PresentationService._load_bundled_definitions(PACKAGE / 'transforms'))
    return reg


def test_nsd_set_is_complete(vocabulary):
    """The three parts the hub vocabulary is pinned to are present, and every base class resolves."""
    assert {'IEC 61850-7-420', 'IEC 61850-7-4', 'IEC 61850-7-3'} <= set(vocabulary.parts)
    undefined = sorted({c.base for c in vocabulary.classes.values() if c.base and c.base not in vocabulary.classes})
    assert not undefined, f'abstract base classes missing from the NSD set: {undefined}'


def test_every_hub_key_is_an_edition_2_name_or_a_declared_extension(vocabulary, registry):
    rep = report(vocabulary, registry.field_universe(HUB))
    violations = [r for items in rep['violations'].values() for r in items]
    lines = [f"{'.'.join(map(str, r.path))}: {r.status} ({r.detail})" for r in violations[:40]]
    assert not violations, f"{len(violations)} of {rep['total']} hub paths are not Edition 2 names:\n  " + '\n  '.join(lines)


def test_extension_groups_never_reach_a_wire_61850_format(registry):
    leaks = []
    for _, target, data in registry.registry.out_edges(HUB, data=True):
        if target.startswith(WIRE_PREFIX):
            leaks += [(target, p) for p in data['field_map'].sources() if str(p[0]).startswith(EXTENSION_PREFIX)]
    assert not leaks, f'extension groups read by a transform to a wire 61850 format: {leaks}'
