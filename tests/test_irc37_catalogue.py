from __future__ import annotations
import pytest
from app.core.catalogue.loader import load_irc37_catalogue, load_catalogue_metadata
from app.core.catalogue.engine import lookup_catalogue_design

def test_load_catalogue_and_metadata() -> None:
    entries = load_irc37_catalogue()
    assert len(entries) == 30
    
    meta = load_catalogue_metadata()
    assert "safety_note" in meta
    assert "Catalogue database incomplete" in meta["safety_note"]

def test_standard_lookups() -> None:
    # CBR 3% (class [3.0, 5.0)), Traffic 10 MSA (class [10.0, 20.0))
    res = lookup_catalogue_design(msa=10.0, cbr=3.0)
    assert res.is_out_of_range is False
    assert res.is_boundary is True  # 10.0 and 3.0 are boundary values
    
    assert len(res.composition) == 4
    assert res.composition[0].thickness_mm == 40
    assert res.composition[1].thickness_mm == 100
    assert res.composition[2].thickness_mm == 250
    assert res.composition[3].thickness_mm == 300
    assert "Skeleton" in res.source_reference
    
    # CBR 5% (class [5.0, 8.0)), Traffic 50 MSA (class [50.0, 100000.0))
    res2 = lookup_catalogue_design(msa=55.0, cbr=5.5)
    assert res2.is_out_of_range is False
    assert res2.is_boundary is False
    assert res2.composition[1].thickness_mm == 190
    assert res2.composition[3].thickness_mm == 230

def test_boundary_conditions() -> None:
    res1 = lookup_catalogue_design(msa=5.0, cbr=5.0)
    assert res1.is_boundary is True
    # cbr 5.0 is in [5.0, 8.0); msa 5.0 is in [5.0, 10.0)
    assert res1.composition[1].thickness_mm == 70
    assert res1.composition[3].thickness_mm == 230

def test_out_of_range_warnings() -> None:
    # CBR below minimum (1.5%)
    res = lookup_catalogue_design(msa=10.0, cbr=1.5)
    assert res.is_out_of_range is True
    # Should cap at CBR 3.0, returning GSB 300 (class [3.0, 5.0))
    assert res.composition[3].thickness_mm == 300
    warnings_str = " ".join(res.warnings)
    assert "below the minimum catalogue limit" in warnings_str
    assert "Catalogue database incomplete — engineer verification required." in warnings_str
    
    # Traffic above maximum (250 MSA)
    res_heavy = lookup_catalogue_design(msa=250.0, cbr=5.0)
    assert res_heavy.is_out_of_range is True
    # Should cap at 150 MSA (which matches the >=50 band, so DBM 190)
    assert res_heavy.composition[1].thickness_mm == 190
    warnings_heavy = " ".join(res_heavy.warnings)
    assert "exceeds the maximum catalogue limit" in warnings_heavy
    assert "Catalogue database incomplete — engineer verification required." in warnings_heavy
    
    # Traffic below minimum (0.5 MSA)
    res_light = lookup_catalogue_design(msa=0.5, cbr=5.0)
    assert res_light.is_out_of_range is True
    # Should cap at 2.0 MSA (class [0.0, 5.0))
    assert res_light.composition[1].thickness_mm == 50
    warnings_light = " ".join(res_light.warnings)
    assert "is below the minimum catalogue limit" in warnings_light
