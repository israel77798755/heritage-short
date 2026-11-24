# Architecture

This document separates the **working foundation** from the **planned production pipeline**. The project has tested assembly command builders, but it has not generated or assembled film media.

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

pipeline/cached_generation.py
  cache lookup before provider calls; cache misses use retries and run logging

pipeline/keyframes.py
  provider-injected storyboard keyframe stage with character/style references

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

pipeline/provider_runner.py
  bounded retries, output checks, and per-attempt run logging

pipeline/media_preflight.py
  FFmpeg/ffprobe lookup, media probing, subtitle checks, and output directories

pipeline/assembly.py
  radio cut, still-image motion fallback, and two-ratio FFmpeg commands

pipeline/cli.py
  offline assembly preflight and explicit radio/video rendering commands
```

`storyboard.json` is the proposed contract shared by all production stages. `validate_storyboard.py` checks the JSON Schema and additional film rules before generation. `pipeline/config.py` centralizes paths and loads local environment variables with `python-dotenv`. Focused tests cover cache, retry, logging, orchestration, subtitle, media preflight, and assembly utilities.

The protocols in `pipeline/providers.py` define separate text, image, video, music, and narration capabilities so an adapter can declare only what its service supports. `pipeline/provider_runner.py` connects an adapter call to bounded retries and `runs.jsonl` logging, verifies that a non-empty output file was created, and records only a prompt hash. No concrete AI provider adapter exists yet, and no real provider call has been made. There are no generated assets, `runs.jsonl`, or final exports in the repository yet.

`pipeline/media_preflight.py` checks tool availability, probes every shot/audio input, validates the English SRT and licensed-font file, and prepares writable output directories for both aspect ratios and the radio cut. `pipeline/assembly.py` builds and runs FFmpeg commands for normalized shot clips, a still-image pan/zoom fallback, the narration-only WAV cut, and 9:16 / 16:9 exports. Final exports have selectable English subtitles, a centered disclosure card, music ducking, loudness normalization, and output-stream/duration checks. Existing outputs are never overwritten.

The FFmpeg workflow has only been tested with mocked tools and temporary fake assets. `ffmpeg` and `ffprobe` are absent from the current PATH, so no command has rendered real media. A licensed font with Ethiopic glyph coverage must be supplied, and its shaping behavior still needs an actual render check.

## Assembly CLI

`python -m pipeline.cli preflight --font <font-path>` checks the storyboard, expected shot/audio/subtitle assets, font file, FFmpeg tools, streams, and output directories without rendering. The default inputs are `outputs/assets/moving_shots/shot-NN.mp4` with `outputs/assets/keyframes/shot-NN.png` as a per-shot fallback, `outputs/audio/narration.wav`, `outputs/audio/music.wav`, and `outputs/subtitles/en.srt`.

`python -m pipeline.cli render --font <font-path>` runs preflight first, then creates the narration-only radio cut and both video ratios. It refuses to overwrite existing output files. This interface performs no AI calls; the CLI's command flow is tested with mocks, while actual rendering still requires FFmpeg, prepared assets, and a licensed font with verified Amharic glyph shaping. See [README.md](README.md) for Windows commands and path overrides.

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
| Keyframes | Validated storyboard, approved Almaz/Dawit/style reference images, shot seeds | One cached still per shot, with scene references and prompts | Callable provider-injected stage is implemented and fake-tested; reference creation/review and real provider execution are pending |
| Moving shots | Approved keyframe, motion prompt, duration, seed | Short video clips for selected shots | Not implemented |
| Music | Instrumental direction, music cues, timing, seed | Candidate score(s) and selected score | Not implemented |
| Narration and subtitles | Amharic narration, English subtitle text, narration settings | Narration audio and timed subtitle file | Draft SRT writer exists; narration generation and final audio synchronization are not implemented |
| Assembly | Approved media, shot durations, narration, score, subtitles, licensed font | Radio cut, mixed 9:16 and 16:9 videos, disclosure card | Command builders and mocked tests implemented; real rendering awaits FFmpeg and approved assets |

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

`pipeline/cache.py` implements stable input hashing, includes the contents of named reference files, and derives cache output paths. `pipeline/cached_generation.py` computes keys from shot ID, provider/model, prompt, parameters, seed, file type, and reference-image contents. It skips provider calls and run-log entries for a valid cache hit; a miss runs through the retrying, logging provider runner and writes to the deterministic cache path. Tests cover cache hits, invalidation by reference/shot/parameter changes, and corrupt empty entries. Concrete production stages do not use this wrapper yet.

## Retries and failures (helper implemented; provider integration pending)

`pipeline/retry.py` implements bounded retries for caller-declared transient exception types. `pipeline/provider_runner.py` retries rate-limit and timeout errors by default and logs every attempt. Validation errors, missing credentials, permission errors, and other undeclared failures are not retried by default. If moving-shot generation is unavailable, the documented fallback is a slow FFmpeg pan/zoom over an approved still; record that fallback honestly. No real provider call has exercised these helpers.

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

The current tests use temporary files and fake stages/providers/tools to cover validation-before-generation, deterministic cache keys and invalidation, per-attempt provider logging, bounded retries, secret-safe run logs, subtitle validation, assembly command construction, overwrite protection, and final-output checks. Actual FFmpeg execution, media inspection, hosted provider tests, and Amharic quality checks remain pending and require the tools, assets, terms, and human review to be available.
