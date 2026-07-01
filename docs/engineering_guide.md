# RoadX Solver Engineering Guide

This guide details the mathematical formulations and design equations governing multi-layer elastic analysis (MLEA) in RoadX.

## 1. Multi-Layer Elastic Theory & Burmister Formulations

RoadX solves the governing differential equations of equilibrium for axisymmetric systems under circular loads. For an $n$-layer system, stresses and displacements in each layer are expressed using stress functions integrated over Hankel parameters:

$$w_i(r,z) = \int_{0}^{\infty} J_0(mr) \cdot [A_i e^{mz} + B_i e^{-mz} + C_i z e^{mz} + D_i z e^{-mz}] \, dm$$

System boundary conditions at layer interfaces assume fully bonded contacts, yielding equal vertical stresses, displacements, and shear continuity:
- $\sigma_{z,i} = \sigma_{z,i+1}$
- $\tau_{rz,i} = \tau_{rz,i+1}$
- $u_{r,i} = u_{r,i+1}$
- $w_i = w_{i+1}$

## 2. Hankel Quadrature Integration
Quadrature is performed using adaptive Simpson's rule or SciPy Clenshaw-Curtis integrations. Extrapolation limits are clamped based on user profile settings to ensure numerical stability at deep layer interfaces.

## 3. IRC 37 Design Criteria
- **Bituminous Fatigue cracking model:** Allowable repetitions $N_f$ is computed via:
  $$N_f = C \cdot k_1 \cdot \left(\frac{1}{\epsilon_t}\right)^{k_2} \cdot \left(\frac{1}{E_{BC}}\right)^{k_3}$$
- **Subgrade Rutting model:** Allowable repetitions $N_r$ is computed via:
  $$N_r = k_r \cdot \left(\frac{1}{\epsilon_v}\right)^{k_v}$$
where values represent default IRC:37-2018 parameters.
