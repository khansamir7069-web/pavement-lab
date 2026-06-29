"""Module-aware combined report builder (Phase 6).

Discovers which modules of a project have saved data and produces a single
Word document containing every available section, each with its governing
IRC code citations:

    * Bituminous Mix Design     → MoRTH Section 500 / IRC:111 (via the
                                  existing ``word_report.build_mix_design_docx``
                                  helpers, only when a live ``MixDesignResult``
                                  is supplied — the DB stores a summary, not
                                  the full re-compute payload).
    * Flexible Pavement Design  → IRC:37-2018
    * BBD Overlay               → IRC:81-1997
    * Cold Mix                  → IRC:SP:100-2014
    * Micro-Surfacing           → IRC:SP:81

Inputs that are persisted in the DB (structural, maintenance) are
re-hydrated via the deterministic engine entry points
(``compute_structural_design``, ``compute_overlay``, ``compute_cold_mix``,
``compute_micro_surfacing``) so the report reproduces exactly what the
user saw at save time. No state escapes the engine.
"""
from __future__ import annotations

import json
import platform
import sys
from dataclasses import dataclass, field, replace
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

from docx.enum.text import WD_ALIGN_PARAGRAPH

from app import __product_name__, __version__
from app.core import (
    ColdMixInput,
    ConditionSurveyInput,
    CodeRef,
    DistressRecord,
    FatigueCalibration,
    FatigueCheck,
    LayerInput,
    MaterialQuantityInput,
    MechanisticValidationSummary,
    MicroSurfacingInput,
    MixDesignResult,
    OverlayInput,
    RuttingCalibration,
    RuttingCheck,
    StructuralInput,
    TrafficInput,
    StabilizedInput,
    StabilizedResult,
    compute_cold_mix,
    compute_condition_survey,
    compute_material_quantity,
    compute_micro_surfacing,
    compute_overlay,
    compute_structural_design,
    compute_traffic_analysis,
    compute_stabilized_design,
)
from app.core.import_summary import ImportedMixResult
from app.db.project_exchange import PROJECT_EXPORT_FORMAT, PROJECT_EXPORT_FORMAT_VERSION
from app.graphs import MarshallChartSet, build_chart_set

from ._docx_common import (
    add_heading,
    add_kv_table,
    add_p,
    add_signature_block,
    new_portrait_document,
    add_table,
)
from .maintenance_report import (
    MaintenanceReportContext,
    write_cold_mix_section,
    write_micro_surfacing_section,
    write_overlay_section,
)
from .material_qty_report import (
    MaterialQuantityReportContext,
    write_material_quantity_section,
)
from .traffic_report import (
    TrafficReportContext,
    write_traffic_section,
)
from .condition_report import (
    ConditionReportContext,
    write_condition_section,
)
from .rehab_report import (
    RehabReportContext,
    write_rehab_section,
)
from .report_revision import ReportRevisionSnapshot
from .structural_report import (
    StructuralReportContext,
    write_structural_section,
)
from .stabilized_report import (
    StabilizedReportContext,
    write_stabilized_section,
)
from .iitpave_schema_history import (
    IITPaveSchemaHistoryReportContext,
    build_iitpave_schema_history_report_summary,
    build_iitpave_schema_history_review,
    write_iitpave_schema_history_section,
)


# ---------------------------------------------------------------------------
# Combined-report context
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class CombinedReportContext:
    project_title: str = ""
    work_name: str = ""
    work_order_no: str = ""
    work_order_date: str = ""
    client: str = ""
    agency: str = ""
    submitted_by: str = ""
    lab_name: str = "Pavement Laboratory"
    report_date: str = field(default_factory=lambda: datetime.now().strftime("%d-%b-%Y"))
    binder_grade: str = ""
    binder_properties: Mapping[str, float] = field(default_factory=dict)
    mix_type_key: str = ""


@dataclass(frozen=True, slots=True)
class CombinedReportProvenanceSummary:
    generated_at: str
    operator_identifier: str
    report_path: str
    project_id: int
    project_work_name: str
    schema_history_selection_status: str
    schema_history_available_ids: tuple[int, ...] = ()
    schema_history_selected_ids: tuple[int, ...] = ()
    schema_history_unknown_ids: tuple[int, ...] = ()
    schema_history_included_count: int = 0
    schema_history_diagnostic_row_count: int = 0
    validation_warnings: tuple[str, ...] = ()
    export_provenance: tuple[str, ...] = ()
    environment_metadata: tuple[str, ...] = ()
    engineering_calculations_allowed: bool = False

    @property
    def operator_summary(self) -> tuple[str, ...]:
        warnings = self.validation_warnings or (
            "No report-time validation warnings recorded.",
        )
        return (
            f"Report generated at: {self.generated_at}.",
            f"Operator identifier: {self.operator_identifier}.",
            f"Project ID: {self.project_id}.",
            f"Project work name: {self.project_work_name}.",
            f"IITPAVE schema-history selection status: {self.schema_history_selection_status}.",
            f"Selected schema history IDs: {_ids_text(self.schema_history_selected_ids)}.",
            f"Available schema history IDs: {_ids_text(self.schema_history_available_ids)}.",
            f"Unknown requested schema history IDs: {_ids_text(self.schema_history_unknown_ids)}.",
            f"Included schema history records: {self.schema_history_included_count}.",
            f"Propagated schema diagnostic rows: {self.schema_history_diagnostic_row_count}.",
            *warnings,
            "Engineering calculations remain blocked for IITPAVE schema audit content.",
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "generated_at": self.generated_at,
            "operator_identifier": self.operator_identifier,
            "report_path": self.report_path,
            "project_id": self.project_id,
            "project_work_name": self.project_work_name,
            "schema_history_selection_status": self.schema_history_selection_status,
            "schema_history_available_ids": list(self.schema_history_available_ids),
            "schema_history_selected_ids": list(self.schema_history_selected_ids),
            "schema_history_unknown_ids": list(self.schema_history_unknown_ids),
            "schema_history_included_count": self.schema_history_included_count,
            "schema_history_diagnostic_row_count": self.schema_history_diagnostic_row_count,
            "validation_warnings": list(self.validation_warnings),
            "export_provenance": list(self.export_provenance),
            "environment_metadata": list(self.environment_metadata),
            "engineering_calculations_allowed": self.engineering_calculations_allowed,
            "operator_summary": list(self.operator_summary),
        }


# ---------------------------------------------------------------------------
# Re-hydrate persisted module rows via the deterministic engines
# ---------------------------------------------------------------------------

def _ids_text(values: Sequence[int]) -> str:
    return ", ".join(str(i) for i in values) if values else "None"


def _coerce_tuple(v) -> tuple:
    return tuple(v) if isinstance(v, list) else v


def _code_refs_from_json(raw) -> tuple[CodeRef, ...]:
    if not isinstance(raw, list):
        return ()
    refs: list[CodeRef] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        code_id = item.get("code_id") or ""
        if code_id:
            refs.append(CodeRef(
                code_id=code_id,
                clause=item.get("clause", "") or "",
                note=item.get("note", "") or "",
            ))
    return tuple(refs)


def _rehydrate_mechanistic_validation(row) -> MechanisticValidationSummary | None:
    if not row or not row.summary_json:
        return None
    try:
        data = json.loads(row.summary_json)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    fatigue_data = data.get("fatigue") or {}
    rutting_data = data.get("rutting") or {}
    fcal_data = fatigue_data.get("calibration") or {}
    rcal_data = rutting_data.get("calibration") or {}
    fatigue_cal = FatigueCalibration(
        label=fcal_data.get("label", "IRC37_PLACEHOLDER_80pct"),
        k1=float(fcal_data.get("k1", 2.21e-04)),
        k2=float(fcal_data.get("k2", 3.89)),
        k3=float(fcal_data.get("k3", 0.854)),
        reliability_pct=int(fcal_data.get("reliability_pct", 80)),
        is_placeholder=bool(fcal_data.get("is_placeholder", True)),
    )
    rutting_cal = RuttingCalibration(
        label=rcal_data.get("label", "IRC37_PLACEHOLDER_80pct"),
        k_r=float(rcal_data.get("k_r", 4.1656e-08)),
        k_v=float(rcal_data.get("k_v", 4.5337)),
        reliability_pct=int(rcal_data.get("reliability_pct", 80)),
        is_placeholder=bool(rcal_data.get("is_placeholder", True)),
    )
    fatigue = FatigueCheck(
        epsilon_t_microstrain=fatigue_data.get("epsilon_t_microstrain"),
        e_bc_mpa=fatigue_data.get("e_bc_mpa"),
        design_msa=float(fatigue_data.get("design_msa", 0.0)),
        c_factor=float(fatigue_data.get("c_factor", 1.0)),
        cumulative_life_msa=fatigue_data.get("cumulative_life_msa"),
        verdict=fatigue_data.get("verdict"),
        calibration=fatigue_cal,
        references=_code_refs_from_json(fatigue_data.get("references")),
        is_placeholder=bool(fatigue_data.get("is_placeholder", True)),
        refused=bool(fatigue_data.get("refused", False)),
        refused_reason=fatigue_data.get("refused_reason", "") or "",
        notes=fatigue_data.get("notes", "") or "",
    )
    rutting = RuttingCheck(
        epsilon_v_microstrain=rutting_data.get("epsilon_v_microstrain"),
        design_msa=float(rutting_data.get("design_msa", fatigue.design_msa)),
        cumulative_life_msa=rutting_data.get("cumulative_life_msa"),
        verdict=rutting_data.get("verdict"),
        calibration=rutting_cal,
        references=_code_refs_from_json(rutting_data.get("references")),
        is_placeholder=bool(rutting_data.get("is_placeholder", True)),
        refused=bool(rutting_data.get("refused", False)),
        refused_reason=rutting_data.get("refused_reason", "") or "",
        notes=rutting_data.get("notes", "") or "",
    )
    return MechanisticValidationSummary(
        fatigue=fatigue,
        rutting=rutting,
        is_placeholder=bool(data.get("is_placeholder", True)),
        refused=bool(data.get("refused", False)),
        refused_reason=data.get("refused_reason", "") or "",
        references=_code_refs_from_json(data.get("references")),
        notes=data.get("notes", "") or "",
    )


def _rehydrate_structural(sd_row, mech_row=None) -> "StructuralResult | None":
    if not sd_row or not sd_row.inputs_json:
        return None
    try:
        d = json.loads(sd_row.inputs_json)
    except json.JSONDecodeError:
        return None
    inp = StructuralInput(
        road_category=d.get("road_category", "NH / SH"),
        design_life_years=int(d.get("design_life_years", 15)),
        initial_cvpd=float(d.get("initial_cvpd", 2000.0)),
        growth_rate_pct=float(d.get("growth_rate_pct", 7.5)),
        vdf=float(d.get("vdf", 2.5)),
        ldf=float(d.get("ldf", 0.75)),
        subgrade_cbr_pct=float(d.get("subgrade_cbr_pct", 5.0)),
        resilient_modulus_mpa=d.get("resilient_modulus_mpa"),
        notes=d.get("notes", "") or "",
    )
    result = compute_structural_design(inp)
    mech = _rehydrate_mechanistic_validation(mech_row)
    if mech is not None and abs(float(mech.fatigue.design_msa) - result.design_msa) <= 0.01:
        has_mech = False
        try:
            inputs_data = json.loads(mech_row.inputs_json) if mech_row.inputs_json else {}
            selection = inputs_data.get("selection") or {}
            runner = selection.get("runner") or {}
            if runner.get("source") == "external_exe":
                has_mech = not mech.refused
        except Exception:
            pass
        mode = "Mechanistic Verified Mode" if has_mech else "Decision Support Mode"
        return replace(
            result,
            mechanistic_validation=mech,
            validation_mode=mode,
            fatigue_check=(
                mech.fatigue.verdict
                or mech.fatigue.refused_reason
                or result.fatigue_check
            ),
            rutting_check=(
                mech.rutting.verdict
                or mech.rutting.refused_reason
                or result.rutting_check
            ),
        )
    return result


def _rehydrate_stabilized(row, has_mechanistic: bool = False) -> "StabilizedResult | None":
    if not row or not row.inputs_json:
        return None
    try:
        d = json.loads(row.inputs_json)
    except json.JSONDecodeError:
        return None
    inp = StabilizedInput(
        ctb_thickness_mm=float(d.get("ctb_thickness_mm", 100.0)),
        ctb_modulus_mpa=float(d.get("ctb_modulus_mpa", 5000.0)),
        ctb_ucs_mpa=float(d.get("ctb_ucs_mpa", 4.0)),
        ctb_poisson=float(d.get("ctb_poisson", 0.25)),
        cts_class=d.get("cts_class", "C1.5/2.0"),
        cts_thickness_mm=float(d.get("cts_thickness_mm", 100.0)),
        cts_modulus_mpa=float(d.get("cts_modulus_mpa", 3000.0)),
        cts_poisson=float(d.get("cts_poisson", 0.25)),
        gsb_thickness_mm=float(d.get("gsb_thickness_mm", 150.0)),
        bituminous_thickness_mm=float(d.get("bituminous_thickness_mm", 100.0)),
        flexible_design_msa=float(d.get("flexible_design_msa", 10.0)),
        flexible_subgrade_cbr=float(d.get("flexible_subgrade_cbr", 5.0)),
        notes=d.get("notes", "") or "",
    )
    return compute_stabilized_design(inp, has_mechanistic_validation=has_mechanistic)


def _rehydrate_overlay(row) -> "OverlayResult | None":
    if not row or not row.inputs_json:
        return None
    try:
        d = json.loads(row.inputs_json)
    except json.JSONDecodeError:
        return None
    inp = OverlayInput(
        deflections_mm=tuple(d.get("deflections_mm") or ()),
        pavement_temp_c=float(d.get("pavement_temp_c", 35.0)),
        bituminous_thickness_mm=float(d.get("bituminous_thickness_mm", 100.0)),
        season_factor=float(d.get("season_factor", 1.0)),
        subgrade_type=d.get("subgrade_type", "granular"),
        design_traffic_msa=float(d.get("design_traffic_msa", 10.0)),
        road_category=d.get("road_category", "NH / SH"),
        notes=d.get("notes", "") or "",
    )
    return compute_overlay(inp)


def _rehydrate_cold_mix(row) -> "ColdMixResult | None":
    if not row or not row.inputs_json:
        return None
    try:
        d = json.loads(row.inputs_json)
    except json.JSONDecodeError:
        return None
    inp = ColdMixInput(
        aggregate_mass_kg=float(d.get("aggregate_mass_kg", 100.0)),
        emulsion_pct=float(d.get("emulsion_pct", 8.0)),
        emulsion_residue_pct=float(d.get("emulsion_residue_pct", 60.0)),
        water_addition_pct=float(d.get("water_addition_pct", 4.0)),
        filler_pct=float(d.get("filler_pct", 2.0)),
        mix_type=d.get("mix_type", "Dense-Graded"),
        notes=d.get("notes", "") or "",
    )
    return compute_cold_mix(inp)


def _rehydrate_traffic(row) -> "TrafficResult | None":
    if not row or not row.inputs_json:
        return None
    try:
        d = json.loads(row.inputs_json)
    except json.JSONDecodeError:
        return None
    inp = TrafficInput(
        initial_cvpd=float(d.get("initial_cvpd", 2000.0)),
        growth_rate_pct=float(d.get("growth_rate_pct", 7.5)),
        design_life_years=int(d.get("design_life_years", 15)),
        terrain=d.get("terrain", "Plain"),
        lane_config=d.get("lane_config", "Two-lane carriageway"),
        vdf=d.get("vdf"),
        ldf=d.get("ldf"),
        road_category=d.get("road_category", "NH / SH"),
        notes=d.get("notes", "") or "",
        axle_spectrum_kn=tuple(d.get("axle_spectrum_kn") or ()),
        wim_records=tuple(d.get("wim_records") or ()),
        survey_source_file=d.get("survey_source_file", "") or "",
    )
    return compute_traffic_analysis(inp)


def _rehydrate_condition(row) -> "ConditionSurveyResult | None":
    if not row or not row.inputs_json:
        return None
    try:
        d = json.loads(row.inputs_json)
    except json.JSONDecodeError:
        return None
    records = tuple(
        DistressRecord(
            distress_type=r.get("distress_type", "cracking"),
            severity=r.get("severity", "low"),
            length_m=float(r.get("length_m") or 0),
            area_m2=float(r.get("area_m2") or 0),
            count=int(r.get("count") or 0),
            notes=r.get("notes", "") or "",
            image_paths=tuple(r.get("image_paths") or ()),
        )
        for r in (d.get("records") or ())
    )
    inp = ConditionSurveyInput(
        work_name=d.get("work_name", "") or "",
        surveyed_by=d.get("surveyed_by", "") or "",
        survey_date=d.get("survey_date", "") or "",
        chainage_from_km=float(d.get("chainage_from_km") or 0),
        chainage_to_km=float(d.get("chainage_to_km") or 0),
        lane_id=d.get("lane_id", "") or "",
        records=records,
        notes=d.get("notes", "") or "",
        image_paths=tuple(d.get("image_paths") or ()),
        ai_classification_hint=d.get("ai_classification_hint", "") or "",
        gis_geometry_geojson=d.get("gis_geometry_geojson", "") or "",
    )
    return compute_condition_survey(inp)


def _rehydrate_material_qty(row) -> "MaterialQuantityResult | None":
    if not row or not row.inputs_json:
        return None
    try:
        d = json.loads(row.inputs_json)
    except json.JSONDecodeError:
        return None
    layers_raw = d.get("layers") or []
    layers = tuple(
        LayerInput(
            layer_type=L.get("layer_type", "DBM"),
            length_m=float(L.get("length_m", 1000.0)),
            width_m=float(L.get("width_m", 3.5)),
            thickness_mm=float(L.get("thickness_mm", 40.0)),
            density_t_m3=L.get("density_t_m3"),
            binder_pct=L.get("binder_pct"),
            spray_rate_kgm2=L.get("spray_rate_kgm2"),
            waste_pct=float(L.get("waste_pct", 2.0)),
            notes=L.get("notes", "") or "",
        )
        for L in layers_raw
    )
    return compute_material_quantity(MaterialQuantityInput(
        project_id=d.get("project_id"), layers=layers,
        notes=d.get("notes", "") or "",
    ))


def _rehydrate_micro(row) -> "MicroSurfacingResult | None":
    if not row or not row.inputs_json:
        return None
    try:
        d = json.loads(row.inputs_json)
    except json.JSONDecodeError:
        return None
    inp = MicroSurfacingInput(
        surfacing_type=d.get("surfacing_type", "Type II"),
        aggregate_mass_kg=float(d.get("aggregate_mass_kg", 100.0)),
        emulsion_pct=float(d.get("emulsion_pct", 13.0)),
        emulsion_residue_pct=float(d.get("emulsion_residue_pct", 62.0)),
        additive_water_pct=float(d.get("additive_water_pct", 8.0)),
        mineral_filler_pct=float(d.get("mineral_filler_pct", 1.5)),
        notes=d.get("notes", "") or "",
    )
    return compute_micro_surfacing(inp)


# ---------------------------------------------------------------------------
# Section dispatch (sub_module key -> writer)
# ---------------------------------------------------------------------------

def _maint_ctx(ctx: CombinedReportContext) -> MaintenanceReportContext:
    return MaintenanceReportContext(
        project_title=ctx.project_title,
        work_name=ctx.work_name,
        work_order_no=ctx.work_order_no,
        work_order_date=ctx.work_order_date,
        client=ctx.client,
        agency=ctx.agency,
        submitted_by=ctx.submitted_by,
        lab_name=ctx.lab_name,
        report_date=ctx.report_date,
    )


def _struct_ctx(ctx: CombinedReportContext, execution_time: str | None = None) -> StructuralReportContext:
    return StructuralReportContext(
        project_title=ctx.project_title,
        work_name=ctx.work_name,
        work_order_no=ctx.work_order_no,
        work_order_date=ctx.work_order_date,
        client=ctx.client,
        agency=ctx.agency,
        submitted_by=ctx.submitted_by,
        lab_name=ctx.lab_name,
        report_date=ctx.report_date,
        execution_time=execution_time,
    )


def _stab_ctx(ctx: CombinedReportContext, execution_time: str | None = None) -> StabilizedReportContext:
    return StabilizedReportContext(
        project_title=ctx.project_title,
        work_name=ctx.work_name,
        work_order_no=ctx.work_order_no,
        work_order_date=ctx.work_order_date,
        client=ctx.client,
        agency=ctx.agency,
        submitted_by=ctx.submitted_by,
        lab_name=ctx.lab_name,
        report_date=ctx.report_date,
        execution_time=execution_time,
    )


def _schema_history_ctx(ctx: CombinedReportContext) -> IITPaveSchemaHistoryReportContext:
    return IITPaveSchemaHistoryReportContext(
        project_title=ctx.project_title,
        work_name=ctx.work_name,
        work_order_no=ctx.work_order_no,
        work_order_date=ctx.work_order_date,
        client=ctx.client,
        agency=ctx.agency,
        submitted_by=ctx.submitted_by,
        lab_name=ctx.lab_name,
        report_date=ctx.report_date,
    )


def _project_validation_warnings(db, project_id: int) -> tuple[str, ...]:
    if not hasattr(db, "validate_project_config"):
        return ()
    try:
        validation = db.validate_project_config(project_id)
    except Exception:
        return ("Project configuration validation metadata could not be loaded.",)
    warnings: list[str] = []
    for issue in getattr(validation, "issues", ()) or ():
        severity = str(getattr(issue, "severity", "") or "warning")
        field = str(getattr(issue, "field", "") or "project.config")
        message = str(getattr(issue, "message", "") or "Validation metadata unavailable.")
        warnings.append(f"{severity}: {field}: {message}")
    return tuple(warnings)


def build_combined_report_provenance_summary(
    *,
    db,
    project_id: int,
    project,
    ctx: CombinedReportContext,
    out_path: Path,
    schema_history_summary=None,
) -> CombinedReportProvenanceSummary:
    selection = getattr(schema_history_summary, "selection", None)
    validation_warnings = list(_project_validation_warnings(db, project_id))
    if selection is not None and selection.skipped_unknown_history_ids:
        validation_warnings.append(
            "warning: iitpave_schema_history_selection: "
            "unknown requested history IDs were ignored: "
            f"{_ids_text(selection.skipped_unknown_history_ids)}."
        )
    return CombinedReportProvenanceSummary(
        generated_at=datetime.now().replace(microsecond=0).isoformat(sep=" "),
        operator_identifier=(ctx.submitted_by or "Not recorded"),
        report_path=str(out_path),
        project_id=project_id,
        project_work_name=(
            ctx.work_name
            or getattr(project, "work_name", "")
            or "Not recorded"
        ),
        schema_history_selection_status=(
            selection.status if selection is not None else "No schema-history selection metadata."
        ),
        schema_history_available_ids=(
            selection.available_history_ids if selection is not None else ()
        ),
        schema_history_selected_ids=(
            selection.selected_history_ids if selection is not None else ()
        ),
        schema_history_unknown_ids=(
            selection.skipped_unknown_history_ids if selection is not None else ()
        ),
        schema_history_included_count=int(
            getattr(schema_history_summary, "included_history_count", 0) or 0
        ),
        schema_history_diagnostic_row_count=int(
            getattr(schema_history_summary, "diagnostic_row_count", 0) or 0
        ),
        validation_warnings=tuple(validation_warnings),
        export_provenance=(
            f"Project exchange format: {PROJECT_EXPORT_FORMAT} "
            f"v{PROJECT_EXPORT_FORMAT_VERSION}.",
            "Project import creates new local rows; source record IDs are preserved only as provenance.",
            "Imported IITPAVE schema-history audit IDs are shown exactly as recorded and are not remapped.",
        ),
        environment_metadata=(
            f"Application: {__product_name__} v{__version__}.",
            f"Runtime: Python {sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}.",
            f"Platform family: {platform.system() or 'Not recorded'} {platform.release() or ''}".strip(),
        ),
        engineering_calculations_allowed=False,
    )


def write_combined_report_provenance_section(
    doc,
    summary: CombinedReportProvenanceSummary,
) -> None:
    add_heading(
        doc,
        "REPORT PROVENANCE AND TRACEABILITY",
        level=1,
        align=WD_ALIGN_PARAGRAPH.CENTER,
    )
    add_heading(doc, "Generation Metadata", level=2)
    add_kv_table(doc, (
        ("Report generated at", summary.generated_at),
        ("Operator identifier", summary.operator_identifier),
        ("Project ID", str(summary.project_id)),
        ("Project work name", summary.project_work_name),
        ("Report path", summary.report_path),
    ))

    add_heading(doc, "IITPAVE Schema-History Selection Summary", level=2)
    add_kv_table(doc, (
        ("Selection status", summary.schema_history_selection_status),
        ("Available candidate IDs", _ids_text(summary.schema_history_available_ids)),
        ("Selected history IDs", _ids_text(summary.schema_history_selected_ids)),
        ("Unknown requested IDs", _ids_text(summary.schema_history_unknown_ids)),
        ("Included history records", str(summary.schema_history_included_count)),
        ("Propagated diagnostic rows", str(summary.schema_history_diagnostic_row_count)),
        ("Engineering calculations allowed", "No"),
    ))

    add_heading(doc, "Validation Warning Summary", level=2)
    for line in summary.validation_warnings or (
        "No report-time validation warnings recorded.",
    ):
        add_p(doc, line, size=10)

    add_heading(doc, "Export And Import Provenance", level=2)
    for line in summary.export_provenance:
        add_p(doc, line, size=10)

    add_heading(doc, "Report Environment Metadata", level=2)
    for line in summary.environment_metadata:
        add_p(doc, line, size=10)

    add_p(
        doc,
        "This provenance section is read-only audit metadata. It does not "
        "extract IITPAVE strains, run mechanistic calculations, evaluate "
        "fatigue or rutting, make IRC compliance claims, or issue engineering "
        "recommendations.",
        size=9,
        italic=True,
    )


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def build_combined_report(
    out_path: Path,
    db,
    project_id: int,
    ctx: CombinedReportContext,
    *,
    mix_result_live: "MixDesignResult | ImportedMixResult | None" = None,
    mix_chart_set: Optional[MarshallChartSet] = None,
    mix_material_calc=None,
    schema_history_selection_ids: Sequence[int] | None = None,
) -> tuple[Path, list[str]]:
    """Build a single Word document for every module that has saved data."""
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    p = db.get_project(project_id)
    if p is None:
        raise ValueError(f"Project #{project_id} not found.")

    # Run Expert Design Audit (fail-safe)
    audit_result = None
    try:
        from app.engineering.design_audit import run_project_audit
        audit_result = run_project_audit(project_id, db)
    except Exception as e:
        import logging
        logging.getLogger(__name__).exception("Failed to run design audit for report: %s", e)

    # Run Pavement Alternative Comparison (fail-safe)
    pavement_options = []
    has_pavement_options = False
    try:
        from app.engineering.option_engine import generate_pavement_options
        pavement_options = generate_pavement_options(project_id, db)
        has_pavement_options = any(opt.get("total_pavement_thickness", 0.0) > 0 for opt in pavement_options)
    except Exception as e:
        import logging
        logging.getLogger(__name__).exception("Failed to generate pavement options for report: %s", e)


    # Discover persisted modules
    sd_row = db.latest_structural_design(project_id)
    ov_row = db.latest_maintenance_design(project_id, "overlay")
    cm_row = db.latest_maintenance_design(project_id, "cold_mix")
    ms_row = db.latest_maintenance_design(project_id, "micro_surfacing")
    stab_row = db.latest_stabilized_design(project_id)

    mech_val = db.latest_mechanistic_validation(project_id)
    has_mechanistic = mech_val is not None and not mech_val.refused
    exec_time_str = None
    if mech_val and mech_val.computed_at:
        exec_time_str = mech_val.computed_at.strftime("%d-%b-%Y %H:%M:%S")

    structural = _rehydrate_structural(
        sd_row,
        mech_val,
    )
    overlay = _rehydrate_overlay(ov_row)
    cold_mix = _rehydrate_cold_mix(cm_row)
    micro = _rehydrate_micro(ms_row)
    stabilized = _rehydrate_stabilized(stab_row, has_mechanistic=has_mechanistic)
    mq_row = db.latest_material_quantity(project_id)
    material_qty = _rehydrate_material_qty(mq_row)
    tr_row = db.latest_traffic_analysis(project_id)
    traffic = _rehydrate_traffic(tr_row)
    condition = _rehydrate_condition(db.latest_condition_survey(project_id))
    
    # Phase 12 synthesis — derived on-demand from the rehydrated
    # condition + traffic + maintenance results.
    rehab_synthesis = None
    if condition is not None:
        from app.core import (
            RecommendationContext,
            compute_rehab_recommendations,
        )
        rehab_synthesis = compute_rehab_recommendations(
            RecommendationContext(
                condition=condition,
                traffic=traffic,
                overlay_design=overlay,
                cold_mix_design=cold_mix,
                micro_surfacing_design=micro,
            )
        )

    schema_history_review = build_iitpave_schema_history_review(
        project_id,
        db.list_iitpave_schema_diagnostics(project_id),
        selected_history_ids=schema_history_selection_ids,
    )
    schema_history_provenance_summary = build_iitpave_schema_history_report_summary(
        schema_history_review,
        selection=schema_history_review.selection,
        report_path=out_path,
    )

    provenance_summary = build_combined_report_provenance_summary(
        db=db,
        project_id=project_id,
        project=p,
        ctx=ctx,
        out_path=out_path,
        schema_history_summary=schema_history_provenance_summary,
    )

    have_mix = mix_result_live is not None
    have_any = any((have_mix, traffic, structural, stabilized, overlay, cold_mix, micro,
                    material_qty, condition, schema_history_review.items))
    if not have_any:
        raise ValueError(
            "No module data found for this project — compute and save at "
            "least one module before exporting a combined report."
        )

    # Load local branding config
    from app.core.branding import get_branding_profile
    brand = get_branding_profile()
    brand_company = brand.get("company_name") or p.consultant or ctx.agency or "Pavement Engineering Consultants"
    brand_engineer = brand.get("engineer_name") or ctx.submitted_by or "N/A"
    brand_logo = brand.get("logo_path") or ""

    doc = new_portrait_document()

    # ---- 1. Standalone Cover Page ----
    add_p(doc, "\n" * 1)
    if brand_logo:
        logo_path = Path(brand_logo)
        if logo_path.is_file():
            try:
                p_logo = doc.add_paragraph()
                p_logo.alignment = WD_ALIGN_PARAGRAPH.CENTER
                run_logo = p_logo.add_run()
                run_logo.add_picture(str(logo_path), width=Inches(1.5))
                add_p(doc, "\n")
            except Exception:
                pass

    add_heading(doc, brand_company.upper(), level=1, align=WD_ALIGN_PARAGRAPH.CENTER)
    add_heading(doc, "PROFESSIONAL PAVEMENT DESIGN REPORT", level=2, align=WD_ALIGN_PARAGRAPH.CENTER)
    add_p(doc, "\n")
    
    add_kv_table(doc, (
        ("Project Name",      p.work_name or "(Untitled Project)"),
        ("Client Name",       p.client.name if p.client else (ctx.client or "N/A")),
        ("Location",          p.location or "N/A"),
        ("Consultant",        brand_company),
        ("Report Number",     p.report_id or "N/A"),
        ("Revision Number",   f"R{p.revision_number}"),
        ("Submission Date",   ctx.report_date),
    ))
    
    add_p(doc, "\n" * 1)
    add_p(doc, "========================================================================", size=10, align=WD_ALIGN_PARAGRAPH.CENTER)
    add_p(doc, "Engineering Decision-Support Report — Final approval/sign-off by qualified pavement engineer required.",
          bold=True, size=10, align=WD_ALIGN_PARAGRAPH.CENTER)
    add_p(doc, "========================================================================", size=10, align=WD_ALIGN_PARAGRAPH.CENTER)
    
    doc.add_page_break()

    # ---- 2. Standalone Document Control Page ----
    add_heading(doc, "DOCUMENT CONTROL SHEET", level=1, align=WD_ALIGN_PARAGRAPH.LEFT)
    add_p(doc, "\n")
    
    doc_control_rows = [
        ("Prepared By", brand_engineer),
        ("Checked By", p.checked_by or "N/A"),
        ("Approved By", "Qualified Reviewing Engineer / Client Authority")
    ]
    add_kv_table(doc, doc_control_rows)
    
    add_p(doc, "\n" * 2)
    add_heading(doc, "Revision History Table", level=2)
    
    rev_rows = []
    
    revisions_list = []
    if p.revisions_json:
        try:
            revisions_list = json.loads(p.revisions_json)
        except Exception:
            pass
            
    # Check if R0 is in the list, if not prepend it
    has_r0 = any(r.get("revision_number") == 0 for r in revisions_list)
    if not has_r0:
        r0_date = p.created_at.strftime("%Y-%m-%d") if p.created_at else "N/A"
        r0_eng = p.submitted_by or brand_engineer or "N/A"
        r0_val = "Not Audited"
        if p.validation_results_json and (p.revision_number or 0) == 0:
            try:
                res_dict = json.loads(p.validation_results_json)
                r0_val = f"{res_dict.get('final_recommendation')} (Score: {res_dict.get('score')}/100)"
            except Exception:
                pass
        rev_rows.append(["R0", r0_date, r0_eng, "Initial Design Submission", r0_val, "None"])
        
    for r in revisions_list:
        rev_num = r.get("revision_number", 0)
        rev_id = f"R{rev_num}"
        dt_str = r.get("created_date") or r.get("date_time") or ""
        if "T" in dt_str:
            try:
                dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
                date_str = dt.strftime("%Y-%m-%d")
            except Exception:
                date_str = dt_str[:10]
        else:
            date_str = dt_str or "N/A"
            
        eng = r.get("engineer") or r.get("engineer_name") or "N/A"
        desc = r.get("description") or r.get("engineer_note") or "N/A"
        
        # If engineer_note is a JSON string, extract details
        if isinstance(desc, str) and desc.strip().startswith("{"):
            try:
                note_data = json.loads(desc)
                desc = note_data.get("description") or desc
                eng = note_data.get("engineer") or eng
            except Exception:
                pass
                
        val_status = r.get("validation_status") or "Draft"
        files = r.get("generated_files", [])
        files_str = ", ".join(files) if files else "None"
        
        rev_rows.append([rev_id, date_str, eng, desc, val_status, files_str])
        
    add_table(doc, ["Rev", "Date", "Engineer", "Description of Change", "Validation Status", "Generated Files"], rev_rows)
    doc.add_page_break()

    # ---- 3. Contents Page ----
    add_heading(doc, "Contents of this Report", level=2)
    toc_rows: list[list[str]] = [
        ["Executive Summary", "Project summary and engineering disclaimer"],
        ["Appendix A: Traffic Calculation", "Commercial traffic projection and MSA calculation"],
        ["Appendix B: Subgrade Evaluation", "Subgrade CBR and Resilient Modulus (Mr) details"],
        ["Appendix C: Pavement Design Summary", "Empirical structural design layers & alternative comparison"],
        ["Appendix D: IITPAVE Verification", "Linear elastic mechanistic strain checks and life verdicts"],
        ["Appendix E: Mix Design", "Optimum Binder Content & companion mix report reference"],
        ["Appendix F: BOQ & Cost Estimate", "Preliminary material quantities & cost estimate summary"],
        ["Appendix G: Expert Audit Report", "Consultant design validation suitabilty score & findings"]
    ]
    
    if overlay or cold_mix or micro:
        toc_rows.append(["Maintenance & Rehabilitation Design", "BBD overlay / Cold mix / Micro-surfacing options"])
    if condition:
        toc_rows.append(["Pavement Condition Survey", "PCI distress index survey and condition state summary"])
    if schema_history_review.items:
        toc_rows.append(["IITPAVE Schema Diagnostics History", "Audit-only parser/fixture traceability"])
        
    toc_rows.append(["Assumptions Sheet", "Poisson's ratios, moduli, and growth presets"])
    toc_rows.append(["Limitations of the Report", "Engineering screening disclaimers"])
    toc_rows.append(["Engineer Review Checklist", "Checklist verification list"])
    toc_rows.append(["Engineering Sign-Off and Seal", "Reviewer signatures"])

    add_table(doc, ["Section / Appendix", "Governing Reference / Description"], toc_rows)
    doc.add_page_break()
    
    # ---- 4. Executive Summary ----
    write_executive_summary_section(doc, p, structural, stabilized, mech_val, db=db)

    included: list[str] = []
    schema_history_summary = None

    # ---- APPENDIX A: TRAFFIC CALCULATION ----
    doc.add_page_break()
    add_heading(doc, "APPENDIX A: TRAFFIC CALCULATION", level=1, align=WD_ALIGN_PARAGRAPH.CENTER)
    if traffic:
        write_traffic_section(doc, TrafficReportContext(
            project_title=ctx.project_title, work_name=ctx.work_name,
            work_order_no=ctx.work_order_no, work_order_date=ctx.work_order_date,
            client=ctx.client, agency=ctx.agency, submitted_by=ctx.submitted_by,
            lab_name=ctx.lab_name, report_date=ctx.report_date,
        ), traffic, include_header=False)
        
        # Traceability
        traffic_inputs = [
            ("Initial Commercial Traffic (A)", f"{traffic.inputs.initial_cvpd:g} CVPD"),
            ("Annual Growth Rate (r)", f"{traffic.inputs.growth_rate_pct:g} %"),
            ("Vehicle Damage Factor (F)", f"{traffic.vdf_used:g}"),
            ("Lane Distribution Factor (D)", f"{traffic.ldf_used:g}"),
            ("Design Life (n)", f"{traffic.inputs.design_life_years} years")
        ]
        traffic_outputs = [
            ("Cumulative Design Traffic (N)", f"{traffic.design_msa:.2f} MSA")
        ]
        add_traceability_block(doc, "Traffic Projection", traffic_inputs, traffic_outputs, "IRC:37-2018 (Clause 4.6)")
        included.append("Appendix A: Traffic Calculation")
    else:
        add_p(doc, "No traffic analysis recorded for this project.")

    # ---- APPENDIX B: SUBGRADE EVALUATION ----
    doc.add_page_break()
    add_heading(doc, "APPENDIX B: SUBGRADE EVALUATION", level=1, align=WD_ALIGN_PARAGRAPH.CENTER)
    if structural:
        add_heading(doc, "Subgrade Characterization", level=2)
        add_p(doc, "The subgrade strength is evaluated in terms of the California Bearing Ratio (CBR) and Resilient Modulus (M_R).")
        subg_data = [
            ["Subgrade CBR (4-day soaked)", f"{structural.inputs.subgrade_cbr_pct:g}", "%"],
            ["Resilient Modulus (M_R)", f"{structural.subgrade_mr_mpa:.1f}", "MPa"]
        ]
        add_table(doc, ["Property Description", "Design Value", "Unit"], subg_data)
        add_p(doc, "")
        
        # Traceability
        subg_inputs = [
            ("California Bearing Ratio (CBR)", f"{structural.inputs.subgrade_cbr_pct:g} %")
        ]
        subg_outputs = [
            ("Resilient Modulus (Mr)", f"{structural.subgrade_mr_mpa:.1f} MPa")
        ]
        add_traceability_block(doc, "Subgrade Resilient Modulus", subg_inputs, subg_outputs, "IRC:37-2018 (Annex E)")
        included.append("Appendix B: Subgrade Evaluation")
    else:
        add_p(doc, "No subgrade strength evaluations recorded.")

    # ---- APPENDIX C: PAVEMENT DESIGN SUMMARY ----
    doc.add_page_break()
    add_heading(doc, "APPENDIX C: PAVEMENT DESIGN SUMMARY", level=1, align=WD_ALIGN_PARAGRAPH.CENTER)
    
    has_c_content = False
    if structural:
        write_structural_section(doc, _struct_ctx(ctx, execution_time=exec_time_str), structural, include_header=False)
        # Traceability
        struct_inputs = [
            ("Cumulative Design Traffic (N)", f"{structural.design_msa:.2f} MSA"),
            ("Subgrade Resilient Modulus (Mr)", f"{structural.subgrade_mr_mpa:.1f} MPa")
        ]
        struct_outputs = [
            ("Total Pavement Thickness", f"{structural.total_pavement_thickness_mm:.0f} mm")
        ]
        add_traceability_block(doc, "Flexible Pavement Structural Thickness", struct_inputs, struct_outputs, "IRC:37-2018 (Pavement Catalogue / Plates)")
        has_c_content = True
        
    if stabilized:
        add_p(doc, "\n")
        write_stabilized_section(doc, _stab_ctx(ctx, execution_time=exec_time_str), stabilized, include_header=False)
        has_c_content = True
        
    if has_pavement_options:
        add_p(doc, "\n")
        write_pavement_alternative_comparison_section(doc, pavement_options, p)
        has_c_content = True
        
    if has_c_content:
        included.append("Appendix C: Pavement Design Summary")
    else:
        add_p(doc, "No structural pavement designs have been finalized.")

    # ---- APPENDIX D: IITPAVE VERIFICATION ----
    doc.add_page_break()
    add_heading(doc, "APPENDIX D: IITPAVE VERIFICATION", level=1, align=WD_ALIGN_PARAGRAPH.CENTER)
    if mech_val and not mech_val.refused:
        add_heading(doc, "Mechanistic Validation Outcomes", level=2)
        if "Demo verification example only" in (mech_val.notes or ""):
            add_p(doc, "WARNING: Demo verification example only — not actual IITPAVE execution.", bold=True)
        else:
            add_p(doc, "The designed pavement layer composition has been validated using the linear elastic analysis program IITPAVE.")
        
        iit_data = [
            ["Fatigue Life (MSA)", f"{mech_val.fatigue_life_msa:.2f}"],
            ["Rutting Life (MSA)", f"{mech_val.rutting_life_msa:.2f}"],
            ["Design Life (MSA)", f"{mech_val.design_msa:.2f}"],
            ["Tensile Strain (Microstrain)", f"{mech_val.tensile_strain_micro:.1f}"],
            ["Compressive Strain (Microstrain)", f"{mech_val.compressive_strain_micro:.1f}"],
            ["Fatigue Check Verdict", mech_val.fatigue_verdict],
            ["Rutting Check Verdict", mech_val.rutting_verdict]
        ]
        add_table(doc, ["Verification Metric", "Value / Verdict"], iit_data)
        add_p(doc, "")
        
        subgrade_mr_val = 0.0
        if structural:
            subgrade_mr_val = structural.subgrade_mr_mpa
        elif p.subgrade_mr:
            subgrade_mr_val = p.subgrade_mr
            
        iit_inputs = [
            ("Design Traffic", f"{mech_val.design_msa} MSA"),
            ("Subgrade Mr", f"{subgrade_mr_val:.1f} MPa")
        ]
        iit_outputs = [
            ("Fatigue Life", f"{mech_val.fatigue_life_msa:.2f} MSA"),
            ("Rutting Life", f"{mech_val.rutting_life_msa:.2f} MSA")
        ]
        add_traceability_block(doc, "IITPAVE Mechanistic Safety Verification", iit_inputs, iit_outputs, "IRC:37-2018 (Section 6 & IITPAVE Engine)")
        included.append("Appendix D: IITPAVE Verification")
    else:
        add_p(doc, "IITPAVE mechanistic validation was not performed. Pavement design is prepared under empirical Decision Support Mode guidelines.")

    # ---- APPENDIX E: MIX DESIGN ----
    doc.add_page_break()
    add_heading(doc, "APPENDIX E: MIX DESIGN", level=1, align=WD_ALIGN_PARAGRAPH.CENTER)
    if have_mix:
        from . import word_report
        from app.core import MIX_SPECS
        
        chart_set = mix_chart_set or build_chart_set(mix_result_live.summary, mix_result_live.obc)
        chart_image_dir = out_path.parent / f"{out_path.stem}_charts"
        
        mix_path = out_path.with_name(f"{out_path.stem}_MixDesign.docx")
        if not ctx.mix_type_key:
            raise ValueError("Combined report includes mix design but mix_type_key is empty.")
            
        word_report.build_mix_design_docx(
            mix_path,
            word_report.ReportContext(
                project_title=ctx.project_title, mix_type_key=ctx.mix_type_key,
                work_name=ctx.work_name, work_order_no=ctx.work_order_no,
                work_order_date=ctx.work_order_date, client=ctx.client,
                agency=ctx.agency, submitted_by=ctx.submitted_by,
                lab_name=ctx.lab_name, report_date=ctx.report_date,
                binder_grade=ctx.binder_grade, binder_properties=ctx.binder_properties,
                materials={},
            ),
            mix_result_live, chart_set, chart_image_dir, material_calc=mix_material_calc
        )
        
        spec_name = MIX_SPECS.get(ctx.mix_type_key)
        spec_label = spec_name.name if spec_name else ctx.mix_type_key
        
        add_heading(doc, "Bituminous Mix Summary", level=2)
        add_p(doc, f"Detailed Marshall Mix Design charts and gradation tables are exported in companion file: {mix_path.name}.")
        
        add_kv_table(doc, (
            ("Mix Type", spec_label),
            ("Optimum Bitumen Content (OBC)", f"{mix_result_live.obc.obc_pct:.2f} %"),
            ("Target Air Voids", f"{mix_result_live.obc.target_air_voids_pct:.1f} %"),
            ("Bulk SG (Gsb)", f"{mix_result_live.bulk_sg_blend:.3f}"),
            ("Compliance", "PASS" if mix_result_live.compliance.overall_pass else "FAIL"),
        ))
        
        # Traceability
        mix_inputs = [
            ("Gradation Standard", "MoRTH Section 500"),
            ("Binder Properties", ctx.binder_grade or "N/A")
        ]
        mix_outputs = [
            ("Optimum Binder Content (OBC)", f"{mix_result_live.obc.obc_pct:.2f} %"),
            ("Overall Compliance Check", "PASS" if mix_result_live.compliance.overall_pass else "FAIL")
        ]
        add_traceability_block(doc, "Marshall Mix Design", mix_inputs, mix_outputs, "MoRTH Section 500 / IRC:111 / Marshall Method")
        included.append("Appendix E: Mix Design")
    else:
        add_p(doc, "No bituminous mix design data recorded.")

    # ---- APPENDIX F: BOQ & COST ESTIMATE ----
    doc.add_page_break()
    add_heading(doc, "APPENDIX F: BOQ & COST ESTIMATE", level=1, align=WD_ALIGN_PARAGRAPH.CENTER)
    if material_qty:
        mq_ctx = MaterialQuantityReportContext(
            project_title=ctx.project_title, work_name=ctx.work_name,
            work_order_no=ctx.work_order_no, work_order_date=ctx.work_order_date,
            client=ctx.client, agency=ctx.agency, submitted_by=ctx.submitted_by,
            lab_name=ctx.lab_name, report_date=ctx.report_date,
        )
        write_material_quantity_section(doc, mq_ctx, material_qty, include_header=False, db=db)
        
        # Cost Estimate
        boq_res = {}
        try:
            from app.engineering.boq_engine import generate_boq
            boq_res = generate_boq(project_id, db)
        except Exception:
            pass
            
        if boq_res.get("available"):
            add_heading(doc, "Preliminary Pavement Cost Estimate", level=2)
            add_p(doc, "Estimated preliminary material cost based on pavement geometry and base SOR rates:")
            
            est_cost_str = boq_res.get("total_project_cost_formatted") or f"Rs. {boq_res.get('total_project_cost', 0):,.2f}"
            cost_km_str = f"Rs. {boq_res.get('cost_per_km', 0):,.2f} / km" if boq_res.get("cost_per_km") else "—"
            
            cost_data = [
                ["Total Project Estimated Cost", est_cost_str],
                ["Cost per Kilometre", cost_km_str]
            ]
            add_table(doc, ["Metric Description", "Value (Preliminary Estimate)"], cost_data)
            
            # Traceability
            boq_inputs = [
                ("Pavement Geometry Length", f"{boq_res.get('road_length_m', 1000)} m"),
                ("Carriageway Width", f"{boq_res.get('carriageway_width_m', 7.0)} m")
            ]
            boq_outputs = [
                ("Preliminary Estimated Cost", est_cost_str)
            ]
            add_traceability_block(doc, "Preliminary BOQ Costing", boq_inputs, boq_outputs, "MoRTH Specification & SOR Standard")
            
        included.append("Appendix F: BOQ & Cost Estimate")
    else:
        add_p(doc, "No materials estimation or BOQ calculations recorded.")

    # ---- APPENDIX G: EXPERT AUDIT REPORT ----
    doc.add_page_break()
    add_heading(doc, "APPENDIX G: EXPERT AUDIT REPORT", level=1, align=WD_ALIGN_PARAGRAPH.CENTER)
    if audit_result:
        write_expert_design_audit_section(doc, audit_result)
        # Traceability
        audit_inputs = [
            ("Pavement Project Design Parameters", "SQLite DB Snapshot")
        ]
        audit_outputs = [
            ("Engineering Suitability Score", f"{audit_result.score}/100"),
            ("Design Risk Level", audit_result.risk_level),
            ("Readiness Status", audit_result.readiness_status)
        ]
        add_traceability_block(doc, "Pavement Design Audit", audit_inputs, audit_outputs, "Senior Highway Consultant Guidelines Checklist")
        included.append("Appendix G: Expert Audit Report")
    else:
        add_p(doc, "Design audit report not available.")

    # ---- Report Provenance ----
    doc.add_page_break()
    write_combined_report_provenance_section(doc, provenance_summary)
    included.append("Report Provenance and Traceability")

    # ---- Maintenance / Rehab design sections (for backward compatibility) ----
    maint_ctx = _maint_ctx(ctx)
    if overlay:
        doc.add_page_break()
        add_heading(doc, "MAINTENANCE / REHABILITATION", level=1, align=WD_ALIGN_PARAGRAPH.CENTER)
        write_overlay_section(doc, maint_ctx, overlay)
        included.append("Overlay Design (BBD)")
    if cold_mix:
        if not overlay:
            doc.add_page_break()
            add_heading(doc, "MAINTENANCE / REHABILITATION", level=1, align=WD_ALIGN_PARAGRAPH.CENTER)
        write_cold_mix_section(doc, maint_ctx, cold_mix)
        included.append("Cold Mix Design")
    if micro:
        if not (overlay or cold_mix):
            doc.add_page_break()
            add_heading(doc, "MAINTENANCE / REHABILITATION", level=1, align=WD_ALIGN_PARAGRAPH.CENTER)
        write_micro_surfacing_section(doc, maint_ctx, micro)
        included.append("Micro-Surfacing Design")

    # ---- Condition Survey ----
    if condition:
        doc.add_page_break()
        cs_ctx = ConditionReportContext(
            project_title=ctx.project_title, work_name=ctx.work_name,
            work_order_no=ctx.work_order_no, work_order_date=ctx.work_order_date,
            client=ctx.client, agency=ctx.agency, submitted_by=ctx.submitted_by,
            lab_name=ctx.lab_name, report_date=ctx.report_date,
        )
        write_condition_section(doc, cs_ctx, condition, include_header=True)
        included.append("Pavement Condition Survey")

    # ---- Rehab Synthesis ----
    if rehab_synthesis is not None:
        doc.add_page_break()
        rh_ctx = RehabReportContext(
            project_title=ctx.project_title, work_name=ctx.work_name,
            work_order_no=ctx.work_order_no, work_order_date=ctx.work_order_date,
            client=ctx.client, agency=ctx.agency, submitted_by=ctx.submitted_by,
            lab_name=ctx.lab_name, report_date=ctx.report_date,
        )
        write_rehab_section(doc, rh_ctx, rehab_synthesis, include_header=True)
        included.append("Rehabilitation Recommendations")

    # ---- IITPAVE Schema Diagnostics History ----
    if schema_history_review.items:
        doc.add_page_break()
        schema_history_summary = write_iitpave_schema_history_section(
            doc, _schema_history_ctx(ctx), schema_history_review,
            include_header=True, selection=schema_history_review.selection,
            report_path=out_path
        )
        included.append("IITPAVE Schema Diagnostics History")
    elif schema_history_review.selection and schema_history_review.selection.available_history_ids:
        schema_history_summary = build_iitpave_schema_history_report_summary(
            schema_history_review, selection=schema_history_review.selection,
            report_path=out_path
        )

    # ---- Assumptions ----
    doc.add_page_break()
    write_assumptions_section(doc, p, structural, stabilized, tr_row)
    included.append("Assumptions Sheet")

    # ---- Limitations ----
    doc.add_page_break()
    write_limitations_section(doc)
    included.append("Limitations Sheet")

    # ---- Checklist ----
    doc.add_page_break()
    write_engineer_checklist_section(doc, p)
    included.append("Engineer Review Checklist")

    # ---- Signature ----
    doc.add_page_break()
    write_signature_placeholders(doc)
    included.append("Signature & Seal Placeholders")

    doc.save(out_path)
    if schema_history_summary is not None and hasattr(db, "save_iitpave_schema_history_selection_audit"):
        db.save_iitpave_schema_history_selection_audit(
            project_id=project_id, report_path=str(out_path), summary=schema_history_summary
        )
    if hasattr(db, "save_report_revision_snapshot"):
        db.save_report_revision_snapshot(
            project_id=project_id,
            snapshot=ReportRevisionSnapshot.from_provenance(
                provenance_summary, report_identifier=f"combined_report:{project_id}:{out_path.name}"
            )
        )
    return out_path, included


def add_traceability_block(doc, title: str, inputs: list[tuple[str, str]], outputs: list[tuple[str, str]], reference: str) -> None:
    """Add a structured calculation traceability section to the document."""
    add_heading(doc, f"Calculation Traceability — {title}", level=3)
    rows = []
    for name, val in inputs:
        rows.append(["Input Source Data", name, str(val)])
    for name, val in outputs:
        rows.append(["Calculation Result", name, str(val)])
    rows.append(["Reference Standard", "Standard Citation", reference])
    add_table(doc, ["Traceability Parameter", "Property Name", "Value"], rows)
    add_p(doc, "")


def write_executive_summary_section(doc, p, structural, stabilized, mech_val, db=None) -> None:
    add_heading(doc, "EXECUTIVE SUMMARY", level=1)
    
    # 1. Fetch Design Audit Score (fail-safe)
    audit_score = "N/A"
    if db is not None:
        try:
            from app.engineering.design_audit import run_project_audit
            audit = run_project_audit(p.id, db)
            audit_score = f"{audit.score}/100 ({audit.readiness_status})"
        except Exception:
            pass
            
    # 2. Fetch Estimated Cost (fail-safe)
    est_cost = "N/A"
    if db is not None:
        try:
            from app.engineering.boq_engine import generate_boq
            boq = generate_boq(p.id, db)
            if boq.get("available") and boq.get("show_rupees"):
                est_cost = boq.get("total_project_cost_formatted") or f"Rs. {boq.get('total_project_cost', 0):,.2f}"
            elif boq.get("available"):
                est_cost = f"Cost Index: {boq.get('cost_index', 'N/A')}"
        except Exception:
            pass

    road_type = p.highway_type or p.road_category or "N/A"
    traffic_msa = f"{structural.design_msa:.2f} MSA" if structural else "N/A"
    subgrade_cbr = f"{p.subgrade_cbr:.1f} %" if p.subgrade_cbr else "N/A"
    selected_opt = p.selected_design_option or "Option A (Conventional Flexible)"
    
    # Table Summary
    summary_data = [
        ["Road Type / Category", road_type],
        ["Design Traffic", traffic_msa],
        ["Subgrade CBR", subgrade_cbr],
        ["Selected Pavement Option", selected_opt],
        ["Engineering Audit Score", audit_score],
        ["Estimated Cost (Preliminary Estimate)", est_cost]
    ]
    
    add_p(doc, "The key pavement design parameters and project outcomes are summarized in the table below:")
    add_table(doc, ["Pavement Metric", "Design Value / Outcome"], summary_data)
    
    add_p(doc, "\n")
    summary_para = (
        f"This professional pavement design report presents the mechanistic and empirical design parameters "
        f"established for the work '{p.work_name or 'Untitled work'}'. The evaluation incorporates design traffic analysis, "
        f"subgrade pavement layer profiling, and mechanistic safety screening. "
    )
    if structural:
        summary_para += (
            f"A conventional flexible pavement design has been developed for a design traffic of {structural.design_msa or 0:.2f} MSA, "
            f"resulting in a total pavement thickness of {structural.total_pavement_thickness_mm or 0:.0f} mm. "
        )
    if stabilized:
        summary_para += "A cement-stabilized design (CTB/CTS) has been analyzed as an alternative to achieve structural thickness optimization. "
    
    if mech_val and not mech_val.refused:
        if "Demo verification example only" in (mech_val.notes or ""):
            summary_para += f"Mechanistic verification has been successfully conducted (Demo verification example only — not actual IITPAVE execution)."
        else:
            summary_para += f"Mechanistic verification has been successfully conducted using IITPAVE under Mechanistic Verified Mode."
    else:
        summary_para += f"The design calculations have been prepared under Decision Support Mode guidelines."
        
    add_p(doc, summary_para)
    
    # Disclaimer
    add_p(
        doc,
        "Disclaimer: This Engineering Intelligence Review and report is a decision-support screening tool. "
        "Final design acceptance for construction field execution remains subject to independent review "
        "and sign-off by a qualified pavement engineer.",
        italic=True,
        size=9
    )


def write_assumptions_section(doc, p, structural, stabilized, ta_row=None) -> None:
    add_heading(doc, "ASSUMPTIONS SHEET", level=1)
    add_p(doc, "The design is based on the following standard engineering assumptions and presets:")
    
    # Let's extract design traffic if available
    growth = "7.5"
    if ta_row and ta_row.inputs_json:
        try:
            ta_inp = json.loads(ta_row.inputs_json)
            growth = str(ta_inp.get("growth_rate_pct", "7.5"))
        except Exception:
            pass
            
    rows = [
        ["Poisson's Ratio (Bituminous Layer)", "0.35"],
        ["Poisson's Ratio (Granular Base/Sub-base)", "0.35"],
        ["Poisson's Ratio (Subgrade Soil)", "0.35"],
        ["Poisson's Ratio (Cement Treated Base - CTB)", "0.25"],
        ["Poisson's Ratio (Cement Treated Sub-grade/Sub-base - CTS)", "0.25"],
        ["Design Traffic Growth Rate", f"{growth} %"],
        ["Subgrade Soil Behavior Modulus Relation", "IRC:37-2018 Formulae (MR = 17.6 * CBR^0.64 for CBR > 5)"]
    ]
    add_table(doc, ["Parameter Description", "Assumed / Preset Value"], rows)


def write_limitations_section(doc) -> None:
    add_heading(doc, "LIMITATIONS OF THE REPORT", level=1)
    add_p(
        doc,
        "1. This pavement design report is prepared as a decision-support guide for the client and the "
        "design engineers. It does not constitute official government approval or official regulatory stamp."
    )
    add_p(
        doc,
        "2. The layer thicknesses, material properties, and traffic projections are calculated using subgrade soils "
        "and traffic data inputs supplied by the client. Any variations in site conditions, soil properties, "
        "or traffic loads must be verified in the field and the design updated accordingly."
    )
    add_p(
        doc,
        "3. Final execution of the pavement construction works requires a detailed site-specific verification, "
        "structural validation, and formal sign-off/approval by a qualified pavement engineer."
    )


def write_engineer_checklist_section(doc, p) -> None:
    add_heading(doc, "ENGINEER REVIEW CHECKLIST", level=1)
    add_p(doc, "Review checklists completed by the certifying pavement engineer:")
    
    checklist_dict = {}
    if p.checklist_json:
        try:
            checklist_dict = json.loads(p.checklist_json)
        except Exception:
            pass
            
    rows = [
        ["Review Workflow Status", p.review_status or "Draft"],
        ["Design Review Checklist Completed", "YES" if checklist_dict.get("design_review") else "NO"],
        ["Input Verification Completed", "YES" if checklist_dict.get("input_verification") else "NO"],
        ["Traffic Assumptions Verified", "YES" if checklist_dict.get("traffic_verification") else "NO"],
        ["Material Assumptions Verified", "YES" if checklist_dict.get("material_verification") else "NO"],
        ["IITPAVE Verification Status", checklist_dict.get("iitpave_verification") or "Not Verified"],
        ["Final Reviewer Notes / Remarks", checklist_dict.get("reviewer_notes") or "No remarks added."]
    ]
    add_table(doc, ["Verification Checklist Item", "Status / Remarks"], rows)


def write_signature_placeholders(doc) -> None:
    add_heading(doc, "ENGINEERING SIGN-OFF AND SEAL", level=2)
    add_p(doc, "")
    add_p(doc, "")
    add_p(doc, "  ___________________________________________", bold=True)
    add_p(doc, "  Signature of Reviewing Engineer")
    add_p(doc, "")
    add_p(doc, "  Date: _____________________________________")
    add_p(doc, "")
    add_p(doc, "  Seal / Registration No: ____________________")


def write_expert_design_audit_section(doc, audit_result) -> None:
    try:
        if not audit_result:
            return
        
        add_heading(doc, "ENGINEERING VALIDATION & DESIGN REVIEW SUMMARY", level=1)
        
        # Summary details
        rec = getattr(audit_result, "final_recommendation", "NOT READY FOR SUBMISSION")
        ts = getattr(audit_result, "timestamp", "")
        summary_info = [
            ("Engineering Score", f"{getattr(audit_result, 'score', 0)} / 100"),
            ("Risk Level", str(getattr(audit_result, "risk_level", "UNKNOWN"))),
            ("Readiness Status", str(getattr(audit_result, "readiness_status", "UNKNOWN"))),
            ("Submission Recommendation", str(rec)),
            ("Validation Timestamp", str(ts) if ts else "N/A")
        ]
        add_kv_table(doc, summary_info)
        add_p(doc, "")

        # 1. Engineering Score Cards breakdown
        if hasattr(audit_result, "completeness_score"):
            add_heading(doc, "Engineering Score Breakdown", level=2)
            score_rows = [
                ["Completeness Score", f"{getattr(audit_result, 'completeness_score', 0)}%", getattr(audit_result, "completeness_explanation", "")],
                ["Consistency Score", f"{getattr(audit_result, 'consistency_score', 0)}%", getattr(audit_result, "consistency_explanation", "")],
                ["Mechanistic Score", f"{getattr(audit_result, 'mechanistic_score', 0)}%", getattr(audit_result, "mechanistic_explanation", "")],
                ["Documentation Score", f"{getattr(audit_result, 'documentation_score', 0)}%", getattr(audit_result, "documentation_explanation", "")],
                ["Submission Score", f"{getattr(audit_result, 'submission_score', 0)}%", getattr(audit_result, "submission_explanation", "")],
            ]
            add_table(doc, ["Score Type", "Rating", "Explanation / Evaluation Details"], score_rows)
            add_p(doc, "")

        # 2. Module status
        if hasattr(audit_result, "module_statuses") and audit_result.module_statuses:
            add_heading(doc, "Module Quality Gate Status", level=2)
            mod_rows = []
            for m, st in audit_result.module_statuses.items():
                mod_rows.append([m.title(), str(st)])
            add_table(doc, ["Pavement Module", "Status"], mod_rows)
            add_p(doc, "")

        # 3. Cross-Module consistency
        if hasattr(audit_result, "consistency_checks") and audit_result.consistency_checks:
            add_heading(doc, "Cross-Module Parameter Alignment", level=2)
            cm_rows = []
            for check in audit_result.consistency_checks:
                cm_rows.append([
                    str(check.get("module")),
                    str(check.get("field")),
                    str(check.get("source_val")),
                    str(check.get("target_val")),
                    str(check.get("status"))
                ])
            add_table(doc, ["Module Pairs", "Parameter Field", "Source Value", "Target Value", "Status"], cm_rows)
            add_p(doc, "")

        # 4. Outstanding Issues
        findings = getattr(audit_result, "findings", [])
        if findings:
            add_heading(doc, "Outstanding Design Validation Issues", level=2)
            findings_rows = []
            for f in findings:
                findings_rows.append([
                    str(getattr(f, "severity", "")).upper(),
                    str(getattr(f, "module", "")).capitalize(),
                    str(getattr(f, "issue", "")),
                    str(getattr(f, "recommendation", "")),
                    str(getattr(f, "engineering_reason", ""))
                ])
            add_table(
                doc,
                ["Severity", "Module", "Issue Description", "Suggested Action", "Engineering Reason"],
                findings_rows
            )
            add_p(doc, "")
            
    except Exception as e:
        import logging
        logging.getLogger(__name__).exception("Failed to write expert design audit section: %s", e)


def write_pavement_alternative_comparison_section(doc, options: list[dict], project) -> None:
    try:
        if not options:
            return

        # Lazy import of reporting helpers if needed, but they are already in the file namespace
        add_heading(doc, "PAVEMENT ALTERNATIVE COMPARISON", level=1)
        add_p(doc, "This section presents a comparative analysis of the four design alternatives evaluated for the project:")

        # Build option comparison table
        table_rows = []
        for opt in options:
            total_thick = opt.get("total_pavement_thickness", 0.0)
            thick_str = f"{total_thick:.0f} mm" if total_thick > 0 else "—"
            table_rows.append([
                str(opt.get("option_name", "")),
                thick_str,
                str(opt.get("layers", "")),
                str(opt.get("estimated_cost_indicator", "")),
                str(opt.get("engineering_score", "")),
                str(opt.get("iitpave_status", "")),
                str(opt.get("recommendation_reason", ""))
            ])

        add_table(
            doc,
            ["Option", "Thickness", "Layers", "Approx Cost Index", "Engineering Score", "IITPAVE Status", "Recommendation"],
            table_rows
        )
        add_p(doc, "")  # blank line

        # Display selected option
        selected_opt = getattr(project, "selected_design_option", None) or "None Selected"
        add_p(doc, f"Selected Pavement Design Option: {selected_opt}", bold=True)

        # Display cost-optimized recommendation if present
        opt_d = next((o for o in options if o.get("design_type") == "Recommended Option"), None)

        if opt_d and opt_d.get("total_pavement_thickness", 0.0) > 0:
            add_p(doc, f"Consultant Recommendation Reason: {opt_d.get('recommendation_reason', '')}")

    except Exception as e:
        import logging
        logging.getLogger(__name__).exception("Failed to write pavement alternative comparison section: %s", e)


def write_cost_estimation_section(doc, project_id: int, db) -> None:
    try:
        from app.engineering.boq_engine import generate_boq
        boq_res = generate_boq(project_id, db)
        if not boq_res.get("available") or not boq_res.get("show_rupees"):
            return
            
        add_heading(doc, "PRELIMINARY COST ESTIMATE SUMMARY", level=1)
        add_p(
            doc,
            "This section presents a preliminary commercial estimate and option cost comparison "
            "for the pavement design configurations. All cost figures are based on default/sample "
            "rates or rates updated by the consultant in the Rate Manager. These estimates do "
            "not constitute a final tender or detailed project report (DPR) cost schedule, but serve "
            "to guide the alternative design selection process."
        )
        
        # Options Cost Table
        add_heading(doc, "Option Cost Comparison Summary (Preliminary Engineer Estimate / Consultant BOQ Estimate)", level=2)
        
        table_rows = []
        options_data = boq_res.get("options", {})
        for opt_key in ["Option A", "Option B", "Option C", "Option D"]:
            opt = options_data.get(opt_key, {})
            if opt.get("available"):
                thick = sum(ly.get('thickness_mm', 0.0) for ly in opt.get('layers', []))
                table_rows.append([
                    opt_key,
                    f"{thick:.0f} mm",
                    f"{opt.get('bitumen_t', 0.0):.2f} t",
                    f"{opt.get('cement_t', 0.0):.2f} t",
                    opt.get("formatted_cost", "—")
                ])
                
        if table_rows:
            add_table(
                doc,
                ['Pavement Option', 'Thickness', 'Bitumen', 'Cement', 'Preliminary Cost Estimate'],
                table_rows
            )
            
        add_p(doc, "")
        
        # Rates Table
        add_heading(doc, "Pavement Construction Unit Rates (Sample/Default SOR Rates)", level=2)
        
        rates_rows = []
        rates = boq_res.get("rates", {})
        for mat in ["BC", "DBM", "WMM", "GSB", "Bitumen", "Cement", "Aggregate"]:
            r_info = rates.get(mat, {})
            if r_info:
                rates_rows.append([
                    mat,
                    r_info.get("unit", "Tonne"),
                    f"₹{r_info.get('rate', 0.0):,.2f}",
                    "Sample/Default Rate (Needs project-specific update)"
                ])
                
        if rates_rows:
            add_table(
                doc,
                ['Material Item', 'Unit', 'Unit Rate', 'Remarks / Source'],
                rates_rows
            )
            
        add_p(doc, "")
        add_p(
            doc,
            "Note: Cement-treated base and subgrade layers (CTB/CTS) are analyzed based on their constituent "
            "cement and aggregate rates as configured in the Rate Manager. The rates must be verified locally before final project submission."
        )
        
    except Exception as e:
        import logging
        logging.getLogger(__name__).exception("Failed to write cost estimation section: %s", e)


