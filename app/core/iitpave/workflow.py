"""End-to-end structural IITPAVE mechanistic workflow.

This module is intentionally an orchestration layer. It does not change
the catalogue layer suggestion engine and it never falls back to the
stub runner when a real IITPAVE run was requested.
"""
from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from typing import Any

from app.core.mechanistic_validation import (
    LABEL_FATIGUE,
    LABEL_RUTTING,
    MechanisticValidationInput,
    MechanisticValidationSummary,
    compute_mechanistic_validation,
)
from app.core.structural_design import StructuralResult

from .input_builder import build_iitpave_input
from .output_contract import inspect_iitpave_output_contract
from .parser import parse_iitpave_output
from .pavement_structure import (
    LoadConfig,
    PavementStructure,
    default_evaluation_points,
    from_structural_layers,
)
from .results import MechanisticResult, PointResult
from .runner import SOURCE_EXTERNAL
from .runner_config import (
    IITPAVE_RUNNER_EXTERNAL,
    IITPaveRunnerConfig,
    IITPaveRunnerSelectionResult,
    select_iitpave_runner,
)


IITPAVE_WORKFLOW_STATUS_READY = "mechanistic_workflow_ready"
IITPAVE_WORKFLOW_STATUS_WARN = "mechanistic_workflow_warn"
IITPAVE_WORKFLOW_STATUS_BLOCKED = "mechanistic_workflow_blocked"


@dataclass(frozen=True, slots=True)
class IITPaveMechanisticWorkflowResult:
    status: str
    structural_result: StructuralResult
    input_text: str = ""
    output_text: str = ""
    summary: MechanisticValidationSummary | None = None
    selection: IITPaveRunnerSelectionResult | None = None
    output_contract: Any = None
    blocked_reason: str = ""
    operator_message: str = ""

    @property
    def ok(self) -> bool:
        return self.summary is not None and not self.summary.refused

    @property
    def blocked(self) -> bool:
        return self.status == IITPAVE_WORKFLOW_STATUS_BLOCKED

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "ok": self.ok,
            "blocked": self.blocked,
            "blocked_reason": self.blocked_reason,
            "operator_message": self.operator_message,
            "input_preview": self.input_text[:1000],
            "output_preview": self.output_text[:1000],
            "selection": self.selection.as_dict() if self.selection else None,
            "output_contract": (
                self.output_contract.as_dict()
                if hasattr(self.output_contract, "as_dict")
                else None
            ),
        }


def _append_note(existing: str, note: str) -> str:
    return " ".join(part for part in (existing, note) if part).strip()


def _diagnostic_structural_result(
    result: StructuralResult,
    *,
    fatigue_check: str,
    rutting_check: str,
    note: str,
) -> StructuralResult:
    return dataclasses.replace(
        result,
        fatigue_check=fatigue_check,
        rutting_check=rutting_check,
        notes=_append_note(result.notes, note),
        mechanistic_validation=None,
    )


def _blocked(
    result: StructuralResult,
    *,
    input_text: str,
    selection: IITPaveRunnerSelectionResult | None = None,
    output_contract: Any = None,
    output_text: str = "",
    reason: str,
) -> IITPaveMechanisticWorkflowResult:
    message = (
        "IITPAVE mechanistic analysis was not completed. "
        f"{reason}"
    )
    diagnostic = _diagnostic_structural_result(
        result,
        fatigue_check=f"IITPAVE unavailable - {reason}",
        rutting_check=f"IITPAVE unavailable - {reason}",
        note=message,
    )
    return IITPaveMechanisticWorkflowResult(
        status=IITPAVE_WORKFLOW_STATUS_BLOCKED,
        structural_result=diagnostic,
        input_text=input_text,
        output_text=output_text,
        selection=selection,
        output_contract=output_contract,
        blocked_reason=reason,
        operator_message=message,
    )


def _format_life(value: float | None) -> str:
    return "not available" if value is None else f"{value:.2f} MSA"


def _format_check(
    *,
    label: str,
    verdict: str | None,
    life_msa: float | None,
    design_msa: float,
    strain_label: str,
    strain: float | None,
    refused: bool,
    refused_reason: str,
    calibration_placeholder: bool,
) -> str:
    if refused:
        return f"WARN - IITPAVE ran, but {label} verdict was refused: {refused_reason}"
    if verdict == "FAIL":
        return (
            f"FAIL - life {_format_life(life_msa)} < design traffic "
            f"{design_msa:.2f} MSA; {strain_label}="
            f"{strain:.2f} microstrain."
        )
    prefix = "WARN" if calibration_placeholder else "PASS"
    suffix = (
        " Calibration constants are marked IRC37_PLACEHOLDER."
        if calibration_placeholder
        else ""
    )
    return (
        f"{prefix} - computed {verdict or 'NO VERDICT'}; life "
        f"{_format_life(life_msa)} vs design traffic {design_msa:.2f} MSA; "
        f"{strain_label}={strain:.2f} microstrain.{suffix}"
    )


def _nearest_points(
    mech_result: MechanisticResult,
    *,
    target_z: float,
) -> tuple[PointResult, ...]:
    points = mech_result.point_results
    if not points:
        return ()
    nearest_delta = min(abs(pt.z_mm - target_z) for pt in points)
    tolerance = max(1.0, nearest_delta + 0.001)
    return tuple(pt for pt in points if abs(pt.z_mm - target_z) <= tolerance)


def _point_with_design_strains(
    point: PointResult,
    *,
    epsilon_t_microstrain: float | None = None,
    epsilon_z_microstrain: float | None = None,
) -> PointResult:
    return PointResult(
        z_mm=point.z_mm,
        r_mm=point.r_mm,
        sigma_z_mpa=point.sigma_z_mpa,
        sigma_r_mpa=point.sigma_r_mpa,
        sigma_t_mpa=point.sigma_t_mpa,
        epsilon_z_microstrain=(
            abs(point.epsilon_z_microstrain)
            if epsilon_z_microstrain is None
            else abs(epsilon_z_microstrain)
        ),
        epsilon_r_microstrain=point.epsilon_r_microstrain,
        epsilon_t_microstrain=(
            max(abs(point.epsilon_t_microstrain), abs(point.epsilon_r_microstrain))
            if epsilon_t_microstrain is None
            else abs(epsilon_t_microstrain)
        ),
    )


def _critical_design_result(
    mech_result: MechanisticResult,
    structure: PavementStructure,
) -> MechanisticResult:
    """Reduce raw IITPAVE rows to the two IRC fatigue/rutting design points."""
    if not mech_result.point_results:
        return mech_result

    fatigue_candidates = _nearest_points(
        mech_result,
        target_z=structure.bituminous_thickness_mm(),
    )
    rutting_candidates = _nearest_points(
        mech_result,
        target_z=structure.total_finite_thickness_mm,
    )
    fatigue_source = max(
        fatigue_candidates or mech_result.point_results,
        key=lambda pt: max(abs(pt.epsilon_t_microstrain), abs(pt.epsilon_r_microstrain)),
    )
    rutting_source = max(
        rutting_candidates or mech_result.point_results,
        key=lambda pt: abs(pt.epsilon_z_microstrain),
    )
    fatigue_point = _point_with_design_strains(fatigue_source)
    rutting_point = _point_with_design_strains(rutting_source)
    return MechanisticResult(
        point_results=(fatigue_point, rutting_point),
        references=mech_result.references,
        is_placeholder=mech_result.is_placeholder,
        source=mech_result.source,
        notes=_append_note(
            mech_result.notes,
            "Critical fatigue/rutting strain magnitudes selected from IITPAVE rows.",
        ),
    )


def _completed(
    result: StructuralResult,
    *,
    input_text: str,
    output_text: str,
    selection: IITPaveRunnerSelectionResult,
    output_contract: Any,
    summary: MechanisticValidationSummary,
) -> IITPaveMechanisticWorkflowResult:
    fatigue_text = _format_check(
        label="fatigue",
        verdict=summary.fatigue.verdict,
        life_msa=summary.fatigue.cumulative_life_msa,
        design_msa=summary.fatigue.design_msa,
        strain_label="epsilon_t",
        strain=summary.fatigue.epsilon_t_microstrain,
        refused=summary.fatigue.refused,
        refused_reason=summary.fatigue.refused_reason,
        calibration_placeholder=summary.fatigue.calibration.is_placeholder,
    )
    rutting_text = _format_check(
        label="rutting",
        verdict=summary.rutting.verdict,
        life_msa=summary.rutting.cumulative_life_msa,
        design_msa=summary.rutting.design_msa,
        strain_label="epsilon_v",
        strain=summary.rutting.epsilon_v_microstrain,
        refused=summary.rutting.refused,
        refused_reason=summary.rutting.refused_reason,
        calibration_placeholder=summary.rutting.calibration.is_placeholder,
    )
    status = (
        IITPAVE_WORKFLOW_STATUS_BLOCKED
        if summary.refused
        else IITPAVE_WORKFLOW_STATUS_WARN
        if summary.is_placeholder
        else IITPAVE_WORKFLOW_STATUS_READY
    )
    updated = dataclasses.replace(
        result,
        fatigue_check=fatigue_text,
        rutting_check=rutting_text,
        mechanistic_validation=summary,
        notes=_append_note(
            result.notes,
            "IITPAVE mechanistic workflow executed through the local external runner.",
        ),
    )
    reason = summary.refused_reason if summary.refused else ""
    return IITPaveMechanisticWorkflowResult(
        status=status,
        structural_result=updated,
        input_text=input_text,
        output_text=output_text,
        summary=summary,
        selection=selection,
        output_contract=output_contract,
        blocked_reason=reason,
        operator_message=(
            reason
            if reason
            else "IITPAVE mechanistic workflow completed; review calibration notes before certification."
        ),
    )


def run_structural_iitpave_mechanistic_workflow(
    result: StructuralResult,
    *,
    runner_config: IITPaveRunnerConfig | None = None,
    load: LoadConfig | None = None,
) -> IITPaveMechanisticWorkflowResult:
    """Run IITPAVE and attach the IRC fatigue/rutting validation summary."""
    structure = from_structural_layers(
        result.composition,
        subgrade_mr_mpa=result.subgrade_mr_mpa,
    )
    points = default_evaluation_points(structure)
    input_text = build_iitpave_input(structure, load or LoadConfig(), points)

    cfg = runner_config or IITPaveRunnerConfig(mode=IITPAVE_RUNNER_EXTERNAL)
    selection = select_iitpave_runner(cfg)
    if not selection.ok or selection.runner is None:
        reason = selection.blocked_reason or "No usable local IITPAVE executable was found."
        return _blocked(result, input_text=input_text, selection=selection, reason=reason)

    try:
        output_text = selection.runner.run(input_text)
    except Exception as exc:
        return _blocked(
            result,
            input_text=input_text,
            selection=selection,
            reason=f"IITPAVE execution failed: {exc}",
        )

    output_contract = inspect_iitpave_output_contract(text=output_text)
    if not output_contract.parse_allowed:
        return _blocked(
            result,
            input_text=input_text,
            output_text=output_text,
            selection=selection,
            output_contract=output_contract,
            reason=output_contract.blocked_reason or "IITPAVE output format is not supported.",
        )

    try:
        mech_result = parse_iitpave_output(
            output_text,
            source=output_contract.parser_source or SOURCE_EXTERNAL,
        )
    except Exception as exc:
        return _blocked(
            result,
            input_text=input_text,
            output_text=output_text,
            selection=selection,
            output_contract=output_contract,
            reason=f"IITPAVE output parsing failed: {exc}",
        )

    mech_result = _critical_design_result(mech_result, structure)
    summary = compute_mechanistic_validation(
        MechanisticValidationInput(
            mech_result=mech_result,
            structure=structure,
            design_msa=result.design_msa,
            point_labels=(LABEL_FATIGUE, LABEL_RUTTING),
        )
    )
    return _completed(
        result,
        input_text=input_text,
        output_text=output_text,
        selection=selection,
        output_contract=output_contract,
        summary=summary,
    )
