"""Phase-15 Priority-4 smoke — mechanistic-validation persistence.

Validates the new ``mechanistic_validations`` table + repository
accessors:

  1. save -> latest round-trip preserves verdicts, lives, refused flag
     and is_placeholder flag (denormalized columns).
  2. summary_json round-trips so the report layer can re-hydrate the
     full Phase-14 summary shape.
  3. Backward compatibility: a project with NO mechanistic-validation
     row still works — ``latest_mechanistic_validation`` returns None.
  4. Cascade-on-delete-project removes the mechanistic row alongside
     the existing condition / traffic / structural rows.
  5. Refused-summary persistence: verdict columns store NULL (not
     "REFUSED"), refused_reason is preserved verbatim.

Pure-Python; uses a tempdir sqlite file so the existing user DB is
untouched.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

_tmp = Path(tempfile.mkdtemp())

import app.config as _cfg  # noqa: E402
_cfg.DB_PATH = _tmp / "phase15_p4.db"

from app.core import (  # noqa: E402
    ConditionSurveyInput,
    IITPavePavementLayer,
    IITPavePointResult,
    LABEL_FATIGUE,
    LABEL_RUTTING,
    MechanisticResult,
    MechanisticValidationInput,
    PavementStructure,
    compute_condition_survey,
    compute_mechanistic_validation,
)
from app.core.code_refs import CodeRef
from app.db.repository import Database
from app.db.schema import MechanisticValidation


def _structure() -> PavementStructure:
    return PavementStructure(layers=(
        IITPavePavementLayer(name="BC",  material="BC",  modulus_mpa=3000.0,
                             thickness_mm=40.0),
        IITPavePavementLayer(name="DBM", material="DBM", modulus_mpa=2500.0,
                             thickness_mm=80.0),
        IITPavePavementLayer(name="GSB", material="GSB", modulus_mpa=300.0,
                             thickness_mm=200.0),
        IITPavePavementLayer(name="Subgrade", material="Subgrade",
                             modulus_mpa=50.0, thickness_mm=None),
    ))


def _mech_result(*, is_placeholder: bool,
                 source: str = "external_exe") -> MechanisticResult:
    bt = IITPavePointResult(
        z_mm=120.0, r_mm=0.0,
        sigma_z_mpa=0.5, sigma_r_mpa=0.1, sigma_t_mpa=0.1,
        epsilon_z_microstrain=-150.0,
        epsilon_r_microstrain=150.0,
        epsilon_t_microstrain=150.0,
    )
    sg = IITPavePointResult(
        z_mm=320.0, r_mm=0.0,
        sigma_z_mpa=0.05, sigma_r_mpa=0.01, sigma_t_mpa=0.01,
        epsilon_z_microstrain=300.0,
        epsilon_r_microstrain=-90.0,
        epsilon_t_microstrain=-90.0,
    )
    return MechanisticResult(
        point_results=(bt, sg),
        references=(CodeRef("IRC:37-2018", "cl. 6.2", "Elastic"),),
        is_placeholder=is_placeholder,
        source=source,
    )


def main() -> int:
    db = Database(_cfg.DB_PATH)

    # ---------------------------------------------------------------
    # 1) save -> latest round-trip (verdict path).
    # ---------------------------------------------------------------
    print("=== 1) Verdict round-trip ===")
    proj = db.create_project(work_name="P15 P4 verdict")
    structure = _structure()
    inp = MechanisticValidationInput(
        mech_result=_mech_result(is_placeholder=False),
        structure=structure,
        design_msa=30.0,
        point_labels=(LABEL_FATIGUE, LABEL_RUTTING),
    )
    summary = compute_mechanistic_validation(inp)
    assert summary.refused is False
    assert summary.fatigue.verdict in ("PASS", "FAIL")
    row = db.save_mechanistic_validation(project_id=proj.id, summary=summary)
    assert row.id is not None
    got = db.latest_mechanistic_validation(proj.id)
    assert got is not None
    assert got.refused is False
    assert got.is_placeholder is True   # calibration still placeholder
    assert got.fatigue_verdict == summary.fatigue.verdict
    assert got.rutting_verdict == summary.rutting.verdict
    assert abs(got.fatigue_life_msa - summary.fatigue.cumulative_life_msa) < 1e-6
    assert abs(got.rutting_life_msa - summary.rutting.cumulative_life_msa) < 1e-6
    assert got.design_msa == 30.0
    # JSON round-trip carries the full summary.
    summary_json = json.loads(got.summary_json or "{}")
    assert summary_json["fatigue"]["verdict"] == summary.fatigue.verdict
    assert summary_json["rutting"]["verdict"] == summary.rutting.verdict
    print(f"  [PASS] id={got.id} fatigue={got.fatigue_verdict} "
          f"rutting={got.rutting_verdict} life_f={got.fatigue_life_msa:.2f}")

    # ---------------------------------------------------------------
    # 2) Refused-summary persistence — verdicts NULL, reason verbatim.
    # ---------------------------------------------------------------
    print("\n=== 2) Refused round-trip ===")
    proj2 = db.create_project(work_name="P15 P4 refused")
    refused = compute_mechanistic_validation(MechanisticValidationInput(
        mech_result=_mech_result(is_placeholder=True, source="stub"),
        structure=structure,
        design_msa=30.0,
        point_labels=(LABEL_FATIGUE, LABEL_RUTTING),
    ))
    assert refused.refused is True
    db.save_mechanistic_validation(project_id=proj2.id, summary=refused)
    got2 = db.latest_mechanistic_validation(proj2.id)
    assert got2 is not None
    assert got2.refused is True
    assert got2.is_placeholder is True
    assert got2.fatigue_verdict is None
    assert got2.rutting_verdict is None
    assert got2.fatigue_life_msa is None
    assert got2.rutting_life_msa is None
    assert "placeholder" in (got2.refused_reason or "").lower()
    print(f"  [PASS] refused=True; verdicts NULL; reason cites placeholder")

    # ---------------------------------------------------------------
    # 3) Backward compatibility: project without any mech run.
    # ---------------------------------------------------------------
    print("\n=== 3) Project without mechanistic row ===")
    proj3 = db.create_project(work_name="P15 P4 untouched")
    # Save an unrelated condition survey to prove the project is live.
    db.save_condition_survey(
        project_id=proj3.id,
        result=compute_condition_survey(ConditionSurveyInput()),
    )
    assert db.latest_mechanistic_validation(proj3.id) is None
    assert db.latest_condition_survey(proj3.id) is not None
    print("  [PASS] None returned; sibling tables still queryable")

    # ---------------------------------------------------------------
    # 4) Cascade on delete_project.
    # ---------------------------------------------------------------
    print("\n=== 4) Cascade on delete_project ===")
    assert db.delete_project(proj.id) is True
    assert db.latest_mechanistic_validation(proj.id) is None
    # Manually verify the row is gone from the ORM session.
    with db.session() as s:
        from sqlalchemy import select
        remaining = s.scalars(
            select(MechanisticValidation).where(
                MechanisticValidation.project_id == proj.id
            )
        ).all()
    assert remaining == []
    print("  [PASS] mechanistic_validations row cascade-deleted with project")

    # ---------------------------------------------------------------
    # 5) Existing-project regression (multiple sibling tables).
    # ---------------------------------------------------------------
    print("\n=== 5) Existing-project regression ===")
    # proj2 still alive; condition row + mechanistic row should coexist.
    db.save_condition_survey(
        project_id=proj2.id,
        result=compute_condition_survey(ConditionSurveyInput()),
    )
    assert db.latest_condition_survey(proj2.id) is not None
    assert db.latest_mechanistic_validation(proj2.id) is not None
    print("  [PASS] condition + mechanistic rows coexist on the same project")

    print("\nPHASE 15 PERSISTENCE SMOKE: ALL OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
