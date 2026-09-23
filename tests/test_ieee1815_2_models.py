"""Tests for the generated IEEE 1815.2 (MESA-DER) pydantic models."""
from __future__ import annotations

from interoperability.models import ieee1815_2
from interoperability.models.ieee1815_2 import (
    AI,
    AO,
    BI,
    BO,
    CTR,
    POINTS,
    Curve,
    Inverter,
    InverterAI,
    Nameplate,
    PointDatabase,
    PointType,
    Profile,
    VoltVar,
    build_curve_ai,
    build_inverter,
    build_inverter_ai,
    build_nameplate,
    build_nameplate_ai,
    build_point_database,
    definition,
    find,
)
from interoperability.models.ieee1815_2 import profile_builders, profiles


def test_point_enums_match_the_standard_indexes():
    assert AI.DGEN_WMaxRtg == 4
    assert AI.MESA_VersNum == 0
    assert BO.DGEN_PrmConn == 3
    assert AO.DECP_VRef == 0
    assert CTR.MMTR_SupWh == 0
    assert BO.DVVR_Mod == 29 and BO(29) is BO.DVVR_Mod


def test_definitions_carry_metadata():
    d = definition('AI', 4)
    assert d.uid == 'DGEN.WMaxRtg' and d.units == 'Watts' and d.mandatory_1547 and d.purpose == 'Nameplate'
    assert find('DGEN.WMaxRtg', PointType.AI) == [d]
    assert all(len(POINTS[pt]) > 0 for pt in PointType)
    assert sum(len(v) for v in POINTS.values()) > 3000


def test_every_profile_instantiates_and_round_trips():
    for name in profiles.__all__:
        cls = getattr(profiles, name)
        if isinstance(cls, type) and issubclass(cls, (Profile, ieee1815_2.PointGroup)):
            instance = cls()
            assert cls.model_validate(instance.model_dump(mode='json')) == instance
            cls.model_json_schema()


def test_every_builder_is_callable_without_arguments():
    for name in profile_builders.__all__:
        getattr(profile_builders, name)()


def test_profile_to_points_and_back():
    nameplate = build_nameplate(AI=build_nameplate_ai(DGEN_WMaxRtg=5000, DGEN_VMaxRtg=480))
    db = nameplate.to_points()
    assert db.AI == {3: 480.0, 4: 5000.0}
    assert db.inputs() == {'AI': {3: 480.0, 4: 5000.0}, 'BI': {}, 'CTR': {}}
    again = Nameplate.from_points(db)
    assert again.AI.DGEN_WMaxRtg == 5000.0 and again.AI.DGEN_VMaxRtg == 480.0
    assert again.AI.DGEN_VMinRtg is None


def test_from_points_only_picks_up_own_points():
    vv = VoltVar.from_points({'BO': {'29': 1, '12': 1}})
    assert vv.BO.DVVR_Mod is True
    assert vv.AI is None and vv.AO is None and vv.BI is None


def test_curve_arrays_and_enumerations():
    curve = build_curve_ai(curve_type=2, number_of_points=2, x_values=[9200, 10800], y_values=[4400, -4400])
    assert curve.curve_type.name == 'VOLT_VAR'
    db = curve.to_points()
    assert db.AI[333] == 9200.0 and db.AI[335] == 10800.0 and db.AI[334] == 4400.0
    assert Curve.from_points(db).AI.x_values == [9200.0, 10800.0]
    assert curve.curve_type == 2


def test_repeated_equipment_blocks_offset_by_instance():
    inverter = build_inverter(AI=build_inverter_ai(active_power=1234))
    assert inverter.to_points(instance=1).AI == {InverterAI.index_of('active_power'): 1234.0}
    assert InverterAI.index_of('active_power', 3) == InverterAI.index_of('active_power') + 2 * InverterAI.POINTS_PER
    third = Inverter.from_points(inverter.to_points(instance=3), instance=3)
    assert third.AI.active_power == 1234.0


def test_build_point_database_layers_profiles_and_raw_tables():
    db = build_point_database(
        build_nameplate(AI=build_nameplate_ai(DGEN_WMaxRtg=5000)),
        (build_inverter(AI=build_inverter_ai(active_power=1)), 2),
        BI={'0': True},
    )
    assert isinstance(db, PointDatabase)
    dumped = db.model_dump(mode='json', exclude_defaults=True)
    assert dumped['AI']['4'] == 5000.0 and dumped['BI']['0'] is True
    assert len(db) == 3


def test_package_exports_are_unique():
    assert len(ieee1815_2.__all__) == len(set(ieee1815_2.__all__))
