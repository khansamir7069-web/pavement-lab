"""Parser for extracting responses from IITPAVE output files."""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

_NUMERIC_PREFIX_RE = re.compile(r"^\s*([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[Ee][+-]?\d+)?)")

_HEADER_MAPPING = {
    "z": "z",
    "depth": "z",
    "r": "r",
    "radial": "r",
    "radius": "r",
    "sigmaz": "sigma_z",
    "sigmazz": "sigma_z",
    "sigmat": "sigma_t",
    "sigmatt": "sigma_t",
    "sigmatheta": "sigma_t",
    "sigmar": "sigma_r",
    "sigmarr": "sigma_r",
    "taorz": "tau_rz",
    "taurz": "tau_rz",
    "dispz": "deflection",
    "displacement": "deflection",
    "deflection": "deflection",
    "epz": "epsilon_z",
    "epsz": "epsilon_z",
    "epsilonz": "epsilon_z",
    "ept": "epsilon_t",
    "epst": "epsilon_t",
    "epsilont": "epsilon_t",
    "epr": "epsilon_r",
    "epsr": "epsilon_r",
    "epsilonr": "epsilon_r",
}


@dataclass(frozen=True, slots=True)
class ParsedIITPAVEOutput:
    """Structured parsed output from an IITPAVE output text block."""
    source_file: str
    raw_text: str
    critical_responses: Mapping[str, float | None]
    layer_responses: Sequence[Mapping[str, Any]] = field(default_factory=list)
    metadata: Mapping[str, Any] = field(default_factory=dict)
    warnings: Sequence[str] = field(default_factory=list)
    parse_status: str = "failed"  # "success", "partial", "failed"

    def to_dict(self) -> dict[str, Any]:
        """Convert parsed outputs to dictionary."""
        return {
            "source_file": self.source_file,
            "raw_text": self.raw_text,
            "critical_responses": dict(self.critical_responses),
            "layer_responses": list(self.layer_responses),
            "metadata": dict(self.metadata),
            "warnings": list(self.warnings),
            "parse_status": self.parse_status,
        }


class IITPAVEOutputParser:
    """Parses IITPAVE output text blocks to extract key response metrics."""

    def _normalize_token(self, token: str) -> str:
        return re.sub(r"[^A-Za-z0-9]", "", token).lower()

    def _parse_numeric_prefix(self, token: str) -> tuple[float | None, str]:
        match = _NUMERIC_PREFIX_RE.match(token)
        if not match:
            return None, ""
        try:
            val = float(match.group(1))
            suffix = token[match.end():].strip()
            return val, suffix
        except ValueError:
            return None, ""

    def parse(
        self,
        text: str,
        source_file: str = "unknown",
        bituminous_depth_mm: float | None = None,
        subgrade_depth_mm: float | None = None
    ) -> ParsedIITPAVEOutput:
        """Parse raw text of an IITPAVE output file."""
        warnings: list[str] = []
        layer_responses: list[dict[str, Any]] = []
        
        # 1. Look for text summary block first (regex checks)
        summary_t = re.search(
            r"(?:tensile\s+strain\s+(?:at\s+bottom\s+of\s+bituminous|in\s+bituminous\s+layer)|bituminous\s+strain).*?[:=]\s*([+-]?\d+(?:\.\d*)?)",
            text, re.IGNORECASE
        )
        summary_v = re.search(
            r"(?:vertical\s+compressive\s+strain\s+(?:on\s+top\s+of\s+subgrade|in\s+subgrade)|subgrade\s+strain).*?[:=]\s*([+-]?\d+(?:\.\d*)?)",
            text, re.IGNORECASE
        )
        summary_s = re.search(
            r"vertical\s+stress.*?[:=]\s*([+-]?\d+(?:\.\d*)?)",
            text, re.IGNORECASE
        )
        summary_d = re.search(
            r"(?:deflection|displacement).*?[:=]\s*([+-]?\d+(?:\.\d*)?)",
            text, re.IGNORECASE
        )

        eps_t = float(summary_t.group(1)) if summary_t else None
        eps_v = float(summary_v.group(1)) if summary_v else None
        stress_z = float(summary_s.group(1)) if summary_s else None
        defl_z = float(summary_d.group(1)) if summary_d else None

        # 2. Parse table
        header_mapping: dict[str, int] = {}
        header_found = False
        
        lines = text.splitlines()
        for idx, line in enumerate(lines):
            line_str = line.strip()
            if not line_str or line_str.startswith("#"):
                continue
                
            line_str = re.sub(r"([0-9A-DF-Za-df-z])\-", r"\1 -", line_str)
            tokens = line_str.split()
            
            # Check if this is the header row
            if not header_found:
                normalized_tokens = [self._normalize_token(t) for t in tokens]
                # We need at least z and r to detect header
                if "z" in normalized_tokens and "r" in normalized_tokens:
                    # Map roles
                    for t_idx, token in enumerate(tokens):
                        norm = self._normalize_token(token)
                        role = _HEADER_MAPPING.get(norm)
                        if role and role not in header_mapping:
                            header_mapping[role] = t_idx
                    if "z" in header_mapping and "r" in header_mapping:
                        header_found = True
                    continue
            
            # Parse data row
            if header_found and tokens:
                # First column should start with a number
                val, suffix = self._parse_numeric_prefix(tokens[0])
                if val is None:
                    continue
                    
                row_data: dict[str, Any] = {}
                row_valid = True
                
                for role, col_idx in header_mapping.items():
                    if col_idx >= len(tokens):
                        row_valid = False
                        break
                    tok = tokens[col_idx]
                    if role == "z":
                        row_data["z"] = val
                        row_data["label"] = suffix
                    else:
                        v_val, _ = self._parse_numeric_prefix(tok)
                        if v_val is None:
                            row_valid = False
                            break
                        row_data[role] = v_val
                
                if row_valid:
                    layer_responses.append(row_data)

        # 3. If summary was missing, try to extract critical values from parsed table rows
        if layer_responses:
            if eps_t is None and bituminous_depth_mm is not None:
                # Find row matching bituminous_depth_mm
                bit_rows = [r for r in layer_responses if abs(r["z"] - bituminous_depth_mm) <= 1.5]
                if bit_rows:
                    # Select max tensile strain (microstrain)
                    # Note: strain values in IITPAVE may be normalized or raw.
                    # Standard IITPAVE reports strains like 0.000120 or 120.0
                    # We normalize to microstrain (e.g., if value < 0.1, multiply by 1e6)
                    candidates: list[float] = []
                    for r in bit_rows:
                        for key in ["epsilon_t", "epsilon_r"]:
                            if key in r:
                                val = r[key]
                                if abs(val) < 0.1:
                                    val = val * 1e6
                                candidates.append(val)
                    if candidates:
                        eps_t = max(candidates)
                else:
                    warnings.append(f"No table row matches bituminous depth: {bituminous_depth_mm} mm")
                    
            if eps_v is None and subgrade_depth_mm is not None:
                sub_rows = [r for r in layer_responses if abs(r["z"] - subgrade_depth_mm) <= 1.5]
                if sub_rows:
                    candidates = []
                    for r in sub_rows:
                        if "epsilon_z" in r:
                            val = r["epsilon_z"]
                            if abs(val) < 0.1:
                                val = val * 1e6
                            candidates.append(abs(val))  # compressive is often positive/abs strain
                    if candidates:
                        eps_v = max(candidates)
                else:
                    warnings.append(f"No table row matches subgrade top depth: {subgrade_depth_mm} mm")

            # Extract default centerline stress and deflection at first available depth if missing
            if stress_z is None and "sigma_z" in layer_responses[0]:
                stress_z = layer_responses[0]["sigma_z"]
            if defl_z is None and "deflection" in layer_responses[0]:
                defl_z = layer_responses[0]["deflection"]

        status = "failed"
        if layer_responses or eps_t is not None or eps_v is not None:
            status = "success"
            if eps_t is None or eps_v is None:
                status = "partial"
                warnings.append("Some critical responses could not be identified.")
        else:
            warnings.append("Failed to parse any layer responses or critical responses.")

        critical_responses = {
            "epsilon_t_bottom_bituminous": eps_t,
            "epsilon_v_top_subgrade": eps_v,
            "vertical_stress": stress_z,
            "deflection": defl_z
        }

        return ParsedIITPAVEOutput(
            source_file=os.path.basename(source_file),
            raw_text=text,
            critical_responses=critical_responses,
            layer_responses=layer_responses,
            metadata={
                "has_summary_block": summary_t is not None,
                "parsed_rows_count": len(layer_responses),
                "header_columns": list(header_mapping.keys())
            },
            warnings=warnings,
            parse_status=status
        )
