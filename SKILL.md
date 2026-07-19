---
name: digital-human-short-video
description: Use when a user asks to turn an authorized portrait photo and a topic or script into a watermark-free digital-human talking-head short video, especially when the workflow needs economical cloud APIs, synchronized Chinese voice and captions, explicit paid-call approval, or resumable provider jobs.
---

# Digital Human Short Video

Create a 9:16 talking-head video through explicit approval gates. Preserve the paid provider original, drive every provider from one narration WAV, and resume persisted jobs without duplicate submission.

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
  "provider": "auto",
  "title": "Product launch",
  "output": "out/final.mp4"
}
```

Use `provider: auto` to select Aliyun only when its AK, SK, OSS endpoint, and bucket are available; otherwise select HeyGen only when `HEYGEN_API_KEY` is available. Use `fake` only for local tests.

## 3. Generate and approve the script

Create `script.json` with unique segment IDs, non-empty `spoken_text` and `subtitle_text`, pauses from 0–2000 ms, `hook` first, and `cta` last. Structure the message as a 3-second hook, pain point, solution/evidence, and CTA. Use only supplied evidence; mark unresolved claims for the user.

Show the complete script and initial duration estimate. Run `plan`, then ask the user to approve the exact SHA-256 printed in state. Continue to `narrate` only with that exact hash.

## 4. Plan cost and paid approval

Prefer Aliyun for the economic default. Use HeyGen only as an explicit fallback after reporting a new estimate and receiving a new approval.

Treat the implementation baselines—Aliyun `6 CNY/min`, HeyGen `0.05 USD/sec`, and the separately displayed CosyVoice billed-character line—as configurable estimates, not live quotes. Check current official pricing before payment, update the deployment's rate configuration, rerun `plan`, and use its serialized estimate. Never silently substitute a web price after approval.

Require a paid approval file whose tuple exactly matches the current state:

```text
(provider, currency, amount, script_sha256, narration_sha256, portrait_sha256)
```

Stop before any paid mutation when one value differs.

## 5. Generate audio first

Synthesize each segment with CosyVoice, join declared pauses, and normalize to `loudnorm=I=-16:TP=-1:LRA=11`. Use the measured WAV duration rather than the text estimate. Reject the merged narration when it exceeds 58 seconds.

Generate word timing and captions from the same segment stream. Revise only segments whose measured duration differs by more than 8%. Preserve at most two subtitle lines and 12–16 Chinese display cells per line.

Treat `.runtime/audio/narration.wav` and `narration.wav.sha256` as the audio source of truth. Submit that same file to either provider. Accept no other provider audio hash.

## 6. Submit and resume providers

Use Aliyun Marketing Engine by default. Publish the portrait and narration to the user's OSS bucket, retain only object keys in state, and use 24-hour signed HTTPS URLs transiently. Require sufficient `SelectResource` seconds. Reuse a portrait-hash anchor mapping; create an anchor only when no mapping exists.

Use HeyGen only after an explicit fallback decision. Upload the same portrait and narration, prefer a cached avatar, and use explicit image fallback only when configured. Send idempotency keys on every mutation.

Persist asset IDs, avatar/anchor IDs, task/video ID, and submission intent before polling. Poll only GET status endpoints. Never automatically repeat a mutation after a timeout or ambiguous 429. Quarantine the state as `submission_unknown` until the original provider ID is recovered.

## 7. Compose and verify

Preserve `.runtime/provider-original.mp4` as the immutable paid original. Prepare only project-owned assets for Remotion. Compose at 1080×1920, 30 FPS with the original as the primary full-height video, optional branding/B-roll, timed captions, final CTA, and deterministic BGM ducking.

Verify dimensions, FPS, duration, audio presence, playability, subtitle timing, provider capability evidence, and hashes. Keep `final.mp4`, `manifest.json`, `verify-report.json`, `state.json`, the paid original, narration, captions, and approvals.

## 8. Resume safely

| State or event | Action |
| --- | --- |
| `draft` | Review script and estimate; do not narrate without the script hash. |
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
python scripts/run_pipeline.py narrate project.json --script-approval <script-sha256>
python scripts/run_pipeline.py submit project.json --approval-file paid-approval.json
python scripts/run_pipeline.py resume project.json
python scripts/run_pipeline.py compose project.json
python scripts/run_pipeline.py verify project.json
python scripts/run_pipeline.py all project.json --script-approval <script-sha256> --approval-file paid-approval.json
```

Use `all` as a resumable dispatcher, not as permission to bypass either approval. Without an approval file it stops after planning; with an existing paid job it resumes the stored ID.

## 10. Load references conditionally

- Read [references/provider-setup.md](references/provider-setup.md) only when configuring credentials, endpoints, account capability, or pricing baselines.
- Read [references/troubleshooting.md](references/troubleshooting.md) only when a command fails, submission is ambiguous, a URL expires, duration drifts, captions drift, or Remotion/verification rejects output.
