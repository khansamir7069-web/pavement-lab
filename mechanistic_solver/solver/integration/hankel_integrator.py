"""Hankel integration engine for inverse Hankel transforms.

Integrates response functions using SciPy quad quadrature where available,
falling back to adaptive Simpson's rule.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import math
import time
from typing import Callable

from mechanistic_solver.math.bessel import j0, j1

try:
    from scipy.integrate import quad
    SCIPY_AVAILABLE = True
except ImportError:
    SCIPY_AVAILABLE = False


@dataclass(frozen=True)
class IntegrationResult:
    """Diagnostic report for numerical integration runs."""
    value: float
    estimated_error: float
    converged: bool
    method: str
    upper_limit: float
    subdivisions: int
    warnings: list[str] = field(default_factory=list)
    runtime: float = 0.0

    def to_dict(self) -> dict:
        """Serialize integration result."""
        return {
            "value": self.value,
            "estimated_error": self.estimated_error,
            "converged": self.converged,
            "method": self.method,
            "upper_limit": self.upper_limit,
            "subdivisions": self.subdivisions,
            "warnings": self.warnings,
            "runtime": self.runtime
        }


class HankelIntegrator:
    """Executes order 0 and order 1 Bessel-weighted inverse Hankel integrals.

    The integrals  INT_0^inf f(m) J_nu(m r) dm  have an oscillatory tail (the
    Bessel weight oscillates with period 2*pi/r) on top of an exponentially
    decaying response f(m).  Rather than truncating at a fixed upper limit and
    silently accepting whatever SciPy returns, the tail is integrated panel by
    panel and extended until the incremental contribution is negligible.  If the
    tail never settles, ``converged`` is reported False with an explicit
    diagnostic warning instead of being hidden.
    """

    def __init__(self, default_upper_limit: float = 100.0) -> None:
        self.default_upper_limit = default_upper_limit
        # Hard cap on how far the oscillatory tail is chased before giving up.
        self.max_upper_limit = 4000.0
        self.max_panels = 400

    def integrate_order0(
        self,
        func: Callable[[float], float],
        r: float,
        upper_limit: float | None = None,
        tolerance: float = 1e-6,
        kernel_length: float | None = None
    ) -> IntegrationResult:
        """Compute integral of func(m)*J0(m*r) from 0 to convergence."""
        r_val = float(r)

        def integrand(m: float) -> float:
            if m == 0.0:
                return func(m)  # J0(0) = 1.0
            return func(m) * j0(m * r_val)

        return self._execute_integration(integrand, r_val, kernel_length, upper_limit, tolerance, "J0_kernel")

    def integrate_order1(
        self,
        func: Callable[[float], float],
        r: float,
        upper_limit: float | None = None,
        tolerance: float = 1e-6,
        kernel_length: float | None = None
    ) -> IntegrationResult:
        """Compute integral of func(m)*J1(m*r) from 0 to convergence."""
        r_val = float(r)

        def integrand(m: float) -> float:
            if m == 0.0:
                return 0.0  # J1(0) = 0.0
            return func(m) * j1(m * r_val)

        return self._execute_integration(integrand, r_val, kernel_length, upper_limit, tolerance, "J1_kernel")

    def _panel_width(self, r_val: float, kernel_length: float | None) -> float:
        """Choose a panel width equal to one half-period of the kernel oscillation.

        The integrand oscillates from both the evaluation Bessel weight
        J_nu(m*r) (period 2*pi/r) and the circular-load transform J1(m*a)
        baked into f(m) (period 2*pi/a).  The faster oscillation is set by the
        larger length, so the half-period panel uses L_char = max(r, a).  When
        there is no oscillatory length scale a single base panel is used.
        """
        base = self.default_upper_limit
        length = max(r_val, float(kernel_length or 0.0))
        if length <= 1e-9:
            return base
        return min(base, max(math.pi / length, base / 50.0))

    def _execute_integration(
        self,
        integrand: Callable[[float], float],
        r_val: float,
        kernel_length: float | None,
        upper_limit: float | None,
        tolerance: float,
        kernel_name: str
    ) -> IntegrationResult:
        """Integrate over [0, L], extending L panel by panel until convergence.

        Slowly decaying oscillatory tails (e.g. surface deflection, where the
        J1(m*a) load term decays only as m^-1.5) are accelerated by averaging
        consecutive partial sums: for an alternating, decaying panel series the
        mean of two successive partial sums brackets and converges to the limit
        far faster than the raw sum.
        """
        from mechanistic_solver.core.profiler import global_profiler
        with global_profiler.measure("hankel_integration"):
            start_time = time.perf_counter()
            warnings: list[str] = []

            panel = self._panel_width(r_val, kernel_length)
            # If an explicit upper limit is requested, integrate exactly that
            # span as a single window (legacy/test behaviour) but still report
            # convergence honestly.
            fixed_window = upper_limit is not None
            if fixed_window:
                panel = float(upper_limit)

            total = 0.0
            total_err = 0.0
            lower = 0.0
            panels_used = 0
            converged = False
            prev_total = 0.0
            prev_avg: float | None = None
            value = 0.0
            abs_floor = tolerance

            while panels_used < self.max_panels:
                upper = lower + panel
                val_k, err_k = self._integrate_panel(integrand, lower, upper, tolerance)
                total += val_k
                total_err += err_k
                panels_used += 1
                value = total

                if fixed_window:
                    converged = err_k <= max(tolerance, abs(val_k) * tolerance)
                    break

                # Fast path: a single panel already carries negligible tail.
                if abs(val_k) <= abs(total) * tolerance + abs_floor:
                    converged = True
                    break

                # Averaged partial sum accelerates the oscillatory tail.
                if panels_used >= 2:
                    avg = 0.5 * (total + prev_total)
                    if prev_avg is not None:
                        if abs(avg - prev_avg) <= abs(avg) * tolerance + abs_floor:
                            converged = True
                            value = avg
                            break
                    prev_avg = avg

                if upper >= self.max_upper_limit:
                    break
                prev_total = total
                lower = upper

            duration = time.perf_counter() - start_time
            method = f"scipy_quad_{kernel_name}" if SCIPY_AVAILABLE else f"adaptive_simpson_{kernel_name}"

            if not converged and not fixed_window:
                warnings.append(
                    f"Hankel {kernel_name} tail did not converge within "
                    f"{panels_used} panels up to m={lower + panel:.1f}; last panel "
                    f"contribution {abs(val_k):.3e}. Result is non-converged."
                )
            elif fixed_window and not converged:
                warnings.append(
                    f"Hankel {kernel_name} did not satisfy error tolerance on the "
                    f"requested fixed window [0, {panel:.1f}] (est. error {total_err:.3e})."
                )

            return IntegrationResult(
                value=value,
                estimated_error=total_err,
                converged=converged,
                method=method,
                upper_limit=lower + panel,
                subdivisions=panels_used,
                warnings=warnings,
                runtime=duration,
            )

    def _integrate_panel(
        self,
        integrand: Callable[[float], float],
        lower: float,
        upper: float,
        tolerance: float
    ) -> tuple[float, float]:
        """Integrate a single panel with SciPy quad, falling back to Simpson."""
        if SCIPY_AVAILABLE:
            try:
                return quad(integrand, lower, upper, epsabs=tolerance, epsrel=tolerance, limit=200)
            except Exception:
                pass
        from mechanistic_solver.math.integration import integrate_adaptive_simpson
        val = integrate_adaptive_simpson(integrand, lower, upper, tolerance=tolerance, max_depth=14)
        return val, tolerance * 10.0
