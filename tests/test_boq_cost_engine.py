import json
import pytest
from app.core import LayerInput, MaterialQuantityInput, compute_material_quantity
from app.engineering.boq_engine import calculate_layer_boq, validate_boq_data, DEFAULT_RATES


def test_layer_quantity_volumes_and_splits():
    # Test Bituminous mix (BC)
    inp_bc = LayerInput(
        layer_type="BC",
        length_m=1000.0,
        width_m=7.0,
        thickness_mm=40.0,
        density_t_m3=2.40,
        binder_pct=5.5,
        waste_pct=2.0
    )
    res_bc = compute_material_quantity(MaterialQuantityInput(layers=(inp_bc,)))
    assert len(res_bc.layers) == 1
    layer_res = res_bc.layers[0]
    
    # Compacted Vol = 1000 * 7 * 0.04 = 280 m3
    assert abs(layer_res.compacted_volume_m3 - 280.0) < 1e-3
    # Loose Vol = 280 * 1.15 = 322 m3
    assert abs(layer_res.loose_volume_m3 - 322.0) < 1e-3
    # Tonnage = 280 * 2.4 * 1.02 = 685.44 t
    assert abs(layer_res.layer_tonnage_t - 685.44) < 1e-3
    # Bitumen splits = 685.44 * 5.5% = 37.6992 t
    assert abs(layer_res.bitumen_tonnage_t - 37.6992) < 1e-3
    # Filler splits = 685.44 * 2.0% = 13.7088 t
    assert abs(layer_res.filler_tonnage_t - 13.7088) < 1e-3
    # Aggregate splits = 685.44 - 37.6992 - 13.7088 = 634.032 t
    assert abs(layer_res.aggregate_tonnage_t - 634.032) < 1e-3


def test_layer_quantity_stabilized_splits():
    # Test Stabilized mix (CTB)
    inp_ctb = LayerInput(
        layer_type="CTB",
        length_m=1000.0,
        width_m=7.0,
        thickness_mm=100.0,
        density_t_m3=2.20,
        binder_pct=4.5,  # cement content
        waste_pct=2.0
    )
    res_ctb = compute_material_quantity(MaterialQuantityInput(layers=(inp_ctb,)))
    layer_res = res_ctb.layers[0]
    
    # Compacted Vol = 1000 * 7 * 0.1 = 700 m3
    assert abs(layer_res.compacted_volume_m3 - 700.0) < 1e-3
    # Loose Vol = 700 * 1.20 = 840 m3
    assert abs(layer_res.loose_volume_m3 - 840.0) < 1e-3
    # Tonnage = 700 * 2.2 * 1.02 = 1570.8 t
    assert abs(layer_res.layer_tonnage_t - 1570.8) < 1e-3
    # Cement splits = 1570.8 * 4.5% = 70.686 t
    assert abs(layer_res.cement_tonnage_t - 70.686) < 1e-3
    # Aggregate splits = 1570.8 - 70.686 = 1500.114 t
    assert abs(layer_res.aggregate_tonnage_t - 1500.114) < 1e-3


def test_boq_cost_calculation():
    # Test calculate_layer_boq
    rates = DEFAULT_RATES.copy()
    boq = calculate_layer_boq(
        name="BC",
        thickness_mm=40.0,
        length_m=1000.0,
        width_m=7.0,
        rates=rates
    )
    
    assert boq["layer_name"] == "BC"
    assert boq["thickness_mm"] == 40.0
    assert boq["volume_m3"] == 280.0
    assert boq["loose_volume_m3"] == 322.0
    
    # Rate for BC = 8500
    # Amount = weight_t * 8500
    expected_weight = 280.0 * 2.4 * 1.02  # 685.44
    expected_cost = expected_weight * 8500.0  # 5,826,240.00
    assert abs(boq["cost"] - expected_cost) < 1e-3
    
    # GST = 18% of cost
    expected_gst = expected_cost * 0.18
    assert abs(boq["gst"] - expected_gst) < 1e-3
    
    # Grand Total = cost + gst
    assert abs(boq["grand_total"] - (expected_cost + expected_gst)) < 1e-3
    
    # Traceability check
    assert "BC Tonnage" in boq["traceability"]
    assert "Waste Factor" in boq["traceability"]
