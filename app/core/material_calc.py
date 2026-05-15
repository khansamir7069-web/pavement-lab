"""Material Calculation for Preparation of Bituminous Mix Sample.

Mirrors the Excel sheet "Material  Cal" exactly. The sheet has two parallel
blocks:

  LEFT  — "Standard Bituminous Mix Sample"     (Pb_std, agg_wt fixed at 1200g)
  RIGHT — "Material Calculation For Preparation of Bituminous Mix Sample"
          (Pb_target, weights scaled to the standard total)

Plus a per-fraction dry-material breakdown (25mm, 20mm, 6mm, SD, Cement)
weighted by the gradation blend ratios.

Excel formulas reproduced literally (CALCULATION_SPEC, sheet "Material  Cal"):

  Standard block:
    D9  = 100 - D6                 # aggregate %
    D10 = D6                       # bitumen %
    E9  = 1200                     # aggregate weight (gm), user input
    E10 = E9 * D6 / D9             # bitumen weight (gm)
    D11 = D9 + D10                 # total mix %
    E11 = E9 + E10                 # total mix weight
    D13 = E9                       # aggregate weight (gm) restated
    D14 = E11 * D6 / 100           # bitumen weight (gm) restated
    D15 = D13 + D14                # total bituminous mix weight

  Target block:
    I9  = 100 - I6                 # aggregate %
    I10 = I6                       # bitumen %
    J9  = I9 * D15 / 100           # scaled aggregate weight
    J10 = I10 * D15 / 100          # scaled bitumen weight
    I11 = I9 + I10                 # total mix %
    J11 = J9 + J10                 # total mix weight

  Dry material per fraction (each block):
    Standard:  E_row = D13 * blend_ratio
    Target:    J_row = J9 * blend_ratio
    Totals are SUM() over rows.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping


@dataclass(frozen=True, slots=True)
class MaterialCalcInput:
    standard_bitumen_pct: float = 4.5
    standard_aggregate_weight_g: float = 1200.0
    target_bitumen_pct: float = 4.0
    # Blend ratios per fraction (must come from the same gradation input).
    blend_ratios: Mapping[str, float] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.blend_ratios is None:
            object.__setattr__(
                self, "blend_ratios",
                {"25mm": 0.23, "20mm": 0.11, "6mm": 0.32, "SD": 0.32, "Cement": 0.02},
            )


@dataclass(frozen=True, slots=True)
class MaterialBlock:
    bitumen_pct: float
    aggregate_pct: float
    aggregate_weight_g: float
    bitumen_weight_g: float
    total_mix_pct: float
    total_mix_weight_g: float


@dataclass(frozen=True, slots=True)
class DryMaterialRow:
    name: str
    fraction: float           # 0..1, e.g. 0.23
    weight_g: float


@dataclass(frozen=True, slots=True)
class MaterialCalcResult:
    standard: MaterialBlock
    target: MaterialBlock
    dry_material_standard: tuple[DryMaterialRow, ...]
    dry_material_target: tuple[DryMaterialRow, ...]

    @property
    def total_dry_standard_g(self) -> float:
        return sum(r.weight_g for r in self.dry_material_standard)

    @property
    def total_dry_target_g(self) -> float:
        return sum(r.weight_g for r in self.dry_material_target)


def compute_material_calc(inp: MaterialCalcInput) -> MaterialCalcResult:
    pb_std = inp.standard_bitumen_pct
    agg_wt_std = inp.standard_aggregate_weight_g

    # ----- Standard block (matches Excel D6..E15) -----
    agg_pct_std = 100.0 - pb_std
    bit_wt_std = agg_wt_std * pb_std / agg_pct_std if agg_pct_std else 0.0
    total_mix_wt_std = agg_wt_std + bit_wt_std        # D15
    total_mix_pct_std = agg_pct_std + pb_std

    # Excel restates D14 = D15 * D6 / 100, mathematically identical to bit_wt_std
    standard = MaterialBlock(
        bitumen_pct=pb_std,
        aggregate_pct=agg_pct_std,
        aggregate_weight_g=agg_wt_std,
        bitumen_weight_g=bit_wt_std,
        total_mix_pct=total_mix_pct_std,
        total_mix_weight_g=total_mix_wt_std,
    )

    # ----- Target block (matches Excel I6..J11) -----
    pb_tgt = inp.target_bitumen_pct
    agg_pct_tgt = 100.0 - pb_tgt
    agg_wt_tgt = agg_pct_tgt * total_mix_wt_std / 100.0     # J9
    bit_wt_tgt = pb_tgt * total_mix_wt_std / 100.0          # J10
    total_mix_wt_tgt = agg_wt_tgt + bit_wt_tgt              # J11
    total_mix_pct_tgt = agg_pct_tgt + pb_tgt

    target = MaterialBlock(
        bitumen_pct=pb_tgt,
        aggregate_pct=agg_pct_tgt,
        aggregate_weight_g=agg_wt_tgt,
        bitumen_weight_g=bit_wt_tgt,
        total_mix_pct=total_mix_pct_tgt,
        total_mix_weight_g=total_mix_wt_tgt,
    )

    # ----- Dry material breakdown -----
    rows_std: list[DryMaterialRow] = []
    rows_tgt: list[DryMaterialRow] = []
    for name, frac in inp.blend_ratios.items():
        rows_std.append(DryMaterialRow(name=name, fraction=frac,
                                       weight_g=agg_wt_std * frac))
        rows_tgt.append(DryMaterialRow(name=name, fraction=frac,
                                       weight_g=agg_wt_tgt * frac))

    return MaterialCalcResult(
        standard=standard,
        target=target,
        dry_material_standard=tuple(rows_std),
        dry_material_target=tuple(rows_tgt),
    )
