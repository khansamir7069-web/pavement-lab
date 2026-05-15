"""Top-level mix-design input/result models that orchestrate the engine."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping

from .compliance import ComplianceResult, check_compliance
from .gmb import GmbInput, GmbResult, compute_gmb
from .gmm import GmmInput, GmmResult, compute_gmm
from .gradation import GradationInput, GradationResult, compute_gradation
from .marshall import MarshallSummary, build_marshall_summary
from .obc import OBCResult, properties_at_obc
from .specific_gravity import (
    BitumenSGInput,
    CoarseAggSGInput,
    FineAggSGInput,
    SpecificGravityResult,
    compute_bitumen_sg,
    compute_bulk_sg_blend,
    compute_coarse_sg,
    compute_fine_sg,
)
from .stability_flow import (
    StabilityFlowInput,
    StabilityFlowResult,
    compute_stability_flow,
)


@dataclass(frozen=True, slots=True)
class ProjectInfo:
    mix_type: str           # one of MIX_SPECS keys (DBM-II, BC-I, ...)
    work_name: str = ""
    work_order_no: str = ""
    work_order_date: str = ""
    client: str = ""
    agency: str = ""
    submitted_by: str = ""
    materials: Mapping[str, str] = field(default_factory=dict)  # name -> source


@dataclass(frozen=True, slots=True)
class MixDesignInput:
    project: ProjectInfo
    gradation: GradationInput
    sg_coarse: Mapping[str, CoarseAggSGInput]   # e.g. "25mm" -> input
    sg_fine: Mapping[str, FineAggSGInput]       # e.g. "6mm" -> input
    sg_bitumen: BitumenSGInput
    gmb: GmbInput
    gmm: GmmInput
    stability_flow: StabilityFlowInput


@dataclass(frozen=True, slots=True)
class MixDesignResult:
    gradation: GradationResult
    sg_coarse: Mapping[str, SpecificGravityResult]
    sg_fine: Mapping[str, SpecificGravityResult]
    bitumen_sg: float
    bulk_sg_blend: float                     # Gsb
    gmm: GmmResult
    gmb: GmbResult
    stability_flow: StabilityFlowResult
    summary: MarshallSummary
    obc: OBCResult
    compliance: ComplianceResult


def compute_mix_design(inp: MixDesignInput) -> MixDesignResult:
    grad = compute_gradation(inp.gradation)

    coarse_sg = {name: compute_coarse_sg(v) for name, v in inp.sg_coarse.items()}
    fine_sg = {name: compute_fine_sg(v) for name, v in inp.sg_fine.items()}
    bit_sg = compute_bitumen_sg(inp.sg_bitumen)

    # bulk SG blend uses oven-dry bulk SG average per aggregate, weighted by blend ratio.
    bulk_by_name: dict[str, float] = {}
    for name, res in coarse_sg.items():
        bulk_by_name[name] = res.avg_bulk_ovendry
    for name, res in fine_sg.items():
        bulk_by_name[name] = res.avg_bulk_ovendry

    gsb = compute_bulk_sg_blend(dict(inp.gradation.blend_ratios), bulk_by_name)

    gmm_in = inp.gmm
    if gmm_in.bitumen_sg == 0:
        # Patch from computed bitumen SG when input left blank.
        gmm_in = GmmInput(
            reference_pb_pct=gmm_in.reference_pb_pct,
            samples_at_reference=gmm_in.samples_at_reference,
            design_pb_pct=gmm_in.design_pb_pct,
            bitumen_sg=bit_sg,
        )
    gmm_res = compute_gmm(gmm_in)

    gmb_res = compute_gmb(inp.gmb)
    sf_res = compute_stability_flow(inp.stability_flow)

    gmm_map = {pb: g for pb, g in gmm_res.gmm_per_design_pb}
    gmb_map = {grp.bitumen_pct: grp.mean for grp in gmb_res.groups}
    sf_map = {
        grp.bitumen_pct: (grp.avg_stability_kn, grp.avg_flow_mm, grp.marshall_quotient)
        for grp in sf_res.groups
    }

    design_pbs = gmm_in.design_pb_pct
    summary = build_marshall_summary(design_pbs, gmm_map, gmb_map, sf_map, gsb)
    obc = properties_at_obc(summary)
    comp = check_compliance(
        inp.project.mix_type,
        stability_kn=obc.stability_at_obc_kn,
        flow_mm=obc.flow_at_obc_mm,
        air_voids_pct=obc.air_voids_at_obc_pct,
        vma_pct=obc.vma_at_obc_pct,
        vfb_pct=obc.vfb_at_obc_pct,
        marshall_quotient=obc.stability_at_obc_kn / obc.flow_at_obc_mm if obc.flow_at_obc_mm else 0.0,
    )

    return MixDesignResult(
        gradation=grad,
        sg_coarse=coarse_sg,
        sg_fine=fine_sg,
        bitumen_sg=bit_sg,
        bulk_sg_blend=gsb,
        gmm=gmm_res,
        gmb=gmb_res,
        stability_flow=sf_res,
        summary=summary,
        obc=obc,
        compliance=comp,
    )
