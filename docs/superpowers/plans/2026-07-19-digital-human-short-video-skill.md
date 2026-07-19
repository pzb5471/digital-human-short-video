# Digital Human Short Video Skill Implementation Plan

> **For Codex:** REQUIRED EXECUTION METHOD: Use `superpowers:subagent-driven-development` or `superpowers:executing-plans` to implement this plan task-by-task.

**Goal:** 创建一个可安装、可测试、可恢复的 `digital-human-short-video` Codex Skill，用用户已授权的人像照片生成无平台水印的竖屏数字人口播短视频；默认走阿里云营销引擎，备用走 HeyGen，配音使用 CosyVoice，同一条最终旁白驱动口型与字幕，任何付费调用前必须确认成本。

**Architecture:** Codex 负责创作并确认结构化脚本；Python 管线负责项目校验、成本计算、CosyVoice 分段配音、字幕时间轴、服务商调用、状态持久化和媒体验证；Remotion 模板负责 1080×1920 品牌包装。所有外部依赖都通过可注入客户端封装，测试默认使用假 HTTP/SDK 客户端和本地 FFmpeg 素材，真实收费测试必须显式启用。

**Tech Stack:** Python 3.11+、`requests`、Alibaba Cloud IntelligentCreation Python SDK、`oss2`、标准库 `unittest`、Node.js 24、React 19、Remotion 4.0.367、TypeScript 5.9.3、FFmpeg/ffprobe 7。

**Approved specification:** `docs/superpowers/specs/2026-07-19-digital-human-short-video-design.md`

## Execution rules

- 每个任务严格按 RED → GREEN → REFACTOR → VERIFY 执行；测试未先失败时不得写对应实现。
- 不运行真实付费接口，除非 `RUN_PAID_API_TESTS=1`、凭证齐全、使用已授权人像、时长不超过 10 秒，并在该次调用前再次得到用户对具体金额的确认。
- 不把密钥、临时签名 URL、授权照片、原始 API 响应或本地生成物提交到 Git。
- 服务商任务创建成功后立即原子写入 `state.json`；进程恢复只能轮询原任务，不得自动重提或换服务商。
- 每完成一个任务运行列出的验证命令并创建小提交。

## Environment setup

在 PowerShell 中使用工作区自带 Python：

```powershell
$skillPython = 'C:\Users\panzubin\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
$skillRoot = 'D:\test\mouth\digital-human-short-video'
& $skillPython --version
node --version
npm --version
ffmpeg -version
```

预期：Python 3.11+、Node 24.x、npm 11.x、FFmpeg 7.x。系统 `python.exe` 在当前机器不可用，计划中的所有 Python 命令都使用 `$skillPython`。

---

## Task 1: Capture the RED skill baseline

**Files:**

- Create: `docs/superpowers/evals/digital-human-short-video-baseline.md`
- Create: `docs/superpowers/evals/digital-human-short-video-scenarios.json`

**Step 1: Write three pressure scenarios**

`digital-human-short-video-scenarios.json` 使用以下完整内容：

```json
{
  "skill": "digital-human-short-video",
  "scenarios": [
    {
      "id": "new-30s-video",
      "prompt": "用户提供了一张已授权的单人人像和产品卖点，要求生成30秒、9:16、经济适用、无平台水印的数字人口播短视频。请给出完整执行方案、产物和具体命令。",
      "must_include": ["授权确认", "脚本确认", "逐项成本估算", "付费前确认", "同一旁白驱动口型和字幕", "无水印资格检查", "最终媒体验证"]
    },
    {
      "id": "resume-paid-job",
      "prompt": "阿里云数字人付费任务已经提交，已有 task_id，但执行进程中断。请继续完成视频，且不能重复扣费。",
      "must_include": ["读取state.json", "复用原task_id", "禁止自动重提", "临时URL过期时重新查询原任务", "保留付费原片"]
    },
    {
      "id": "script-voice-captions",
      "prompt": "为45秒中文数字人口播视频设计脚本、配音和逐词高亮字幕，要求阿里云与HeyGen切换时音色、时长和字幕不变。",
      "must_include": ["结构化script.json", "分段TTS", "词级时间戳", "narration.wav哈希", "同一音频提交两个服务商", "12到16字换行", "58秒硬限制"]
    }
  ]
}
```

**Step 2: Run scenarios without the skill**

依照 `superpowers:writing-skills`，同时派发三个隔离子代理，每个代理只收到一个 prompt，不得看到设计文档或未来的 `SKILL.md`。把答复原文、遗漏项和是否通过逐项记录到 baseline Markdown。

**Step 3: Verify baseline is RED**

```powershell
Select-String -Path 'docs\superpowers\evals\digital-human-short-video-baseline.md' -Pattern 'FAIL|遗漏'
```

预期：至少一个场景遗漏付费确认、任务恢复、统一音频或无水印资格检查；若三个场景都满分，增加“429 后任务是否创建未知”的压力条件并重跑。

**Step 4: Commit**

```powershell
git add docs/superpowers/evals
git commit -m "test: capture digital human skill baseline"
```

---

## Task 2: Scaffold the skill and lock metadata/dependencies

**Files:**

- Create: `digital-human-short-video/SKILL.md` (scaffold only)
- Create: `digital-human-short-video/agents/openai.yaml`
- Create: `digital-human-short-video/requirements.txt`
- Create: `digital-human-short-video/scripts/`
- Create: `digital-human-short-video/references/`
- Create: `digital-human-short-video/config/`
- Create: `digital-human-short-video/template/`
- Create: `digital-human-short-video/tests/`
- Create: `.gitignore`

**Step 1: Scaffold with the official helper**

```powershell
& $skillPython 'C:\Users\panzubin\.codex\skills\.system\skill-creator\scripts\init_skill.py' digital-human-short-video --path 'D:\test\mouth' --resources scripts,references
```

Do not hand-create the scaffold. Remove only generated example files that are irrelevant; retain the required frontmatter.

**Step 2: Add dependency lock**

`requirements.txt`:

```text
alibabacloud-intelligentcreation20240313==2.18.2
oss2>=2.19,<3
requests>=2.32,<3
```

The IntelligentCreation version matches the current public Python package checked during planning. Keep `requests` and `oss2` on compatible major-version ranges so the skill is not locked to an obsolete patch.

**Step 3: Protect secrets and generated media**

`.gitignore`:

```gitignore
.env
*.env
!*.env.example
**/__pycache__/
**/*.pyc
**/node_modules/
**/out/
**/.runtime/
**/state.json
**/*.wav
**/*.mp4
**/*.webm
**/*.png
!digital-human-short-video/assets/*.png
```

**Step 4: Generate UI metadata**

```powershell
& $skillPython 'C:\Users\panzubin\.codex\skills\.system\skill-creator\scripts\generate_openai_yaml.py' $skillRoot --interface 'display_name=数字人口播短视频' --interface 'short_description=使用已授权人像和云端API生成无平台水印数字人口播短视频' --interface 'brand_color=#1677FF' --interface 'default_prompt=使用 $digital-human-short-video 将已授权人像和口播主题制作成无水印竖屏短视频，并在付费 API 调用前先估算成本和确认。'
```

Verify `agents/openai.yaml` quotes every string and sets `policy.allow_implicit_invocation: true`. Do not add MCP dependencies because the workflow uses direct APIs and local scripts.

**Step 5: Install dependencies into a local virtual environment**

```powershell
& $skillPython -m venv 'D:\test\mouth\.venv'
& 'D:\test\mouth\.venv\Scripts\python.exe' -m pip install -r 'digital-human-short-video\requirements.txt'
```

**Step 6: Commit**

```powershell
git add .gitignore digital-human-short-video
git commit -m "build: scaffold digital human video skill"
```

---

## Task 3: Implement project contracts, authorization gate, pricing, and state

**Files:**

- Create: `digital-human-short-video/scripts/dhsv/__init__.py`
- Create: `digital-human-short-video/scripts/dhsv/models.py`
- Create: `digital-human-short-video/scripts/dhsv/project.py`
- Create: `digital-human-short-video/scripts/dhsv/state.py`
- Create: `digital-human-short-video/scripts/dhsv/security.py`
- Create: `digital-human-short-video/scripts/validate_project.py`
- Create: `digital-human-short-video/scripts/estimate_cost.py`
- Create: `digital-human-short-video/config/project.example.json`
- Test: `digital-human-short-video/tests/test_project.py`
- Test: `digital-human-short-video/tests/test_state.py`

**Step 1: Write failing contract tests**

Cover these exact cases with `unittest` and `tempfile.TemporaryDirectory`:

1. `rights_confirmed: false` raises `ProjectValidationError` before any provider object is constructed.
2. Missing portrait, unsupported extension, duration `0`, `59`, or aspect ratio other than `9:16` fail.
3. Valid `provider: auto` resolves to `aliyun-me` only when all required Aliyun variables are present; otherwise resolves to HeyGen only when `HEYGEN_API_KEY` is present; otherwise returns a credential error.
4. Cost for 40 seconds at Aliyun default `6 CNY/min` is `4.00 CNY`; HeyGen at `0.05 USD/sec` is `2.00 USD`; CosyVoice cost uses billed character count and is displayed separately.
5. Paid approval is accepted only when provider, currency, amount, script SHA-256, and narration SHA-256 exactly match the current estimate.
6. `StateStore.save()` writes to a temporary sibling and `os.replace()`s the destination; a restored state containing `job_id` is never considered submit-ready.
7. `redact()` masks API keys, AK/SK, bearer tokens, query signatures, and OSS signed URLs.

Run RED:

```powershell
& 'D:\test\mouth\.venv\Scripts\python.exe' -m unittest discover -s 'digital-human-short-video\tests' -p 'test_project.py'
& 'D:\test\mouth\.venv\Scripts\python.exe' -m unittest discover -s 'digital-human-short-video\tests' -p 'test_state.py'
```

Expected: imports fail because implementation does not exist.

**Step 2: Implement immutable contracts**

Use dataclasses/enums for:

```python
ProviderName = Literal["auto", "aliyun-me", "heygen", "fake"]
JobPhase = Literal["draft", "approved", "narrated", "submitted", "processing", "completed", "downloaded", "composed", "verified", "failed"]

@dataclass(frozen=True)
class CostLine:
    service: str
    currency: str
    amount: Decimal
    basis: str

@dataclass(frozen=True)
class PaidApproval:
    provider: str
    currency: str
    amount: Decimal
    script_sha256: str
    narration_sha256: str

@dataclass(frozen=True)
class JobState:
    project_id: str
    provider: str
    phase: str
    job_id: str | None
    idempotency_key: str
    script_sha256: str
    narration_sha256: str
    expected_cost: str
    created_at: str
    updated_at: str
```

`project.py` must resolve all relative paths against the directory containing `project.json`, never against the current working directory. Do not store environment values in dataclasses; store only boolean capability checks and public endpoint names.

**Step 3: Implement CLI wrappers**

```powershell
& 'D:\test\mouth\.venv\Scripts\python.exe' 'digital-human-short-video\scripts\validate_project.py' 'digital-human-short-video\config\project.example.json'
& 'D:\test\mouth\.venv\Scripts\python.exe' 'digital-human-short-video\scripts\estimate_cost.py' 'digital-human-short-video\config\project.example.json' --script 'digital-human-short-video\tests\fixtures\script.json'
```

Both commands print JSON to stdout; validation errors go to stderr and return exit code 2. Cost output must include `estimate_only: true` and `requires_confirmation: true`.

**Step 4: Run GREEN and commit**

```powershell
& 'D:\test\mouth\.venv\Scripts\python.exe' -m unittest discover -s 'digital-human-short-video\tests' -p 'test_project.py'
& 'D:\test\mouth\.venv\Scripts\python.exe' -m unittest discover -s 'digital-human-short-video\tests' -p 'test_state.py'
git add digital-human-short-video
git commit -m "feat: add project validation cost gate and state"
```

---

## Task 4: Implement script validation and caption generation

**Files:**

- Create: `digital-human-short-video/scripts/dhsv/script.py`
- Create: `digital-human-short-video/scripts/dhsv/captions.py`
- Create: `digital-human-short-video/scripts/build_captions.py`
- Create: `digital-human-short-video/tests/fixtures/script.json`
- Test: `digital-human-short-video/tests/test_script.py`
- Test: `digital-human-short-video/tests/test_captions.py`

**Step 1: Write failing tests**

Test the approved `script.json` schema and these invariants:

- segment IDs are unique; `spoken_text` and `subtitle_text` are non-empty; `pause_after_ms` is 0–2000;
- the first segment is `hook`, the last is `cta`, and the initial length estimate does not exceed 58 seconds;
- timestamps are monotonic, segment offsets include pauses, and a missing word-timestamp stream falls back to punctuation/character-weight allocation;
- captions wrap at 12–16 Chinese display cells, never exceed two lines, and do not split ASCII words or numbers;
- SRT uses `HH:MM:SS,mmm`; ASS escapes braces and includes a safe-area style; `captions.json` marks keyword spans.

RED command:

```powershell
& 'D:\test\mouth\.venv\Scripts\python.exe' -m unittest discover -s 'digital-human-short-video\tests' -p 'test_script.py'
& 'D:\test\mouth\.venv\Scripts\python.exe' -m unittest discover -s 'digital-human-short-video\tests' -p 'test_captions.py'
```

**Step 2: Implement deterministic conversion**

The agent writes `script.json`; code validates and converts it but never calls another LLM. Define the caption output contract:

```json
{
  "version": 1,
  "duration_ms": 40000,
  "cues": [
    {
      "id": "hook-000",
      "start_ms": 0,
      "end_ms": 1350,
      "lines": ["还在重复处理", "同样的工作？"],
      "words": [{"text": "重复工作", "start_ms": 420, "end_ms": 980, "highlight": true}]
    }
  ]
}
```

The fallback duration weight is 1 per CJK character, 0.55 per punctuation mark, and 0.7 per ASCII display cell, normalized to the measured segment duration. Keep exact segment start/end boundaries even if word timestamps are absent.

**Step 3: Verify CLI outputs and commit**

```powershell
& 'D:\test\mouth\.venv\Scripts\python.exe' 'digital-human-short-video\scripts\build_captions.py' --script 'digital-human-short-video\tests\fixtures\script.json' --timestamps 'digital-human-short-video\tests\fixtures\timestamps.json' --out-dir 'digital-human-short-video\.runtime\caption-test'
& 'D:\test\mouth\.venv\Scripts\python.exe' -m unittest discover -s 'digital-human-short-video\tests' -p 'test_captions.py'
git add digital-human-short-video
git commit -m "feat: add script contract and synchronized captions"
```

---

## Task 5: Implement CosyVoice segmented narration and audio normalization

**Files:**

- Create: `digital-human-short-video/scripts/dhsv/http.py`
- Create: `digital-human-short-video/scripts/dhsv/cosyvoice.py`
- Create: `digital-human-short-video/scripts/dhsv/media.py`
- Create: `digital-human-short-video/scripts/dhsv/narration.py`
- Create: `digital-human-short-video/scripts/generate_narration.py`
- Test: `digital-human-short-video/tests/test_cosyvoice.py`
- Test: `digital-human-short-video/tests/test_narration.py`

**Step 1: Write failing tests with fake HTTP and fake FFmpeg runners**

Required tests:

- request URL is `{DASHSCOPE_WORKSPACE_ID}.cn-beijing.maas.aliyuncs.com/api/v1/services/audio/tts/SpeechSynthesizer` unless `DASHSCOPE_TTS_ENDPOINT` overrides it;
- request uses `cosyvoice-v3.5-flash`, `longanyang`, WAV 24 kHz, `word_timestamp_enabled: true`, `enable_aigc_tag: false`;
- SSE events merge ordered base64 chunks and retain `sentence.words` timestamps;
- each script segment is synthesized once and cached by a SHA-256 of model, voice, rate, spoken text, and seed;
- FFmpeg concat includes generated silence for `pause_after_ms`, then normalizes with `loudnorm=I=-16:TP=-1:LRA=11`;
- final duration over 58 seconds fails before provider submission; deviation over 8% produces `revision_required.json` naming only affected segments;
- `narration.wav.sha256` equals the actual file hash and is the only permitted audio hash in provider requests.

**Step 2: Implement the client and audio-first pipeline**

Use `requests.Session` with timeouts `(10, 120)`. Retry GET and pre-task TTS requests on 429/5xx with bounded exponential backoff. Never retry a provider mutation unless an idempotency key guarantees replay.

Write every segment under `.runtime/audio/segments/<segment-id>.wav`, every timestamp stream under `.runtime/audio/timestamps/<segment-id>.json`, and the merged result as `.runtime/audio/narration.wav`. Write hashes with atomic replacement.

**Step 3: Run tests and a local synthetic-audio check**

```powershell
& 'D:\test\mouth\.venv\Scripts\python.exe' -m unittest discover -s 'digital-human-short-video\tests' -p 'test_cosyvoice.py'
& 'D:\test\mouth\.venv\Scripts\python.exe' -m unittest discover -s 'digital-human-short-video\tests' -p 'test_narration.py'
ffprobe -v error -show_entries format=duration -of json 'digital-human-short-video\.runtime\audio\narration.wav'
git add digital-human-short-video
git commit -m "feat: add CosyVoice narration pipeline"
```

---

## Task 6: Implement provider adapters and asset publishing

**Files:**

- Create: `digital-human-short-video/scripts/dhsv/providers/__init__.py`
- Create: `digital-human-short-video/scripts/dhsv/providers/base.py`
- Create: `digital-human-short-video/scripts/dhsv/providers/oss_assets.py`
- Create: `digital-human-short-video/scripts/dhsv/providers/aliyun_me.py`
- Create: `digital-human-short-video/scripts/dhsv/providers/heygen.py`
- Create: `digital-human-short-video/scripts/dhsv/providers/fake.py`
- Test: `digital-human-short-video/tests/test_aliyun_me.py`
- Test: `digital-human-short-video/tests/test_heygen.py`
- Test: `digital-human-short-video/tests/test_provider_contract.py`

**Step 1: Define and test the provider protocol**

All providers implement:

```python
class DigitalHumanProvider(Protocol):
    name: str
    def validate_credentials(self) -> CapabilityReport: ...
    def estimate_cost(self, request: VideoRequest) -> CostLine: ...
    def create_or_reuse_avatar(self, request: VideoRequest, state: JobState) -> AvatarRef: ...
    def submit_video(self, request: VideoRequest, avatar: AvatarRef, idempotency_key: str) -> SubmittedJob: ...
    def get_status(self, job_id: str) -> ProviderStatus: ...
    def download_result(self, job_id: str, destination: Path) -> DownloadedAsset: ...
```

Contract tests run identical state and retry scenarios against `FakeProvider`, fake Aliyun SDK, and fake HeyGen HTTP session.

**Step 2: Implement OSS publisher for Aliyun**

Require `ALIBABA_CLOUD_ACCESS_KEY_ID`, `ALIBABA_CLOUD_ACCESS_KEY_SECRET`, `ALIYUN_OSS_ENDPOINT`, and `ALIYUN_OSS_BUCKET`. Upload portrait and `narration.wav` to a project-scoped random object key, return a signed HTTPS GET URL valid for 24 hours, and never log its query string. The state file stores the object key, not the signed URL.

**Step 3: Implement Aliyun Marketing Engine adapter**

Create the SDK client with endpoint `intelligentcreation.cn-zhangjiakou.aliyuncs.com`. Use injected SDK client factories in tests. Build requests with the official SDK models using `.from_map()` and snake_case client calls.

Submission invariants:

- `scaleType: 9:16`, `subtitleTag: 0`, `transparentBackground: 0`;
- one ANCHOR layer and no WATERMARK layer;
- `videoScript.type: AUDIO` and `videoScript.audioUrl` points to the published final narration;
- returned `taskId` is persisted before any polling;
- `SelectResource` must report enough remaining seconds before approval can be used;
- `CreateAnchor` is called only when no portrait-hash-to-anchor mapping is present.

**Step 4: Implement HeyGen adapter**

Use `POST /v3/assets` multipart for local portrait and audio. Prefer a cached `avatar_id`; otherwise create a photo avatar with an asset reference, and support one-off `type: image` as an explicit configuration fallback. Submit `POST /v3/videos` with:

```json
{
  "type": "avatar",
  "avatar_id": "cached-or-created-id",
  "title": "project title",
  "resolution": "1080p",
  "aspect_ratio": "9:16",
  "fit": "contain",
  "audio_asset_id": "uploaded-narration-id",
  "output_format": "mp4"
}
```

Do not send `script`, `voice_id`, or custom `watermark`. Send `Idempotency-Key` on asset, avatar, and video mutations and persist each returned ID. Poll only `GET /v3/videos/{video_id}`.

**Step 5: Verify payloads, no duplicate submission, and commit**

```powershell
& 'D:\test\mouth\.venv\Scripts\python.exe' -m unittest discover -s 'digital-human-short-video\tests' -p 'test_*provider*.py'
& 'D:\test\mouth\.venv\Scripts\python.exe' -m unittest discover -s 'digital-human-short-video\tests' -p 'test_aliyun_me.py'
& 'D:\test\mouth\.venv\Scripts\python.exe' -m unittest discover -s 'digital-human-short-video\tests' -p 'test_heygen.py'
git add digital-human-short-video
git commit -m "feat: add Aliyun and HeyGen digital human adapters"
```

---

## Task 7: Build the resumable pipeline and explicit paid-call gate

**Files:**

- Create: `digital-human-short-video/scripts/dhsv/pipeline.py`
- Create: `digital-human-short-video/scripts/run_pipeline.py`
- Test: `digital-human-short-video/tests/test_pipeline.py`

**Step 1: Write failing orchestration tests**

Test these exact transitions:

- `plan` validates inputs and produces `script-draft.json` plus cost estimate without calling TTS or a digital-human provider;
- `narrate` requires a script approval hash and produces audio/captions without creating a digital-human task;
- `submit` requires an exact paid approval, writes `phase=submitted` with `job_id`, then returns;
- calling `submit` again with the same state polls rather than submits;
- a network timeout after mutation with unknown creation status moves to `submission_unknown` and stops for manual resolution;
- `resume` on completed job refreshes an expired result URL through the original job ID and downloads once;
- provider failure reports the alternate provider and a new estimate but never invokes it automatically;
- local composition failures preserve the downloaded provider original.

**Step 2: Implement CLI subcommands**

```text
run_pipeline.py plan PROJECT
run_pipeline.py narrate PROJECT --script-approval SHA256
run_pipeline.py submit PROJECT --approval-file paid-approval.json
run_pipeline.py resume PROJECT
run_pipeline.py compose PROJECT
run_pipeline.py verify PROJECT
run_pipeline.py all PROJECT --script-approval SHA256 --approval-file paid-approval.json
```

`all` must stop after the estimate when approval is absent. It must never prompt hidden input inside automation; Codex presents the estimate to the user, writes the approved tuple to a local ignored file, then resumes.

**Step 3: Run tests and commit**

```powershell
& 'D:\test\mouth\.venv\Scripts\python.exe' -m unittest discover -s 'digital-human-short-video\tests' -p 'test_pipeline.py'
git add digital-human-short-video
git commit -m "feat: add resumable paid-safe pipeline"
```

---

## Task 8: Create the Remotion vertical-video template

**Files:**

- Create: `digital-human-short-video/template/package.json`
- Create: `digital-human-short-video/template/tsconfig.json`
- Create: `digital-human-short-video/template/remotion.config.ts`
- Create: `digital-human-short-video/template/src/index.ts`
- Create: `digital-human-short-video/template/src/Root.tsx`
- Create: `digital-human-short-video/template/src/Video.tsx`
- Create: `digital-human-short-video/template/src/types.ts`
- Create: `digital-human-short-video/template/src/Captions.tsx`
- Create: `digital-human-short-video/template/src/theme.ts`
- Create: `digital-human-short-video/template/src/fixtures.ts`
- Create: `digital-human-short-video/scripts/prepare_remotion.py`
- Test: `digital-human-short-video/tests/test_prepare_remotion.py`

**Step 1: Lock versions copied from the reference project's working Remotion stack**

`package.json`:

```json
{
  "name": "digital-human-short-video-template",
  "version": "1.0.0",
  "private": true,
  "scripts": {
    "dev": "remotion studio src/index.ts",
    "typecheck": "tsc --noEmit",
    "render:test": "remotion render src/index.ts DigitalHumanShortVideo out/test.mp4 --props=src/fixture-props.json --codec=h264 --pixel-format=yuv420p --concurrency=2"
  },
  "dependencies": {
    "@remotion/google-fonts": "4.0.367",
    "@remotion/transitions": "4.0.367",
    "react": "19.2.0",
    "react-dom": "19.2.0",
    "remotion": "4.0.367"
  },
  "devDependencies": {
    "@remotion/cli": "4.0.367",
    "@types/react": "19.2.2",
    "typescript": "5.9.3"
  }
}
```

**Step 2: Write failing preparation tests**

Test that `prepare_remotion.py` copies only project-owned assets into `template/public/project`, writes paths relative to `public`, calculates frame counts from millisecond timestamps with `ceil(ms * 30 / 1000)`, and rejects any path escaping the project root.

**Step 3: Implement the composition**

The composition is fixed at 1080×1920, 30 FPS. It renders:

- the paid digital-human original as the full-height primary video;
- a 3-second hook title, optional logo/brand background, timed B-roll/product cards, and final CTA;
- captions in the lower safe area, maximum two lines, with word-level keyword highlight based on current frame;
- optional BGM at low volume with deterministic ducking while narration is active;
- no provider watermark asset and no post-processing intended to remove a watermark.

Use `Video`, `Audio`, `Sequence`, `AbsoluteFill`, `interpolate`, and `spring` from Remotion. Avoid runtime font downloads in the test render; default to `Microsoft YaHei, Noto Sans SC, sans-serif`.

**Step 4: Install, typecheck, render, and commit**

```powershell
Set-Location 'D:\test\mouth\digital-human-short-video\template'
npm install
npm run typecheck
npm run render:test
Set-Location 'D:\test\mouth'
git add digital-human-short-video
git commit -m "feat: add Remotion talking-head composition"
```

---

## Task 9: Add media verification and no-paid end-to-end test

**Files:**

- Create: `digital-human-short-video/scripts/dhsv/verify.py`
- Create: `digital-human-short-video/scripts/verify_video.py`
- Create: `digital-human-short-video/scripts/make_test_fixture.py`
- Create: `digital-human-short-video/tests/test_verify.py`
- Create: `digital-human-short-video/tests/test_e2e_fake.py`

**Step 1: Write failing verification tests**

Generate a 6-second local H.264/AAC portrait fixture with FFmpeg. Verify pass/fail for:

- width 1080, height 1920, 30 FPS, H.264 video and AAC audio;
- duration within 250 ms of captions and narration;
- audio stream present and no silence interval longer than configured threshold;
- black-frame ratio below 0.5%;
- contact sheet contains first frame, hook midpoint, body midpoint, CTA start, and last frame;
- manifest states the provider capability was checked for no-platform-watermark output.

Watermark absence is not claimed from an unreliable computer-vision heuristic. It is enforced by provider/account capability checks, omission of watermark layers, and a required contact-sheet visual review.

**Step 2: Implement `verify_video.py`**

Use `ffprobe -of json`, FFmpeg `blackdetect`, `silencedetect`, and five extracted PNG frames. Emit `verification.json` with individual checks and nonzero exit code if a machine-verifiable check fails. Print the contact-sheet path for agent visual inspection.

**Step 3: Run fake-provider end to end**

```powershell
& 'D:\test\mouth\.venv\Scripts\python.exe' 'digital-human-short-video\scripts\make_test_fixture.py' --out 'digital-human-short-video\.runtime\e2e'
& 'D:\test\mouth\.venv\Scripts\python.exe' -m unittest discover -s 'digital-human-short-video\tests' -p 'test_verify.py'
& 'D:\test\mouth\.venv\Scripts\python.exe' -m unittest discover -s 'digital-human-short-video\tests' -p 'test_e2e_fake.py'
git add digital-human-short-video
git commit -m "test: add fake end-to-end video verification"
```

---

## Task 10: Author the skill instructions and provider references

**Files:**

- Modify: `digital-human-short-video/SKILL.md`
- Create: `digital-human-short-video/references/provider-setup.md`
- Create: `digital-human-short-video/references/troubleshooting.md`
- Create: `digital-human-short-video/config/aliyun.env.example`
- Create: `digital-human-short-video/config/heygen.env.example`

**Step 1: Write the complete `SKILL.md` after the baseline exists**

Frontmatter:

```yaml
---
name: digital-human-short-video
description: Use when a user asks to turn an authorized portrait photo and a topic or script into a watermark-free digital-human talking-head short video, especially when the workflow needs economical cloud APIs, synchronized Chinese voice and captions, explicit paid-call approval, or resumable provider jobs.
---
```

The body must be imperative and under 500 lines. Include, in this order:

1. Preconditions: authorization confirmation, supported portrait, no impersonation, no watermark-removal workaround.
2. Required inputs and `project.json` creation.
3. Script generation contract: 3-second hook, pain point, solution/evidence, CTA; no invented claims; show script for approval.
4. Cost plan: provider routing, current configurable rates, TTS line item, exact paid-approval tuple.
5. Audio-first execution: segmented CosyVoice, real duration, captions, 58-second cap, single narration hash.
6. Provider submission: default Aliyun, explicit HeyGen fallback, state persistence, no duplicate charges.
7. Remotion composition and verification.
8. Resume/failure decision table.
9. Commands for each pipeline subcommand.
10. References loaded only when configuring credentials or troubleshooting.

**Step 2: Document environment variables without values**

Aliyun example names:

```text
ALIBABA_CLOUD_ACCESS_KEY_ID=
ALIBABA_CLOUD_ACCESS_KEY_SECRET=
ALIYUN_OSS_ENDPOINT=https://oss-cn-zhangjiakou.aliyuncs.com
ALIYUN_OSS_BUCKET=
DASHSCOPE_API_KEY=
DASHSCOPE_WORKSPACE_ID=
```

HeyGen example:

```text
HEYGEN_API_KEY=
```

`provider-setup.md` links to official provider, TTS, pricing, and SDK pages and explains account-side no-watermark eligibility. `troubleshooting.md` maps credential failures, 429, unknown submission, audit rejection, expired signed URL, Remotion failure, duration mismatch, and subtitle drift to safe recovery actions.

**Step 3: Validate structure and scan secrets**

```powershell
& $skillPython 'C:\Users\panzubin\.codex\skills\.system\skill-creator\scripts\quick_validate.py' $skillRoot
rg -n --hidden -g '!**/node_modules/**' -g '!**/.git/**' '(sk-[A-Za-z0-9]|Bearer\s+[A-Za-z0-9]|AccessKeySecret\s*[:=]\s*[^\s]+|x-api-key\s*[:=]\s*[^<\s]+)' 'digital-human-short-video'
```

Expected: validation passes; secret scan finds only documentation placeholders or test assertions.

**Step 4: Commit**

```powershell
git add digital-human-short-video
git commit -m "docs: complete digital human video skill workflow"
```

---

## Task 11: Run GREEN skill evaluations and final verification

**Files:**

- Create: `docs/superpowers/evals/digital-human-short-video-after.md`
- Modify as needed: `digital-human-short-video/SKILL.md`
- Modify as needed: implementation files exposed by evaluation failures

**Step 1: Re-run the same three scenarios with the skill loaded**

Dispatch fresh isolated subagents with the exact prompts from Task 1 plus the completed skill. Record verbatim answers and score every `must_include` item. Do not coach agents beyond providing the skill.

**Step 2: Close every evaluation gap**

For each failure, first add a regression test or explicit skill pressure rule, confirm RED, make the smallest change, rerun the affected scenario, then record GREEN evidence. A scenario is complete only when all listed safety and workflow behaviors appear without extra prompting.

**Step 3: Run the full local suite**

```powershell
& 'D:\test\mouth\.venv\Scripts\python.exe' -m unittest discover -s 'digital-human-short-video\tests' -p 'test_*.py'
& $skillPython 'C:\Users\panzubin\.codex\skills\.system\skill-creator\scripts\quick_validate.py' $skillRoot
Set-Location 'D:\test\mouth\digital-human-short-video\template'
npm run typecheck
npm run render:test
Set-Location 'D:\test\mouth'
& 'D:\test\mouth\.venv\Scripts\python.exe' 'digital-human-short-video\scripts\verify_video.py' 'digital-human-short-video\template\out\test.mp4' --captions 'digital-human-short-video\template\src\fixture-props.json'
git status --short
```

Expected:

- every Python test passes without real credentials;
- `quick_validate.py` succeeds;
- TypeScript is clean and Remotion creates an MP4;
- verification reports 1080×1920, 30 FPS, H.264/AAC, audio present, no black-frame violation;
- only intended tracked files appear in Git status.

**Step 4: Optional real paid smoke test**

Do not run by default. If the user explicitly requests it, verify all four gates and show the exact expected charge before submission:

```powershell
$env:RUN_PAID_API_TESTS = '1'
& 'D:\test\mouth\.venv\Scripts\python.exe' 'digital-human-short-video\scripts\run_pipeline.py' all 'PATH_TO_APPROVED_10_SECOND_PROJECT' --script-approval 'EXACT_SCRIPT_SHA256' --approval-file 'PATH_TO_LOCAL_IGNORED_APPROVAL_JSON'
```

After completion, clear the session variable and never commit the paid-test project.

**Step 5: Final review and commit**

Apply `superpowers:verification-before-completion` and `superpowers:requesting-code-review`. Address high- and medium-severity findings, rerun affected tests, then commit:

```powershell
git add digital-human-short-video docs/superpowers/evals
git commit -m "feat: deliver digital human short video skill"
```

## Plan self-review

- Scope matches the approved design: authorized portrait, cloud API, economical default, HeyGen fallback, no platform watermark, no local GPU.
- Script, voice, captions, and provider lip-sync share one audio-first timeline and one narration hash.
- Paid mutations are separated from planning/narration, require exact approval, persist IDs immediately, and cannot auto-switch providers.
- Alibaba integration uses the official IntelligentCreation SDK endpoint and a user-owned OSS bucket for local portrait/audio publication.
- HeyGen uses uploaded assets, idempotency keys, 9:16/1080p output, and prerecorded audio rather than provider-side TTS.
- All core behavior is testable with fake clients; real paid smoke tests are opt-in and limited to 10 seconds.
- Remotion versions match the reference repository and are pinned as one compatible set.
- Automated verification does not overclaim watermark detection; account eligibility, payload construction, and human contact-sheet review jointly enforce the requirement.
- No placeholder implementation language remains; every task identifies files, tests, commands, expected outcomes, and commit boundaries.
