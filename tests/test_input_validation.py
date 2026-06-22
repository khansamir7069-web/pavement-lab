import pytest
from app.core.structural_design import StructuralInput, PavementLayer as StructuralPavementLayer
from app.core.traffic import TrafficInput
from app.core.iitpave.pavement_structure import PavementLayer as IITPavePavementLayer

def test_structural_input_validation() -> None:
    # Safe construction
    StructuralInput()
    
    # Negative CVPD
    with pytest.raises(ValueError, match="CVPD must be >= 0"):
        StructuralInput(initial_cvpd=-1.0)
        
    # Negative CBR
    with pytest.raises(ValueError, match="CBR must be > 0"):
        StructuralInput(subgrade_cbr_pct=-5.0)
        
    # Zero CBR
    with pytest.raises(ValueError, match="CBR must be > 0"):
        StructuralInput(subgrade_cbr_pct=0.0)
        
    # Zero design life
    with pytest.raises(ValueError, match="Design life must be >= 1"):
        StructuralInput(design_life_years=0)
        
    # Negative design life
    with pytest.raises(ValueError, match="Design life must be >= 1"):
        StructuralInput(design_life_years=-10)
        
    # Negative VDF
    with pytest.raises(ValueError, match="VDF must be >= 0"):
        StructuralInput(vdf=-0.5)
        
    # Invalid Lane Distribution Factor
    with pytest.raises(ValueError, match="Lane distribution factor must be > 0 and <= 1"):
        StructuralInput(ldf=0.0)
    with pytest.raises(ValueError, match="Lane distribution factor must be > 0 and <= 1"):
        StructuralInput(ldf=1.05)


def test_traffic_input_validation() -> None:
    # Safe construction
    TrafficInput()
    
    # Negative CVPD
    with pytest.raises(ValueError, match="CVPD must be >= 0"):
        TrafficInput(initial_cvpd=-10.0)
        
    # Negative growth rate
    with pytest.raises(ValueError, match="Growth rate must be >= 0"):
        TrafficInput(growth_rate_pct=-1.5)
        
    # Zero design life
    with pytest.raises(ValueError, match="Design life must be >= 1"):
        TrafficInput(design_life_years=0)
        
    # Negative VDF
    with pytest.raises(ValueError, match="VDF must be >= 0"):
        TrafficInput(vdf=-1.0)
        
    # Invalid LDF
    with pytest.raises(ValueError, match="Lane distribution factor must be > 0 and <= 1"):
        TrafficInput(ldf=0.0)
    with pytest.raises(ValueError, match="Lane distribution factor must be > 0 and <= 1"):
        TrafficInput(ldf=1.2)


def test_pavement_layer_validation() -> None:
    # Structural layer thickness
    with pytest.raises(ValueError, match="Layer thickness must be > 0"):
        StructuralPavementLayer("BC", 0.0)
    with pytest.raises(ValueError, match="Layer thickness must be > 0"):
        StructuralPavementLayer("BC", -10.0)
        
    # Structural layer modulus
    with pytest.raises(ValueError, match="Modulus must be > 0"):
        StructuralPavementLayer("BC", 40.0, modulus_mpa=0)
    with pytest.raises(ValueError, match="Modulus must be > 0"):
        StructuralPavementLayer("BC", 40.0, modulus_mpa=-100)

    # IITPAVE layer thickness
    with pytest.raises(ValueError, match="Layer thickness must be > 0"):
        IITPavePavementLayer("BC", "BC", 3000.0, 0.35, 0.0)
        
    # IITPAVE layer modulus
    with pytest.raises(ValueError, match="Modulus must be > 0"):
        IITPavePavementLayer("BC", "BC", 0.0, 0.35, 40.0)
    with pytest.raises(ValueError, match="Modulus must be > 0"):
        IITPavePavementLayer("BC", "BC", -50.0, 0.35, 40.0)
        
    # IITPAVE layer Poisson ratio
    with pytest.raises(ValueError, match="Poisson ratio must be > 0 and < 0.5"):
        IITPavePavementLayer("BC", "BC", 3000.0, 0.0, 40.0)
    with pytest.raises(ValueError, match="Poisson ratio must be > 0 and < 0.5"):
        IITPavePavementLayer("BC", "BC", 3000.0, 0.5, 40.0)
    with pytest.raises(ValueError, match="Poisson ratio must be > 0 and < 0.5"):
        IITPavePavementLayer("BC", "BC", 3000.0, -0.1, 40.0)
