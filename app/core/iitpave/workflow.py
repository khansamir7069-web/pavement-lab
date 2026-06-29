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
from app.core.stabilized_design import StabilizedResult

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
from .installation_manager import load_persisted_config


def compile_iitpave_metadata(selection, input_text: str, output_text: str, duration: float) -> dict[str, Any]:
    import hashlib
    import os
    from datetime import datetime, timezone
    from app.core.iitpave.installation_manager import detect_iitpave_version
    
    inp_sha = hashlib.sha256(input_text.encode("utf-8")).hexdigest() if input_text else ""
    out_sha = hashlib.sha256(output_text.encode("utf-8")).hexdigest() if output_text else ""
    
    metadata = {
        "execution_timestamp": datetime.now(timezone.utc).isoformat(),
        "execution_duration_sec": duration,
        "input_sha256": inp_sha,
        "output_sha256": out_sha,
        "real_iitpave_executed": False,
        "exe_path": "",
        "exe_sha256": "",
        "exe_version": "Unavailable"
    }
    
    if selection and selection.runner and hasattr(selection.runner, "exe_path"):
        exe_path = selection.runner.exe_path
        metadata["exe_path"] = str(exe_path)
        if exe_path and os.path.isfile(exe_path):
            metadata["real_iitpave_executed"] = (selection.runner.source == SOURCE_EXTERNAL)
            try:
                with open(exe_path, "rb") as f:
                    metadata["exe_sha256"] = hashlib.sha256(f.read()).hexdigest()
            except Exception:
                pass
            try:
                metadata["exe_version"] = detect_iitpave_version(str(exe_path)) or "Unknown"
            except Exception:
                metadata["exe_version"] = "Detected"
                
    return metadata


IITPAVE_WORKFLOW_STATUS_READY = "mechanistic_workflow_ready"
IITPAVE_WORKFLOW_STATUS_WARN = "mechanistic_workflow_warn"
IITPAVE_WORKFLOW_STATUS_BLOCKED = "mechanistic_workflow_blocked"


@dataclass(frozen=True, slots=True)
class IITPaveMechanisticWorkflowResult:
    status: str
    structural_result: Any
    input_text: str = ""
    output_text: str = ""
    summary: MechanisticValidationSummary | None = None
    selection: IITPaveRunnerSelectionResult | None = None
    output_contract: Any = None
    blocked_reason: str = ""
    operator_message: str = ""
    iteration_history: tuple[dict[str, Any], ...] = ()

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
            "iteration_history": list(self.iteration_history),
        }


def _append_note(existing: str, note: str) -> str:
    return " ".join(part for part in (existing, note) if part).strip()


def _diagnostic_structural_result(
    result: Any,
    *,
    fatigue_check: str,
    rutting_check: str,
    note: str,
    summary: Any = None,
) -> Any:
    if isinstance(result, StabilizedResult):
        existing_warnings = list(result.warnings)
        msg = f"IITPAVE integration alert: {note}"
        if msg not in existing_warnings:
            existing_warnings.append(msg)
        return dataclasses.replace(
            result,
            validation_mode="Decision Support Mode",
            warnings=tuple(existing_warnings),
            mechanistic_validation=summary,
        )
    return dataclasses.replace(
        result,
        fatigue_check=fatigue_check,
        rutting_check=rutting_check,
        notes=_append_note(result.notes, note),
        mechanistic_validation=summary,
    )


def _blocked(
    result: Any,
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
    
    import hashlib
    from datetime import datetime, timezone
    from app.core.mechanistic_validation.engine import refused_fatigue_check, refused_rutting_check, MechanisticValidationSummary
    from app.core.mechanistic_validation.engine import get_fatigue_calibration, get_rutting_calibration
    
    design_msa = getattr(result, "design_msa", 0.0) or 0.0
    fcal = get_fatigue_calibration()
    rcal = get_rutting_calibration()
    
    fatigue = refused_fatigue_check(
        design_msa=design_msa,
        epsilon_t_microstrain=None,
        e_bc_mpa=None,
        c_factor=0.0,
        calibration=fcal,
        refused_reason=reason,
    )
    rutting = refused_rutting_check(
        design_msa=design_msa,
        epsilon_v_microstrain=None,
        calibration=rcal,
        refused_reason=reason,
    )
    
    inp_sha = hashlib.sha256(input_text.encode("utf-8")).hexdigest() if input_text else ""
    out_sha = hashlib.sha256(output_text.encode("utf-8")).hexdigest() if output_text else ""
    
    metadata = {
        "execution_timestamp": datetime.now(timezone.utc).isoformat(),
        "execution_duration_sec": 0.0,
        "input_sha256": inp_sha,
        "output_sha256": out_sha,
        "real_iitpave_executed": False,
        "exe_path": "",
        "exe_sha256": "",
        "exe_version": "Unavailable",
        "notes": "Real IITPAVE verification was not performed."
    }
    
    import os
    if selection and selection.runner and hasattr(selection.runner, "exe_path"):
        exe_path = selection.runner.exe_path
        metadata["exe_path"] = str(exe_path)
        if exe_path and os.path.isfile(exe_path):
            try:
                with open(exe_path, "rb") as f:
                    metadata["exe_sha256"] = hashlib.sha256(f.read()).hexdigest()
            except Exception:
                pass
            try:
                from app.core.iitpave.installation_manager import detect_iitpave_version
                metadata["exe_version"] = detect_iitpave_version(str(exe_path)) or "Unknown"
            except Exception:
                metadata["exe_version"] = "Detected"
                
    summary = MechanisticValidationSummary(
        fatigue=fatigue,
        rutting=rutting,
        is_placeholder=True,
        refused=True,
        refused_reason=reason,
        notes=f"Real IITPAVE verification was not performed: {reason}",
        validation_metadata=metadata
    )
    
    diagnostic = _diagnostic_structural_result(
        result,
        fatigue_check=f"IITPAVE unavailable - {reason}",
        rutting_check=f"IITPAVE unavailable - {reason}",
        note=message,
        summary=summary,
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
        summary=None,
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
        return f"WARN - IITPAVE verification blocked because licensed executable was unavailable: {refused_reason}"
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
    result: Any,
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
    has_mech = (selection is not None and selection.runner is not None and selection.runner.source == SOURCE_EXTERNAL and not summary.refused)
    mode = "Mechanistic Verified Mode" if has_mech else "Decision Support Mode"

    if isinstance(result, StabilizedResult):
        updated = dataclasses.replace(
            result,
            validation_mode=mode,
            mechanistic_validation=summary,
        )
    else:
        from app.core.explainable_design import generate_explainable_details
        import json
        temp_res = dataclasses.replace(
            result,
            fatigue_check=fatigue_text,
            rutting_check=rutting_text,
            mechanistic_validation=summary,
            validation_mode=mode,
        )
        log_dict = generate_explainable_details(temp_res, db=None, project_id=None)
        updated = dataclasses.replace(
            temp_res,
            notes=_append_note(
                result.notes,
                "IITPAVE mechanistic workflow executed through the local external runner.",
            ),
            traceability_log_json=json.dumps(log_dict)
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

    cfg = runner_config or load_persisted_config()
    selection = select_iitpave_runner(cfg)
    if not selection.ok or selection.runner is None:
        reason = selection.blocked_reason or "No usable local IITPAVE executable was found."
        return _blocked(result, input_text=input_text, selection=selection, reason=reason)

    import time
    start_time = time.time()
    try:
        output_text = selection.runner.run(input_text)
        duration = time.time() - start_time
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
            reason="IITPAVE execution completed but output verification failed.",
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
            reason="IITPAVE execution completed but output verification failed.",
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
    
    metadata = compile_iitpave_metadata(selection, input_text, output_text, duration)
    summary = dataclasses.replace(summary, validation_metadata=metadata)
    
    return _completed(
        result,
        input_text=input_text,
        output_text=output_text,
        selection=selection,
        output_contract=output_contract,
        summary=summary,
    )


def run_stabilized_iitpave_mechanistic_workflow(
    result: StabilizedResult,
    *,
    runner_config: IITPaveRunnerConfig | None = None,
    load: LoadConfig | None = None,
) -> IITPaveMechanisticWorkflowResult:
    """Run IITPAVE on the stabilized design composition and attach mechanistic validation."""
    from app.core.structural_design import compute_subgrade_mr
    mr = compute_subgrade_mr(result.inputs.flexible_subgrade_cbr)
    structure = from_structural_layers(
        result.stabilized_composition,
        subgrade_mr_mpa=mr,
    )
    points = default_evaluation_points(structure)
    input_text = build_iitpave_input(structure, load or LoadConfig(), points)

    cfg = runner_config or load_persisted_config()
    selection = select_iitpave_runner(cfg)
    if not selection.ok or selection.runner is None:
        reason = selection.blocked_reason or "No usable local IITPAVE executable was found."
        return _blocked(result, input_text=input_text, selection=selection, reason=reason)

    import time
    start_time = time.time()
    try:
        output_text = selection.runner.run(input_text)
        duration = time.time() - start_time
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
            reason="IITPAVE execution completed but output verification failed.",
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
            reason="IITPAVE execution completed but output verification failed.",
        )

    mech_result = _critical_design_result(mech_result, structure)
    summary = compute_mechanistic_validation(
        MechanisticValidationInput(
            mech_result=mech_result,
            structure=structure,
            design_msa=result.inputs.flexible_design_msa,
            point_labels=(LABEL_FATIGUE, LABEL_RUTTING),
        )
    )
    
    metadata = compile_iitpave_metadata(selection, input_text, output_text, duration)
    summary = dataclasses.replace(summary, validation_metadata=metadata)
    
    return _completed(
        result,
        input_text=input_text,
        output_text=output_text,
        selection=selection,
        output_contract=output_contract,
        summary=summary,
    )


def run_structural_iitpave_optimization_workflow(
    result: StructuralResult,
    *,
    db,
    project_id: int,
    runner_config: IITPaveRunnerConfig | None = None,
    load: LoadConfig | None = None,
    log_callback = None,
) -> tuple[IITPaveMechanisticWorkflowResult, list[dict[str, Any]]]:
    """Execute the iterative silent IITPAVE validation and auto-optimization loop.

    At each step, this function:
    1. Runs the silent subprocess IITPAVE workflow.
    2. Checks if fatigue and/or rutting validations pass.
    3. If they fail, determines the governing failure mechanism based on safety ratios.
    4. Adjusts bituminous, base, or subbase layers based on the governing mode.
    5. Repeats until PASS is achieved, iterations exceed limits, or layer thickness bounds are hit.
    """
    cfg = runner_config or load_persisted_config()
    max_iter = cfg.max_iterations
    
    iterations = []
    current_result = result
    current_wf = None
    
    def log(msg: str):
        if log_callback:
            log_callback(msg)
            
    log(f"Starting verification with config mode: {cfg.mode}")
    
    # Keep track of previous iteration fatigue/rutting life for expected improvement calculation
    prev_nf = None
    prev_nr = None
    
    for i in range(1, max_iter + 1):
        log(f"--- Iteration {i} ---")
        
        # 1. Run the workflow
        current_wf = run_structural_iitpave_mechanistic_workflow(current_result, runner_config=cfg, load=load)
        
        if current_wf.blocked:
            log(f"Iteration {i} blocked: {current_wf.blocked_reason}")
            break
            
        summary = current_wf.summary
        if summary is None:
            log(f"Iteration {i} failed: No summary returned.")
            break
            
        fatigue_pass = summary.fatigue.verdict == "PASS"
        rutting_pass = summary.rutting.verdict == "PASS"
        
        # Calculate safety ratios (life / design_msa)
        design_msa = summary.fatigue.design_msa or 1.0
        nf = summary.fatigue.cumulative_life_msa or 0.0
        nr = summary.rutting.cumulative_life_msa or 0.0
        
        sr_f = nf / design_msa
        sr_r = nr / design_msa
        
        # Determine governing failure
        gov_fail = "None"
        if not fatigue_pass and not rutting_pass:
            gov_fail = "Fatigue" if sr_f < sr_r else "Rutting"
        elif not fatigue_pass:
            gov_fail = "Fatigue"
        elif not rutting_pass:
            gov_fail = "Rutting"
            
        # Log status
        verdict = "PASS" if fatigue_pass and rutting_pass else "FAIL"
        log(f"Verdicts: Fatigue={summary.fatigue.verdict} (Life={nf:.2f} MSA, SR={sr_f:.2f}), "
            f"Rutting={summary.rutting.verdict} (Life={nr:.2f} MSA, SR={sr_r:.2f}). Governing={gov_fail}")
            
        # Determine next optimization decision and reason
        decision = "Keep current design"
        reason = "Design satisfies all mechanistic criteria"
        delta_layer = ""
        delta_val = 0.0
        
        if verdict == "FAIL":
            if gov_fail == "Fatigue":
                # Fatigue governs -> Increase bituminous capacity
                # Get current thicknesses
                bc_val = next((ly.thickness_mm for ly in current_result.composition if ly.name.upper() == "BC"), 0.0)
                dbm_val = next((ly.thickness_mm for ly in current_result.composition if ly.name.upper() == "DBM"), 0.0)
                
                if bc_val > 0.0 and bc_val < cfg.bc_min:
                    decision = f"Increase BC by 10 mm"
                    reason = f"Fatigue governs (SR={sr_f:.2f}) and BC thickness ({bc_val:.0f} mm) is below configurable minimum ({cfg.bc_min:.0f} mm)."
                    delta_layer = "BC"
                    delta_val = 10.0
                elif dbm_val > 0.0 and dbm_val < cfg.dbm_max:
                    decision = f"Increase DBM by 10 mm"
                    reason = f"Fatigue governs (SR={sr_f:.2f}). Increasing DBM to improve fatigue life."
                    delta_layer = "DBM"
                    delta_val = 10.0
                elif bc_val > 0.0 and bc_val < cfg.bc_max:
                    decision = f"Increase BC by 10 mm"
                    reason = f"Fatigue governs (SR={sr_f:.2f}) and DBM is at limit ({dbm_val:.0f} mm). Increasing BC."
                    delta_layer = "BC"
                    delta_val = 10.0
                else:
                    decision = "Exceeded bituminous thickness limits"
                    reason = "Bituminous layers cannot be increased further under current constraints."
            else:
                # Rutting governs -> Increase total/lower structural capacity
                bc_val = next((ly.thickness_mm for ly in current_result.composition if ly.name.upper() == "BC"), 0.0)
                dbm_val = next((ly.thickness_mm for ly in current_result.composition if ly.name.upper() == "DBM"), 0.0)
                wmm_val = next((ly.thickness_mm for ly in current_result.composition if ly.name.upper() == "WMM"), 0.0)
                gsb_val = next((ly.thickness_mm for ly in current_result.composition if ly.name.upper() == "GSB"), 0.0)
                
                if wmm_val > 0.0 and wmm_val < cfg.wmm_max:
                    decision = f"Increase WMM by 10 mm"
                    reason = f"Rutting governs (SR={sr_r:.2f}). Increasing base layer (WMM)."
                    delta_layer = "WMM"
                    delta_val = 10.0
                elif gsb_val > 0.0 and gsb_val < cfg.gsb_max:
                    decision = f"Increase GSB by 10 mm"
                    reason = f"Rutting governs (SR={sr_r:.2f}). Increasing subbase layer (GSB)."
                    delta_layer = "GSB"
                    delta_val = 10.0
                elif dbm_val > 0.0 and dbm_val < cfg.dbm_max:
                    decision = f"Increase DBM by 10 mm"
                    reason = f"Rutting governs (SR={sr_r:.2f}) and WMM/GSB are at limits. Increasing DBM."
                    delta_layer = "DBM"
                    delta_val = 10.0
                elif bc_val > 0.0 and bc_val < cfg.bc_max:
                    decision = f"Increase BC by 10 mm"
                    reason = f"Rutting governs (SR={sr_r:.2f}) and other layers are at limits. Increasing BC."
                    delta_layer = "BC"
                    delta_val = 10.0
                else:
                    decision = "Exceeded total thickness limits"
                    reason = "Pavement layers cannot be increased further under current constraints."

        # Calculate Expected Improvement percentages
        imp_f = 0.0
        imp_r = 0.0
        if prev_nf is not None and prev_nf > 0.0:
            imp_f = ((nf - prev_nf) / prev_nf) * 100.0
        if prev_nr is not None and prev_nr > 0.0:
            imp_r = ((nr - prev_nr) / prev_nr) * 100.0
            
        # Estimate additional material quantity and cost if we made an adjustment
        tonnage_inc = 0.0
        cost_inc = 0.0
        if delta_layer and delta_val > 0.0:
            tonnage_inc, cost_inc, _ = estimate_material_and_cost_increase(
                db=db,
                project_id=project_id,
                layer_name=delta_layer,
                thickness_increase_mm=delta_val
            )
            
        # Store attempt step
        attempt_record = {
            "attempt": i,
            "thicknesses": {ly.name: ly.thickness_mm for ly in current_result.composition},
            "epsilon_t": summary.fatigue.epsilon_t_microstrain,
            "epsilon_v": summary.rutting.epsilon_v_microstrain,
            "nf": nf,
            "nr": nr,
            "fatigue_verdict": summary.fatigue.verdict,
            "rutting_verdict": summary.rutting.verdict,
            "verdict": verdict,
            "governing_failure": gov_fail,
            "decision": decision,
            "reason": reason,
            "expected_improvement_fatigue_pct": imp_f,
            "expected_improvement_rutting_pct": imp_r,
            "estimated_additional_tonnage": tonnage_inc,
            "estimated_cost_increase": cost_inc,
        }
        iterations.append(attempt_record)
        
        prev_nf = nf
        prev_nr = nr
        
        # Stop check
        if verdict == "PASS":
            log(f"Design optimization succeeded on iteration {i}!")
            break
            
        if delta_val == 0.0:
            log(f"Optimization stopped: thickness limits exceeded.")
            break
            
        # Apply the optimization decision
        new_layers = []
        for ly in current_result.composition:
            if ly.name.upper() == delta_layer.upper():
                new_layers.append(dataclasses.replace(ly, thickness_mm=ly.thickness_mm + delta_val))
            else:
                new_layers.append(ly)
                
        new_total_thick = sum(ly.thickness_mm for ly in new_layers)
        current_result = dataclasses.replace(
            current_result,
            composition=tuple(new_layers),
            total_pavement_thickness_mm=new_total_thick
        )
        
    # Return the final result with accumulated history
    final_wf = dataclasses.replace(current_wf, structural_result=current_result, iteration_history=tuple(iterations))
    return final_wf, iterations


def estimate_material_and_cost_increase(
    db,
    project_id: int,
    layer_name: str,
    thickness_increase_mm: float,
) -> tuple[float, float, str]:
    """Return (tonnage_increase, cost_increase, rate_info_str) for a given layer thickness change."""
    # 1. Fetch road length and width from BOQ
    length = 1000.0
    width = 7.0
    mq = db.latest_material_quantity(project_id)
    if mq and mq.inputs_json:
        try:
            import json
            mq_in = json.loads(mq.inputs_json)
            length = float(mq_in.get("road_length_m", 1000.0))
            width = float(mq_in.get("carriageway_width_m", 7.0))
        except Exception:
            pass

    # 2. Get density of layer (t/m^3)
    density = 2.4
    lname = layer_name.upper()
    if "BC" in lname:
        density = 2.4
    elif "DBM" in lname:
        density = 2.4
    elif "WMM" in lname:
        density = 2.2
    elif "GSB" in lname:
        density = 2.1

    # 3. Calculate tonnage increase
    volume = length * width * (thickness_increase_mm / 1000.0)
    tonnage = volume * density

    # 4. Fetch rate for material
    rate = 0.0
    unit = "t"
    try:
        rates = db.list_material_rates()
        for r in rates:
            if r.material.upper() == lname or lname in r.material.upper():
                rate = r.rate
                unit = r.unit
                break
    except Exception:
        pass

    # Standard fallback rates if not found in db:
    if rate == 0.0:
        if "BC" in lname:
            rate, unit = 5500.0, "t"
        elif "DBM" in lname:
            rate, unit = 5000.0, "t"
        elif "WMM" in lname:
            rate, unit = 1800.0, "t"
        elif "GSB" in lname:
            rate, unit = 1200.0, "t"

    cost = tonnage * rate
    rate_info = f"Rate: Rs. {rate:.2f}/{unit}"
    return tonnage, cost, rate_info
