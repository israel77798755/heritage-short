# Costs and performance

This ledger records measured usage and the pricing basis for the actual project runs. Do not substitute estimates for measurements or assume a free tier is available. Verify the provider's current model, quota, and pricing terms at the time of any future call.

## Current evidence

The repository does not contain `runs.jsonl` or generated media, and no production-stage API or GPU call has been made by the project pipeline. Therefore there are currently no measured model latencies, GPU minutes, billed charges, or supported list-price equivalents to report.

## Stage ledger

| Stage | Candidate service | Calls recorded | Latency / GPU minutes | Billed cost | List-price equivalent |
|---|---|---:|---|---|---|
| Script and prompt assistance | Gemini API | None recorded | Not measured | Not measured | Not verified |
| Amharic narration | Gemini TTS | None recorded | Not measured | Not measured | Not verified |
| Keyframe images | Cloudflare Workers AI | None recorded | Not measured | Not measured | Not verified |
| Moving shots | Wan 2.2 on Kaggle/Colab | None recorded | GPU minutes not measured | Not measured | Not verified |
| Original music | ACE-Step on Kaggle/Colab | None recorded | GPU minutes not measured | Not measured | Not verified |
| FFmpeg assembly | Local or hosted CPU | Not run | Not measured | Not measured | Not applicable / not measured |

These are candidate stages and providers from the project plan, not completed runs or verified access.

## Public pricing reference (not project usage)

The official [Gemini 3.8 Flash TTS model page](https://ai.google.dev/gemini-api/docs/models/gemini-3.8-flash-tts), checked 2026-11-25, lists free-tier text and audio pricing as free of charge. It also lists standard paid pricing of $0.50 per million text input tokens and $9.00 per million audio output tokens through 2026-12-31, equivalent to $0.00225 per 10 seconds of generated audio. The listed rates change on 2027-01-01. This is a public reference only: no API request or charge has occurred, actual account quota is unverified, Amharic support is unverified, and paid use is not authorized.

## How to record a future run

For each real run, record:

- Provider, exact model/version, stage, shot, and run identifier.
- Call count, latency, retries, and cache hits.
- GPU minutes and runtime environment for hosted generation.
- Actual billed amount, currency, and source (provider usage record or invoice).
- A list-price equivalent only when the official price and calculation are documented; otherwise use `not verified`.

The run logger should write the per-call evidence to `runs.jsonl`; this document should summarize those records. Do not record API keys, authorization headers, or other credentials here or in the run log. Do not claim savings from caching until the inputs and avoided calls have been measured.
