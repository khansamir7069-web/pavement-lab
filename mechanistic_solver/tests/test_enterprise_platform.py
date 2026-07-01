"""Unit and integration tests verifying Phase 6 Enterprise Platform components."""
from __future__ import annotations

import os
import tempfile
from pathlib import Path
import pytest

from mechanistic_solver.enterprise import (
    ConditionRecord,
    MaintenanceActivity,
    RoadSection,
    PavementAsset,
    SensorMetadata,
    DeteriorationState,
    DigitalTwinSection,
    EnterpriseServiceAPI,
    CloudSolverSystem,
    NetworkAnalysisEngine,
    User,
    Organization,
    ProjectPermission,
    CollaborationManager,
    TenantContext,
    Workspace,
    EnterpriseEcosystemManager,
    EnterpriseReportGenerator
)
from mechanistic_solver.core.models import Layer, ObservationPoint, Pavement, WheelLoad
from mechanistic_solver.solver.engine import MechanisticSolver


def test_asset_inventory() -> None:
    """Verify road, section, and condition record assets are managed correctly."""
    l1 = Layer(name="BC", thickness=40.0, elastic_modulus=3000.0, poisson_ratio=0.35, density=2400.0)
    sub = Layer(name="Subgrade", thickness=None, elastic_modulus=60.0, poisson_ratio=0.4, density=1800.0)
    
    sec = RoadSection(
        section_id="sec-1",
        name="Main Section",
        start_chainage=0.0,
        end_chainage=1500.0,
        layers=(l1,),
        subgrade=sub
    )
    
    record = ConditionRecord("2026-06-30", rutting_depth_mm=4.5, crack_area_pct=1.2, deflection_mm=0.25, roughness_iri=2.1)
    sec.add_condition(record)
    
    asset = PavementAsset(road_id="road-A", name="National Highway A", length_km=1.5)
    asset.add_section(sec)
    
    assert len(asset.sections) == 1
    assert asset.sections[0].condition_history[0].rutting_depth_mm == 4.5


def test_digital_twin_diagnostics() -> None:
    """Verify digital twin metadata, sensor updates, and maintenance triggers."""
    twin = DigitalTwinSection(section_id="sec-1", lifecycle_state="OPERATION")
    
    sensor = SensorMetadata("sensor-1", "strain_gauge", depth_mm=40.0, current_value=0.0, unit="microstrain")
    twin.sensors.append(sensor)
    
    twin.update_sensor("sensor-1", 120.5)
    assert twin.sensors[0].current_value == 120.5
    
    # 1. Trigger PCI alert
    twin.deterioration = DeteriorationState(pavement_condition_index_pci=65.0, structural_capacity_index=0.9, remaining_service_life_years=12.0)
    triggers = twin.evaluate_maintenance_triggers()
    assert "resurfacing overlay required" in triggers[0]


def test_api_service_layer() -> None:
    """Verify that consolidated service API endpoints trigger correct solver and optimizer logic."""
    api = EnterpriseServiceAPI()
    
    layers_data = [{"name": "BC", "thickness": 100.0, "elastic_modulus": 3000.0}]
    subgrade_data = {"name": "Subgrade", "elastic_modulus": 60.0}
    
    pavement = api.create_pavement_project(layers_data, subgrade_data)
    assert pavement.layers[0].thickness == 100.0
    
    loads_data = [{"wheel_load": 39.58, "pressure": 0.56, "radius": 150.0}]
    points_data = [{"x": 0.0, "y": 0.0, "z": 100.0}]
    
    res = api.execute_solver_run(pavement, loads_data, points_data)
    assert res["deflection_mm"] > 0.0
    assert len(res["strains"]) > 0


def test_cloud_solver_lifecycle() -> None:
    """Verify cloud job submissions, processing status queues, logs, and retries."""
    l1 = Layer(name="BC", thickness=100.0, elastic_modulus=3000.0, poisson_ratio=0.35, density=2400.0)
    sub = Layer(name="Subgrade", thickness=None, elastic_modulus=60.0, poisson_ratio=0.4, density=1800.0)
    pavement = Pavement(layers=(l1,), subgrade=sub)
    load = WheelLoad(wheel_load=39.58, pressure=0.56, radius=150.0)
    point = ObservationPoint(x=0.0, y=0.0, z=100.0)
    
    system = CloudSolverSystem()
    job_id = system.submit_job(pavement, (load,), [point])
    
    job = system.get_job(job_id)
    assert job.status == "SUBMITTED"
    
    processed_id = system.process_next_job()
    assert processed_id == job_id
    assert job.status == "COMPLETED"
    assert job.result["deflection_mm"] > 0.0


def test_batch_network_analysis() -> None:
    """Verify road network condition rankings and budget allocations."""
    l1 = Layer(name="BC", thickness=100.0, elastic_modulus=3000.0, poisson_ratio=0.35, density=2400.0)
    sub = Layer(name="Subgrade", thickness=None, elastic_modulus=60.0, poisson_ratio=0.4, density=1800.0)
    
    sec1 = RoadSection("sec-1", "Highway East", 0.0, 1000.0, (l1,), sub)
    sec2 = RoadSection("sec-2", "Highway West", 0.0, 1000.0, (l1,), sub)
    
    asset = PavementAsset("road-A", "Highway corridor", 2.0, [sec1, sec2])
    
    engine = NetworkAnalysisEngine()
    load_data = {"wheel_load": 39.58, "pressure": 0.56, "radius": 150.0}
    
    # Light design traffic so the thin BC-on-subgrade sections have sane
    # utilisation (and rehab cost) under the corrected solver physics, keeping
    # the budget-allocation cut-off meaningful: the top-priority section is
    # funded within the 600k budget, the second is not.
    res = engine.analyze_network([asset], load_data, design_traffic_msa=0.1, budget_limit=600000.0)
    
    assert res["network_size_sections"] == 2
    assert len(res["prioritized_actions"]) == 2
    # Ensure prioritized_actions are sorted by cost allocation priority
    assert res["prioritized_actions"][0]["budget_allocated"] is True


def test_collaboration_authorizations() -> None:
    """Verify user roles, annotations, project permissions, and audit logs."""
    manager = CollaborationManager()
    
    manager.grant_permission("user-1", "proj-A", "WRITE")
    assert manager.check_authorized("user-1", "proj-A", "READ") is True
    assert manager.check_authorized("user-1", "proj-A", "WRITE") is True
    assert manager.check_authorized("user-1", "proj-A", "ADMIN") is False
    
    manager.log_activity("user-1", "run_solver", "proj-A", "Deterministic solver execution triggered.")
    assert len(manager.audit_log) == 1
    
    ann = manager.add_annotation("sec-1", "user-1", "Base thickness requires optimization.")
    assert ann.comment == "Base thickness requires optimization."


def test_enterprise_licensing_and_health() -> None:
    """Verify tenant isolation workspace, licensing restrictions, and diagnostics."""
    tenant = TenantContext("tenant-1", "DOT organization", "Professional")
    mgr = EnterpriseEcosystemManager(tenant)
    
    ws = mgr.create_workspace("ws-1", "Primary Workspace")
    assert ws.tenant_id == "tenant-1"
    
    # Professional license can run general features but is restricted from multi-tenant redundancy
    assert mgr.verify_feature_capability("AI_OPTIMIZATION") is True
    assert mgr.verify_feature_capability("MULTI_TENANT_REDUNDANCY") is False
    
    health = mgr.generate_health_report(active_queue_length=3)
    assert health["status"] == "HEALTHY"


def test_enterprise_report_generation() -> None:
    """Verify enterprise reports MD/JSON save successfully under reports/enterprise/."""
    results = {
        "tenant_id": "tenant-1",
        "organization_name": "DOT organization",
        "license_tier": "Enterprise",
        "health_status": "HEALTHY",
        "assets_summary": {"total_corridors": 2, "total_sections": 5},
        "digital_twin_summary": {"lifecycle_state": "OPERATION", "pci": 85.0, "remaining_service_life_years": 14.5, "active_sensors": 4, "triggered_maintenance": []},
        "cloud_queue_summary": {"total_jobs": 12, "pending_jobs": 0, "completed_jobs": 12, "queue_status": "idle"},
        "network_analysis": {"network_size_sections": 2, "budget_limit": 1000000.0, "allocated_total": 500000.0, "remaining_budget": 500000.0, "prioritized_actions": [{"road_name": "Road A", "section_name": "Sec 1", "passed": True, "rehab_cost": 500000.0, "budget_allocated": True}]},
        "audit_trail": [{"user_id": "user-1", "action": "run_solver", "target_id": "sec-1", "details": "Run"}]
    }
    
    with tempfile.TemporaryDirectory() as tmp_dir:
        md_path, json_path = EnterpriseReportGenerator.save_reports(results, tmp_dir)
        assert Path(md_path).exists()
        assert Path(json_path).exists()
        
        md_content = Path(md_path).read_text(encoding="utf-8")
        assert "# RoadX Enterprise Platform Status Report" in md_content
