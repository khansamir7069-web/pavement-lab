"""Conservative layer thickness optimization engine."""
from __future__ import annotations

from typing import Any, Mapping, Sequence

from mechanistic_solver.core.models import Layer, ObservationPoint, Pavement, WheelLoad
from mechanistic_solver.solver.engine import MechanisticSolver
from mechanistic_solver.design.adequacy import check_structural_adequacy


def optimize_bituminous_thickness(
    pavement: Pavement,
    loads: Sequence[WheelLoad],
    design_traffic_msa: float,
    min_thickness_mm: float = 40.0,
    max_thickness_mm: float = 300.0,
    step_mm: float = 5.0,
    max_iterations: int = 30
) -> Mapping[str, Any]:
    from mechanistic_solver.licensing import active_license, FEATURE_LAYER_OPTIMIZATION
    active_license.check_feature(FEATURE_LAYER_OPTIMIZATION)
    
    from mechanistic_solver.core.profiler import global_profiler
    global_profiler.start_time("optimization")
    try:
        return _optimize_bituminous_thickness_internal(
            pavement=pavement,
            loads=loads,
            design_traffic_msa=design_traffic_msa,
            min_thickness_mm=min_thickness_mm,
            max_thickness_mm=max_thickness_mm,
            step_mm=step_mm,
            max_iterations=max_iterations
        )
    finally:
        global_profiler.stop_time("optimization")


def _optimize_bituminous_thickness_internal(
    pavement: Pavement,
    loads: Sequence[WheelLoad],
    design_traffic_msa: float,
    min_thickness_mm: float = 40.0,
    max_thickness_mm: float = 300.0,
    step_mm: float = 5.0,
    max_iterations: int = 30
) -> Mapping[str, Any]:
    history: list[dict[str, Any]] = []
    warnings: list[str] = []
    
    if not pavement.layers:
        return {
            "optimal_thickness_mm": None,
            "optimized_pavement": pavement,
            "history": [],
            "converged": False,
            "warnings": ["No layers in pavement to optimize."]
        }

    solver = MechanisticSolver(mode="multilayer")
    base_pavement = pavement
    
    # Extract baseline properties of first layer
    first_layer = base_pavement.layers[0]
    other_layers = list(base_pavement.layers[1:])
    e_bc_mpa = first_layer.elastic_modulus

    # Subgrade modulus is subgrade.elastic_modulus
    subgrade_modulus = base_pavement.subgrade.elastic_modulus

    def evaluate_thickness(t: float, trial_idx: int) -> dict[str, Any]:
        # Build modified pavement
        opt_first_layer = Layer(
            name=first_layer.name,
            thickness=t,
            elastic_modulus=first_layer.elastic_modulus,
            poisson_ratio=first_layer.poisson_ratio,
            density=first_layer.density,
            temperature=first_layer.temperature,
            nonlinear_flag=first_layer.nonlinear_flag,
            viscoelastic_flag=first_layer.viscoelastic_flag,
            orthotropic_flag=first_layer.orthotropic_flag,
            drainage_flag=first_layer.drainage_flag
        )
        trial_pavement = Pavement(
            layers=tuple([opt_first_layer] + other_layers),
            subgrade=base_pavement.subgrade,
            surface=base_pavement.surface,
            boundary=base_pavement.boundary
        )
        
        # Build observation points: bottom of first layer and top of subgrade
        h1 = t
        subgrade_depth = t + sum(float(l.thickness) for l in other_layers)
        
        pts = [
            ObservationPoint(0.0, 0.0, h1),
            ObservationPoint(0.0, 0.0, subgrade_depth)
        ]
        
        try:
            # Solve
            response = solver.solve(trial_pavement, loads, pts)
            
            # Extract strains
            # Point 0: bottom of bituminous
            strain_0 = response.strain_results[0]
            # Compression-positive solver: take strain magnitudes for IRC:37 models.
            eps_t = max(abs(strain_0.get("epsilon_r") or 0.0), abs(strain_0.get("epsilon_t") or 0.0))

            # Point 1: top of subgrade
            strain_1 = response.strain_results[1]
            eps_v = abs(strain_1.get("epsilon_z") or 0.0)
            
            # Check adequacy
            adequacy = check_structural_adequacy(eps_t, e_bc_mpa, eps_v, design_traffic_msa)
            
            trial_record = {
                "trial_index": trial_idx,
                "thickness_mm": t,
                "epsilon_t": eps_t,
                "epsilon_v": eps_v,
                "fatigue_passed": adequacy["fatigue_status"]["passed"],
                "rutting_passed": adequacy["rutting_status"]["passed"],
                "overall_passed": adequacy["overall_passed"],
                "utilization_ratio": max(
                    adequacy["fatigue_status"]["utilization_ratio"],
                    adequacy["rutting_status"]["utilization_ratio"]
                ),
                "solver_status": response.status
            }
            return trial_record
        except Exception as e:
            return {
                "trial_index": trial_idx,
                "thickness_mm": t,
                "error": str(e),
                "overall_passed": False
            }

    # Initial trial
    current_thickness = float(first_layer.thickness)
    trial_rec = evaluate_thickness(current_thickness, 0)
    history.append(trial_rec)
    
    if "error" in trial_rec:
        warnings.append(f"Initial trial thickness evaluation failed: {trial_rec['error']}")
        return {
            "optimal_thickness_mm": current_thickness,
            "optimized_pavement": pavement,
            "history": history,
            "converged": False,
            "warnings": warnings
        }

    init_passed = trial_rec["overall_passed"]
    best_passing_thickness = current_thickness if init_passed else None
    
    converged = False
    
    if init_passed:
        # Pavement is adequate. Try reducing thickness to optimize
        for i in range(1, max_iterations):
            next_thickness = current_thickness - step_mm
            if next_thickness < min_thickness_mm:
                warnings.append(f"Clamped at minimum bituminous thickness: {min_thickness_mm} mm")
                converged = True
                break
                
            rec = evaluate_thickness(next_thickness, i)
            history.append(rec)
            
            if "error" in rec or not rec["overall_passed"]:
                # Failed or errored. Stop. Best passing thickness was current_thickness.
                converged = True
                break
                
            current_thickness = next_thickness
            best_passing_thickness = current_thickness
    else:
        # Pavement fails. Try increasing thickness to satisfy adequacy
        for i in range(1, max_iterations):
            next_thickness = current_thickness + step_mm
            if next_thickness > max_thickness_mm:
                warnings.append(f"Exceeded maximum bituminous thickness: {max_thickness_mm} mm")
                break
                
            rec = evaluate_thickness(next_thickness, i)
            history.append(rec)
            
            if "error" in rec:
                warnings.append(f"Evaluation error at thickness {next_thickness}: {rec['error']}")
                break
                
            if rec["overall_passed"]:
                best_passing_thickness = next_thickness
                converged = True
                break
                
            current_thickness = next_thickness

    optimal_thickness = best_passing_thickness if best_passing_thickness is not None else current_thickness
    
    # Build optimal pavement
    opt_first_layer = Layer(
        name=first_layer.name,
        thickness=optimal_thickness,
        elastic_modulus=first_layer.elastic_modulus,
        poisson_ratio=first_layer.poisson_ratio,
        density=first_layer.density,
        temperature=first_layer.temperature,
        nonlinear_flag=first_layer.nonlinear_flag,
        viscoelastic_flag=first_layer.viscoelastic_flag,
        orthotropic_flag=first_layer.orthotropic_flag,
        drainage_flag=first_layer.drainage_flag
    )
    optimized_pavement = Pavement(
        layers=tuple([opt_first_layer] + other_layers),
        subgrade=base_pavement.subgrade,
        surface=base_pavement.surface,
        boundary=base_pavement.boundary
    )

    return {
        "optimal_thickness_mm": optimal_thickness,
        "optimized_pavement": optimized_pavement,
        "history": history,
        "converged": converged,
        "warnings": warnings
    }
