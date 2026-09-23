from __future__ import annotations

from typing import Any

from openfmb.openfmb_information_model_regen import *
from openfmb.openfmb_information_model_regen.common_module import (
    ConductingEquipmentTerminalReading,
    PhaseMMTN,
    ReadingMMDC,
    ReadingMMTR,
    ReadingMMXU,
    StatusValue,
)
from openfmb.openfmb_information_model_regen.solar_module import (
    SolarEvent,
    SolarEventProfile,
    SolarReading,
    SolarReadingProfile,
    SolarStatus,
    SolarStatusProfile,
)


def _value_or_none(value: Any) -> Any:
    return value if value is not None else None


def _build_conducting_equipment_terminal_reading(
    *,
    terminal: str | None = None,
    value: float | None = None,
    quality: str | None = None,
    mrid: dict[str, Any] | None = None,
) -> ConductingEquipmentTerminalReading | None:
    if terminal is None and value is None and quality is None and mrid is None:
        return None
    return ConductingEquipmentTerminalReading(
        terminal=terminal,
        value=value,
        quality=quality,
        mRID=mrid,
    )


def _build_phase_mmtn(*, phase: str | None = None, phase_n: str | None = None) -> PhaseMMTN | None:
    if phase is None and phase_n is None:
        return None
    return PhaseMMTN(phase=phase, n=phase_n)


def _build_reading_mmtr(*, value: float | None = None, unit: str | None = None) -> ReadingMMTR | None:
    if value is None and unit is None:
        return None
    return ReadingMMTR(value=value, unit=unit)


def _build_reading_mmxu(*, value: float | None = None, unit: str | None = None) -> ReadingMMXU | None:
    if value is None and unit is None:
        return None
    return ReadingMMXU(value=value, unit=unit)


def _build_reading_mmdc(*, value: float | None = None, unit: str | None = None) -> ReadingMMDC | None:
    if value is None and unit is None:
        return None
    return ReadingMMDC(value=value, unit=unit)


def _build_status_value(*, value: str | None = None, quality: str | None = None) -> StatusValue | None:
    if value is None and quality is None:
        return None
    return StatusValue(value=value, quality=quality)


def build_breaker_discrete_control_profile(
    *,
    breakerDiscreteControl: BreakerDiscreteControl | dict[str, Any] | None = None,
    breakerDiscreteControlProfile: Breaker | dict[str, Any] | None = None,
    breakerEventProfile: BreakerEventProfile | dict[str, Any] | None = None,
    resourceDiscreteControlProfile: ResourceDiscreteControlProfile | dict[str, Any] | None = None,
) -> BreakerDiscreteControlProfile:
    return BreakerDiscreteControlProfile(
        breakerDiscreteControl=breakerDiscreteControl,
        breakerDiscreteControlProfile=breakerDiscreteControlProfile,
        breakerEventProfile=breakerEventProfile,
        resourceDiscreteControlProfile=resourceDiscreteControlProfile,
    )


def build_breaker_event_profile(
    *,
    breakerEvent: dict[str, Any] | None = None,
    breakerEventProfile: Breaker | dict[str, Any] | None = None,
    recloserStatus: RecloserStatus | dict[str, Any] | None = None,
    resourceDiscreteControlProfile: ResourceDiscreteControlProfile | dict[str, Any] | None = None,
) -> BreakerEventProfile:
    return BreakerEventProfile(
        breakerEvent=breakerEvent,
        breakerEventProfile=breakerEventProfile,
        recloserStatus=recloserStatus,
        resourceDiscreteControlProfile=resourceDiscreteControlProfile,
    )


def build_breaker_reading_profile(
    *,
    breakerEventProfile: BreakerEventProfile | dict[str, Any] | None = None,
    breakerReadingProfile: Breaker | dict[str, Any] | None = None,
    conductingEquipmentTerminalReading_terminal: str | None = None,
    conductingEquipmentTerminalReading_value: float | None = None,
    conductingEquipmentTerminalReading_quality: str | None = None,
    conductingEquipmentTerminalReading_mrid: dict[str, Any] | None = None,
    measurementIED_value: float | None = None,
    measurementIED_unit: str | None = None,
    recloserReading: RecloserReading | dict[str, Any] | None = None,
    resourceDiscreteControlProfile: ResourceDiscreteControlProfile | dict[str, Any] | None = None,
    resourceReading: MeterReading | dict[str, Any] | None = None,
    solarReading: SolarReading | dict[str, Any] | None = None,
) -> BreakerReadingProfile:
    conductingEquipmentTerminalReading_value_obj = _build_conducting_equipment_terminal_reading(
        terminal=conductingEquipmentTerminalReading_terminal,
        value=conductingEquipmentTerminalReading_value,
        quality=conductingEquipmentTerminalReading_quality,
        mrid=conductingEquipmentTerminalReading_mrid,
    )
    measurementIED_value_obj = _build_reading_mmtr(
        value=measurementIED_value,
        unit=measurementIED_unit,
    )
    return BreakerReadingProfile(
        breakerEventProfile=breakerEventProfile,
        breakerReadingProfile=breakerReadingProfile,
        conductingEquipmentTerminalReading=conductingEquipmentTerminalReading_value_obj,
        measurementIED=measurementIED_value_obj,
        recloserReading=recloserReading,
        resourceDiscreteControlProfile=resourceDiscreteControlProfile,
        resourceReading=resourceReading,
        solarReading=solarReading,
    )


def build_breaker_status_profile(
    *,
    breakerEventProfile: BreakerEventProfile | dict[str, Any] | None = None,
    breakerStatus: dict[str, Any] | None = None,
    breakerStatusProfile: Breaker | dict[str, Any] | None = None,
    recloserStatus: RecloserStatus | dict[str, Any] | None = None,
    resourceDiscreteControlProfile: ResourceDiscreteControlProfile | dict[str, Any] | None = None,
) -> BreakerStatusProfile:
    return BreakerStatusProfile(
        breakerEventProfile=breakerEventProfile,
        breakerStatus=breakerStatus,
        breakerStatusProfile=breakerStatusProfile,
        recloserStatus=recloserStatus,
        resourceDiscreteControlProfile=resourceDiscreteControlProfile,
    )


def build_cap_bank_control_profile(
    *,
    capBankControl: CapBankControl | dict[str, Any] | None = None,
    capBankControlFSCC: CapBankControlFSCC | dict[str, Any] | None = None,
    capBankControlProfile: CapBankControl | dict[str, Any] | None = None,
    capBankReadingProfile: CapBankReadingProfile | dict[str, Any] | None = None,
    controlFSCC: dict[str, Any] | None = None,
    resourceDiscreteControlProfile: ResourceDiscreteControlProfile | dict[str, Any] | None = None,
) -> CapBankControlProfile:
    return CapBankControlProfile(
        capBankControl=capBankControl,
        capBankControlFSCC=capBankControlFSCC,
        capBankControlProfile=capBankControlProfile,
        capBankReadingProfile=capBankReadingProfile,
        controlFSCC=controlFSCC,
        resourceDiscreteControlProfile=resourceDiscreteControlProfile,
    )


def build_cap_bank_discrete_control_profile(
    *,
    capBankDiscreteControl: CapBankDiscreteControl | dict[str, Any] | None = None,
    capBankDiscreteControlProfile: CapBankSystem | dict[str, Any] | None = None,
    capBankReadingProfile: CapBankReadingProfile | dict[str, Any] | None = None,
    resourceDiscreteControlProfile: ResourceDiscreteControlProfile | dict[str, Any] | None = None,
) -> CapBankDiscreteControlProfile:
    return CapBankDiscreteControlProfile(
        capBankDiscreteControl=capBankDiscreteControl,
        capBankDiscreteControlProfile=capBankDiscreteControlProfile,
        capBankReadingProfile=capBankReadingProfile,
        resourceDiscreteControlProfile=resourceDiscreteControlProfile,
    )


def build_cap_bank_event_profile(
    *,
    capBankEvent: CapBankEvent | dict[str, Any] | None = None,
    capBankEventProfile: CapBankEvent | dict[str, Any] | None = None,
    capBankReadingProfile: CapBankReadingProfile | dict[str, Any] | None = None,
    resourceDiscreteControlProfile: ResourceDiscreteControlProfile | dict[str, Any] | None = None,
) -> CapBankEventProfile:
    return CapBankEventProfile(
        capBankEvent=capBankEvent,
        capBankEventProfile=capBankEventProfile,
        capBankReadingProfile=capBankReadingProfile,
        resourceDiscreteControlProfile=resourceDiscreteControlProfile,
    )


def build_cap_bank_reading_profile(
    *,
    capBankReading_value: float | None = None,
    capBankReading_unit: str | None = None,
    capBankReadingProfile: CapBankReadingProfile | dict[str, Any] | None = None,
    conductingEquipmentTerminalReading_terminal: str | None = None,
    conductingEquipmentTerminalReading_value: float | None = None,
    conductingEquipmentTerminalReading_quality: str | None = None,
    conductingEquipmentTerminalReading_mrid: dict[str, Any] | None = None,
    recloserReading: RecloserReading | dict[str, Any] | None = None,
    resourceDiscreteControlProfile: ResourceDiscreteControlProfile | dict[str, Any] | None = None,
    resourceReading: MeterReading | dict[str, Any] | None = None,
    solarReading: SolarReading | dict[str, Any] | None = None,
) -> CapBankReadingProfile:
    capBankReading_value_obj = _build_reading_mmtr(value=capBankReading_value, unit=capBankReading_unit)
    conductingEquipmentTerminalReading_value_obj = _build_conducting_equipment_terminal_reading(
        terminal=conductingEquipmentTerminalReading_terminal,
        value=conductingEquipmentTerminalReading_value,
        quality=conductingEquipmentTerminalReading_quality,
        mrid=conductingEquipmentTerminalReading_mrid,
    )
    return CapBankReadingProfile(
        capBankReading=capBankReading_value_obj,
        capBankReadingProfile=capBankReadingProfile,
        conductingEquipmentTerminalReading=conductingEquipmentTerminalReading_value_obj,
        recloserReading=recloserReading,
        resourceDiscreteControlProfile=resourceDiscreteControlProfile,
        resourceReading=resourceReading,
        solarReading=solarReading,
    )


def build_cap_bank_status_profile(
    *,
    capBankEvent: CapBankEvent | dict[str, Any] | None = None,
    capBankReadingProfile: CapBankReadingProfile | dict[str, Any] | None = None,
    capBankStatus: CapBankEventAndStatusYPSH | dict[str, Any] | None = None,
    capBankStatusProfile: CapBankStatus | dict[str, Any] | None = None,
    resourceDiscreteControlProfile: ResourceDiscreteControlProfile | dict[str, Any] | None = None,
) -> CapBankStatusProfile:
    return CapBankStatusProfile(
        capBankEvent=capBankEvent,
        capBankReadingProfile=capBankReadingProfile,
        capBankStatus=capBankStatus,
        capBankStatusProfile=capBankStatusProfile,
        resourceDiscreteControlProfile=resourceDiscreteControlProfile,
    )


def build_circuit_segment_control_profile(
    *,
    circuitSegmentControl: CircuitSegmentControl | dict[str, Any] | None = None,
    circuitSegmentControlProfile: CircuitSegmentControl | dict[str, Any] | None = None,
    reserveRequestProfile: ReserveRequestProfile | dict[str, Any] | None = None,
) -> CircuitSegmentControlProfile:
    return CircuitSegmentControlProfile(
        circuitSegmentControl=circuitSegmentControl,
        circuitSegmentControlProfile=circuitSegmentControlProfile,
        reserveRequestProfile=reserveRequestProfile,
    )


def build_circuit_segment_event_profile(
    *,
    circuitSegmentEvent: CircuitSegmentEvent | dict[str, Any] | None = None,
    circuitSegmentEventProfile: CircuitSegmentEvent | dict[str, Any] | None = None,
    reserveRequestProfile: ReserveRequestProfile | dict[str, Any] | None = None,
) -> CircuitSegmentEventProfile:
    return CircuitSegmentEventProfile(
        circuitSegmentEvent=circuitSegmentEvent,
        circuitSegmentEventProfile=circuitSegmentEventProfile,
        reserveRequestProfile=reserveRequestProfile,
    )


def build_circuit_segment_status_profile(
    *,
    circuitSegmentStatus: CircuitSegmentStatus | dict[str, Any] | None = None,
    circuitSegmentStatusProfile: CircuitSegmentStatus | dict[str, Any] | None = None,
    reserveRequestProfile: ReserveRequestProfile | dict[str, Any] | None = None,
) -> CircuitSegmentStatusProfile:
    return CircuitSegmentStatusProfile(
        circuitSegmentStatus=circuitSegmentStatus,
        circuitSegmentStatusProfile=circuitSegmentStatusProfile,
        reserveRequestProfile=reserveRequestProfile,
    )


def build_environment_reading_profile(**kwargs: Any) -> EnvironmentReadingProfile:
    return EnvironmentReadingProfile(**kwargs)


def build_ess_capability_override_profile(**kwargs: Any) -> ESSCapabilityOverrideProfile:
    return ESSCapabilityOverrideProfile(**kwargs)


def build_ess_capability_profile(**kwargs: Any) -> ESSCapabilityProfile:
    return ESSCapabilityProfile(**kwargs)


def build_ess_control_profile(
    *,
    controlFSCC: dict[str, Any] | None = None,
    essControl: ESSControlProfile | dict[str, Any] | None = None,
    essControlFSCC: ESSControlScheduleFSCH | dict[str, Any] | None = None,
    essControlProfile: dict[str, Any] | None = None,
    resourceDiscreteControlProfile: ResourceDiscreteControlProfile | dict[str, Any] | None = None,
) -> ESSControlProfile:
    return ESSControlProfile(
        controlFSCC=controlFSCC,
        essControl=essControl,
        essControlFSCC=essControlFSCC,
        essControlProfile=essControlProfile,
        resourceDiscreteControlProfile=resourceDiscreteControlProfile,
    )


def build_ess_discrete_control_profile(**kwargs: Any) -> ESSDiscreteControlProfile:
    return ESSDiscreteControlProfile(**kwargs)


def build_ess_event_profile(
    *,
    essControlProfile: ESSControlProfile | dict[str, Any] | None = None,
    essEvent: ESSEvent | dict[str, Any] | None = None,
    essEventProfile: ESSEvent | dict[str, Any] | None = None,
    resourceDiscreteControlProfile: ResourceDiscreteControlProfile | dict[str, Any] | None = None,
) -> ESSEventProfile:
    return ESSEventProfile(
        essControlProfile=essControlProfile,
        essEvent=essEvent,
        essEventProfile=essEventProfile,
        resourceDiscreteControlProfile=resourceDiscreteControlProfile,
    )


def build_ess_reading_profile(
    *,
    conductingEquipmentTerminalReading_terminal: str | None = None,
    conductingEquipmentTerminalReading_value: float | None = None,
    conductingEquipmentTerminalReading_quality: str | None = None,
    conductingEquipmentTerminalReading_mrid: dict[str, Any] | None = None,
    essControlProfile: ESSControlProfile | dict[str, Any] | None = None,
    essReadingProfile: dict[str, Any] | None = None,
    essReadingValue_value: float | None = None,
    essReadingValue_unit: str | None = None,
    recloserReading: RecloserReading | dict[str, Any] | None = None,
    resourceDiscreteControlProfile: ResourceDiscreteControlProfile | dict[str, Any] | None = None,
    resourceReading: MeterReading | dict[str, Any] | None = None,
    solarReading: SolarReading | dict[str, Any] | None = None,
) -> ESSReadingProfile:
    conductingEquipmentTerminalReading_value_obj = _build_conducting_equipment_terminal_reading(
        terminal=conductingEquipmentTerminalReading_terminal,
        value=conductingEquipmentTerminalReading_value,
        quality=conductingEquipmentTerminalReading_quality,
        mrid=conductingEquipmentTerminalReading_mrid,
    )
    essReadingValue_value_obj = _build_reading_mmtr(
        value=essReadingValue_value,
        unit=essReadingValue_unit,
    )
    return ESSReadingProfile(
        conductingEquipmentTerminalReading=conductingEquipmentTerminalReading_value_obj,
        essControlProfile=essControlProfile,
        essReadingProfile=essReadingProfile,
        essReadingValue=essReadingValue_value_obj,
        recloserReading=recloserReading,
        resourceDiscreteControlProfile=resourceDiscreteControlProfile,
        resourceReading=resourceReading,
        solarReading=solarReading,
    )


def build_ess_status_profile(
    *,
    essControlProfile: ESSControlProfile | dict[str, Any] | None = None,
    essStatus: ESSStatus | dict[str, Any] | None = None,
    essStatusProfile: ESSStatus | dict[str, Any] | None = None,
    resourceDiscreteControlProfile: ResourceDiscreteControlProfile | dict[str, Any] | None = None,
) -> ESSStatusProfile:
    return ESSStatusProfile(
        essControlProfile=essControlProfile,
        essStatus=essStatus,
        essStatusProfile=essStatusProfile,
        resourceDiscreteControlProfile=resourceDiscreteControlProfile,
    )


def build_evse_capability_override_profile(**kwargs: Any) -> EVSECapabilityOverrideProfile:
    return EVSECapabilityOverrideProfile(**kwargs)


def build_evse_capability_profile(**kwargs: Any) -> EVSECapabilityProfile:
    return EVSECapabilityProfile(**kwargs)


def build_evse_control_profile(**kwargs: Any) -> EVSEControlProfile:
    return EVSEControlProfile(**kwargs)


def build_evse_discrete_control_profile(**kwargs: Any) -> EVSEDiscreteControlProfile:
    return EVSEDiscreteControlProfile(**kwargs)


def build_evse_event_profile(**kwargs: Any) -> EVSEEventProfile:
    return EVSEEventProfile(**kwargs)


def build_evse_reading_profile(**kwargs: Any) -> EVSEReadingProfile:
    return EVSEReadingProfile(**kwargs)


def build_evse_status_profile(**kwargs: Any) -> EVSEStatusProfile:
    return EVSEStatusProfile(**kwargs)


def build_generation_capability_override_profile(**kwargs: Any) -> GenerationCapabilityOverrideProfile:
    return GenerationCapabilityOverrideProfile(**kwargs)


def build_generation_capability_profile(**kwargs: Any) -> GenerationCapabilityProfile:
    return GenerationCapabilityProfile(**kwargs)


def build_generation_control_profile(
    *,
    controlFSCC: dict[str, Any] | None = None,
    generationControl: GenerationControl | dict[str, Any] | None = None,
    generationControlFSCC: GenerationControlScheduleFSCH | dict[str, Any] | None = None,
    generationControlProfile: GeneratingUnit | dict[str, Any] | None = None,
    generationEventProfile: GenerationEventProfile | dict[str, Any] | None = None,
    resourceDiscreteControlProfile: ResourceDiscreteControlProfile | dict[str, Any] | None = None,
) -> GenerationControlProfile:
    return GenerationControlProfile(
        controlFSCC=controlFSCC,
        generationControl=generationControl,
        generationControlFSCC=generationControlFSCC,
        generationControlProfile=generationControlProfile,
        generationEventProfile=generationEventProfile,
        resourceDiscreteControlProfile=resourceDiscreteControlProfile,
    )


def build_generation_discrete_control_profile(
    *,
    generationDiscreteControl: GenerationDiscreteControl | dict[str, Any] | None = None,
    generationDiscreteControlProfile: GeneratingUnit | dict[str, Any] | None = None,
    generationEventProfile: GenerationEventProfile | dict[str, Any] | None = None,
    resourceDiscreteControlProfile: ResourceDiscreteControlProfile | dict[str, Any] | None = None,
) -> GenerationDiscreteControlProfile:
    return GenerationDiscreteControlProfile(
        generationDiscreteControl=generationDiscreteControl,
        generationDiscreteControlProfile=generationDiscreteControlProfile,
        generationEventProfile=generationEventProfile,
        resourceDiscreteControlProfile=resourceDiscreteControlProfile,
    )


def build_generation_event_profile(
    *,
    generationEvent: GenerationEventZGEN | dict[str, Any] | None = None,
    generationEventProfile: GenerationEventProfile | dict[str, Any] | None = None,
    resourceDiscreteControlProfile: ResourceDiscreteControlProfile | dict[str, Any] | None = None,
) -> GenerationEventProfile:
    return GenerationEventProfile(
        generationEvent=generationEvent,
        generationEventProfile=generationEventProfile,
        resourceDiscreteControlProfile=resourceDiscreteControlProfile,
    )


def build_generation_reading_profile(
    *,
    conductingEquipmentTerminalReading_terminal: str | None = None,
    conductingEquipmentTerminalReading_value: float | None = None,
    conductingEquipmentTerminalReading_quality: str | None = None,
    conductingEquipmentTerminalReading_mrid: dict[str, Any] | None = None,
    generationEventProfile: GenerationEventProfile | dict[str, Any] | None = None,
    generationReading_phase: str | None = None,
    generationReading_phase_n: str | None = None,
    generationReadingProfile: GeneratingUnit | dict[str, Any] | None = None,
    recloserReading: RecloserReading | dict[str, Any] | None = None,
    resourceDiscreteControlProfile: ResourceDiscreteControlProfile | dict[str, Any] | None = None,
    resourceReading: MeterReading | dict[str, Any] | None = None,
    solarReading: SolarReading | dict[str, Any] | None = None,
) -> GenerationReadingProfile:
    conductingEquipmentTerminalReading_value_obj = _build_conducting_equipment_terminal_reading(
        terminal=conductingEquipmentTerminalReading_terminal,
        value=conductingEquipmentTerminalReading_value,
        quality=conductingEquipmentTerminalReading_quality,
        mrid=conductingEquipmentTerminalReading_mrid,
    )
    generationReading_value_obj = _build_phase_mmtn(
        phase=generationReading_phase,
        phase_n=generationReading_phase_n,
    )
    return GenerationReadingProfile(
        conductingEquipmentTerminalReading=conductingEquipmentTerminalReading_value_obj,
        generationEventProfile=generationEventProfile,
        generationReading=generationReading_value_obj,
        generationReadingProfile=generationReadingProfile,
        recloserReading=recloserReading,
        resourceDiscreteControlProfile=resourceDiscreteControlProfile,
        resourceReading=resourceReading,
        solarReading=solarReading,
    )


def build_generation_status_profile(
    *,
    generationEventProfile: GenerationEventProfile | dict[str, Any] | None = None,
    generationStatus: GenerationStatusZGEN | dict[str, Any] | None = None,
    generationStatusProfile: GenerationStatus | dict[str, Any] | None = None,
    resourceDiscreteControlProfile: ResourceDiscreteControlProfile | dict[str, Any] | None = None,
) -> GenerationStatusProfile:
    return GenerationStatusProfile(
        generationEventProfile=generationEventProfile,
        generationStatus=generationStatus,
        generationStatusProfile=generationStatusProfile,
        resourceDiscreteControlProfile=resourceDiscreteControlProfile,
    )


def build_interconnection_planned_schedule_profile(**kwargs: Any) -> InterconnectionPlannedScheduleProfile:
    return InterconnectionPlannedScheduleProfile(**kwargs)


def build_interconnection_requested_schedule_profile(**kwargs: Any) -> InterconnectionRequestedScheduleProfile:
    return InterconnectionRequestedScheduleProfile(**kwargs)


def build_load_control_profile(
    *,
    controlFSCC: dict[str, Any] | None = None,
    loadControl: LoadControl | dict[str, Any] | None = None,
    loadControlFSCC: LoadControlFSCC | dict[str, Any] | None = None,
    loadEventProfile: LoadEventProfile | dict[str, Any] | None = None,
    resourceDiscreteControlProfile: ResourceDiscreteControlProfile | dict[str, Any] | None = None,
) -> LoadControlProfile:
    return LoadControlProfile(
        controlFSCC=controlFSCC,
        loadControl=loadControl,
        loadControlFSCC=loadControlFSCC,
        loadEventProfile=loadEventProfile,
        resourceDiscreteControlProfile=resourceDiscreteControlProfile,
    )


def build_load_event_profile(
    *,
    loadEvent: LoadEvent | dict[str, Any] | None = None,
    loadEventProfile: LoadEvent | dict[str, Any] | None = None,
    resourceDiscreteControlProfile: ResourceDiscreteControlProfile | dict[str, Any] | None = None,
) -> LoadEventProfile:
    return LoadEventProfile(
        loadEvent=loadEvent,
        loadEventProfile=loadEventProfile,
        resourceDiscreteControlProfile=resourceDiscreteControlProfile,
    )


def build_load_reading_profile(
    *,
    conductingEquipmentTerminalReading_terminal: str | None = None,
    conductingEquipmentTerminalReading_value: float | None = None,
    conductingEquipmentTerminalReading_quality: str | None = None,
    conductingEquipmentTerminalReading_mrid: dict[str, Any] | None = None,
    loadEventProfile: LoadEventProfile | dict[str, Any] | None = None,
    loadReading_phase: str | None = None,
    loadReading_phase_n: str | None = None,
    loadReadingProfile: LoadReading | dict[str, Any] | None = None,
    recloserReading: RecloserReading | dict[str, Any] | None = None,
    resourceDiscreteControlProfile: ResourceDiscreteControlProfile | dict[str, Any] | None = None,
    resourceReading: MeterReading | dict[str, Any] | None = None,
    solarReading: SolarReading | dict[str, Any] | None = None,
) -> LoadReadingProfile:
    conductingEquipmentTerminalReading_value_obj = _build_conducting_equipment_terminal_reading(
        terminal=conductingEquipmentTerminalReading_terminal,
        value=conductingEquipmentTerminalReading_value,
        quality=conductingEquipmentTerminalReading_quality,
        mrid=conductingEquipmentTerminalReading_mrid,
    )
    loadReading_value_obj = _build_phase_mmtn(
        phase=loadReading_phase,
        phase_n=loadReading_phase_n,
    )
    return LoadReadingProfile(
        conductingEquipmentTerminalReading=conductingEquipmentTerminalReading_value_obj,
        loadEventProfile=loadEventProfile,
        loadReading=loadReading_value_obj,
        loadReadingProfile=loadReadingProfile,
        recloserReading=recloserReading,
        resourceDiscreteControlProfile=resourceDiscreteControlProfile,
        resourceReading=resourceReading,
        solarReading=solarReading,
    )


def build_load_status_profile(
    *,
    loadEventProfile: LoadEventProfile | dict[str, Any] | None = None,
    loadStatus: LoadStatus | dict[str, Any] | None = None,
    loadStatusProfile: dict[str, Any] | None = None,
    resourceDiscreteControlProfile: ResourceDiscreteControlProfile | dict[str, Any] | None = None,
) -> LoadStatusProfile:
    return LoadStatusProfile(
        loadEventProfile=loadEventProfile,
        loadStatus=loadStatus,
        loadStatusProfile=loadStatusProfile,
        resourceDiscreteControlProfile=resourceDiscreteControlProfile,
    )


def build_meter_reading_profile(
    *,
    conductingEquipmentTerminalReading_terminal: str | None = None,
    conductingEquipmentTerminalReading_value: float | None = None,
    conductingEquipmentTerminalReading_quality: str | None = None,
    conductingEquipmentTerminalReading_mrid: dict[str, Any] | None = None,
    meterReadingProfile: dict[str, Any] | None = None,
    recloserReading: RecloserReading | dict[str, Any] | None = None,
    resourceDiscreteControlProfile: ResourceDiscreteControlProfile | dict[str, Any] | None = None,
    resourceReading_phase: str | None = None,
    resourceReading_phase_n: str | None = None,
    solarReading: SolarReading | dict[str, Any] | None = None,
) -> MeterReadingProfile:
    conductingEquipmentTerminalReading_value_obj = _build_conducting_equipment_terminal_reading(
        terminal=conductingEquipmentTerminalReading_terminal,
        value=conductingEquipmentTerminalReading_value,
        quality=conductingEquipmentTerminalReading_quality,
        mrid=conductingEquipmentTerminalReading_mrid,
    )
    resourceReading_value_obj = _build_phase_mmtn(
        phase=resourceReading_phase,
        phase_n=resourceReading_phase_n,
    )
    return MeterReadingProfile(
        conductingEquipmentTerminalReading=conductingEquipmentTerminalReading_value_obj,
        meterReadingProfile=meterReadingProfile,
        recloserReading=recloserReading,
        resourceDiscreteControlProfile=resourceDiscreteControlProfile,
        resourceReading=resourceReading_value_obj,
        solarReading=solarReading,
    )


def build_recloser_discrete_control_profile(
    *,
    recloserDiscreteControl: RecloserDiscreteControl | dict[str, Any] | None = None,
    recloserDiscreteControlProfile: Recloser | dict[str, Any] | None = None,
    reclosetStatusProfile: RecloserStatusProfile | dict[str, Any] | None = None,
    resourceDiscreteControlProfile: ResourceDiscreteControlProfile | dict[str, Any] | None = None,
) -> RecloserDiscreteControlProfile:
    return RecloserDiscreteControlProfile(
        recloserDiscreteControl=recloserDiscreteControl,
        recloserDiscreteControlProfile=recloserDiscreteControlProfile,
        reclosetStatusProfile=reclosetStatusProfile,
        resourceDiscreteControlProfile=resourceDiscreteControlProfile,
    )


def build_recloser_event_profile(
    *,
    recloserEvent: dict[str, Any] | None = None,
    recloserEventProfile: RecloserEvent | dict[str, Any] | None = None,
    recloserStatus: RecloserStatus | dict[str, Any] | None = None,
    reclosetStatusProfile: RecloserStatusProfile | dict[str, Any] | None = None,
    resourceDiscreteControlProfile: ResourceDiscreteControlProfile | dict[str, Any] | None = None,
) -> RecloserEventProfile:
    return RecloserEventProfile(
        recloserEvent=recloserEvent,
        recloserEventProfile=recloserEventProfile,
        recloserStatus=recloserStatus,
        reclosetStatusProfile=reclosetStatusProfile,
        resourceDiscreteControlProfile=resourceDiscreteControlProfile,
    )


def build_recloser_reading_profile(
    *,
    conductingEquipmentTerminalReading_terminal: str | None = None,
    conductingEquipmentTerminalReading_value: float | None = None,
    conductingEquipmentTerminalReading_quality: str | None = None,
    conductingEquipmentTerminalReading_mrid: dict[str, Any] | None = None,
    recloserReading: RecloserReading | dict[str, Any] | None = None,
    recloserReadingProfile: Recloser | dict[str, Any] | None = None,
    reclosetStatusProfile: RecloserStatusProfile | dict[str, Any] | None = None,
    resourceDiscreteControlProfile: ResourceDiscreteControlProfile | dict[str, Any] | None = None,
    resourceReading: MeterReading | dict[str, Any] | None = None,
    solarReading: SolarReading | dict[str, Any] | None = None,
) -> RecloserReadingProfile:
    conductingEquipmentTerminalReading_value_obj = _build_conducting_equipment_terminal_reading(
        terminal=conductingEquipmentTerminalReading_terminal,
        value=conductingEquipmentTerminalReading_value,
        quality=conductingEquipmentTerminalReading_quality,
        mrid=conductingEquipmentTerminalReading_mrid,
    )
    return RecloserReadingProfile(
        conductingEquipmentTerminalReading=conductingEquipmentTerminalReading_value_obj,
        recloserReading=recloserReading,
        recloserReadingProfile=recloserReadingProfile,
        reclosetStatusProfile=reclosetStatusProfile,
        resourceDiscreteControlProfile=resourceDiscreteControlProfile,
        resourceReading=resourceReading,
        solarReading=solarReading,
    )


def build_recloser_status_profile(
    *,
    recloserStatus: RecloserStatus | dict[str, Any] | None = None,
    recloserStatusProfile: RecloserStatus | dict[str, Any] | None = None,
    reclosetStatusProfile: RecloserStatusProfile | dict[str, Any] | None = None,
    resourceDiscreteControlProfile: ResourceDiscreteControlProfile | dict[str, Any] | None = None,
) -> RecloserStatusProfile:
    return RecloserStatusProfile(
        recloserStatus=recloserStatus,
        recloserStatusProfile=recloserStatusProfile,
        reclosetStatusProfile=reclosetStatusProfile,
        resourceDiscreteControlProfile=resourceDiscreteControlProfile,
    )


def build_regulator_control_profile(
    *,
    controlFSCC: dict[str, Any] | None = None,
    regulatorControl: RegulatorControl | dict[str, Any] | None = None,
    regulatorControlFSCC: RegulatorControlFSCC | dict[str, Any] | None = None,
    regulatorControlProfile: RegulatorSystem | dict[str, Any] | None = None,
    regulatorDiscreteControl: RegulatorDiscreteControl | dict[str, Any] | None = None,
    regulatorStatusProfile: RegulatorStatusProfile | dict[str, Any] | None = None,
    resourceDiscreteControlProfile: ResourceDiscreteControlProfile | dict[str, Any] | None = None,
) -> RegulatorControlProfile:
    return RegulatorControlProfile(
        controlFSCC=controlFSCC,
        regulatorControl=regulatorControl,
        regulatorControlFSCC=regulatorControlFSCC,
        regulatorControlProfile=regulatorControlProfile,
        regulatorDiscreteControl=regulatorDiscreteControl,
        regulatorStatusProfile=regulatorStatusProfile,
        resourceDiscreteControlProfile=resourceDiscreteControlProfile,
    )


def build_regulator_discrete_control_profile(
    *,
    regulatorDiscreteControl: RegulatorControlATCC | dict[str, Any] | None = None,
    regulatorDiscreteControlProfile: RegulatorDiscreteControl | dict[str, Any] | None = None,
    regulatorStatusProfile: RegulatorStatusProfile | dict[str, Any] | None = None,
    resourceDiscreteControlProfile: ResourceDiscreteControlProfile | dict[str, Any] | None = None,
) -> RegulatorDiscreteControlProfile:
    return RegulatorDiscreteControlProfile(
        regulatorDiscreteControl=regulatorDiscreteControl,
        regulatorDiscreteControlProfile=regulatorDiscreteControlProfile,
        regulatorStatusProfile=regulatorStatusProfile,
        resourceDiscreteControlProfile=resourceDiscreteControlProfile,
    )


def build_regulator_event_profile(
    *,
    regulatorEvent: RegulatorEvent | dict[str, Any] | None = None,
    regulatorStatusProfile: RegulatorStatusProfile | dict[str, Any] | None = None,
    resourceDiscreteControlProfile: ResourceDiscreteControlProfile | dict[str, Any] | None = None,
) -> RegulatorEventProfile:
    return RegulatorEventProfile(
        regulatorEvent=regulatorEvent,
        regulatorStatusProfile=regulatorStatusProfile,
        resourceDiscreteControlProfile=resourceDiscreteControlProfile,
    )


def build_regulator_reading_profile(
    *,
    conductingEquipmentTerminalReading_terminal: str | None = None,
    conductingEquipmentTerminalReading_value: float | None = None,
    conductingEquipmentTerminalReading_quality: str | None = None,
    conductingEquipmentTerminalReading_mrid: dict[str, Any] | None = None,
    recloserReading: RecloserReading | dict[str, Any] | None = None,
    regulatorReading_value: float | None = None,
    regulatorReading_unit: str | None = None,
    regulatorReadingProfile: RegulatorReading | dict[str, Any] | None = None,
    regulatorStatusProfile: RegulatorStatusProfile | dict[str, Any] | None = None,
    resourceDiscreteControlProfile: ResourceDiscreteControlProfile | dict[str, Any] | None = None,
    resourceReading: MeterReading | dict[str, Any] | None = None,
    solarReading: SolarReading | dict[str, Any] | None = None,
) -> RegulatorReadingProfile:
    conductingEquipmentTerminalReading_value_obj = _build_conducting_equipment_terminal_reading(
        terminal=conductingEquipmentTerminalReading_terminal,
        value=conductingEquipmentTerminalReading_value,
        quality=conductingEquipmentTerminalReading_quality,
        mrid=conductingEquipmentTerminalReading_mrid,
    )
    regulatorReading_value_obj = _build_reading_mmxu(
        value=regulatorReading_value,
        unit=regulatorReading_unit,
    )
    return RegulatorReadingProfile(
        conductingEquipmentTerminalReading=conductingEquipmentTerminalReading_value_obj,
        recloserReading=recloserReading,
        regulatorReading=regulatorReading_value_obj,
        regulatorReadingProfile=regulatorReadingProfile,
        regulatorStatusProfile=regulatorStatusProfile,
        resourceDiscreteControlProfile=resourceDiscreteControlProfile,
        resourceReading=resourceReading,
        solarReading=solarReading,
    )


def build_regulator_status_profile(
    *,
    regulatorEvent: RegulatorEvent | dict[str, Any] | None = None,
    regulatorStatus: RegulatorEventAndStatusANCR | dict[str, Any] | None = None,
    regulatorStatusProfile: RegulatorStatus | dict[str, Any] | None = None,
    resourceDiscreteControlProfile: ResourceDiscreteControlProfile | dict[str, Any] | None = None,
) -> RegulatorStatusProfile:
    return RegulatorStatusProfile(
        regulatorEvent=regulatorEvent,
        regulatorStatus=regulatorStatus,
        regulatorStatusProfile=regulatorStatusProfile,
        resourceDiscreteControlProfile=resourceDiscreteControlProfile,
    )


def build_reserve_availability_profile(
    *,
    allocatedMargin: ReserveMargin | dict[str, Any] | None = None,
    reserveAvailability: ReserveMargin | dict[str, Any] | None = None,
    reserveAvailabilityProfile: ReserveAvailability | dict[str, Any] | None = None,
    reserveRequestProfile: ReserveRequestProfile | dict[str, Any] | None = None,
    resourceDiscreteControlProfile: ResourceDiscreteControlProfile | dict[str, Any] | None = None,
) -> ReserveAvailabilityProfile:
    return ReserveAvailabilityProfile(
        allocatedMargin=allocatedMargin,
        reserveAvailability=reserveAvailability,
        reserveAvailabilityProfile=reserveAvailabilityProfile,
        reserveRequestProfile=reserveRequestProfile,
        resourceDiscreteControlProfile=resourceDiscreteControlProfile,
    )


def build_reserve_request_profile(
    *,
    allocatedMargin: AllocatedMargin | dict[str, Any] | None = None,
    reserveAvailability: ReserveMargin | dict[str, Any] | None = None,
    reserveRequestProfile: ReserveRequestProfile | dict[str, Any] | None = None,
    resourceDiscreteControlProfile: ResourceDiscreteControlProfile | dict[str, Any] | None = None,
) -> ReserveRequestProfile:
    return ReserveRequestProfile(
        allocatedMargin=allocatedMargin,
        reserveAvailability=reserveAvailability,
        reserveRequestProfile=reserveRequestProfile,
        resourceDiscreteControlProfile=resourceDiscreteControlProfile,
    )


def build_resource_discrete_control_profile(
    *,
    resourceDiscreteControl: ResourceDiscreteControl | dict[str, Any] | None = None,
    resourceDiscreteControlProfile: ResourceDiscreteControlProfile | dict[str, Any] | None = None,
) -> ResourceDiscreteControlProfile:
    return ResourceDiscreteControlProfile(
        resourceDiscreteControl=resourceDiscreteControl,
        resourceDiscreteControlProfile=resourceDiscreteControlProfile,
    )


def build_resource_event_profile(
    *,
    resourceDiscreteControlProfile: ResourceDiscreteControlProfile | dict[str, Any] | None = None,
    resourceEvent: dict[str, Any] | None = None,
    resourceEventProfile: ResourceEvent | dict[str, Any] | None = None,
    resourceStatus: ResourceStatus | dict[str, Any] | None = None,
    stringEventAndStatusGGIO: ResourceStatus | dict[str, Any] | None = None,
) -> ResourceEventProfile:
    return ResourceEventProfile(
        resourceDiscreteControlProfile=resourceDiscreteControlProfile,
        resourceEvent=resourceEvent,
        resourceEventProfile=resourceEventProfile,
        resourceStatus=resourceStatus,
        stringEventAndStatusGGIO=stringEventAndStatusGGIO,
    )


def build_resource_reading_profile(
    *,
    conductingEquipmentTerminalReading_terminal: str | None = None,
    conductingEquipmentTerminalReading_value: float | None = None,
    conductingEquipmentTerminalReading_quality: str | None = None,
    conductingEquipmentTerminalReading_mrid: dict[str, Any] | None = None,
    recloserReading: RecloserReading | dict[str, Any] | None = None,
    resourceDiscreteControlProfile: ResourceDiscreteControlProfile | dict[str, Any] | None = None,
    resourceReading: MeterReading | dict[str, Any] | None = None,
    resourceReadingProfile: ResourceReading | dict[str, Any] | None = None,
    solarReading: SolarReading | dict[str, Any] | None = None,
) -> ResourceReadingProfile:
    conductingEquipmentTerminalReading_value_obj = _build_conducting_equipment_terminal_reading(
        terminal=conductingEquipmentTerminalReading_terminal,
        value=conductingEquipmentTerminalReading_value,
        quality=conductingEquipmentTerminalReading_quality,
        mrid=conductingEquipmentTerminalReading_mrid,
    )
    return ResourceReadingProfile(
        conductingEquipmentTerminalReading=conductingEquipmentTerminalReading_value_obj,
        recloserReading=recloserReading,
        resourceDiscreteControlProfile=resourceDiscreteControlProfile,
        resourceReading=resourceReading,
        resourceReadingProfile=resourceReadingProfile,
        solarReading=solarReading,
    )


def build_resource_status_profile(
    *,
    resourceDiscreteControlProfile: ResourceDiscreteControlProfile | dict[str, Any] | None = None,
    resourceStatus: ResourceStatus | dict[str, Any] | None = None,
    resourceStatusProfile: dict[str, Any] | None = None,
    stringEventAndStatusGGIO: ResourceStatus | dict[str, Any] | None = None,
) -> ResourceStatusProfile:
    return ResourceStatusProfile(
        resourceDiscreteControlProfile=resourceDiscreteControlProfile,
        resourceStatus=resourceStatus,
        resourceStatusProfile=resourceStatusProfile,
        stringEventAndStatusGGIO=stringEventAndStatusGGIO,
    )


def build_solar_event_profile(
    *,
    eventMessageInfo: dict[str, Any] | None = None,
    solarEvent: SolarEvent | dict[str, Any] | None = None,
    solarInverter: dict[str, Any] | None = None,
) -> SolarEventProfile:
    return SolarEventProfile(
        eventMessageInfo=eventMessageInfo,
        solarEvent=solarEvent,
        solarInverter=solarInverter,
    )


def build_solar_reading_profile(
    *,
    readingMessageInfo: dict[str, Any] | None = None,
    solarInverter: dict[str, Any] | None = None,
    solarReading_conductingEquipmentTerminalReading_terminal: str | None = None,
    solarReading_conductingEquipmentTerminalReading_value: float | None = None,
    solarReading_conductingEquipmentTerminalReading_quality: str | None = None,
    solarReading_conductingEquipmentTerminalReading_mrid: dict[str, Any] | None = None,
    solarReading_phaseMMTN_phase: str | None = None,
    solarReading_phaseMMTN_phase_n: str | None = None,
    solarReading_readingMMTR_value: float | None = None,
    solarReading_readingMMTR_unit: str | None = None,
    solarReading_readingMMXU_value: float | None = None,
    solarReading_readingMMXU_unit: str | None = None,
    solarReading_readingMMDC_value: float | None = None,
    solarReading_readingMMDC_unit: str | None = None,
    solarReading: SolarReading | None = None,
) -> SolarReadingProfile:
    solarReading_value_obj = solarReading
    if solarReading_value_obj is None:
        solarReading_value_obj = SolarReading(
            conductingEquipmentTerminalReading=_build_conducting_equipment_terminal_reading(
                terminal=solarReading_conductingEquipmentTerminalReading_terminal,
                value=solarReading_conductingEquipmentTerminalReading_value,
                quality=solarReading_conductingEquipmentTerminalReading_quality,
                mrid=solarReading_conductingEquipmentTerminalReading_mrid,
            ),
            phaseMMTN=_build_phase_mmtn(
                phase=solarReading_phaseMMTN_phase,
                phase_n=solarReading_phaseMMTN_phase_n,
            ),
            readingMMTR=_build_reading_mmtr(
                value=solarReading_readingMMTR_value,
                unit=solarReading_readingMMTR_unit,
            ),
            readingMMXU=_build_reading_mmxu(
                value=solarReading_readingMMXU_value,
                unit=solarReading_readingMMXU_unit,
            ),
            readingMMDC=_build_reading_mmdc(
                value=solarReading_readingMMDC_value,
                unit=solarReading_readingMMDC_unit,
            ),
        )
    return SolarReadingProfile(
        readingMessageInfo=readingMessageInfo,
        solarInverter=solarInverter,
        solarReading=solarReading_value_obj,
    )


def build_solar_status_profile(
    *,
    statusMessageInfo: dict[str, Any] | None = None,
    solarInverter: dict[str, Any] | None = None,
    solarStatus_statusValue_value: str | None = None,
    solarStatus_statusValue_quality: str | None = None,
    solarStatus_solarStatusZGEN: dict[str, Any] | None = None,
    solarStatus: SolarStatus | None = None,
) -> SolarStatusProfile:
    solarStatus_value_obj = solarStatus
    if solarStatus_value_obj is None:
        solarStatus_value_obj = SolarStatus(
            statusValue=_build_status_value(
                value=solarStatus_statusValue_value,
                quality=solarStatus_statusValue_quality,
            ),
            solarStatusZGEN=solarStatus_solarStatusZGEN,
        )
    return SolarStatusProfile(
        statusMessageInfo=statusMessageInfo,
        solarInverter=solarInverter,
        solarStatus=solarStatus_value_obj,
    )


def build_switch_discrete_control_profile(
    *,
    resourceDiscreteControlProfile: ResourceDiscreteControlProfile | dict[str, Any] | None = None,
    switchDiscreteControl: SwitchDiscreteControl | dict[str, Any] | None = None,
    switchDiscreteControlProfile: ProtectedSwitch | dict[str, Any] | None = None,
    switchStatusProfile: SwitchStatusProfile | dict[str, Any] | None = None,
) -> SwitchDiscreteControlProfile:
    return SwitchDiscreteControlProfile(
        resourceDiscreteControlProfile=resourceDiscreteControlProfile,
        switchDiscreteControl=switchDiscreteControl,
        switchDiscreteControlProfile=switchDiscreteControlProfile,
        switchStatusProfile=switchStatusProfile,
    )


def build_switch_event_profile(
    *,
    resourceDiscreteControlProfile: ResourceDiscreteControlProfile | dict[str, Any] | None = None,
    switchEvent: SwitchEvent | dict[str, Any] | None = None,
    switchEventProfile: SwitchEvent | dict[str, Any] | None = None,
    switchStatusProfile: SwitchStatusProfile | dict[str, Any] | None = None,
) -> SwitchEventProfile:
    return SwitchEventProfile(
        resourceDiscreteControlProfile=resourceDiscreteControlProfile,
        switchEvent=switchEvent,
        switchEventProfile=switchEventProfile,
        switchStatusProfile=switchStatusProfile,
    )


def build_switch_reading_profile(
    *,
    conductingEquipmentTerminalReading_terminal: str | None = None,
    conductingEquipmentTerminalReading_value: float | None = None,
    conductingEquipmentTerminalReading_quality: str | None = None,
    conductingEquipmentTerminalReading_mrid: dict[str, Any] | None = None,
    recloserReading: RecloserReading | dict[str, Any] | None = None,
    resourceDiscreteControlProfile: ResourceDiscreteControlProfile | dict[str, Any] | None = None,
    resourceReading: MeterReading | dict[str, Any] | None = None,
    solarReading: SolarReading | dict[str, Any] | None = None,
    switchReading_value: float | None = None,
    switchReading_unit: str | None = None,
    switchReadingProfile: ProtectedSwitch | dict[str, Any] | None = None,
    switchStatusProfile: SwitchStatusProfile | dict[str, Any] | None = None,
) -> SwitchReadingProfile:
    conductingEquipmentTerminalReading_value_obj = _build_conducting_equipment_terminal_reading(
        terminal=conductingEquipmentTerminalReading_terminal,
        value=conductingEquipmentTerminalReading_value,
        quality=conductingEquipmentTerminalReading_quality,
        mrid=conductingEquipmentTerminalReading_mrid,
    )
    switchReading_value_obj = _build_reading_mmtr(
        value=switchReading_value,
        unit=switchReading_unit,
    )
    return SwitchReadingProfile(
        conductingEquipmentTerminalReading=conductingEquipmentTerminalReading_value_obj,
        recloserReading=recloserReading,
        resourceDiscreteControlProfile=resourceDiscreteControlProfile,
        resourceReading=resourceReading,
        solarReading=solarReading,
        switchReading=switchReading_value_obj,
        switchReadingProfile=switchReadingProfile,
        switchStatusProfile=switchStatusProfile,
    )


def build_switch_status_profile(
    *,
    resourceDiscreteControlProfile: ResourceDiscreteControlProfile | dict[str, Any] | None = None,
    switchStatus: SwitchStatus | dict[str, Any] | None = None,
    switchStatusProfile: ProtectedSwitch | dict[str, Any] | None = None,
) -> SwitchStatusProfile:
    return SwitchStatusProfile(
        resourceDiscreteControlProfile=resourceDiscreteControlProfile,
        switchStatus=switchStatus,
        switchStatusProfile=switchStatusProfile,
    )


__all__ = [
    'build_breaker_discrete_control_profile',
    'build_breaker_event_profile',
    'build_breaker_reading_profile',
    'build_breaker_status_profile',
    'build_cap_bank_control_profile',
    'build_cap_bank_discrete_control_profile',
    'build_cap_bank_event_profile',
    'build_cap_bank_reading_profile',
    'build_cap_bank_status_profile',
    'build_circuit_segment_control_profile',
    'build_circuit_segment_event_profile',
    'build_circuit_segment_status_profile',
    'build_environment_reading_profile',
    'build_ess_capability_override_profile',
    'build_ess_capability_profile',
    'build_ess_control_profile',
    'build_ess_discrete_control_profile',
    'build_ess_event_profile',
    'build_ess_reading_profile',
    'build_ess_status_profile',
    'build_evse_capability_override_profile',
    'build_evse_capability_profile',
    'build_evse_control_profile',
    'build_evse_discrete_control_profile',
    'build_evse_event_profile',
    'build_evse_reading_profile',
    'build_evse_status_profile',
    'build_generation_capability_override_profile',
    'build_generation_capability_profile',
    'build_generation_control_profile',
    'build_generation_discrete_control_profile',
    'build_generation_event_profile',
    'build_generation_reading_profile',
    'build_generation_status_profile',
    'build_interconnection_planned_schedule_profile',
    'build_interconnection_requested_schedule_profile',
    'build_load_control_profile',
    'build_load_event_profile',
    'build_load_reading_profile',
    'build_load_status_profile',
    'build_meter_reading_profile',
    'build_recloser_discrete_control_profile',
    'build_recloser_event_profile',
    'build_recloser_reading_profile',
    'build_recloser_status_profile',
    'build_regulator_control_profile',
    'build_regulator_discrete_control_profile',
    'build_regulator_event_profile',
    'build_regulator_reading_profile',
    'build_regulator_status_profile',
    'build_reserve_availability_profile',
    'build_reserve_request_profile',
    'build_resource_discrete_control_profile',
    'build_resource_event_profile',
    'build_resource_reading_profile',
    'build_resource_status_profile',
    'build_solar_event_profile',
    'build_solar_reading_profile',
    'build_solar_status_profile',
    'build_switch_discrete_control_profile',
    'build_switch_event_profile',
    'build_switch_reading_profile',
    'build_switch_status_profile',
]
