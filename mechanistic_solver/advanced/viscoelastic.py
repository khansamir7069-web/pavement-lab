"""Viscoelastic material models including Prony series and Temperature-Time Superposition."""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Sequence


@dataclass(frozen=True)
class PronyTerm:
    """A single Maxwell element in a Prony series representation."""
    modulus: float      # E_i (MPa) or compliance D_i (1/MPa)
    relaxation_time: float  # tau_i or retardancy time lambda_i (seconds)


@dataclass(frozen=True)
class ViscoelasticMaterial:
    """Represents a linear viscoelastic material defined by a Prony series."""
    e_inf: float                                # Long-term/equilibrium modulus E_infinity (MPa)
    prony_terms: Sequence[PronyTerm] = field(default_factory=tuple)
    t_ref: float = 20.0                         # Reference temperature for shift factor (Celsius)
    c1: float = 19.0                            # WLF shift factor constant C1
    c2: float = 92.0                            # WLF shift factor constant C2 (Kelvin or Celsius)
    activation_energy_j_mol: float = 200000.0  # Arrhenius activation energy delta_E (J/mol)

    def get_relaxation_modulus(self, t: float, temp: float | None = None) -> float:
        """Calculate relaxation modulus E(t) at time t and temperature temp (Celsius).

        Formula: E(t) = E_inf + sum( E_i * exp(-t / (a_T * tau_i)) )
        Reference: Huang, Y.H. (2004). Pavement Analysis and Design.
        """
        if t < 0.0:
            raise ValueError("Time must be non-negative.")
            
        a_t = self.get_shift_factor(temp) if temp is not None else 1.0
        
        val = self.e_inf
        for term in self.prony_terms:
            reduced_time = t / a_t
            if term.relaxation_time > 0.0:
                val += term.modulus * math.exp(-reduced_time / term.relaxation_time)
            else:
                val += term.modulus
        return val

    def get_dynamic_modulus(self, frequency_hz: float, temp: float | None = None) -> float:
        """Calculate dynamic modulus |E*(omega)| at frequency_hz and temperature temp.

        Formula:
          omega = 2 * pi * frequency
          E'(omega) = E_inf + sum( (E_i * omega^2 * tau^2) / (1 + omega^2 * tau^2) )
          E''(omega) = sum( (E_i * omega * tau) / (1 + omega^2 * tau^2) )
          |E*| = sqrt(E'^2 + E''^2)
        Reference: AASHTO R 62 (Standard Practice for Developing Dynamic Modulus Master Curves).
        """
        if frequency_hz <= 0.0:
            raise ValueError("Frequency must be positive.")
            
        a_t = self.get_shift_factor(temp) if temp is not None else 1.0
        # Convert frequency to angular frequency omega (rad/s) and apply shift factor
        omega = 2.0 * math.pi * frequency_hz * a_t
        
        e_prime = self.e_inf
        e_double_prime = 0.0
        
        for term in self.prony_terms:
            w_tau = omega * term.relaxation_time
            denom = 1.0 + w_tau**2
            e_prime += (term.modulus * w_tau**2) / denom
            e_double_prime += (term.modulus * w_tau) / denom
            
        return math.sqrt(e_prime**2 + e_double_prime**2)

    def get_shift_factor(self, temp: float, method: str = "wlf") -> float:
        """Compute the temperature shift factor a_T using WLF or Arrhenius.

        WLF Formula: log10(a_T) = -C1 * (T - T_ref) / (C2 + T - T_ref)
        Arrhenius Formula: ln(a_T) = (E_a / R) * (1/(T + 273.15) - 1/(T_ref + 273.15))
        Reference: Williams, M.L., Landel, R.F., & Ferry, J.D. (1955). J. Am. Chem. Soc.
        """
        if method.lower() == "wlf":
            dt = temp - self.t_ref
            denom = self.c2 + dt
            if abs(denom) < 1e-5:
                denom = 1e-5
            log_a_t = -self.c1 * dt / denom
            return 10.0**log_a_t
        elif method.lower() == "arrhenius":
            r = 8.314  # Gas constant J/(mol*K)
            t_k = temp + 273.15
            t_ref_k = self.t_ref + 273.15
            ln_a_t = (self.activation_energy_j_mol / r) * (1.0 / t_k - 1.0 / t_ref_k)
            return math.exp(ln_a_t)
        else:
            raise ValueError(f"Unknown shift factor method: {method}")
