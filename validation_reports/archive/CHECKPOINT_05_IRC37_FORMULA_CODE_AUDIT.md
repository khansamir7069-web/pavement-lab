# Checkpoint 5 Validation Report: IRC:37 Formula and Code Audit

This report presents a code-level audit of the mathematical equations, engineering models, and data-mapping paths in the SamPave Engineering Suite, cross-referenced with IRC:37-2018 design guidelines.

## 1. Traffic Formula & MSA Calculations

* **Mathematical Equation:** Cumulative design traffic in MSA is calculated in `app/core/structural_design.py` using:
  $$N = \frac{365 \cdot A \cdot [(1+r)^n - 1]}{r} \cdot D \cdot F \cdot 10^{-6}$$
  where $A$ = CVPD, $r$ = growth rate (annual decimal), $n$ = design life (years), $D$ = lane distribution factor, $F$ = Vehicle Damage Factor (VDF).
* **Code Implementation (`compute_design_traffic`):**
  ```python
  r = inp.growth_rate_pct / 100.0
  n = inp.design_life_years
  gf = ((1 + r) ** n - 1) / r if r > 0 else float(n)
  msa = 365.0 * inp.initial_cvpd * gf * inp.ldf * inp.vdf / 1_000_000.0
  ```
* **Audit Verdict:** **PASS**. The implementation perfectly matches IRC:37 Eq 3.1. It also includes a division guard for $r = 0$, resolving to a simple linear multiplication of $n$, which is mathematically correct.

---

## 2. Resilient Modulus from CBR (Subgrade Modulus)

* **Mathematical Equation:** Subgrade resilient modulus $M_r$ (MPa) calculation (IRC:37-2018 Annex E):
  $$M_r = 10 \cdot CBR \quad \text{for } CBR \le 5\%$$
  $$M_r = 17.6 \cdot CBR^{0.64} \quad \text{for } CBR > 5\%$$
* **Code Implementation (`compute_subgrade_mr`):**
  ```python
  if cbr_pct <= 0:
      return 0.0
  if cbr_pct <= 5:
      return 10.0 * cbr_pct
  return 17.6 * (cbr_pct ** 0.64)
  ```
* **Audit Verdict:** **PASS**. The equations perfectly match the IRC guidelines. Negative and zero CBR cases are floored at 0.0 MPa to prevent complex or invalid number results.

---

## 3. Pavement Layer suggestion Catalogue

* **Code Implementation (`suggest_composition`):**
  * BC wearing course thickness: fixed at 40 mm.
  * DBM-II thickness: scales with traffic (50 mm for < 5 MSA up to 190 mm for >= 50 MSA).
  * WMM base course: fixed standard 250 mm.
  * GSB sub-base: scales inversely with subgrade CBR (400 mm for CBR < 3% down to 150 mm for CBR >= 12%).
* **Audit Verdict:** **PASS** (within skeleton scope). The composition suggested is reasonable, but clearly marked as a placeholder catalogue-style suggestion, with an explicit warning note warning the engineer to cross-check against actual Plates 1–4 of IRC:37.

---

## 4. Mechanistic IITPAVE Integration & Life Equations

* **IITPAVE Input Format (`build_iitpave_input`):**
  Properly outputs the number of layers, modulus, Poisson's ratio, layer thicknesses (with subgrade designated as 0/semi-infinite), wheel load (20 kN dual wheel standard), contact pressure (0.56 MPa standard), center-to-centre spacing (310 mm standard), and evaluation points. (PASS)
* **Tensile Strain Fatigue Formula (IRC:37-2018 cl. 6.4.2):**
  Calculates fatigue life $N_f$ (axle passes) using the custom calibration parameters:
  $$N_f = C \cdot k_1 \cdot \left(\frac{1}{\epsilon_t}\right)^{k_2} \cdot \left(\frac{1}{E_{BC}}\right)^{k_3}$$
  * Code matches. Correctly scales micro-strain input `epsilon_t_microstrain * 1.0e-6` to standard strain before exponent calculation. (PASS)
* **Compressive Strain Rutting Formula (IRC:37-2018 cl. 6.4.3):**
  Calculates rutting life $N_r$ (axle passes) using:
  $$N_r = k_r \cdot \left(\frac{1}{\epsilon_v}\right)^{k_v}$$
  * Code matches. Correctly scales `epsilon_v_microstrain * 1.0e-6`. (PASS)
* **Pass/Fail Verdict Logic:**
  Compares cumulative computed life (in MSA) vs design traffic MSA. Verdict is PASS if life >= design traffic, else FAIL. (PASS)

---

## 5. Input Validation Audit

We investigated the vulnerability of the core calculation modules to extreme or garbage inputs:

| Vulnerability Input | Core Engine Response | Severity Class | Audit / recommendation |
|---|---|---|---|
| **Negative CVPD** | Computes negative MSA, suggested layers unaffected. | **MAJOR** | No ValueError raised. Rejects negative values at UI form validation. |
| **Negative CBR** | Returns subgrade Mr = 0.0 MPa; suggested GSB = 400 mm. | **MAJOR** | No ValueError raised. Rejects negative values at UI level. |
| **Zero/Negative VDF** | Computes zero or negative MSA. | **MAJOR** | No ValueError raised. UI must block non-positive VDFs. |
| **Zero Design Life** | Computes 0.0 MSA. | **MAJOR** | No ValueError raised. UI must enforce design life >= 1. |
| **Extreme Growth Rate** | Exponent computes very large numbers, could overflow. | **MINOR** | Python handles large integers but float overflow is possible. Enforce growth limit (e.g. 0-25%) in UI. |
| **Missing Layer Values** | Mechanics blocks if non-subgrade thickness is missing/invalid. | **PASS** | Handled safely by `PavementStructure` post-init validation checks. |

---

## 6. Export Mapping & Unit Mismatch Check

* **Word Combined DPR Output:**
  * Context class `CombinedReportContext` correctly maps client name, agency, work order, and date properties.
  * Mappings for `design_msa` (reported as `"%.2f MSA"`), layer thicknesses (reported in `"mm"`), and resilient subgrade modulus (`"MPa"`) use standard formatting strings without units mismatch.
  * Mechanistic checks are outputted as refused under the stub runner (`refused=True`), and warnings cite that placeholders are used. (PASS)

---
**Status of Checkpoint 5:** COMPLETED
