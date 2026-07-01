import json
import pytest
from PySide6.QtWidgets import QApplication
from app.db.repository import Database
import app.ui.widgets.roadx_solver_panel as panel_mod
from app.ui.widgets.roadx_solver_panel import RoadXSolverPanel
from app.db.schema import StructuralDesign

def _app() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app

@pytest.fixture
def temp_db(tmp_path):
    db_file = tmp_path / "test_roadx_solver_gui.db"
    database = Database(db_file)
    yield database
    try:
        database.engine.dispose()
    except Exception:
        pass

def test_roadx_solver_gui_bituminous_depth(temp_db):
    _app()
    
    # 1. Create a project in the database
    pid = temp_db.create_project(
        client_id=1,
        work_name="Test RoadX Solver Project",
        subgrade_cbr=6.0,
        subgrade_mr=50.0,
        road_category="NH / SH"
    )
    temp_db.initialize_workflow_statuses(pid.id)
    
    # 2. Add structural design with BC 40mm and DBM 190mm
    composition = [
        {"name": "BC", "thickness_mm": 40.0, "modulus_mpa": 3000.0, "poisson": 0.35},
        {"name": "DBM", "thickness_mm": 190.0, "modulus_mpa": 3000.0, "poisson": 0.35},
        {"name": "WMM", "thickness_mm": 250.0, "modulus_mpa": 350.0, "poisson": 0.35},
        {"name": "GSB", "thickness_mm": 230.0, "modulus_mpa": 150.0, "poisson": 0.35}
    ]
    
    with temp_db.session() as s:
        sd = StructuralDesign(
            project_id=pid.id,
            design_msa=100.0,
            subgrade_mr_mpa=50.0,
            composition_json=json.dumps(composition)
        )
        s.add(sd)
        s.flush()
        
    # 3. Instantiate RoadXSolverPanel and trigger solver run logic internally
    panel = RoadXSolverPanel(temp_db)
    panel.set_project(pid.id, "Test RoadX Solver Project")
    
    import unittest.mock as mock
    from mechanistic_solver.solver.engine import MechanisticSolver
    
    mock_solver = mock.MagicMock(spec=MechanisticSolver)
    mock_response = mock.MagicMock()
    mock_response.status = "success"
    mock_response.strain_results = [{"epsilon_r": 1e-4, "epsilon_t": 1.2e-4}, {"epsilon_z": 2.5e-4}]
    mock_response.displacement_results = [{}, {}, {"vertical_deflection": 1.5e-3}]
    mock_solver.solve.return_value = mock_response
    
    with mock.patch("app.ui.widgets.roadx_solver_panel.MechanisticSolver", return_value=mock_solver):
        panel._on_run_solver()
        
        assert mock_solver.solve.called
        # Verify the first call (direct GUI invocation) has the correct ObservationPoint list
        args, kwargs = mock_solver.solve.call_args_list[0]
        observation_points = args[2]
        
        # Verification details:
        # epsilon_t observation point depth (index 0) should be BC (40) + DBM (190) = 230.0
        assert observation_points[0].z == 230.0
        # epsilon_v observation point depth (index 1)
        assert observation_points[1].z == 710.0  # BC (40) + DBM (190) + WMM (250) + GSB (230)
        # Deflection observation point depth (index 2)
        assert observation_points[2].z == 0.0
        
        # Verify the depth label shows the correct extraction depths
        expected_txt = "Extraction Depths: ε_t depth = 230.0 mm, ε_v depth = 710.0 mm, deflection depth = 0 mm"
        assert panel.lbl_depths_info.text() == expected_txt
