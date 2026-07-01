# RoadX Independent Mechanistic Solver — Theory Manual

This document details the governing equations, engineering assumptions, and mathematical formulations for the multi-layered elastic pavement solver, establishing the mathematical foundations for Phase 1.

---

## 1. Introduction to Multi-Layered Elastic Pavement Theory

In flexible-pavement engineering, the structure is represented as a multi-layered elastic system. The surface, binder, base, sub-base, and subgrade layers are modeled as horizontal layers of infinite lateral extent, resting on a semi-infinite elastic half-space (the subgrade soil). 

The response of this system to wheel loading is calculated by solving the equations of elasticity under axisymmetrically applied circular contact pressures.

---

## 2. Governing Equations of Elasticity

For an axisymmetrical coordinate system $(r, \theta, z)$, where $z$ represents the depth coordinate and $r$ the radial coordinate:

### A. Equations of Equilibrium
Neglecting body forces:
\[
\frac{\partial \sigma_r}{\partial r} + \frac{\partial \tau_{zr}}{\partial z} + \frac{\sigma_r - \sigma_\theta}{r} = 0
\]
\[
\frac{\partial \tau_{zr}}{\partial r} + \frac{\partial \sigma_z}{\partial z} + \frac{\tau_{zr}}{r} = 0
\]

### B. Strain-Displacement Relations
Let $u$ be the radial displacement and $w$ be the vertical displacement:
\[
\varepsilon_r = \frac{\partial u}{\partial r}, \quad \varepsilon_\theta = \frac{u}{r}, \quad \varepsilon_z = \frac{\partial w}{\partial z}
\]
\[
\gamma_{zr} = \frac{\partial u}{\partial z} + \frac{\partial w}{\partial r}
\]

### C. Constitutive Relations (Hooke's Law)
For an isotropic material with Young's modulus $E$ and Poisson's ratio $\nu$:
\[
\varepsilon_z = \frac{1}{E} \left[ \sigma_z - \nu (\sigma_r + \sigma_\theta) \right]
\]
\[
\varepsilon_r = \frac{1}{E} \left[ \sigma_r - \nu (\sigma_\theta + \sigma_z) \right]
\]
\[
\varepsilon_\theta = \frac{1}{E} \left[ \sigma_\theta - \nu (\sigma_r + \sigma_z) \right]
\]
\[
\gamma_{zr} = \frac{2(1+\nu)}{E} \tau_{zr}
\]

---

## 3. Boundary & Interface Conditions

For a system with $N$ layers:

1. **Surface Boundary ($z = 0$):**
   Under a uniform circular load of radius $R$ and pressure $q$:
   - Vertical stress $\sigma_z(r, 0) = -q$ for $r \le R$, and $0$ for $r > R$.
   - Shear stress $\tau_{zr}(r, 0) = 0$.

2. **Interfacial Continuity ($z = z_i$ at the interface of layer $i$ and $i+1$):**
   Assuming a perfect bonded interface (full friction):
   - Vertical stress continuity: $\sigma_z^{(i)} = \sigma_z^{(i+1)}$
   - Shear stress continuity: $\tau_{zr}^{(i)} = \tau_{zr}^{(i+1)}$
   - Vertical displacement continuity: $w^{(i)} = w^{(i+1)}$
   - Radial displacement continuity: $u^{(i)} = u^{(i+1)}$

3. **Subgrade Boundary ($z \to \infty$):**
   - All stresses, strains, and displacements approach zero:
     \[
     \lim_{z \to \infty} (\sigma_j, \varepsilon_j, u, w) = 0
     \]

---

## 4. Mathematical Solution via Hankel Transforms

The governing partial differential equations are transformed into ordinary differential equations using the Hankel transform of order 0 (for vertical stress and deflection) and order 1 (for shear stress and radial displacement).

The vertical stress and deflection at depth $z$ are expressed using Bessel functions $J_0(m \cdot r)$ and $J_1(m \cdot r)$:
\[
w(r, z) = \int_0^\infty m \cdot \phi(m, z) J_0(m \cdot r) dm
\]
where $\phi(m, z)$ is the transfer function determined by solving boundary condition matrices for each layer interface using the transfer matrix method.

---

## 5. Analytical Reference Models

- **Boussinesq (1885):** Solves the case of a single point load on a homogeneous, isotropic elastic half-space.
- **Burmister (1943):** Extended Boussinesq's work to a two-layered elastic system under circular loading.
- **Burmister (1945):** Generalizes the solution to a three-layered elastic system, establishing the foundation for multi-layer elastic analytical solvers.

---

## 6. Engineering Assumptions

The mechanistic solver foundation operates under the following classic pavement mechanics assumptions:
1. Each layer is composed of a homogeneous, isotropic, and linearly elastic material.
2. Materials are weightless and experience no body forces.
3. The surface boundary is free of shear forces.
4. Layer boundaries are infinite in the horizontal direction.
5. The subgrade layer is infinite in depth.
6. The contact pressure between the tire and the pavement is uniform over a circular contact area.

---

## 7. Standard References

1. **Indian Roads Congress (IRC):** *IRC:37-2018: Guidelines for the Design of Flexible Pavements* (specifically cl. 6.2 and 6.4 regarding multi-layered elastic systems).
2. **Burmister, D. M. (1943):** *The Theory of Stresses and Displacements in Layered Systems and Applications to the Design of Airport Runways*. Proceedings, Highway Research Board, Vol. 23.
3. **Boussinesq, J. (1885):** *Application des Potentiels à l'Étude de l'Équilibre et du Mouvement des Solides Élastiques*. Gauthier-Villars, Paris.
4. **Huang, Y. H. (2004):** *Pavement Analysis and Design*, 2nd Edition. Pearson Prentice Hall.
