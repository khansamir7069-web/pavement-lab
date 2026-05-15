"""SQLAlchemy 2.0 ORM models."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


def _now() -> datetime:
    return datetime.utcnow()


class Client(Base):
    __tablename__ = "clients"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    address: Mapped[Optional[str]] = mapped_column(Text)
    contact: Mapped[Optional[str]] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)

    projects: Mapped[list["Project"]] = relationship(back_populates="client")


class Material(Base):
    __tablename__ = "materials"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False, unique=True)
    type: Mapped[Optional[str]] = mapped_column(String(50))   # aggregate | bitumen | filler
    source: Mapped[Optional[str]] = mapped_column(String(200))
    notes: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class Project(Base):
    __tablename__ = "projects"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    client_id: Mapped[Optional[int]] = mapped_column(ForeignKey("clients.id"))
    work_name: Mapped[str] = mapped_column(String(300), nullable=False)
    work_order_no: Mapped[Optional[str]] = mapped_column(String(100))
    work_order_date: Mapped[Optional[str]] = mapped_column(String(50))
    agency: Mapped[Optional[str]] = mapped_column(String(200))
    submitted_by: Mapped[Optional[str]] = mapped_column(String(200))
    mix_type: Mapped[Optional[str]] = mapped_column(String(20), default=None)   # DBM-II, BC-I, etc. (now optional)
    modules_json: Mapped[Optional[str]] = mapped_column(Text, default=None)     # {"mix_design":"complete", ...}
    binder_grade: Mapped[Optional[str]] = mapped_column(String(40), default=None)        # VG-30, CRMB, …
    binder_properties_json: Mapped[Optional[str]] = mapped_column(Text, default=None)    # {"penetration":65, …}
    status: Mapped[str] = mapped_column(String(20), default="draft")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)

    client: Mapped[Optional[Client]] = relationship(back_populates="projects")
    mix_designs: Mapped[list["MixDesign"]] = relationship(back_populates="project", cascade="all, delete-orphan")
    structural_designs: Mapped[list["StructuralDesign"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    maintenance_designs: Mapped[list["MaintenanceDesign"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    material_quantities: Mapped[list["MaterialQuantityDesign"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )


class MixDesign(Base):
    __tablename__ = "mix_designs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), nullable=False)

    # Raw inputs (JSON blobs — full input objects for reproducibility)
    gradation_json: Mapped[Optional[str]] = mapped_column(JSON)
    spgr_json: Mapped[Optional[str]] = mapped_column(JSON)
    gmb_json: Mapped[Optional[str]] = mapped_column(JSON)
    gmm_json: Mapped[Optional[str]] = mapped_column(JSON)
    stability_flow_json: Mapped[Optional[str]] = mapped_column(JSON)
    materials_json: Mapped[Optional[str]] = mapped_column(JSON)

    # Computed
    gsb: Mapped[Optional[float]] = mapped_column(Float)
    gb: Mapped[Optional[float]] = mapped_column(Float)
    obc_pct: Mapped[Optional[float]] = mapped_column(Float)
    gmb_at_obc: Mapped[Optional[float]] = mapped_column(Float)
    gmm_at_obc: Mapped[Optional[float]] = mapped_column(Float)
    stability_at_obc_kn: Mapped[Optional[float]] = mapped_column(Float)
    flow_at_obc_mm: Mapped[Optional[float]] = mapped_column(Float)
    vma_at_obc_pct: Mapped[Optional[float]] = mapped_column(Float)
    vfb_at_obc_pct: Mapped[Optional[float]] = mapped_column(Float)
    air_voids_at_obc_pct: Mapped[Optional[float]] = mapped_column(Float)
    compliance_pass: Mapped[Optional[bool]] = mapped_column(Boolean)
    summary_json: Mapped[Optional[str]] = mapped_column(JSON)

    computed_at: Mapped[datetime] = mapped_column(DateTime, default=_now)

    project: Mapped[Project] = relationship(back_populates="mix_designs")
    reports: Mapped[list["Report"]] = relationship(back_populates="mix_design", cascade="all, delete-orphan")


class Report(Base):
    __tablename__ = "reports"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    mix_design_id: Mapped[int] = mapped_column(ForeignKey("mix_designs.id"), nullable=False)
    file_path: Mapped[str] = mapped_column(String(500))
    file_type: Mapped[str] = mapped_column(String(10))   # docx | pdf
    generated_at: Mapped[datetime] = mapped_column(DateTime, default=_now)

    mix_design: Mapped[MixDesign] = relationship(back_populates="reports")


class StructuralDesign(Base):
    """Phase-4 module: IRC:37 structural design inputs + computed result."""
    __tablename__ = "structural_designs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), nullable=False)

    inputs_json: Mapped[Optional[str]] = mapped_column(JSON)
    design_msa: Mapped[Optional[float]] = mapped_column(Float)
    growth_factor: Mapped[Optional[float]] = mapped_column(Float)
    subgrade_mr_mpa: Mapped[Optional[float]] = mapped_column(Float)
    total_pavement_thickness_mm: Mapped[Optional[float]] = mapped_column(Float)
    composition_json: Mapped[Optional[str]] = mapped_column(JSON)
    notes: Mapped[Optional[str]] = mapped_column(Text)

    computed_at: Mapped[datetime] = mapped_column(DateTime, default=_now)

    project: Mapped[Project] = relationship(back_populates="structural_designs")


class MaintenanceDesign(Base):
    """Phase-5 module: maintenance / rehabilitation skeleton.

    A single row stores one sub-module computation. ``sub_module`` is one of
    ``"overlay" | "cold_mix" | "micro_surfacing"``. ``inputs_json`` and
    ``results_json`` carry the full dataclass payloads as JSON for
    reproducibility — no per-field columns at this skeleton stage.
    """
    __tablename__ = "maintenance_designs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), nullable=False)
    sub_module: Mapped[str] = mapped_column(String(40), nullable=False)
    inputs_json: Mapped[Optional[str]] = mapped_column(JSON)
    results_json: Mapped[Optional[str]] = mapped_column(JSON)
    notes: Mapped[Optional[str]] = mapped_column(Text)
    computed_at: Mapped[datetime] = mapped_column(DateTime, default=_now)

    project: Mapped[Project] = relationship(back_populates="maintenance_designs")


class MaterialQuantityDesign(Base):
    """Phase-7 module: per-project layer-wise material-quantity BOQ.

    One row stores one full BOQ submission. ``inputs_json`` contains the
    list of LayerInput rows; ``results_json`` carries the computed totals
    and per-layer tonnages. Pure-JSON storage keeps the schema stable as
    the formula table evolves.
    """
    __tablename__ = "material_quantities"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), nullable=False)
    inputs_json: Mapped[Optional[str]] = mapped_column(JSON)
    results_json: Mapped[Optional[str]] = mapped_column(JSON)
    total_layer_tonnage_t: Mapped[Optional[float]] = mapped_column(Float)
    total_binder_tonnage_t: Mapped[Optional[float]] = mapped_column(Float)
    notes: Mapped[Optional[str]] = mapped_column(Text)
    computed_at: Mapped[datetime] = mapped_column(DateTime, default=_now)

    project: Mapped[Project] = relationship(back_populates="material_quantities")


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(200), nullable=False)
    role: Mapped[str] = mapped_column(String(20), default="engineer")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class AuditLog(Base):
    __tablename__ = "audit_log"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"))
    action: Mapped[str] = mapped_column(String(100))
    object_type: Mapped[Optional[str]] = mapped_column(String(50))
    object_id: Mapped[Optional[int]] = mapped_column(Integer)
    detail: Mapped[Optional[str]] = mapped_column(Text)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=_now)
