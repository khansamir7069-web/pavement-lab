"""End-to-end parity test: software outputs must match the cached Excel
values for every row of the Shirdi DBM golden fixture, within 1e-9 absolute.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.core import (
    BitumenSGInput,
    CoarseAggSGInput,
    FineAggSGInput,
    GmbGroup,
    GmbInput,
    GmbSpecimen,
    GmmInput,
    GmmSampleRaw,
    GradationInput,
    MaterialCalcInput,
    MixDesignInput,
    StabilityFlowInput,
    StabilitySpecimen,
    compute_bitumen_sg,
    compute_bulk_sg_blend,
    compute_coarse_sg,
    compute_fine_sg,
    compute_gmb,
    compute_gmm,
    compute_gradation,
    compute_material_calc,
    compute_mix_design,
    compute_stability_flow,
)
from app.core.models import ProjectInfo

FIXTURE = Path(__file__).with_name("golden") / "shirdi_dbm.json"
TOL = 1e-9


@pytest.fixture(scope="module")
def fx() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def _g(grad_fx: dict) -> GradationInput:
    pass_pct = {k: tuple(v) for k, v in grad_fx["pass_pct"].items()}
    return GradationInput(
        sieve_sizes_mm=tuple(grad_fx["sieve_sizes_mm"]),
        pass_pct=pass_pct,
        blend_ratios=grad_fx["blend_ratios"],
        spec_lower=tuple(grad_fx["spec_lower"]),
        spec_upper=tuple(grad_fx["spec_upper"]),
    )


def test_gradation_combined_matches_excel(fx):
    g = _g(fx["gradation"])
    res = compute_gradation(g)
    for i, (got, exp) in enumerate(zip(res.combined_pass_pct, fx["gradation"]["expected_combined"])):
        assert abs(got - exp) < TOL, f"row {i}: software={got} excel={exp} delta={got - exp}"


def test_bitumen_sg_matches_excel(fx):
    bit = fx["sp_gr"]["bitumen"]
    sg = compute_bitumen_sg(BitumenSGInput(
        a_empty=tuple(bit["A"]),
        b_water=tuple(bit["B"]),
        c_sample=tuple(bit["C"]),
        d_sample_water=tuple(bit["D"]),
    ))
    exp = fx["sp_gr"]["expected"]["Gb_avg"]
    assert abs(sg - exp) < TOL


def test_coarse_25_bulk_od_avg(fx):
    blk = fx["sp_gr"]["coarse_25"]
    res = compute_coarse_sg(CoarseAggSGInput(
        a_sample_plus_container_water=tuple(blk["A"]),
        b_container_in_water=tuple(blk["B"]),
        c_ssd_in_air=tuple(blk["C"]),
        d_ovendry_in_air=tuple(blk["D"]),
    ))
    exp = fx["sp_gr"]["expected"]["25mm_bulk_od_avg"]
    assert abs(res.avg_bulk_ovendry - exp) < TOL


def test_coarse_20_bulk_od_avg(fx):
    blk = fx["sp_gr"]["coarse_20"]
    res = compute_coarse_sg(CoarseAggSGInput(
        a_sample_plus_container_water=tuple(blk["A"]),
        b_container_in_water=tuple(blk["B"]),
        c_ssd_in_air=tuple(blk["C"]),
        d_ovendry_in_air=tuple(blk["D"]),
    ))
    exp = fx["sp_gr"]["expected"]["20mm_bulk_od_avg"]
    assert abs(res.avg_bulk_ovendry - exp) < TOL


def test_fine_sg_6mm(fx):
    blk = fx["sp_gr"]["fine_6"]
    res = compute_fine_sg(FineAggSGInput(
        w1_empty=tuple(blk["W1"]),
        w2_dry_sample=tuple(blk["W2"]),
        w3_dry_sample_water=tuple(blk["W3"]),
        w4_water_only=tuple(blk["W4"]),
    ))
    exp = fx["sp_gr"]["expected"]["6mm_sg_avg"]
    assert abs(res.avg_bulk_ovendry - exp) < TOL


def test_fine_sg_stone_dust(fx):
    blk = fx["sp_gr"]["fine_sd"]
    res = compute_fine_sg(FineAggSGInput(
        w1_empty=tuple(blk["W1"]),
        w2_dry_sample=tuple(blk["W2"]),
        w3_dry_sample_water=tuple(blk["W3"]),
        w4_water_only=tuple(blk["W4"]),
    ))
    exp = fx["sp_gr"]["expected"]["SD_sg_avg"]
    assert abs(res.avg_bulk_ovendry - exp) < TOL


def test_gsb_blend(fx):
    # Build per-aggregate avg bulk OD SG using results above
    blk25 = fx["sp_gr"]["coarse_25"]
    g25 = compute_coarse_sg(CoarseAggSGInput(
        a_sample_plus_container_water=tuple(blk25["A"]),
        b_container_in_water=tuple(blk25["B"]),
        c_ssd_in_air=tuple(blk25["C"]),
        d_ovendry_in_air=tuple(blk25["D"]),
    )).avg_bulk_ovendry
    blk20 = fx["sp_gr"]["coarse_20"]
    g20 = compute_coarse_sg(CoarseAggSGInput(
        a_sample_plus_container_water=tuple(blk20["A"]),
        b_container_in_water=tuple(blk20["B"]),
        c_ssd_in_air=tuple(blk20["C"]),
        d_ovendry_in_air=tuple(blk20["D"]),
    )).avg_bulk_ovendry
    blk6 = fx["sp_gr"]["fine_6"]
    g6 = compute_fine_sg(FineAggSGInput(
        w1_empty=tuple(blk6["W1"]),
        w2_dry_sample=tuple(blk6["W2"]),
        w3_dry_sample_water=tuple(blk6["W3"]),
        w4_water_only=tuple(blk6["W4"]),
    )).avg_bulk_ovendry
    blkSD = fx["sp_gr"]["fine_sd"]
    gSD = compute_fine_sg(FineAggSGInput(
        w1_empty=tuple(blkSD["W1"]),
        w2_dry_sample=tuple(blkSD["W2"]),
        w3_dry_sample_water=tuple(blkSD["W3"]),
        w4_water_only=tuple(blkSD["W4"]),
    )).avg_bulk_ovendry

    # Excel J37 sums only the 4 aggregates (not cement) — see CALCULATION_SPEC §3.5
    blend = {k: v for k, v in fx["gradation"]["blend_ratios"].items() if k != "Cement"}
    bulk_sg = {"25mm": g25, "20mm": g20, "6mm": g6, "SD": gSD}
    gsb = compute_bulk_sg_blend(blend, bulk_sg)
    exp = fx["sp_gr"]["expected"]["Gsb"]
    assert abs(gsb - exp) < TOL, f"Gsb mismatch: {gsb} vs {exp}, delta={gsb - exp}"


def test_gmb_per_group_avg(fx):
    groups = []
    for grp in fx["gmb"]["groups"]:
        specs = tuple(
            GmbSpecimen(
                a_dry_in_air=s["A"],
                c_in_water=s["D"],
                b_ssd_in_air=s["B"],
            )
            for s in grp["specimens"]
        )
        groups.append(GmbGroup(bitumen_pct=grp["pb_pct"], specimens=specs))
    res = compute_gmb(GmbInput(groups=tuple(groups)))

    # Expected averages from Charts!D2:D6
    expected = [row["gmb"] for row in fx["summary_expected"]]
    for grp_res, exp in zip(res.groups, expected):
        assert abs(grp_res.mean - exp) < TOL, (
            f"Gmb avg at Pb={grp_res.bitumen_pct}: {grp_res.mean} vs {exp}"
        )


def test_gmm_avg_at_ref_and_gse(fx):
    samples = tuple(
        GmmSampleRaw(
            a_empty_flask=s["A"],
            b_flask_plus_dry_sample=s["B"],
            d_flask_filled_water=s["D"],
            e_flask_sample_water=s["E"],
        )
        for s in fx["gmm"]["samples_ref"]
    )
    res = compute_gmm(GmmInput(
        reference_pb_pct=fx["gmm"]["reference_pb"],
        samples_at_reference=samples,
        design_pb_pct=(3.5, 4.0, 4.5, 5.0, 5.5),
        bitumen_sg=fx["sp_gr"]["expected"]["Gb_avg"],
    ))
    assert abs(res.gmm_avg_at_ref - fx["gmm"]["expected"]["Gmm_avg_at_ref"]) < TOL
    assert abs(res.gse - fx["gmm"]["expected"]["Gse"]) < TOL
    for (pb, gmm_got), exp in zip(res.gmm_per_design_pb, fx["gmm"]["expected"]["per_pb"]):
        assert abs(gmm_got - exp["gmm"]) < TOL, f"Gmm Pb={pb}: {gmm_got} vs {exp['gmm']}"


def test_stability_flow_per_group(fx):
    specs = []
    for grp in fx["stability_flow"]["groups"]:
        for i, s in enumerate(grp["specimens"], start=1):
            specs.append(StabilitySpecimen(
                bitumen_pct=grp["pb_pct"],
                sample_id=f"SAMPLE-{i}",
                height_readings_mm=(s["h1"], s["h2"], s["h3"]),
                diameter_mm=s["dia"],
                correction_factor=s["corr"],
                measured_stability_kn=s["stab"],
                flow_mm=s["flow"],
                include_in_stab_avg=s.get("include_stab", True),
                include_in_flow_avg=s.get("include_flow", True),
                corrected_stability_kn_override=s.get("n_cached"),
            ))
    res = compute_stability_flow(StabilityFlowInput(specimens=tuple(specs)))

    # Expected from Charts!H..J2:6
    for grp_res, exp_row in zip(res.groups, fx["summary_expected"]):
        assert abs(grp_res.avg_stability_kn - exp_row["stability"]) < TOL, (
            f"Stab Pb={grp_res.bitumen_pct}: {grp_res.avg_stability_kn} vs {exp_row['stability']}"
        )
        assert abs(grp_res.avg_flow_mm - exp_row["flow"]) < TOL, (
            f"Flow Pb={grp_res.bitumen_pct}: {grp_res.avg_flow_mm} vs {exp_row['flow']}"
        )
        assert abs(grp_res.marshall_quotient - exp_row["mq"]) < TOL, (
            f"MQ Pb={grp_res.bitumen_pct}: {grp_res.marshall_quotient} vs {exp_row['mq']}"
        )


def _build_full_input(fx) -> MixDesignInput:
    g = _g(fx["gradation"])
    sg_coarse = {
        "25mm": CoarseAggSGInput(
            a_sample_plus_container_water=tuple(fx["sp_gr"]["coarse_25"]["A"]),
            b_container_in_water=tuple(fx["sp_gr"]["coarse_25"]["B"]),
            c_ssd_in_air=tuple(fx["sp_gr"]["coarse_25"]["C"]),
            d_ovendry_in_air=tuple(fx["sp_gr"]["coarse_25"]["D"]),
        ),
        "20mm": CoarseAggSGInput(
            a_sample_plus_container_water=tuple(fx["sp_gr"]["coarse_20"]["A"]),
            b_container_in_water=tuple(fx["sp_gr"]["coarse_20"]["B"]),
            c_ssd_in_air=tuple(fx["sp_gr"]["coarse_20"]["C"]),
            d_ovendry_in_air=tuple(fx["sp_gr"]["coarse_20"]["D"]),
        ),
    }
    sg_fine = {
        "6mm": FineAggSGInput(
            w1_empty=tuple(fx["sp_gr"]["fine_6"]["W1"]),
            w2_dry_sample=tuple(fx["sp_gr"]["fine_6"]["W2"]),
            w3_dry_sample_water=tuple(fx["sp_gr"]["fine_6"]["W3"]),
            w4_water_only=tuple(fx["sp_gr"]["fine_6"]["W4"]),
        ),
        "SD": FineAggSGInput(
            w1_empty=tuple(fx["sp_gr"]["fine_sd"]["W1"]),
            w2_dry_sample=tuple(fx["sp_gr"]["fine_sd"]["W2"]),
            w3_dry_sample_water=tuple(fx["sp_gr"]["fine_sd"]["W3"]),
            w4_water_only=tuple(fx["sp_gr"]["fine_sd"]["W4"]),
        ),
    }
    sg_bit = BitumenSGInput(
        a_empty=tuple(fx["sp_gr"]["bitumen"]["A"]),
        b_water=tuple(fx["sp_gr"]["bitumen"]["B"]),
        c_sample=tuple(fx["sp_gr"]["bitumen"]["C"]),
        d_sample_water=tuple(fx["sp_gr"]["bitumen"]["D"]),
    )
    gmb_groups = tuple(
        GmbGroup(
            bitumen_pct=grp["pb_pct"],
            specimens=tuple(
                GmbSpecimen(a_dry_in_air=s["A"], c_in_water=s["D"], b_ssd_in_air=s["B"])
                for s in grp["specimens"]
            ),
        )
        for grp in fx["gmb"]["groups"]
    )
    gmm_in = GmmInput(
        reference_pb_pct=fx["gmm"]["reference_pb"],
        samples_at_reference=tuple(
            GmmSampleRaw(
                a_empty_flask=s["A"],
                b_flask_plus_dry_sample=s["B"],
                d_flask_filled_water=s["D"],
                e_flask_sample_water=s["E"],
            )
            for s in fx["gmm"]["samples_ref"]
        ),
        design_pb_pct=(3.5, 4.0, 4.5, 5.0, 5.5),
        bitumen_sg=0.0,                       # let engine compute it
    )
    specs = []
    for grp in fx["stability_flow"]["groups"]:
        for i, s in enumerate(grp["specimens"], start=1):
            specs.append(StabilitySpecimen(
                bitumen_pct=grp["pb_pct"],
                sample_id=f"SAMPLE-{i}",
                height_readings_mm=(s["h1"], s["h2"], s["h3"]),
                diameter_mm=s["dia"],
                correction_factor=s["corr"],
                measured_stability_kn=s["stab"],
                flow_mm=s["flow"],
                include_in_stab_avg=s.get("include_stab", True),
                include_in_flow_avg=s.get("include_flow", True),
                corrected_stability_kn_override=s.get("n_cached"),
            ))
    proj = ProjectInfo(mix_type="DBM-II")

    # Override gradation blend so Gsb uses only the 4 aggregates (Excel sample skips cement)
    g_blend = {k: v for k, v in g.blend_ratios.items() if k != "Cement"}
    g2 = GradationInput(
        sieve_sizes_mm=g.sieve_sizes_mm,
        pass_pct=g.pass_pct,
        blend_ratios=g_blend,
        spec_lower=g.spec_lower,
        spec_upper=g.spec_upper,
    )

    return MixDesignInput(
        project=proj,
        gradation=g2,
        sg_coarse=sg_coarse,
        sg_fine=sg_fine,
        sg_bitumen=sg_bit,
        gmb=GmbInput(groups=gmb_groups),
        gmm=gmm_in,
        stability_flow=StabilityFlowInput(specimens=tuple(specs)),
    )


def test_full_mix_design_matches_charts_sheet(fx):
    inp = _build_full_input(fx)
    res = compute_mix_design(inp)

    assert abs(res.bulk_sg_blend - fx["gsb_expected"]) < TOL

    for got, exp in zip(res.summary.rows, fx["summary_expected"]):
        assert abs(got.bitumen_pct - exp["pb"]) < TOL
        assert abs(got.aggregate_pct - exp["agg"]) < TOL
        assert abs(got.gmm - exp["gmm"]) < TOL
        assert abs(got.gmb - exp["gmb"]) < TOL
        assert abs(got.air_voids_pct - exp["air_voids"]) < TOL
        assert abs(got.vma_pct - exp["vma"]) < TOL
        assert abs(got.vfb_pct - exp["vfb"]) < TOL
        assert abs(got.stability_kn - exp["stability"]) < TOL
        assert abs(got.flow_mm - exp["flow"]) < TOL
        assert abs(got.marshall_quotient - exp["mq"]) < TOL


def test_obc_matches_excel(fx):
    inp = _build_full_input(fx)
    res = compute_mix_design(inp)
    # Excel stores 0.04254 (as decimal) -> 4.254%
    exp_obc_pct = fx["obc_expected"] * 100
    assert abs(res.obc.obc_pct - exp_obc_pct) < 1e-3, (
        f"OBC: software={res.obc.obc_pct} excel≈{exp_obc_pct}"
    )


# --------------------------------------------------------------------------
# Material Calculation parity (sheet "Material  Cal")
# --------------------------------------------------------------------------

def _material_input(fx) -> MaterialCalcInput:
    mc = fx["material_calc"]["inputs"]
    blend = {k: v for k, v in fx["gradation"]["blend_ratios"].items() if v is not None}
    return MaterialCalcInput(
        standard_bitumen_pct=mc["standard_bitumen_pct"],
        standard_aggregate_weight_g=mc["standard_aggregate_weight_g"],
        target_bitumen_pct=mc["target_bitumen_pct"],
        blend_ratios=blend,
    )


def test_material_calc_standard_block_matches_excel(fx):
    res = compute_material_calc(_material_input(fx))
    exp = fx["material_calc"]["standard_expected"]
    s = res.standard
    assert abs(s.aggregate_pct - exp["aggregate_pct"]) < TOL
    assert abs(s.bitumen_weight_g - exp["bitumen_weight_g"]) < TOL
    assert abs(s.total_mix_pct - exp["total_mix_pct"]) < TOL
    assert abs(s.total_mix_weight_g - exp["total_mix_weight_g"]) < TOL
    assert abs(s.aggregate_weight_g - exp["aggregate_weight_restated_g"]) < TOL
    # Excel D14 = D15 * D6 / 100 — same value algebraically
    assert abs(s.bitumen_weight_g - exp["bitumen_weight_restated_g"]) < TOL
    assert abs(s.total_mix_weight_g - exp["total_bituminous_mix_g"]) < TOL


def test_material_calc_target_block_matches_excel(fx):
    res = compute_material_calc(_material_input(fx))
    exp = fx["material_calc"]["target_expected"]
    t = res.target
    assert abs(t.aggregate_pct - exp["aggregate_pct"]) < TOL
    assert abs(t.aggregate_weight_g - exp["aggregate_weight_g"]) < TOL
    assert abs(t.bitumen_weight_g - exp["bitumen_weight_g"]) < TOL
    assert abs(t.total_mix_pct - exp["total_mix_pct"]) < TOL
    assert abs(t.total_mix_weight_g - exp["total_mix_weight_g"]) < TOL


def test_material_calc_dry_material_standard_matches_excel(fx):
    res = compute_material_calc(_material_input(fx))
    expected = fx["material_calc"]["dry_material_standard_expected"]
    expected_total = fx["material_calc"]["dry_material_standard_total_expected"]
    for got, exp in zip(res.dry_material_standard, expected):
        assert got.name == exp["name"]
        assert abs(got.fraction - exp["pct"]) < TOL
        assert abs(got.weight_g - exp["weight_g"]) < TOL, (
            f"{got.name}: {got.weight_g} vs {exp['weight_g']}"
        )
    assert abs(res.total_dry_standard_g - expected_total) < TOL


def test_material_calc_dry_material_target_matches_excel(fx):
    res = compute_material_calc(_material_input(fx))
    expected = fx["material_calc"]["dry_material_target_expected"]
    expected_total = fx["material_calc"]["dry_material_target_total_expected"]
    for got, exp in zip(res.dry_material_target, expected):
        assert got.name == exp["name"]
        assert abs(got.fraction - exp["pct"]) < TOL
        assert abs(got.weight_g - exp["weight_g"]) < TOL, (
            f"{got.name}: {got.weight_g} vs {exp['weight_g']}"
        )
    assert abs(res.total_dry_target_g - expected_total) < TOL
