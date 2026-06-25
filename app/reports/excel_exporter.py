from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Any, List, Optional
import openpyxl
from openpyxl.styles import Font, Alignment, PatternFill, Border, Side
from openpyxl.utils import get_column_letter

from app.engineering.boq_engine import generate_boq, get_material_key, format_indian_currency, DEFAULT_RATES
from app.reports.report_builder import _rehydrate_material_qty, _rehydrate_structural
from app.core.material_quantity import DEFAULT_DENSITY

# Premium Styles
FONT_TITLE = Font(name="Arial", size=16, bold=True, color="1F4E78")
FONT_SUBTITLE = Font(name="Arial", size=10, italic=True, color="595959")
FONT_SECTION = Font(name="Arial", size=12, bold=True, color="1F4E78")
FONT_HEADER = Font(name="Arial", size=10, bold=True, color="FFFFFF")
FONT_DATA = Font(name="Arial", size=10)
FONT_BOLD = Font(name="Arial", size=10, bold=True)
FONT_SMALL = Font(name="Arial", size=9, color="595959")

FILL_HEADER = PatternFill(start_color="1F4E78", end_color="1F4E78", fill_type="solid")
FILL_ZEBRA = PatternFill(start_color="F2F2F2", end_color="F2F2F2", fill_type="solid")
FILL_ACCENT = PatternFill(start_color="D9E1F2", end_color="D9E1F2", fill_type="solid")
FILL_HIGHLIGHT = PatternFill(start_color="FFF2CC", end_color="FFF2CC", fill_type="solid")

ALIGN_LEFT = Alignment(horizontal="left", vertical="center")
ALIGN_RIGHT = Alignment(horizontal="right", vertical="center")
ALIGN_CENTER = Alignment(horizontal="center", vertical="center")

BORDER_THIN = Border(
    left=Side(style='thin', color='BFBFBF'),
    right=Side(style='thin', color='BFBFBF'),
    top=Side(style='thin', color='BFBFBF'),
    bottom=Side(style='thin', color='BFBFBF')
)
BORDER_TOTAL = Border(
    top=Side(style='thin', color='000000'),
    bottom=Side(style='double', color='000000')
)

FORMAT_CURRENCY = '[$₹-4009] #,##,##0.00'
FORMAT_NUMBER = '#,##0.00'
FORMAT_QTY = '#,##0.000'

def autofit_columns(ws):
    for col in ws.columns:
        max_len = 0
        for cell in col:
            val_str = str(cell.value or '')
            if cell.number_format == FORMAT_CURRENCY:
                val_str = f"Rs. {val_str}"
            max_len = max(max_len, len(val_str))
        col_letter = get_column_letter(col[0].column)
        ws.column_dimensions[col_letter].width = max(max_len + 4, 12)

def build_boq_excel(file_path: Path, project_id: int, db, meta: dict) -> Path:
    """Export the multi-sheet BOQ + Cost Estimation Excel report."""
    wb = openpyxl.Workbook()
    # Remove default sheet
    default_sheet = wb.active
    wb.remove(default_sheet)

    # 1. Fetch BOQ calculations
    boq_res = generate_boq(project_id, db)
    
    # Pre-fetch active BOQ if saved
    mq_row = db.latest_material_quantity(project_id)
    active_qty = _rehydrate_material_qty(mq_row)

    # ----------------------------------------------------
    # Sheet 1: Project Summary
    # ----------------------------------------------------
    ws_summary = wb.create_sheet(title="Project Summary")
    ws_summary.views.sheetView[0].showGridLines = True
    
    ws_summary.cell(row=2, column=2, value="PAVEMENT DESIGN ESTIMATION SUMMARY").font = FONT_TITLE
    ws_summary.cell(row=3, column=2, value="Preliminary Engineer Estimate / Consultant BOQ Estimate (Not a Final Tender Estimate)").font = FONT_SUBTITLE
    
    # Metadata Block
    ws_summary.cell(row=5, column=2, value="PROJECT DETAILS").font = FONT_SECTION
    meta_rows = [
        ("Project Work Name", meta.get("work_name", "")),
        ("Client", meta.get("client", "")),
        ("Agency / Authority", meta.get("agency", "")),
        ("Submitted By", meta.get("submitted_by", "")),
        ("Design Standard", meta.get("design_standard", "IRC:37-2018")),
        ("Road Geometry Length", f"{boq_res.get('road_length_m', 1000.0):,.1f} m"),
        ("Carriageway Width", f"{boq_res.get('carriageway_width_m', 7.0):,.2f} m"),
        ("Shoulder Width (each side)", f"{boq_res.get('shoulder_width_m', 1.5):,.2f} m"),
    ]
    
    r_idx = 6
    for label, val in meta_rows:
        c1 = ws_summary.cell(row=r_idx, column=2, value=label)
        c2 = ws_summary.cell(row=r_idx, column=3, value=val)
        c1.font = FONT_BOLD
        c1.border = BORDER_THIN
        c1.fill = FILL_ZEBRA
        c2.font = FONT_DATA
        c2.border = BORDER_THIN
        r_idx += 1

    # Selected Option Cost block
    r_idx += 1
    ws_summary.cell(row=r_idx, column=2, value="RECOMMENDED PAVEMENT OPTION").font = FONT_SECTION
    r_idx += 1
    
    opt_d = boq_res.get("options", {}).get("Option D", {})
    if opt_d.get("available") and boq_res.get("show_rupees"):
        ref = opt_d.get("selected_reference", "Option A")
        cost_val = opt_d.get("total_cost", 0.0)
        cost_per_km = opt_d.get("cost_per_km", 0.0)
        
        detail_rows = [
            ("Selected Option", f"{ref} (Cost Optimized)"),
            ("Thickness Summary", opt_d.get("thickness_summary", "")),
            ("Total Preliminary Estimate", cost_val),
            ("Est. Cost per Kilometre", cost_per_km),
        ]
        for label, val in detail_rows:
            c1 = ws_summary.cell(row=r_idx, column=2, value=label)
            c2 = ws_summary.cell(row=r_idx, column=3, value=val)
            c1.font = FONT_BOLD
            c1.border = BORDER_THIN
            c1.fill = FILL_ACCENT
            c2.font = FONT_BOLD if "Estimate" in label else FONT_DATA
            c2.border = BORDER_THIN
            if isinstance(val, (int, float)):
                c2.number_format = FORMAT_CURRENCY
                c2.alignment = ALIGN_RIGHT
            r_idx += 1
    else:
        c1 = ws_summary.cell(row=r_idx, column=2, value="Status")
        c2 = ws_summary.cell(row=r_idx, column=3, value="rupee costs only shown if geometry + rates + layer data are saved.")
        c1.font = FONT_BOLD; c1.border = BORDER_THIN
        c2.font = FONT_DATA; c2.border = BORDER_THIN
        r_idx += 1
        
    autofit_columns(ws_summary)

    # ----------------------------------------------------
    # Sheet 2: Quantity Abstract (Active project BOQ)
    # ----------------------------------------------------
    ws_qty = wb.create_sheet(title="Quantity Abstract")
    ws_qty.views.sheetView[0].showGridLines = True
    
    ws_qty.cell(row=2, column=2, value="BILL OF QUANTITIES (ACTIVE DESIGN)").font = FONT_SECTION
    ws_qty.cell(row=3, column=2, value="Preliminary Engineer Estimate based on active rates").font = FONT_SUBTITLE
    
    headers = ["Sl.", "Layer Type", "Thickness (mm)", "Volume (m³)", "Density (t/m³)", "Quantity", "Unit", "Rate (₹)", "Amount (₹)"]
    for col_idx, h in enumerate(headers, start=2):
        cell = ws_qty.cell(row=5, column=col_idx, value=h)
        cell.font = FONT_HEADER
        cell.fill = FILL_HEADER
        cell.alignment = ALIGN_CENTER
        cell.border = BORDER_THIN

    # Populate active BOQ layers
    db_rates = db.list_material_rates()
    rates_map = {r.material: r for r in db_rates}
    
    row_num = 1
    cur_row = 6
    total_boq_amount = 0.0

    if active_qty:
        for lr in active_qty.layers:
            layer_type = lr.inputs.layer_type
            thick = lr.inputs.thickness_mm
            area = lr.area_m2
            category = lr.category
            density = lr.inputs.density_t_m3 if lr.inputs.density_t_m3 is not None else DEFAULT_DENSITY.get(layer_type, 2.20)
            
            material_key = get_material_key(layer_type)
            vol = area * (thick / 1000.0) if category != "sprayed_coat" else 0.0

            # Calculate Quantity and Rate
            if category == "sprayed_coat":
                qty = lr.binder_tonnage_t
                unit = "Tonne"
                r_info = rates_map.get("Bitumen")
                rate = r_info.rate if r_info else DEFAULT_RATES["Bitumen"]["rate"]
                vol_str, dens_str, thick_str = "—", "—", "—"
            elif layer_type.upper() in ("CTB", "CTS") or material_key == "STABILIZED":
                qty = lr.layer_tonnage_t
                unit = "Tonne"
                # Stabilized constituent rates
                cement_pct = 4.5 if layer_type.upper() == "CTB" else 3.0
                cement_t = qty * cement_pct / 100.0
                agg_t = qty - cement_t
                
                c_rate = rates_map.get("Cement").rate if rates_map.get("Cement") else DEFAULT_RATES["Cement"]["rate"]
                a_rate = rates_map.get("Aggregate").rate if rates_map.get("Aggregate") else DEFAULT_RATES["Aggregate"]["rate"]
                amount_val = (cement_t * c_rate) + (agg_t * a_rate)
                rate = amount_val / qty if qty > 0 else a_rate
                vol_str, dens_str, thick_str = vol, density, thick
            else:
                qty = lr.layer_tonnage_t
                r_info = rates_map.get(material_key)
                unit = r_info.unit if r_info else DEFAULT_RATES.get(material_key, {}).get("unit", "Tonne")
                rate = r_info.rate if r_info else DEFAULT_RATES.get(material_key, {}).get("rate", 0.0)
                if unit.lower() in ("cum", "m3"):
                    qty = vol
                vol_str, dens_str, thick_str = vol, density, thick

            amount_val = qty * rate if not (layer_type.upper() in ("CTB", "CTS") or material_key == "STABILIZED") else amount_val
            total_boq_amount += amount_val

            # Write row cells
            cells = [
                ws_qty.cell(row=cur_row, column=2, value=row_num),
                ws_qty.cell(row=cur_row, column=3, value=layer_type),
                ws_qty.cell(row=cur_row, column=4, value=thick_str),
                ws_qty.cell(row=cur_row, column=5, value=vol_str),
                ws_qty.cell(row=cur_row, column=6, value=dens_str),
                ws_qty.cell(row=cur_row, column=7, value=qty),
                ws_qty.cell(row=cur_row, column=8, value=unit),
                ws_qty.cell(row=cur_row, column=9, value=rate),
                ws_qty.cell(row=cur_row, column=10, value=amount_val)
            ]

            for idx, c in enumerate(cells):
                c.font = FONT_DATA
                c.border = BORDER_THIN
                if cur_row % 2 == 1:
                    c.fill = FILL_ZEBRA
                if idx in (0, 7): # Sl. No, Unit
                    c.alignment = ALIGN_CENTER
                elif idx in (2, 3, 4, 5, 8): # Numbers & Cost
                    c.alignment = ALIGN_RIGHT
                    if idx in (2, 3, 5):
                        c.number_format = FORMAT_NUMBER
                    elif idx == 4:
                        c.number_format = FORMAT_QTY
                    elif idx == 8:
                        c.number_format = FORMAT_CURRENCY
                else:
                    c.alignment = ALIGN_LEFT
                    
            row_num += 1
            cur_row += 1
            
        # Total row
        ws_qty.cell(row=cur_row, column=2, value="").border = BORDER_TOTAL
        ws_qty.cell(row=cur_row, column=3, value="Total Preliminary Estimate").font = FONT_BOLD
        ws_qty.cell(row=cur_row, column=3).border = BORDER_TOTAL
        
        for c_idx in range(4, 10):
            ws_qty.cell(row=cur_row, column=c_idx, value="").border = BORDER_TOTAL

        tot_cell = ws_qty.cell(row=cur_row, column=10, value=total_boq_amount)
        tot_cell.font = FONT_BOLD
        tot_cell.border = BORDER_TOTAL
        tot_cell.number_format = FORMAT_CURRENCY
        tot_cell.alignment = ALIGN_RIGHT
    else:
        # Empty placeholder
        ws_qty.cell(row=cur_row, column=2, value="No active BOQ layers calculated or saved yet.").font = FONT_BOLD
        
    autofit_columns(ws_qty)

    # ----------------------------------------------------
    # Sheet 3: Rate Analysis
    # ----------------------------------------------------
    ws_rates = wb.create_sheet(title="Rate Analysis")
    ws_rates.views.sheetView[0].showGridLines = True

    ws_rates.cell(row=2, column=2, value="UNIT MATERIAL RATES").font = FONT_SECTION
    ws_rates.cell(row=3, column=2, value="NOTE: These rates are sample/default market rates. User must update project-specific market/SOR rates before final submission.").font = FONT_SUBTITLE
    
    r_headers = ["Material / Item", "Unit", "Unit Rate (₹)", "Source / Status"]
    for col_idx, h in enumerate(r_headers, start=2):
        cell = ws_rates.cell(row=5, column=col_idx, value=h)
        cell.font = FONT_HEADER
        cell.fill = FILL_HEADER
        cell.alignment = ALIGN_CENTER
        cell.border = BORDER_THIN
        
    cur_row = 6
    materials_list = ["BC", "DBM", "WMM", "GSB", "Bitumen", "Cement", "Aggregate"]
    for mat in materials_list:
        r_info = rates_map.get(mat)
        unit = r_info.unit if r_info else DEFAULT_RATES.get(mat, {}).get("unit", "Tonne")
        rate = r_info.rate if r_info else DEFAULT_RATES.get(mat, {}).get("rate", 0.0)
        status_str = "Project-Specific Rate" if r_info else "Sample/Default Rate (Needs Update)"
        
        c1 = ws_rates.cell(row=cur_row, column=2, value=mat)
        c2 = ws_rates.cell(row=cur_row, column=3, value=unit)
        c3 = ws_rates.cell(row=cur_row, column=4, value=rate)
        c4 = ws_rates.cell(row=cur_row, column=5, value=status_str)
        
        for c in (c1, c2, c3, c4):
            c.font = FONT_DATA
            c.border = BORDER_THIN
        
        c1.alignment = ALIGN_LEFT
        c2.alignment = ALIGN_CENTER
        c3.alignment = ALIGN_RIGHT
        c3.number_format = FORMAT_CURRENCY
        c4.alignment = ALIGN_LEFT
        if "Default" in status_str:
            c4.font = FONT_SMALL
            c4.fill = FILL_HIGHLIGHT
            
        cur_row += 1
        
    autofit_columns(ws_rates)

    # ----------------------------------------------------
    # Sheet 4: Material Summary
    # ----------------------------------------------------
    ws_summary_mat = wb.create_sheet(title="Material Summary")
    ws_summary_mat.views.sheetView[0].showGridLines = True
    
    ws_summary_mat.cell(row=2, column=2, value="CONSTITUENT MATERIAL DEMAND (ACTIVE DESIGN)").font = FONT_SECTION
    ws_summary_mat.cell(row=3, column=2, value="Aggregated material volumes/weights from active calculations").font = FONT_SUBTITLE
    
    m_headers = ["Material Component", "Total Demand (Tonne)", "Unit Rate (₹)", "Estimated Cost Component (₹)"]
    for col_idx, h in enumerate(m_headers, start=2):
        cell = ws_summary_mat.cell(row=5, column=col_idx, value=h)
        cell.font = FONT_HEADER
        cell.fill = FILL_HEADER
        cell.alignment = ALIGN_CENTER
        cell.border = BORDER_THIN

    # Calculate active quantities
    tot_bitumen = 0.0
    tot_cement = 0.0
    tot_agg = 0.0

    if active_qty:
        for lr in active_qty.layers:
            layer_type = lr.inputs.layer_type
            qty = lr.layer_tonnage_t
            category = lr.category
            
            material_key = get_material_key(layer_type)
            if category == "sprayed_coat":
                tot_bitumen += lr.binder_tonnage_t
            elif layer_type.upper() in ("CTB", "CTS") or material_key == "STABILIZED":
                cement_pct = 4.5 if layer_type.upper() == "CTB" else 3.0
                c_t = qty * cement_pct / 100.0
                a_t = qty - c_t
                tot_cement += c_t
                tot_agg += a_t
            else:
                # Regular layer
                # binder split if bituminous
                binder_pct = 0.0
                if material_key == "BC":
                    binder_pct = 5.5
                elif material_key == "DBM":
                    binder_pct = 4.5
                
                if binder_pct > 0:
                    b_t = qty * binder_pct / 100.0
                    a_t = qty - b_t
                    tot_bitumen += b_t
                    tot_agg += a_t
                else:
                    tot_agg += qty

    bit_rate = rates_map.get("Bitumen").rate if rates_map.get("Bitumen") else DEFAULT_RATES["Bitumen"]["rate"]
    cem_rate = rates_map.get("Cement").rate if rates_map.get("Cement") else DEFAULT_RATES["Cement"]["rate"]
    agg_rate = rates_map.get("Aggregate").rate if rates_map.get("Aggregate") else DEFAULT_RATES["Aggregate"]["rate"]

    mat_rows = [
        ("Bitumen (VG-30/VG-40)", tot_bitumen, bit_rate, tot_bitumen * bit_rate),
        ("Portland Cement", tot_cement, cem_rate, tot_cement * cem_rate),
        ("Stone Aggregate / Granular Material", tot_agg, agg_rate, tot_agg * agg_rate)
    ]

    cur_row = 6
    for name, qty, rate, cost in mat_rows:
        c1 = ws_summary_mat.cell(row=cur_row, column=2, value=name)
        c2 = ws_summary_mat.cell(row=cur_row, column=3, value=qty)
        c3 = ws_summary_mat.cell(row=cur_row, column=4, value=rate)
        c4 = ws_summary_mat.cell(row=cur_row, column=5, value=cost)
        
        for c in (c1, c2, c3, c4):
            c.font = FONT_DATA
            c.border = BORDER_THIN
            
        c1.alignment = ALIGN_LEFT
        c2.alignment = ALIGN_RIGHT; c2.number_format = FORMAT_QTY
        c3.alignment = ALIGN_RIGHT; c3.number_format = FORMAT_CURRENCY
        c4.alignment = ALIGN_RIGHT; c4.number_format = FORMAT_CURRENCY
        cur_row += 1

    autofit_columns(ws_summary_mat)

    # ----------------------------------------------------
    # Sheet 5: Option Comparison
    # ----------------------------------------------------
    ws_comp = wb.create_sheet(title="Option Comparison")
    ws_comp.views.sheetView[0].showGridLines = True
    
    ws_comp.cell(row=2, column=2, value="PAVEMENT DESIGN OPTIONS COST COMPARISON").font = FONT_SECTION
    ws_comp.cell(row=3, column=2, value="Preliminary Engineer Estimate comparing options A, B, C, and D").font = FONT_SUBTITLE
    
    comp_headers = ["Parameter / Metric", "Option A (Conventional)", "Option B (Stabilized)", "Option C (Optimized)", "Option D (Recommended)"]
    for col_idx, h in enumerate(comp_headers, start=2):
        cell = ws_comp.cell(row=5, column=col_idx, value=h)
        cell.font = FONT_HEADER
        cell.fill = FILL_HEADER
        cell.alignment = ALIGN_CENTER
        cell.border = BORDER_THIN

    # Extract metrics
    opts = boq_res.get("options", {})
    metrics = [
        ("Thickness Summary", "thickness_summary", "thickness_summary", "thickness_summary", "thickness_summary"),
        ("Estimated Total Cost (₹)", "total_cost", "total_cost", "total_cost", "total_cost"),
        ("Cost per Kilometre (₹/km)", "cost_per_km", "cost_per_km", "cost_per_km", "cost_per_km"),
        ("Total Bitumen Demand (Tonne)", "bitumen_t", "bitumen_t", "bitumen_t", "bitumen_t"),
        ("Total Cement Demand (Tonne)", "cement_t", "cement_t", "cement_t", "cement_t"),
        ("Total Aggregate Demand (Tonne)", "aggregate_t", "aggregate_t", "aggregate_t", "aggregate_t")
    ]

    opt_keys = ["Option A", "Option B", "Option C", "Option D"]
    cur_row = 6

    for label, *prop_names in metrics:
        ws_comp.cell(row=cur_row, column=2, value=label).font = FONT_BOLD
        ws_comp.cell(row=cur_row, column=2).border = BORDER_THIN
        ws_comp.cell(row=cur_row, column=2).fill = FILL_ZEBRA
        
        for k_idx, opt_k in enumerate(opt_keys, start=3):
            opt_d = opts.get(opt_k, {})
            prop = prop_names[k_idx - 3]
            
            cell = ws_comp.cell(row=cur_row, column=k_idx)
            cell.border = BORDER_THIN
            
            if opt_d.get("available"):
                val = opt_d.get(prop, "—")
                if isinstance(val, (int, float)):
                    cell.value = val
                    cell.alignment = ALIGN_RIGHT
                    if "Cost" in label:
                        cell.number_format = FORMAT_CURRENCY
                    else:
                        cell.number_format = FORMAT_NUMBER
                else:
                    cell.value = str(val)
                    cell.alignment = ALIGN_LEFT
            else:
                cell.value = "—"
                cell.alignment = ALIGN_CENTER
                
        cur_row += 1

    autofit_columns(ws_comp)

    # Save to file
    wb.save(str(file_path))
    return file_path


def build_input_data_excel(file_path: Path, project_id: int, db) -> Path:
    """Export the design input parameters Excel spreadsheet."""
    wb = openpyxl.Workbook()
    # Remove default sheet
    default_sheet = wb.active
    wb.remove(default_sheet)

    p = db.get_project(project_id)
    if not p:
        raise ValueError(f"Project #{project_id} not found.")

    # Sheet 1: Project Info
    ws_meta = wb.create_sheet(title="Project Info")
    ws_meta.views.sheetView[0].showGridLines = True
    ws_meta.cell(row=2, column=2, value="PROJECT INFO & METADATA").font = FONT_SECTION
    
    rows_meta = [
        ("Project Work Name", p.work_name),
        ("Client", p.client.name if p.client else "N/A"),
        ("Location", p.location or "N/A"),
        ("Consultant", p.consultant or "N/A"),
        ("Report Identifier", p.report_id or "N/A"),
        ("Revision Number", f"R{p.revision_number}"),
        ("Created Date", p.created_at.strftime("%Y-%m-%d") if p.created_at else "N/A"),
        ("Review Status", p.review_status or "Draft"),
        ("Checked By", p.checked_by or "N/A"),
        ("Work Order No", p.work_order_no or "N/A"),
        ("Work Order Date", p.work_order_date or "N/A"),
        ("Agency / Authority", p.agency or "N/A"),
        ("Submitted By", p.submitted_by or "N/A")
    ]
    
    r_idx = 4
    for label, val in rows_meta:
        c1 = ws_meta.cell(row=r_idx, column=2, value=label)
        c2 = ws_meta.cell(row=r_idx, column=3, value=val)
        c1.font = FONT_BOLD
        c1.border = BORDER_THIN
        c1.fill = FILL_ZEBRA
        c2.font = FONT_DATA
        c2.border = BORDER_THIN
        c2.alignment = ALIGN_LEFT
        r_idx += 1
    autofit_columns(ws_meta)

    # Sheet 2: Traffic Inputs
    ws_traffic = wb.create_sheet(title="Traffic Inputs")
    ws_traffic.views.sheetView[0].showGridLines = True
    ws_traffic.cell(row=2, column=2, value="TRAFFIC PROJECTION INPUTS").font = FONT_SECTION
    
    ta = db.latest_traffic_analysis(project_id)
    ta_inputs = {}
    ta_results = {}
    if ta:
        if ta.inputs_json:
            try:
                ta_inputs = json.loads(ta.inputs_json)
            except Exception:
                pass
        if ta.results_json:
            try:
                ta_results = json.loads(ta.results_json)
            except Exception:
                pass
            
    rows_traffic = [
        ("Road Category", ta_inputs.get("road_category", p.road_category or "N/A")),
        ("Terrain", ta_inputs.get("terrain", "N/A")),
        ("Lane Configuration", ta_inputs.get("lane_config", p.carriageway or "N/A")),
        ("Initial CVPD (A)", ta_inputs.get("initial_cvpd", 0.0)),
        ("Annual Growth Rate (r, %)", ta_inputs.get("growth_rate_pct", 7.5)),
        ("Design Life (n, years)", ta_inputs.get("design_life_years", p.design_life or 15)),
        ("Vehicle Damage Factor (VDF)", ta_inputs.get("vdf") or ta_results.get("vdf_used") or "N/A"),
        ("Lane Distribution Factor (LDF)", ta_inputs.get("ldf") or ta_results.get("ldf_used") or "N/A"),
        ("Design Traffic (N, MSA)", ta.design_msa if ta else "N/A"),
    ]
    
    r_idx = 4
    for label, val in rows_traffic:
        c1 = ws_traffic.cell(row=r_idx, column=2, value=label)
        c2 = ws_traffic.cell(row=r_idx, column=3, value=val)
        c1.font = FONT_BOLD
        c1.border = BORDER_THIN
        c1.fill = FILL_ZEBRA
        c2.font = FONT_DATA
        c2.border = BORDER_THIN
        if isinstance(val, (int, float)):
            c2.alignment = ALIGN_RIGHT
            c2.number_format = FORMAT_NUMBER
        else:
            c2.alignment = ALIGN_LEFT
        r_idx += 1
    autofit_columns(ws_traffic)

    # Sheet 3: Subgrade Inputs
    ws_subg = wb.create_sheet(title="Subgrade Inputs")
    ws_subg.views.sheetView[0].showGridLines = True
    ws_subg.cell(row=2, column=2, value="SUBGRADE DESIGN INPUTS").font = FONT_SECTION
    
    rows_subg = [
        ("Subgrade CBR (%)", p.subgrade_cbr or "N/A"),
        ("Resilient Modulus Mr (MPa)", p.subgrade_mr or "N/A")
    ]
    
    r_idx = 4
    for label, val in rows_subg:
        c1 = ws_subg.cell(row=r_idx, column=2, value=label)
        c2 = ws_subg.cell(row=r_idx, column=3, value=val)
        c1.font = FONT_BOLD
        c1.border = BORDER_THIN
        c1.fill = FILL_ZEBRA
        c2.font = FONT_DATA
        c2.border = BORDER_THIN
        if isinstance(val, (int, float)):
            c2.alignment = ALIGN_RIGHT
            c2.number_format = FORMAT_NUMBER
        else:
            c2.alignment = ALIGN_LEFT
        r_idx += 1
    autofit_columns(ws_subg)

    # Sheet 4: Mix Design Inputs
    ws_mix = wb.create_sheet(title="Mix Design Inputs")
    ws_mix.views.sheetView[0].showGridLines = True
    ws_mix.cell(row=2, column=2, value="BITUMINOUS MIX DESIGN INPUTS").font = FONT_SECTION
    
    mix = db.latest_mix_design(project_id)
    rows_mix = []
    if mix:
        rows_mix = [
            ("Optimum Binder Content (OBC, %)", mix.obc_pct or "N/A"),
            ("Marshall Stability (kN)", mix.stability_at_obc_kn or "N/A"),
            ("Marshall Flow (mm)", mix.flow_at_obc_mm or "N/A"),
            ("Air Voids at OBC (%)", mix.air_voids_at_obc_pct or "N/A"),
            ("VMA at OBC (%)", mix.vma_at_obc_pct or "N/A"),
            ("VFB at OBC (%)", mix.vfb_at_obc_pct or "N/A"),
            ("Compliance Result", "PASS" if mix.compliance_pass else "FAIL")
        ]
    else:
        rows_mix = [("Mix Design Data", "Not completed")]

    r_idx = 4
    for label, val in rows_mix:
        c1 = ws_mix.cell(row=r_idx, column=2, value=label)
        c2 = ws_mix.cell(row=r_idx, column=3, value=val)
        c1.font = FONT_BOLD
        c1.border = BORDER_THIN
        c1.fill = FILL_ZEBRA
        c2.font = FONT_DATA
        c2.border = BORDER_THIN
        if isinstance(val, (int, float)):
            c2.alignment = ALIGN_RIGHT
            c2.number_format = FORMAT_NUMBER
        else:
            c2.alignment = ALIGN_LEFT
        r_idx += 1
    autofit_columns(ws_mix)

    wb.save(str(file_path))
    return file_path


def build_layer_summary_excel(file_path: Path, project_id: int, db) -> Path:
    """Export the pavement layer composition and modulus summary Excel spreadsheet."""
    wb = openpyxl.Workbook()
    default_sheet = wb.active
    wb.remove(default_sheet)

    p = db.get_project(project_id)
    if not p:
        raise ValueError(f"Project #{project_id} not found.")

    # Sheet 1: Layer Composition
    ws_layers = wb.create_sheet(title="Layer Composition")
    ws_layers.views.sheetView[0].showGridLines = True
    ws_layers.cell(row=2, column=2, value="PAVEMENT LAYER DETAILS").font = FONT_SECTION

    # Headers
    headers = ["Layer Name", "Material Type", "Thickness (mm)", "Modulus (MPa)", "Poisson's Ratio"]
    for col_idx, h in enumerate(headers, start=2):
        cell = ws_layers.cell(row=4, column=col_idx, value=h)
        cell.font = FONT_HEADER
        cell.fill = FILL_HEADER
        cell.alignment = ALIGN_CENTER
        cell.border = BORDER_THIN

    # Fetch structural design
    sd_row = db.latest_structural_design(project_id)
    structural = _rehydrate_structural(sd_row, db.latest_mechanistic_validation(project_id))
    
    r_idx = 5
    if structural and structural.composition:
        for ly in structural.composition:
            ws_layers.cell(row=r_idx, column=2, value=ly.name).border = BORDER_THIN
            ws_layers.cell(row=r_idx, column=3, value=ly.material or "—").border = BORDER_THIN
            
            c_thick = ws_layers.cell(row=r_idx, column=4, value=ly.thickness_mm)
            c_thick.border = BORDER_THIN
            c_thick.number_format = FORMAT_NUMBER
            c_thick.alignment = ALIGN_RIGHT
            
            c_mod = ws_layers.cell(row=r_idx, column=5, value=ly.modulus_mpa)
            c_mod.border = BORDER_THIN
            c_mod.number_format = FORMAT_NUMBER
            c_mod.alignment = ALIGN_RIGHT
            
            c_poi = ws_layers.cell(row=r_idx, column=6, value=ly.poisson)
            c_poi.border = BORDER_THIN
            c_poi.number_format = FORMAT_NUMBER
            c_poi.alignment = ALIGN_RIGHT
            r_idx += 1
            
        # Total Row
        ws_layers.cell(row=r_idx, column=2, value="TOTAL THICKNESS").font = FONT_BOLD
        ws_layers.cell(row=r_idx, column=2).border = BORDER_TOTAL
        ws_layers.cell(row=r_idx, column=3, value="—").border = BORDER_TOTAL
        
        c_tot = ws_layers.cell(row=r_idx, column=4, value=structural.total_pavement_thickness_mm)
        c_tot.font = FONT_BOLD
        c_tot.border = BORDER_TOTAL
        c_tot.number_format = FORMAT_NUMBER
        c_tot.alignment = ALIGN_RIGHT
        
        ws_layers.cell(row=r_idx, column=5, value="—").border = BORDER_TOTAL
        ws_layers.cell(row=r_idx, column=6, value="—").border = BORDER_TOTAL
    else:
        # Empty placeholder
        ws_layers.cell(row=r_idx, column=2, value="No active design layer composition recorded").border = BORDER_THIN
        ws_layers.merge_cells(start_row=r_idx, start_column=2, end_row=r_idx, end_column=6)
        
    autofit_columns(ws_layers)

    # Sheet 2: Stabilized Design CTB/CTS (if available)
    ws_stab = wb.create_sheet(title="Stabilized Details")
    ws_stab.views.sheetView[0].showGridLines = True
    ws_stab.cell(row=2, column=2, value="STABILIZED PAVEMENT LAYERS (CTB/CTS)").font = FONT_SECTION
    
    stab_row = db.latest_stabilized_design(project_id)
    has_stab = False
    rows_stab = []
    if stab_row and stab_row.results_json:
        try:
            res = json.loads(stab_row.results_json)
            inputs = res.get("inputs", {})
            rows_stab = [
                ("CTB Thickness (mm)", inputs.get("ctb_thickness_mm", "—")),
                ("CTB Modulus (MPa)", inputs.get("ctb_modulus_mpa", "—")),
                ("CTS Thickness (mm)", inputs.get("cts_thickness_mm", "—")),
                ("CTS Modulus (MPa)", inputs.get("cts_modulus_mpa", "—")),
                ("Comparison Mode", res.get("validation_mode", "—"))
            ]
            has_stab = True
        except Exception:
            pass
            
    if not has_stab:
        rows_stab = [("Stabilized Design", "Not completed")]
        
    r_idx = 4
    for label, val in rows_stab:
        c1 = ws_stab.cell(row=r_idx, column=2, value=label)
        c2 = ws_stab.cell(row=r_idx, column=3, value=val)
        c1.font = FONT_BOLD
        c1.border = BORDER_THIN
        c1.fill = FILL_ZEBRA
        c2.font = FONT_DATA
        c2.border = BORDER_THIN
        if isinstance(val, (int, float)):
            c2.alignment = ALIGN_RIGHT
            c2.number_format = FORMAT_NUMBER
        else:
            c2.alignment = ALIGN_LEFT
        r_idx += 1
    autofit_columns(ws_stab)

    # Sheet 3: Mechanistic Validation (IITPAVE result)
    ws_mech = wb.create_sheet(title="IITPAVE Validation")
    ws_mech.views.sheetView[0].showGridLines = True
    ws_mech.cell(row=2, column=2, value="IITPAVE MECHANISTIC CHECK RESULTS").font = FONT_SECTION
    
    mech = db.latest_mechanistic_validation(project_id)
    rows_mech = []
    if mech and not mech.refused:
        is_mock = "Demo verification example only" in (mech.notes or "")
        mode_val = "Decision Support Mode (Demo Run)" if is_mock else "Mechanistic Verified Mode"
        rows_mech = [
            ("Fatigue Life (MSA)", mech.fatigue_life_msa or "N/A"),
            ("Rutting Life (MSA)", mech.rutting_life_msa or "N/A"),
            ("Design Life (MSA)", mech.design_msa or "N/A"),
            ("Fatigue Check Verdict", mech.fatigue_verdict or "N/A"),
            ("Rutting Check Verdict", mech.rutting_verdict or "N/A"),
            ("Computed Tensile Strain (Microstrain)", mech.tensile_strain_micro or "—"),
            ("Computed Compressive Strain (Microstrain)", mech.compressive_strain_micro or "—"),
            ("Verification Mode", mode_val)
        ]
        if is_mock:
            rows_mech.append(("Note", "Demo verification example only — not actual IITPAVE execution."))
    else:
        rows_mech = [("IITPAVE Verification", "Not performed / Decision Support Mode")]
        
    r_idx = 4
    for label, val in rows_mech:
        c1 = ws_mech.cell(row=r_idx, column=2, value=label)
        c2 = ws_mech.cell(row=r_idx, column=3, value=val)
        c1.font = FONT_BOLD
        c1.border = BORDER_THIN
        c1.fill = FILL_ZEBRA
        c2.font = FONT_DATA
        c2.border = BORDER_THIN
        if isinstance(val, (int, float)):
            c2.alignment = ALIGN_RIGHT
            c2.number_format = FORMAT_NUMBER
        else:
            c2.alignment = ALIGN_LEFT
        r_idx += 1
    autofit_columns(ws_mech)

    wb.save(str(file_path))
    return file_path
