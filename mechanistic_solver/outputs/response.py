"""Standardized solver output models for the mechanistic solver.

Defines the Response object, which serves as the universal output
for all future calculation kernels.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence


@dataclass(frozen=True, slots=True)
class Response:
    """Universal response object containing pavement structural stress/strain calculations."""
    surface_deflection: float
    stress_results: Sequence[Mapping[str, Any]] = field(default_factory=list)
    strain_results: Sequence[Mapping[str, Any]] = field(default_factory=list)
    displacement_results: Sequence[Mapping[str, Any]] = field(default_factory=list)
    principal_results: Sequence[Mapping[str, Any]] = field(default_factory=list)
    layer_results: Sequence[Mapping[str, Any]] = field(default_factory=list)
    runtime_seconds: float = 0.0
    metadata: Mapping[str, Any] = field(default_factory=dict)
    warnings: Sequence[str] = field(default_factory=list)
    solver_version: str = "1.0.0"
    
    # Multilayer validation extensions (Phase 3 Part 3)
    status: str = "computed"
    partial_results: Sequence[Mapping[str, Any]] = field(default_factory=list)
    unsupported_results: Sequence[Mapping[str, Any]] = field(default_factory=list)
    method_metadata: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize the response object to a dict."""
        return {
            "surface_deflection": self.surface_deflection,
            "stress_results": list(self.stress_results),
            "strain_results": list(self.strain_results),
            "displacement_results": list(self.displacement_results),
            "principal_results": list(self.principal_results),
            "layer_results": list(self.layer_results),
            "runtime_seconds": self.runtime_seconds,
            "metadata": dict(self.metadata),
            "warnings": list(self.warnings),
            "solver_version": self.solver_version,
            "status": self.status,
            "partial_results": list(self.partial_results),
            "unsupported_results": list(self.unsupported_results),
            "method_metadata": dict(self.method_metadata),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Response:
        """Deserialize a response object from a dict."""
        return cls(
            surface_deflection=float(data["surface_deflection"]),
            stress_results=data.get("stress_results", []),
            strain_results=data.get("strain_results", []),
            displacement_results=data.get("displacement_results", []),
            principal_results=data.get("principal_results", []),
            layer_results=data.get("layer_results", []),
            runtime_seconds=float(data.get("runtime_seconds", 0.0)),
            metadata=data.get("metadata", {}),
            warnings=data.get("warnings", []),
            solver_version=str(data.get("solver_version", "1.0.0")),
            status=str(data.get("status", "computed")),
            partial_results=data.get("partial_results", []),
            unsupported_results=data.get("unsupported_results", []),
            method_metadata=data.get("method_metadata", {}),
        )
