"""Pydantic models of the SunSpec Modbus information model.

The classes are generated from the SunSpec Alliance model definitions by
``generate_models.py``; see that module for how to regenerate them. ``common`` holds the
shared base classes and the ``SunSpecDevice`` container, ``models`` the per-model classes
and ``profile_builders`` keyword-only constructors for each model and group.
"""
from __future__ import annotations

from .common import (
    MODEL_REGISTRY,
    SunSpecDevice,
    SunSpecEnum,
    SunSpecFlags,
    SunSpecGroup,
    SunSpecModel,
    model_class,
    register_model,
)
from .models import *  # noqa: F401,F403
from .models import __all__ as _model_names
from .profile_builders import *  # noqa: F401,F403
from .profile_builders import __all__ as _builder_names

__all__ = [
    'MODEL_REGISTRY',
    'SunSpecDevice',
    'SunSpecEnum',
    'SunSpecFlags',
    'SunSpecGroup',
    'SunSpecModel',
    'model_class',
    'register_model',
    *_model_names,
    *_builder_names,
]
