"""Tests for the OpenFMB pydantic models generated from the protobuf PSM, and their profile builders."""
from __future__ import annotations

import enum
import json
import time

import pytest

from interoperability import field_universe
from interoperability.models import openfmb
from interoperability.models.openfmb import PROFILES, OpenFMBMessage, common_module, ess_module, profile_builders as pb
from interoperability.models.openfmb.generate_samples import example_profiles

# Messages exactly as protobuf's JSON mapping renders them (int64 as strings, enums by name, wrappers unwrapped).
CANONICAL_READING = {'essReading': {'readingMMXU': {'Hz': {'mag': 60.0}, 'W': {'net': {'cVal': {'mag': 12480.0}}},
                                                    'PhV': {'phsA': {'cVal': {'mag': 240.1}}}}}}
CANONICAL_CONTROL = {
    'controlMessageInfo': {'messageInfo': {'identifiedObject': {'mRID': 'ctl-1'}, 'messageTimeStamp': {'seconds': '1700000000'}}},
    'ess': {'conductingEquipment': {'mRID': 'ess-1'}},
    'essControl': {'essControlFSCC': {'essControlScheduleFSCH': {'ValDCSG': {'crvPts': [
        {'control': {'mode': {'setVal': 'GridConnectModeKind_CSI'},
                     'voltVarOperation': {'crvPts': [{'varVal': 0.44, 'voltVal': 0.95}], 'vVarParameter': {'modEna': True}}},
         'startTime': {'seconds': '1700000000'}}]}}}}}


def test_package_exposes_every_profile_and_a_shared_base():
    assert len(PROFILES) == 67
    assert all(name.endswith('Profile') and cls.PROFILE for name, cls in PROFILES.items())
    assert all(issubclass(cls, OpenFMBMessage) for cls in PROFILES.values())
    assert ess_module.ESSReadingProfile.PROTO == 'essmodule.ESSReadingProfile'
    assert set(PROFILES) >= {'ESSReadingProfile', 'ESSControlProfile', 'SolarReadingProfile', 'SolarStatusProfile'}


def test_every_export_instantiates_and_round_trips_empty():
    for name in openfmb.__all__:
        obj = getattr(openfmb, name)
        if not (isinstance(obj, type) and issubclass(obj, OpenFMBMessage)):
            continue
        instance = obj()
        assert type(instance).model_validate(instance.model_dump(mode='json', by_alias=True)) == instance


def test_canonical_protobuf_json_validates_and_round_trips():
    reading = ess_module.ESSReadingProfile.model_validate(CANONICAL_READING)
    assert reading.essReading.readingMMXU.W.net.cVal.mag == 12480.0
    control = ess_module.ESSControlProfile.model_validate(CANONICAL_CONTROL)
    point = control.essControl.essControlFSCC.essControlScheduleFSCH.ValDCSG.crvPts[0]
    assert point.startTime.seconds == 1700000000                                       # int64 string coerced
    assert point.control.mode.setVal == common_module.GridConnectModeKind.GridConnectModeKind_CSI
    assert point.control.voltVarOperation.crvPts[0].voltVal == 0.95
    dumped = control.model_dump(mode='json', by_alias=True, exclude_none=True)
    assert ess_module.ESSControlProfile.model_validate(dumped) == control
    assert dumped['essControl']['essControlFSCC']['essControlScheduleFSCH']['ValDCSG']['crvPts'][0]['control']['mode'] == {
        'setVal': 'GridConnectModeKind_CSI'}


def test_wrong_shapes_are_rejected():
    with pytest.raises(ValueError):                                        # the old flattened sample shape
        ess_module.ESSReadingProfile.model_validate({'essReading': {'readingMMXU': {'W': {'net': {'mag': 1}}}}})
    with pytest.raises(ValueError):                                        # unknown field
        ess_module.ESSReadingProfile.model_validate({'essReading': {'readingMMXU': {'value': 1, 'unit': 'W'}}})
    with pytest.raises(ValueError):                                        # unknown enum name
        common_module.ENG_GridConnectModeKind.model_validate({'setVal': 'not_a_mode'})


def test_enums_accept_names_or_numbers():
    assert common_module.ENG_GridConnectModeKind.model_validate({'setVal': 'GridConnectModeKind_VSI_PQ'}).setVal is \
        common_module.GridConnectModeKind.GridConnectModeKind_VSI_PQ
    assert common_module.ENG_GridConnectModeKind.model_validate({'setVal': 6}).setVal == 6
    assert issubclass(common_module.GridConnectModeKind, enum.Enum)


def test_fields_that_shadow_class_names_keep_their_wire_name():
    from interoperability.models.openfmb import cap_bank_module
    info = cap_bank_module.CapBankEvent.model_fields['CapBankEventAndStatusYPSH_']
    assert info.alias == 'CapBankEventAndStatusYPSH'
    instance = cap_bank_module.CapBankEvent.model_validate({'CapBankEventAndStatusYPSH': {}})
    assert 'CapBankEventAndStatusYPSH' in instance.model_dump(by_alias=True, exclude_none=True)


def test_builders_produce_valid_profiles():
    reading = pb.build_ess_reading_profile(mrid='bess-1', name='B', seconds=1700000000.5, w=-25000.0, hz=60.0,
                                           phase_voltages={'phsA': 240.0})
    d = reading.model_dump(mode='json', by_alias=True, exclude_none=True)
    assert d['essReading']['readingMMXU']['W']['net']['cVal']['mag'] == -25000.0
    assert d['essReading']['readingMMXU']['PhV']['phsA']['cVal']['mag'] == 240.0
    assert d['readingMessageInfo']['messageInfo']['messageTimeStamp'] == {'seconds': 1700000000, 'nanoseconds': 500000000}
    assert d['ess'] == {'conductingEquipment': {'mRID': 'bess-1', 'namedObject': {'name': 'B'}}}
    control = pb.build_ess_control_profile(mrid='bess-1', seconds=1, schedule=[
        pb.control_point(start_seconds=10, volt_var_curve=pb.volt_var([(0.95, 0.44)], vref=1.0), power_factor=0.95,
                         power_factor_excitation=True, watt_limit_max=0.8)])
    point = control.essControl.essControlFSCC.essControlScheduleFSCH.ValDCSG.crvPts[0]
    assert point.control.voltVarOperation.vVarParameter.VRef == 1.0
    assert point.control.pFOperation.ctlVal is True and point.control.pFOperation.pFParameter.pFGnTgtMxVal == 0.95
    solar = pb.build_solar_control_profile(mrid='pv-1', schedule=[pb.control_point(start_seconds=10, watt_limit_max=0.5)])
    assert solar.solarControl.solarControlFSCC.SolarControlScheduleFSCH_.ValDCSG.crvPts[0].control.limitWOperation.wMaxSptVal == 0.5
    assert point.control.limitWOperation.wMaxSptVal == 0.8 and point.control.limitWOperation.maxLimParameter.modEna is True
    status = pb.build_ess_status_profile(mrid='bess-1', soc=63.5, grid_mode='GridConnectModeKind_VSI_PQ')
    assert status.essStatus.essStatusZBAT.Soc.mag == 63.5
    assert pb.timestamp(1.25) == {'seconds': 1, 'nanoseconds': 250000000}
    assert abs(pb.timestamp()['seconds'] - time.time()) < 5


def test_example_profiles_are_valid_and_cover_the_der_set(tmp_path):
    from interoperability.models.openfmb.generate_samples import write_example_payloads
    examples = example_profiles()
    assert set(examples) == {'SolarReadingProfile', 'SolarStatusProfile', 'SolarControlProfile', 'ESSReadingProfile',
                             'ESSStatusProfile', 'ESSControlProfile', 'ESSCapabilityProfile'}
    for name, message in examples.items():
        PROFILES[name].model_validate(message)
    written = write_example_payloads(tmp_path)
    assert json.loads(written['ESSControlProfile'].read_text())['essControl']['essControlFSCC']['essControlScheduleFSCH']['ValDCSG']['crvPts'][1]['control']['pFOperation']['pFParameter']['pFGnTgtMxVal'] == 0.95


def test_openfmb_field_universe_comes_from_the_profiles():
    universe = field_universe.models_provider('openfmb')
    assert ('essReading', 'readingMMXU', 'W', 'net', 'cVal', 'mag') in universe
    assert ('essControl', 'essControlFSCC', 'essControlScheduleFSCH', 'ValDCSG', 'crvPts', '*', 'control',
            'voltVarOperation', 'crvPts', '*', 'voltVal') in universe
    assert ('essStatus', 'essStatusZBAT', 'Soc', 'mag') in universe
    assert not any(path[-1].endswith('_') for path in universe)       # wire names, not python attribute names
