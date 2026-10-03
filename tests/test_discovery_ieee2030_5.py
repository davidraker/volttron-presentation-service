"""The IEEE 2030.5 mirror generator: registry rows, device format and the round trip through the service."""
from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from interoperability.discovery import ieee2030_5
from interoperability.transform_parser import TransformParser

CASE = Path(__file__).parent / 'integration' / 'fake_sunspec'
MODE_DIR = CASE / 'transform_scaling'


@pytest.fixture(scope='module')
def registry():
    return ieee2030_5.load_registry(MODE_DIR / 'presentation_config.json')


@pytest.fixture(scope='module')
def mirror(registry):
    return ieee2030_5.discover_mirror(registry, 'fake_sunspec_pv')


def test_mirror_points_follow_the_client_polarity(mirror):
    names = {p.name: p for p in mirror.points}
    # Upward: what the inverter can report. Downward: the controls the inverter can take.
    assert names['DERSettings_setMaxW'].writable and names['MirrorMeterReading_V_PhaseA'].writable
    assert names['DERStatus_connectStatus'].writable and names['DeviceInformation_mfModel'].writable
    assert not names['DERControl_opModMaxLimW'].writable and not names['DERCurve_opModVoltVar_CurveData'].writable
    assert not names['DERControlList'].writable
    # Curves are one list-valued point, cut at CurveData; DERControl settings the device *reports* are not upward rows.
    assert not any(p.name.endswith('_xvalue') for p in mirror.points)
    assert all(p.resource in ieee2030_5.UPWARD_RESOURCES for p in mirror.upward())
    assert all(p.resource in ieee2030_5.DOWNWARD_RESOURCES for p in mirror.downward())
    assert names['DERSettings_setMaxW'].via == 'sunspec > 2030.5' and names['DERControl_opModMaxLimW'].via.startswith('2030.5 >')


def test_registry_rows_validate_against_the_driver_schema(mirror):
    rows = ieee2030_5.registry_rows(mirror)
    by_name = {r['Volttron Point Name']: r for r in rows}
    assert by_name['DERSettings_setMaxW'] == {'Volttron Point Name': 'DERSettings_setMaxW', 'Path': 'DERSettings.setMaxW', 'Writable': 'TRUE',
                                             'Multiplier': 0, 'Scaling': 1, 'Units': 'W', 'Starting Value': 0, 'Notes': 'via sunspec > 2030.5'}
    assert by_name['MirrorMeterReading_W']['Units'] == 'W' and by_name['MirrorMeterReading_W']['Multiplier'] == ''
    assert by_name['DERCapability_type']['Starting Value'] == 83 and 'required by the schema' in by_name['DERCapability_type']['Notes']
    assert by_name['DERControl_opModMaxLimW']['Units'] == '% x100' and by_name['DERControl_opModMaxLimW']['Writable'] == 'FALSE'
    assert by_name['DERSettings_setGradW']['Units'] == '% x100/s'
    assert list(rows[0]) == ieee2030_5.COLUMNS


def test_generated_mirror_case_is_current(registry, mirror):
    """``build_configs.py`` wrote the mirror files; they must match what the generator produces now."""
    for mode in ('transform', 'driver'):
        out = CASE / f'{mode}_scaling'
        with (out / 'fake_sunspec_pv_sep2.ieee2030_5.csv').open() as f:
            rows = list(csv.DictReader(f))
        expected = [{k: str(v) for k, v in row.items()} for row in ieee2030_5.registry_rows(
            ieee2030_5.discover_mirror(ieee2030_5.load_registry(out / 'presentation_config.json'), 'fake_sunspec_pv'))]
        assert rows == expected
        device = json.loads((out / 'fake_sunspec_pv_sep2.ieee2030_5.device.json').read_text())
        assert device['remote_config']['driver_type'] == 'ieee2030_5' and device['remote_config']['subscribe'] is True
        fragment = json.loads((out / 'fake_sunspec_pv_sep2.presentation.json').read_text())
        assert set(fragment) == {'formats', 'transforms', 'mappings'}
        assert [m['uai'] for m in fragment['mappings']] == [['site1', 'pv_sep2'], ['site1', 'pv_sep2_2030_5']]


def test_mirror_round_trips_through_the_convention(registry, mirror):
    fragment = ieee2030_5.presentation_fragment('fake_sunspec_pv_sep2', mirror, 'devices/site1/feeder1/pv_sep2', ['site1', 'pv_sep2'])
    to_sep2, from_sep2 = fragment['transforms']
    parser = TransformParser()
    # What the ieee2030_5 driver publishes (controls it received, upward rows as last written), as [values, meta].
    published = [{'DERControl_opModMaxLimW': 5000, 'DERControl_opModEnergize': True,
                  'DERCurve_opModVoltVar_CurveData': [{'xvalue': 9500, 'yvalue': 2500}],
                  'DERControlList': [{'mRID': 'EE', 'interval': {'start': 1, 'duration': 2}}],
                  'DERSettings_setMaxW': 6000, 'MirrorMeterReading_W': 4321}, {}]
    message = parser.build_transform_from_schema([to_sep2['pattern']]).execute(published)
    assert message['DERControl'] == {'opModMaxLimW': 5000, 'opModEnergize': True}
    assert message['DERCurve']['opModVoltVar']['CurveData'] == [{'xvalue': 9500, 'yvalue': 2500}]
    assert message['DERControlList'][0]['interval'] == {'start': 1, 'duration': 2} and message['DERSettings'] == {'setMaxW': 6000}
    # A 2030.5 message written to the mirror becomes flat points, upward rows only.
    flat = parser.build_transform_from_schema([from_sep2['pattern']]).execute(
        {'DERSettings': {'setMaxW': 7000}, 'MirrorMeterReading': {'W': 100, 'V': {'PhaseA': 240}},
         'DERControl': {'opModMaxLimW': 1}})
    assert flat == {'DERSettings_setMaxW': 7000, 'MirrorMeterReading_W': 100, 'MirrorMeterReading_V_PhaseA': 240}


def test_inverter_to_mirror_chain_through_the_service(registry, mirror):
    """SunSpec inverter telemetry -> 2030.5 -> the mirror's flat points: the path the service's writer would take."""
    fragment = ieee2030_5.presentation_fragment('fake_sunspec_pv_sep2', mirror, 'devices/site1/feeder1/pv_sep2', ['site1', 'pv_sep2'])
    registry.declare_format('fake_sunspec_pv_sep2', **fragment['formats']['fake_sunspec_pv_sep2'])
    registry.update_registry(fragment['transforms'])
    chain, retention, path = registry.lookup_scored('fake_sunspec_pv', 'fake_sunspec_pv_sep2')
    assert path == ['fake_sunspec_pv', 'sunspec', '2030.5', 'fake_sunspec_pv_sep2'] and retention > 0
    from tests.test_integration_fake_sunspec import fake_driver_all_message
    flat = TransformParser().execute_chain(chain, [fake_driver_all_message('transform'), {}]) \
        if hasattr(TransformParser(), 'execute_chain') else TransformParser().build_transform_from_schema(chain).execute([fake_driver_all_message('transform'), {}])
    assert flat['DERSettings_setMaxW'] == pytest.approx(flat['DERSettings_setMaxW']) and 'MirrorMeterReading_W' in flat
    assert all(not k.startswith('DERControl') for k in flat)         # controls do not flow into the server
    sunspec = TransformParser().build_transform_from_schema(registry.lookup('fake_sunspec_pv', 'sunspec')).execute([fake_driver_all_message('transform'), {}])
    assert flat['MirrorMeterReading_W'] == pytest.approx(sunspec['701']['W'])
