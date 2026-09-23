"""Pydantic models of the IEEE 2030.5 (Smart Energy Profile 2.0) schema.

Generated from the Eclipse VOLTTRON xsdata dataclasses of ``sep.xsd`` by
``generate_models.py`` (pinned to commit 804bed4ae5d9); see that module for how to
regenerate. ``common`` holds the base class, ``sep`` every schema type, ``enums`` the
enumerations and ``profile_builders`` keyword-only constructors for each resource.
"""
from __future__ import annotations

from .common import NAMESPACE, SepBase
from .enums import *  # noqa: F401,F403
from .enums import __all__ as _enum_names
from .sep import *  # noqa: F401,F403
from .sep import __all__ as _type_names
from .profile_builders import *  # noqa: F401,F403
from .profile_builders import __all__ as _builder_names

__all__ = [
    'NAMESPACE',
    'SepBase',
    *_enum_names,
    *_type_names,
    *_builder_names,
]
