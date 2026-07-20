# Troubleshooting

Load this reference only after a configuration or execution failure. Preserve `state.json`, approvals, provider IDs, request IDs, and paid originals before recovery.

| Symptom | Safe recovery |
| --- | --- |
| Credential validation fails | Check required variable names, region, bucket, workspace, and provider-specific watermark capability. Do not print secret values. |
| 429 before a task ID is known | Treat submission as unknown when the request may have reached the provider. Do not retry the mutation automatically. Recover by request/idempotency evidence or provider support. |
| `submission_unknown` | Locate the original task/video ID and add it through an audited recovery step. Resume that ID; never create another task automatically. |
| Paid approval is rejected | Rerun `plan`; compare provider, currency, amount, and all three SHA-256 values. Issue a new approval rather than editing state. |
| Signed OSS or result URL expired | Query/sign the same stored object key or original provider job again. Do not resubmit generation. |
| Provider reports failed | Preserve the error/request ID and paid original if any. Estimate the alternate provider and request a new approval. |
| Narration duration mismatch | Inspect `revision_required.json`; revise the listed script segments, run `plan` again, and obtain new exact script and estimate approvals. Reject final narration above 58 seconds. |
| Unresolved paid TTS intent | Preserve `.runtime/audio/intents/<segment-id>.json`; do not repeat the CosyVoice POST automatically. Confirm the provider result or clear it only through an audited manual recovery. |
| Subtitle drift | Rebuild captions from the final narration word timestamps; keep segment boundaries and the same narration hash. |
| Remotion render fails | Run fixture generation and `npm run typecheck`, confirm every `public/project` asset exists, then rerun `npm run render:test`. Do not alter the paid original. |
| Verification/audit rejects output | Read `.runtime/verification/verification.json` and inspect its contact sheet; fix composition or metadata locally. Do not hide provider watermarks or weaken capability checks. |
| Download interrupted | Resume download for the same completed job into a temporary sibling, validate it, then atomically replace the destination. |

For every resume path, poll or download the original stored job. A timeout, missing temporary URL, or local crash is not authority to resubmit a paid mutation.
