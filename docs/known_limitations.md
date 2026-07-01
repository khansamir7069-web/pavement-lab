# RoadX Solver Known Limitations

This document lists the scope bounds and known limitations of the current release.

## 1. Multilayer Parity
The multilayer elastic response solver output matches boundary requirements and decay trends but is marked as `EXPERIMENTAL` pending official benchmark parity audit verification.

## 2. Interface Conditions
All layer interfaces are modeled as fully bonded. Sliding or friction interface models are not supported in the current release.

## 3. Calibration Scaling
Default fatigue and rutting damage constants follow default values of IRC:37. Site-specific calibration models are not automated and must be passed as overrides.
