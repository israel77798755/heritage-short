"""Cloud-only media generation script for GitHub Actions (zero API keys, zero spending).

Generates:
1. Character reference sheets + 10 scene keyframes via AI Horde (https://aihorde.net)
   using the documented anonymous key ``0000000000`` (free volunteer GPU cluster;
   AI Horde server software is AGPL-3.0-or-later, AI Horde claims no ownership over
   outputs, and generated-image terms follow the selected worker model's license,
   such as CreativeML OpenRAIL-M / OpenRAIL++).
2. Per-scene Amharic narration via edge-tts (am-ET-MekdesNeural, free) aligned to shot durations.
3. Original 78s instrumental score via pure-Python MIDI + FluidSynth (open-source).
4. English subtitles (en.srt) via pipeline.subtitles.

Every generation call is logged to runs.jsonl. Never creates fake media on failure.
HTTP 401/403 authentication errors fail immediately without pointless retries.
Supports resuming from cached images after a timeout or failed job.
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import json
import os
import struct
import subprocess
import time
import urllib.error
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

AI_HORDE_BASE = "https://aihorde.net/api/v2"
AI_HORDE_ANON_KEY = "0000000000"
AI_HORDE_CLIENT_AGENT = (
    "heritage-short:1.0:https://github.com/israel77798755/heritage-short"
)
DEFAULT_PER_IMAGE_TIMEOUT_SECONDS = 240.0
DEFAULT_OVERALL_VISUAL_TIMEOUT_SECONDS = 900.0
TTS_VOICE = "am-ET-MekdesNeural"
SOUNDFONT_PATH = Path("/usr/share/sounds/sf2/FluidR3_GM.sf2")


class ProviderAuthError(RuntimeError):
    """Raised immediately on HTTP 401/403 without retrying."""


class ProviderError(RuntimeError):
    """Raised when a remote media provider fails or times out."""


def _log_run(entry: dict[str, Any]) -> None:
    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        **entry,
    }
    with RUNS_JSONL_PATH.open("a", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def _http_json(
    url: str,
    *,
    method: str = "GET",
    payload: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    timeout: int = 60,
) -> dict[str, Any]:
    req_headers = {
        "Accept": "application/json",
        "User-Agent": AI_HORDE_CLIENT_AGENT,
        "Client-Agent": AI_HORDE_CLIENT_AGENT,
    }
    if headers:
        req_headers.update(headers)
    data = None
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        req_headers["Content-Type"] = "application/json"

    req = urllib.request.Request(url, data=data, headers=req_headers, method=method)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _http_bytes(url: str, *, timeout: int = 120) -> bytes:
    req = urllib.request.Request(
        url,
        headers={"User-Agent": AI_HORDE_CLIENT_AGENT},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def _raise_if_auth_error(exc: urllib.error.HTTPError, provider: str, label: str) -> None:
    if exc.code in (401, 403):
        raise ProviderAuthError(
            f"{provider} rejected request for {label} with HTTP {exc.code} "
            f"({exc.reason}). Authentication is required or the anonymous key is not "
            "accepted for this endpoint; aborting without retrying."
        ) from exc


def _retry_delay_for_http_error(exc: urllib.error.HTTPError, attempt: int) -> float:
    if exc.code == 429 and getattr(exc, "headers", None):
        retry_after = exc.headers.get("Retry-After")
        if retry_after and retry_after.isdigit():
            return float(min(int(retry_after), 60))
    return float(5 * attempt)


def _fetch_aihorde_image(
    prompt: str,
    seed: int,
    out_path: Path,
    label: str,
    *,
    poll_interval_seconds: float = 5.0,
    max_wait_seconds: float = DEFAULT_PER_IMAGE_TIMEOUT_SECONDS,
    overall_deadline: float | None = None,
    completed_count: int = 0,
    total_count: int = 1,
    max_submit_attempts: int = 3,
) -> bool:
    """Ensure out_path holds a generated PNG. Returns True if newly generated, False if cached."""
    if out_path.is_file() and out_path.stat().st_size > 10_000:
        print(f"[cache] {label} already exists at {out_path}")
        return False

    out_path.parent.mkdir(parents=True, exist_ok=True)
    # 512x512 @ 20 steps stays within AI Horde's zero-kudos anonymous tier limits.
    full_prompt = (
        f"{prompt} ### blurry, deformed, extra fingers, text, watermark, logo"
    )
    payload = {
        "prompt": full_prompt,
        "params": {
            "sampler_name": "k_euler_a",
            "width": 512,
            "height": 512,
            "steps": 20,
            "cfg_scale": 7.0,
            "seed": str(seed),
            "n": 1,
        },
        "nsfw": False,
        "censor_nsfw": True,
        "r2": True,
        "shared": False,
    }
    headers = {"apikey": AI_HORDE_ANON_KEY}
    remaining = max(0, total_count - completed_count)

    last_err: Exception | None = None
    for attempt in range(1, max_submit_attempts + 1):
        if overall_deadline is not None and time.monotonic() >= overall_deadline:
            msg = (
                f"Overall visual generation timeout exceeded before {label}: "
                f"{completed_count} of {total_count} images completed, "
                f"{remaining} remaining. Re-run to resume from cached images."
            )
            _log_run(
                {
                    "stage": "keyframes",
                    "target": label,
                    "provider": "aihorde.net",
                    "seed": seed,
                    "completed_images": completed_count,
                    "remaining_images": remaining,
                    "cost_usd": 0.0,
                    "status": "timeout",
                    "error": msg,
                }
            )
            raise ProviderError(msg)

        t0 = time.monotonic()
        try:
            submitted = _http_json(
                f"{AI_HORDE_BASE}/generate/async",
                method="POST",
                payload=payload,
                headers=headers,
                timeout=60,
            )
            job_id = submitted.get("id")
            if not job_id:
                raise ProviderError(
                    f"AI Horde did not return a generation job id for {label}: {submitted}"
                )

            per_image_deadline = time.monotonic() + max_wait_seconds
            effective_deadline = (
                min(per_image_deadline, overall_deadline)
                if overall_deadline is not None
                else per_image_deadline
            )

            while True:
                check = _http_json(
                    f"{AI_HORDE_BASE}/generate/check/{job_id}",
                    method="GET",
                    headers=headers,
                    timeout=30,
                )
                if check.get("faulted"):
                    raise ProviderError(
                        f"AI Horde job {job_id} faulted for {label} "
                        f"({completed_count} of {total_count} completed, {remaining} remaining): {check}"
                    )
                if check.get("done"):
                    break
                if check.get("is_possible") is False:
                    raise ProviderError(
                        f"AI Horde reported no available worker for {label} "
                        f"({completed_count} of {total_count} completed, {remaining} remaining): {check}"
                    )
                if time.monotonic() >= effective_deadline:
                    reason = (
                        "overall visual generation timeout"
                        if overall_deadline is not None
                        and overall_deadline <= per_image_deadline
                        and time.monotonic() >= overall_deadline
                        else f"per-image queue timeout ({max_wait_seconds}s)"
                    )
                    raise ProviderError(
                        f"AI Horde job {job_id} timed out ({reason}) for {label}: "
                        f"{completed_count} of {total_count} images completed, "
                        f"{remaining} remaining. Re-run to resume from cached images."
                    )
                time.sleep(poll_interval_seconds)

            status = _http_json(
                f"{AI_HORDE_BASE}/generate/status/{job_id}",
                method="GET",
                headers=headers,
                timeout=60,
            )
            generations = status.get("generations") or []
            if not generations:
                raise ProviderError(
                    f"AI Horde job {job_id} returned no generations for {label}"
                )
            gen0 = generations[0]
            img_ref = gen0.get("img", "")
            if not img_ref:
                raise ProviderError(
                    f"AI Horde generation missing image payload for {label}"
                )

            if img_ref.startswith("http://") or img_ref.startswith("https://"):
                raw_bytes = _http_bytes(img_ref, timeout=120)
            else:
                raw_bytes = base64.b64decode(img_ref)

            img = Image.open(BytesIO(raw_bytes))
            img.verify()
            img = Image.open(BytesIO(raw_bytes)).convert("RGB")
            tmp_path = out_path.with_suffix(".tmp.png")
            img.save(tmp_path, format="PNG")
            tmp_path.replace(out_path)

            selected_model = gen0.get("model", "unknown")
            latency = round(time.monotonic() - t0, 3)
            _log_run(
                {
                    "stage": "keyframes",
                    "target": label,
                    "provider": "aihorde.net",
                    "model": selected_model,
                    "worker_name": gen0.get("worker_name", "unknown"),
                    "seed": seed,
                    "width": 512,
                    "height": 512,
                    "latency_seconds": latency,
                    "cost_usd": 0.0,
                    "status": "ok",
                    "output": str(out_path),
                }
            )
            print(
                f"[image] Generated {label} with model '{selected_model}' "
                f"({latency}s, seed={seed})"
            )
            return True
        except urllib.error.HTTPError as exc:
            latency = round(time.monotonic() - t0, 3)
            _log_run(
                {
                    "stage": "keyframes",
                    "target": label,
                    "provider": "aihorde.net",
                    "model": "anonymous_worker",
                    "seed": seed,
                    "attempt": attempt,
                    "latency_seconds": latency,
                    "cost_usd": 0.0,
                    "status": "error",
                    "http_status": exc.code,
                    "error": f"HTTP {exc.code}: {exc.reason}",
                }
            )
            _raise_if_auth_error(exc, "aihorde.net", label)
            if exc.code == 429:
                last_err = ProviderError(
                    f"AI Horde rate limited request for {label} (HTTP 429: {exc.reason})."
                )
            elif exc.code == 503:
                last_err = ProviderError(
                    f"AI Horde service unavailable for {label} (HTTP 503: {exc.reason})."
                )
            else:
                last_err = exc
            print(f"[image] Attempt {attempt} failed for {label}: HTTP {exc.code}")
            if attempt < max_submit_attempts:
                time.sleep(_retry_delay_for_http_error(exc, attempt))
        except ProviderAuthError:
            raise
        except Exception as exc:
            last_err = exc
            latency = round(time.monotonic() - t0, 3)
            _log_run(
                {
                    "stage": "keyframes",
                    "target": label,
                    "provider": "aihorde.net",
                    "model": "anonymous_worker",
                    "seed": seed,
                    "attempt": attempt,
                    "latency_seconds": latency,
                    "cost_usd": 0.0,
                    "status": "error",
                    "error": str(exc)[:300],
                }
            )
            print(f"[image] Attempt {attempt} failed for {label}: {exc}")
            if "not available" in str(exc) or "faulted" in str(exc) or "timed out" in str(exc):
                break
            if attempt < max_submit_attempts:
                time.sleep(5 * attempt)

    raise ProviderError(
        f"Failed to generate {label} after {max_submit_attempts} attempts "
        f"({completed_count} of {total_count} completed, {remaining} remaining): {last_err}"
    )


def resolve_overall_visual_timeout(cli_value: float | None = None) -> float:
    """Resolve overall visual timeout from CLI flag, env var, or default (900s)."""
    if cli_value is not None:
        if cli_value <= 0:
            raise ValueError("Overall visual timeout must be positive.")
        return cli_value
    env_raw = os.environ.get("VISUAL_OVERALL_TIMEOUT_SECONDS", "").strip()
    if env_raw:
        value = float(env_raw)
        if value <= 0:
            raise ValueError("VISUAL_OVERALL_TIMEOUT_SECONDS must be positive.")
        return value
    return DEFAULT_OVERALL_VISUAL_TIMEOUT_SECONDS


def generate_visuals(
    storyboard: dict[str, Any],
    *,
    overall_timeout_seconds: float | None = None,
) -> dict[str, int]:
    """Generate character references then scene keyframes, resuming from cache."""
    refs_dir = OUTPUTS_DIR / "assets" / "references"
    keyframes_dir = OUTPUTS_DIR / "assets" / "keyframes"
    style = storyboard["visual_style"]["style_block"]
    mother_desc = storyboard["characters"]["mother"]["description"]
    child_desc = storyboard["characters"]["child"]["description"]

    timeout_seconds = resolve_overall_visual_timeout(overall_timeout_seconds)
    overall_deadline = time.monotonic() + timeout_seconds

    targets: list[tuple[str, int, Path, str]] = [
        (
            f"Character reference portrait of {mother_desc}. {style}",
            901,
            refs_dir / "mother_almaz.png",
            "ref-mother-almaz",
        ),
        (
            f"Character reference portrait of {child_desc}. {style}",
            902,
            refs_dir / "child_dawit.png",
            "ref-child-dawit",
        ),
    ]
    for scene in storyboard["scenes"]:
        num = scene["scene_number"]
        prompt = (
            f"{scene['image_prompt']} Consistent character look: "
            f"{mother_desc} {child_desc} {style}"
        )
        targets.append(
            (prompt, scene["seed"], keyframes_dir / f"shot-{num:02d}.png", f"shot-{num:02d}")
        )

    total_count = len(targets)
    completed_count = 0
    generated_count = 0
    cached_count = 0

    for prompt, seed, out_path, label in targets:
        was_generated = _fetch_aihorde_image(
            prompt=prompt,
            seed=seed,
            out_path=out_path,
            label=label,
            overall_deadline=overall_deadline,
            completed_count=completed_count,
            total_count=total_count,
        )
        completed_count += 1
        if was_generated:
            generated_count += 1
        else:
            cached_count += 1

    return {
        "total": total_count,
        "completed": completed_count,
        "generated": generated_count,
        "cached": cached_count,
    }


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
    bpm = storyboard["music"]["tempo_bpm"]
    tpq = 480
    us_per_beat = int(60_000_000 / bpm)
    beats_total = int(total_sec * bpm / 60) + 2

    tempo_events: list[tuple[int, bytes]] = [
        (0, b"\xff\x51\x03" + us_per_beat.to_bytes(3, "big")),
    ]

    chords = [
        (50, 53, 57),  # Dm
        (46, 53, 58),  # Bb
        (45, 53, 60),  # F/A
        (48, 52, 55),  # C
    ]
    melody_notes = [62, 65, 69, 67, 65, 62, 60, 62, 65, 69, 72, 69]

    t1: list[tuple[int, bytes]] = [(0, bytes([0xC0, 24]))]
    t2: list[tuple[int, bytes]] = [(0, bytes([0xC1, 0]))]
    t3: list[tuple[int, bytes]] = [(0, bytes([0xC2, 48]))]
    t4: list[tuple[int, bytes]] = [(0, bytes([0xC3, 73]))]

    for beat in range(beats_total):
        bar = beat // 4
        chord = chords[bar % len(chords)]
        tick = beat * tpq

        for sub in range(2):
            note = chord[(beat * 2 + sub) % len(chord)] + 12
            st = tick + sub * (tpq // 2)
            t1.append((st, bytes([0x90, note, 62])))
            t1.append((st + int(tpq * 0.45), bytes([0x80, note, 0])))

        if beat % 4 == 0:
            dur = tpq * 4 - 20
            for n in chord:
                t2.append((tick, bytes([0x91, n, 52])))
                t2.append((tick + dur, bytes([0x81, n, 0])))
                t3.append((tick, bytes([0x92, n, 44])))
                t3.append((tick + dur, bytes([0x82, n, 0])))

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


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Cloud media generation for Heritage Short.")
    parser.add_argument(
        "--visual-timeout",
        type=float,
        default=None,
        help="Overall timeout in seconds for visual generation (default: VISUAL_OVERALL_TIMEOUT_SECONDS or 900).",
    )
    args = parser.parse_args(argv)

    storyboard = require_valid_storyboard(STORYBOARD_PATH, SCHEMA_PATH)
    OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
    generate_visuals(storyboard, overall_timeout_seconds=args.visual_timeout)
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
