"""Material Quantity — Word section + standalone docx builder (Phase 7).

Reuses ``_docx_common`` helpers and the Phase-6 ``CodeRef`` registry — no
new docx primitives, no new code-citation strings.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH

from app.core import MaterialQuantityResult
from app.core.material_quantity import REFERENCES as ENGINE_REFS

from ._docx_common import (
    add_code_references,
    add_heading,
    add_kv_table,
    add_note,
    add_p,
    add_signature_block,
    add_table,
    new_portrait_document,
)


@dataclass(frozen=True, slots=True)
class MaterialQuantityReportContext:
    project_title: str = ""
    work_name: str = ""
    work_order_no: str = ""
    work_order_date: str = ""
    client: str = ""
    agency: str = ""
    submitted_by: str = ""
    lab_name: str = "Pavement Laboratory"
    report_date: str = field(default_factory=lambda: datetime.now().strftime("%d-%b-%Y"))


def write_material_quantity_section(
    doc: Document,
    ctx: MaterialQuantityReportContext,
    result: MaterialQuantityResult,
    *, include_header: bool = True,
    db = None
) -> None:
    if include_header:
        add_heading(doc, "BILL OF MATERIAL QUANTITIES",
                    level=1, align=WD_ALIGN_PARAGRAPH.CENTER)
        if ctx.project_title:
            add_p(doc, ctx.project_title, bold=True, size=12,
                  align=WD_ALIGN_PARAGRAPH.CENTER)
        add_p(doc,
              "Quantities estimated per MoRTH Section 400 / 500 and IRC:111 "
              "default densities and spray rates. Job-Mix Formula and "
              "lab-verified densities supersede the defaults shown here.",
              italic=True, size=10, align=WD_ALIGN_PARAGRAPH.CENTER)
        add_p(doc, f"{ctx.lab_name}  •  Report Date: {ctx.report_date}",
              size=10, align=WD_ALIGN_PARAGRAPH.CENTER)
        add_heading(doc, "Project Information", level=2)
        add_kv_table(doc, (
            ("Name of Work",     ctx.work_name),
            ("Work Order No.",   ctx.work_order_no),
            ("Work Order Date",  ctx.work_order_date),
            ("Client",           ctx.client),
            ("Agency",           ctx.agency),
            ("Submitted By",     ctx.submitted_by),
        ))

    # Retrieve Rates
    rates = {}
    db_rates = []
    if db:
        try:
            db_rates = db.list_material_rates()
            rates = {rate.material: {"rate": rate.rate, "unit": rate.unit} for rate in db_rates}
        except Exception:
            pass
            
    from app.engineering.boq_engine import DEFAULT_RATES, get_material_key, format_indian_currency
    for k, v in DEFAULT_RATES.items():
        if k not in rates:
            rates[k] = v

    # Per-layer breakdown
    add_heading(doc, "Layer-wise Breakdown (Compacted & Loose Volumes)", level=2)
    rows: list[list[str]] = []
    
    total_compacted_vol = 0.0
    total_loose_vol = 0.0
    total_bitumen = 0.0
    total_cement = 0.0
    total_filler = 0.0
    total_aggregate = 0.0
    total_cost = 0.0
    
    traceability_steps = []
    
    for lr in result.layers:
        inp = lr.inputs
        density = (inp.density_t_m3 if inp.density_t_m3 is not None else "(default)")
        binder = (f"{inp.binder_pct:.2f}" if inp.binder_pct is not None else ("—" if lr.category != "bituminous_mix" else "(default)"))
        spray = (f"{inp.spray_rate_kgm2:.3f}" if inp.spray_rate_kgm2 is not None else ("(default)" if lr.category == "sprayed_coat" else "—"))
        
        # Compacted & Loose Volumes
        vol = lr.compacted_volume_m3
        loose_vol = lr.loose_volume_m3
        
        total_compacted_vol += vol
        total_loose_vol += loose_vol
        total_bitumen += lr.binder_tonnage_t
        total_cement += lr.cement_tonnage_t
        total_filler += lr.filler_tonnage_t
        total_aggregate += lr.aggregate_tonnage_t
        
        # Calculate cost
        rate_source = "Preliminary Estimate"
        material_key = get_material_key(inp.layer_type)
        if lr.category == "sprayed_coat":
            qty = lr.binder_tonnage_t
            unit = "Tonne"
            r_info = rates.get("Bitumen", DEFAULT_RATES["Bitumen"])
            rate_val = r_info.get("rate", 0.0)
            if db and "Bitumen" in [r.material for r in db_rates]:
                rate_source = "Project rate"
            amount = qty * rate_val
        elif inp.layer_type.upper() in ("CTB", "CTS") or material_key == "STABILIZED":
            qty = lr.layer_tonnage_t
            unit = "Tonne"
            cement_pct = 4.5 if inp.layer_type.upper() == "CTB" else 3.0
            if inp.binder_pct is not None and inp.binder_pct > 0.0:
                cement_pct = inp.binder_pct
            cement_t = qty * cement_pct / 100.0
            agg_t = qty - cement_t
            c_rate = rates.get("Cement", {}).get("rate", DEFAULT_RATES["Cement"]["rate"])
            agg_rate = rates.get("Aggregate", {}).get("rate", DEFAULT_RATES["Aggregate"]["rate"])
            if db and "Cement" in [r.material for r in db_rates] and "Aggregate" in [r.material for r in db_rates]:
                rate_source = "Project rate"
            amount = (cement_t * c_rate) + (agg_t * agg_rate)
            rate_val = amount / qty if qty > 0 else agg_rate
        else:
            qty = lr.layer_tonnage_t
            r_info = rates.get(material_key, DEFAULT_RATES.get(material_key, {}))
            unit = r_info.get("unit", "Tonne")
            rate_val = r_info.get("rate", 0.0)
            if db and material_key in [r.material for r in db_rates]:
                rate_source = "Project rate"
            if unit.lower() in ("cum", "m3"):
                qty = vol
            amount = qty * rate_val
            
        total_cost += amount
        
        # Traceability
        waste_pct = inp.waste_pct
        if lr.category == "sprayed_coat":
            tr = f"• {inp.layer_type}: Bitumen Tonnage ({qty:.2f} t) = Area ({lr.area_m2:.1f} m²) × Spray Rate ({inp.spray_rate_kgm2 or 0.25:.2f} kg/m² / 1000)"
        else:
            tr = f"• {inp.layer_type}: Compacted Vol ({vol:.1f} m³) = L ({inp.length_m:.1f} m) × W ({inp.width_m:.1f} m) × Thickness ({inp.thickness_mm:.0f} mm / 1000); " \
                 f"Tonnage ({lr.layer_tonnage_t:.2f} t) = Vol × Density ({density if isinstance(density, str) else f'{density:.2f}'} t/m³) × Waste ({1 + waste_pct/100:.2f}); " \
                 f"Loose Vol ({loose_vol:.1f} m³) = Compacted Vol × bulking factor"
        traceability_steps.append(tr)

        rows.append([
            inp.layer_type,
            f"{inp.length_m:g}", f"{inp.width_m:g}",
            f"{inp.thickness_mm:g}" if lr.category != "sprayed_coat" else "—",
            f"{vol:.1f}" if lr.category != "sprayed_coat" else "—",
            f"{loose_vol:.1f}" if lr.category != "sprayed_coat" else "—",
            str(density) if isinstance(density, str) else f"{density:g}",
            f"₹{rate_val:,.2f}",
            f"₹{amount:,.2f}"
        ])
        
    add_table(doc,
        ["Layer", "L (m)", "W (m)", "t (mm)", "Comp (m³)", "Loose (m³)", "ρ (t/m³)", "Rate", "Amount"],
        rows,
    )

    # Cost Estimation totals
    add_heading(doc, "Preliminary Pavement Cost Estimate (GST & Grand Total)", level=2)
    gst_val = total_cost * 0.18
    grand_total = total_cost + gst_val
    
    add_kv_table(doc, (
        ("Pavement Subtotal Amount",  f"₹{total_cost:,.2f}"),
        ("GST (18% tax)",            f"₹{gst_val:,.2f}"),
        ("Grand Total Estimated Cost", f"₹{grand_total:,.2f}"),
    ))
    
    add_p(doc, "* Note: All cost values are labeled as a Preliminary Engineering Estimate and do not represent final contractor or commercial tender figures.", italic=True, size=9)

    # Material Tonnage Splits
    add_heading(doc, "Material Consumption Splits", level=2)
    add_kv_table(doc, (
        ("Total Stone Aggregates",  f"{total_aggregate:.2f} t"),
        ("Total Bitumen Binder",    f"{total_bitumen:.2f} t"),
        ("Total Cement Binder",     f"{total_cement:.2f} t"),
        ("Total Mineral Filler",    f"{total_filler:.2f} t"),
    ))

    # Quantity Traceability Log
    add_heading(doc, "Pavement Quantity Traceability Log", level=2)
    for step in traceability_steps:
        add_p(doc, step, size=9)

    # BOQ Validation Status
    errors = []
    warnings = []
    
    for lr in result.layers:
        if lr.inputs.length_m <= 0 or lr.inputs.width_m <= 0:
            errors.append(f"Negative or zero geometry detected for layer '{lr.inputs.layer_type}'.")
            
    if db and result.inputs.project_id:
        sd = db.latest_structural_design(result.inputs.project_id)
        if sd:
            try:
                comp = json.loads(sd.composition_json) if isinstance(sd.composition_json, str) else sd.composition_json
            except Exception:
                comp = []
            
            struct_thicknesses = {}
            for s_ly in comp:
                s_name = s_ly.get("name", "").upper()
                struct_thicknesses[s_name] = float(s_ly.get("thickness_mm", 0.0))
                
            for lr in result.layers:
                layer_type = lr.inputs.layer_type
                if layer_type in ("Prime Coat", "Tack Coat"):
                    continue
                matched_s_name = None
                for s_name in struct_thicknesses:
                    if layer_type.upper() in s_name or s_name in layer_type.upper():
                        matched_s_name = s_name
                        break
                if matched_s_name:
                    s_thick = struct_thicknesses[matched_s_name]
                    if abs(lr.inputs.thickness_mm - s_thick) > 0.1:
                        warnings.append(
                            f"Thickness mismatch for '{layer_type}': "
                            f"BOQ = {lr.inputs.thickness_mm:.0f} mm, Structural Design = {s_thick:.0f} mm."
                        )
                else:
                    warnings.append(f"Layer '{layer_type}' in BOQ does not match any layer in the approved structural design.")
        else:
            errors.append("No approved structural design found to validate thicknesses.")
            
    val_status = "PASS" if not errors else "FAIL"
    add_heading(doc, f"BOQ Validation: {val_status}", level=2)
    if errors:
        add_p(doc, "Critical Validation Errors:", bold=True, size=10)
        for e in errors:
            add_p(doc, f"❌ {e}", size=9)
    if warnings:
        add_p(doc, "Validation Warnings:", bold=True, size=10)
        for w in warnings:
            add_p(doc, f"⚠️ {w}", size=9)
    if not errors and not warnings:
        add_p(doc, "All validation rules passed successfully.", italic=True, size=9)

    add_code_references(doc, ENGINE_REFS, heading="References")

    if result.notes:
        add_note(doc, result.notes)


def build_material_quantity_docx(
    out_path: Path,
    ctx: MaterialQuantityReportContext,
    result: MaterialQuantityResult,
    db = None
) -> Path:
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    doc = new_portrait_document()
    write_material_quantity_section(doc, ctx, result, include_header=True, db=db)
    add_signature_block(doc)
    doc.save(out_path)
    return out_path
