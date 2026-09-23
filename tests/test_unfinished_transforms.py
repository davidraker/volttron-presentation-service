"""Checks for the drafts in transforms/unfinished/.

The only remaining draft is the SunSpec curve-point mapping. Its SunSpec-to-61850 direction
uses an unquoted ``Pt[#]`` "for each point" segment the expression language cannot parse
yet, which is what keeps it out of the bundled set. The agent does not load this directory
(see ``test_agent_loads_bundled_definitions``), but the drafts must stay well formed so they
can be promoted once the language supports them.
"""
import json
from importlib import resources

import pytest

from interoperability.transform_parser import TransformParser

UNFINISHED = resources.files('interoperability').joinpath('transforms', 'unfinished')


def _draft_files():
    return sorted((f for f in UNFINISHED.iterdir() if f.is_file() and f.name.endswith('.json')),
                  key=lambda f: f.name)


@pytest.fixture(scope='module')
def parser():
    return TransformParser()


def test_drafts_are_well_formed():
    files = _draft_files()
    assert files, 'expected at least the curve mapping draft'
    for f in files:
        definitions = json.loads(f.read_text())
        assert isinstance(definitions, list) and definitions, f.name
        for d in definitions:
            assert {'input_format', 'output_format', 'pattern'} <= d.keys(), f.name
            assert isinstance(d['pattern'], dict) and d['pattern'], f.name


def _compiles(parser, pattern):
    try:
        return parser.build_transform_from_schema(pattern) is not None
    except Exception:
        return False


@pytest.mark.parametrize('draft', _draft_files(), ids=lambda f: f.name)
def test_each_draft_still_has_a_reason_to_be_unfinished(parser, draft):
    """Once every definition in a draft compiles it should be moved into transforms/."""
    results = [_compiles(parser, d['pattern']) for d in json.loads(draft.read_text())]
    assert not all(results), f'{draft.name} compiles completely; promote it to transforms/'
