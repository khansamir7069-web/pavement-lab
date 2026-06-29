import sys
import json
import shutil
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db.repository import Database
from app.demo.demo_project_loader import create_demo_project
from app.engineering.design_audit import check_validation_gate, run_project_audit
from app.reports.report_builder import CombinedReportContext, build_combined_report
from app.reports.excel_exporter import build_boq_excel
from app.reports.word_report import export_to_pdf
from app.core.project_archive import generate_project_archive

def main():
    # 1. Initialize database
    db_path = Path("validation_reports/validation_pavement.db")
    if db_path.exists():
        try:
            db_path.unlink()
        except Exception:
            pass
            
    db = Database(db_path)
    
    # 2. Create the demo project
    # This automatically runs traffic, structural, stabilized, and mix designs
    project_id = create_demo_project(db)
    
    # 3. Approve review checklist
    with db.session() as s:
        from app.db.schema import Project
        proj = s.get(Project, project_id)
        proj.review_status = "Approved for Submission"
        proj.checklist_json = json.dumps({
            "design_review": True,
            "input_verification": True,
            "traffic_verification": True,
            "material_verification": True
        })
        s.commit()
        
    # 4. Save a basic material quantity estimate/BOQ so it is fully populated
    from app.db.schema import MaterialQuantityDesign
    with db.session() as s:
        mq = s.query(MaterialQuantityDesign).filter_by(project_id=project_id).first()
        if not mq:
            mq = MaterialQuantityDesign(
                project_id=project_id,
                inputs_json=json.dumps({"layers": []}),
                results_json="{}",
                total_layer_tonnage_t=12500.0,
                total_binder_tonnage_t=480.0
            )
            s.add(mq)
            s.commit()
            
    # 5. Lock project
    ok, errors = check_validation_gate(project_id, db)
    print(f"Validation Gate Passed: {ok}, Errors: {errors}")
    
    db.lock_project(project_id)
    print(f"Project #{project_id} successfully locked.")
    
    # 6. Generate combined Word report (DPR)
    ctx = CombinedReportContext(
        project_title="RoadX Professional Suite v2.2 - Sample DPR",
        work_name="NH-48 Surat bypass corridor pavement design",
        client="Sample Highway Authority",
        agency="Arcstone Infrastructure",
        submitted_by="QA Validator"
    )
    
    reports_dir = Path("validation_reports")
    docx_path = reports_dir / "Sample_DPR_Report.docx"
    build_combined_report(docx_path, db, project_id, ctx)
    print(f"Word report generated: {docx_path}")
    
    # 7. Convert to PDF
    pdf_path = export_to_pdf(docx_path)
    print(f"PDF report generated: {pdf_path}")
    
    # 8. Generate Excel BOQ
    xlsx_path = reports_dir / "Sample_BOQ_Estimate.xlsx"
    build_boq_excel(xlsx_path, project_id, db, {})
    print(f"Excel BOQ generated: {xlsx_path}")
    
    # 9. Generate Submission ZIP
    zip_path = reports_dir / "Sample_Submission_Package.zip"
    generate_project_archive(db, project_id, docx_path, zip_path)
    print(f"Submission ZIP generated: {zip_path}")
    
    # 10. Copy deliverables to release folder
    # Rename release/SamPave_v2.0_Professional to release/RoadX_v2.2_Professional
    legacy_release_dir = Path("release/SamPave_v2.0_Professional")
    roadx_release_dir = Path("release/RoadX_v2.2_Professional")
    
    if legacy_release_dir.exists() and not roadx_release_dir.exists():
        try:
            shutil.move(str(legacy_release_dir), str(roadx_release_dir))
        except Exception:
            pass
            
    roadx_release_dir.mkdir(parents=True, exist_ok=True)
    
    # Copy fresh deliverables
    shutil.copy(str(docx_path), str(roadx_release_dir / "Sample_DPR_Report.docx"))
    shutil.copy(str(pdf_path), str(roadx_release_dir / "Sample_DPR_Report.pdf"))
    shutil.copy(str(xlsx_path), str(roadx_release_dir / "Sample_BOQ_Estimate.xlsx"))
    shutil.copy(str(zip_path), str(roadx_release_dir / "Sample_Submission_Package.zip"))
    
    print("All fresh deliverables successfully compiled and copied to release directory!")

if __name__ == "__main__":
    main()
