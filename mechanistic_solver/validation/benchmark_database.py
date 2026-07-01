"""Discovers, parses, and indexes benchmark validation cases."""
from __future__ import annotations

from dataclasses import dataclass
import json
import os
from typing import Any, Sequence

from mechanistic_solver.validation.parity_models import ParityCase
from mechanistic_solver.validation.iitpave_parser import IITPAVEOutputParser


@dataclass(frozen=True, slots=True)
class BenchmarkCase:
    """Represents an ingested benchmark validation case."""
    case_id: str
    is_official: bool
    json_path: str
    out_path: str | None
    parity_case: ParityCase | None
    parse_status: str  # "success", "missing_out", "corrupt_json", "failed"
    error_message: str = ""


class BenchmarkDatabase:
    """Manages the discovery, indexing, and loading of benchmark test cases."""

    def __init__(self, root_dir: str | None = None) -> None:
        self.root_dir = root_dir or os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "tests", "fixtures", "iitpave"
        )
        self.cases: list[BenchmarkCase] = []

    def discover_cases(self) -> Sequence[BenchmarkCase]:
        """Scan directories to index benchmark JSON files and matching .out outputs."""
        self.cases = []
        if not os.path.exists(self.root_dir):
            return self.cases

        # Walk through all directories in root_dir
        for root, _, files in os.walk(self.root_dir):
            is_official = "official" in root.lower() or "official" in os.path.basename(root).lower()
            
            for file in files:
                if file.endswith(".json") and not file.endswith("schema.json") and not file.startswith("sample_iitpave_expected"):
                    json_path = os.path.join(root, file)
                    case_id = os.path.splitext(file)[0]
                    
                    # Check for matching .out or .txt file
                    out_candidate_out = os.path.join(root, f"{case_id}.out")
                    out_candidate_txt = os.path.join(root, f"{case_id}.txt")
                    
                    out_path = None
                    if os.path.exists(out_candidate_out):
                        out_path = out_candidate_out
                    elif os.path.exists(out_candidate_txt):
                        out_path = out_candidate_txt
                        
                    # Load case
                    benchmark_case = self._load_case(case_id, json_path, out_path, is_official)
                    self.cases.append(benchmark_case)
                    
        return self.cases

    def _load_case(
        self,
        case_id: str,
        json_path: str,
        out_path: str | None,
        is_official: bool
    ) -> BenchmarkCase:
        """Parse JSON inputs and matching output files into a BenchmarkCase."""
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            return BenchmarkCase(
                case_id=case_id,
                is_official=is_official,
                json_path=json_path,
                out_path=out_path,
                parity_case=None,
                parse_status="corrupt_json",
                error_message=f"JSON decoding or read failed: {str(e)}"
            )

        # Build expected values from .out file if available, or fallback to JSON expected outputs
        expected_responses: dict[str, float | None] = {}
        warnings: list[str] = []
        
        if out_path:
            try:
                with open(out_path, "r", encoding="utf-8") as f:
                    out_text = f.read()
                
                # Derive depths from json to help parser
                bit_depth = None
                sub_depth = None
                
                if "inputs" in data:
                    layers = data["inputs"].get("layers", [])
                    if layers:
                        bit_depth = float(layers[0].get("thickness", 0.0))
                        sub_depth = sum(float(l.get("thickness", 0.0)) for l in layers)
                
                parser = IITPAVEOutputParser()
                parsed = parser.parse(
                    out_text,
                    source_file=out_path,
                    bituminous_depth_mm=bit_depth,
                    subgrade_depth_mm=sub_depth
                )
                
                if parsed.parse_status == "failed":
                    warnings.append(f"IITPAVE output file parse failed: {parsed.warnings}")
                else:
                    expected_responses = dict(parsed.critical_responses)
                    if parsed.warnings:
                        warnings.extend(parsed.warnings)
            except Exception as e:
                warnings.append(f"Failed to read/parse output file: {str(e)}")

        # Fallback to json expected outputs if not parsed from out file
        json_expected = data.get("expected_iitpave_outputs") or data.get("expected_outputs")
        if json_expected:
            for k, v in json_expected.items():
                if expected_responses.get(k) is None:
                    expected_responses[k] = v

        try:
            # Build the ParityCase object
            # Map json inputs structure to ParityCase properties
            inputs = data.get("inputs")
            if not inputs:
                raise KeyError("Missing 'inputs' root in case definition.")
                
            p_case = ParityCase.from_dict({
                "case_id": case_id,
                "layers": inputs.get("layers", []),
                "subgrade": inputs.get("subgrade", {}),
                "loads": inputs.get("loads", []),
                "observation_points": data.get("observation_points", []),
                "expected_iitpave_outputs": expected_responses,
                "tolerance_limits": data.get("tolerance_limits", {}),
                "source_file": out_path or json_path,
                "notes": data.get("notes", "") + (" | " + " | ".join(warnings) if warnings else ""),
            })
            
            parse_status = "success"
            if not out_path:
                parse_status = "missing_out"
                
            return BenchmarkCase(
                case_id=case_id,
                is_official=is_official,
                json_path=json_path,
                out_path=out_path,
                parity_case=p_case,
                parse_status=parse_status
            )
        except Exception as e:
            return BenchmarkCase(
                case_id=case_id,
                is_official=is_official,
                json_path=json_path,
                out_path=out_path,
                parity_case=None,
                parse_status="failed",
                error_message=f"Failed to construct parity case: {str(e)}"
            )
