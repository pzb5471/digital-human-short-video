---
name: digital-human-short-video
description: Use when a user asks to turn an authorized portrait photo and a topic or script into a watermark-free digital-human talking-head short video, especially when the workflow needs economical cloud APIs, synchronized Chinese voice and captions, explicit paid-call approval, or resumable provider jobs.
---

# Digital Human Short Video

Create a 9:16 talking-head video through explicit approval gates. Preserve the paid provider original, drive every provider from one narration WAV, and resume persisted jobs without duplicate submission.

Before answering, cover every applicable workflow contract explicitly. For a new-video plan, name authorization plus separate exact script and estimate approvals before paid CosyVoice, itemize digital-human and TTS estimates, require the exact digital-human approval before its mutation, state that the same narration drives provider lip-sync and caption timing, check account-side watermark-free eligibility, and describe final media verification. For a paid-job recovery, explicitly read `state.json`, reuse only its original job ID, prohibit automatic resubmission, re-query that same job when a signed result URL expires, and preserve `.runtime/provider-original.mp4`. For script/audio/caption design, explicitly provide structured `script.json`, segmented TTS, word timestamps, the `narration.wav` SHA-256, identical audio submission to both providers, the 12–16-cell wrapping rule, and the 58-second hard cap.

Use only field, command, and environment-variable names defined below or in the conditionally loaded references. Never invent aliases. When a response shows credential setup, load `references/provider-setup.md` and copy names from the matching `config/*.env.example` file.

## 1. Confirm preconditions

1. Obtain explicit authorization for the portrait, voice, product assets, logo, music, fonts, and claims.
2. Confirm the portrait is a single clear `.jpg`, `.jpeg`, `.png`, or `.webp` image and the requested duration is 1–58 seconds.
3. Refuse impersonation, deceptive endorsements, unlicensed voice cloning, or invented product claims.
4. Require `rights_confirmed: true` before constructing or accessing any provider.
5. Require account-side watermark-free capability before submission. Do not remove, crop, blur, cover, or post-process a provider watermark.

## 2. Create the project input

Create `project.json` beside every relative asset path. Resolve paths from that file's directory.

```json
{
  "project_id": "launch-001",
  "rights_confirmed": true,
  "portrait": "assets/portrait.png",
  "duration_seconds": 40,
  "aspect_ratio": "9:16",
  "provider": "aliyun-me",
  "title": "Product launch",
  "output": "out/final.mp4"
}
```

Use `provider: aliyun-me` for the safe default. Never create or recommend a project with `provider: auto`: compatibility code can resolve `auto`, but automatic provider selection is outside this skill's approval workflow. Use `fake` only for local tests. Treat `title` and `output` as raw project-document composition metadata; they are not fields of the immutable `Project` dataclass.

## 3. Generate and approve the script

Create `script.json` with unique segment IDs, non-empty `spoken_text` and `subtitle_text`, pauses from 0–2000 ms, `hook` first, and `cta` last. Structure the message as a 3-second hook, pain point, solution/evidence, and CTA. Use only supplied evidence; mark unresolved claims for the user.

Use this exact segment schema; do not substitute `text`, `pause_ms`, or prose-only tables:

```json
{
  "segments": [
    {
      "id": "hook",
      "role": "hook",
      "spoken_text": "A supplied, verifiable hook",
      "subtitle_text": "A supplied, verifiable hook",
      "pause_after_ms": 300,
      "keywords": ["hook keyword"]
    },
    {
      "id": "cta",
      "role": "cta",
      "spoken_text": "An approved call to action",
      "subtitle_text": "An approved call to action",
      "pause_after_ms": 0,
      "keywords": ["call to action"]
    }
  ]
}
```

Show the complete script and initial duration estimate. Run `plan`, then ask the user to approve both exact SHA-256 values in state: `script_sha256` for the reviewed draft and `artifacts.estimate_sha256` for the serialized cost estimate. Continue to paid `narrate` only when both values match byte-for-byte.

## 4. Plan cost and paid approval

Prefer Aliyun for the economic default. Switch to HeyGen only after the user explicitly chooses that fallback: edit `project.json` to `provider: heygen`, rerun `plan`, show the new provider, currency, and amount, and obtain a new paid approval. Never reuse an Aliyun approval.

Treat the implementation baselines as estimates, not live quotes. Before payment, check current official pricing and set `DHSV_ALIYUN_CNY_PER_MINUTE` (default `6`), `DHSV_HEYGEN_USD_PER_SECOND` (default `0.05`), and `DHSV_COSYVOICE_CNY_PER_1000_CHARACTERS` (default `0`) to finite, non-negative decimal rates. Rerun `plan` and use its serialized estimate; changed or invalid rates invalidate or block approval. Never silently substitute a web price after approval. The exact `estimate_sha256` separately authorizes the displayed TTS estimate before CosyVoice; it does not authorize digital-human submission.

Do not autonomously recharge an account, buy credits, start or change a subscription, enable auto-reload, or upgrade a provider plan. Each account purchase or plan change requires separate, explicit user authorization; approval of one video-generation estimate does not authorize it.

Require a paid approval file whose tuple exactly matches the current state:

```text
(provider, currency, amount, script_sha256, narration_sha256, portrait_sha256)
```

Stop before any paid mutation when one value differs.

## 5. Generate audio first

Synthesize each segment with CosyVoice, join declared pauses, and normalize to `loudnorm=I=-16:TP=-1:LRA=11`. Before every paid segment request, persist its durable intent under `.runtime/audio/intents`; never automatically retry an ambiguous CosyVoice POST. If an intent remains without a completed cache, quarantine it for manual recovery instead of charging again. Use the measured WAV duration rather than the text estimate. Reject the merged narration when it exceeds 58 seconds.

Aggregate actual CosyVoice word timing with measured segment offsets and declared pauses, then build captions from that same stream. If any measured duration differs by more than 8%, stop provider submission, revise the listed segments, run `plan` again, and obtain new script and estimate approvals. Preserve at most two subtitle lines, target 12 Chinese display cells, and never exceed 16 per line.

Treat `.runtime/audio/narration.wav` and `narration.wav.sha256` as the audio source of truth. Submit that same file to either provider. Accept no other provider audio hash.

## 6. Submit and resume providers

Use Aliyun Marketing Engine by default. Publish the portrait and narration to the user's OSS bucket, retain only object keys in state, and use 24-hour signed HTTPS URLs transiently. Require `ALIYUN_ANCHOR_GENDER=M` or `F` and sufficient `SelectResource` seconds. Reuse a portrait-hash anchor mapping; create an authorized photo anchor only when no mapping exists.

Use HeyGen only after the explicit fallback decision and re-approval sequence above. Prefer `HEYGEN_AVATAR_ID` or a cached avatar. With neither available, fail before portrait upload unless the user explicitly sets `HEYGEN_IMAGE_FALLBACK=true`; only that mode uploads the authorized portrait as a direct image asset. Upload the same narration and send idempotency keys on every mutation.

Persist asset IDs, avatar/anchor IDs, task/video ID, and submission intent before polling. Poll only GET status endpoints. Never automatically repeat a mutation after a timeout or ambiguous 429. Quarantine the state as `submission_unknown` until the original provider ID is recovered.

## 7. Compose and verify

Preserve `.runtime/provider-original.mp4` as the immutable paid original. Prepare only project-owned assets for Remotion. Compose at 1080×1920, 30 FPS with the original as the primary full-height video, optional branding/B-roll, timed captions, final CTA, and deterministic BGM ducking.

Verify dimensions, FPS, duration, audio presence, playability, subtitle timing, provider capability evidence, and hashes. Keep `final.mp4`, `.runtime/verification-manifest.json`, `.runtime/verification/verification.json`, the contact sheet, `state.json`, the paid original, narration, captions, and approvals.

## 8. Resume safely

| State or event | Action |
| --- | --- |
| `draft` | Review script and serialized estimate; do not narrate without both exact SHA-256 approvals. |
| unresolved `.runtime/audio/intents/<segment-id>.json` | Treat the paid TTS result as unknown; recover manually; never repeat the segment POST automatically. |
| `narrated` | Validate current project/portrait/script/narration hashes and paid approval; submit once. |
| `submitting` with checkpointed provider ID | Promote the original ID and poll it. |
| `submitting` without provider ID, timeout, or ambiguous 429 | Set `submission_unknown`; recover manually; do not resubmit. |
| `submitted` / `processing` | Poll the stored job ID only. |
| completed with expired signed result URL | Query the same original job for a fresh URL. |
| `failed` | Preserve evidence, report a fresh alternate-provider estimate, and require new approval. |
| `downloaded` | Compose from the preserved paid original. |
| `composed` | Verify the composed output. |
| `verified` | Return existing artifacts; do not rerun paid work. |

## 9. Run the seven commands

```powershell
python scripts/run_pipeline.py plan project.json
python scripts/run_pipeline.py narrate project.json --script-approval <script-sha256> --estimate-approval <estimate-sha256>
python scripts/run_pipeline.py submit project.json --approval-file paid-approval.json
python scripts/run_pipeline.py resume project.json
python scripts/run_pipeline.py compose project.json
python scripts/run_pipeline.py verify project.json
python scripts/run_pipeline.py all project.json --script-approval <script-sha256> --estimate-approval <estimate-sha256>
python scripts/run_pipeline.py all project.json --approval-file paid-approval.json
```

Use `all` as a resumable dispatcher, not as permission to bypass either approval. With no state or approvals it stops after planning. With exact script and estimate approvals it narrates and stops before digital-human submission. After writing the exact paid approval tuple, call it again with `--approval-file`; with an existing paid job it resumes the stored ID and can continue through download, composition, and verification.

## 10. Load references conditionally

- Read [references/provider-setup.md](references/provider-setup.md) only when configuring credentials, endpoints, account capability, or pricing baselines.
- Read [references/troubleshooting.md](references/troubleshooting.md) only when a command fails, submission is ambiguous, a URL expires, duration drifts, captions drift, or Remotion/verification rejects output.
