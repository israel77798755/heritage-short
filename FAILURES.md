# Failures and blockers

This log records actual problems encountered while building or running the project, what was tried, and the outcome. It does not predict failures or claim that a workaround succeeded when it has not been tested.

## Current status

- No model or media-generation call has been made by the project pipeline, so there are no provider quota, model, or output failures to report.
- No production pipeline run has been attempted.

## Observed environment blocker

### FFmpeg tools were not found on the laptop PATH

- **Observed:** A PowerShell preflight on 2026-11-24 did not find `ffmpeg` or `ffprobe` on `PATH`.
- **Impact:** Local assembly and media probing cannot be assumed available.
- **Attempts:** No installation or download was attempted.
- **Resolution:** None yet. Recheck tool availability before assembly. Prefer a hosted environment if suitable; ask before installing software on the laptop.
- **Status:** Open; this observation should be rechecked because the environment may have changed.

## Failure entry template

For each real failure, record:

- **Date, stage, and run ID:**
- **Expected behavior:**
- **Observed error or failure:**
- **Relevant model/version, parameters, and seed:** (never include credentials)
- **What was tried:**
- **Resolution or fallback:** (or `unresolved`)
- **Evidence:** (redacted error text, run-log line, or output identifier)
- **Impact on quality, time, or cost:** (measured where possible; otherwise `not measured`)
