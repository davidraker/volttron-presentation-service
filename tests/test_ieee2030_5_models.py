"""Tests for the generated IEEE 2030.5 pydantic models."""
from __future__ import annotations

from interoperability.models import ieee2030_5
from interoperability.models.ieee2030_5 import (
    ConsumptionTariffInterval,
    DERCapability,
    DERControl,
    DERControlList,
    List_type,
    RtgNormalCategoryType,
    SepBase,
    SubscribableList,
    build_der_capability,
    build_der_control,
    build_der_control_base,
    build_der_settings,
)
from interoperability.models.ieee2030_5 import profile_builders, sep


def test_every_type_instantiates_round_trips_and_has_schema():
    for name in sep.__all__:
        cls = getattr(sep, name)
        assert issubclass(cls, SepBase)
        instance = cls()
        assert cls.model_validate(instance.model_dump(mode='json')) == instance
        cls.model_json_schema()


def test_every_builder_is_callable_without_arguments():
    for name in profile_builders.__all__:
        getattr(profile_builders, name)()
    assert 'build_der_capability_link' not in profile_builders.__all__
    assert 'build_der_control_list' not in profile_builders.__all__


def test_der_capability_fields_and_required_metadata():
    cap = build_der_capability(rtgMaxW={'multiplier': 3, 'value': 5}, modesSupported='0F', type=83)
    assert cap.rtgMaxW.value == 5
    assert cap.missing_required() == []
    assert DERCapability().missing_required() == ['modesSupported', 'rtgMaxW', 'type']
    assert DERCapability.field_metadata('modesSupported')['format'] == 'base16'
    assert DERCapability.field_metadata('href')['xml'] == 'attribute'


def test_inheritance_and_lists():
    ctl = build_der_control(mRID='ABCD', DERControlBase=build_der_control_base(opModFixedW=50, opModVoltVar={'href': '/crv/1'}))
    assert isinstance(ctl, DERControl) and ctl.DERControlBase.opModVoltVar.href == '/crv/1'
    lst = DERControlList.model_validate({'all': 1, 'results': 1, 'DERControl': [ctl.model_dump(exclude_none=True)]})
    assert issubclass(DERControlList, SubscribableList) and issubclass(SubscribableList, SepBase)
    assert lst.DERControl[0].mRID == 'ABCD'
    assert List_type.xml_name() == 'List' and DERControlList.xml_name() == 'DERControlList'


def test_field_shadowing_a_type_name_still_validates():
    cti = ConsumptionTariffInterval.model_validate({'EnvironmentalCost': [{'amount': 1}], 'price': 3})
    assert cti.EnvironmentalCost[0].amount == 1
    assert ConsumptionTariffInterval.model_fields['price'].description.startswith('The charge')


def test_enums_and_settings():
    assert RtgNormalCategoryType.category_a == 1
    settings = build_der_settings(setMaxW={'multiplier': 0, 'value': 5000})
    assert settings.setMaxW.value == 5000


def test_package_exports_are_unique():
    assert len(ieee2030_5.__all__) == len(set(ieee2030_5.__all__))
