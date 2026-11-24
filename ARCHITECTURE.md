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
```

`storyboard.json` is the proposed contract shared by all production stages. `validate_storyboard.py` checks the JSON Schema and additional film rules before generation. `pipeline/config.py` centralizes paths and loads local environment variables with `python-dotenv`. The current test suite checks valid and invalid storyboard cases.

There are no production-stage scripts, generated assets, `runs.jsonl`, or final exports in the repository yet.

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

The stages are planned, not implemented. Candidate providers and hosted execution environments are described in [README.md](README.md) and tracked for consent, transparency, and licensing in [ETHICS.md](ETHICS.md). Provider availability, free-tier limits, terms, and Amharic quality must be checked before using a service. Heavy image, video, and music generation is intended for hosted services or Kaggle/Colab, not the laptop.

## Stage contracts (planned)

Each stage will read the validated storyboard and write assets or metadata under `outputs/`. Exact output formats and provider parameters remain to be decided before generation.

| Stage | Inputs from the storyboard | Planned outputs | Status |
|---|---|---|---|
| Keyframes | Character descriptions, visual style, image prompts, shot seeds, aspect-ratio framing | Character/style reference sheet and one approved still per shot | Not implemented |
| Moving shots | Approved keyframe, motion prompt, duration, seed | Short video clips for selected shots | Not implemented |
| Music | Instrumental direction, music cues, timing, seed | Candidate score(s) and selected score | Not implemented |
| Narration and subtitles | Amharic narration, English subtitle text, narration settings | Narration audio and timed subtitle file | Not implemented |
| Assembly | Approved media, shot durations, end-card details, export ratios | Radio cut, mixed film, and two final aspect-ratio exports | Not implemented |

The narration-only radio cut is an early story prototype. It must be reviewed before spending time or quota on expensive visual generation.

## Validation gate

The current command is:

```powershell
.\.venv\Scripts\python.exe validate_storyboard.py
```

Production orchestration must call the same validation function before invoking any provider or modifying generated assets. A validation error should stop the run and identify the invalid field; it must not be converted into a success-shaped fallback.

## Caching (planned)

Cache each generated item independently so an unchanged shot can be reused. A cache key should be a stable hash of all inputs that can affect that item, including:

- Stage and shot identifier.
- Prompt and relevant storyboard fields.
- Character/style reference file contents or their hashes.
- Provider, model/version, parameters, and seed.
- Dependency hashes from earlier stages.

When an input changes, invalidate that item and only its downstream dependents. For example, changing one motion prompt should not regenerate unrelated keyframes or the score. Final assembly may rerun to incorporate changed inputs without making new model calls. Cache metadata and files should remain inspectable. This mechanism is not implemented yet.

## Retries and failures (planned)

Retries should be bounded and limited to transient failures such as timeouts or rate limits. Validation errors, missing credentials, permission errors, and other permanent failures should stop clearly rather than retry indefinitely. Record each real attempt and its outcome. If moving-shot generation is unavailable, the documented fallback is a slow FFmpeg pan/zoom over an approved still; record that fallback honestly.

No provider calls or generation failures have been recorded by the current pipeline because those stages do not exist yet.

## Run logging and cost evidence (planned)

`runs.jsonl` will contain one JSON object per actual model/API call, including at least:

- Timestamp, run identifier, stage, shot, and attempt.
- Provider and model/version.
- Non-secret parameters and seed (or `null` if the provider does not expose a seed).
- Input/cache fingerprint, status, and latency.
- Billed cost and/or list-price-equivalent cost, with the pricing basis or `null` when it cannot be verified.

Never log API keys, authorization headers, private personal data, or full secret-bearing environment values. Cache hits are not model calls and must not be logged as if a provider ran. The log does not exist yet because no model calls have been made.

## Configuration and secrets

`pipeline/config.py` resolves paths relative to the repository, loads `.env` with `python-dotenv`, and exposes `get_env()` without printing values. `.env.example` contains placeholders, and `.gitignore` excludes `.env`. Provider-specific credentials should only be supplied to the provider that needs them and must not appear in source, notebooks, error messages, screenshots, or run logs.

## Testing strategy

The current lightweight checks are:

```powershell
.\.venv\Scripts\python.exe validate_storyboard.py
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Planned pipeline tests will use mocked provider calls to test validation-before-generation, deterministic cache keys and invalidation, bounded retry behavior, failure reporting, secret-safe run logs, and FFmpeg command construction without making paid or heavy model calls. Actual hosted provider smoke tests and media inspection will be recorded separately and run only after service access, terms, and costs are checked.
