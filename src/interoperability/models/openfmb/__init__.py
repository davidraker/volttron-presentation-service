"""OpenFMB profiles as pydantic models, generated from the OpenFMB protobuf PSM by ``generate_models.py``.

Every module package (``ess_module``, ``solar_module``, ...) holds one class per protobuf message and one
``Enum`` per enumeration. ``PROFILES`` maps every profile class name to its class.
"""
from __future__ import annotations

from ._base import OpenFMBMessage
from . import common_module
from . import breaker_module
from . import cap_bank_module
from . import circuit_segment_service_module
from . import environment_module
from . import ess_module
from . import evse_module
from . import generation_module
from . import interconnection_module
from . import load_module
from . import meter_module
from . import recloser_module
from . import regulator_module
from . import reserve_module
from . import resource_module
from . import solar_module
from . import switch_module

PROFILES: dict[str, type] = {}
__all__ = []
PROFILES.update(common_module.PROFILES)
__all__ += common_module.__all__
globals().update({name: getattr(common_module, name) for name in common_module.__all__})
PROFILES.update(breaker_module.PROFILES)
__all__ += breaker_module.__all__
globals().update({name: getattr(breaker_module, name) for name in breaker_module.__all__})
PROFILES.update(cap_bank_module.PROFILES)
__all__ += cap_bank_module.__all__
globals().update({name: getattr(cap_bank_module, name) for name in cap_bank_module.__all__})
PROFILES.update(circuit_segment_service_module.PROFILES)
__all__ += circuit_segment_service_module.__all__
globals().update({name: getattr(circuit_segment_service_module, name) for name in circuit_segment_service_module.__all__})
PROFILES.update(environment_module.PROFILES)
__all__ += environment_module.__all__
globals().update({name: getattr(environment_module, name) for name in environment_module.__all__})
PROFILES.update(ess_module.PROFILES)
__all__ += ess_module.__all__
globals().update({name: getattr(ess_module, name) for name in ess_module.__all__})
PROFILES.update(evse_module.PROFILES)
__all__ += evse_module.__all__
globals().update({name: getattr(evse_module, name) for name in evse_module.__all__})
PROFILES.update(generation_module.PROFILES)
__all__ += generation_module.__all__
globals().update({name: getattr(generation_module, name) for name in generation_module.__all__})
PROFILES.update(interconnection_module.PROFILES)
__all__ += interconnection_module.__all__
globals().update({name: getattr(interconnection_module, name) for name in interconnection_module.__all__})
PROFILES.update(load_module.PROFILES)
__all__ += load_module.__all__
globals().update({name: getattr(load_module, name) for name in load_module.__all__})
PROFILES.update(meter_module.PROFILES)
__all__ += meter_module.__all__
globals().update({name: getattr(meter_module, name) for name in meter_module.__all__})
PROFILES.update(recloser_module.PROFILES)
__all__ += recloser_module.__all__
globals().update({name: getattr(recloser_module, name) for name in recloser_module.__all__})
PROFILES.update(regulator_module.PROFILES)
__all__ += regulator_module.__all__
globals().update({name: getattr(regulator_module, name) for name in regulator_module.__all__})
PROFILES.update(reserve_module.PROFILES)
__all__ += reserve_module.__all__
globals().update({name: getattr(reserve_module, name) for name in reserve_module.__all__})
PROFILES.update(resource_module.PROFILES)
__all__ += resource_module.__all__
globals().update({name: getattr(resource_module, name) for name in resource_module.__all__})
PROFILES.update(solar_module.PROFILES)
__all__ += solar_module.__all__
globals().update({name: getattr(solar_module, name) for name in solar_module.__all__})
PROFILES.update(switch_module.PROFILES)
__all__ += switch_module.__all__
globals().update({name: getattr(switch_module, name) for name in switch_module.__all__})
__all__ = sorted(set(__all__)) + ['OpenFMBMessage', 'PROFILES']
