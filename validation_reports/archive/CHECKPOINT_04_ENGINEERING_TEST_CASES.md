# Checkpoint 4 Validation Report: Engineering Test Cases

This report documents the results of executing 10 pavement design scenarios using the SamPave structural and mechanistic engines.

## 1. Scenario Results Table

| Case | Name | CVPD | Growth | Life | CBR | MSA | Total Thickness | Composition | Fatigue Strain (με) | Rutting Strain (με) | Fatigue Life (MSA) | Rutting Life (MSA) | PASS/FAIL |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | Case 1: Low traffic + low CBR | 100.0 | 5.0% | 10 | 2.0% | 0.5165 | 740 mm | Bituminous Concrete (BC) (40mm), Dense Bituminous Macadam (DBM) (50mm), Wet Mix Macadam (WMM) (250mm), Granular Sub-base (GSB) (400mm) | N/A | N/A | N/A | N/A | REFUSED (stub) |
| 2 | Case 2: Low traffic + high CBR | 100.0 | 5.0% | 10 | 12.0% | 0.5165 | 490 mm | Bituminous Concrete (BC) (40mm), Dense Bituminous Macadam (DBM) (50mm), Wet Mix Macadam (WMM) (250mm), Granular Sub-base (GSB) (150mm) | N/A | N/A | N/A | N/A | REFUSED (stub) |
| 3 | Case 3: Medium traffic + low CBR | 1000.0 | 6.0% | 15 | 3.0% | 22.3013 | 720 mm | Bituminous Concrete (BC) (40mm), Dense Bituminous Macadam (DBM) (130mm), Wet Mix Macadam (WMM) (250mm), Granular Sub-base (GSB) (300mm) | N/A | N/A | N/A | N/A | REFUSED (stub) |
| 4 | Case 4: Medium traffic + high CBR | 1000.0 | 6.0% | 15 | 10.0% | 22.3013 | 620 mm | Bituminous Concrete (BC) (40mm), Dense Bituminous Macadam (DBM) (130mm), Wet Mix Macadam (WMM) (250mm), Granular Sub-base (GSB) (200mm) | N/A | N/A | N/A | N/A | REFUSED (stub) |
| 5 | Case 5: High traffic + poor CBR | 3000.0 | 7.5% | 15 | 2.5% | 96.5237 | 880 mm | Bituminous Concrete (BC) (40mm), Dense Bituminous Macadam (DBM) (190mm), Wet Mix Macadam (WMM) (250mm), Granular Sub-base (GSB) (400mm) | N/A | N/A | N/A | N/A | REFUSED (stub) |
| 6 | Case 6: High traffic + good CBR | 3000.0 | 7.5% | 15 | 8.0% | 96.5237 | 680 mm | Bituminous Concrete (BC) (40mm), Dense Bituminous Macadam (DBM) (190mm), Wet Mix Macadam (WMM) (250mm), Granular Sub-base (GSB) (200mm) | N/A | N/A | N/A | N/A | REFUSED (stub) |
| 7 | Case 7: Very high MSA case | 8000.0 | 8.0% | 20 | 4.0% | 551.2029 | 780 mm | Bituminous Concrete (BC) (40mm), Dense Bituminous Macadam (DBM) (190mm), Wet Mix Macadam (WMM) (250mm), Granular Sub-base (GSB) (300mm) | N/A | N/A | N/A | N/A | REFUSED (stub) |
| 8 | Case 8: Stabilized/custom layer case | 2000.0 | 7.5% | 15 | 5.0% | 50.0493 | 440 mm | Bituminous Concrete (BC) (40mm), Dense Bituminous Macadam (DBM) (100mm), Cement Treated Base (CTB) (150mm), Granular Sub-base (GSB) (150mm) | N/A | N/A | N/A | N/A | REFUSED (stub) |
| 9 | Case 9: Invalid input case | -100.0 | 5.0% | 10 | -2.0% | Failed: ValueError: CVPD must be >= 0 | | | | | | | ERROR |
| 10 | Case 10: Boundary limit case | 0.0 | 0.0% | 1 | 0.1% | 0.0000 | 740 mm | Bituminous Concrete (BC) (40mm), Dense Bituminous Macadam (DBM) (50mm), Wet Mix Macadam (WMM) (250mm), Granular Sub-base (GSB) (400mm) | N/A | N/A | N/A | N/A | REFUSED (stub) |

## 2. Logical Validation Analysis

* **Traffic Load Validation:** Higher traffic increases pavement thickness? **PASS** (Case 3 thickness: 720 mm vs Case 5 thickness: 880 mm)
* **Subgrade Strength Validation:** Lower CBR increases required thickness? **PASS** (CBR 3% thickness: 720 mm vs CBR 10% thickness: 620 mm)
* **Invalid Input Rejection:** Rejects negative inputs natively in core engine? **PASS** (Negative inputs in Case 9 successfully raised exception: CVPD must be >= 0)

## 3. Detailed Case Observations

### Scenario 1: Case 1: Low traffic + low CBR
* **Design MSA:** 0.5165
* **Resilient Modulus (Mr) of Subgrade:** 20.00 MPa
* **Total Suggested Thickness:** 740 mm
* **Pavement Layer Configuration:** Bituminous Concrete (BC) (40mm), Dense Bituminous Macadam (DBM) (50mm), Wet Mix Macadam (WMM) (250mm), Granular Sub-base (GSB) (400mm)
* **Fatigue Check Status:** WARN - IITPAVE ran, but fatigue verdict was refused: Mechanistic result flagged placeholder mechanistic input (MechanisticResult.is_placeholder=True). Final verdict refused.
* **Rutting Check Status:** WARN - IITPAVE ran, but rutting verdict was refused: Mechanistic result flagged placeholder mechanistic input (MechanisticResult.is_placeholder=True). Final verdict refused.
* **Verdict:** REFUSED (stub)

### Scenario 2: Case 2: Low traffic + high CBR
* **Design MSA:** 0.5165
* **Resilient Modulus (Mr) of Subgrade:** 86.34 MPa
* **Total Suggested Thickness:** 490 mm
* **Pavement Layer Configuration:** Bituminous Concrete (BC) (40mm), Dense Bituminous Macadam (DBM) (50mm), Wet Mix Macadam (WMM) (250mm), Granular Sub-base (GSB) (150mm)
* **Fatigue Check Status:** WARN - IITPAVE ran, but fatigue verdict was refused: Mechanistic result flagged placeholder mechanistic input (MechanisticResult.is_placeholder=True). Final verdict refused.
* **Rutting Check Status:** WARN - IITPAVE ran, but rutting verdict was refused: Mechanistic result flagged placeholder mechanistic input (MechanisticResult.is_placeholder=True). Final verdict refused.
* **Verdict:** REFUSED (stub)

### Scenario 3: Case 3: Medium traffic + low CBR
* **Design MSA:** 22.3013
* **Resilient Modulus (Mr) of Subgrade:** 30.00 MPa
* **Total Suggested Thickness:** 720 mm
* **Pavement Layer Configuration:** Bituminous Concrete (BC) (40mm), Dense Bituminous Macadam (DBM) (130mm), Wet Mix Macadam (WMM) (250mm), Granular Sub-base (GSB) (300mm)
* **Fatigue Check Status:** WARN - IITPAVE ran, but fatigue verdict was refused: Mechanistic result flagged placeholder mechanistic input (MechanisticResult.is_placeholder=True). Final verdict refused.
* **Rutting Check Status:** WARN - IITPAVE ran, but rutting verdict was refused: Mechanistic result flagged placeholder mechanistic input (MechanisticResult.is_placeholder=True). Final verdict refused.
* **Verdict:** REFUSED (stub)

### Scenario 4: Case 4: Medium traffic + high CBR
* **Design MSA:** 22.3013
* **Resilient Modulus (Mr) of Subgrade:** 76.83 MPa
* **Total Suggested Thickness:** 620 mm
* **Pavement Layer Configuration:** Bituminous Concrete (BC) (40mm), Dense Bituminous Macadam (DBM) (130mm), Wet Mix Macadam (WMM) (250mm), Granular Sub-base (GSB) (200mm)
* **Fatigue Check Status:** WARN - IITPAVE ran, but fatigue verdict was refused: Mechanistic result flagged placeholder mechanistic input (MechanisticResult.is_placeholder=True). Final verdict refused.
* **Rutting Check Status:** WARN - IITPAVE ran, but rutting verdict was refused: Mechanistic result flagged placeholder mechanistic input (MechanisticResult.is_placeholder=True). Final verdict refused.
* **Verdict:** REFUSED (stub)

### Scenario 5: Case 5: High traffic + poor CBR
* **Design MSA:** 96.5237
* **Resilient Modulus (Mr) of Subgrade:** 25.00 MPa
* **Total Suggested Thickness:** 880 mm
* **Pavement Layer Configuration:** Bituminous Concrete (BC) (40mm), Dense Bituminous Macadam (DBM) (190mm), Wet Mix Macadam (WMM) (250mm), Granular Sub-base (GSB) (400mm)
* **Fatigue Check Status:** WARN - IITPAVE ran, but fatigue verdict was refused: Mechanistic result flagged placeholder mechanistic input (MechanisticResult.is_placeholder=True). Final verdict refused.
* **Rutting Check Status:** WARN - IITPAVE ran, but rutting verdict was refused: Mechanistic result flagged placeholder mechanistic input (MechanisticResult.is_placeholder=True). Final verdict refused.
* **Verdict:** REFUSED (stub)

### Scenario 6: Case 6: High traffic + good CBR
* **Design MSA:** 96.5237
* **Resilient Modulus (Mr) of Subgrade:** 66.60 MPa
* **Total Suggested Thickness:** 680 mm
* **Pavement Layer Configuration:** Bituminous Concrete (BC) (40mm), Dense Bituminous Macadam (DBM) (190mm), Wet Mix Macadam (WMM) (250mm), Granular Sub-base (GSB) (200mm)
* **Fatigue Check Status:** WARN - IITPAVE ran, but fatigue verdict was refused: Mechanistic result flagged placeholder mechanistic input (MechanisticResult.is_placeholder=True). Final verdict refused.
* **Rutting Check Status:** WARN - IITPAVE ran, but rutting verdict was refused: Mechanistic result flagged placeholder mechanistic input (MechanisticResult.is_placeholder=True). Final verdict refused.
* **Verdict:** REFUSED (stub)

### Scenario 7: Case 7: Very high MSA case
* **Design MSA:** 551.2029
* **Resilient Modulus (Mr) of Subgrade:** 40.00 MPa
* **Total Suggested Thickness:** 780 mm
* **Pavement Layer Configuration:** Bituminous Concrete (BC) (40mm), Dense Bituminous Macadam (DBM) (190mm), Wet Mix Macadam (WMM) (250mm), Granular Sub-base (GSB) (300mm)
* **Fatigue Check Status:** WARN - IITPAVE ran, but fatigue verdict was refused: Mechanistic result flagged placeholder mechanistic input (MechanisticResult.is_placeholder=True). Final verdict refused.
* **Rutting Check Status:** WARN - IITPAVE ran, but rutting verdict was refused: Mechanistic result flagged placeholder mechanistic input (MechanisticResult.is_placeholder=True). Final verdict refused.
* **Verdict:** REFUSED (stub)

### Scenario 8: Case 8: Stabilized/custom layer case
* **Design MSA:** 50.0493
* **Resilient Modulus (Mr) of Subgrade:** 50.00 MPa
* **Total Suggested Thickness:** 440 mm
* **Pavement Layer Configuration:** Bituminous Concrete (BC) (40mm), Dense Bituminous Macadam (DBM) (100mm), Cement Treated Base (CTB) (150mm), Granular Sub-base (GSB) (150mm)
* **Fatigue Check Status:** WARN - IITPAVE ran, but fatigue verdict was refused: Mechanistic result flagged placeholder mechanistic input (MechanisticResult.is_placeholder=True). Final verdict refused.
* **Rutting Check Status:** WARN - IITPAVE ran, but rutting verdict was refused: Mechanistic result flagged placeholder mechanistic input (MechanisticResult.is_placeholder=True). Final verdict refused.
* **Verdict:** REFUSED (stub)

### Scenario 9: Case 9: Invalid input case
Execution failed: CVPD must be >= 0
### Scenario 10: Case 10: Boundary limit case
* **Design MSA:** 0.0000
* **Resilient Modulus (Mr) of Subgrade:** 1.00 MPa
* **Total Suggested Thickness:** 740 mm
* **Pavement Layer Configuration:** Bituminous Concrete (BC) (40mm), Dense Bituminous Macadam (DBM) (50mm), Wet Mix Macadam (WMM) (250mm), Granular Sub-base (GSB) (400mm)
* **Fatigue Check Status:** WARN - IITPAVE ran, but fatigue verdict was refused: Mechanistic result flagged placeholder mechanistic input (MechanisticResult.is_placeholder=True). Final verdict refused.
* **Rutting Check Status:** WARN - IITPAVE ran, but rutting verdict was refused: Mechanistic result flagged placeholder mechanistic input (MechanisticResult.is_placeholder=True). Final verdict refused.
* **Verdict:** REFUSED (stub)
