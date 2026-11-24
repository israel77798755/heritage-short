# The Wisdom of Our Mothers

**The Wisdom of Our Mothers (የእናቶቻችን ጥበብ)** is a planned short film and a small Python project for building a reproducible AI-assisted film-production pipeline. The film tells a fictional Ethiopian family story; the code is intended to turn its storyboard into images, moving shots, sound, and finished video.

> **Project status:** The storyboard contract, validator, pipeline helpers, media preflight, and tested FFmpeg command builders are present. No provider-backed generation or real media render has run. FFmpeg and ffprobe are not installed on the current PATH.

See [REPORT.md](REPORT.md) for the current implementation progress report; it is not a final evaluation of a completed film.

## Story

Almaz, a fictional Ethiopian mother, passes everyday wisdom to her young son Dawit. Across ten planned shots, he learns to trust God, respect others, keep trying when work is difficult, and remain hopeful through hardship. The story is set in the Ethiopian highlands and is planned with Amharic narration and English subtitles.

## Film specifications

- **Story content:** 75 seconds across 10 shots.
- **AI disclosure end card:** 3 seconds, making the planned total runtime 78 seconds.
- **Narration:** Amharic (`am-ET`); English subtitles.
- **Exports:** vertical 9:16 and horizontal 16:9.
- **Style:** warm, emotional, cinematic; the storyboard specifies the visual and music direction.

These are storyboard specifications, not claims that a film has already been generated or exported.

## Planned production pipeline

Story and script development happen before media generation. The planned production stages read the storyboard contract and should validate it before making any generation calls:

1. **Keyframes:** `pipeline.visual_workflow` validates the storyboard and generates reference candidates. Its approval callback must explicitly return `True` after human review before keyframe requests can run. `GeminiImageProvider` implements Google's Interactions image API; the current model docs recommend `gemini-nano-banana-2.1`, but account access, pricing, and terms must be checked before any call. The reference stage can create candidate portraits of Almaz and Dawit plus a visual-style image. No provider call or media generation has occurred.
2. **Moving shots:** Animate selected keyframes. Wan 2.2 is a candidate for Kaggle or Colab execution.
3. **Music:** Generate and choose an original instrumental score. ACE-Step is a candidate for Kaggle or Colab execution.
4. **Narration:** Generate Amharic narration and check pronunciation and pacing. Gemini TTS is a candidate, subject to model availability and free-tier checks.
5. **Assembly:** Tested command builders prepare a narration-only WAV radio cut and 9:16 / 16:9 video exports. They include an English subtitle track, a disclosure end card, music ducking, loudness normalization, output checks, and a still-image pan/zoom fallback. Real rendering awaits FFmpeg, ffprobe, approved media assets, and a licensed font with Amharic glyph coverage.

The provider-injected reference and keyframe functions use content caching, bounded retries, and per-attempt model-call logging. The Gemini image adapter is concrete but has not been invoked; a complete production run and video/music/narration adapters remain unimplemented. The SRT writer creates draft timing from shot durations; it is not synchronized to generated narration. The assembly workflow has command-level tests but has not rendered real outputs. Heavy image, video, and music generation is intended for hosted services or Kaggle/Colab, not a local laptop.

## Current project structure

```text
heritage-short/
├── .env.example
├── .gitignore
├── ARCHITECTURE.md
├── COSTS.md
├── DESIGN.md
├── ETHICS.md
├── EXPERIMENTS.md
├── FAILURES.md
├── MEDIA_PLACEHOLDERS.json
├── README.md
├── REPORT.md
├── requirements.txt
├── storyboard.json
├── validate_storyboard.py
├── pipeline/
│   ├── __init__.py
│   ├── assembly.py
│   ├── cached_generation.py
│   ├── cache.py
│   ├── cli.py
│   ├── config.py
│   ├── gemini_image.py
│   ├── keyframes.py
│   ├── media_preflight.py
│   ├── orchestrator.py
│   ├── provider_runner.py
│   ├── providers.py
│   ├── references.py
│   ├── retry.py
│   ├── runlog.py
│   ├── subtitles.py
│   └── visual_workflow.py
├── schema/
│   └── storyboard.schema.json
└── tests/
    ├── test_assembly.py
    ├── test_cached_generation.py
    ├── test_cache.py
    ├── test_cli.py
    ├── test_gemini_image.py
    ├── test_keyframes.py
    ├── test_media_placeholders.py
    ├── test_media_preflight.py
    ├── test_orchestrator.py
    ├── test_provider_runner.py
    ├── test_providers.py
    ├── test_references.py
    ├── test_retry.py
    ├── test_runlog.py
    ├── test_subtitles.py
    ├── test_validate_storyboard.py
    └── test_visual_workflow.py
```

`.venv/`, Python cache folders, generated outputs, and local secrets are not listed as source files. The ignore rules exclude `.venv/`, Python caches, and `.env`.

## Windows PowerShell setup

Run these commands from PowerShell. The installation command uses the dependencies already listed in `requirements.txt`; this project does not ask you to install AI models on your laptop.

```powershell
Set-Location -LiteralPath 'C:\Users\HP\Downloads\heritage-short'
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

No API key or `.env` file is needed to validate the storyboard or run the offline tests. Do not create or enter provider credentials for this offline workflow. If a provider is separately approved later, `.env.example` contains placeholders and the optional `.env` file is excluded by `.gitignore`.

## Environment variables

`pipeline/config.py` loads a local `.env` with `python-dotenv` and provides `get_env()` for reading required or optional variables. It does not print or log their values.

| Variable | Intended use | Status |
|---|---|---|
| `GEMINI_API_KEY` | Explicitly invoked Gemini image adapter; candidate Gemini text and Amharic TTS calls | Only read when a Gemini request is explicitly made. Verify model access, pricing, data terms, and quotas first. |
| `CLOUDFLARE_ACCOUNT_ID` | Candidate Cloudflare Workers AI image generation | Planned; verify access and limits before use. |
| `CLOUDFLARE_API_TOKEN` | Authenticate to Cloudflare Workers AI | Planned; keep secret. |
| `KAGGLE_USERNAME`, `KAGGLE_KEY` | Optional Kaggle notebook access for hosted generation | Optional; keep credentials secret. |
| `HF_TOKEN` | Optional Hugging Face access | Only needed if a selected service requires it; keep secret. |

Only configure credentials for services actually selected. Never put keys in source files, storyboard prompts, terminal output, screenshots, or `runs.jsonl`. The example file is not a real credential file.

### Gemini image adapter status

`pipeline.gemini_image.GeminiImageProvider` uses Python's standard-library HTTP client and does not create a client or make a request during construction. It is not used by validation or the assembly CLI; tests invoke it only with mocked HTTP, so no API key or network request is needed. A direct `generate_image()` call would upload its prompt and any reference images and may incur charges, so keep it unused until model access, pricing, quotas, and Google's data terms are checked and accepted. The API's seed is not exposed, so a call made through the logged runner records a null seed. Google's current image documentation states generated images carry SynthID; preserve that provenance. No provider-generation CLI command exists.

### Media placeholders

[`MEDIA_PLACEHOLDERS.json`](MEDIA_PLACEHOLDERS.json) is a tracking inventory only, not a set of media files. Every listed asset is marked pending; no fake or empty `.png`, `.mp4`, or audio files are supplied. The assembly CLI requires actual files and does not accept this JSON inventory as media. Update the inventory when a real, reviewed asset is produced; do not mark an asset complete before checking the file and its provenance.

## Validate the storyboard and run tests

From the project root, use the project virtual environment:

```powershell
.\.venv\Scripts\python.exe validate_storyboard.py
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m json.tool storyboard.json > $null
```

The first command validates `storyboard.json` against `schema/storyboard.schema.json` and the film rules. The unit tests cover valid and invalid storyboards, including scene count, timing, Amharic narration, subtitles, lesson coverage, and pre-generation validation. The final command checks that the storyboard is valid JSON syntax.

## Assembly preflight and rendering

The assembly CLI has two explicit commands. It does not call AI providers or generate assets. Both commands require an existing font file; before a real render, verify that the font is licensed for this use and supports Amharic text.

Run an offline preflight after the inputs are prepared:

```powershell
.\.venv\Scripts\python.exe -m pipeline.cli preflight --font 'C:\path\to\licensed-font.ttf'
```

By default, the CLI looks for each shot first at `outputs\assets\moving_shots\shot-NN.mp4`, then falls back to `outputs\assets\keyframes\shot-NN.png`. It also requires `outputs\audio\narration.wav`, `outputs\audio\music.wav`, and `outputs\subtitles\en.srt`. The output directory defaults to `outputs\production`. Paths and FFmpeg executable locations can be overridden with the command's `--help` options.

Only after preflight succeeds and the media/tools are approved and available, render the radio cut and both aspect ratios:

```powershell
.\.venv\Scripts\python.exe -m pipeline.cli render --font 'C:\path\to\licensed-font.ttf'
```

Rendering uses FFmpeg locally for assembly only, never for heavy AI generation. It refuses to overwrite existing outputs. CLI and assembly tests use mocked media tools and temporary fixtures; they do not prove that a real FFmpeg render or Amharic text shaping works. Neither preflight on production assets nor a real render has been performed yet.

## Ethics and AI transparency

See [ETHICS.md](ETHICS.md) for the project's consent policy, fictional-character commitments, AI disclosure plan, privacy rules, cultural-respect notes, and model/tool license tracking. The license table includes items still marked for verification; those must be checked before the corresponding tools are used. No real person's likeness or voice may be used without documented informed consent.

The planned film includes a visible AI disclosure end card, and the platform's AI label will be enabled if the film is published. Audience feedback, experiments, costs, and model results will be recorded only after they actually happen.

## Progress and remaining work

### Foundations present

- A 10-shot, 75-second storyboard contract with Amharic narration text, English subtitles, four lesson tags, shot prompts, fictional character descriptions, seeds, aspect ratios, and a 3-second AI end card.
- A JSON Schema and Python validator with semantic checks.
- Unit tests for storyboard validation and the helper modules listed below.
- Shared project paths and environment-variable helpers.
- Content-based cache-key and output-path helpers used by the cache-aware provider-call wrapper.
- Cache-aware provider-call wrapper integrated into the provider-injected reference and keyframe stages: cache hits skip API calls; cache misses use the logged retry runner.
- Gemini image adapter using Python's standard-library HTTP client; it is lazy, does not call the API on construction, and has mocked tests only.
- Provider-injected keyframe stage that combines storyboard style and shot prompts with Almaz, Dawit, and visual-style reference images; fake-provider tests verify cache reuse. It has not been run with a real provider or media.
- Provider-injected, cached generation of candidate Almaz, Dawit, and visual-style reference images. These are not generated yet and require human review before use.
- Bounded retry helper used by the provider-call runner; Gemini rate limits and timeouts are classified for retry. No live provider calls have occurred.
- JSONL model-call logger with sensitive-value redaction (no provider calls or `runs.jsonl` yet).
- Validation-gated visual workflow that stops on invalid storyboards and requires explicit approval of reference candidates before keyframe generation.
- Reference/keyframe stages are registered in the visual workflow; moving shots, music, and narration remain unregistered.
- Provider-neutral text, image, video, music, and narration capability contracts; Gemini image is the only concrete adapter, while text/video/music/narration adapters remain unimplemented.
- Provider-call runner with bounded retries, output-file checks, prompt-hash logging, and per-attempt run records; no real provider calls have occurred.
- A machine-readable placeholder inventory for references, per-shot keyframes and optional moving shots, audio, subtitles, font, and final exports; no fake media files are supplied.
- Draft English SRT generation from storyboard shot durations (not final narration sync).
- Assembly preflight checks FFmpeg/ffprobe paths, media streams, SRT timing, font-file presence, and writable output directories.
- FFmpeg command builders for still-image pan/zoom, normalized shot clips, a narration-only radio cut, and selectable-subtitle 1080p vertical/horizontal exports.
- Music sidechain ducking, final loudness normalization (-14 LUFS / -1 dBTP), three-second disclosure card, and export duration/stream validation.
- Mocked assembly tests; no FFmpeg executable or real source media was available for an actual render.
- Project documentation, a progress report (not a final film evaluation), dependency declarations, placeholder environment template, and ethics policy.

### Still to do

- Have an Amharic speaker review narration, subtitles, and pronunciation guidance.
- Verify Gemini image model access, pricing, and data terms; create and approve the three reference images, then generate/review keyframes. No media has been generated yet.
- Implement video, music, and narration adapters and complete script/story and production-stage orchestration; real provider calls remain pending.
- Once FFmpeg/ffprobe and approved assets are available, run preflight and render/inspect the radio cut and both aspect ratios; command-level tests are not a substitute for media inspection.
- Provide and verify the license and Amharic glyph/shaping of the end-card font before rendering.
- Conduct both audience tests with at least three people each; neither test has happened yet.
- Continue recording real experiments, failures, and costs in their existing ledgers; create the written report and walkthrough video, and prepare the public post.

There is not yet a one-command run of the complete pipeline. Costs, audience feedback, experiments, model results, generated media, and completed exports remain unrecorded or unfinished until they actually occur.
