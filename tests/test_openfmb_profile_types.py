"""Every OpenFMB profile the generated cases produce must be encodable: each leaf of the transformed payload has the
type its protobuf field declares. Protobuf's JSON parser refuses, for instance, an integer in a bool field, and the bus
adapter then drops the whole profile (seen on the real platform as a ParseError per relayed SunSpec control profile when
the volt-var enable register, a SunSpec enum16, reached ``modEna`` as 1). The check walks the descriptor so every
mismatch is reported at once rather than the first one only."""
from __future__ import annotations

import json
from importlib import resources
from pathlib import Path

import pytest

from case_helpers import fake_driver_all_message
from interoperability.transform_parser import TransformParser
from interoperability.transform_registry import TransformRegistry

pytest.importorskip('google.protobuf')
from google.protobuf.descriptor import FieldDescriptor as FD  # noqa: E402
from interoperability.codecs import openfmb as codec  # noqa: E402

CASES = Path(__file__).parent / 'integration'
NUMERIC = {FD.TYPE_DOUBLE, FD.TYPE_FLOAT, FD.TYPE_INT32, FD.TYPE_INT64, FD.TYPE_UINT32, FD.TYPE_UINT64, FD.TYPE_SINT32,
           FD.TYPE_SINT64, FD.TYPE_FIXED32, FD.TYPE_FIXED64, FD.TYPE_SFIXED32, FD.TYPE_SFIXED64}
PROFILES = [('fake_sunspec', 'fake_sunspec_pv', 'fake_sunspec_pv.fake.csv', 'openfmb.solar.control', 'solarmodule.SolarControlProfile'),
            ('fake_sunspec', 'fake_sunspec_pv', 'fake_sunspec_pv.fake.csv', 'openfmb.solar.reading', 'solarmodule.SolarReadingProfile'),
            ('fake_dnp3', 'fake_dnp3_der', 'fake_dnp3_der.fake.csv', 'openfmb.ess.control', 'essmodule.ESSControlProfile'),
            ('fake_dnp3', 'fake_dnp3_der', 'fake_dnp3_der.fake.csv', 'openfmb.ess.reading', 'essmodule.ESSReadingProfile')]


def registry_for(case: Path) -> TransformRegistry:
    config = json.loads((case / 'transform_scaling' / 'presentation_config.json').read_text())
    registry = TransformRegistry()
    for name, spec in config['formats'].items():
        registry.declare_format(name, **spec)
    bundled = resources.files('interoperability').joinpath('transforms')
    registry.update_registry([d for f in sorted(bundled.iterdir(), key=lambda f: f.name)
                              if f.is_file() and f.name.endswith('.json') for d in json.loads(f.read_text())]
                             + config['transforms'])
    return registry


def type_mismatches(descriptor, payload, path='') -> list[tuple[str, str]]:
    """(path, problem) for every leaf whose Python type the protobuf JSON parser would refuse for its field."""
    if not isinstance(payload, dict):
        return [(path, f'expected a message, got {type(payload).__name__}')]
    fields = {f.json_name: f for f in descriptor.fields} | {f.name: f for f in descriptor.fields}
    out = []
    for key, value in payload.items():
        field = fields.get(key)
        here = f'{path}.{key}' if path else key
        if field is None:
            out.append((here, 'unknown field'))
            continue
        repeated = field.is_repeated if hasattr(field, 'is_repeated') else field.label == FD.LABEL_REPEATED
        for i, item in enumerate(value if repeated and isinstance(value, list) else [value]):
            at = f'{here}[{i}]' if repeated else here
            if field.type == FD.TYPE_MESSAGE:
                wrapper = field.message_type.full_name.startswith('google.protobuf.')
                if isinstance(item, dict):
                    out += type_mismatches(field.message_type, item, at)
                elif wrapper and field.message_type.full_name == 'google.protobuf.BoolValue' and not isinstance(item, bool):
                    out.append((at, f'BoolValue got {type(item).__name__} {item!r}'))
                elif not wrapper:
                    out.append((at, f'expected message {field.message_type.full_name}, got {type(item).__name__} {item!r}'))
            elif field.type == FD.TYPE_BOOL and not isinstance(item, bool):
                out.append((at, f'bool got {type(item).__name__} {item!r}'))
            elif field.type in NUMERIC and (isinstance(item, bool) or not isinstance(item, (int, float))):
                out.append((at, f'number got {type(item).__name__} {item!r}'))
            elif field.type in NUMERIC - {FD.TYPE_DOUBLE, FD.TYPE_FLOAT} and isinstance(item, float) and not item.is_integer():
                out.append((at, f'integer got {item!r}'))
            elif field.type == FD.TYPE_STRING and not isinstance(item, str):
                out.append((at, f'string got {type(item).__name__} {item!r}'))
    return out


@pytest.mark.parametrize('case, device_format, registry_file, target, proto', PROFILES, ids=[p[3] for p in PROFILES])
@pytest.mark.parametrize('mode', ['transform', 'driver'])
def test_profile_leaves_match_their_protobuf_types(case, device_format, registry_file, target, proto, mode):
    registry = registry_for(CASES / case)
    chain, retention, path = registry.lookup_scored(device_format, target)
    assert path[-1] == target and retention > 0
    values = fake_driver_all_message(CASES / case, mode, registry_file)
    pipeline = TransformParser(context={'mrid': '7d1a2b3c-0000-4000-8000-000000000001', 'name': 'case device'})
    result = pipeline.build_transform_from_schema(chain).execute([values, {name: {'units': ''} for name in values}])
    assert type_mismatches(codec.message_class(proto).DESCRIPTOR, result) == []
    # And the parser agrees: the profile encodes and comes back.
    assert codec.decode(proto, codec.encode(proto, result))


def test_sunspec_excitation_and_enter_service_flags_round_trip():
    """SunSpec codes the PF excitation as 0 over-excited / 1 under-excited and enter-service as 0/1; 61850 and OpenFMB
    carry both as booleans (PFExtSet TRUE = over-excited)."""
    # The direct sunspec <-> 61850 definitions (the registry's route between the two formats may run through 1547).
    bundled = resources.files('interoperability').joinpath('transforms')
    defs = [d for f in bundled.iterdir() if f.is_file() and f.name.endswith('.json') for d in json.loads(f.read_text())]
    direct = lambda a, b: [d['pattern'] for d in defs if d.get('input_format') == a and d.get('output_format') == b]
    to_hub = TransformParser().build_transform_from_schema(direct('sunspec', '61850'))
    back = TransformParser().build_transform_from_schema(direct('61850', 'sunspec'))
    hub = to_hub.execute({'704': {'PFWInj': {'Ext': 0}}, '703': {'ES': 1}})
    assert hub['DFPF']['PFExtSet'] is True and hub['DCTE']['RtnSrvAuth'] is True
    hub = to_hub.execute({'704': {'PFWInj': {'Ext': 1}}, '703': {'ES': 0}})
    assert hub['DFPF']['PFExtSet'] is False and hub['DCTE']['RtnSrvAuth'] is False
    regs = back.execute({'DFPF': {'PFExtSet': True}, 'DCTE': {'RtnSrvAuth': True}})
    assert regs['704']['PFWInj']['Ext'] == 0 and regs['703']['ES'] == 1 and not isinstance(regs['703']['ES'], bool)
    regs = back.execute({'DFPF': {'PFExtSet': False}, 'DCTE': {'RtnSrvAuth': False}})
    assert regs['704']['PFWInj']['Ext'] == 1 and regs['703']['ES'] == 0


def test_durations_split_into_seconds_and_nanoseconds_and_back():
    """Trip-curve times (seconds, fractional) become OpenFMB ClearingTime {seconds, nanoseconds} and come back whole."""
    bundled = resources.files('interoperability').joinpath('transforms')
    defs = [d for f in bundled.iterdir() if f.is_file() and f.name.endswith('.json') for d in json.loads(f.read_text())]
    direct = lambda a, b: [d['pattern'] for d in defs if d.get('input_format') == a and d.get('output_format') == b]
    out = TransformParser(context={'mrid': 'm', 'name': 'n'}).build_transform_from_schema(direct('61850', 'openfmb.solar')) \
        .execute({'DHFT': {'TrZnSt': {'PTOF': {'TmHzCrv': {'crvPts': [{'xVal': 61.2, 'yVal': 0.16}]}}}},
                  'DVVR': {'OpnLoopMax': 2.5}})
    control = out['solarControl']['solarControlFSCC']['SolarControlScheduleFSCH']['ValDCSG']['crvPts'][0]['control']
    assert control['tmHzTripOperation']['overCrvPts'][0]['tmVal'] == {'seconds': 0, 'nanoseconds': 160000000}
    assert control['voltVarOperation']['vVarParameter']['OplTmmsMax'] == {'seconds': 2, 'nanoseconds': 500000000}
    back = TransformParser().build_transform_from_schema(direct('openfmb.solar', '61850')).execute(out)
    assert back['DHFT']['TrZnSt']['PTOF']['TmHzCrv']['crvPts'][0]['yVal'] == pytest.approx(0.16)
    assert back['DVVR']['OpnLoopMax'] == pytest.approx(2.5)
