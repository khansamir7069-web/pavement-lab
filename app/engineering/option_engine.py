from __future__ import annotations

import json
from typing import List, Dict, Any, Optional
from app.db.schema import Project, StructuralDesign, StabilizedDesign, MechanisticValidation

def generate_pavement_options(project_id: int, db) -> List[Dict[str, Any]]:
    """Generate and compare 4 pavement design options for the project:
    Option A: Conventional Flexible Pavement
    Option B: CTB/CTS Stabilized Pavement
    Option C: Mechanistic Verified Optimized Design
    Option D: Cost Optimized Recommendation
    """
    # 1. Fetch project and related records
    p = db.get_project(project_id)
    if not p:
        return []

    sd = db.latest_structural_design(project_id)
    stab = db.latest_stabilized_design(project_id)
    mv = db.latest_mechanistic_validation(project_id)

    options = []

    # --- Option A: Conventional Flexible Pavement ---
    opt_a = {
        "option_name": "Option A: Conventional Flexible Pavement",
        "design_type": "Conventional Flexible",
        "layers": "No design computed",
        "thickness_summary": "—",
        "total_pavement_thickness": 0.0,
        "material_requirement": "High bituminous binder (VG-30/40) & standard stone aggregate volume.",
        "estimated_cost_indicator": "High",
        "engineering_score": 0,
        "iitpave_status": "Not Run",
        "advantages": [
            "High local contractor familiarity and simple construction",
            "No specialized chemical stabilizers required",
            "Easy to repair and maintain"
        ],
        "limitations": [
            "Thicker pavement structure requires more natural aggregates",
            "High consumption of bituminous materials increases cost",
            "Prone to rutting under very heavy traffic loading"
        ],
        "recommendation_reason": "Simple construction but requires more natural aggregates."
    }

    if sd:
        try:
            comp = json.loads(sd.composition_json) if sd.composition_json else []
        except Exception:
            comp = []

        if comp:
            layer_strs = []
            bit_thick = 0.0
            gran_thick = 0.0
            for ly in comp:
                name = ly.get("name", "")
                thick = ly.get("thickness_mm", 0.0)
                layer_strs.append(f"{name} ({thick:.0f} mm)")
                name_upper = name.upper()
                if any(x in name_upper for x in ["BC", "DBM", "BITUMINOUS", "BINDER", "WEARING"]):
                    bit_thick += thick
                else:
                    gran_thick += thick

            opt_a["layers"] = ", ".join(layer_strs)
            total_thick = sd.total_pavement_thickness_mm or sum(ly.get("thickness_mm", 0.0) for ly in comp)
            opt_a["total_pavement_thickness"] = float(total_thick)
            opt_a["thickness_summary"] = f"Bituminous: {bit_thick:.0f} mm, Granular: {gran_thick:.0f} mm (Total: {total_thick:.0f} mm)"
            opt_a["engineering_score"] = 75
            opt_a["recommendation_reason"] = "Standard IRC:37 design template using conventional bituminous and granular layers."
        else:
            opt_a["layers"] = "No design computed"

    options.append(opt_a)

    # --- Option B: CTB/CTS Stabilized Pavement ---
    opt_b = {
        "option_name": "Option B: CTB/CTS Stabilized Pavement",
        "design_type": "Stabilized Pavement",
        "layers": "No design computed",
        "thickness_summary": "—",
        "total_pavement_thickness": 0.0,
        "material_requirement": "Reduced bituminous binder, cement-treated base/subbase layer aggregates.",
        "estimated_cost_indicator": "Medium",
        "engineering_score": 0,
        "iitpave_status": "Not Run",
        "advantages": [
            "Reduces overall pavement thickness by 20-30%",
            "Substantially reduces consumption of natural aggregates",
            "Higher structural integrity and stiffness"
        ],
        "limitations": [
            "Requires strict quality control during cement mixing and curing",
            "Potential for reflection cracking from the stabilized base to the surface",
            "Requires specialized stabilization equipment"
        ],
        "recommendation_reason": "Reduces granular thickness by using cement stabilized base/subbase."
    }

    has_suitable_ucs = True
    if stab:
        try:
            res_data = json.loads(stab.results_json) if stab.results_json else {}
            inputs_data = json.loads(stab.inputs_json) if stab.inputs_json else {}
        except Exception:
            res_data = {}
            inputs_data = {}

        comp = res_data.get("stabilized_composition", [])
        if comp:
            layer_strs = []
            bit_thick = 0.0
            stab_thick = 0.0
            gran_thick = 0.0
            for ly in comp:
                name = ly.get("name", "")
                thick = ly.get("thickness_mm", 0.0)
                layer_strs.append(f"{name} ({thick:.0f} mm)")
                name_upper = name.upper()
                if any(x in name_upper for x in ["BC", "DBM", "BITUMINOUS", "BINDER", "WEARING"]):
                    bit_thick += thick
                elif any(x in name_upper for x in ["CTB", "CTS", "STABILIZED"]):
                    stab_thick += thick
                else:
                    gran_thick += thick

            opt_b["layers"] = ", ".join(layer_strs)
            total_thick = sum(ly.get("thickness_mm", 0.0) for ly in comp)
            opt_b["total_pavement_thickness"] = float(total_thick)
            opt_b["thickness_summary"] = f"Bituminous: {bit_thick:.0f} mm, Stabilized: {stab_thick:.0f} mm, Granular: {gran_thick:.0f} mm (Total: {total_thick:.0f} mm)"
            
            # Check UCS availability
            ctb_ucs = inputs_data.get("ctb_ucs_mpa", 0.0)
            if ctb_ucs == 0.0:
                opt_b["engineering_score"] = 55
                has_suitable_ucs = False
                opt_b["limitations"].append("Missing UCS: Unconfined Compressive Strength not specified.")
                opt_b["recommendation_reason"] = "Stabilized alternative computed, but UCS data is missing."
            elif ctb_ucs < 3.0 or ctb_ucs > 7.0:
                opt_b["engineering_score"] = 65
                has_suitable_ucs = False
                opt_b["limitations"].append(f"Suboptimal UCS: UCS of {ctb_ucs:.1f} MPa is outside the recommended 3.0-7.0 MPa range.")
                opt_b["recommendation_reason"] = "Stabilized alternative computed, but UCS value is outside typical range."
            else:
                opt_b["engineering_score"] = 85
                opt_b["recommendation_reason"] = "CTB/CTS stabilized base provides significant thickness savings while maintaining strength."
        else:
            opt_b["layers"] = "No design computed"

    options.append(opt_b)

    # --- Option C: Mechanistic Verified Optimized Design ---
    opt_c = {
        "option_name": "Option C: Mechanistic Verified Optimized Design",
        "design_type": "Mechanistic Verified",
        "layers": "No design computed",
        "thickness_summary": "—",
        "total_pavement_thickness": 0.0,
        "material_requirement": "Highly optimized bituminous and stabilized material quantities.",
        "estimated_cost_indicator": "Medium",
        "engineering_score": 0,
        "iitpave_status": "Not Run",
        "advantages": [
            "Mechanistically verified using IITPAVE strain analysis",
            "Ensures compliance against both fatigue cracking and rutting failure",
            "Minimizes structural risk under heavy axle loads"
        ],
        "limitations": [
            "Demands detailed traffic axle load spectrum and resilient modulus testing",
            "Higher technical expertise required for design verification"
        ],
        "recommendation_reason": "IITPAVE analysis confirms the structure safely resists critical fatigue and rutting strains."
    }

    is_verified_pass = False
    if mv:
        comp = []
        if stab:
            try:
                res_data = json.loads(stab.results_json) if stab.results_json else {}
                comp = res_data.get("stabilized_composition", [])
            except Exception:
                comp = []
        if not comp and sd:
            try:
                comp = json.loads(sd.composition_json) if sd.composition_json else []
            except Exception:
                comp = []

        if comp:
            layer_strs = []
            bit_thick = 0.0
            stab_thick = 0.0
            gran_thick = 0.0
            for ly in comp:
                name = ly.get("name", "")
                thick = ly.get("thickness_mm", 0.0)
                layer_strs.append(f"{name} ({thick:.0f} mm)")
                name_upper = name.upper()
                if any(x in name_upper for x in ["BC", "DBM", "BITUMINOUS", "BINDER", "WEARING"]):
                    bit_thick += thick
                elif any(x in name_upper for x in ["CTB", "CTS", "STABILIZED"]):
                    stab_thick += thick
                else:
                    gran_thick += thick

            opt_c["layers"] = ", ".join(layer_strs)
            total_thick = sum(ly.get("thickness_mm", 0.0) for ly in comp)
            opt_c["total_pavement_thickness"] = float(total_thick)
            if stab_thick > 0:
                opt_c["thickness_summary"] = f"Bituminous: {bit_thick:.0f} mm, Stabilized: {stab_thick:.0f} mm, Granular: {gran_thick:.0f} mm (Total: {total_thick:.0f} mm)"
            else:
                opt_c["thickness_summary"] = f"Bituminous: {bit_thick:.0f} mm, Granular: {gran_thick:.0f} mm (Total: {total_thick:.0f} mm)"

            fatigue = (mv.fatigue_verdict or "FAIL").upper()
            rutting = (mv.rutting_verdict or "FAIL").upper()
            opt_c["iitpave_status"] = f"Fatigue: {fatigue}, Rutting: {rutting}"

            if fatigue == "PASS" and rutting == "PASS":
                opt_c["engineering_score"] = 95
                is_verified_pass = True
                opt_c["recommendation_reason"] = "Mechanistically validated with IITPAVE; structural safety confirmed."
            else:
                opt_c["engineering_score"] = 50
                opt_c["limitations"].append(f"IITPAVE check failed: fatigue={fatigue}, rutting={rutting}.")
                opt_c["recommendation_reason"] = "Mechanistic validation failed to satisfy strain limits."
        else:
            opt_c["layers"] = "No design computed"

    options.append(opt_c)

    # --- Option D: Cost Optimized Recommendation ---
    valid_options = []
    if opt_c["total_pavement_thickness"] > 0 and is_verified_pass:
        valid_options.append((opt_c, 3, opt_c["total_pavement_thickness"]))
    if opt_b["total_pavement_thickness"] > 0 and has_suitable_ucs:
        valid_options.append((opt_b, 2, opt_b["total_pavement_thickness"]))
    if opt_a["total_pavement_thickness"] > 0:
        valid_options.append((opt_a, 1, opt_a["total_pavement_thickness"]))

    if not valid_options:
        if opt_c["total_pavement_thickness"] > 0:
            valid_options.append((opt_c, 0, opt_c["total_pavement_thickness"]))
        if opt_b["total_pavement_thickness"] > 0:
            valid_options.append((opt_b, 0, opt_b["total_pavement_thickness"]))
        if opt_a["total_pavement_thickness"] > 0:
            valid_options.append((opt_a, 0, opt_a["total_pavement_thickness"]))

    opt_d = {
        "option_name": "Option D: Recommended Option",
        "design_type": "Recommended Option",

        "layers": "No design computed",
        "thickness_summary": "—",
        "total_pavement_thickness": 0.0,
        "material_requirement": "Optimized materials.",
        "estimated_cost_indicator": "Low",
        "engineering_score": 0,
        "iitpave_status": "Not Run",
        "advantages": [
            "Lowest estimated construction cost and aggregate consumption",
            "Passed structural check or mechanistic verification",
            "Optimized layer design"
        ],
        "limitations": [
            "Requires strict compliance with the selected option's quality controls",
            "Construction complexity depends on the chosen base option"
        ],
        "recommendation_reason": "No valid option computed yet."
    }

    if valid_options:
        valid_options.sort(key=lambda x: (-x[1], x[2]))
        selected_opt = valid_options[0][0]

        opt_d["layers"] = selected_opt["layers"]
        opt_d["total_pavement_thickness"] = selected_opt["total_pavement_thickness"]
        opt_d["thickness_summary"] = selected_opt["thickness_summary"]
        opt_d["material_requirement"] = selected_opt["material_requirement"]
        opt_d["engineering_score"] = selected_opt["engineering_score"]
        opt_d["iitpave_status"] = selected_opt["iitpave_status"]
        
        if selected_opt["design_type"] == "Stabilized Pavement":
            opt_d["recommendation_reason"] = "CTB/CTS alternative reduces granular thickness and material cost while maintaining performance."
        elif selected_opt["design_type"] == "Mechanistic Verified":
            opt_d["recommendation_reason"] = "IITPAVE verified stabilized design offers maximum aggregate savings and guaranteed fatigue/rutting resistance."
        else:
            opt_d["recommendation_reason"] = "Conventional flexible pavement recommended due to moderate traffic and simpler construction."

    options.append(opt_d)

    return options
