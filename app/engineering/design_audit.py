from __future__ import annotations

import json
from dataclasses import dataclass
from typing import List, Dict, Any, Optional

@dataclass
class AuditFinding:
    severity: str        # 'info' | 'warning' | 'critical'
    module: str          # 'traffic' | 'subgrade' | 'structural' | 'stabilized' | 'iitpave' | 'mix' | 'boq' | 'submission'
    issue: str
    recommendation: str
    engineering_reason: str

    def to_dict(self) -> dict:
        return {
            "severity": self.severity,
            "module": self.module,
            "issue": self.issue,
            "recommendation": self.recommendation,
            "engineering_reason": self.engineering_reason
        }

@dataclass
class AuditResult:
    score: int
    risk_level: str      # 'GREEN' | 'YELLOW' | 'RED'
    readiness_status: str # 'Ready for Review' | 'Needs Engineer Review' | 'Not Ready'
    findings: List[AuditFinding]

    def to_dict(self) -> dict:
        return {
            "score": self.score,
            "risk_level": self.risk_level,
            "readiness_status": self.readiness_status,
            "findings": [f.to_dict() for f in self.findings]
        }


def run_project_audit(project_id: int, db) -> AuditResult:
    findings: List[AuditFinding] = []
    
    p = db.get_project(project_id)
    if not p:
        return AuditResult(
            score=0,
            risk_level="RED",
            readiness_status="Not Ready",
            findings=[
                AuditFinding(
                    severity="critical",
                    module="submission",
                    issue="Project not found",
                    recommendation="Ensure the project exists and is loaded properly.",
                    engineering_reason="The database query returned no record for this project ID."
                )
            ]
        )

    # 1. Traffic Survey / MSA
    ta = db.latest_traffic_analysis(project_id)
    msa = 0.0
    if not ta:
        findings.append(AuditFinding(
            severity="critical",
            module="traffic",
            issue="Missing traffic analysis",
            recommendation="Conduct and save traffic projection to estimate cumulative MSA.",
            engineering_reason="Traffic projection (MSA) is required to determine the design pavement thickness."
        ))
    else:
        try:
            ta_inputs = json.loads(ta.inputs_json) if ta.inputs_json else {}
        except Exception:
            ta_inputs = {}
            
        initial_cvpd = ta_inputs.get("initial_cvpd", 0.0) or 0.0
        growth_rate_pct = ta_inputs.get("growth_rate_pct", 0.0) or 0.0
        vdf = ta_inputs.get("vdf", None)
        design_life = ta_inputs.get("design_life_years", 0) or 0
        msa = ta.design_msa or 0.0
        
        if initial_cvpd == 0.0:
            findings.append(AuditFinding(
                severity="warning",
                module="traffic",
                issue="Initial CVPD is zero or missing",
                recommendation="Input a valid, non-zero commercial vehicle volume from traffic survey.",
                engineering_reason="Base traffic volume is required to project design life axle repetitions."
            ))
        if growth_rate_pct == 0.0:
            findings.append(AuditFinding(
                severity="warning",
                module="traffic",
                issue="Missing annual growth rate",
                recommendation="Set a realistic growth rate based on regional development or default to 7.5% per IRC:37.",
                engineering_reason="Axle loading grows annually; assuming 0% growth may severely underestimate pavement fatigue."
            ))
        if design_life == 0:
            findings.append(AuditFinding(
                severity="warning",
                module="traffic",
                issue="Missing design life in traffic analysis",
                recommendation="Define standard design life (e.g. 15 or 20 years) for structural projection.",
                engineering_reason="Design life determines cumulative traffic repetition scaling."
            ))
        if vdf is None or vdf == 0.0:
            findings.append(AuditFinding(
                severity="info",
                module="traffic",
                issue="VDF is not explicitly set",
                recommendation="Set custom Vehicle Damage Factor or verify default preset fits actual commercial loading.",
                engineering_reason="Axle configuration distribution determines the damage factor per vehicle."
            ))
            
        if msa < 2.0:
            findings.append(AuditFinding(
                severity="info",
                module="traffic",
                issue="Very low design traffic (< 2.0 MSA)",
                recommendation="Assess if conventional flexible pavement catalogue design remains cost-effective.",
                engineering_reason="For traffic less than 2 MSA, empirical design curves might yield over-designed sections."
            ))
        elif msa > 150.0:
            findings.append(AuditFinding(
                severity="warning",
                module="traffic",
                issue="Very high design traffic (> 150.0 MSA)",
                recommendation="Apply robust mechanistic checks and modified binder criteria.",
                engineering_reason="Extremely high MSA requires specialized crack and rut resistant asphalt design."
            ))

    # 2. Subgrade / CBR
    subgrade_cbr = p.subgrade_cbr
    subgrade_mr = p.subgrade_mr
    
    if subgrade_cbr is None or subgrade_cbr == 0.0:
        findings.append(AuditFinding(
            severity="critical",
            module="subgrade",
            issue="Missing subgrade CBR",
            recommendation="Determine soaked CBR through lab tests and save in Subgrade module.",
            engineering_reason="CBR is the fundamental input for empirical base thickness calculations."
        ))
    else:
        if subgrade_cbr < 5.0:
            findings.append(AuditFinding(
                severity="warning",
                module="subgrade",
                issue="Very low subgrade CBR (< 5%)",
                recommendation="Evaluate soil stabilization (lime/cement) or design a robust capping layer.",
                engineering_reason="CBR values under 5% signify poor subgrade strength, prone to high vertical rutting strains."
            ))
            
        if subgrade_mr is None or subgrade_mr == 0.0:
            findings.append(AuditFinding(
                severity="warning",
                module="subgrade",
                issue="Missing Resilient Modulus (Mr)",
                recommendation="Initialize resilient modulus in the subgrade panel using auto-computation or site values.",
                engineering_reason="Mr represents subgrade elastic response under load and is key for mechanistic validation."
            ))
        elif subgrade_cbr is not None:
            # Consistency check
            if subgrade_cbr <= 5.0:
                calc_mr = 10.0 * subgrade_cbr
            else:
                calc_mr = 17.6 * (subgrade_cbr ** 0.64)
            
            # Allow 10% discrepancy
            if abs(subgrade_mr - calc_mr) > 0.1 * calc_mr:
                findings.append(AuditFinding(
                    severity="warning",
                    module="subgrade",
                    issue="CBR and Resilient Modulus (Mr) are inconsistent",
                    recommendation="Recalculate Mr to align with standard IRC:37 Annex E empirical correlation.",
                    engineering_reason="Significant variance between Mr and CBR values violates empirical correlation guidelines in IRC:37."
                ))

    # 3. Pavement Structural Design
    sd = db.latest_structural_design(project_id)
    has_layers = False
    if not sd:
        findings.append(AuditFinding(
            severity="critical",
            module="structural",
            issue="Structural design is not finalized",
            recommendation="Complete the pavement base layer calculation and save options in Structural Design panel.",
            engineering_reason="Without structural design, no structural layer layout or thicknesses are defined."
        ))
    else:
        has_layers = sd.total_pavement_thickness_mm is not None and sd.total_pavement_thickness_mm > 0.0
        if not has_layers:
            findings.append(AuditFinding(
                severity="critical",
                module="structural",
                issue="Pavement layer layout is empty",
                recommendation="Define and compute layer thicknesses matching target design CBR and MSA.",
                engineering_reason="Total pavement thickness must be positive for execution."
            ))
        else:
            try:
                comp = json.loads(sd.composition_json) if sd.composition_json else []
            except Exception:
                comp = []
                
            for layer in comp:
                name = layer.get("name", "").upper()
                thick = layer.get("thickness_mm", 0.0)
                
                # Check unusually thin layers
                if ("BC" in name or "WEARING" in name) and thick < 30.0:
                    findings.append(AuditFinding(
                        severity="warning",
                        module="structural",
                        issue=f"Unusually thin wearing course: {layer.get('name')} is {thick} mm",
                        recommendation="Increase wearing course (BC) thickness to at least 30 mm per MoRTH specifications.",
                        engineering_reason="Asphalt wearing courses thinner than 30 mm are susceptible to premature weathering and cracking."
                    ))
                elif "DBM" in name and thick < 50.0:
                    findings.append(AuditFinding(
                        severity="warning",
                        module="structural",
                        issue=f"Unusually thin DBM layer: {layer.get('name')} is {thick} mm",
                        recommendation="Increase DBM thickness to at least 50 mm.",
                        engineering_reason="Dense Bituminous Macadam base layer requires a minimum of 50 mm thickness for structural load spreading."
                    ))
                elif ("BASE" in name or "SUBBASE" in name or "WMM" in name or "GSB" in name) and thick < 100.0:
                    findings.append(AuditFinding(
                        severity="warning",
                        module="structural",
                        issue=f"Unusually thin granular base/subbase: {layer.get('name')} is {thick} mm",
                        recommendation="Increase granular base or subbase layer thickness to at least 100 mm.",
                        engineering_reason="Base/subbase layers thinner than 100 mm cannot be compacted properly, leading to structural failures."
                    ))

            # High traffic check
            if msa > 20.0:
                mv = db.latest_mechanistic_validation(project_id)
                if not mv or mv.refused:
                    findings.append(AuditFinding(
                        severity="warning",
                        module="structural",
                        issue="High traffic design (MSA > 20.0) but mechanistic verification is missing",
                        recommendation="Complete IITPAVE mechanistic verification to check critical strains.",
                        engineering_reason="IRC:37-2018 mandates mechanistic design validation using IITPAVE for traffic exceeding 20 MSA."
                    ))

    # 4. Alternative Selection (CTB/CTS)
    stab = db.latest_stabilized_design(project_id)
    if (subgrade_cbr is not None and subgrade_cbr < 5.0) or msa > 30.0:
        if not stab:
            findings.append(AuditFinding(
                severity="info",
                module="stabilized",
                issue="Stabilized design (CTB/CTS) alternative has not been evaluated",
                recommendation="Configure a cement-stabilized base/subbase alternative design to optimize costs.",
                engineering_reason="CTB/CTS bases provide high fatigue resistance, allowing significant bituminous layer thickness reductions."
            ))
            
    if stab:
        try:
            stab_inputs = json.loads(stab.inputs_json) if stab.inputs_json else {}
        except Exception:
            stab_inputs = {}
        # Warn if UCS data is missing
        ucs = stab_inputs.get("ctb_ucs_mpa", 0.0) or 0.0
        if ucs == 0.0:
            findings.append(AuditFinding(
                severity="warning",
                module="stabilized",
                issue="Missing UCS data for stabilized alternative design",
                recommendation="Specify the target 7-day Unconfined Compressive Strength (UCS) for cement treated base.",
                engineering_reason="Cement treated base elastic modulus is empirically derived from its UCS value."
            ))

    # 5. IITPAVE Verification
    mv = db.latest_mechanistic_validation(project_id)
    if not mv:
        findings.append(AuditFinding(
            severity="warning",
            module="iitpave",
            issue="IITPAVE verification is not completed",
            recommendation="Run IITPAVE validation to ensure fatigue and rutting strain criteria are met.",
            engineering_reason="Mechanistic validation verifies that tensile and compressive strains at boundaries are safe."
        ))
    else:
        if mv.refused:
            findings.append(AuditFinding(
                severity="warning",
                module="iitpave",
                issue="IITPAVE run bypassed in decision-support mode",
                recommendation="Configure actual layer parameters and execute a full verification run.",
                engineering_reason="Bypassed validation leaves the structure unverified against mechanistic fatigue models."
            ))
        else:
            # Check results
            try:
                mv_results = json.loads(mv.summary_json) if mv.summary_json else {}
            except Exception:
                mv_results = {}
            
            # If there's fatigue or rutting check that fails
            fatigue_verdict = mv_results.get("fatigue", {}).get("verdict", "") or mv.fatigue_verdict or ""
            rutting_verdict = mv_results.get("rutting", {}).get("verdict", "") or mv.rutting_verdict or ""
            
            if fatigue_verdict == "FAIL" or rutting_verdict == "FAIL":
                findings.append(AuditFinding(
                    severity="critical",
                    module="iitpave",
                    issue="IITPAVE mechanistic verification failed",
                    recommendation="Increase asphalt layer thickness or improve subgrade resilient modulus to pass criteria.",
                    engineering_reason="Excessive strains under loading will lead to premature fatigue cracking or subgrade rutting."
                ))
            elif fatigue_verdict == "PASS" and rutting_verdict == "PASS":
                findings.append(AuditFinding(
                    severity="info",
                    module="iitpave",
                    issue="IITPAVE verification successful",
                    recommendation="Design meets fatigue and rutting criteria under mechanistic verified mode.",
                    engineering_reason="Computed boundary strains are within the limits allowed by IRC:37 fatigue/rutting equations."
                ))

    # 6. Marshall Mix Design
    mix = db.latest_mix_design(project_id)
    if not mix:
        findings.append(AuditFinding(
            severity="warning",
            module="mix",
            issue="Marshall Mix Design is missing",
            recommendation="Define and compute bituminous mix design (gradation, OBC) to finalize materials selection.",
            engineering_reason="Mix design optimization is required to determine compliance of asphalt binder content and air voids."
        ))
    else:
        # Check binder mismatch
        binder_grade = p.binder_grade or ""
        mix_type = p.mix_type or ""
        
        # Mismatch check: if heavy traffic (MSA > 50) and using light binder (VG-10 / VG-30) instead of VG-40 or PMB/CRMB
        if msa > 50.0 and ("VG-30" in binder_grade or "VG-10" in binder_grade):
            findings.append(AuditFinding(
                severity="warning",
                module="mix",
                issue=f"Standard binder {binder_grade} used for high traffic design ({msa:.1f} MSA)",
                recommendation="Consider specifying a modified binder (CRMB-55/60 or PMB) or stiffer binder grade (VG-40).",
                engineering_reason="High shear stress and heavy repetitive wheel loads require modified binders to prevent rutting."
            ))
            
        # Check if DBM/BC missing when required
        if has_layers:
            # project has bituminous base/wear, check if mix design type matches
            if "DBM" not in mix_type and "BC" not in mix_type:
                findings.append(AuditFinding(
                    severity="warning",
                    module="mix",
                    issue="Selected Marshall Mix Type does not match bituminous base/surface layers",
                    recommendation="Verify mix type configuration is matching structural layer materials.",
                    engineering_reason="Mix design type must represent the actual asphalt concrete layers defined in the structural design."
                ))

    # 7. BOQ
    mq = db.latest_material_quantity(project_id)
    if not mq:
        findings.append(AuditFinding(
            severity="warning",
            module="boq",
            issue="BOQ quantity and cost estimate is missing",
            recommendation="Run BOQ calculation to generate materials quantities and costing estimates.",
            engineering_reason="Cost and material estimation are required to complete the detailed project report."
        ))
    else:
        # If material quantities are missing
        if not mq.total_layer_tonnage_t or mq.total_layer_tonnage_t == 0.0:
            findings.append(AuditFinding(
                severity="warning",
                module="boq",
                issue="Missing quantities in BOQ estimate",
                recommendation="Verify BOQ layer-wise details are configured and computed.",
                engineering_reason="Pavement layer quantities are required for construction materials planning."
            ))

    # 8. Submission
    try:
        checklist = json.loads(p.checklist_json) if p.checklist_json else {}
    except Exception:
        checklist = {}
        
    design_rev = checklist.get("design_review", False)
    input_ver = checklist.get("input_verification", False)
    traffic_ver = checklist.get("traffic_verification", False)
    material_ver = checklist.get("material_verification", False)
    
    if not (design_rev and input_ver and traffic_ver and material_ver):
        findings.append(AuditFinding(
            severity="warning",
            module="submission",
            issue="Engineering review checklists are incomplete",
            recommendation="Review and verify all checklists in the Engineering Review panel.",
            engineering_reason="Review checkboxes indicate formal consultant sign-off of inputs and traffic assumptions."
        ))
        
    if not p.locked:
        findings.append(AuditFinding(
            severity="warning",
            module="submission",
            issue="Project is not locked",
            recommendation="Lock the project in the Submission module to prevent accidental modifications.",
            engineering_reason="Locking freezes design parameters, guaranteeing traceability for DPR generation."
        ))
        
    # Check if DPR generated (meaning a report record exists in the DB for this project)
    has_dpr = False
    from app.db.schema import ReportRevisionSnapshotRecord
    with db.session() as s:
        has_dpr = s.scalars(
            s.query(ReportRevisionSnapshotRecord).where(ReportRevisionSnapshotRecord.project_id == project_id)
        ).first() is not None
        
    if not has_dpr:
        findings.append(AuditFinding(
            severity="info",
            module="submission",
            issue="Design Project Report (DPR) has not been exported",
            recommendation="Export the Combined Pavement Design Report to generate the official word document.",
            engineering_reason="The report records final design computations in a signed-off consultancy format."
        ))

    # Scoring calculation
    score = 100
    for f in findings:
        if f.severity == "critical":
            score -= 15
        elif f.severity == "warning":
            score -= 5
        elif f.severity == "info":
            score -= 1
            
    score = max(0, score)
    
    # Risk and Readiness mapping
    critical_count = sum(1 for f in findings if f.severity == "critical")
    warning_count = sum(1 for f in findings if f.severity == "warning")
    
    if critical_count > 0:
        risk_level = "RED"
        readiness_status = "Not Ready"
    elif warning_count > 0:
        risk_level = "YELLOW"
        readiness_status = "Needs Engineer Review"
    else:
        risk_level = "GREEN"
        readiness_status = "Ready for Review"
        
    return AuditResult(
        score=score,
        risk_level=risk_level,
        readiness_status=readiness_status,
        findings=findings
    )
