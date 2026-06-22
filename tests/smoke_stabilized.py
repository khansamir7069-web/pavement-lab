"""Smoke test for Phase L: Stabilized Pavement Module.

Headless. Verifies database save/load, standalone export, and combined report inclusion.
"""
import sys
import traceback
from pathlib import Path

OUT = Path(__file__).with_name("smoke_stabilized_result.txt")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

lines: list[str] = []
try:
    from app.db import get_db
    from app.core.stabilized_design import StabilizedInput, compute_stabilized_design
    from app.reports.stabilized_report import StabilizedReportContext, build_stabilized_docx
    from app.reports.report_builder import build_combined_report, CombinedReportContext
    from docx import Document

    db = get_db()
    lines.append("Database connected successfully")

    # 1. Create a dummy project
    p = db.create_project(
        work_name="Stabilized Pavement Test Work",
        agency="Test Agency",
        submitted_by="Test Engineer",
    )
    project_id = p.id
    lines.append(f"Project created with ID: {project_id}")

    # 2. Run computation
    inp = StabilizedInput(
        ctb_thickness_mm=120.0,
        ctb_modulus_mpa=5000.0,
        ctb_ucs_mpa=4.2,
        ctb_poisson=0.25,
        cts_class="C3/4",
        cts_thickness_mm=100.0,
        cts_modulus_mpa=3000.0,
        cts_poisson=0.25,
        gsb_thickness_mm=150.0,
        bituminous_thickness_mm=100.0,
        flexible_design_msa=15.0,
        flexible_subgrade_cbr=6.0,
        notes="Empirically suggested, mechanistic check required.",
    )
    result = compute_stabilized_design(inp, has_mechanistic_validation=False)
    lines.append(f"Calculation succeeded. Savings: {result.thickness_savings_mm:.0f} mm")

    # 3. Save to database
    row = db.save_stabilized_design(project_id=project_id, result=result)
    db.set_module_status(project_id, "stabilized", "complete")
    lines.append(f"Saved stabilized design ID: {row.id}")

    # 4. Load from database and verify values
    saved = db.latest_stabilized_design(project_id)
    assert saved is not None, "Failed to load saved design"
    lines.append("Loaded saved stabilized design successfully")

    # 5. Export Standalone report
    ctx_stand = StabilizedReportContext(
        project_title="Stabilized Design Test",
        work_name=p.work_name,
        client="",
        agency=p.agency or "",
        submitted_by=p.submitted_by or "",
    )
    out_standalone = Path("build/smoke_stabilized_standalone.docx").resolve()
    out_standalone.parent.mkdir(parents=True, exist_ok=True)
    build_stabilized_docx(out_standalone, ctx_stand, result)
    lines.append(f"Standalone report written: {out_standalone.name} ({out_standalone.stat().st_size} bytes)")

    # Verify standalone report contents
    doc = Document(str(out_standalone))
    paras = [para.text for para in doc.paragraphs]
    has_header = any("STABILIZED PAVEMENT DESIGN" in text for text in paras)
    has_disclaimer = any("This design is for decision support only" in text for text in paras)
    lines.append(f"Standalone report has header: {has_header}")
    lines.append(f"Standalone report has disclaimer: {has_disclaimer}")
    assert has_header, "Standalone header missing"
    assert has_disclaimer, "Standalone disclaimer missing"

    # 6. Export Combined report
    ctx_comb = CombinedReportContext(
        project_title="Combined Design Test",
        work_name=p.work_name,
        client="",
        agency=p.agency or "",
        submitted_by=p.submitted_by or "",
        mix_type_key="DBM-II",
    )
    out_combined = Path("build/smoke_stabilized_combined.docx").resolve()
    build_combined_report(out_combined, db, project_id, ctx_comb)
    lines.append(f"Combined report written: {out_combined.name} ({out_combined.stat().st_size} bytes)")

    # Verify combined report has Stabilized section
    doc_comb = Document(str(out_combined))
    comb_paras = [para.text for para in doc_comb.paragraphs]
    has_comb_header = any("STABILIZED PAVEMENT DESIGN" in text for text in comb_paras)
    has_comb_mode = any("Validation Mode:" in text for text in comb_paras)
    lines.append(f"Combined report contains stabilized header: {has_comb_header}")
    lines.append(f"Combined report contains validation mode: {has_comb_mode}")
    assert has_comb_header, "Combined stabilized header missing"

    lines.append("STABILIZED SMOKE OK")
except Exception:
    lines.append("STABILIZED SMOKE FAIL")
    lines.append(traceback.format_exc())
finally:
    OUT.write_text("\n".join(lines), encoding="utf-8")
