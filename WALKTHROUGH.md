# Walkthrough Script (5 Minutes Max) — The Wisdom of Our Mothers

**Target duration:** ~4 minutes 15 seconds (under the 5-minute limit)  
**Format:** Screen share of the GitHub repository + GitHub Actions run + final film preview

---

## 0:00 – 0:45 | Introduction & Story Goal
> "Hi, I'm Israel, and this is **The Wisdom of Our Mothers (የእናቶቻችን ጥበብ)**—a 78-second AI-assisted short film and reproducible production pipeline.  
> The film tells a fictional story about an Ethiopian mother, Almaz, and her son, Dawit, sharing four timeless lessons: **trust God, respect others, never give up, and remain hopeful during difficult times**.  
> It is narrated in Amharic, subtitled in English, scored with original instrumental music, and exported in both vertical `9:16` and horizontal `16:9` formats with a 3-second AI disclosure end card."

---

## 0:45 – 2:00 | Architecture & How the Pipeline Works
*(Show `storyboard.json`, `schema/storyboard.schema.json`, and `pipeline/` on GitHub.)*

> "The key idea behind the codebase is that **`storyboard.json` is the single contract between every stage**.  
> First, `validate_storyboard.py` checks `storyboard.json` against `schema/storyboard.schema.json` using `jsonschema`, plus semantic rules: 8 to 12 shots, 60 to 90 seconds total runtime including the end card, Amharic Ge'ez script in narration, non-empty English subtitles, both aspect ratios, and all four lessons covered.  
> Second, the pipeline separates generation from assembly:
> - `pipeline/config.py` loads paths and environment keys safely without exposing secrets.
> - `pipeline/cache.py` and `pipeline/runlog.py` hash inputs for caching and log every model call—provider, model, seed, latency, and cost—into `runs.jsonl`.
> - `pipeline/subtitles.py` builds timed English SRT subtitles from the storyboard.
> - `pipeline/media_preflight.py` and `pipeline/assembly.py` validate tools and assets, then drive FFmpeg to apply slow Ken Burns motion to stills, duck the music under narration with `sidechaincompress`, normalize loudness to `-14 LUFS`, add the AI disclosure end card, and export both `9:16` and `16:9` MP4s."

---

## 2:00 – 3:00 | One Hard Technical Decision
*(Show `pipeline/assembly.py` and `.github/workflows/produce_film.yml`.)*

> "The hardest technical decision was **running the entire production pipeline remotely in GitHub Actions with zero paid APIs and zero local laptop rendering**.  
> My laptop did not have FFmpeg installed and I had no paid API billing or GPU access. Instead of blocking on paid video/image APIs, I designed the pipeline around **graceful fallbacks and clean stage boundaries**:
> - FFmpeg runs on GitHub-hosted Ubuntu runners.
> - When moving-shot video generation isn't available, `pipeline/cli.py` automatically falls back from `moving_shots/shot-XX.mp4` to `keyframes/shot-XX.png` and `assembly.py` adds gentle Ken Burns zoom-and-pan motion.
> - For Amharic narration and score, we used zero-key free tools (`edge-tts` with `am-ET-MekdesNeural` and FluidSynth MIDI synthesis) so the whole pipeline remains reproducible from a clean clone."

---

## 3:00 – 4:15 | Live Demo: Regenerating a Single Shot
*(Show `storyboard.json` and `pipeline/cache.py` / `scripts/produce_cloud.py`.)*

> "To regenerate just one shot—say, changing Scene 4's `image_prompt` or `narration` in `storyboard.json`—we don't throw away the other nine shots.  
> Because each shot's output is stored deterministically (`shot-04.png`, `shot-04.wav`) and keyed by a SHA-256 hash of its inputs (`pipeline/cache.py`), re-running the pipeline skips unchanged shots (`[cache] shot-01 already exists...`) and only calls the model for the modified shot, then re-assembles the final MP4s and appends one new entry to `runs.jsonl`.  
> Thanks for watching!"
