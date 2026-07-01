# RoadX Solver Release Notes - Version 2.2.0

## 1. What's New in Version 2.2.0

- **IRC:37 Design Engine:** Standard fatigue and rutting damage models based on allowable repetition boundaries.
- **Intelligent Caching System:** Added cache layers for Bessel functions and coefficients, yielding a 6.3x execution speedup.
- **Licensing Tier Abstraction:** Modular licensing check supporting Community, Professional, and Enterprise configurations.
- **Multi-profile Configuration:** Added `development`, `production`, `benchmark`, and `debug` profiles with custom tolerance limits.

## 2. Upgrade Guide
Simply deploy the new `mechanistic_solver/` folder into your python workspace. Backward compatibility with older models is fully preserved.
