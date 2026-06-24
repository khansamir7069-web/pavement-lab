"""Database access façade. Single point of contact between UI and SQLite."""
from __future__ import annotations

import json
from contextlib import contextmanager
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Optional

from sqlalchemy import create_engine, func, select, text
from sqlalchemy.orm import Session, joinedload, sessionmaker

from app.config import DB_PATH
from app.core import MixDesignResult
from app.core.config_profiles import (
    ApplicationConfig,
    ConfigValidationResult,
    load_application_config,
    validate_application_config,
)

from .schema import (
    AuditLog,
    Base,
    Client,
    ConditionSurvey,
    IITPaveSchemaDiagnosticsHistory,
    IITPaveSchemaHistorySelectionAudit,
    MaintenanceDesign,
    Material,
    MaterialQuantityDesign,
    MechanisticValidation,
    MixDesign,
    Project,
    Report,
    ReportRevisionSnapshotRecord,
    StructuralDesign,
    StabilizedDesign,
    TrafficAnalysis,
    User,
)


def _to_json_safe(obj):
    """Walk a structure converting dataclasses, tuples and namedtuples into
    JSON-serialisable forms."""
    if is_dataclass(obj):
        return _to_json_safe(asdict(obj))
    if isinstance(obj, dict):
        return {k: _to_json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_to_json_safe(v) for v in obj]
    return obj


def _utc_iso() -> str:
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _json_mapping(raw: str | None) -> dict[str, Any] | None:
    if not raw:
        return None
    try:
        parsed = json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return None
    return parsed if isinstance(parsed, dict) else None


def _project_config_payload(
    cfg: ApplicationConfig,
    *,
    created_at: str,
    updated_at: str,
) -> dict[str, Any]:
    validation = validate_application_config(cfg)
    return {
        "profile": cfg.metadata.requested_profile or cfg.profile.key,
        "resolved_profile": cfg.profile.key,
        "schema_version": cfg.metadata.schema_version,
        "config_version": cfg.metadata.schema_version,
        "created_at": created_at,
        "updated_at": updated_at,
        "report_metadata_enabled": cfg.report_metadata_enabled,
        "strict_engineering_mode": cfg.strict_engineering_mode,
        "metadata": cfg.metadata.as_dict(),
        "validation": {
            "ok": validation.ok,
            "issues": [i.as_dict() for i in validation.issues],
        },
    }


def _check_not_locked(session: Session, project_id: int) -> None:
    p = session.get(Project, project_id)
    if p and p.locked:
        raise ValueError("Cannot modify a locked project.")


class Database:
    """Thin façade. Owns the engine + sessionmaker."""

    def __init__(self, path: Optional[Path] = None):
        self.path = Path(path) if path else DB_PATH
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.engine = create_engine(
            f"sqlite:///{self.path}",
            echo=False,
            future=True,
            connect_args={"check_same_thread": False},
        )
        Base.metadata.create_all(self.engine)
        self._migrate_schema()
        self._Session = sessionmaker(bind=self.engine, expire_on_commit=False)

    def _migrate_schema(self) -> None:
        """Idempotently add columns introduced after the first schema version.

        SQLite cannot drop NOT NULL via ALTER COLUMN, so legacy DBs keep the
        mix_type NOT NULL constraint and we work around it by always storing
        an empty string for 'not selected' (handled in the UI / repository).
        """
        with self.engine.begin() as conn:
            cols = {r[1] for r in conn.execute(text("PRAGMA table_info(projects)"))}
            if "modules_json" not in cols:
                conn.execute(text("ALTER TABLE projects ADD COLUMN modules_json TEXT"))
            if "config_json" not in cols:
                conn.execute(text("ALTER TABLE projects ADD COLUMN config_json TEXT"))
            if "binder_grade" not in cols:
                conn.execute(text("ALTER TABLE projects ADD COLUMN binder_grade VARCHAR(40)"))
            if "binder_properties_json" not in cols:
                conn.execute(text("ALTER TABLE projects ADD COLUMN binder_properties_json TEXT"))
            if "locked" not in cols:
                conn.execute(text("ALTER TABLE projects ADD COLUMN locked BOOLEAN DEFAULT 0"))
            if "locked_at" not in cols:
                conn.execute(text("ALTER TABLE projects ADD COLUMN locked_at TEXT"))
            if "lock_snapshot_json" not in cols:
                conn.execute(text("ALTER TABLE projects ADD COLUMN lock_snapshot_json TEXT"))
            if "review_status" not in cols:
                conn.execute(text("ALTER TABLE projects ADD COLUMN review_status VARCHAR(40) DEFAULT 'Draft'"))
            if "checklist_json" not in cols:
                conn.execute(text("ALTER TABLE projects ADD COLUMN checklist_json TEXT"))
            if "consultant" not in cols:
                conn.execute(text("ALTER TABLE projects ADD COLUMN consultant TEXT"))
            if "report_id" not in cols:
                conn.execute(text("ALTER TABLE projects ADD COLUMN report_id TEXT"))
            if "revisions_json" not in cols:
                conn.execute(text("ALTER TABLE projects ADD COLUMN revisions_json TEXT"))
            if "location" not in cols:
                conn.execute(text("ALTER TABLE projects ADD COLUMN location TEXT"))
            if "road_category" not in cols:
                conn.execute(text("ALTER TABLE projects ADD COLUMN road_category VARCHAR(100)"))
            if "highway_type" not in cols:
                conn.execute(text("ALTER TABLE projects ADD COLUMN highway_type VARCHAR(100)"))
            if "carriageway" not in cols:
                conn.execute(text("ALTER TABLE projects ADD COLUMN carriageway VARCHAR(100)"))
            if "design_standard" not in cols:
                conn.execute(text("ALTER TABLE projects ADD COLUMN design_standard VARCHAR(100)"))
            if "design_life" not in cols:
                conn.execute(text("ALTER TABLE projects ADD COLUMN design_life INTEGER"))
            if "checked_by" not in cols:
                conn.execute(text("ALTER TABLE projects ADD COLUMN checked_by VARCHAR(200)"))
            if "project_date" not in cols:
                conn.execute(text("ALTER TABLE projects ADD COLUMN project_date VARCHAR(50)"))
            if "subgrade_cbr" not in cols:
                conn.execute(text("ALTER TABLE projects ADD COLUMN subgrade_cbr FLOAT"))
            if "subgrade_mr" not in cols:
                conn.execute(text("ALTER TABLE projects ADD COLUMN subgrade_mr FLOAT"))
            if "is_legacy" not in cols:
                conn.execute(text("ALTER TABLE projects ADD COLUMN is_legacy BOOLEAN DEFAULT 0"))
                conn.execute(text("UPDATE projects SET is_legacy = 1"))

    def initialize_workflow_statuses(self, project_id: int) -> dict:
        with self.session() as s:
            p = s.get(Project, project_id)
            if not p:
                return {}
            is_legacy = bool(p.is_legacy)
            try:
                status = json.loads(p.modules_json) if p.modules_json else {}
            except json.JSONDecodeError:
                status = {}

            # 1. Project Setup
            if "project" not in status:
                status["project"] = "complete"

            # 2. Traffic Survey / MSA
            if "traffic" not in status:
                from app.db.schema import TrafficAnalysis
                has_data = s.scalars(select(TrafficAnalysis).where(TrafficAnalysis.project_id == project_id)).first() is not None
                status["traffic"] = "complete" if has_data else ("needs_review" if is_legacy else "empty")

            # 3. Subgrade / CBR
            if "subgrade" not in status:
                has_data = p.subgrade_cbr is not None or p.subgrade_mr is not None
                status["subgrade"] = "complete" if has_data else ("needs_review" if is_legacy else "empty")

            # 4. Pavement Structural Design
            if "structural" not in status:
                from app.db.schema import StructuralDesign
                has_data = s.scalars(select(StructuralDesign).where(StructuralDesign.project_id == project_id)).first() is not None
                status["structural"] = "complete" if has_data else ("needs_review" if is_legacy else "empty")

            # 5. Alternative Selection
            if "stabilized" not in status:
                from app.db.schema import StabilizedDesign
                has_data = s.scalars(select(StabilizedDesign).where(StabilizedDesign.project_id == project_id)).first() is not None
                status["stabilized"] = "complete" if has_data else ("needs_review" if is_legacy else "empty")

            # 6. IITPAVE Verification
            if "iitpave_status" not in status:
                from app.db.schema import MechanisticValidation
                has_data = s.scalars(select(MechanisticValidation).where(MechanisticValidation.project_id == project_id)).first() is not None
                status["iitpave_status"] = "complete" if has_data else ("needs_review" if is_legacy else "empty")

            # 7. Mix Design
            if "mix_design" not in status:
                from app.db.schema import MixDesign
                has_data = s.scalars(select(MixDesign).where(MixDesign.project_id == project_id)).first() is not None
                status["mix_design"] = "complete" if has_data else ("needs_review" if is_legacy else "empty")

            # 8. BOQ
            if "material_qty" not in status:
                from app.db.schema import MaterialQuantityDesign
                has_data = s.scalars(select(MaterialQuantityDesign).where(MaterialQuantityDesign.project_id == project_id)).first() is not None
                status["material_qty"] = "complete" if has_data else ("needs_review" if is_legacy else "empty")

            # 9. Engineering Review
            if "engineering_review" not in status:
                has_data = p.review_status in ("Reviewed", "Approved for Submission") or p.checklist_json is not None
                status["engineering_review"] = "complete" if has_data else ("needs_review" if is_legacy else "empty")

            # 10. Submission
            if "submission" not in status:
                has_data = bool(p.locked)
                status["submission"] = "complete" if has_data else ("needs_review" if is_legacy else "empty")

            p.modules_json = json.dumps(status)
            s.flush()
            return status

    @contextmanager
    def session(self) -> Session:
        s = self._Session()
        try:
            yield s
            s.commit()
        except Exception:
            s.rollback()
            raise
        finally:
            s.close()

    # ---- Clients --------------------------------------------------------
    def list_clients(self) -> list[Client]:
        with self.session() as s:
            return list(s.scalars(select(Client).order_by(Client.name)))

    def upsert_client(self, *, name: str, address: str = "", contact: str = "") -> Client:
        with self.session() as s:
            existing = s.scalars(select(Client).where(Client.name == name)).first()
            if existing:
                existing.address = address or existing.address
                existing.contact = contact or existing.contact
                s.flush()
                return existing
            c = Client(name=name, address=address, contact=contact)
            s.add(c)
            s.flush()
            return c

    # ---- Projects -------------------------------------------------------
    def list_projects(self) -> list[Project]:
        with self.session() as s:
            stmt = (
                select(Project)
                .options(joinedload(Project.client))
                .order_by(Project.updated_at.desc())
            )
            return list(s.scalars(stmt))

    def get_project(self, project_id: int) -> Project | None:
        with self.session() as s:
            stmt = (
                select(Project)
                .options(joinedload(Project.client))
                .where(Project.id == project_id)
            )
            return s.scalars(stmt).first()

    def create_project(self, **kwargs) -> Project:
        kwargs.setdefault("mix_type", "")   # legacy NOT NULL safety
        with self.session() as s:
            p = Project(**kwargs)
            s.add(p)
            s.flush()
            return p

    def update_project(self, project_id: int, **kwargs) -> Project | None:
        with self.session() as s:
            p = s.get(Project, project_id)
            if not p:
                return None
            if p.locked:
                allowed = {"locked", "locked_at", "lock_snapshot_json", "review_status", "checklist_json", "revisions_json", "consultant", "report_id"}
                if not set(kwargs.keys()).issubset(allowed):
                    raise ValueError("Cannot modify a locked project.")
            for k, v in kwargs.items():
                setattr(p, k, v)
            s.flush()
            return p

    def delete_project(self, project_id: int) -> bool:
        with self.session() as s:
            p = s.get(Project, project_id)
            if not p:
                return False
            s.delete(p)
        # Best-effort filesystem cleanup of the project's image evidence
        # tree. Lazy import to avoid hard-coupling the DB layer to the
        # condition-survey pipeline at module load. Outcome does not
        # affect the return value — DB delete is the contract.
        try:
            from app.core.condition_survey.image_pipeline import (
                delete_project_images,
            )
            delete_project_images(project_id)
        except Exception:
            pass
        return True

    def set_module_status(self, project_id: int, module: str, status: str) -> None:
        """Update modules_json: {module_key: 'complete' | 'in_progress' | 'empty'}."""
        with self.session() as s:
            _check_not_locked(s, project_id)
            p = s.get(Project, project_id)
            if not p:
                return
            try:
                mods = json.loads(p.modules_json) if p.modules_json else {}
            except json.JSONDecodeError:
                mods = {}
            mods[module] = status
            p.modules_json = json.dumps(mods)

    def get_module_status(self, project_id: int) -> dict:
        with self.session() as s:
            p = s.get(Project, project_id)
            if not p:
                return {}
            try:
                mods = json.loads(p.modules_json) if p.modules_json else {}
            except json.JSONDecodeError:
                mods = {}
            stages = ["project", "traffic", "subgrade", "structural", "stabilized", "iitpave_status", "mix_design", "material_qty", "engineering_review", "submission"]
            if not mods or not all(stage in mods for stage in stages):
                s.rollback()
                return self.initialize_workflow_statuses(project_id)
            return mods

    def attach_project_config(
        self,
        project_id: int,
        *,
        profile_key: str | None = None,
        config: ApplicationConfig | None = None,
    ) -> ApplicationConfig | None:
        """Persist project-level workflow/profile configuration metadata.

        The stored payload is JSON-only and intentionally contains no
        engineering calculation switches. Unknown profiles are resolved
        through the central config helpers, which preserve fallback warning
        metadata for auditability.
        """
        source = f"project:{project_id}"
        cfg = config or load_application_config(
            {"profile": profile_key or ""},
            source=source,
        )
        with self.session() as s:
            _check_not_locked(s, project_id)
            p = s.get(Project, project_id)
            if not p:
                return None
            existing = _json_mapping(p.config_json)
            now = _utc_iso()
            created_at = (
                existing.get("created_at")
                if existing and isinstance(existing.get("created_at"), str)
                else now
            )
            p.config_json = json.dumps(
                _project_config_payload(
                    cfg,
                    created_at=created_at,
                    updated_at=now,
                ),
                sort_keys=True,
            )
            s.flush()
            return cfg

    def load_project_config(self, project_id: int) -> ApplicationConfig:
        """Return a resolved config for a project, defaulting safely.

        Existing projects created before Phase 19 have ``config_json`` as
        NULL; those load as the default profile without warning. Malformed
        JSON payloads fall back to default with warning metadata.
        """
        source = f"project:{project_id}"
        with self.session() as s:
            p = s.get(Project, project_id)
            raw = p.config_json if p else None
        if not raw:
            return load_application_config(None, source=source)
        try:
            payload = json.loads(raw)
        except (TypeError, json.JSONDecodeError):
            payload = "malformed-project-config"
        return load_application_config(payload, source=source)

    def validate_project_config(self, project_id: int) -> ConfigValidationResult:
        return validate_application_config(self.load_project_config(project_id))

    # ---- Materials ------------------------------------------------------
    def list_materials(self) -> list[Material]:
        with self.session() as s:
            return list(s.scalars(select(Material).order_by(Material.name)))

    def upsert_material(self, *, name: str, type: str = "", source: str = "",
                        notes: str = "") -> Material:
        with self.session() as s:
            existing = s.scalars(select(Material).where(Material.name == name)).first()
            if existing:
                if type: existing.type = type
                if source: existing.source = source
                if notes: existing.notes = notes
                s.flush()
                return existing
            m = Material(name=name, type=type, source=source, notes=notes)
            s.add(m)
            s.flush()
            return m

    # ---- Mix designs ----------------------------------------------------
    def save_mix_design(
        self,
        *,
        project_id: int,
        inputs_payload: dict,
        result: MixDesignResult,
    ) -> MixDesign:
        with self.session() as s:
            _check_not_locked(s, project_id)
            md = MixDesign(
                project_id=project_id,
                gradation_json=json.dumps(_to_json_safe(inputs_payload.get("gradation"))),
                spgr_json=json.dumps(_to_json_safe(inputs_payload.get("spgr"))),
                gmb_json=json.dumps(_to_json_safe(inputs_payload.get("gmb"))),
                gmm_json=json.dumps(_to_json_safe(inputs_payload.get("gmm"))),
                stability_flow_json=json.dumps(_to_json_safe(inputs_payload.get("stability_flow"))),
                materials_json=json.dumps(inputs_payload.get("materials", {})),
                gsb=result.bulk_sg_blend,
                gb=result.bitumen_sg,
                obc_pct=result.obc.obc_pct,
                gmb_at_obc=result.obc.gmb_at_obc,
                gmm_at_obc=result.obc.gmm_at_obc,
                stability_at_obc_kn=result.obc.stability_at_obc_kn,
                flow_at_obc_mm=result.obc.flow_at_obc_mm,
                vma_at_obc_pct=result.obc.vma_at_obc_pct,
                vfb_at_obc_pct=result.obc.vfb_at_obc_pct,
                air_voids_at_obc_pct=result.obc.air_voids_at_obc_pct,
                compliance_pass=result.compliance.overall_pass,
                summary_json=json.dumps(_to_json_safe(result.summary)),
            )
            s.add(md)
            s.flush()
            return md

    def latest_mix_design(self, project_id: int) -> MixDesign | None:
        with self.session() as s:
            stmt = (
                select(MixDesign)
                .where(MixDesign.project_id == project_id)
                .order_by(MixDesign.computed_at.desc())
                .limit(1)
            )
            return s.scalars(stmt).first()

    # ---- Structural designs --------------------------------------------
    def save_structural_design(self, *, project_id: int, result) -> StructuralDesign:
        """Persist a Phase-4 StructuralResult.  ``result`` is core.StructuralResult."""
        inputs_dict = _to_json_safe(result.inputs)
        comp_dict = _to_json_safe(result.composition)
        with self.session() as s:
            _check_not_locked(s, project_id)
            sd = StructuralDesign(
                project_id=project_id,
                inputs_json=json.dumps(inputs_dict),
                design_msa=result.design_msa,
                growth_factor=result.growth_factor,
                subgrade_mr_mpa=result.subgrade_mr_mpa,
                total_pavement_thickness_mm=result.total_pavement_thickness_mm,
                composition_json=json.dumps(comp_dict),
                notes=result.notes,
            )
            s.add(sd); s.flush()
            return sd

    def latest_structural_design(self, project_id: int) -> StructuralDesign | None:
        with self.session() as s:
            stmt = (
                select(StructuralDesign)
                .where(StructuralDesign.project_id == project_id)
                .order_by(StructuralDesign.computed_at.desc())
                .limit(1)
            )
            return s.scalars(stmt).first()

    # ---- Stabilized designs ---------------------------------------------
    def save_stabilized_design(self, *, project_id: int, result) -> StabilizedDesign:
        inputs_dict = _to_json_safe(result.inputs)
        result_dict = _to_json_safe(result)
        with self.session() as s:
            _check_not_locked(s, project_id)
            sd = StabilizedDesign(
                project_id=project_id,
                inputs_json=json.dumps(inputs_dict),
                results_json=json.dumps(result_dict),
                notes=result.inputs.notes,
            )
            s.add(sd); s.flush()
            return sd

    def latest_stabilized_design(self, project_id: int) -> StabilizedDesign | None:
        with self.session() as s:
            stmt = (
                select(StabilizedDesign)
                .where(StabilizedDesign.project_id == project_id)
                .order_by(StabilizedDesign.computed_at.desc())
                .limit(1)
            )
            return s.scalars(stmt).first()

    # ---- Maintenance designs -------------------------------------------
    def save_maintenance_design(
        self, *, project_id: int, sub_module: str, result
    ) -> MaintenanceDesign:
        """Persist one Phase-5 maintenance sub-module result.

        ``sub_module`` ∈ {"overlay", "cold_mix", "micro_surfacing"}.
        ``result`` is the corresponding dataclass instance — its ``inputs``
        attribute is serialised separately for clarity.
        """
        inputs_dict = _to_json_safe(getattr(result, "inputs", None))
        # Result without the inputs attribute, to avoid duplication in storage.
        result_dict = _to_json_safe(result)
        if isinstance(result_dict, dict):
            result_dict.pop("inputs", None)
        with self.session() as s:
            _check_not_locked(s, project_id)
            row = MaintenanceDesign(
                project_id=project_id,
                sub_module=sub_module,
                inputs_json=json.dumps(inputs_dict),
                results_json=json.dumps(result_dict),
                notes=getattr(result, "notes", "") or "",
            )
            s.add(row); s.flush()
            return row

    def latest_maintenance_design(
        self, project_id: int, sub_module: str | None = None
    ) -> MaintenanceDesign | None:
        """Return the most recent maintenance row for the project.

        If ``sub_module`` is given, restrict to that sub-module; otherwise
        return the most recent row across all three sub-modules.
        """
        with self.session() as s:
            stmt = (
                select(MaintenanceDesign)
                .where(MaintenanceDesign.project_id == project_id)
                .order_by(MaintenanceDesign.computed_at.desc())
                .limit(1)
            )
            if sub_module:
                stmt = (
                    select(MaintenanceDesign)
                    .where(MaintenanceDesign.project_id == project_id)
                    .where(MaintenanceDesign.sub_module == sub_module)
                    .order_by(MaintenanceDesign.computed_at.desc())
                    .limit(1)
                )
            return s.scalars(stmt).first()

    # ---- Material quantities (Phase 7) ---------------------------------
    def save_material_quantity(
        self, *, project_id: int, result
    ) -> MaterialQuantityDesign:
        inputs_dict = _to_json_safe(getattr(result, "inputs", None))
        result_dict = _to_json_safe(result)
        if isinstance(result_dict, dict):
            result_dict.pop("inputs", None)
        with self.session() as s:
            _check_not_locked(s, project_id)
            row = MaterialQuantityDesign(
                project_id=project_id,
                inputs_json=json.dumps(inputs_dict),
                results_json=json.dumps(result_dict),
                total_layer_tonnage_t=getattr(result, "total_layer_tonnage_t", 0.0),
                total_binder_tonnage_t=getattr(result, "total_binder_tonnage_t", 0.0),
                notes=getattr(result, "notes", "") or "",
            )
            s.add(row); s.flush()
            return row

    def latest_material_quantity(
        self, project_id: int
    ) -> MaterialQuantityDesign | None:
        with self.session() as s:
            stmt = (
                select(MaterialQuantityDesign)
                .where(MaterialQuantityDesign.project_id == project_id)
                .order_by(MaterialQuantityDesign.computed_at.desc())
                .limit(1)
            )
            return s.scalars(stmt).first()

    # ---- Traffic analyses (Phase 8) ------------------------------------
    def save_traffic_analysis(
        self, *, project_id: int, result
    ) -> TrafficAnalysis:
        inputs_dict = _to_json_safe(getattr(result, "inputs", None))
        result_dict = _to_json_safe(result)
        if isinstance(result_dict, dict):
            result_dict.pop("inputs", None)
        with self.session() as s:
            _check_not_locked(s, project_id)
            row = TrafficAnalysis(
                project_id=project_id,
                inputs_json=json.dumps(inputs_dict),
                results_json=json.dumps(result_dict),
                design_msa=getattr(result, "design_msa", 0.0),
                aashto_esal=getattr(result, "aashto_esal", 0.0),
                traffic_category=getattr(result, "traffic_category", "") or "",
                notes=getattr(result, "notes", "") or "",
            )
            s.add(row); s.flush()
            return row

    def latest_traffic_analysis(self, project_id: int) -> TrafficAnalysis | None:
        with self.session() as s:
            stmt = (
                select(TrafficAnalysis)
                .where(TrafficAnalysis.project_id == project_id)
                .order_by(TrafficAnalysis.computed_at.desc())
                .limit(1)
            )
            return s.scalars(stmt).first()

    # ---- Condition surveys (Phase 10) ----------------------------------
    def save_condition_survey(
        self, *, project_id: int, result
    ) -> ConditionSurvey:
        inputs_dict = _to_json_safe(getattr(result, "inputs", None))
        result_dict = _to_json_safe(result)
        if isinstance(result_dict, dict):
            result_dict.pop("inputs", None)
        with self.session() as s:
            _check_not_locked(s, project_id)
            row = ConditionSurvey(
                project_id=project_id,
                inputs_json=json.dumps(inputs_dict),
                results_json=json.dumps(result_dict),
                pci_score=float(getattr(result, "pci_score", 0.0)),
                condition_category=getattr(result, "condition_category", "") or "",
                notes=getattr(result, "notes", "") or "",
            )
            s.add(row); s.flush()
            return row

    def latest_condition_survey(self, project_id: int) -> ConditionSurvey | None:
        with self.session() as s:
            stmt = (
                select(ConditionSurvey)
                .where(ConditionSurvey.project_id == project_id)
                .order_by(ConditionSurvey.computed_at.desc())
                .limit(1)
            )
            return s.scalars(stmt).first()

    # ---- Mechanistic validation (Phase 15 P4) --------------------------
    def save_mechanistic_validation(
        self, *, project_id: int, summary, inputs=None,
    ) -> MechanisticValidation:
        """Persist a Phase-14 ``MechanisticValidationSummary``.

        ``inputs`` is optional — when supplied it is serialised
        alongside the summary so the report layer can reproduce the
        exact validation that was run. Cascade-on-project-delete is
        wired via the ORM relationship; no extra cleanup needed.
        """
        summary_dict = _to_json_safe(summary)
        inputs_dict = _to_json_safe(inputs) if inputs is not None else None
        with self.session() as s:
            _check_not_locked(s, project_id)
            row = MechanisticValidation(
                project_id=project_id,
                inputs_json=json.dumps(inputs_dict) if inputs_dict is not None else None,
                summary_json=json.dumps(summary_dict),
                refused=bool(getattr(summary, "refused", False)),
                is_placeholder=bool(getattr(summary, "is_placeholder", True)),
                fatigue_verdict=getattr(summary.fatigue, "verdict", None),
                rutting_verdict=getattr(summary.rutting, "verdict", None),
                fatigue_life_msa=getattr(summary.fatigue, "cumulative_life_msa", None),
                rutting_life_msa=getattr(summary.rutting, "cumulative_life_msa", None),
                design_msa=float(getattr(summary.fatigue, "design_msa", 0.0)),
                refused_reason=getattr(summary, "refused_reason", "") or "",
                notes=getattr(summary, "notes", "") or "",
            )
            s.add(row); s.flush()
            return row

    def latest_mechanistic_validation(
        self, project_id: int,
    ) -> MechanisticValidation | None:
        with self.session() as s:
            stmt = (
                select(MechanisticValidation)
                .where(MechanisticValidation.project_id == project_id)
                .order_by(MechanisticValidation.computed_at.desc())
                .limit(1)
            )
            return s.scalars(stmt).first()

    # ---- IITPAVE schema diagnostics history (Phase 33) ----------------
    def save_iitpave_schema_diagnostics(
        self,
        *,
        project_id: int,
        result,
    ) -> IITPaveSchemaDiagnosticsHistory:
        """Persist an audit-only IITPAVE schema diagnostics workflow result."""
        summary_dict = _to_json_safe(
            result.as_dict() if hasattr(result, "as_dict") else result
        )
        manifest = getattr(result, "manifest", None)
        with self.session() as s:
            row = IITPaveSchemaDiagnosticsHistory(
                project_id=project_id,
                fixture_dir=getattr(result, "fixture_dir", "") or "",
                report_path=getattr(result, "report_path", "") or "",
                workflow_status=getattr(result, "status", "") or "",
                manifest_status=getattr(manifest, "status", "") or "",
                parser_audit_ready=bool(getattr(manifest, "parser_audit_ready", False)),
                engineering_calculations_allowed=bool(
                    getattr(result, "engineering_calculations_allowed", False)
                ),
                total_fixture_count=int(getattr(manifest, "total_fixture_count", 0) or 0),
                verified_fixture_count=int(getattr(manifest, "verified_fixture_count", 0) or 0),
                mapped_schema_count=int(getattr(manifest, "mapped_schema_count", 0) or 0),
                blocked_schema_count=int(getattr(manifest, "blocked_schema_count", 0) or 0),
                unknown_schema_count=int(getattr(manifest, "unknown_schema_count", 0) or 0),
                unsupported_schema_count=int(
                    getattr(manifest, "unsupported_schema_count", 0) or 0
                ),
                summary_json=json.dumps(summary_dict),
                operator_message=getattr(result, "operator_message", "") or "",
            )
            s.add(row)
            s.flush()
            return row

    def latest_iitpave_schema_diagnostics(
        self, project_id: int,
    ) -> IITPaveSchemaDiagnosticsHistory | None:
        with self.session() as s:
            stmt = (
                select(IITPaveSchemaDiagnosticsHistory)
                .where(IITPaveSchemaDiagnosticsHistory.project_id == project_id)
                .order_by(
                    IITPaveSchemaDiagnosticsHistory.generated_at.desc(),
                    IITPaveSchemaDiagnosticsHistory.id.desc(),
                )
                .limit(1)
            )
            return s.scalars(stmt).first()

    def get_iitpave_schema_diagnostics(
        self,
        *,
        project_id: int,
        history_id: int,
    ) -> IITPaveSchemaDiagnosticsHistory | None:
        with self.session() as s:
            stmt = (
                select(IITPaveSchemaDiagnosticsHistory)
                .where(IITPaveSchemaDiagnosticsHistory.project_id == project_id)
                .where(IITPaveSchemaDiagnosticsHistory.id == history_id)
                .limit(1)
            )
            return s.scalars(stmt).first()

    def list_iitpave_schema_diagnostics(
        self, project_id: int,
    ) -> list[IITPaveSchemaDiagnosticsHistory]:
        with self.session() as s:
            return list(s.scalars(
                select(IITPaveSchemaDiagnosticsHistory)
                .where(IITPaveSchemaDiagnosticsHistory.project_id == project_id)
                .order_by(
                    IITPaveSchemaDiagnosticsHistory.generated_at.desc(),
                    IITPaveSchemaDiagnosticsHistory.id.desc(),
                )
            ))

    # ---- IITPAVE schema history report-selection audit (Phase 37) -----
    def save_iitpave_schema_history_selection_audit(
        self,
        *,
        project_id: int,
        report_path: str,
        summary,
    ) -> IITPaveSchemaHistorySelectionAudit | None:
        """Persist an audit-only report-time schema-history selection decision."""
        audit_trail = getattr(summary, "selection_audit_trail", None)
        if audit_trail is None:
            return None
        summary_dict = _to_json_safe(
            summary.as_dict() if hasattr(summary, "as_dict") else summary
        )
        with self.session() as s:
            row = IITPaveSchemaHistorySelectionAudit(
                project_id=project_id,
                report_path=report_path,
                decision_status=getattr(audit_trail, "decision_status", "") or "",
                available_history_ids_json=json.dumps(
                    list(getattr(audit_trail, "available_history_ids", ()) or ())
                ),
                selected_history_ids_json=json.dumps(
                    list(getattr(audit_trail, "selected_history_ids", ()) or ())
                ),
                skipped_unknown_history_ids_json=json.dumps(
                    list(getattr(audit_trail, "skipped_unknown_history_ids", ()) or ())
                ),
                included_history_count=int(
                    getattr(audit_trail, "included_history_count", 0) or 0
                ),
                diagnostic_row_count=int(
                    getattr(audit_trail, "diagnostic_row_count", 0) or 0
                ),
                engineering_calculations_allowed=bool(
                    getattr(audit_trail, "engineering_calculations_allowed", False)
                ),
                summary_json=json.dumps(summary_dict, sort_keys=True),
            )
            s.add(row)
            s.flush()
            return row

    def list_iitpave_schema_history_selection_audits(
        self, project_id: int,
    ) -> list[IITPaveSchemaHistorySelectionAudit]:
        with self.session() as s:
            return list(s.scalars(
                select(IITPaveSchemaHistorySelectionAudit)
                .where(IITPaveSchemaHistorySelectionAudit.project_id == project_id)
                .order_by(
                    IITPaveSchemaHistorySelectionAudit.generated_at.desc(),
                    IITPaveSchemaHistorySelectionAudit.id.desc(),
                )
            ))

    # ---- Report revision snapshots (Phase 40) -------------------------
    def save_report_revision_snapshot(
        self,
        *,
        project_id: int,
        snapshot,
    ) -> ReportRevisionSnapshotRecord:
        """Persist an audit-only generated-report revision snapshot."""
        with self.session() as s:
            count = s.scalar(
                select(func.count(ReportRevisionSnapshotRecord.id))
                .where(ReportRevisionSnapshotRecord.project_id == project_id)
            )
            revision_label = getattr(snapshot, "revision_label", "") or f"R{int(count or 0) + 1:03d}"
            summary_dict = _to_json_safe(
                snapshot.as_dict() if hasattr(snapshot, "as_dict") else snapshot
            )
            if isinstance(summary_dict, dict):
                summary_dict["revision_label"] = revision_label
            selection_payload = {
                "status": getattr(snapshot, "schema_history_selection_status", "") or "",
                "available_history_ids": list(
                    getattr(snapshot, "schema_history_available_ids", ()) or ()
                ),
                "selected_history_ids": list(
                    getattr(snapshot, "schema_history_selected_ids", ()) or ()
                ),
                "unknown_history_ids": list(
                    getattr(snapshot, "schema_history_unknown_ids", ()) or ()
                ),
                "included_history_count": int(
                    getattr(snapshot, "schema_history_included_count", 0) or 0
                ),
                "diagnostic_row_count": int(
                    getattr(snapshot, "schema_history_diagnostic_row_count", 0) or 0
                ),
            }
            row = ReportRevisionSnapshotRecord(
                project_id=project_id,
                report_identifier=getattr(snapshot, "report_identifier", "") or "",
                revision_label=revision_label,
                report_path=getattr(snapshot, "report_path", "") or "",
                provenance_fingerprint=getattr(
                    snapshot, "provenance_fingerprint", ""
                ) or "",
                validation_warnings_json=json.dumps(
                    list(getattr(snapshot, "validation_warnings", ()) or ())
                ),
                schema_history_selection_json=json.dumps(selection_payload, sort_keys=True),
                export_provenance_json=json.dumps(
                    list(getattr(snapshot, "export_provenance", ()) or ())
                ),
                summary_json=json.dumps(summary_dict, sort_keys=True),
                engineering_calculations_allowed=bool(
                    getattr(snapshot, "engineering_calculations_allowed", False)
                ),
            )
            s.add(row)
            s.flush()
            return row

    def list_report_revision_snapshots(
        self, project_id: int,
    ) -> list[ReportRevisionSnapshotRecord]:
        with self.session() as s:
            return list(s.scalars(
                select(ReportRevisionSnapshotRecord)
                .where(ReportRevisionSnapshotRecord.project_id == project_id)
                .order_by(
                    ReportRevisionSnapshotRecord.generated_at.desc(),
                    ReportRevisionSnapshotRecord.id.desc(),
                )
            ))

    # ---- Reports --------------------------------------------------------
    def record_report(self, *, mix_design_id: int, file_path: str,
                      file_type: str) -> Report:
        with self.session() as s:
            r = Report(mix_design_id=mix_design_id, file_path=file_path,
                       file_type=file_type)
            s.add(r)
            s.flush()
            return r

    def list_reports(self, mix_design_id: int) -> list[Report]:
        with self.session() as s:
            return list(s.scalars(
                select(Report)
                .where(Report.mix_design_id == mix_design_id)
                .order_by(Report.generated_at.desc())
            ))

    # ---- Audit ----------------------------------------------------------
    def audit(self, *, user_id: int | None, action: str, object_type: str = "",
              object_id: int | None = None, detail: str = "") -> None:
        with self.session() as s:
            s.add(AuditLog(user_id=user_id, action=action, object_type=object_type,
                           object_id=object_id, detail=detail))

    def duplicate_project(self, project_id: int) -> int:
        """Create a complete unlocked clone of the project, renaming it to 'Copy of ...'."""
        with self.session() as s:
            p = s.get(Project, project_id)
            if not p:
                raise ValueError("Project not found")
            
            cloned = Project(
                client_id=p.client_id,
                work_name=f"Copy of {p.work_name}",
                work_order_no=p.work_order_no,
                work_order_date=p.work_order_date,
                agency=p.agency,
                submitted_by=p.submitted_by,
                mix_type=p.mix_type,
                modules_json=p.modules_json,
                config_json=p.config_json,
                binder_grade=p.binder_grade,
                binder_properties_json=p.binder_properties_json,
                status=p.status,
                locked=False,
                locked_at=None,
                lock_snapshot_json=None,
                review_status="Draft",
                checklist_json=None,
                consultant=p.consultant,
                report_id=p.report_id,
                revisions_json=None,
                parent_project_id=None,
                revision_number=0
            )
            s.add(cloned)
            s.flush()
            
            self._clone_child_records(s, p, cloned)
            return cloned.id

    def create_project_revision(self, parent_id: int, engineer_note: str) -> int:
        """Create an unlocked project revision from a locked parent project."""
        with self.session() as s:
            parent = s.get(Project, parent_id)
            if not parent:
                raise ValueError("Parent project not found")
                
            try:
                revisions = json.loads(parent.revisions_json) if parent.revisions_json else []
            except Exception:
                revisions = []
                
            next_rev_num = int(parent.revision_number or 0) + 1
            rev_entry = {
                "revision_number": next_rev_num,
                "date_time": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                "engineer_note": engineer_note,
                "changed_parameters": []
            }
            revisions.append(rev_entry)
            
            cloned = Project(
                client_id=parent.client_id,
                work_name=parent.work_name,
                work_order_no=parent.work_order_no,
                work_order_date=parent.work_order_date,
                agency=parent.agency,
                submitted_by=parent.submitted_by,
                mix_type=parent.mix_type,
                modules_json=parent.modules_json,
                config_json=parent.config_json,
                binder_grade=parent.binder_grade,
                binder_properties_json=parent.binder_properties_json,
                status=parent.status,
                locked=False,
                locked_at=None,
                lock_snapshot_json=None,
                review_status="Draft",
                checklist_json=parent.checklist_json,
                consultant=parent.consultant,
                report_id=parent.report_id,
                revisions_json=json.dumps(revisions),
                parent_project_id=parent.id,
                revision_number=next_rev_num
            )
            s.add(cloned)
            s.flush()
            
            self._clone_child_records(s, parent, cloned)
            return cloned.id

    def _clone_child_records(self, session: Session, source: Project, target: Project) -> None:
        for md in source.mix_designs:
            session.add(MixDesign(
                project_id=target.id, gradation_json=md.gradation_json, spgr_json=md.spgr_json,
                gmb_json=md.gmb_json, gmm_json=md.gmm_json, stability_flow_json=md.stability_flow_json,
                materials_json=md.materials_json, gsb=md.gsb, gb=md.gb, obc_pct=md.obc_pct,
                gmb_at_obc=md.gmb_at_obc, gmm_at_obc=md.gmm_at_obc, stability_at_obc_kn=md.stability_at_obc_kn,
                flow_at_obc_mm=md.flow_at_obc_mm, vma_at_obc_pct=md.vma_at_obc_pct, vfb_at_obc_pct=md.vfb_at_obc_pct,
                air_voids_at_obc_pct=md.air_voids_at_obc_pct, compliance_pass=md.compliance_pass,
                summary_json=md.summary_json, computed_at=md.computed_at
            ))
        for sd in source.structural_designs:
            session.add(StructuralDesign(
                project_id=target.id, inputs_json=sd.inputs_json, design_msa=sd.design_msa,
                growth_factor=sd.growth_factor, subgrade_mr_mpa=sd.subgrade_mr_mpa,
                total_pavement_thickness_mm=sd.total_pavement_thickness_mm,
                composition_json=sd.composition_json, notes=sd.notes, computed_at=sd.computed_at
            ))
        for std in source.stabilized_designs:
            session.add(StabilizedDesign(
                project_id=target.id, inputs_json=std.inputs_json, results_json=std.results_json,
                notes=std.notes, computed_at=std.computed_at
            ))
        for ta in source.traffic_analyses:
            session.add(TrafficAnalysis(
                project_id=target.id, inputs_json=ta.inputs_json, results_json=ta.results_json,
                design_msa=ta.design_msa, aashto_esal=ta.aashto_esal, traffic_category=ta.traffic_category,
                notes=ta.notes, computed_at=ta.computed_at
            ))
        for md in source.maintenance_designs:
            session.add(MaintenanceDesign(
                project_id=target.id, sub_module=md.sub_module, inputs_json=md.inputs_json,
                results_json=md.results_json, notes=md.notes, computed_at=md.computed_at
            ))
        for mq in source.material_quantities:
            session.add(MaterialQuantityDesign(
                project_id=target.id, inputs_json=mq.inputs_json, results_json=mq.results_json,
                total_layer_tonnage_t=mq.total_layer_tonnage_t, total_binder_tonnage_t=mq.total_binder_tonnage_t,
                notes=mq.notes, computed_at=mq.computed_at
            ))
        for cs in source.condition_surveys:
            session.add(ConditionSurvey(
                project_id=target.id, inputs_json=cs.inputs_json, results_json=cs.results_json,
                pci_score=cs.pci_score, condition_category=cs.condition_category,
                notes=cs.notes, computed_at=cs.computed_at
            ))
        for mv in source.mechanistic_validations:
            session.add(MechanisticValidation(
                project_id=target.id, inputs_json=mv.inputs_json, summary_json=mv.summary_json,
                refused=mv.refused, is_placeholder=mv.is_placeholder, fatigue_verdict=mv.fatigue_verdict,
                rutting_verdict=mv.rutting_verdict, fatigue_life_msa=mv.fatigue_life_msa,
                rutting_life_msa=mv.rutting_life_msa, design_msa=mv.design_msa,
                refused_reason=mv.refused_reason, notes=mv.notes, computed_at=mv.computed_at
            ))
        for diag in source.iitpave_schema_diagnostics:
            session.add(IITPaveSchemaDiagnosticsHistory(
                project_id=target.id, fixture_dir=diag.fixture_dir, report_path=diag.report_path,
                workflow_status=diag.workflow_status, manifest_status=diag.manifest_status,
                parser_audit_ready=diag.parser_audit_ready, engineering_calculations_allowed=diag.engineering_calculations_allowed,
                total_fixture_count=diag.total_fixture_count, verified_fixture_count=diag.verified_fixture_count,
                mapped_schema_count=diag.mapped_schema_count, blocked_schema_count=diag.blocked_schema_count,
                unknown_schema_count=diag.unknown_schema_count, unsupported_schema_count=diag.unsupported_schema_count,
                summary_json=diag.summary_json, operator_message=diag.operator_message, generated_at=diag.generated_at
            ))
        for audit in source.iitpave_schema_history_selection_audits:
            session.add(IITPaveSchemaHistorySelectionAudit(
                project_id=target.id, report_path=audit.report_path, decision_status=audit.decision_status,
                available_history_ids_json=audit.available_history_ids_json, selected_history_ids_json=audit.selected_history_ids_json,
                skipped_unknown_history_ids_json=audit.skipped_unknown_history_ids_json, included_history_count=audit.included_history_count,
                diagnostic_row_count=audit.diagnostic_row_count, engineering_calculations_allowed=audit.engineering_calculations_allowed,
                summary_json=audit.summary_json, generated_at=audit.generated_at
            ))
        for snap in source.report_revision_snapshots:
            session.add(ReportRevisionSnapshotRecord(
                project_id=target.id, report_identifier=snap.report_identifier, revision_label=snap.revision_label,
                report_path=snap.report_path, provenance_fingerprint=snap.provenance_fingerprint,
                validation_warnings_json=snap.validation_warnings_json, schema_history_selection_json=snap.schema_history_selection_json,
                export_provenance_json=snap.export_provenance_json, summary_json=snap.summary_json,
                engineering_calculations_allowed=snap.engineering_calculations_allowed, generated_at=snap.generated_at
            ))

    def lock_project(self, project_id: int) -> None:
        from app.db.project_exchange import export_project
        with self.session() as s:
            p = s.get(Project, project_id)
            if not p:
                raise ValueError("Project not found")
            if p.locked:
                return
            snapshot = export_project(self, project_id)
            p.locked = True
            p.locked_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
            p.lock_snapshot_json = json.dumps(snapshot)
            
            if p.parent_project_id:
                parent = s.get(Project, p.parent_project_id)
                if parent:
                    diff = compute_project_diff(parent, p)
                    try:
                        revisions = json.loads(p.revisions_json) if p.revisions_json else []
                        if revisions:
                            for rev in revisions:
                                if rev.get("revision_number") == p.revision_number:
                                    rev["changed_parameters"] = diff
                                    break
                            p.revisions_json = json.dumps(revisions)
                    except Exception:
                        pass
            s.flush()

    def unlock_project(self, project_id: int) -> None:
        with self.session() as s:
            p = s.get(Project, project_id)
            if not p:
                raise ValueError("Project not found")
            p.locked = False
            p.locked_at = None
            p.lock_snapshot_json = None
            s.flush()

    def save_project_checklist(self, project_id: int, review_status: str, checklist: dict) -> None:
        with self.session() as s:
            p = s.get(Project, project_id)
            if not p:
                raise ValueError("Project not found")
            p.review_status = review_status
            p.checklist_json = json.dumps(checklist)
            s.flush()


def compute_project_diff(parent: Project, child: Project) -> list[dict]:
    """Compare traffic, structural, and stabilized design parameters between two project instances."""
    diff = []
    
    # 1. Structural Design Inputs
    parent_sd_input = {}
    if parent.structural_designs:
        sd = sorted(parent.structural_designs, key=lambda x: x.computed_at, reverse=True)[0]
        if sd.inputs_json:
            try:
                parent_sd_input = json.loads(sd.inputs_json)
            except Exception:
                pass
                
    child_sd_input = {}
    if child.structural_designs:
        sd = sorted(child.structural_designs, key=lambda x: x.computed_at, reverse=True)[0]
        if sd.inputs_json:
            try:
                child_sd_input = json.loads(sd.inputs_json)
            except Exception:
                pass
                
    keys_sd = {
        "design_life_years": "Design Life (years)",
        "initial_cvpd": "Initial Traffic (CVPD)",
        "growth_rate_pct": "Traffic Growth Rate (%)",
        "subgrade_cbr_pct": "Subgrade CBR (%)",
        "vdf": "Vehicle Damage Factor (VDF)",
        "ldf": "Lane Distribution Factor (LDF)",
    }
    for k, label in keys_sd.items():
        v1 = parent_sd_input.get(k)
        v2 = child_sd_input.get(k)
        if v1 != v2:
            diff.append({
                "param": label,
                "old": str(v1) if v1 is not None else "N/A",
                "new": str(v2) if v2 is not None else "N/A"
            })
            
    # 2. Structural Layer Thicknesses
    parent_composition = []
    if parent.structural_designs:
        sd = sorted(parent.structural_designs, key=lambda x: x.computed_at, reverse=True)[0]
        if sd.composition_json:
            try:
                val = sd.composition_json
                if isinstance(val, str):
                    val = json.loads(val)
                if isinstance(val, dict):
                    parent_composition = val.get("layers", [])
                elif isinstance(val, list):
                    parent_composition = val
            except Exception:
                pass
                
    child_composition = []
    if child.structural_designs:
        sd = sorted(child.structural_designs, key=lambda x: x.computed_at, reverse=True)[0]
        if sd.composition_json:
            try:
                val = sd.composition_json
                if isinstance(val, str):
                    val = json.loads(val)
                if isinstance(val, dict):
                    child_composition = val.get("layers", [])
                elif isinstance(val, list):
                    child_composition = val
            except Exception:
                pass
                
    for i in range(max(len(parent_composition), len(child_composition))):
        p_layer = parent_composition[i] if i < len(parent_composition) else {}
        c_layer = child_composition[i] if i < len(child_composition) else {}
        name = p_layer.get("name") or c_layer.get("name") or f"Layer {i+1}"
        
        p_thick = p_layer.get("thickness_mm")
        c_thick = c_layer.get("thickness_mm")
        if p_thick != c_thick:
            diff.append({
                "param": f"{name} Thickness (mm)",
                "old": str(p_thick) if p_thick is not None else "N/A",
                "new": str(c_thick) if c_thick is not None else "N/A"
            })
            
        p_mod = p_layer.get("modulus_mpa")
        c_mod = c_layer.get("modulus_mpa")
        if p_mod != c_mod:
            diff.append({
                "param": f"{name} Modulus (MPa)",
                "old": str(p_mod) if p_mod is not None else "N/A",
                "new": str(c_mod) if c_mod is not None else "N/A"
            })
            
    # 3. Stabilized Design Inputs
    parent_stab_input = {}
    if parent.stabilized_designs:
        std = sorted(parent.stabilized_designs, key=lambda x: x.computed_at, reverse=True)[0]
        if std.inputs_json:
            try:
                # Stabilized result is serialized. The inputs are inside `inputs_json` as a serialized dict
                parent_stab_input = json.loads(std.inputs_json)
            except Exception:
                pass
                
    child_stab_input = {}
    if child.stabilized_designs:
        std = sorted(child.stabilized_designs, key=lambda x: x.computed_at, reverse=True)[0]
        if std.inputs_json:
            try:
                child_stab_input = json.loads(std.inputs_json)
            except Exception:
                pass
                
    keys_stab = {
        "ctb_thickness_mm": "CTB Thickness (mm)",
        "ctb_modulus_mpa": "CTB Modulus (MPa)",
        "cts_thickness_mm": "CTS Thickness (mm)",
        "cts_modulus_mpa": "CTS Modulus (MPa)",
    }
    for k, label in keys_stab.items():
        v1 = parent_stab_input.get(k)
        v2 = child_stab_input.get(k)
        if v1 != v2:
            diff.append({
                "param": label,
                "old": str(v1) if v1 is not None else "N/A",
                "new": str(v2) if v2 is not None else "N/A"
            })
            
    return diff


_singleton: Database | None = None


def get_db() -> Database:
    global _singleton
    if _singleton is None:
        _singleton = Database()
    return _singleton
