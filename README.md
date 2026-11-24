# The Wisdom of Our Mothers

**The Wisdom of Our Mothers (የእናቶቻችን ጥበብ)** is a planned short film and a small Python project for building a reproducible AI-assisted film-production pipeline. The film tells a fictional Ethiopian family story; the code is intended to turn its storyboard into images, moving shots, sound, and finished video.

> **Project status:** The storyboard contract, JSON Schema, validator, validator tests, shared configuration helper, dependency list, environment template, and ethics policy are present. The production stages and finished media are not implemented yet. This README describes the current foundation separately from planned work.

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

1. **Keyframes:** Create character/style references and a still image for each shot. Cloudflare Workers AI is listed as a candidate for image generation; availability and terms must be checked before use.
2. **Moving shots:** Animate selected keyframes. Wan 2.2 is a candidate for Kaggle or Colab execution.
3. **Music:** Generate and choose an original instrumental score. ACE-Step is a candidate for Kaggle or Colab execution.
4. **Narration:** Generate Amharic narration and check pronunciation and pacing. Gemini TTS is a candidate, subject to model availability and free-tier checks.
5. **Assembly:** Use FFmpeg to add subtitles and the AI disclosure end card, mix narration and music, duck music under speech, normalize loudness, and export both aspect ratios.

The production-stage scripts, caching, retries, model-call logging, radio cut, and exports are **planned work**, not available end-to-end yet. Heavy image, video, and music generation is intended for hosted services or Kaggle/Colab, not a local laptop.

## Current project structure

```text
heritage-short/
├── .env.example
├── .gitignore
├── ETHICS.md
├── README.md
├── requirements.txt
├── storyboard.json
├── validate_storyboard.py
├── pipeline/
│   ├── __init__.py
│   └── config.py
├── schema/
│   └── storyboard.schema.json
└── tests/
    └── test_validate_storyboard.py
```

`.venv/`, Python cache folders, generated outputs, and local secrets are not listed as source files. The ignore rules exclude `.venv/`, Python caches, and `.env`.

## Windows PowerShell setup

Run these commands from PowerShell. The installation command uses the dependencies already listed in `requirements.txt`; this project does not ask you to install AI models on your laptop.

```powershell
Set-Location -LiteralPath 'C:\Users\HP\Downloads\heritage-short'
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
notepad .env
```

The copy command leaves an existing `.env` untouched. Do not commit `.env`; `.gitignore` excludes it. `.env.example` contains placeholder values only.

## Environment variables

`pipeline/config.py` loads a local `.env` with `python-dotenv` and provides `get_env()` for reading required or optional variables. It does not print or log their values.

| Variable | Intended use | Status |
|---|---|---|
| `GEMINI_API_KEY` | Candidate Gemini text and Amharic TTS calls | Check current model availability and free-tier limits before use. |
| `CLOUDFLARE_ACCOUNT_ID` | Candidate Cloudflare Workers AI image generation | Planned; verify access and limits before use. |
| `CLOUDFLARE_API_TOKEN` | Authenticate to Cloudflare Workers AI | Planned; keep secret. |
| `KAGGLE_USERNAME`, `KAGGLE_KEY` | Optional Kaggle notebook access for hosted generation | Optional; keep credentials secret. |
| `HF_TOKEN` | Optional Hugging Face access | Only needed if a selected service requires it; keep secret. |

Only configure credentials for services actually selected. Never put keys in source files, storyboard prompts, terminal output, screenshots, or `runs.jsonl`. The example file is not a real credential file.

## Validate the storyboard and run tests

From the project root, use the project virtual environment:

```powershell
.\.venv\Scripts\python.exe validate_storyboard.py
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m json.tool storyboard.json > $null
```

The first command validates `storyboard.json` against `schema/storyboard.schema.json` and the film rules. The unit tests cover valid and invalid storyboards, including scene count, timing, Amharic narration, subtitles, lesson coverage, and pre-generation validation. The final command checks that the storyboard is valid JSON syntax.

## Ethics and AI transparency

See [ETHICS.md](ETHICS.md) for the project's consent policy, fictional-character commitments, AI disclosure plan, privacy rules, cultural-respect notes, and model/tool license tracking. The license table includes items still marked for verification; those must be checked before the corresponding tools are used. No real person's likeness or voice may be used without documented informed consent.

The planned film includes a visible AI disclosure end card, and the platform's AI label will be enabled if the film is published. Audience feedback, experiments, costs, and model results will be recorded only after they actually happen.

## Progress and remaining work

### Foundations present

- A 10-shot, 75-second storyboard contract with Amharic narration text, English subtitles, four lesson tags, shot prompts, fictional character descriptions, seeds, aspect ratios, and a 3-second AI end card.
- A JSON Schema and Python validator with semantic checks.
- Unit tests for storyboard validation.
- Shared project paths and environment-variable helpers.
- Dependency declarations, a placeholder environment template, and an ethics policy.

### Still to do

- Have an Amharic speaker review narration, subtitles, and pronunciation guidance.
- Implement the script/story workflow and production-stage scripts.
- Generate and review reference images, keyframes, moving shots, music, and narration using hosted services; no media has been generated yet.
- Implement caching, retries, failure handling, and `runs.jsonl` logging for actual model calls.
- Create the narration-only radio cut and conduct both audience tests with at least three people each; neither test has happened yet.
- Implement FFmpeg assembly and verify subtitles, music ducking, loudness, the end card, and both exports.
- Complete the remaining documentation, actual experiment/failure/cost records, written report, walkthrough video, and public post.

There is not yet a one-command run of the complete pipeline. Costs, audience feedback, experiments, model results, generated media, and completed exports remain unrecorded or unfinished until they actually occur.
