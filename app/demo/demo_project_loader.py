"""Demo Project Loader Backend.

Dynamically creates a complete, client-ready pavement design project
using live calculation engines, and handles fallback mock mechanistic validation
records if IITPAVE is unavailable.
"""
from __future__ import annotations

import json
from pathlib import Path
from datetime import datetime

from app.db.schema import (
    Project, Client, TrafficAnalysis, StructuralDesign, StabilizedDesign,
    MechanisticValidation, MixDesign, MaterialQuantityDesign
)
from app.core import (
    compute_traffic_analysis, TrafficInput,
    compute_structural_design, StructuralInput,
    compute_stabilized_design, StabilizedInput,
    compute_mix_design, MixDesignInput,
    GradationInput, CoarseAggSGInput, FineAggSGInput, BitumenSGInput,
    GmbInput, GmbGroup, GmbSpecimen, GmmInput, GmmSampleRaw, StabilitySpecimen,
    StabilityFlowInput,
    compute_material_quantity, MaterialQuantityInput, LayerInput
)
from app.core.models import ProjectInfo
from app.engineering.design_audit import run_project_audit

def create_demo_project(db, name_suffix: str = "") -> int:
    # 1. Work name handling
    work_name = "NH-48 Flexible Pavement Preset"
    if name_suffix:
        work_name = f"NH-48 Flexible Pavement Preset (Copy - {name_suffix})"
        
    # 2. Client upsert
    client = db.upsert_client(
        name="Sample Highway Authority",
        address="Surat, Gujarat",
        contact="+91-99999-88888"
    )
    
    # 3. Project creation
    # Compute Subgrade MR dynamically: CBR = 6%
    from app.core.structural_design import compute_subgrade_mr
    mr = compute_subgrade_mr(6.0)
    
    project = db.create_project(
        client_id=client.id,
        work_name=work_name,
        subgrade_cbr=6.0,
        subgrade_mr=mr,
        road_category="NH / SH",
        highway_type="National Highway",
        carriageway="Four-lane divided carriageway",
        design_standard="IRC:37-2018",
        design_life=20,
        location="Surat, Gujarat",
        submitted_by="Pavement Consultant Ltd.",
        status="draft",
        review_status="Draft",
        mix_type="DBM-II"
    )
    
    # Initialize workflow statuses
    db.initialize_workflow_statuses(project.id)
    
    # 4. Traffic Analysis calculation
    traffic_input = TrafficInput(
        initial_cvpd=4500.0,
        growth_rate_pct=5.0,
        design_life_years=20,
        vdf=4.5,
        ldf=0.75,
        road_category="NH / SH",
        notes="Standard heavy traffic design for NH-48 Surat bypass corridor."
    )
    traffic_result = compute_traffic_analysis(traffic_input)
    db.save_traffic_analysis(project_id=project.id, result=traffic_result)
    db.set_module_status(project.id, "traffic", "complete")
    
    # 5. Structural Design (Option A) calculation
    structural_input = StructuralInput(
        road_category="NH / SH",
        design_life_years=20,
        initial_cvpd=4500.0,
        growth_rate_pct=5.0,
        vdf=4.5,
        ldf=0.75,
        subgrade_cbr_pct=6.0,
        notes="Catalogue Plate 1 lookup based on 183.34 MSA and 6% subgrade CBR."
    )
    structural_result = compute_structural_design(structural_input)
    db.save_structural_design(project_id=project.id, result=structural_result)
    db.set_module_status(project.id, "structural", "complete")
    
    # 6. Stabilized Design (Option B) calculation
    stabilized_input = StabilizedInput(
        ctb_thickness_mm=140.0,
        ctb_modulus_mpa=5000.0,
        ctb_ucs_mpa=4.5,
        ctb_poisson=0.25,
        cts_class="C1.5/2.0",
        cts_thickness_mm=100.0,
        cts_modulus_mpa=3000.0,
        cts_poisson=0.25,
        gsb_thickness_mm=150.0,
        bituminous_thickness_mm=100.0, # Cover (BC 40 + DBM 60)
        flexible_design_msa=traffic_result.design_msa,
        flexible_subgrade_cbr=6.0,
        notes="Cement stabilized base (CTB) and sub-base (CTS) layer configuration."
    )
    stabilized_result = compute_stabilized_design(stabilized_input, has_mechanistic_validation=False)
    db.save_stabilized_design(project_id=project.id, result=stabilized_result)
    db.set_module_status(project.id, "stabilization", "complete")
    
    # 7. IITPAVE mechanistic verification (Option C)
    from app.core.iitpave.installation_manager import load_persisted_config
    from app.core.iitpave.runner_config import select_iitpave_runner
    cfg = load_persisted_config()
    selection = select_iitpave_runner(cfg)
    has_real_iitpave = (
        selection.ok 
        and selection.runner is not None 
        and selection.runner_source == "external_exe"
    )
    
    workflow_result = None
    if has_real_iitpave:
        from app.core.iitpave.workflow import run_structural_iitpave_mechanistic_workflow
        workflow_result = run_structural_iitpave_mechanistic_workflow(structural_result)
        if workflow_result.summary is None or workflow_result.summary.refused:
            has_real_iitpave = False
            
    if has_real_iitpave and workflow_result is not None:
        db.save_mechanistic_validation(
            project_id=project.id,
            summary=workflow_result.summary,
            inputs=workflow_result.selection.as_dict() if workflow_result.selection else None
        )
    else:
        # Mock validation
        from app.core.mechanistic_validation.engine import MechanisticValidationSummary
        from app.core.mechanistic_validation.fatigue import FatigueCheck, FatigueCalibration
        from app.core.mechanistic_validation.rutting import RuttingCheck, RuttingCalibration
        
        fatigue_check = FatigueCheck(
            epsilon_t_microstrain=112.5,
            e_bc_mpa=3000.0,
            design_msa=traffic_result.design_msa,
            c_factor=1.0,
            cumulative_life_msa=250.0,
            verdict=None,
            calibration=FatigueCalibration(label="IRC37_PLACEHOLDER_80pct", k1=2.21e-04, k2=3.89, k3=0.854, reliability_pct=80, is_placeholder=True),
            is_placeholder=True,
            refused=True,
            refused_reason="Mechanistic verification was not executed because a licensed IITPAVE installation was unavailable.",
            notes="Mechanistic verification was not executed because a licensed IITPAVE installation was unavailable."
        )
        rutting_check = RuttingCheck(
            epsilon_v_microstrain=220.0,
            design_msa=traffic_result.design_msa,
            cumulative_life_msa=300.0,
            verdict=None,
            calibration=RuttingCalibration(label="IRC37_PLACEHOLDER_80pct", k_r=4.1656e-08, k_v=4.5337, reliability_pct=80, is_placeholder=True),
            is_placeholder=True,
            refused=True,
            refused_reason="Mechanistic verification was not executed because a licensed IITPAVE installation was unavailable.",
            notes="Mechanistic verification was not executed because a licensed IITPAVE installation was unavailable."
        )
        summary = MechanisticValidationSummary(
            fatigue=fatigue_check,
            rutting=rutting_check,
            is_placeholder=True,
            refused=True,
            refused_reason="Mechanistic verification was not executed because a licensed IITPAVE installation was unavailable.",
            notes="Mechanistic verification was not executed because a licensed IITPAVE installation was unavailable."
        )
        inputs_payload = {
            "is_mock_preset": True,
            "refused": True,
            "refused_reason": "Mechanistic verification was not executed because a licensed IITPAVE installation was unavailable.",
            "notes": "Mechanistic verification was not executed because a licensed IITPAVE installation was unavailable."
        }
        db.save_mechanistic_validation(
            project_id=project.id,
            summary=summary,
            inputs=inputs_payload
        )
    db.set_module_status(project.id, "mechanistic", "complete")
    
    # 8. Marshall mix designs
    demo_file_path = Path(__file__).resolve()
    workspace_root = demo_file_path.parents[2]
    fixture_path = workspace_root / "tests" / "golden" / "shirdi_dbm.json"
    
    if fixture_path.exists():
        fx = json.loads(fixture_path.read_text(encoding="utf-8"))
        g_sieve = GradationInput(
            sieve_sizes_mm=tuple(fx["gradation"]["sieve_sizes_mm"]),
            pass_pct={k: tuple(v) for k, v in fx["gradation"]["pass_pct"].items()},
            blend_ratios={k: v for k, v in fx["gradation"]["blend_ratios"].items() if k != "Cement"},
            spec_lower=tuple(fx["gradation"]["spec_lower"]),
            spec_upper=tuple(fx["gradation"]["spec_upper"]),
        )
        sg_coarse = {
            "25mm": CoarseAggSGInput(
                a_sample_plus_container_water=tuple(fx["sp_gr"]["coarse_25"]["A"]),
                b_container_in_water=tuple(fx["sp_gr"]["coarse_25"]["B"]),
                c_ssd_in_air=tuple(fx["sp_gr"]["coarse_25"]["C"]),
                d_ovendry_in_air=tuple(fx["sp_gr"]["coarse_25"]["D"]),
            ),
            "20mm": CoarseAggSGInput(
                a_sample_plus_container_water=tuple(fx["sp_gr"]["coarse_20"]["A"]),
                b_container_in_water=tuple(fx["sp_gr"]["coarse_20"]["B"]),
                c_ssd_in_air=tuple(fx["sp_gr"]["coarse_20"]["C"]),
                d_ovendry_in_air=tuple(fx["sp_gr"]["coarse_20"]["D"]),
            ),
        }
        sg_fine = {
            "6mm": FineAggSGInput(
                w1_empty=tuple(fx["sp_gr"]["fine_6"]["W1"]),
                w2_dry_sample=tuple(fx["sp_gr"]["fine_6"]["W2"]),
                w3_dry_sample_water=tuple(fx["sp_gr"]["fine_6"]["W3"]),
                w4_water_only=tuple(fx["sp_gr"]["fine_6"]["W4"]),
            ),
            "SD": FineAggSGInput(
                w1_empty=tuple(fx["sp_gr"]["fine_sd"]["W1"]),
                w2_dry_sample=tuple(fx["sp_gr"]["fine_sd"]["W2"]),
                w3_dry_sample_water=tuple(fx["sp_gr"]["fine_sd"]["W3"]),
                w4_water_only=tuple(fx["sp_gr"]["fine_sd"]["W4"]),
            ),
        }
        sg_bit = BitumenSGInput(
            a_empty=tuple(fx["sp_gr"]["bitumen"]["A"]),
            b_water=tuple(fx["sp_gr"]["bitumen"]["B"]),
            c_sample=tuple(fx["sp_gr"]["bitumen"]["C"]),
            d_sample_water=tuple(fx["sp_gr"]["bitumen"]["D"]),
        )
        gmb_groups = tuple(
            GmbGroup(
                bitumen_pct=grp["pb_pct"],
                specimens=tuple(
                    GmbSpecimen(a_dry_in_air=s["A"], c_in_water=s["D"], b_ssd_in_air=s["B"])
                    for s in grp["specimens"]
                ),
            )
            for grp in fx["gmb"]["groups"]
        )
        gmm_in = GmmInput(
            reference_pb_pct=fx["gmm"]["reference_pb"],
            samples_at_reference=tuple(
                GmmSampleRaw(
                    a_empty_flask=s["A"],
                    b_flask_plus_dry_sample=s["B"],
                    d_flask_filled_water=s["D"],
                    e_flask_sample_water=s["E"],
                )
                for s in fx["gmm"]["samples_ref"]
            ),
            design_pb_pct=(3.5, 4.0, 4.5, 5.0, 5.5),
            bitumen_sg=0.0,
        )
        specs = []
        for grp in fx["stability_flow"]["groups"]:
            for i_sp, s_sp in enumerate(grp["specimens"], start=1):
                specs.append(StabilitySpecimen(
                    bitumen_pct=grp["pb_pct"],
                    sample_id=f"SAMPLE-{i_sp}",
                    height_readings_mm=(s_sp["h1"], s_sp["h2"], s_sp["h3"]),
                    diameter_mm=s_sp["dia"],
                    correction_factor=s_sp["corr"],
                    measured_stability_kn=s_sp["stab"],
                    flow_mm=s_sp["flow"],
                    include_in_stab_avg=s_sp.get("include_stab", True),
                    include_in_flow_avg=s_sp.get("include_flow", True),
                    corrected_stability_kn_override=s_sp.get("n_cached"),
                ))
        
        # Save DBM-II mix design
        mix_in_dbm = MixDesignInput(
            project=ProjectInfo(mix_type="DBM-II", work_name=work_name, client="Sample Highway Authority"),
            gradation=g_sieve,
            sg_coarse=sg_coarse,
            sg_fine=sg_fine,
            sg_bitumen=sg_bit,
            gmb=GmbInput(groups=gmb_groups),
            gmm=gmm_in,
            stability_flow=StabilityFlowInput(specimens=tuple(specs)),
        )
        mix_res_dbm = compute_mix_design(mix_in_dbm)
        db.save_mix_design(
            project_id=project.id,
            inputs_payload={
                "gradation": fx["gradation"],
                "spgr": {"coarse": list(sg_coarse.keys()), "fine": list(sg_fine.keys())},
                "gmb": fx["gmb"],
                "gmm": {
                    "reference_pb": fx["gmm"]["reference_pb"],
                    "samples_ref": fx["gmm"]["samples_ref"]
                },
                "stability_flow": fx["stability_flow"],
                "materials": {},
            },
            result=mix_res_dbm
        )

        # Save BC-II mix design
        mix_in_bc = MixDesignInput(
            project=ProjectInfo(mix_type="BC-II", work_name=work_name, client="Sample Highway Authority"),
            gradation=g_sieve,
            sg_coarse=sg_coarse,
            sg_fine=sg_fine,
            sg_bitumen=sg_bit,
            gmb=GmbInput(groups=gmb_groups),
            gmm=gmm_in,
            stability_flow=StabilityFlowInput(specimens=tuple(specs)),
        )
        mix_res_bc = compute_mix_design(mix_in_bc)
        db.save_mix_design(
            project_id=project.id,
            inputs_payload={
                "gradation": fx["gradation"],
                "spgr": {"coarse": list(sg_coarse.keys()), "fine": list(sg_fine.keys())},
                "gmb": fx["gmb"],
                "gmm": {
                    "reference_pb": fx["gmm"]["reference_pb"],
                    "samples_ref": fx["gmm"]["samples_ref"]
                },
                "stability_flow": fx["stability_flow"],
                "materials": {},
            },
            result=mix_res_bc
        )
        db.set_module_status(project.id, "mix_design", "complete")
        
    # 9. BOQ Quantity & Cost Estimation
    mq_input = MaterialQuantityInput(
        project_id=project.id,
        road_length_m=5000.0,
        carriageway_width_m=7.0,
        shoulder_width_m=1.5,
        layers=(
            LayerInput("Prime Coat", length_m=5000, width_m=7.0),
            LayerInput("Tack Coat", length_m=5000, width_m=7.0),
            LayerInput("BC", length_m=5000, width_m=7.0, thickness_mm=40),
            LayerInput("DBM", length_m=5000, width_m=7.0, thickness_mm=190),
            LayerInput("WMM", length_m=5000, width_m=7.0, thickness_mm=250),
            LayerInput("GSB", length_m=5000, width_m=7.0, thickness_mm=230),
        )
    )
    mq_result = compute_material_quantity(mq_input)
    db.save_material_quantity(project_id=project.id, result=mq_result)
    db.set_module_status(project.id, "boq", "complete")
    
    # 10. Cost option comparison / recommendation engine
    db.update_selected_design_option(project.id, "Option D: Recommended Option")
    
    # 11. Project checklist / expert audit
    run_project_audit(project.id, db)
    
    return project.id
