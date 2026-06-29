from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Dict, Any, Optional

# Central Engineering Validation Config Defaults
VALIDATION_CONFIG = {
    "traffic": {
        "min_growth_rate_pct": 2.0,
        "max_growth_rate_pct": 12.0,
        "min_design_life_years": 10,
        "max_design_life_years": 30,
        "min_msa": 2.0,
        "max_msa": 150.0,
    },
    "subgrade": {
        "min_cbr_pct": 2.0,
        "max_cbr_pct": 15.0,
        "min_mr_mpa": 20.0,
        "max_mr_mpa": 120.0,
        "mr_cbr_tolerance_pct": 10.0,  # 10% tolerance for consistency check
    },
    "structural": {
        "min_bc_thick_mm": 30.0,
        "max_bc_thick_mm": 50.0,
        "min_dbm_thick_mm": 50.0,
        "max_dbm_thick_mm": 150.0,
        "min_wmm_thick_mm": 75.0,
        "max_wmm_thick_mm": 250.0,
        "min_gsb_thick_mm": 100.0,
        "max_gsb_thick_mm": 300.0,
    },
    "mix_design": {
        "min_stability_kn": 9.0,
        "min_flow_mm": 2.0,
        "max_flow_mm": 4.0,
        "min_air_voids_pct": 3.0,
        "max_air_voids_pct": 5.0,
        "min_obc_pct": 4.0,
        "max_obc_pct": 7.0,
    }
}


@dataclass
class AuditFinding:
    severity: str        # 'critical' | 'major' | 'warning' | 'info'
    module: str          # 'traffic' | 'subgrade' | 'structural' | 'stabilized' | 'iitpave' | 'mix' | 'boq' | 'submission'
    issue: str
    recommendation: str
    engineering_reason: str
    navigation_key: str = "Traffic"  # Tab redirection key
    technical_details: str = ""

    def to_dict(self) -> dict:
        return {
            "severity": self.severity,
            "module": self.module,
            "issue": self.issue,
            "recommendation": self.recommendation,
            "engineering_reason": self.engineering_reason,
            "navigation_key": self.navigation_key,
            "technical_details": self.technical_details
        }


@dataclass
class AuditResult:
    score: int
    risk_level: str      # 'GREEN' | 'YELLOW' | 'RED'
    readiness_status: str # 'Ready for Review' | 'Needs Engineer Review' | 'Not Ready'
    findings: List[AuditFinding]
    # P5 new fields
    completeness_score: int = 0
    completeness_explanation: str = ""
    consistency_score: int = 0
    consistency_explanation: str = ""
    mechanistic_score: int = 0
    mechanistic_explanation: str = ""
    documentation_score: int = 0
    documentation_explanation: str = ""
    submission_score: int = 0
    submission_explanation: str = ""
    final_recommendation: str = "NOT READY FOR SUBMISSION"
    timestamp: str = ""
    module_statuses: Dict[str, str] = field(default_factory=dict)
    consistency_checks: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "score": self.score,
            "risk_level": self.risk_level,
            "readiness_status": self.readiness_status,
            "findings": [f.to_dict() for f in self.findings],
            "completeness_score": self.completeness_score,
            "completeness_explanation": self.completeness_explanation,
            "consistency_score": self.consistency_score,
            "consistency_explanation": self.consistency_explanation,
            "mechanistic_score": self.mechanistic_score,
            "mechanistic_explanation": self.mechanistic_explanation,
            "documentation_score": self.documentation_score,
            "documentation_explanation": self.documentation_explanation,
            "submission_score": self.submission_score,
            "submission_explanation": self.submission_explanation,
            "final_recommendation": self.final_recommendation,
            "timestamp": self.timestamp,
            "module_statuses": self.module_statuses,
            "consistency_checks": self.consistency_checks
        }


def run_project_audit(project_id: int, db) -> AuditResult:
    findings: List[AuditFinding] = []
    consistency_checks: List[Dict[str, Any]] = []
    
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
                    engineering_reason="The database query returned no record for this project ID.",
                    navigation_key="Submission Center"
                )
            ],
            final_recommendation="NOT READY FOR SUBMISSION",
            timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        )

    # 0. Load manual overrides
    overrides = []
    if p.override_history_json:
        try:
            if isinstance(p.override_history_json, str):
                overrides = json.loads(p.override_history_json)
            else:
                overrides = p.override_history_json
        except Exception:
            pass

    def has_override(field_name: str) -> Optional[dict]:
        for o in overrides:
            if o.get("field_name") == field_name:
                return o
        return None

    # Track module completions
    mod_statuses = {
        "traffic": "INCOMPLETE",
        "subgrade": "INCOMPLETE",
        "structural": "INCOMPLETE",
        "iitpave": "INCOMPLETE",
        "mix": "INCOMPLETE",
        "boq": "INCOMPLETE",
        "submission": "INCOMPLETE",
    }

    # 1. Traffic Survey / MSA
    ta = db.latest_traffic_analysis(project_id)
    msa = 0.0
    initial_cvpd = 0.0
    growth_rate_pct = 0.0
    vdf = 0.0
    ldf = 0.0
    design_life = 0
    
    if not ta:
        findings.append(AuditFinding(
            severity="critical",
            module="traffic",
            issue="Missing traffic analysis",
            recommendation="Conduct and save traffic projection to estimate cumulative MSA.",
            engineering_reason="Traffic projection (MSA) is required to determine the design pavement thickness.",
            navigation_key="Traffic"
        ))
    else:
        mod_statuses["traffic"] = "PASS"
        try:
            ta_inputs = json.loads(ta.inputs_json) if ta.inputs_json else {}
        except Exception:
            ta_inputs = {}
            
        initial_cvpd = float(ta_inputs.get("initial_cvpd", 0.0) or 0.0)
        growth_rate_pct = float(ta_inputs.get("growth_rate_pct", 0.0) or 0.0)
        vdf = float(ta_inputs.get("vdf", 0.0) or 0.0)
        ldf = float(ta_inputs.get("ldf", 0.0) or ta_inputs.get("lane_distribution_factor", 0.0) or 0.0)
        design_life = int(ta_inputs.get("design_life_years", 0) or 0)
        msa = ta.design_msa or 0.0
        
        # Validations
        if initial_cvpd <= 0.0:
            findings.append(AuditFinding(
                severity="critical",
                module="traffic",
                issue="Initial CVPD is zero or missing",
                recommendation="Input a valid, non-zero commercial vehicle volume from traffic survey.",
                engineering_reason="Base traffic volume is required to project design life axle repetitions.",
                navigation_key="Traffic"
            ))
            mod_statuses["traffic"] = "FAIL"

        growth_override = has_override("growth_rate_pct")
        if growth_rate_pct < VALIDATION_CONFIG["traffic"]["min_growth_rate_pct"] or growth_rate_pct > VALIDATION_CONFIG["traffic"]["max_growth_rate_pct"]:
            if growth_override:
                findings.append(AuditFinding(
                    severity="warning",
                    module="traffic",
                    issue=f"Growth rate ({growth_rate_pct}%) is outside standard range (2-12%) but accepted via Manual Override.",
                    recommendation=f"Overridden with reason: {growth_override.get('reason')}",
                    engineering_reason="A manual override has been recorded by the engineer, acknowledging this value.",
                    navigation_key="Traffic",
                    technical_details=f"Value: {growth_rate_pct}%, Reason: {growth_override.get('reason')}"
                ))
            else:
                findings.append(AuditFinding(
                    severity="critical",
                    module="traffic",
                    issue=f"Growth rate ({growth_rate_pct}%) is outside standard IRC engineering range (2-12%).",
                    recommendation="Set growth rate between 2.0% and 12.0% or record a manual override with justification.",
                    engineering_reason="Axle growth rates outside typical limits require explicit justification to prevent under/over design.",
                    navigation_key="Traffic"
                ))
                mod_statuses["traffic"] = "FAIL"

        if design_life == 0:
            findings.append(AuditFinding(
                severity="critical",
                module="traffic",
                issue="Missing design life in traffic analysis",
                recommendation="Define standard design life (e.g. 15 or 20 years) for structural projection.",
                engineering_reason="Design life determines cumulative traffic repetition scaling.",
                navigation_key="Traffic"
            ))
            mod_statuses["traffic"] = "FAIL"

        if vdf <= 0.0:
            findings.append(AuditFinding(
                severity="critical",
                module="traffic",
                issue="VDF is zero or missing",
                recommendation="Set custom Vehicle Damage Factor or verify default preset fits commercial loading.",
                engineering_reason="Axle configuration distribution determines the damage factor per vehicle.",
                navigation_key="Traffic"
            ))
            mod_statuses["traffic"] = "FAIL"

        if ldf <= 0.0:
            if msa <= 0.0:
                findings.append(AuditFinding(
                    severity="critical",
                    module="traffic",
                    issue="LDF is zero or missing",
                    recommendation="Specify the Lane Distribution Factor per carriage config.",
                    engineering_reason="LDF scales the design lane repetitions based on lane width.",
                    navigation_key="Traffic"
                ))
                mod_statuses["traffic"] = "FAIL"
            else:
                findings.append(AuditFinding(
                    severity="warning",
                    module="traffic",
                    issue="LDF is not set explicitly in inputs",
                    recommendation="Ensure LDF is specified or verify default presets.",
                    engineering_reason="A default LDF preset was used because none was explicitly specified in the inputs.",
                    navigation_key="Traffic"
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
            engineering_reason="CBR is the fundamental input for empirical base thickness calculations.",
            navigation_key="Subgrade"
        ))
    else:
        mod_statuses["subgrade"] = "PASS"
        if subgrade_cbr < 2.0 or subgrade_cbr > 15.0:
            findings.append(AuditFinding(
                severity="warning",
                module="subgrade",
                issue=f"Subgrade CBR ({subgrade_cbr}%) is outside typical design limits (2-15%).",
                recommendation="Confirm soil properties; low CBR values require stabilization or subgrade cap.",
                engineering_reason="Soaked CBR values below 2% represent extremely weak subgrades that cannot support compaction directly.",
                navigation_key="Subgrade"
            ))
            
        if subgrade_mr is None or subgrade_mr == 0.0:
            findings.append(AuditFinding(
                severity="critical",
                module="subgrade",
                issue="Missing Resilient Modulus (Mr)",
                recommendation="Initialize resilient modulus in the subgrade panel using auto-computation or site values.",
                engineering_reason="Mr represents subgrade elastic response under load and is key for mechanistic validation.",
                navigation_key="Subgrade"
            ))
            mod_statuses["subgrade"] = "FAIL"
        else:
            # CBR to Mr consistency check
            if subgrade_cbr <= 5.0:
                calc_mr = 10.0 * subgrade_cbr
            else:
                calc_mr = 17.6 * (subgrade_cbr ** 0.64)
            
            mr_override = has_override("subgrade_mr")
            tolerance = VALIDATION_CONFIG["subgrade"]["mr_cbr_tolerance_pct"] / 100.0
            if abs(subgrade_mr - calc_mr) > tolerance * calc_mr:
                if mr_override:
                    findings.append(AuditFinding(
                        severity="warning",
                        module="subgrade",
                        issue=f"CBR ({subgrade_cbr}%) and Mr ({subgrade_mr} MPa) are inconsistent but accepted via Manual Override.",
                        recommendation=f"Overridden with reason: {mr_override.get('reason')}",
                        engineering_reason="CBR/Mr inconsistent, manually accepted by engineer.",
                        navigation_key="Subgrade",
                        technical_details=f"CBR={subgrade_cbr}%, Mr={subgrade_mr} MPa, Expected={calc_mr:.1f} MPa"
                    ))
                else:
                    findings.append(AuditFinding(
                        severity="major",
                        module="subgrade",
                        issue=f"CBR ({subgrade_cbr}%) and Mr ({subgrade_mr} MPa) are inconsistent.",
                        recommendation="Recalculate Mr to align with standard IRC:37 Annex E empirical correlation.",
                        engineering_reason="Significant variance between Mr and CBR values violates empirical correlation guidelines in IRC:37.",
                        navigation_key="Subgrade"
                    ))
                    mod_statuses["subgrade"] = "FAIL"

    # 3. Pavement Structural Design
    sd = db.latest_structural_design(project_id)
    has_layers = False
    comp = []
    
    if not sd:
        findings.append(AuditFinding(
            severity="critical",
            module="structural",
            issue="Structural design is not finalized",
            recommendation="Complete the pavement base layer calculation and save options in Structural Design panel.",
            engineering_reason="Without structural design, no structural layer layout or thicknesses are defined.",
            navigation_key="Structural Design"
        ))
    else:
        mod_statuses["structural"] = "PASS"
        has_layers = sd.total_pavement_thickness_mm is not None and sd.total_pavement_thickness_mm > 0.0
        if not has_layers:
            findings.append(AuditFinding(
                severity="critical",
                module="structural",
                issue="Pavement layer layout is empty",
                recommendation="Define and compute layer thicknesses matching target design CBR and MSA.",
                engineering_reason="Total pavement thickness must be positive for execution.",
                navigation_key="Structural Design"
            ))
            mod_statuses["structural"] = "FAIL"
        else:
            try:
                comp = json.loads(sd.composition_json) if sd.composition_json else []
            except Exception:
                comp = []
                
            # Verify Layer order (BC must be above DBM, WMM, GSB)
            layer_ranks = {"BC": 4, "DBM": 3, "BM": 3.5, "WMM": 2, "GSB": 1, "CTB": 2.5, "CTS": 1.5}
            ranks = []
            
            def map_layer_name(cname: str) -> str:
                cname_upper = cname.upper()
                if "BC" in cname_upper or "CONCRETE" in cname_upper or "WEARING" in cname_upper:
                    return "BC"
                if "DBM" in cname_upper or "BINDER" in cname_upper:
                    return "DBM"
                if "WMM" in cname_upper or "WET MIX" in cname_upper:
                    return "WMM"
                if "GSB" in cname_upper or "SUB-BASE" in cname_upper or "SUBBASE" in cname_upper or "GRANULAR" in cname_upper:
                    return "GSB"
                if "CTB" in cname_upper:
                    return "CTB"
                if "CTS" in cname_upper:
                    return "CTS"
                return "DBM"

            for layer in comp:
                name = layer.get("name", "")
                mapped = map_layer_name(name)
                thick = float(layer.get("thickness_mm", 0.0))
                
                # Check unusually thin layers
                if mapped == "BC" and thick < VALIDATION_CONFIG["structural"]["min_bc_thick_mm"]:
                    findings.append(AuditFinding(
                        severity="warning",
                        module="structural",
                        issue=f"Unusually thin wearing course: {name} is {thick} mm",
                        recommendation="Increase wearing course (BC) thickness to at least 30 mm per MoRTH specifications.",
                        engineering_reason="Asphalt wearing courses thinner than 30 mm are susceptible to premature weathering and cracking.",
                        navigation_key="Structural Design"
                    ))
                elif mapped == "DBM" and thick < VALIDATION_CONFIG["structural"]["min_dbm_thick_mm"]:
                    findings.append(AuditFinding(
                        severity="warning",
                        module="structural",
                        issue=f"Unusually thin DBM layer: {name} is {thick} mm",
                        recommendation="Increase DBM thickness to at least 50 mm.",
                        engineering_reason="Dense Bituminous Macadam base layer requires a minimum of 50 mm thickness for structural load spreading.",
                        navigation_key="Structural Design"
                    ))
                elif mapped == "WMM" and thick < VALIDATION_CONFIG["structural"]["min_wmm_thick_mm"]:
                    findings.append(AuditFinding(
                        severity="warning",
                        module="structural",
                        issue=f"Unusually thin WMM base: {name} is {thick} mm",
                        recommendation="Increase WMM thickness to at least 75 mm.",
                        engineering_reason="WMM base thinner than 75 mm cannot be compacted properly.",
                        navigation_key="Structural Design"
                    ))
                elif mapped == "GSB" and thick < VALIDATION_CONFIG["structural"]["min_gsb_thick_mm"]:
                    findings.append(AuditFinding(
                        severity="warning",
                        module="structural",
                        issue=f"Unusually thin GSB subbase: {name} is {thick} mm",
                        recommendation="Increase GSB thickness to at least 100 mm.",
                        engineering_reason="GSB layer thinner than 100 mm fails to prevent subgrade intrusion.",
                        navigation_key="Structural Design"
                    ))

                # Track rank for order check
                r = layer_ranks.get(mapped, 0)
                ranks.append(r)

            # Check layer order consistency (must be strictly descending in rank)
            if ranks != sorted(ranks, reverse=True):
                findings.append(AuditFinding(
                    severity="major",
                    module="structural",
                    issue="Pavement layer sequence order violates standard practice (BC -> DBM -> WMM -> GSB).",
                    recommendation="Reorganize layers in the design panel to place wearing course at top.",
                    engineering_reason="Pavement layers must be arranged in order of stiffness and load-bearing capacity.",
                    navigation_key="Structural Design"
                ))
                mod_statuses["structural"] = "FAIL"

            # Check explainability log exists
            if not sd.traceability_log_json:
                findings.append(AuditFinding(
                    severity="warning",
                    module="structural",
                    issue="Explainability traceability log is missing.",
                    recommendation="Regenerate structural design computation to capture explainability chains.",
                    engineering_reason="Traceability logs are required for auditable design review.",
                    navigation_key="Structural Design"
                ))

            # High traffic check
            if msa > 20.0:
                mv_high = db.latest_mechanistic_validation(project_id)
                if not mv_high or mv_high.refused:
                    findings.append(AuditFinding(
                        severity="warning",
                        module="structural",
                        issue="High traffic design (MSA > 20.0) but mechanistic verification is missing",
                        recommendation="Complete IITPAVE mechanistic verification to check critical strains.",
                        engineering_reason="IRC:37-2018 mandates mechanistic design validation using IITPAVE for traffic exceeding 20 MSA.",
                        navigation_key="Structural Design"
                    ))

    # 4. IITPAVE Verification
    mv = db.latest_mechanistic_validation(project_id)
    if not mv:
        findings.append(AuditFinding(
            severity="critical",
            module="iitpave",
            issue="Mechanistic Verification Incomplete",
            recommendation="Run IITPAVE validation to ensure fatigue and rutting strain criteria are met.",
            engineering_reason="IITPAVE run is missing, leaving structural integrity unverified.",
            navigation_key="IITPAVE Status"
        ))
        mod_statuses["iitpave"] = "INCOMPLETE"
    else:
        mod_statuses["iitpave"] = "PASS"
        if mv.refused:
            findings.append(AuditFinding(
                severity="critical",
                module="iitpave",
                issue="Mechanistic Verification Incomplete",
                recommendation="Execute real IITPAVE production mode validation; IRC Catalogue Design mode is active.",
                engineering_reason="IRC Catalogue Design mode is insufficient for consultancy design validation; real mechanistic validation required.",
                navigation_key="IITPAVE Status"
            ))
            mod_statuses["iitpave"] = "FAIL"
        else:
            try:
                mv_results = json.loads(mv.summary_json) if mv.summary_json else {}
            except Exception:
                mv_results = {}
            
            fatigue_verdict = mv_results.get("fatigue", {}).get("verdict", "") or mv.fatigue_verdict or ""
            rutting_verdict = mv_results.get("rutting", {}).get("verdict", "") or mv.rutting_verdict or ""
            
            if (fatigue_verdict or "").upper() != "PASS" or (rutting_verdict or "").upper() != "PASS":
                findings.append(AuditFinding(
                    severity="critical",
                    module="iitpave",
                    issue="IITPAVE mechanistic verification failed",
                    recommendation="Increase asphalt layer thickness or improve subgrade resilient modulus to pass criteria.",
                    engineering_reason="Excessive strains under loading will lead to premature fatigue cracking or subgrade rutting.",
                    navigation_key="IITPAVE Status"
                ))
                mod_statuses["iitpave"] = "FAIL"

    # 5. Marshall Mix Design
    mix = db.latest_mix_design(project_id)
    if not mix:
        findings.append(AuditFinding(
            severity="warning",
            module="mix",
            issue="Marshall Mix Design is missing",
            recommendation="Define and compute bituminous mix design (gradation, OBC) to finalize materials selection.",
            engineering_reason="Mix design optimization is required to determine compliance of asphalt binder content and air voids.",
            navigation_key="Mix Design"
        ))
    else:
        mod_statuses["mix"] = "PASS"
        stability = float(mix.stability_at_obc_kn or 0.0)
        flow = float(mix.flow_at_obc_mm or 0.0)
        va = float(mix.air_voids_at_obc_pct or 0.0)
        obc = float(mix.obc_pct or 0.0)
        
        if obc <= 0.0:
            findings.append(AuditFinding(
                severity="major",
                module="mix",
                issue="Optimum Binder Content (OBC) is missing",
                recommendation="Run Marshall analysis to compute OBC for target air voids.",
                engineering_reason="Optimum binder percentage is the primary output required for mix design specification.",
                navigation_key="Mix Design"
            ))
        else:
            if stability < VALIDATION_CONFIG["mix_design"]["min_stability_kn"]:
                findings.append(AuditFinding(
                    severity="major",
                    module="mix",
                    issue=f"Low Marshall stability detected: {stability:.1f} kN (Required >= 9.0 kN)",
                    recommendation="Verify mix aggregate gradation and binder properties.",
                    engineering_reason="Low stability implies insufficient structural strength to resist rutting and shear displacement.",
                    navigation_key="Mix Design"
                ))
                
            if flow < VALIDATION_CONFIG["mix_design"]["min_flow_mm"] or flow > VALIDATION_CONFIG["mix_design"]["max_flow_mm"]:
                findings.append(AuditFinding(
                    severity="warning",
                    module="mix",
                    issue=f"Flow value {flow:.1f} mm is outside standard limits (2.0-4.0 mm).",
                    recommendation="Adjust aggregate packing or binder ratio.",
                    engineering_reason="Flow values indicate asphalt strain capability; values too low lead to cracking, too high cause rutting.",
                    navigation_key="Mix Design"
                ))
                
            if va < VALIDATION_CONFIG["mix_design"]["min_air_voids_pct"] or va > VALIDATION_CONFIG["mix_design"]["max_air_voids_pct"]:
                findings.append(AuditFinding(
                    severity="warning",
                    module="mix",
                    issue=f"Mix air voids ({va:.1f}%) are outside standard limits (3-5%).",
                    recommendation="Modify mix compaction parameters.",
                    engineering_reason="Incorrect air voids lead to premature cracking (low binder) or bleeding/plastic flow (high binder).",
                    navigation_key="Mix Design"
                ))

    # 6. BOQ
    mq = db.latest_material_quantity(project_id)
    if not mq:
        findings.append(AuditFinding(
            severity="warning",
            module="boq",
            issue="BOQ quantity and cost estimate is missing",
            recommendation="Run BOQ calculation to generate materials quantities and costing estimates.",
            engineering_reason="Cost and material estimation are required to complete the detailed project report.",
            navigation_key="BOQ"
        ))
    else:
        mod_statuses["boq"] = "PASS"
        if not mq.total_layer_tonnage_t or mq.total_layer_tonnage_t == 0.0:
            findings.append(AuditFinding(
                severity="warning",
                module="boq",
                issue="Missing quantities in BOQ estimate",
                recommendation="Verify BOQ layer-wise details are configured and computed.",
                engineering_reason="Pavement layer quantities are required for construction materials planning.",
                navigation_key="BOQ"
            ))
            mod_statuses["boq"] = "FAIL"

    # 7. Submission
    checklist_dict = {}
    try:
        checklist_dict = json.loads(p.checklist_json) if p.checklist_json else {}
    except Exception:
        pass
        
    design_rev = checklist_dict.get("design_review", False)
    input_ver = checklist_dict.get("input_verification", False)
    traffic_ver = checklist_dict.get("traffic_verification", False)
    material_ver = checklist_dict.get("material_verification", False)
    
    mod_statuses["submission"] = "PASS"
    if not (design_rev and input_ver and traffic_ver and material_ver):
        findings.append(AuditFinding(
            severity="warning",
            module="submission",
            issue="Engineering review checklists are incomplete",
            recommendation="Review and verify all checklists in the Engineering Review panel.",
            engineering_reason="Review checkboxes indicate formal consultant sign-off of inputs and traffic assumptions.",
            navigation_key="Submission Center"
        ))
        
    if not p.locked:
        findings.append(AuditFinding(
            severity="warning",
            module="submission",
            issue="Project is not locked",
            recommendation="Lock the project in the Submission module to prevent accidental modifications.",
            engineering_reason="Locking freezes design parameters, guaranteeing traceability for DPR generation.",
            navigation_key="Submission Center"
        ))
        
    # Check if DPR generated
    has_dpr = False
    from sqlalchemy import select
    from app.db.schema import ReportRevisionSnapshotRecord
    with db.session() as s:
        has_dpr = s.scalars(
            select(ReportRevisionSnapshotRecord).where(ReportRevisionSnapshotRecord.project_id == project_id)
        ).first() is not None
        
    if not has_dpr:
        findings.append(AuditFinding(
            severity="info",
            module="submission",
            issue="Design Project Report (DPR) has not been exported",
            recommendation="Export the Combined Pavement Design Report to generate the official word document.",
            engineering_reason="The report records final design computations in a signed-off consultancy format.",
            navigation_key="Submission Center"
        ))

    # 8. Cross-Module Consistency checks
    # Traffic MSA vs Structural MSA
    if ta and sd:
        t_msa = float(ta.design_msa or 0.0)
        s_msa = float(sd.design_msa or 0.0)
        mismatch = (abs(t_msa - s_msa) > 0.01) if s_msa > 0.0 else False
        consistency_checks.append({
            "module": "Traffic vs Structural",
            "field": "Design MSA",
            "source_val": f"{t_msa:.2f} MSA",
            "target_val": f"{s_msa:.2f} MSA",
            "status": "PASS" if not mismatch else "FAIL"
        })
        if mismatch:
            findings.append(AuditFinding(
                severity="major",
                module="structural",
                issue="Cross-Module Mismatch: Traffic MSA differs from Structural Design MSA.",
                recommendation="Refresh structural design layers from traffic to synchronize MSA values.",
                engineering_reason="Pavement layers must be designed for the same design axle projections.",
                navigation_key="Structural Design",
                technical_details=f"Traffic={t_msa:.2f} MSA, Structural={s_msa:.2f} MSA"
            ))

    # Subgrade CBR/Mr vs Structural Mr
    if p and sd:
        p_mr = float(p.subgrade_mr or 0.0)
        s_mr = float(sd.subgrade_mr_mpa or 0.0)
        mismatch = (abs(p_mr - s_mr) > 0.1) if s_mr > 0.0 else False
        consistency_checks.append({
            "module": "Subgrade vs Structural",
            "field": "Resilient Modulus (Mr)",
            "source_val": f"{p_mr:.1f} MPa",
            "target_val": f"{s_mr:.1f} MPa",
            "status": "PASS" if not mismatch else "FAIL"
        })
        if mismatch:
            findings.append(AuditFinding(
                severity="major",
                module="structural",
                issue="Cross-Module Mismatch: Subgrade Resilient Modulus (Mr) differs from Structural design Mr.",
                recommendation="Align Subgrade resilient modulus values in structural inputs.",
                engineering_reason="Mechanistic pavement validations must utilize consistent subgrade resilient responses.",
                navigation_key="Structural Design",
                technical_details=f"Subgrade={p_mr:.1f} MPa, Structural={s_mr:.1f} MPa"
            ))

    # Structural thickness vs BOQ thickness
    if sd and mq:
        try:
            mq_inputs = json.loads(mq.inputs_json) if mq.inputs_json else {}
            boq_layers = mq_inputs.get("layers", [])
        except Exception:
            boq_layers = []
            
        mismatch_found = False
        mismatched_str = []
        for s_ly in comp:
            s_name = s_ly.get("name", "")
            s_mapped = map_layer_name(s_name)
            s_thick = float(s_ly.get("thickness_mm", 0.0))
            
            # Find in BOQ
            matched_boq = None
            for b_ly in boq_layers:
                if map_layer_name(b_ly.get("layer_type", "")) == s_mapped:
                    matched_boq = b_ly
                    break
            if matched_boq:
                b_thick = float(matched_boq.get("thickness_mm", 0.0))
                if abs(s_thick - b_thick) > 0.1:
                    mismatch_found = True
                    mismatched_str.append(f"{s_mapped} (Struct={s_thick:.0f}mm, BOQ={b_thick:.0f}mm)")
            else:
                mismatch_found = True
                mismatched_str.append(f"{s_mapped} missing in BOQ")

        consistency_checks.append({
            "module": "Structural vs BOQ",
            "field": "Layer Thicknesses",
            "source_val": "Structural Design Layers",
            "target_val": ", ".join(mismatched_str) if mismatch_found else "All Match",
            "status": "FAIL" if mismatch_found else "PASS"
        })
        if mismatch_found:
            findings.append(AuditFinding(
                severity="major",
                module="boq",
                issue="Cross-Module Mismatch: Structural layer thicknesses do not match BOQ layer thicknesses.",
                recommendation="Click 'Refresh Structural Design' in the BOQ panel to synchronize quantities.",
                engineering_reason="Quantity estimates and cost metrics must reflect finalized structural design parameters.",
                navigation_key="BOQ",
                technical_details=", ".join(mismatched_str)
            ))

    # Structural/IITPAVE layer consistency
    if sd and mv:
        try:
            mv_inputs = json.loads(mv.inputs_json) if mv.inputs_json else {}
            iit_layers = mv_inputs.get("layers", [])
        except Exception:
            iit_layers = []
            
        mismatch_found = False
        mismatched_str = []
        for s_ly in comp:
            s_name = s_ly.get("name", "")
            s_mapped = map_layer_name(s_name)
            s_thick = float(s_ly.get("thickness_mm", 0.0))
            
            # Match DBM/BC in IITPAVE
            # IITPAVE inputs store standard layers (layer_1_thickness, layer_2_thickness, etc.)
            # Or they store in list
            pass # Just log standard checks
        # Let's check total thickness as indicator
        total_struct = float(sd.total_pavement_thickness_mm or 0.0)
        total_iit = 0.0
        if mv.recommended_thickness_json:
            try:
                iit_thick_dict = json.loads(mv.recommended_thickness_json)
                total_iit = sum(float(v) for v in iit_thick_dict.values())
            except Exception:
                pass
        if total_iit > 0 and abs(total_struct - total_iit) > 0.1:
            mismatch_found = True
            mismatched_str.append(f"Total (Struct={total_struct:.0f}mm, IITPAVE={total_iit:.0f}mm)")
            
        consistency_checks.append({
            "module": "Structural vs IITPAVE",
            "field": "Pavement Thickness",
            "source_val": f"{total_struct:.0f} mm",
            "target_val": f"{total_iit:.0f} mm" if total_iit > 0 else "N/A",
            "status": "PASS" if not mismatch_found else "FAIL"
        })
        if mismatch_found:
            findings.append(AuditFinding(
                severity="major",
                module="iitpave",
                issue="Cross-Module Mismatch: Structural total thickness differs from IITPAVE model input.",
                recommendation="Rerun IITPAVE mechanistic verification with updated structural thicknesses.",
                engineering_reason="IITPAVE boundary strain models must represent the actual designed layout.",
                navigation_key="IITPAVE Status",
                technical_details=", ".join(mismatched_str)
            ))

    # 9. Scoring calculation (Requirement 11)
    # A. Engineering Completeness (0-100)
    completeness_cnt = sum(1 for status in mod_statuses.values() if status in ("PASS", "FAIL"))
    completeness_score = int((completeness_cnt / 7.0) * 100)
    completeness_explanation = f"Pavement design modules completed: {completeness_cnt} out of 7. Completed modules include: " + \
                               ", ".join(m.title() for m, status in mod_statuses.items() if status in ("PASS", "FAIL"))

    # B. Engineering Consistency (0-100)
    consistency_fails = sum(1 for check in consistency_checks if check["status"] == "FAIL")
    consistency_score = max(0, 100 - (consistency_fails * 20))
    consistency_explanation = f"Cross-module integrity is aligned. Mismatches detected: {consistency_fails}."

    # C. Mechanistic Validation (0-100)
    if mod_statuses["iitpave"] == "PASS":
        mechanistic_score = 100
        mechanistic_explanation = "IITPAVE boundary strains successfully calculated and verify fatigue/rutting structural safety."
    elif mod_statuses["iitpave"] == "FAIL":
        mechanistic_score = 30
        mechanistic_explanation = "IITPAVE analysis completed but failed design strain boundary criteria limits."
    else:
        mechanistic_score = 0
        mechanistic_explanation = "Mechanistic validation checks are incomplete. IITPAVE run is missing."

    # D. Documentation Readiness (0-100)
    doc_score = 30  # Baseline for valid project record
    doc_details = []
    if design_rev and input_ver and traffic_ver and material_ver:
        doc_score += 30
        doc_details.append("Review checklists completed")
    if p.locked:
        doc_score += 20
        doc_details.append("Project locked")
    if has_dpr:
        doc_score += 20
        doc_details.append("DPR snapshots generated")
    documentation_score = min(100, doc_score)
    documentation_explanation = "Documentation completeness status: " + ", ".join(doc_details) if doc_details else "No document artifacts generated."

    # E. Submission Readiness (0-100)
    critical_cnt = sum(1 for f in findings if f.severity == "critical")
    major_cnt = sum(1 for f in findings if f.severity == "major")
    warning_cnt = sum(1 for f in findings if f.severity == "warning")
    
    if critical_cnt > 0:
        submission_score = 30
        submission_explanation = "Critical engineering issues must be resolved before submission is permitted."
    elif major_cnt > 0:
        submission_score = 70
        submission_explanation = "Minor structural or cross-module mismatches require engineer review."
    else:
        submission_score = 100
        submission_explanation = "All validation checks passed. Ready for consultancy submission."

    # F. Overall score (Weighted: Completeness 25%, Consistency 25%, Mechanistic 30%, Documentation 10%, Submission 10%)
    overall_score = int(completeness_score * 0.25 + consistency_score * 0.25 + mechanistic_score * 0.30 + documentation_score * 0.10 + submission_score * 0.10)

    # Risk level & Final recommendation selection
    if critical_cnt > 0 or overall_score < 70:
        risk_level = "RED"
        readiness_status = "Not Ready"
        final_rec = "NOT READY FOR SUBMISSION"
    elif major_cnt > 0 or warning_cnt > 0 or overall_score < 90:
        risk_level = "YELLOW"
        readiness_status = "Needs Engineer Review"
        final_rec = "READY AFTER MINOR CORRECTIONS"
    else:
        risk_level = "GREEN"
        readiness_status = "Ready for Review"
        final_rec = "READY FOR CONSULTANCY SUBMISSION"

    return AuditResult(
        score=overall_score,
        risk_level=risk_level,
        readiness_status=readiness_status,
        findings=findings,
        completeness_score=completeness_score,
        completeness_explanation=completeness_explanation,
        consistency_score=consistency_score,
        consistency_explanation=consistency_explanation,
        mechanistic_score=mechanistic_score,
        mechanistic_explanation=mechanistic_explanation,
        documentation_score=documentation_score,
        documentation_explanation=documentation_explanation,
        submission_score=submission_score,
        submission_explanation=submission_explanation,
        final_recommendation=final_rec,
        timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        module_statuses=mod_statuses,
        consistency_checks=consistency_checks
    )


def check_validation_gate(project_id: int, db) -> tuple[bool, list[str]]:
    """Strict Phase P6 validation gate check before freezing/submitting project."""
    errors = []
    
    # 1. Engineering validation results must exist
    audit = run_project_audit(project_id, db)
    if not audit:
        errors.append("• Engineering Validation results could not be generated.")
    else:
        # 2. Critical issues must be zero
        critical_cnt = sum(1 for f in audit.findings if f.severity == "critical")
        if critical_cnt > 0:
            errors.append(f"• Engineering Validation has {critical_cnt} critical issues that must be resolved.")
            
    # 3. BOQ must be available
    mq = db.latest_material_quantity(project_id)
    if not mq:
        errors.append("• BOQ estimate is missing. Run Material Quantity / BOQ estimation first.")
        
    # 4. Structural design & traceability must be available
    sd = db.latest_structural_design(project_id)
    if not sd:
        errors.append("• Structural design layers are missing.")
    elif not sd.traceability_log_json:
        errors.append("• Structural design explainability traceability log is missing.")
        
    return len(errors) == 0, errors
