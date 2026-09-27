"""Hand-written constructors for the OpenFMB profiles the DER framework exchanges.

The generated classes mirror the protobuf structure exactly, which makes a full profile verbose
to assemble by hand (a single power reading is ``readingMMXU.W.net.cVal.mag``). These helpers
build valid profiles from plain keyword arguments. Anything they do not cover can be built with
:func:`build_profile` from a dict in protobuf JSON form.
"""
from __future__ import annotations

import time
from typing import Any

from . import PROFILES
from ._base import OpenFMBMessage

PHASES = ('phsA', 'phsB', 'phsC')


def build_profile(profile: str | type[OpenFMBMessage], data: dict[str, Any]) -> OpenFMBMessage:
    """Validate ``data`` (protobuf JSON form) as the named profile, e.g. ``build_profile('ESSReadingProfile', {...})``."""
    cls = PROFILES[profile] if isinstance(profile, str) else profile
    return cls.model_validate(data)


def timestamp(seconds: int | float | None = None) -> dict[str, Any]:
    """An OpenFMB ``Timestamp``; now when ``seconds`` is omitted."""
    seconds = time.time() if seconds is None else seconds
    whole = int(seconds)
    return {'seconds': whole, 'nanoseconds': int(round((seconds - whole) * 1e9))}


def message_info(mrid: str, seconds: int | float | None = None, name: str | None = None) -> dict[str, Any]:
    """The ``messageInfo`` block every profile header carries."""
    identified = {'mRID': mrid}
    if name is not None:
        identified['name'] = name
    return {'messageInfo': {'identifiedObject': identified, 'messageTimeStamp': timestamp(seconds)}}


def equipment(mrid: str, name: str | None = None) -> dict[str, Any]:
    """A ``conductingEquipment`` block identifying the device."""
    block: dict[str, Any] = {'mRID': mrid}
    if name is not None:
        block['namedObject'] = {'name': name}
    return {'conductingEquipment': block}


def mv(mag: float | None) -> dict[str, Any] | None:
    """A measured value (``MV``)."""
    return None if mag is None else {'mag': mag}


def cmv(mag: float | None) -> dict[str, Any] | None:
    """A complex measured value (``CMV``) with magnitude only."""
    return None if mag is None else {'cVal': {'mag': mag}}


def wye(net: float | None = None, phases: dict[str, float] | None = None) -> dict[str, Any] | None:
    """A ``WYE`` set of per-phase complex values: ``net`` and any of ``phsA``, ``phsB``, ``phsC``."""
    block = {k: cmv(v) for k, v in {'net': net, **(phases or {})}.items() if v is not None}
    return block or None


def _drop_none(mapping: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in mapping.items() if v is not None}


def reading_mmxu(*, w: float | None = None, var: float | None = None, va: float | None = None, hz: float | None = None,
                 pf: float | None = None, phase_voltages: dict[str, float] | None = None,
                 phase_currents: dict[str, float] | None = None) -> dict[str, Any]:
    """A ``ReadingMMXU`` block from totals and per-phase values (``{'phsA': 240.1, ...}``)."""
    return _drop_none({'W': wye(w), 'VAr': wye(var), 'VA': wye(va), 'PF': wye(pf), 'Hz': mv(hz),
                       'PhV': wye(phases=phase_voltages), 'A': wye(phases=phase_currents)})


def build_ess_reading_profile(*, mrid: str, name: str | None = None, seconds: int | float | None = None,
                              **readings: Any) -> OpenFMBMessage:
    """``ESSReadingProfile`` with the readings accepted by :func:`reading_mmxu`."""
    return build_profile('ESSReadingProfile', {
        'readingMessageInfo': message_info(mrid, seconds), 'ess': equipment(mrid, name),
        'essReading': {'readingMMXU': reading_mmxu(**readings)}})


def build_solar_reading_profile(*, mrid: str, name: str | None = None, seconds: int | float | None = None,
                                **readings: Any) -> OpenFMBMessage:
    """``SolarReadingProfile`` with the readings accepted by :func:`reading_mmxu`."""
    return build_profile('SolarReadingProfile', {
        'readingMessageInfo': message_info(mrid, seconds), 'solarInverter': equipment(mrid, name),
        'solarReading': {'readingMMXU': reading_mmxu(**readings)}})


def build_ess_status_profile(*, mrid: str, name: str | None = None, seconds: int | float | None = None,
                             soc: float | None = None, soh: float | None = None, wh_available: float | None = None,
                             grid_mode: str | None = None, standby: bool | None = None,
                             battery_ok: bool | None = None, alarm: str | None = None) -> OpenFMBMessage:
    """``ESSStatusProfile``: battery state (``essStatusZBAT``) and generator state (``essStatusZGEN``).

    ``grid_mode`` is a ``GridConnectModeKind`` name and ``alarm`` an ``AlrmKind`` name. Unlike the solar
    profile, the ESS generator status has no operating state; the battery status carries ``BatSt``.
    """
    zbat = _drop_none({'Soc': mv(soc), 'SoH': mv(soh), 'WHAvail': mv(wh_available),
                       'GriMod': None if grid_mode is None else {'setVal': grid_mode},
                       'Stdby': None if standby is None else {'stVal': standby},
                       'BatSt': None if battery_ok is None else {'stVal': battery_ok}})
    zgen_status = _drop_none({'Alrm': None if alarm is None else {'value': alarm}})
    status = _drop_none({'essStatusZBAT': zbat or None,
                         'essStatusZGEN': {'eSSEventAndStatusZGEN': zgen_status} if zgen_status else None})
    return build_profile('ESSStatusProfile', {
        'statusMessageInfo': message_info(mrid, seconds), 'ess': equipment(mrid, name), 'essStatus': status})


def build_solar_status_profile(*, mrid: str, name: str | None = None, seconds: int | float | None = None,
                               operating_state: str | None = None, grid_connection_state: str | None = None,
                               alarm: str | None = None) -> OpenFMBMessage:
    """``SolarStatusProfile`` from ``OperatingStateKind``, ``GridConnectionStateKind`` and ``AlrmKind`` names."""
    zgen = _drop_none({'OperatingState': None if operating_state is None else {'value': operating_state},
                       'GridConnectionState': None if grid_connection_state is None else {'value': grid_connection_state},
                       'Alrm': None if alarm is None else {'value': alarm}})
    return build_profile('SolarStatusProfile', {
        'statusMessageInfo': message_info(mrid, seconds), 'solarInverter': equipment(mrid, name),
        'solarStatus': {'solarStatusZGEN': {'solarEventAndStatusZGEN': zgen}}})


def volt_var(points: list[tuple[float, float]], *, enabled: bool = True, vref: float | None = None,
             vref_auto: bool | None = None, open_loop_seconds: float | None = None) -> dict[str, Any]:
    """A ``VoltVarCSG`` block from (voltage, var) pairs."""
    params = _drop_none({'modEna': enabled, 'VRef': vref, 'VRefAdjEna': vref_auto,
                         'OplTmmsMax': None if open_loop_seconds is None else {'seconds': open_loop_seconds}})
    return {'crvPts': [{'voltVal': v, 'varVal': q} for v, q in points], 'vVarParameter': params}


def volt_watt(points: list[tuple[float, float]], *, enabled: bool = True) -> dict[str, Any]:
    """A ``VoltWCSG`` block from (voltage, watt) pairs."""
    return {'crvPts': [{'voltVal': v, 'wVal': w} for v, w in points], 'voltWParameter': {'modEna': enabled}}


def freq_watt(*, over_deadband_hz: float, over_slope: float, under_deadband_hz: float, under_slope: float,
              enabled: bool = True) -> dict[str, Any]:
    """An ``HzWAPC`` block (frequency-watt droop) for both directions."""
    return {'overHzWPt': {'deadbandHzVal': over_deadband_hz, 'slopeVal': over_slope},
            'overHzWParameter': {'modEna': enabled},
            'underHzWPt': {'deadbandHzVal': under_deadband_hz, 'slopeVal': under_slope},
            'underHzWParameter': {'modEna': enabled}}


def control_point(*, start_seconds: int | float, mode: str | None = None, volt_var_curve: dict | None = None,
                  volt_watt_curve: dict | None = None, freq_watt_droop: dict | None = None,
                  power_factor: float | None = None, power_factor_excitation: bool | None = None,
                  watt_limit_max: float | None = None, watt_limit_min: float | None = None) -> dict[str, Any]:
    """One entry of an ESS or solar control schedule. ``mode`` is a ``GridConnectModeKind`` name."""
    control = _drop_none({
        'mode': None if mode is None else {'setVal': mode},
        'voltVarOperation': volt_var_curve, 'voltWOperation': volt_watt_curve, 'hzWOperation': freq_watt_droop,
        # PFSPC.ctlVal enables the mode; the target itself is OperationDFPF.pFGnTgtMxVal.
        'pFOperation': None if power_factor is None else {
            'ctlVal': True,
            'pFParameter': _drop_none({'modEna': True, 'pFGnTgtMxVal': power_factor, 'pFExtSet': power_factor_excitation})},
        'limitWOperation': None if watt_limit_max is None and watt_limit_min is None else _drop_none({
            'wMaxSptVal': watt_limit_max, 'wMinSptVal': watt_limit_min,
            'maxLimParameter': None if watt_limit_max is None else {'modEna': True},
            'minLimParameter': None if watt_limit_min is None else {'modEna': True}})})
    return {'startTime': timestamp(start_seconds), 'control': control}


def build_ess_control_profile(*, mrid: str, name: str | None = None, seconds: int | float | None = None,
                              schedule: list[dict[str, Any]]) -> OpenFMBMessage:
    """``ESSControlProfile`` whose schedule is a list of :func:`control_point` entries."""
    return build_profile('ESSControlProfile', {
        'controlMessageInfo': message_info(mrid, seconds), 'ess': equipment(mrid, name),
        'essControl': {'essControlFSCC': {'essControlScheduleFSCH': {'ValDCSG': {'crvPts': schedule}}}}})


def build_solar_control_profile(*, mrid: str, name: str | None = None, seconds: int | float | None = None,
                                schedule: list[dict[str, Any]]) -> OpenFMBMessage:
    """``SolarControlProfile`` whose schedule is a list of :func:`control_point` entries."""
    return build_profile('SolarControlProfile', {
        'controlMessageInfo': message_info(mrid, seconds), 'solarInverter': equipment(mrid, name),
        # The solar schedule field is capitalised on the wire (``SolarControlScheduleFSCH``), unlike the ESS one.
        'solarControl': {'solarControlFSCC': {'SolarControlScheduleFSCH': {'ValDCSG': {'crvPts': schedule}}}}})


def build_ess_capability_profile(*, mrid: str, name: str | None = None, seconds: int | float | None = None,
                                 vendor: str | None = None, model: str | None = None,
                                 w_max: float | None = None, va_max: float | None = None, v_nom: float | None = None,
                                 wh_rating: float | None = None, w_charge_max: float | None = None,
                                 w_discharge_max: float | None = None) -> OpenFMBMessage:
    """``ESSCapabilityProfile`` with the nameplate ratings the 1547 mappings use."""
    source = {k: {'setMag': v} for k, v in {'WMaxRtg': w_max, 'VAMaxRtg': va_max, 'VNomRtg': v_nom}.items() if v is not None}
    ratings = _drop_none({'sourceCapabilityRatings': source or None,
                          'WHRtg': None if wh_rating is None else {'setMag': wh_rating},
                          'WChaRteMaxRtg': None if w_charge_max is None else {'setMag': w_charge_max},
                          'WDisChaRteMaxRtg': None if w_discharge_max is None else {'setMag': w_discharge_max}})
    capability = _drop_none({'nameplateValue': _drop_none({'vendor': vendor, 'model': model}) or None,
                             'essCapabilityRatings': ratings or None})
    return build_profile('ESSCapabilityProfile', {
        'capabilityMessageInfo': message_info(mrid, seconds), 'ess': equipment(mrid, name), 'essCapability': capability})


__all__ = ['build_profile', 'timestamp', 'message_info', 'equipment', 'mv', 'cmv', 'wye', 'reading_mmxu',
           'build_ess_reading_profile', 'build_solar_reading_profile', 'build_ess_status_profile',
           'build_solar_status_profile', 'volt_var', 'volt_watt', 'freq_watt', 'control_point',
           'build_ess_control_profile', 'build_solar_control_profile', 'build_ess_capability_profile']
