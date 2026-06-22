from __future__ import annotations
from typing import List, Tuple
from .loader import load_irc37_catalogue, load_catalogue_metadata
from .models import CatalogueLookupResult, CatalogueEntry

def lookup_catalogue_design(msa: float, cbr: float) -> CatalogueLookupResult:
    """Lookup pavement composition from the verified database with warning logic."""
    meta = load_catalogue_metadata()
    entries = load_irc37_catalogue()
    
    warnings: list[str] = []
    is_out_of_range = False
    is_boundary = False
    
    # Enforce safety note and verified status warnings
    warnings.append(meta["safety_note"])
    if meta["warning_msg"]:
        warnings.append(meta["warning_msg"])
        
    target_cbr = cbr
    if cbr < 3.0:
        is_out_of_range = True
        warnings.append(
            f"Subgrade CBR ({cbr:.1f}%) is below the minimum catalogue limit of 3.0%. "
            "Suggesting Plate 1 (CBR 3%) composition as baseline; borrow soil subgrade or stabilization is required."
        )
        target_cbr = 3.0
    elif cbr > 15.0:
        is_out_of_range = True
        warnings.append(
            f"Subgrade CBR ({cbr:.1f}%) exceeds the maximum catalogue limit of 15.0%. "
            "Suggesting CBR >= 12% composition as conservative baseline."
        )
        target_cbr = 15.0
        
    target_msa = msa
    if msa < 2.0:
        is_out_of_range = True
        warnings.append(
            f"Design traffic ({msa:.2f} MSA) is below the minimum catalogue limit of 2.0 MSA. "
            "Suggesting 2.0 MSA composition as baseline."
        )
        target_msa = 2.0
    elif msa > 150.0:
        is_out_of_range = True
        warnings.append(
            f"Design traffic ({msa:.2f} MSA) exceeds the maximum catalogue limit of 150.0 MSA. "
            "Suggesting 150.0 MSA composition as baseline; mechanistic design must be verified in IITPAVE."
        )
        target_msa = 150.0

    # Determine boundary state
    if cbr in (3.0, 5.0, 8.0, 12.0, 15.0) or msa in (2.0, 5.0, 10.0, 20.0, 30.0, 50.0, 100.0, 150.0):
        is_boundary = True

    matched_entry = None
    for entry in entries:
        cbr_match = entry.cbr_min <= target_cbr < entry.cbr_max
        if target_cbr == 15.0 and entry.cbr_max == 100.0:
            cbr_match = True
            
        msa_match = entry.msa_min <= target_msa < entry.msa_max
        if target_msa == 150.0 and entry.msa_max >= 150.0:
            msa_match = True
            
        if cbr_match and msa_match:
            matched_entry = entry
            break
            
    if matched_entry is None:
        matched_entry = entries[0]
        warnings.append("No exact catalogue entry found. Using lowest database entry.")
        
    ref_plate = matched_entry.reference_plate
    
    return CatalogueLookupResult(
        composition=matched_entry.composition,
        source_reference=f"IRC:37 catalogue reference: {ref_plate}",
        warnings=tuple(warnings),
        is_out_of_range=is_out_of_range,
        is_boundary=is_boundary
    )
