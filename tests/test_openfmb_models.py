"""Tests for the OpenFMB pydantic models and profile builders."""
from __future__ import annotations

import enum

from interoperability.models import openfmb
from interoperability.models.openfmb import profile_builders
from interoperability.models.openfmb.solar_module import SolarReadingProfile


def test_every_export_resolves_and_every_model_instantiates():
    for name in openfmb.__all__:
        obj = getattr(openfmb, name)
        if isinstance(obj, type) and issubclass(obj, enum.Enum):
            continue
        instance = obj()
        assert type(instance).model_validate(instance.model_dump(mode='json')) == instance
        obj.model_json_schema()


def test_every_builder_is_callable_without_arguments():
    names = [n for n in dir(profile_builders) if n.startswith('build_')]
    assert names
    for name in names:
        getattr(profile_builders, name)()


def test_solar_reading_profile_builder():
    profile = profile_builders.build_solar_reading_profile(
        solarInverter={'name': 'inverter-1'},
        solarReading={'readingMMXU': {'value': 12.5, 'unit': 'W'}},
    )
    assert isinstance(profile, SolarReadingProfile)
    assert profile.solarReading.readingMMXU.value == 12.5
