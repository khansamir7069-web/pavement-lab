# IITPAVE Output Fixture Intake (Phase 26)

Phase 26 adds an intake path for operator-provided IITPAVE output samples.
It is a metadata and contract-review workflow only.

## What This Does

- Captures source filename, byte size, line count, SHA-256 checksum, detected
  markers, and intake timestamp.
- Reuses the Phase-25 output contract detector.
- Classifies samples as `unverified`, `operator_provided_pending_review`,
  `verified_contract_sample`, or `rejected_unsupported`.
- Provides a parser-contract harness that blocks safely when no verified real
  IITPAVE output fixtures exist.
- Phase 27 can inspect `verified_contract_sample` fixtures and expose only
  conservative section metadata: header ranges, table-like line ranges,
  recognized labeled blocks, and marker line indexes.
- Phases 28 and 29 can map reviewed section structures into guarded schema
  families for regression coverage, while leaving real parsing blocked.
- Phase 30 can build an audit manifest summarizing reviewed schema family
  coverage, blocked schema counts, unsupported counts, and operator-readable
  parser readiness status.
- Phase 31 can render that manifest through report diagnostics so operators
  can review parser readiness, blocked schemas, and unsupported fixtures in a
  Word-report section.
- Phase 32 adds a guarded operator workflow entry point for selecting a local
  fixture folder and writing the schema diagnostics report.

## What This Does Not Do

- It does not run IITPAVE.
- It does not generate IITPAVE input files.
- It does not parse real IITPAVE engineering output.
- It does not extract fatigue or rutting strains.
- It does not extract stress/strain values from verified fixtures.
- It does not perform fatigue, rutting, layer recommendation, or any other
  engineering calculation.
- It does not make IRC:37 compliance claims.
- It does not treat schema coverage as permission to run real engineering
  calculations.

## Safe Fixture Workflow

Place operator-provided output samples in a local fixture folder that is not
invented by the application. Supported sample suffixes are `.out`, `.txt`,
`.dat`, and `.log`.

Optionally add `iitpave_fixture_manifest.json` in the same folder:

```json
{
  "fixtures": [
    {
      "filename": "operator_sample.out",
      "verification_status": "operator_provided_pending_review"
    }
  ]
}
```

Only mark a sample `verified_contract_sample` after an engineer has confirmed
that the file is a real IITPAVE output sample suitable for parser-contract
development. Even then, real parsing remains blocked until a verified output
schema is implemented in a later phase.

## Phase 27 Parser-Contract Limitations

`app.core.iitpave.parser_contract.inspect_iitpave_verified_parser_contract(...)`
accepts only Phase-26 fixture records marked `verified_contract_sample` whose
Phase-25 output status is `real_contract_pending`.

The layer rejects unverified records, unsupported formats, missing markers, and
incomplete contracts. When accepted, it reports structural section metadata only
and always records `engineering_values_extracted=false`. The returned sections
are audit aids for future parser work, not mechanistic results.

## Phase 30 Schema Manifest

`app.core.iitpave.schema_manifest.build_iitpave_fixture_schema_manifest(...)`
scans a fixture folder and returns a typed audit summary. It reports:

- total and verified fixture counts;
- reviewed schema family coverage;
- blocked, unknown, unsupported, pending-review, and rejected counts;
- diagnostic issues propagated from intake, parser-contract inspection, and
  schema mapping;
- operator-readable audit summary lines.

The manifest may report `audit_ready_calculations_blocked` when all verified
fixtures in the folder map to reviewed schema families. This is an audit status
only. It still returns `engineering_calculations_allowed=false`, and no
stress/strain extraction, fatigue/rutting computation, or IRC:37 compliance
claim is enabled.

## Phase 31 Report Diagnostics

`app.reports.iitpave_schema_report` converts a Phase-30 manifest into typed
report diagnostics and can render a Word section titled `IITPAVE FIXTURE SCHEMA
DIAGNOSTICS`.

The report section is operator-facing but remains audit-only. It summarizes
parser readiness, schema family coverage, fixture-level blocked status, and
blocking diagnostics. It does not run IITPAVE, does not parse output values,
does not compute mechanistic checks, and does not make compliance conclusions.

## Phase 32 Fixture-Folder Workflow

`app.reports.iitpave_schema_workflow.run_iitpave_schema_diagnostics_workflow(...)`
is the typed entry point used by the desktop UI. It accepts a local fixture
folder, builds the Phase-30 manifest, builds the Phase-31 report diagnostics
summary, and optionally writes a `.docx` diagnostics report.

The desktop UI exposes this as `IITPAVE Schema Diagnostics` in the sidebar. The
operator selects a local fixture folder, then selects a Word report path. The
workflow validates the output path extension, propagates all diagnostics, and
always reports `engineering_calculations_allowed=false`.

## Phase 33 Persistence History

When the Phase-32 workflow runs with an active project, the desktop UI records
an audit-only history row in `iitpave_schema_diagnostics_history`. The persisted
record stores the fixture folder, report path, workflow/manifest statuses,
reviewed schema counts, diagnostics summary JSON, and operator message.

The persisted row is included in project export/import records under
`iitpave_schema_diagnostics` for traceability. It is not a calculation record:
there are no strain, fatigue, rutting, IRC compliance, or recommendation fields,
and the serialized workflow payload continues to report
`engineering_calculations_allowed=false`.

## Phase 34 History Review

`app.reports.iitpave_schema_history` converts persisted history rows into typed
operator-review summaries. The desktop UI exposes these records through
`IITPAVE Schema History` for the active project.

The review workflow recalls stored fixture/report paths, workflow and manifest
statuses, schema counts, propagated diagnostics, and the original operator
message. It is read-only and audit-only: recalled history cannot trigger
strain extraction, mechanistic calculations, fatigue/rutting checks, IRC
compliance conclusions, or recommendation logic.

## Phase 35 Consultancy Report Inclusion

`app.reports.iitpave_schema_history.write_iitpave_schema_history_section(...)`
adds recalled schema diagnostics history to Word reports as an audit-only
section. The combined report builder includes this section when a project has
persisted IITPAVE schema diagnostics history.

The section lists persisted history records, the latest recalled fixture/report
paths, schema counts, propagated diagnostics, and the original operator message.
It continues to serialize `engineering_calculations_allowed=false` and does not
authorize parser output, strain extraction, mechanistic calculations,
fatigue/rutting checks, IRC compliance conclusions, or engineering
recommendations.
