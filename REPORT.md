# Project Progress Report

**The Wisdom of Our Mothers (የእናቶቻችን ጥበብ)**

> This is an implementation progress report, not a final report on a completed
> film. No production media, audience results, or provider-call results are
> available to evaluate yet.

## Project goal

Create a fictional Ethiopian mother-and-child heritage short about Almaz and
Dawit. The planned film has ten shots containing 75 seconds of story, followed
by a three-second AI disclosure card. It will use Amharic narration, English
subtitles, a warm cinematic style, and 9:16 and 16:9 exports.

## Work completed

- The ten-shot storyboard and JSON Schema define the film contract. The
  validator checks project-specific rules and uses the optional `jsonschema`
  package for full schema validation when available.
- The Python foundation includes cache-aware provider calls, bounded retries,
  redacted JSONL run logging, provider interfaces, and a validation-gated
  reference/keyframe workflow.
- A lazy Gemini image adapter is implemented using Python's standard-library
  HTTP client. It supports prompt and reference-image inputs, validates PNG
  responses, avoids overwriting existing outputs, and maps rate limits and
  timeouts to retryable errors. It has only been tested with mocked HTTP.
- Offline assembly preflight and FFmpeg command builders cover narration-only
  radio, music ducking, loudness normalization, subtitles, a still-image
  pan/zoom fallback, the disclosure card, and both aspect ratios.
- Project documentation records architecture, design, ethics, costs,
  experiments, and failures without claiming unobserved results.

## Verification

The latest full local test run completed with **94 tests passing**. The
storyboard validator reports ten scenes, 75 seconds of story, and a three-second
end card (78 seconds total). These tests use mocked providers and media tools;
they do not establish that a real API call or video render works.

FFmpeg and ffprobe were not available on the checked laptop PATH. No system
software was installed, no AI models were run locally, and no provider API
request or media generation was performed.

## Not yet completed

- Verify Gemini image model availability, account access, pricing, quota, and
  applicable data terms before sending prompts or reference images.
- Generate and manually approve the character/style references and keyframes.
- Implement or select video, narration, and music providers; generate and review
  those assets only after their terms and costs are accepted.
- Have a fluent Amharic speaker review narration, subtitles, and pronunciation.
- Supply a licensed font with Amharic glyph coverage and perform real render
  checks.
- Render and inspect the radio cut and both final aspect ratios.
- Conduct both audience tests with at least three real, consenting participants
  each. No audience feedback is available yet.
- Complete the final film report, walkthrough video (five minutes or less), and
  public post after the relevant production and review work.

No measured API costs, model results, generation experiments, or audience
feedback are claimed in this report. For detailed pending work and evidence,
see [DESIGN.md](DESIGN.md), [COSTS.md](COSTS.md), [EXPERIMENTS.md](EXPERIMENTS.md),
[FAILURES.md](FAILURES.md), and [ETHICS.md](ETHICS.md).
