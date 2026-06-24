# SamPave V2.0 Professional Baseline Full Validation Audit Report

## 1. Audit Overview
* **Tested Commit:** `9f85afc44773a61d0eb4a20ddc91b6c1db3528bc`
* **Tested Git Tag:** `v2.0-professional`
* **Test Date:** 2026-06-24
* **Environment:** Python 3.14.4, PySide6, Windows 11
* **Total Test Cases Executed:** 40
* **Pass Count:** 40
* **Fail Count:** 0

## 2. Final Verdict
* **Verdict Status:** **PASS**: Commercial demo ready
* **Verdict Status:** **PASS**: Decision-support engineering workflow ready
* **Certifications Limit Warning:** **NOT CERTIFIED**: Final field execution requires qualified pavement engineer sign-off

---

## 3. Full Pass/Fail Results Table
| Case ID | Module | Input Summary | Expected Output | Actual Output | Status | Review Notes |
|---|---|---|---|---|---|---|
| 1 | Traffic/MSA | CVPD=100, growth=5%, life=10, VDF=1.5, LDF=0.75 | 0.5165 MSA | 0.5165 MSA | PASS | Low traffic cumulative traffic matches formula perfectly. |
| 2 | Traffic/MSA | CVPD=1000, growth=6%, life=15, VDF=3.5, LDF=0.75 | 22.3013 MSA | 22.3013 MSA | PASS | Medium traffic cumulative traffic matches formula. |
| 3 | Traffic/MSA | CVPD=3000, growth=7.5%, life=15, VDF=4.5, LDF=0.75 | 96.5237 MSA | 96.5237 MSA | PASS | High traffic cumulative traffic matches formula. |
| 4 | Traffic/MSA | CVPD=100, growth=0.001%, life=10, VDF=1.0, LDF=0.5 | 0.1825 MSA | 0.1825 MSA | PASS | Boundary traffic checks close to zero growth. |
| 5 | Traffic/MSA | Negative CVPD (-100) | ValueError raised | ValueError: CVPD must be >= 0 | PASS | Blocked negative CVPD successfully in constructor. |
| 6 | Subgrade MR | CBR=2.0% (10 * CBR) | 20.00 MPa | 20.00 MPa | PASS | Subgrade MR matches empirical relation for CBR=2.0%. |
| 7 | Subgrade MR | CBR=3.0% (10 * CBR) | 30.00 MPa | 30.00 MPa | PASS | Subgrade MR matches empirical relation for CBR=3.0%. |
| 8 | Subgrade MR | CBR=5.0% (10 * CBR) | 50.00 MPa | 50.00 MPa | PASS | Subgrade MR matches empirical relation for CBR=5.0%. |
| 9 | Subgrade MR | CBR=8.0% (17.6 * CBR^0.64) | 66.60 MPa | 66.60 MPa | PASS | Subgrade MR matches empirical relation for CBR=8.0%. |
| 10 | Subgrade MR | CBR=10.0% (17.6 * CBR^0.64) | 76.83 MPa | 76.83 MPa | PASS | Subgrade MR matches empirical relation for CBR=10.0%. |
| 11 | Subgrade MR | CBR=15.0% (17.6 * CBR^0.64) | 99.59 MPa | 99.59 MPa | PASS | Subgrade MR matches empirical relation for CBR=15.0%. |
| 12 | Subgrade MR | CBR=25.0% (17.6 * CBR^0.64) | 138.10 MPa | 138.10 MPa | PASS | Subgrade MR matches empirical relation for CBR=25.0%. |
| 13 | Catalogue | CBR 3%, MSA 10 (exact boundary lookup) | BC=40, DBM=100, WMM=250, GSB=300 | BC=40, DBM=100, WMM=250, GSB=300 | PASS | Boundary lookup returns expected thicknesses exactly. |
| 14 | Catalogue | CBR 5%, MSA 5 (exact boundary lookup) | BC=40, DBM=70, WMM=250, GSB=230 | BC=40, DBM=70, WMM=250, GSB=230 | PASS | Boundary lookup returns intermediate thicknesses exactly. |
| 15 | Catalogue | CBR 5%, MSA 250 (out of range) | Out-of-range = True, warning generated | Out-of-range = True, warning = Catalogue database incomplete — engineer... | PASS | Heavy traffic lookup caps and logs engineering warnings correctly. |
| 16 | Catalogue | CBR 5%, MSA 0.5 (out of range) | Out-of-range = True, warning generated | Out-of-range = True, warning = Catalogue database incomplete — engineer... | PASS | Light traffic lookup caps and logs warning correctly. |
| 17 | Intelligence | BC 40, DBM 80, WMM 250, GSB 200, Subgrade=50 (Healthy) | Screening Score = 100.0 | Screening Score = 100.0 | PASS | Healthy pavement stack achieves a perfect screening score. |
| 18 | Intelligence | WMM (700) over GSB (100) (Ratio 7.0 > 4.0) | Screening Score = 85.0 | Screening Score = 85.0 | PASS | Bad modular ratio detected and score deducted by 15 points. |
| 19 | Intelligence | Poisson's ratio = 0.55 | ValueError raised | ValueError: Poisson's ratio must be physically realistic (between 0.05 and 0.49) | PASS | Blocked physically invalid Poisson's ratio in layer constructor. |
| 20 | Intelligence | CTB (5000) over GSB (150) (modulus < 500 MPa) | Screening Score = 65.0 | Screening Score = 65.0 | PASS | Stiff stabilized layer over weak support detected, score deducted by 20. |
| 21 | CTB/CTS | BC 40, DBM 80, CTB 120, CTS 100, GSB 150, Subgrade=50 | Screening Score = 65.0 | Screening Score = 65.0 | PASS | Valid CTB/CTS stack computed and flagged correctly. |
| 22 | CTB/CTS | CTB UCS = 0.0 (Missing) | UCS missing warning generated | Warnings match | PASS | Missing UCS warning correctly generated. |
| 23 | CTB/CTS | CTB Modulus = 2000 MPa, CTS Modulus = 500 MPa | Unrealistic modulus warnings | Warnings match | PASS | Unrealistic stabilized modulus warnings correctly generated. |
| 24 | CTB/CTS | CTB Poisson = 0.40 (Non-standard) | Non-standard Poisson warning | Warnings match | PASS | Non-standard stabilized Poisson ratio correctly flagged in warnings. |
| 25 | CTB/CTS | CTB Thickness = 80mm (<100mm) | Very low thickness warning | Warnings match | PASS | Thin CTB layer correctly flagged with thickness warning. |
| 26 | Negative Testing | Design life = 0 | ValueError raised | ValueError: Design life must be >= 1 | PASS | Blocked zero design life successfully in constructor. |
| 27 | Negative Testing | Subgrade CBR = -1.0 | ValueError raised | ValueError: CBR must be > 0 | PASS | Blocked negative CBR successfully in constructor. |
| 28 | Negative Testing | Growth rate = -2.0% | ValueError raised | ValueError: Growth rate must be >= 0 | PASS | Blocked negative growth rate successfully in constructor. |
| 29 | Negative Testing | VDF = -1.0 | ValueError raised | ValueError: VDF must be >= 0 | PASS | Blocked negative VDF successfully in constructor. |
| 30 | Negative Testing | VDF = 0.0 | 0.0000 MSA | 0.0000 MSA | PASS | VDF=0.0 calculated successfully as zero cumulative traffic. |
| 31 | Negative Testing | Extremely high modulus (500000 MPa) | Calculates score & warnings | Score: 70.0 | PASS | Stably screening extremely high modulus without crashes. |
| 32 | Negative Testing | Edit locked project | ValueError raised | ValueError: Cannot modify a locked project. | PASS | Blocked edit of locked project successfully in database repository. |
| 33 | EXE Audit | Standalone EXE process launch | Process runs offscreen | Launched and terminated successfully | PASS | Compiled standalone EXE launches with zero missing environment dependencies. |
| 34 | Workflow | Project creation | Project object created with ID | Project ID = 1 | PASS | Successfully created project in database façade. |
| 35 | Workflow | Traffic calculation & save | Save traffic with MSA=39.7192 | Saved MSA=39.7192 | PASS | Traffic calculation matches and persists in database. |
| 36 | Workflow | CBR Mr calculation & save | Subgrade MR=40.0 MPa | Saved MR=40.0 MPa | PASS | Subgrade resilient modulus calculation matches and persists. |
| 37 | Workflow | IRC catalogue lookup | Suggested composition found | Bituminous Concrete (BC): 40mm, Dense Bituminous Macadam (DBM): 160mm, Wet Mix Macadam (WMM): 250mm, Granular Sub-base (GSB): 300mm | PASS | Successfully matched design against digitized IRC:37 catalogue. |
| 38 | Workflow | Marshall mix design computation | Calculated Gsb=2.7556, Va=3.4787% | Saved successfully in DB | PASS | Successfully computed mix design and verified database persistence. |
| 39 | Workflow | DPR report generation | Generated non-empty DOCX | DOCX created, size=42180 bytes | PASS | Word report builder runs successfully and compiles all active sections. |
| 40 | Workflow | Submission ZIP package export | Generated non-empty ZIP | ZIP created, size=47594 bytes | PASS | Submission center ZIP packager runs successfully, archiving reports and schemas. |

---

## 4. Excel / Hand Calculation Parity
The core engineering engine outputs were cross-checked against independent hand-calculations to evaluate accuracy.

| Formula Module | Test Case reference | Expected Value | Actual Value | Absolute / Pct Error | Verdict |
|---|---|---|---|---|---|
| MSA Traffic Formula | Traffic/MSA (Case 1) | 0.5165 MSA | 0.5165 MSA | 0.0000% | PASS |
| Subgrade Resilient Modulus (CBR <= 5) | Subgrade MR (Case 6) | 20.00 MPa | 20.00 MPa | 0.0000% | PASS |
| Subgrade Resilient Modulus (CBR > 5) | Subgrade MR (Case 9) | 66.60 MPa | 66.60 MPa | 0.0000% | PASS |
| Marshall Air Voids (Va) at 4.5% Pb | Marshall Mix | 3.4787% | 3.4787% | 0.0000% | PASS |
| Marshall VMA at 4.5% Pb | Marshall Mix | 14.7616% | 14.7616% | 0.0000% | PASS |
| Marshall VFB at 4.5% Pb | Marshall Mix | 76.4338% | 76.4338% | 0.0000% | PASS |
| Screening Score Deduction (modular ratio) | Intelligence Review | 85.0 | 85.0 | 0.0000% | PASS |
| Screening Score Deduction (weak support) | Intelligence Review | 65.0 | 65.0 | 0.0000% | PASS |

---

## 5. Report Quality Verification
Generated Word DPR and ZIP submission packages were audited:
- **Cover Page:** Confirmed presence of clear title, Client (National Highway Authority of India), Consultant Name, Date, and Report ID.
- **Assumptions Sheet:** Preset Poisson's ratios (Bituminous 0.35, granular 0.35, stabilized 0.25) and traffic growth are explicitly presented in table format.
- **Limitations Sheet:** Standalone sheet with clear limitations warning including: *"Final design acceptance for construction field execution remains subject to independent review and sign-off by a qualified pavement engineer."*
- **Engineer Review Checklist Table:** Checkboxes show reviews completed state with notes.
- **Sign-off Space:** Present at the bottom of the review page.
- **Safety Disclaimer:** Prominently featured on the Cover Page, Executive Summary, and ZIP `README_Disclaimer.txt`.

---

## 6. Known System Limitations
1. **Decision Support Boundaries:** Empirical design projections based on IRC:37 catalogue and Marshall tables are decision-support values.
2. **IITPAVE Environment:** The mechanistic validation workflow automatically falls back to Decision Support Mode if the `IITPAVE.exe` binary path is missing or fails execution, preventing silent failure.
