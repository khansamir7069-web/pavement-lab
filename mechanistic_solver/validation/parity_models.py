"""Parity data models representing IITPAVE validation comparison structures."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from mechanistic_solver.core.models import Layer, ObservationPoint, WheelLoad


@dataclass(frozen=True, slots=True)
class ParityCase:
    """Represents a single validation test case comparing RoadX solver to IITPAVE benchmark."""
    case_id: str
    layers: Sequence[Layer]
    subgrade: Layer
    loads: Sequence[WheelLoad]
    observation_points: Sequence[ObservationPoint]
    expected_iitpave_outputs: Mapping[str, float | None]
    tolerance_limits: Mapping[str, Any] = field(default_factory=dict)
    source_file: str = ""
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Serialize validation case to dictionary."""
        return {
            "case_id": self.case_id,
            "layers": [l.to_dict() for l in self.layers],
            "subgrade": self.subgrade.to_dict(),
            "loads": [
                {
                    "wheel_load": ld.wheel_load,
                    "pressure": ld.pressure,
                    "radius": ld.radius,
                    "x": ld.x,
                    "y": ld.y
                }
                for ld in self.loads
            ],
            "observation_points": [{"x": p.x, "y": p.y, "z": p.z} for p in self.observation_points],
            "expected_iitpave_outputs": dict(self.expected_iitpave_outputs),
            "tolerance_limits": dict(self.tolerance_limits),
            "source_file": self.source_file,
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ParityCase:
        """Deserialize validation case from dictionary."""
        from mechanistic_solver.core.models import ObservationPoint, WheelLoad
        return cls(
            case_id=str(data["case_id"]),
            layers=[Layer.from_dict(l) for l in data.get("layers", [])],
            subgrade=Layer.from_dict(data["subgrade"]),
            loads=[
                WheelLoad(
                    wheel_load=float(ld["wheel_load"]),
                    pressure=float(ld["pressure"]),
                    radius=float(ld["radius"]),
                    x=float(ld.get("x", 0.0)),
                    y=float(ld.get("y", 0.0))
                )
                for ld in data.get("loads", [])
            ],
            observation_points=[
                ObservationPoint(
                    x=float(p["x"]),
                    y=float(p["y"]),
                    z=float(p["z"])
                )
                for p in data.get("observation_points", [])
            ],
            expected_iitpave_outputs=data.get("expected_iitpave_outputs", {}),
            tolerance_limits=data.get("tolerance_limits", {}),
            source_file=str(data.get("source_file", "")),
            notes=str(data.get("notes", "")),
        )


@dataclass(frozen=True, slots=True)
class ParityResult:
    """Represents the results of running comparison solver outputs against expected values."""
    case_id: str
    roadx_outputs: Mapping[str, float | None]
    expected_outputs: Mapping[str, float | None]
    absolute_errors: Mapping[str, float | None]
    relative_errors: Mapping[str, float | None]
    pass_status: Mapping[str, bool]
    overall_passed: bool
    warnings: Sequence[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Serialize comparison results to dictionary."""
        return {
            "case_id": self.case_id,
            "roadx_outputs": dict(self.roadx_outputs),
            "expected_outputs": dict(self.expected_outputs),
            "absolute_errors": dict(self.absolute_errors),
            "relative_errors": dict(self.relative_errors),
            "pass_status": dict(self.pass_status),
            "overall_passed": self.overall_passed,
            "warnings": list(self.warnings),
        }


@dataclass(frozen=True, slots=True)
class ParityMetric:
    """Holds a singular parity error metric description."""
    name: str
    value: float | None
    description: str = ""


@dataclass(frozen=True, slots=True)
class ParitySummary:
    """Aggregated validation statistics across multiple test runs."""
    case_results: Sequence[ParityResult]
    total_cases: int
    passed_cases: int
    failed_cases: int
    overall_status: str  # "experimental", "validated_case_pass", "validated_case_fail"
    metrics: Mapping[str, float | None]
    generation_timestamp: str
    warnings: Sequence[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Serialize summary record to dictionary."""
        return {
            "total_cases": self.total_cases,
            "passed_cases": self.passed_cases,
            "failed_cases": self.failed_cases,
            "overall_status": self.overall_status,
            "metrics": dict(self.metrics),
            "generation_timestamp": self.generation_timestamp,
            "warnings": list(self.warnings),
            "case_results": [r.to_dict() for r in self.case_results],
        }
