# Ethics — The Wisdom of Our Mothers (የእናቶቻችን ጥበብ)

This document records the ethical commitments, consent status, licensing, and cultural considerations for this project. It is a living document updated as the project progresses.

**Status note (2026-11-25):** No production model calls or media generation have been recorded in the repository. Planned tools and stages below must not be read as completed work.

---

## 1. Fictional Characters

The film features two fictional characters:

| Character | Name | Description | Real person? |
|-----------|------|-------------|--------------|
| Mother | Almaz (አልማዝ) | Fictional Ethiopian mother in her early 40s | No |
| Child | Dawit (ዳዊት) | Fictional Ethiopian boy, around 9 years old | No |

Both characters are entirely invented for this project. No real person's likeness, face, or identity is used or referenced in the creation of these characters.

**Commitment:** If any future version of this project uses a real person's likeness, face, or voice, their informed written consent will be obtained and recorded in this document before any generation takes place.

---

## 2. Consent

### 2.1 Real-Person Consent Policy

This project will not use a real person's image, voice, or personal story without their informed, recorded consent. Consent means the person:

- Understands how their likeness or voice will be used.
- Agrees to the specific words or actions attributed to them.
- Knows the content is AI-generated.
- Can withdraw consent at any time before publication.

### 2.2 Current Consent Status

| Category | Status | Notes |
|----------|--------|-------|
| Character likenesses | ✅ Not needed | All characters are fictional |
| Real-person voice use or cloning | ✅ None used | No voice has been generated; a synthetic narration provider and voice have not been selected |
| Personal family stories | ✅ Not needed | The story is fictional and not based on a specific real family |
| Audience test participants | Not recruited; tests not conducted | Obtain voluntary informed consent before each session; no consent or feedback is claimed yet |

### 2.3 Audience Testing Consent

Before each audience test:

- Participants will be told the purpose of the test.
- Participation is voluntary.
- Feedback may be quoted anonymously in project documentation.
- No participant names or identifying information will be published without explicit permission.
- Feedback will be recorded honestly and never invented.

---

## 3. AI Disclosure

### 3.1 End Card

The final film includes a visible end card (approximately 3 seconds) with the following AI-generated content disclosure:

- **English:** "Created with AI tools for story, visuals, narration, and music."
- **Amharic:** "ይህ አጭር ፊልም በአርቲፊሻል ኢንተለጀንስ (AI) መሳሪያዎች ተዘጋጅቷል።"

This end card appears in both the vertical (9:16) and horizontal (16:9) exports.

### 3.2 Platform Disclosure

When the film is posted publicly, the platform's AI content disclosure label will be switched on (e.g., YouTube's AI-generated content flag, TikTok's AI label, Meta's AI disclosure).

### 3.3 Watermarks and Provenance

Where AI generation tools embed watermarks or provenance metadata (such as SynthID or C2PA), these will be left intact in the final exports. We will not strip or alter provenance metadata.

---

## 4. Copyright and Licensing

### 4.1 Policy

Every model, tool, and asset used in this project must have its license verified and documented before use. Only tools with licenses that permit our intended use (educational, non-commercial project) will be used.

### 4.2 Model and Tool Licenses

| Tool / Model | Purpose | License | Commercial use? | Status |
|---|---|---|---|---|
| Gemini 3.8 Flash | Script, prompts, translation | Google AI Terms of Service | Subject to ToS | ⏳ To verify before first API call |
| Gemini 3.8 Flash TTS | Possible narration candidate | Google AI Terms of Service | Subject to ToS | ⏳ Amharic support, service terms, and quota still need verification |
| FLUX.1 schnell / FLUX.2 klein 4B | Keyframe image generation | Apache 2.0 (4B variant) | Yes (Apache 2.0) | ⏳ To verify before first API call |
| Wan 2.2 TI2V-5B | Image-to-video generation | Apache 2.0 | Yes | ⏳ To verify before first use |
| ACE-Step 1.5 | Original music generation | MIT | Yes | ⏳ To verify before first use |
| FFmpeg | Video assembly, mixing, export | LGPL / GPL | Yes | ✅ Open source, widely used |
| jsonschema (Python) | Storyboard validation | MIT | Yes | ✅ Verified |
| python-dotenv | Environment variable loading | BSD-3-Clause | Yes | ✅ Verified |

### 4.3 Generated Output Terms

- No generated images, video, narration, or music are currently recorded in the repository, so no output ownership or output-license claim is made yet.
- No third-party copyrighted music, stock footage, or stock images have been added to the project so far.
- An original score using ACE-Step 1.5 is planned; no score has been generated or selected.
- Before using generated outputs, record the exact model/version, applicable service terms, and any required attribution or provenance.
- No font has been selected for the final export. Verify its license before use.
- Google’s [Gemini 3.8 Flash TTS model page](https://ai.google.dev/gemini-api/docs/models/gemini-3.8-flash-tts) lists free-tier text and audio pricing as free of charge, and marks free-tier content as used to improve Google products. Actual quota, Amharic support, and applicable terms have not been verified for this project. No Gemini request has been made; paid API use still requires explicit approval.

### 4.4 Fonts

| Font | Purpose | License | Status |
|------|---------|---------|--------|
| ⏳ To be selected | Subtitles and end card | ⏳ Pending | Will verify before use |

**Note:** Font licenses will be checked and recorded here before any font is used in the final exports.

---

## 5. Cultural Respect

### 5.1 Representation

This film portrays a fictional Ethiopian mother and child in an Ethiopian highland setting. The story communicates four universal lessons: trusting God, respecting others, never giving up, and remaining hopeful during difficult times.

### 5.2 Commitments

- Represent Ethiopian culture, clothing, food, architecture, and language with respect and care.
- Use authentic cultural elements (netela, jebena, mesob, injera, krar, washint) appropriately and in context.
- Avoid stereotypes, exaggeration, or caricature.
- Do not present fictional scenes as historical facts.
- Do not fabricate proverbs or attribute invented sayings to Ethiopian culture without clearly marking them as fictional.
- Narration is in Amharic and will be reviewed for accuracy and natural pronunciation.

### 5.3 Style Choices

- Visual prompts describe qualities (warm, cinematic, respectful) rather than naming living artists.
- No living artist's distinctive style is deliberately imitated.

---

## 6. Privacy and Security

### 6.1 API Keys and Secrets

- API keys are stored in a local `.env` file, which is listed in `.gitignore`.
- `.env.example` contains only placeholder values.
- The `pipeline/config.py` module loads keys from environment variables and never prints or logs their values.
- Every commit is checked for accidentally included secrets before pushing.

### 6.2 Personal Data

- No personal data (names, addresses, phone numbers, photos) of real people is stored in the repository.
- Audience test feedback is recorded anonymously unless explicit permission is given.
- No private family details are sent to AI services that may use inputs for model training.

---

## 7. Planned AI Use by Production Stage

The following table describes intended use, not completed calls or outputs.

| Stage | Intended AI use | Candidate tool(s) | Human role | Status |
|-------|------------------|------------------|------------|--------|
| Story and script | Possible drafting assistance | Gemini text model | Author reviews, edits, and approves narrative content | Planned; no model call recorded |
| Storyboard and prompts | Possible drafting assistance | Gemini text model | Author designs shot structure and reviews prompts | Planned; no model call recorded |
| Keyframe images | Generate reference and shot images | Hosted image model; candidate listed in Section 4.2 | Author selects, reviews, and approves each image | Planned; no images generated |
| Moving shots (video) | Animate approved keyframes | Wan 2.2 on Kaggle/Colab is a candidate | Author reviews each clip and decides keep/regenerate | Planned; no video generated |
| Narration | Generate Amharic narration | Gemini TTS is a candidate | Author and Amharic speaker review pronunciation and pacing | Planned; no narration generated |
| Music | Generate original score candidates | ACE-Step 1.5 on Kaggle/Colab is a candidate | Author listens to candidates and selects the best fit | Planned; no score generated |
| Video assembly | No generative model intended | FFmpeg | Author controls timing, mixing, subtitles, and export | Planned; no assembly performed |
| Subtitles | Possible translation assistance | Gemini text model, if selected | Author and Amharic speaker verify subtitle text | Planned; no subtitle review recorded |
| Validation and testing | No generative model intended | Python scripts | Automated checks with human review | Storyboard validation and unit tests exist |
| Documentation | No generative model intended | Written and reviewed by the author | Author verifies claims against repository evidence | In progress |

---

## 8. Audience Testing Ethics

### 8.1 Commitments

- All audience feedback is real and voluntary.
- We will never invent, fabricate, or exaggerate viewer responses.
- Participants are informed before the test that their feedback will be used in project documentation.
- Feedback is recorded as accurately as possible, including critical or negative comments.
- If a participant asks not to be quoted, their request is honored.

### 8.2 Testing Status

| Test | Participants | Status |
|------|-------------|--------|
| Radio cut (narration-only) test | At least 3 viewers | ⏳ Not yet conducted |
| Near-final cut test | At least 3 viewers | ⏳ Not yet conducted |

Results will be documented honestly in `DESIGN.md` when the tests are conducted.

---

## Document History

| Date | Change |
|------|--------|
| 2026-11-25 | Initial ethics document created with fictional characters, consent policy, AI disclosure plan, licensing table, cultural respect commitments, privacy rules, transparency matrix, and audience testing ethics. |
