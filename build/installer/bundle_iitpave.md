# Bundling the IITPAVE executable (Phase 17 / V1)

PavementLab V1 ships the **integration seam** for the IRC:37-2018 cl. 6.2
multi-layered elastic analysis tool (IITPAVE) but **not** the binary
itself — the binary is operator-supplied because of licensing and
because version-locking the executable belongs to the deployment, not
the source tree.

This document describes:

1. Where the binary must live.
2. How the runner discovers it.
3. The toggle workflow between `StubRunner` (placeholder, default) and
   `ExternalExeRunner` (subprocess seam).
4. What still works when the binary is absent (V1 default).

---

## 1. Canonical filesystem location

```
<bundle_root>/app/external/iitpave/
    IITPAVE.exe          # Windows binary  (case-sensitive on POSIX)
    iitpave              # POSIX binary    (alternative; lowercase)
```

`<bundle_root>` resolves via `app.config.APP_DIR`, which in turn calls
`app.config._resource_root()`. Under a PyInstaller-frozen build that
expands to `sys._MEIPASS` (the unpacked bundle); from source it is the
`app/` directory.

The directory ships in source control via `.gitkeep` so the bundled
layout exists before any binary is dropped in. Both the legacy
`build/pavement_lab.spec` and the V1 spec at
`build/installer/pyinstaller.spec` ship `app/external/` as a `--add-data`
entry so the directory survives freezing.

---

## 2. Runner discovery

`app.core.iitpave.runner.default_iitpave_exe_path()` returns the first
extant binary it finds in the bundled directory, preferring the
Windows filename. If nothing is present it returns the canonical
Windows path so error messages cite a concrete, expected location
rather than `None`.

`ExternalExeRunner(exe_path=None)` uses this default. Pass an explicit
`exe_path=...` to point at an out-of-tree binary (test harnesses do
this; production builds should not).

Phase 22 adds a structured diagnostics layer in
`app.core.iitpave.discovery`. It validates, without executing the binary,
these candidate sources in order:

1. caller-supplied `configured_path`;
2. `SAMPAVE_IITPAVE_EXE`;
3. the bundled drop-in directory shown above;
4. optional `PATH` search when explicitly requested.

`validate_iitpave_environment(...)` returns typed candidates, the selected
path when one exists, and structured `info` / `warning` / `error` issues
that can be serialized into audit logs or shown in the UI. It does not
claim IITPAVE version compliance; it only validates filesystem
configuration.

Phase 23 adds `app.core.iitpave.runner_config.select_iitpave_runner(...)`.
The default mode is still `stub`. Selecting `external_exe` now goes through
the diagnostics layer first and returns an explicit blocked result when the
executable path is missing, invalid, a directory, unreadable, empty, or lacks
execute permission where the platform exposes that signal. The selector does
not run IITPAVE and does not parse IITPAVE output.

Phase 24 adds `app.core.iitpave.dry_run.check_iitpave_dry_run_readiness(...)`.
It consumes a Phase-23 runner-selection result and can perform a bounded,
no-engineering-input subprocess launch probe. It records command, working
directory, return code, and stdout/stderr previews for audit only. It still
does not build IITPAVE input, parse engineering output, compute strains, or
claim IRC:37 compliance.

Phase 25 adds `app.core.iitpave.output_contract.inspect_iitpave_output_contract(...)`.
It inspects raw output text/files before any parser is used. The only
recognized parseable contract today is SamPave's own Phase-13 stub marker
(`PHASE13_STUB_V1`), which remains placeholder-only. Real IITPAVE-looking
output is classified as `real_contract_pending` and blocked until a verified
real IITPAVE output schema/fixture is added. Unknown, missing, empty, or
unreadable output is also blocked; no default strain/stress values are
invented.

Phase 26 adds `app.core.iitpave.fixture_intake` for operator-provided output
sample intake. It records filename, byte size, line count, detected markers,
SHA-256, timestamp, and review status. The parser-contract harness blocks
safely when no `verified_contract_sample` is available, and even verified
metadata does not enable real parsing until a later phase implements a
reviewed output schema. See `docs/iitpave_fixture_intake.md`.

---

## 3. Toggling between StubRunner and ExternalExeRunner

V1 default everywhere is `StubRunner` — the placeholder produces
deterministic text consumed by the same parser used for real output.
`MechanisticResult.is_placeholder=True` flows out and the Phase-14
refusal gate withholds verdicts.

To switch to the real binary in the surrounding caller (a future Phase
17+ task; not wired into the UI yet):

```python
from app.core.iitpave import (
    ExternalExeRunner,
    StubRunner,
    build_iitpave_input,
    default_iitpave_exe_path,
    parse_iitpave_output,
)

runner = StubRunner()                              # default
# Promote to real binary when present:
if default_iitpave_exe_path().is_file():
    runner = ExternalExeRunner()                   # subprocess seam

input_text  = build_iitpave_input(structure, load, points)
output_text = runner.run(input_text)               # opaque text I/O
mech_result = parse_iitpave_output(output_text, source=runner.source)
```

The parser sets `MechanisticResult.is_placeholder=False` automatically
when `source != SOURCE_STUB` — Phase-14 verdicts will then be produced
instead of refused.

### Exchange modes

`ExternalExeRunner` supports two subprocess exchange modes:

| Mode | Selected by | When to use |
|---|---|---|
| stdin/stdout (default) | `use_stdin_stdout=True` | Modern Fortran builds with READ(5) / WRITE(6). |
| File-based            | `use_stdin_stdout=False` | Legacy IRC:37 IITPAVE 6.0 — writes `iitp_inp.dat`, reads `iitp_out.dat`. |

File-based mode runs each invocation in a private `tempfile.TemporaryDirectory`
so concurrent runs cannot collide on the fixed filenames.

A timeout (default 60 s) caps each invocation; exceeded → `TimeoutError`.
Non-zero exit code → `RuntimeError` carrying the first 500 chars of
stderr. Missing exe → `FileNotFoundError` (placeholder-safety contract
— the runner NEVER silently substitutes stub output).

---

## 4. Behaviour when the binary is absent (V1 default)

| Surface | Behaviour |
|---|---|
| `StubRunner.run()` | Works (placeholder text). |
| `parse_iitpave_output(stub_text)` | Returns `MechanisticResult(is_placeholder=True, source="stub")`. |
| `compute_mechanistic_validation(...)` | Refusal gate fires → `summary.refused=True`, both verdicts `None`, reason cites placeholder. |
| `ExternalExeRunner(...).run()` | Raises `FileNotFoundError` referencing this document. |
| Word reports (Phase 15) | Render `[REFUSED]` banner with the verbatim Phase-14 refusal reason; calibration tables still shown for transparency. |
| Sample validation (Phase 16) | `corpus_NN_*` fixtures that set `mechanistic.is_placeholder=true` are expected to produce `refused: true` in their golden snapshots. |

In other words: nothing is silently broken, and every consumer can tell
the difference between *"verdict refused because mechanistic input is
placeholder"* and *"verdict computed against real elastic analysis"*.

---

## 5. Future bundling steps (V2 candidate)

Out of scope for V1 / Phase 17 but the architecture is ready:

1. Vendor the IITPAVE binary into the installer artefact under a
   licence-compatible scheme.
2. Add a one-shot installer hook that verifies the binary's SHA-256
   against a known release manifest before unlocking the
   `ExternalExeRunner` path in the UI.
3. Expose a UI affordance ("Use real IITPAVE / Use stub") so engineers
   can choose per-project; today this is a one-line code change on the
   caller side.
4. Add a parser-level confirmation that real IITPAVE output format
   matches the contract owned by `app/core/iitpave/parser.py`; if the
   bundled version emits a different column ordering, the parser is
   the single file to update.
