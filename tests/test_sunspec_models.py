"""Tests for the generated SunSpec Modbus pydantic models."""
from __future__ import annotations

import pytest

from interoperability.models import sunspec
from interoperability.models.sunspec import (
    MODEL_REGISTRY,
    DERMeasureAC,
    DERMeasureACSt,
    DERVoltVar,
    SunSpecDevice,
    SunSpecModel,
    build_model_701_der_measure_ac,
    build_model_705_der_volt_var,
    build_sunspec_device,
    model_class,
)
from interoperability.models.sunspec import profile_builders


def test_registry_covers_ieee_1547_models():
    for model_id in (1, 701, 702, 703, 704, 705, 706, 707, 708, 709, 710, 711, 712, 713, 714, 715):
        assert model_id in MODEL_REGISTRY
        cls = model_class(model_id)
        assert cls.MODEL_ID == model_id
        assert cls().ID == model_id


def test_every_model_instantiates_round_trips_and_has_schema():
    for model_id, cls in MODEL_REGISTRY.items():
        instance = cls()
        dumped = instance.model_dump(mode='json')
        assert dumped['ID'] == model_id
        assert cls.model_validate(dumped) == instance
        cls.model_json_schema()


def test_every_builder_is_callable_without_arguments():
    for name in profile_builders.__all__:
        getattr(profile_builders, name)()


def test_enum_and_bitfield_points():
    m = build_model_701_der_measure_ac(W=1000, W_SF=1, St=1, Alrm=3)
    assert m.St is DERMeasureACSt.ON
    assert m.Alrm == 3 and m.Alrm.name is not None
    assert m.scaled_value('W') == 10000.0
    # Values outside the symbol list are kept as plain ints instead of failing validation.
    assert DERMeasureAC(St=99).St == 99
    assert DERMeasureAC.point_metadata('W')['sf'] == 'W_SF'
    assert DERMeasureAC.point_metadata('W')['units'] == 'W'


def test_repeating_groups_and_parent_scale_factor():
    vv = build_model_705_der_volt_var(Ena=1, V_SF=-1, DeptRef_SF=-1, Crv=[{'Pt': [{'V': 9200, 'Var': 4400}, {'V': 10800, 'Var': -4400}]}])
    assert isinstance(vv, DERVoltVar)
    assert len(vv.Crv) == 1 and len(vv.Crv[0].Pt) == 2
    assert vv.Crv[0].Pt[1].scaled_value('V', scale_factors=vv) == pytest.approx(1080.0)
    with pytest.raises(KeyError):
        vv.Crv[0].Pt[0].scaled_value('V')


def test_device_dispatches_by_model_id_and_matches_transform_format():
    device = SunSpecDevice.model_validate({'701': {'W': 5}, 705: {'Ena': 1}, '64999': {'L': 3}})
    assert isinstance(device[701], DERMeasureAC)
    assert isinstance(device['705'], DERVoltVar)
    assert type(device[64999]) is SunSpecModel and device[64999].ID == 64999
    payload = device.model_dump(mode='json', exclude_none=True)
    assert payload['701'] == {'ID': 701, 'W': 5}
    assert 705 in device and 999 not in device


def test_build_sunspec_device():
    device = build_sunspec_device(build_model_701_der_measure_ac(W=1), **{'702': {'WMaxRtg': 5000}})
    assert device.model_ids() == [701, 702]
    assert device[702].WMaxRtg == 5000


def test_package_exports_are_unique():
    assert len(sunspec.__all__) == len(set(sunspec.__all__))
