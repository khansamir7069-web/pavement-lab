# RoadX Independent Mechanistic Solver — Material & Layer Engine Reference Manual

This manual details the materials, properties, validation boundaries, and database structures of the RoadX Material & Layer Engine, fulfilling the documentation requirements of Phase 2.

---

## 1. Material Library Templates

The engine supports 13 core material templates, loaded dynamically from versioned JSON files:

1. **Bituminous Concrete (BC):** Standard wearing course, highly temperature sensitive, high stiffness.
2. **Dense Bituminous Macadam (DBM):** Structural binder course, structural core of the bituminous layer.
3. **Dense Graded Bituminous Mix (DGBM):** Semi-dense binder/base course aggregate-binder mixture.
4. **Wet Mix Macadam (WMM):** Unbound granular base, mechanically interlocked aggregates.
5. **Granular Sub Base (GSB):** Granular sub-base, filter and drainage layer directly above subgrade.
6. **Cement Treated Base (CTB):** Cement-bound stabilized base, high stiffness (modulus up to 10,000 MPa), susceptible to shrinkage cracks.
7. **Cement Treated Subbase (CTSB):** Cement-bound stabilized sub-base platform.
8. **Lime Stabilized Layer:** Chemical modification for highly plastic, clayey soils.
9. **Reclaimed Asphalt Pavement (RAP):** Sustainable recycled bituminous mix.
10. **Generic Bituminous Layer:** Configurable bituminous course for custom testing.
11. **Generic Granular Layer:** Configurable granular base/sub-base course.
12. **Generic Stabilized Layer:** Configurable chemically stabilized base/sub-base.
13. **Generic Subgrade:** Foundation soil support, semi-infinite thickness representation.

---

## 2. Engineering Properties & Metadata Schema

Every material and layer record contains the following properties:

| Property | Symbol | Default Unit | Engineering Limits |
|---|---|---|---|
| **Thickness** | $h$ | mm | $1.0 \le h \le 10,000.0$ (finite layers); Subgrade must be `None` (infinite) |
| **Elastic Modulus** | $E$ | MPa | $0.1 \le E \le 100,000.0$ |
| **Poisson's Ratio** | $\nu$ | - | $0.0 < \nu \le 0.5$ |
| **Density** | $\rho$ | kg/m³ | $100.0 \le \rho \le 5,000.0$ |
| **Category** | - | - | Bituminous \| Granular \| Stabilized \| Subgrade |
| **Layer Type** | - | - | Surface \| Binder \| Base \| Subbase \| Subgrade |

*Note: AI Optimization attributes (`locked`, `optimizable`, `min_thickness_mm`, `max_thickness_mm`, `construction_cost_index`, `carbon_footprint_index`, `availability_rating`, `material_priority`, `sustainability_score`) are also supported by the schema for future expansion.*

---

## 3. Strict Engineering Validation Rules

1. **Thickness Limits:** Checks that finite layers fall within $[1, 10000]$ mm.
2. **Elastic Modulus Limits:** Checks that moduli fall within $[0.1, 100000]$ MPa.
3. **Poisson's Ratio Bounds:** Enforces $\nu \in (0.0, 0.5]$.
4. **Semi-infinite Subgrade Constraint:** Enforces that only the last layer in the stack has thickness set to `None`, representing the semi-infinite subgrade.
5. **No Duplicate Names:** Prevents duplicate layer names to ensure clean tracking during edits, duplication, or reordering.
6. **Stiffness Inversion (Warning):** Flags warning messages if a lower layer is stiffer than an upper layer (except for stabilized layers CTB/CTS).

---

## 4. Material Database & Versioning Strategy

- **Location:** `mechanistic_solver/materials/database/`
- **Files:** `IRC37_2018.json`, `IRC37_Latest.json`, `Laboratory.json`, `Client_Custom.json`
- **Versioning Mechanism:** Each database file contains a `version` attribute (e.g. `"1.0.0"`, `"1.1.0"`). The `MaterialLibrary` scans the folder, parses each database, and indexes them in a registry.
- **Independence:** Future standards updates or client-specific test databases can be dropped as new JSON files into this folder without modifying the core solver source code.

---

## 5. References

1. **Indian Roads Congress (IRC):** *IRC:37-2018: Guidelines for the Design of Flexible Pavements*.
2. **Burmister, D. M. (1945):** *The General Theory of Stresses and Displacements in Layered Soil Systems*. Journal of Applied Physics, Vol. 16.
3. **Boussinesq, J. (1885):** *Application des Potentiels à l'Étude de l'Équilibre et du Mouvement des Solides Élastiques*.
4. **Huang, Y. H. (2004):** *Pavement Analysis and Design*, 2nd Edition.
5. **Yoder, E. J. and Witczak, M. W. (1975):** *Principles of Pavement Design*, 2nd Edition. John Wiley & Sons.
