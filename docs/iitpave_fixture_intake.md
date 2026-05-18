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

## What This Does Not Do

- It does not run IITPAVE.
- It does not generate IITPAVE input files.
- It does not parse real IITPAVE engineering output.
- It does not extract fatigue or rutting strains.
- It does not make IRC:37 compliance claims.

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
