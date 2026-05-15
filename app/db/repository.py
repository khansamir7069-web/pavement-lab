"""Database access façade. Single point of contact between UI and SQLite."""
from __future__ import annotations

import json
from contextlib import contextmanager
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Iterable, Optional

from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session, joinedload, sessionmaker

from app.config import DB_PATH
from app.core import MixDesignResult

from .schema import (
    AuditLog,
    Base,
    Client,
    MaintenanceDesign,
    Material,
    MaterialQuantityDesign,
    MixDesign,
    Project,
    Report,
    StructuralDesign,
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
            if "binder_grade" not in cols:
                conn.execute(text("ALTER TABLE projects ADD COLUMN binder_grade VARCHAR(40)"))
            if "binder_properties_json" not in cols:
                conn.execute(text("ALTER TABLE projects ADD COLUMN binder_properties_json TEXT"))

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
            return True

    def set_module_status(self, project_id: int, module: str, status: str) -> None:
        """Update modules_json: {module_key: 'complete' | 'in_progress' | 'empty'}."""
        with self.session() as s:
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
            if not p or not p.modules_json:
                return {}
            try:
                return json.loads(p.modules_json)
            except json.JSONDecodeError:
                return {}

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


_singleton: Database | None = None


def get_db() -> Database:
    global _singleton
    if _singleton is None:
        _singleton = Database()
    return _singleton
