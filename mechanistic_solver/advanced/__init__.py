"""Advanced pavement engineering sub-package entries."""
from __future__ import annotations

from mechanistic_solver.advanced.viscoelastic import PronyTerm, ViscoelasticMaterial
from mechanistic_solver.advanced.temperature import BinderGrade, TemperaturePavementModel
from mechanistic_solver.advanced.dynamic import DynamicWheelLoad
from mechanistic_solver.advanced.moving import TyrePosition, AxleConfiguration, MovingLoadSimulator
from mechanistic_solver.advanced.airport import AircraftMetadata, AirportGearFactory
from mechanistic_solver.advanced.composite import OverlayDesign, CompositePavementModel
from mechanistic_solver.advanced.industrial import IndustrialLoadTemplate, IndustrialPavementModel
from mechanistic_solver.advanced.reliability import StochasticVariable, ReliabilityEngine
from mechanistic_solver.advanced.reports import AdvancedReportGenerator
