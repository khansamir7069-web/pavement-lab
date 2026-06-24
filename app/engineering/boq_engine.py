from __future__ import annotations

import json
from typing import Dict, Any, List, Optional
from sqlalchemy import select
from app.db.schema import Project, StructuralDesign, StabilizedDesign, MaterialQuantityDesign, MaterialRate

DEFAULT_RATES = {
    "GSB": {"rate": 1500.0, "unit": "Cum"},
    "WMM": {"rate": 1800.0, "unit": "Cum"},
    "DBM": {"rate": 7500.0, "unit": "Tonne"},
    "BC": {"rate": 8500.0, "unit": "Tonne"},
    "Bitumen": {"rate": 60000.0, "unit": "Tonne"},
    "Cement": {"rate": 7000.0, "unit": "Tonne"},
    "Aggregate": {"rate": 1200.0, "unit": "Tonne"},
}

def format_indian_currency(amount: float) -> str:
    """Format amount in Indian numbering system as Lakhs or Crores, prefixed with ₹."""
    if amount >= 10_000_000:
        crores = amount / 10_000_000
        return f"₹{crores:.2f} Cr"
    elif amount >= 100_000:
        lakhs = amount / 100_000
        return f"₹{lakhs:.2f} L"
    else:
        return f"₹{amount:,.2f}"

def get_material_key(layer_name: str) -> str:
    name = layer_name.upper()

    if "BC" in name or "CONCRETE" in name or "WEARING" in name:
        return "BC"
    if "DBM" in name or "BINDER" in name or "BM" in name or "BITUMINOUS" in name:
        return "DBM"

    if "WMM" in name or "WET MIX" in name:
        return "WMM"
    if "GSB" in name or "SUB-BASE" in name or "SUBBASE" in name or "GRANULAR" in name:
        return "GSB"
    if "CTB" in name or "CTS" in name or "STABILIZED" in name:
        return "STABILIZED"
    return "Aggregate"

def calculate_layer_boq(
    name: str,
    thickness_mm: float,
    length_m: float,
    width_m: float,
    rates: Dict[str, Dict[str, Any]]
) -> Dict[str, Any]:
    """Calculate quantities and cost for a single structural layer."""
    material_key = get_material_key(name)
    area_m2 = length_m * width_m
    volume_m3 = area_m2 * (thickness_mm / 1000.0)
    
    # Densities
    if material_key == "BC":
        density = 2.40
    elif material_key == "DBM":
        density = 2.40
    elif material_key == "WMM":
        density = 2.20
    elif material_key == "GSB":
        density = 2.10
    elif name.upper() == "CTB":
        density = 2.20
    elif name.upper() == "CTS":
        density = 2.00
    else:
        density = 2.20

    waste_pct = 2.0
    weight_t = volume_m3 * density * (1.0 + waste_pct / 100.0)

    # Binder/Cement splits
    binder_pct = 0.0
    cement_pct = 0.0
    if material_key == "BC":
        binder_pct = 5.5
    elif material_key == "DBM":
        binder_pct = 4.5
    elif name.upper() == "CTB":
        cement_pct = 4.5
    elif name.upper() == "CTS":
        cement_pct = 3.0

    bitumen_t = 0.0
    cement_t = 0.0
    if binder_pct > 0:
        bitumen_t = weight_t * binder_pct / 100.0
        aggregate_t = weight_t - bitumen_t
    elif cement_pct > 0:
        cement_t = weight_t * cement_pct / 100.0
        aggregate_t = weight_t - cement_t
    else:
        aggregate_t = weight_t

    # Cost Calculation
    cost = 0.0
    rate_used = 0.0
    unit_used = ""

    if material_key == "STABILIZED":
        # Calculate from constituents: cement + aggregate
        cement_rate = rates.get("Cement", {}).get("rate", DEFAULT_RATES["Cement"]["rate"])
        agg_rate = rates.get("Aggregate", {}).get("rate", DEFAULT_RATES["Aggregate"]["rate"])
        cost = (cement_t * cement_rate) + (aggregate_t * agg_rate)
        rate_used = agg_rate
        unit_used = "Tonne (Constituent)"
    else:
        r_info = rates.get(material_key, DEFAULT_RATES.get(material_key, {}))
        rate_used = r_info.get("rate", 0.0)
        unit_used = r_info.get("unit", "Tonne")
        if unit_used.lower() in ("cum", "m3"):
            cost = volume_m3 * rate_used
        else:
            cost = weight_t * rate_used

    return {
        "layer_name": name,
        "thickness_mm": thickness_mm,
        "length_m": length_m,
        "width_m": width_m,
        "volume_m3": volume_m3,
        "weight_t": weight_t,
        "bitumen_t": bitumen_t,
        "cement_t": cement_t,
        "aggregate_t": aggregate_t,
        "rate": rate_used,
        "unit": unit_used,
        "cost": cost,
        "formatted_cost": format_indian_currency(cost)
    }

def generate_boq(project_id: int, db) -> Dict[str, Any]:
    """Generate BOQ details and option cost comparisons for a project."""
    p = db.get_project(project_id)
    if not p:
        return {"available": False, "options": {}, "error": "Project not found"}

    # Fetch rates from DB
    db_rates = db.list_material_rates()
    rates = {}
    for r in db_rates:
        rates[r.material] = {"rate": r.rate, "unit": r.unit}
    
    # Merge missing defaults
    for k, v in DEFAULT_RATES.items():
        if k not in rates:
            rates[k] = v

    # Check project-level geometry from latest MaterialQuantityDesign
    mq = db.latest_material_quantity(project_id)
    road_length = 1000.0
    carriageway_width = 7.0
    shoulder_width = 1.5
    has_geometry = False

    if mq and mq.inputs_json:
        try:
            inputs_dict = json.loads(mq.inputs_json)
            if "road_length_m" in inputs_dict:
                road_length = float(inputs_dict["road_length_m"])
                carriageway_width = float(inputs_dict["carriageway_width_m"])
                shoulder_width = float(inputs_dict["shoulder_width_m"])
                has_geometry = True
        except Exception:
            pass

    sd = db.latest_structural_design(project_id)
    stab = db.latest_stabilized_design(project_id)

    # We only show actual ₹ amounts if:
    # 1. geometry is available (either from saved BOQ panel or we have active compositions)
    # 2. rates are loaded
    # 3. at least one composition exists
    has_layers = (sd is not None or stab is not None)
    
    # Option compositions
    comp_a = []
    if sd:
        try:
            comp_a = json.loads(sd.composition_json) if sd.composition_json else []
        except Exception:
            comp_a = []

    comp_b = []
    if stab:
        try:
            res_data = json.loads(stab.results_json) if stab.results_json else {}
            comp_b = res_data.get("stabilized_composition", [])
        except Exception:
            comp_b = []

    comp_c = []
    if comp_b:
        comp_c = comp_b
    elif comp_a:
        comp_c = comp_a

    options_data = {}
    
    # Check if we should calculate exact ₹ costs or fallback to relative cost index
    # We require has_geometry AND has_layers to show rupee values.
    show_rupees = has_geometry and has_layers

    # Option A: Conventional Flexible Pavement
    if comp_a:
        layers_boq = []
        total_cost = 0.0
        tot_bitumen = 0.0
        tot_cement = 0.0
        tot_agg = 0.0
        for ly in comp_a:
            name = ly.get("name", "Unknown")
            thick = ly.get("thickness_mm", 0.0)
            material_key = get_material_key(name)
            
            # WMM and GSB extend to shoulders
            if material_key in ("WMM", "GSB"):
                w = carriageway_width + 2 * shoulder_width
            else:
                w = carriageway_width

            l_boq = calculate_layer_boq(name, thick, road_length, w, rates)
            layers_boq.append(l_boq)
            total_cost += l_boq["cost"]
            tot_bitumen += l_boq["bitumen_t"]
            tot_cement += l_boq["cement_t"]
            tot_agg += l_boq["aggregate_t"]

        options_data["Option A"] = {
            "available": True,
            "total_cost": total_cost,
            "formatted_cost": format_indian_currency(total_cost),
            "cost_per_km": total_cost / (road_length / 1000.0) if road_length > 0 else 0.0,
            "formatted_cost_per_km": format_indian_currency(total_cost / (road_length / 1000.0)) if road_length > 0 else "₹0.00",
            "bitumen_t": tot_bitumen,
            "cement_t": tot_cement,
            "aggregate_t": tot_agg,
            "layers": layers_boq
        }
    else:
        options_data["Option A"] = {"available": False}

    # Option B: CTB/CTS Stabilized Pavement
    if comp_b:
        layers_boq = []
        total_cost = 0.0
        tot_bitumen = 0.0
        tot_cement = 0.0
        tot_agg = 0.0
        for ly in comp_b:
            name = ly.get("name", "Unknown")
            thick = ly.get("thickness_mm", 0.0)
            material_key = get_material_key(name)
            
            if material_key in ("WMM", "GSB", "STABILIZED"):
                w = carriageway_width + 2 * shoulder_width
            else:
                w = carriageway_width

            l_boq = calculate_layer_boq(name, thick, road_length, w, rates)
            layers_boq.append(l_boq)
            total_cost += l_boq["cost"]
            tot_bitumen += l_boq["bitumen_t"]
            tot_cement += l_boq["cement_t"]
            tot_agg += l_boq["aggregate_t"]

        options_data["Option B"] = {
            "available": True,
            "total_cost": total_cost,
            "formatted_cost": format_indian_currency(total_cost),
            "cost_per_km": total_cost / (road_length / 1000.0) if road_length > 0 else 0.0,
            "formatted_cost_per_km": format_indian_currency(total_cost / (road_length / 1000.0)) if road_length > 0 else "₹0.00",
            "bitumen_t": tot_bitumen,
            "cement_t": tot_cement,
            "aggregate_t": tot_agg,
            "layers": layers_boq
        }
    else:
        options_data["Option B"] = {"available": False}

    # Option C: Mechanistic Verified Optimized Design
    # In Option C, we require a MechanisticValidation to exist
    mv = db.latest_mechanistic_validation(project_id)
    if mv and comp_c:
        layers_boq = []
        total_cost = 0.0
        tot_bitumen = 0.0
        tot_cement = 0.0
        tot_agg = 0.0
        for ly in comp_c:
            name = ly.get("name", "Unknown")
            thick = ly.get("thickness_mm", 0.0)
            material_key = get_material_key(name)
            
            if material_key in ("WMM", "GSB", "STABILIZED"):
                w = carriageway_width + 2 * shoulder_width
            else:
                w = carriageway_width

            l_boq = calculate_layer_boq(name, thick, road_length, w, rates)
            layers_boq.append(l_boq)
            total_cost += l_boq["cost"]
            tot_bitumen += l_boq["bitumen_t"]
            tot_cement += l_boq["cement_t"]
            tot_agg += l_boq["aggregate_t"]

        options_data["Option C"] = {
            "available": True,
            "total_cost": total_cost,
            "formatted_cost": format_indian_currency(total_cost),
            "cost_per_km": total_cost / (road_length / 1000.0) if road_length > 0 else 0.0,
            "formatted_cost_per_km": format_indian_currency(total_cost / (road_length / 1000.0)) if road_length > 0 else "₹0.00",
            "bitumen_t": tot_bitumen,
            "cement_t": tot_cement,
            "aggregate_t": tot_agg,
            "layers": layers_boq
        }
    else:
        options_data["Option C"] = {"available": False}

    # Option D: Recommended Option
    # Simply points to the best valid option
    # Determine best valid option
    # Matches option_engine.py decision rule
    has_suitable_ucs = True
    if stab:
        try:
            inputs_data = json.loads(stab.inputs_json) if stab.inputs_json else {}
            ctb_ucs = inputs_data.get("ctb_ucs_mpa", 0.0)
            if ctb_ucs == 0.0 or ctb_ucs < 3.0 or ctb_ucs > 7.0:
                has_suitable_ucs = False
        except Exception:
            has_suitable_ucs = False

    is_verified_pass = False
    if mv:
        fatigue = (mv.fatigue_verdict or "FAIL").upper()
        rutting = (mv.rutting_verdict or "FAIL").upper()
        if fatigue == "PASS" and rutting == "PASS":
            is_verified_pass = True

    best_opt_key = None
    valid_options = []
    if options_data["Option C"].get("available") and is_verified_pass:
        valid_options.append(("Option C", 3, comp_c))
    if options_data["Option B"].get("available") and has_suitable_ucs:
        valid_options.append(("Option B", 2, comp_b))
    if options_data["Option A"].get("available"):
        valid_options.append(("Option A", 1, comp_a))

    if not valid_options:
        if options_data["Option C"].get("available"):
            valid_options.append(("Option C", 0, comp_c))
        if options_data["Option B"].get("available"):
            valid_options.append(("Option B", 0, comp_b))
        if options_data["Option A"].get("available"):
            valid_options.append(("Option A", 0, comp_a))

    if valid_options:
        # Sort by rank descending, then thickness summary ascending (just like option_engine.py)
        # Note x[2] is composition, we can get total thickness
        def get_thick(opt_tuple):
            comp = opt_tuple[2]
            return sum(ly.get("thickness_mm", 0.0) for ly in comp)
            
        valid_options.sort(key=lambda x: (-x[1], get_thick(x)))
        best_opt_key = valid_options[0][0]

    if best_opt_key and options_data[best_opt_key].get("available"):
        best_data = options_data[best_opt_key]
        options_data["Option D"] = {
            "available": True,
            "selected_reference": best_opt_key,
            "total_cost": best_data["total_cost"],
            "formatted_cost": best_data["formatted_cost"],
            "cost_per_km": best_data["cost_per_km"],
            "formatted_cost_per_km": best_data["formatted_cost_per_km"],
            "bitumen_t": best_data["bitumen_t"],
            "cement_t": best_data["cement_t"],
            "aggregate_t": best_data["aggregate_t"],
            "layers": best_data["layers"]
        }
    else:
        options_data["Option D"] = {"available": False}

    return {
        "available": has_layers,
        "show_rupees": show_rupees,
        "road_length_m": road_length,
        "carriageway_width_m": carriageway_width,
        "shoulder_width_m": shoulder_width,
        "options": options_data,
        "rates": rates
    }
