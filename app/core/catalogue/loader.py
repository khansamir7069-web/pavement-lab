from __future__ import annotations
import json
import sys
from pathlib import Path
from app.config import APP_DIR
from app.core.structural_design import PavementLayer
from .models import CatalogueEntry

def get_catalogue_path() -> Path:
    # If running inside PyInstaller bundle, check sys._MEIPASS / "database" / "irc37_catalogue.json"
    # Otherwise check project root's database/irc37_catalogue.json
    mei = getattr(sys, "_MEIPASS", None)
    if mei:
        return Path(mei) / "database" / "irc37_catalogue.json"
    return APP_DIR.parent / "database" / "irc37_catalogue.json"

def load_irc37_catalogue() -> list[CatalogueEntry]:
    path = get_catalogue_path()
    if not path.is_file():
        raise FileNotFoundError(f"IRC:37 catalogue file not found at {path}")
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    entries = []
    for item in data.get("entries", []):
        comp = tuple(
            PavementLayer(
                name=l["name"],
                thickness_mm=l["thickness_mm"],
                material=l.get("material", ""),
                modulus_mpa=l.get("modulus_mpa")
            )
            for l in item.get("composition", [])
        )
        entries.append(
            CatalogueEntry(
                id=item["id"],
                cbr_min=float(item["cbr_min"]),
                cbr_max=float(item["cbr_max"]),
                msa_min=float(item["msa_min"]),
                msa_max=float(item["msa_max"]),
                reference_plate=item.get("reference_plate", ""),
                bituminous_thickness_mm=float(item.get("bituminous_thickness_mm", 0.0)),
                granular_thickness_mm=float(item.get("granular_thickness_mm", 0.0)),
                composition=comp
            )
        )
    return entries

def load_catalogue_metadata() -> dict[str, str]:
    path = get_catalogue_path()
    if not path.is_file():
        return {
            "safety_note": "Catalogue database incomplete — engineer verification required.",
            "warning_msg": "Catalogue lookup warnings present."
        }
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return {
        "safety_note": data.get("safety_note", "Catalogue database incomplete — engineer verification required."),
        "warning_msg": data.get("warning_msg", "")
    }
