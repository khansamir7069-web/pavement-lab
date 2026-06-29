# IITPAVE Installation & Configuration Guide

This guide provides instructions for setting up the separately licensed **IITPAVE** calculation engine for mechanistic design verification within **RoadX Professional Suite**.

## Overview
IITPAVE is the official pavement analysis program recommended by the Indian Roads Congress (IRC:37-2018) for calculating critical strains (tensile strain at the bottom of the bituminous layer, and vertical compressive strain at the top of the subgrade).

RoadX provides dynamic integration with IITPAVE:
- **IRC Catalogue Design (Decision Support Mode)**: Used when IITPAVE is not configured. Designs are verified using the pre-calculated MoRTH/IRC catalog thicknesses.
- **Mechanistically Verified Design**: Enabled once the path to a valid `IITPAVE.exe` is configured. The software runs background strain analysis and verifies fatigue/rutting lives dynamically.

## Configuration Steps
1. Navigate to the **Settings** or **IITPAVE Integration** status panel in RoadX.
2. Under **IITPAVE Configuration**, click **Browse** and select the local path to your licensed `IITPAVE.exe` executable.
3. The system will run automatic diagnostics:
   - **Active Path Check**: Verifies the file exists.
   - **SHA256 Code Checksum**: Computes and shows the file hash for security auditing.
   - **Version Discovery**: Detects the calculation engine version.
   - **Test Execution**: Performs a mock strain calculation to confirm engine readiness.
4. Once validation status shows **Active / Verified**, the mechanistic analysis mode is fully unlocked.

## Troubleshooting
- **File Not Found / Access Denied**: Ensure RoadX has read/execute permissions for the selected executable path.
- **Checksum Mismatch**: If you are using a custom/modified version of IITPAVE, the system will flag the code hash for security verification but will still permit execution if manually overridden.
