"""Cloud-only media generation script for GitHub Actions (zero API keys, zero spending).

Generates:
1. Character reference sheets + 10 scene keyframes via Pollinations.ai (FLUX, free tier).
2. Per-scene Amharic narration via edge-tts (am-ET-MekdesNeural, free) aligned to shot durations.
3. Original 78s instrumental score via pure-Python MIDI + FluidSynth (open-source).
4. English subtitles (en.srt) via pipeline.subtitles.

Every generation call is logged to runs.jsonl. Never creates fake media on failure.
"""

from __future__ import annotations

import asyncio
import json
import struct
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from typing import Any

import edge_tts
from PIL import Image

from pipeline.config import OUTPUTS_DIR, RUNS_JSONL_PATH, SCHEMA_PATH, STORYBOARD_PATH
from pipeline.subtitles import write_english_srt
from validate_storyboard import require_valid_storyboard

POLLINATIONS_BASE = "https://gen.pollinations.ai/image"
TTS_VOICE = "am-ET-MekdesNeural"
SOUNDFONT_PATH = Path("/usr/share/sounds/sf2/FluidR3_GM.sf2")


def _log_run(entry: dict[str, Any]) -> None:
    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        **entry,
    }
    with RUNS_JSONL_PATH.open("a", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def _fetch_pollinations_image(prompt: str, seed: int, out_path: Path, label: str) -> None:
    if out_path.is_file() and out_path.stat().st_size > 10_000:
        print(f"[cache] {label} already exists at {out_path}")
        return

    out_path.parent.mkdir(parents=True, exist_ok=True)
    encoded = urllib.parse.quote(prompt, safe="")
    url = (
        f"{POLLINATIONS_BASE}/{encoded}"
        f"?model=flux&width=1024&height=1024&seed={seed}&nologo=true"
    )

    last_err: Exception | None = None
    for attempt in range(1, 5):
        t0 = time.monotonic()
        try:
            req = urllib.request.Request(
                url,
                headers={"User-Agent": "heritage-short-cloud-pipeline/1.0"},
            )
            with urllib.request.urlopen(req, timeout=120) as resp:
                data = resp.read()
            img = Image.open(BytesIO(data))
            img.verify()
            img = Image.open(BytesIO(data)).convert("RGB")
            img.save(out_path, format="PNG")
            latency = round(time.monotonic() - t0, 3)
            _log_run(
                {
                    "stage": "keyframes",
                    "target": label,
                    "provider": "pollinations.ai",
                    "model": "flux",
                    "seed": seed,
                    "width": 1024,
                    "height": 1024,
                    "latency_seconds": latency,
                    "cost_usd": 0.0,
                    "status": "ok",
                    "output": str(out_path),
                }
            )
            print(f"[image] Generated {label} ({latency}s, seed={seed})")
            time.sleep(2.0)  # gentle pacing for public endpoint
            return
        except Exception as exc:
            last_err = exc
            latency = round(time.monotonic() - t0, 3)
            _log_run(
                {
                    "stage": "keyframes",
                    "target": label,
                    "provider": "pollinations.ai",
                    "model": "flux",
                    "seed": seed,
                    "attempt": attempt,
                    "latency_seconds": latency,
                    "cost_usd": 0.0,
                    "status": "error",
                    "error": str(exc)[:300],
                }
            )
            print(f"[image] Attempt {attempt} failed for {label}: {exc}")
            time.sleep(5 * attempt)

    raise RuntimeError(f"Failed to generate {label} after 4 attempts: {last_err}")


def generate_visuals(storyboard: dict[str, Any]) -> None:
    refs_dir = OUTPUTS_DIR / "assets" / "references"
    keyframes_dir = OUTPUTS_DIR / "assets" / "keyframes"
    style = storyboard["visual_style"]["style_block"]
    mother_desc = storyboard["characters"]["mother"]["description"]
    child_desc = storyboard["characters"]["child"]["description"]

    _fetch_pollinations_image(
        f"Character reference portrait of {mother_desc}. {style}",
        seed=901,
        out_path=refs_dir / "mother_almaz.png",
        label="ref-mother-almaz",
    )
    _fetch_pollinations_image(
        f"Character reference portrait of {child_desc}. {style}",
        seed=902,
        out_path=refs_dir / "child_dawit.png",
        label="ref-child-dawit",
    )

    for scene in storyboard["scenes"]:
        num = scene["scene_number"]
        prompt = f"{scene['image_prompt']} Consistent character look: {mother_desc} {child_desc} {style}"
        _fetch_pollinations_image(
            prompt=prompt,
            seed=scene["seed"],
            out_path=keyframes_dir / f"shot-{num:02d}.png",
            label=f"shot-{num:02d}",
        )


async def _tts_scene(text: str, out_mp3: Path) -> None:
    communicate = edge_tts.Communicate(text=text, voice=TTS_VOICE, rate="-5%")
    await communicate.save(str(out_mp3))


def generate_narration(storyboard: dict[str, Any]) -> Path:
    audio_dir = OUTPUTS_DIR / "audio"
    clips_dir = audio_dir / "narration_clips"
    clips_dir.mkdir(parents=True, exist_ok=True)
    aligned_wavs: list[Path] = []

    for scene in storyboard["scenes"]:
        num = scene["scene_number"]
        dur = scene["duration_seconds"]
        mp3_path = clips_dir / f"shot-{num:02d}.mp3"
        wav_path = clips_dir / f"shot-{num:02d}.wav"

        t0 = time.monotonic()
        asyncio.run(_tts_scene(scene["narration"], mp3_path))
        latency = round(time.monotonic() - t0, 3)

        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-i",
                str(mp3_path),
                "-af",
                f"aresample=48000,aformat=channel_layouts=stereo,apad=whole_dur={dur},atrim=duration={dur}",
                "-c:a",
                "pcm_s16le",
                str(wav_path),
            ],
            check=True,
            capture_output=True,
        )
        aligned_wavs.append(wav_path)
        _log_run(
            {
                "stage": "narration",
                "target": f"shot-{num:02d}",
                "provider": "edge-tts",
                "model": TTS_VOICE,
                "duration_seconds": dur,
                "latency_seconds": latency,
                "cost_usd": 0.0,
                "status": "ok",
                "output": str(wav_path),
            }
        )
        print(f"[tts] Generated Amharic narration shot-{num:02d} ({latency}s, slot={dur}s)")

    end_dur = storyboard["end_card"]["duration_seconds"]
    end_silence = clips_dir / "end_silence.wav"
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "anullsrc=r=48000:cl=stereo",
            "-t",
            str(end_dur),
            "-c:a",
            "pcm_s16le",
            str(end_silence),
        ],
        check=True,
        capture_output=True,
    )
    aligned_wavs.append(end_silence)

    concat_list = clips_dir / "concat.txt"
    concat_list.write_text(
        "\n".join(f"file '{p.resolve().as_posix()}'" for p in aligned_wavs) + "\n",
        encoding="utf-8",
    )
    narration_wav = audio_dir / "narration.wav"
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(concat_list),
            "-c:a",
            "pcm_s16le",
            str(narration_wav),
        ],
        check=True,
        capture_output=True,
    )
    return narration_wav


def _varlen(val: int) -> bytes:
    buf = [val & 0x7F]
    val >>= 7
    while val:
        buf.append((val & 0x7F) | 0x80)
        val >>= 7
    return bytes(reversed(buf))


def _midi_track(events: list[tuple[int, bytes]]) -> bytes:
    events_sorted = sorted(events, key=lambda x: x[0])
    data = bytearray()
    last_t = 0
    for t, ev in events_sorted:
        delta = max(0, t - last_t)
        last_t = t
        data.extend(_varlen(delta))
        data.extend(ev)
    data.extend(b"\x00\xff\x2f\x00")
    return b"MTrk" + struct.pack(">I", len(data)) + bytes(data)


def generate_music(storyboard: dict[str, Any]) -> Path:
    audio_dir = OUTPUTS_DIR / "audio"
    audio_dir.mkdir(parents=True, exist_ok=True)
    mid_path = audio_dir / "score.mid"
    wav_path = audio_dir / "music.wav"

    total_sec = (
        sum(s["duration_seconds"] for s in storyboard["scenes"])
        + storyboard["end_card"]["duration_seconds"]
        + 2
    )
    bpm = storyboard["music"]["tempo_bpm"]  # 72 BPM
    tpq = 480
    us_per_beat = int(60_000_000 / bpm)
    beats_total = int(total_sec * bpm / 60) + 2

    # Tempo track
    tempo_events: list[tuple[int, bytes]] = [
        (0, b"\xff\x51\x03" + us_per_beat.to_bytes(3, "big")),
    ]

    # D minor pentatonic / Tizita-inspired warm progression: Dm -> Bb -> F -> C -> Dm -> F
    chords = [
        (50, 53, 57),  # Dm
        (46, 53, 58),  # Bb
        (45, 53, 60),  # F/A
        (48, 52, 55),  # C
    ]
    melody_notes = [62, 65, 69, 67, 65, 62, 60, 62, 65, 69, 72, 69]

    # Track 1: Nylon Guitar / Krar-like pluck (prog 24), Ch 0
    t1: list[tuple[int, bytes]] = [(0, bytes([0xC0, 24]))]
    # Track 2: Felt Acoustic Piano (prog 0), Ch 1
    t2: list[tuple[int, bytes]] = [(0, bytes([0xC1, 0]))]
    # Track 3: Warm Strings / Cello pad (prog 48), Ch 2
    t3: list[tuple[int, bytes]] = [(0, bytes([0xC2, 48]))]
    # Track 4: Airy Flute / Washint texture (prog 73), Ch 3
    t4: list[tuple[int, bytes]] = [(0, bytes([0xC3, 73]))]

    for beat in range(beats_total):
        bar = beat // 4
        chord = chords[bar % len(chords)]
        tick = beat * tpq

        # Gentle arpeggiated krar/guitar every half-beat
        for sub in range(2):
            note = chord[(beat * 2 + sub) % len(chord)] + 12
            st = tick + sub * (tpq // 2)
            t1.append((st, bytes([0x90, note, 62])))
            t1.append((st + int(tpq * 0.45), bytes([0x80, note, 0])))

        # Piano + string pad at start of each 4-beat bar
        if beat % 4 == 0:
            dur = tpq * 4 - 20
            for n in chord:
                t2.append((tick, bytes([0x91, n, 52])))
                t2.append((tick + dur, bytes([0x81, n, 0])))
                t3.append((tick, bytes([0x92, n, 44])))
                t3.append((tick + dur, bytes([0x82, n, 0])))

        # Expressive flute phrase every 2 beats in second half & opening
        if beat % 2 == 0 and (bar % 2 == 0):
            fn = melody_notes[(beat // 2) % len(melody_notes)]
            t4.append((tick, bytes([0x93, fn, 50])))
            t4.append((tick + int(tpq * 1.6), bytes([0x83, fn, 0])))

    header = b"MThd" + struct.pack(">IHHH", 6, 1, 5, tpq)
    midi_bytes = (
        header
        + _midi_track(tempo_events)
        + _midi_track(t1)
        + _midi_track(t2)
        + _midi_track(t3)
        + _midi_track(t4)
    )
    mid_path.write_bytes(midi_bytes)

    t0 = time.monotonic()
    subprocess.run(
        [
            "fluidsynth",
            "-ni",
            str(SOUNDFONT_PATH),
            str(mid_path),
            "-F",
            str(wav_path),
            "-r",
            "48000",
        ],
        check=True,
        capture_output=True,
    )
    latency = round(time.monotonic() - t0, 3)
    _log_run(
        {
            "stage": "music",
            "target": "original_score",
            "provider": "fluidsynth",
            "model": "FluidR3_GM_midi_score",
            "tempo_bpm": bpm,
            "key": storyboard["music"]["key"],
            "latency_seconds": latency,
            "cost_usd": 0.0,
            "status": "ok",
            "output": str(wav_path),
        }
    )
    print(f"[music] Rendered original instrumental score ({latency}s)")
    return wav_path


def main() -> None:
    storyboard = require_valid_storyboard(STORYBOARD_PATH, SCHEMA_PATH)
    OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
    generate_visuals(storyboard)
    generate_narration(storyboard)
    generate_music(storyboard)
    srt_path = write_english_srt(
        OUTPUTS_DIR / "subtitles" / "en.srt",
        storyboard_path=STORYBOARD_PATH,
        schema_path=SCHEMA_PATH,
    )
    print(f"[subtitles] Wrote {srt_path}")


if __name__ == "__main__":
    main()
