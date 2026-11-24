# Architecture

This document separates the **working foundation** from the **planned production pipeline**. The project currently validates a storyboard; it does not yet generate or assemble film media.

## Current foundation

```text
storyboard.json
      |
      v
validate_storyboard.py <---- schema/storyboard.schema.json
      |
      v
tests/test_validate_storyboard.py

pipeline/config.py
  project paths, .env loading, and safe environment-variable access

pipeline/cache.py
  content fingerprints and deterministic cache paths

pipeline/retry.py
  bounded retries for explicitly classified transient errors

pipeline/runlog.py
  JSONL model-call records with sensitive-field redaction

pipeline/orchestrator.py
  storyboard validation before configured stages execute

pipeline/subtitles.py
  draft SRT timing derived from storyboard shot durations

pipeline/providers.py
  capability-specific, provider-neutral generation contracts
```

`storyboard.json` is the proposed contract shared by all production stages. `validate_storyboard.py` checks the JSON Schema and additional film rules before generation. `pipeline/config.py` centralizes paths and loads local environment variables with `python-dotenv`. Focused tests cover the cache, retry, logging, orchestration, and draft subtitle utilities.

The protocols in `pipeline/providers.py` define separate text, image, video, music, and narration capabilities so an adapter can declare only what its service supports. No concrete AI provider adapter exists yet. The cache, retry, logging, orchestration, subtitle, and provider-contract utilities are foundations; there are no generated assets, `runs.jsonl`, or final exports in the repository yet.

## Planned production flow

Story and script development take place before the production pipeline. The five planned production stages are:

```text
story and script
      |
      v
validate storyboard (required gate)
      |
      +--> keyframes and character/style references
      +--> moving shots
      +--> original music
      +--> Amharic narration and English subtitles
      |
      v
FFmpeg assembly and validation
      |
      +--> 9:16 export
      +--> 16:9 export
```

The image, video, music, and narration generation stages are planned, not implemented. Candidate providers and hosted execution environments are described in [README.md](README.md) and tracked for consent, transparency, and licensing in [ETHICS.md](ETHICS.md). Provider availability, free-tier limits, terms, and Amharic quality must be checked before using a service. Heavy image, video, and music generation is intended for hosted services or Kaggle/Colab, not the laptop.

## Stage contracts (planned)

Each stage will read the validated storyboard and write assets or metadata under `outputs/`. Exact output formats and provider parameters remain to be decided before generation.

| Stage | Inputs from the storyboard | Planned outputs | Status |
|---|---|---|---|
| Keyframes | Character descriptions, visual style, image prompts, shot seeds, aspect-ratio framing | Character/style reference sheet and one approved still per shot | Not implemented |
| Moving shots | Approved keyframe, motion prompt, duration, seed | Short video clips for selected shots | Not implemented |
| Music | Instrumental direction, music cues, timing, seed | Candidate score(s) and selected score | Not implemented |
| Narration and subtitles | Amharic narration, English subtitle text, narration settings | Narration audio and timed subtitle file | Draft SRT writer exists; narration generation and final audio synchronization are not implemented |
| Assembly | Approved media, shot durations, end-card details, export ratios | Radio cut, mixed film, and two final aspect-ratio exports | Not implemented |

The narration-only radio cut is an early story prototype. It must be reviewed before spending time or quota on expensive visual generation.

## Validation gate

The current command is:

```powershell
.\.venv\Scripts\python.exe validate_storyboard.py
```

`pipeline/orchestrator.py` calls `require_valid_storyboard()` before invoking any configured stage. A validation error stops the run before the first stage; a stage error propagates and prevents later stages from running. Production provider stages have not been registered yet.

## Caching helper (implemented; production integration pending)

Cache each generated item independently so an unchanged shot can be reused. A cache key should be a stable hash of all inputs that can affect that item, including:

- Stage and shot identifier.
- Prompt and relevant storyboard fields.
- Character/style reference file contents or their hashes.
- Provider, model/version, parameters, and seed.
- Dependency hashes from earlier stages.

`pipeline/cache.py` implements stable input hashing, includes the contents of named reference files, and derives cache output paths. Its unit tests cover deterministic keys, invalidation when a prompt or reference changes, and empty-file handling. Production stages do not consume the cache helper yet.

## Retries and failures (helper implemented; provider integration pending)

`pipeline/retry.py` implements bounded retries for caller-declared transient exception types. Validation errors, missing credentials, permission errors, and other undeclared failures are not retried. Provider wrappers must log every actual attempt. If moving-shot generation is unavailable, the documented fallback is a slow FFmpeg pan/zoom over an approved still; record that fallback honestly. No provider wrapper currently uses the retry helper.

No provider calls or generation failures have been recorded by the current pipeline because those stages do not exist yet.

## Run logging and cost evidence (logger implemented; provider integration pending)

`pipeline/runlog.py` provides `append_model_call()` to append one JSON object per actual model/API call, including:

- Timestamp, run identifier, stage, shot, and attempt.
- Provider and model/version.
- Non-secret parameters and seed (or `null` if the provider does not expose a seed).
- Input/cache fingerprint, status, and latency.
- Billed cost and/or list-price-equivalent cost, with the pricing basis or `null` when it cannot be verified.

The helper redacts sensitive parameter fields and common credential patterns. Callers must still avoid placing raw prompts or secret-bearing data in parameters; use a prompt hash instead. Never log API keys, authorization headers, private personal data, or full secret-bearing environment values. Cache hits are not model calls and must not be logged as if a provider ran. No provider has called the logger, and `runs.jsonl` does not exist because no model calls have been made.

`pipeline/subtitles.py` can write an English SRT using cumulative storyboard shot durations after validation. These are draft timings only; final subtitles must be checked against generated narration.

## Configuration and secrets

`pipeline/config.py` resolves paths relative to the repository, loads `.env` with `python-dotenv`, and exposes `get_env()` without printing values. `.env.example` contains placeholders, and `.gitignore` excludes `.env`. Provider-specific credentials should only be supplied to the provider that needs them and must not appear in source, notebooks, error messages, screenshots, or run logs.

## Testing strategy

The current lightweight checks are:

```powershell
.\.venv\Scripts\python.exe validate_storyboard.py
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

The current tests use temporary files and fake stages to cover validation-before-generation, deterministic cache keys and invalidation, bounded retry behavior, secret-safe run logs, and draft subtitle timing. Future FFmpeg command tests should avoid requiring media generation or paid model calls. Actual hosted provider smoke tests and media inspection will be recorded separately and run only after service access, terms, and costs are checked.
