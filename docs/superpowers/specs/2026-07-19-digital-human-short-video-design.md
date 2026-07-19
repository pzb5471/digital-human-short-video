# 数字人口播短视频 Skill 设计规格

日期：2026-07-19

## 1. 目标

创建一个可复用的 `digital-human-short-video` Skill。用户提供已获授权的人像照片、口播主题或文案及可选品牌素材后，Skill 先生成结构化脚本、配音和字幕时间轴，再用同一条最终音频驱动云端数字人 API 生成无平台水印的口播原片，最后使用 Remotion 与 FFmpeg 合成为可直接发布的竖屏短视频。

默认成片规格为 1080×1920、30 FPS、H.264 视频与 AAC 音频，默认时长为 30–45 秒。交付物包括 MP4 成片、口播稿、字幕、成本记录、任务状态和可重新渲染的 Remotion 工程。

## 2. 范围

### 包含

- 已授权单人人像照片驱动的数字人口播。
- 阿里云营销引擎照片数字人 API，作为默认服务商。
- HeyGen Photo Avatar API，作为备用服务商。
- 阿里云百炼 CosyVoice API，负责可复用配音和词级时间戳。
- 3 秒钩子、核心内容、行动号召结构的短视频脚本。
- 动态字幕、SRT/ASS、品牌背景、产品图片或 B-roll、标题、Logo、背景音乐和 CTA。
- API 成本预估、付费确认、异步任务恢复、下载与成片验证。
- 9:16 竖屏模板；架构允许以后增加其他画幅与服务商。

### 不包含

- 未经授权的人像、名人仿冒或规避平台审核。
- 实时互动数字人或直播推流。
- 首版 D-ID 适配器。
- 训练定制数字人模型、声音克隆或自动购买 API 套餐。
- 通过裁切、遮挡或后期修补移除平台水印。

## 3. 已确认约束

- 使用云端 API，不依赖本地 GPU。
- 人像由用户上传，且用户必须明确确认已获得使用授权。
- 正式成片不得包含平台水印。
- 经济适用优先，同时保留更高表现力的备用服务商。
- 任何付费 API 调用前必须显示预计费用并取得确认。
- 已产生费用的任务失败后不得自动跨服务商重新提交。

## 4. 服务商决策

### 默认：阿里云营销引擎

选择理由：支持自定义照片数字人、9:16 与 16:9、文本或音频脚本以及可选水印；国内网络、中文语音和人民币结算更适合默认场景。当前官方价目列出 2D 数字人视频生产 100 分钟资源包为 600 元。

接入成本：需要阿里云账号、AK/SK、RAM 授权、服务开通和法务协议。适配器必须在提交前检查凭证和无水印能力。

参考：

- [阿里云营销引擎计费](https://help.aliyun.com/zh/me/product-overview/billing-description)
- [数字人离线合成 OpenAPI](https://help.aliyun.com/zh/me/getting-started/digital-human-offline-synthesis-openapi)

### 备用：HeyGen Photo Avatar

选择理由：单张照片即可创建数字人，API 接口简洁，支持异步生成与 1080p 输出，适合低频使用、海外环境或更重视人物表现力的项目。

当前官方开发者定价中 Photo Avatar 起价为每秒 0.05 美元，即每分钟 3 美元；API 按量付费最低充值 5 美元。适配器必须确认当前账户输出不带平台水印。

参考：

- [HeyGen Photo Avatar API](https://developers.heygen.com/photo-avatar)
- [HeyGen 开发者定价](https://developers.heygen.com/)

### 暂不实现：D-ID

D-ID Scale 年付折算的单位成本较低，并允许使用自定义标识或留空，但需要较高年度承诺。首版保持服务商接口可扩展，不实现 D-ID 代码。

参考：[D-ID API 定价](https://www.d-id.com/pricing/api/)

## 5. 架构

系统分为两个生成阶段：

1. 数字人 API 阶段：验证输入与授权，生成口播稿和字幕节拍，估算费用，创建或复用照片数字人，提交异步任务并下载数字人口播原片。
2. 本地合成阶段：将原片、字幕、产品素材和品牌配置写入 Remotion 工程，渲染成片，再由 FFmpeg/ffprobe 做规格、音画和抽帧验证。

服务商适配器暴露统一能力：

- `validate_credentials()`：验证凭证及账户能力。
- `estimate_cost(request)`：返回币种、预计费用和计费依据。
- `create_or_reuse_avatar(portrait)`：创建或复用照片数字人。
- `submit_video(request)`：提交视频合成任务。
- `get_status(job_id)`：查询异步任务状态。
- `download_result(job_id, destination)`：下载结果并保存校验信息。

首版不要求两个服务商的内部字段完全一致。统一接口只表达工作流需要的最小语义，服务商特有字段保存在各自配置中。

## 6. 目录结构

```text
digital-human-short-video/
├── SKILL.md
├── agents/
│   └── openai.yaml
├── scripts/
│   ├── run_pipeline.py
│   ├── validate_project.py
│   ├── estimate_cost.py
│   ├── generate_narration.py
│   ├── build_captions.py
│   ├── verify_video.py
│   └── providers/
│       ├── base.py
│       ├── aliyun_me.py
│       └── heygen.py
├── references/
│   ├── provider-setup.md
│   └── troubleshooting.md
├── config/
│   ├── aliyun.env.example
│   ├── heygen.env.example
│   └── project.example.json
├── template/
│   ├── package.json
│   ├── remotion.config.ts
│   └── src/
└── tests/
```

真实密钥不得出现在示例、项目配置、日志、测试夹具或 Git 中。

## 7. 项目输入契约

每个项目使用一个 `project.json` 作为唯一配置源，至少包含：

```json
{
  "title": "产品口播短视频",
  "provider": "auto",
  "portrait": "assets/presenter.jpg",
  "rights_confirmed": true,
  "topic": "产品主题或已完成文案",
  "audience": "目标受众",
  "selling_points": ["卖点一", "卖点二"],
  "cta": "立即了解更多",
  "duration_seconds": 40,
  "aspect_ratio": "9:16",
  "voice": {},
  "brand": {},
  "assets": [],
  "output": "out/final.mp4"
}
```

`rights_confirmed` 不等同于保存身份证明或授权文件。Skill 只记录用户已明确确认，不收集额外敏感资料。

## 8. 脚本、配音与字幕设计

### 8.1 结构化口播脚本

脚本默认由正在执行 Skill 的 Codex 直接生成，不额外调用文案生成 API。输入包括目标受众、卖点、语气、目标时长、品牌限制和 CTA，输出 `script.json`：

```json
{
  "target_seconds": 40,
  "segments": [
    {
      "id": "hook",
      "spoken_text": "每天都在重复处理同样的工作？",
      "subtitle_text": "还在重复处理同样的工作？",
      "keywords": ["重复工作"],
      "visual": "数字人近景，标题快速出现",
      "pause_after_ms": 180
    }
  ]
}
```

`spoken_text` 为配音文本，可使用适合朗读的数字、缩写、多音字和停顿写法；`subtitle_text` 为屏幕文案，可以更短，但不得改变原意。脚本结构默认为 3 秒钩子、痛点、解决方案、证据或卖点、CTA。

初稿按约 3.5 个汉字/秒估算长度。该数值只用于控制初稿，最终时长必须以 TTS 生成后的真实音频为准。脚本不得编造数据、价格、承诺或案例；缺乏证据时使用定性表达。生成脚本后先让用户确认内容和预计总费用，再进行配音与数字人付费调用。

### 8.2 分段配音

默认使用阿里云百炼 `cosyvoice-v3.5-flash` 公共音色。每个脚本段落单独生成音频并请求词级时间戳，然后按 `pause_after_ms` 添加停顿并合并为 `narration.wav`。

处理规则：

1. 生成 `hook.wav`、`body-01.wav`、`cta.wav` 等分段音频。
2. 使用 FFmpeg/ffprobe 测量每段真实时长。
3. 合并音频并将每段词级时间戳加上累计偏移。
4. 若最终时长与目标偏差超过 8%，只调整受影响的脚本段并重新生成相应音频。
5. 将最终音频标准化到约 -16 LUFS，峰值不超过 -1 dBTP。
6. 保存最终音频的 SHA-256；后续两个数字人适配器必须使用该文件，不得自行重新生成语音。

CosyVoice HTTP API 可返回词或字符的起止毫秒时间。当前标准价格中 `cosyvoice-v3.5-flash` 为 0.8 元/万字符，短视频配音成本相对数字人视频合成很低。

参考：

- [CosyVoice HTTP API 与时间戳](https://help.aliyun.com/en/model-studio/cosyvoice-tts-http-api)
- [阿里云百炼模型价格](https://help.aliyun.com/zh/model-studio/model-pricing)

首版只使用公共音色，不实现声音克隆。

### 8.3 字幕时间轴

TTS 返回词级时间戳时，直接生成：

- `captions.json`：供 Remotion 使用，包含词级起止时间、分行和高亮关键词。
- `subtitles.srt`：通用字幕交付文件。
- `subtitles.ass`：需要复杂样式时的字幕文件。

字幕每行建议不超过 12–16 个汉字，最多两行；优先在标点处换行，不拆开词语、数字或英文缩写。当前朗读的关键词可使用品牌强调色。字幕必须位于数字人胸部以下的安全区，不遮挡嘴部和主要面部区域。

当所选音色不支持词级时间戳时，退化为分段精确计时，并依据标点、字符数量和停顿权重分配段内时间。默认不再调用 ASR，避免识别文本与已确认脚本不一致。

### 8.4 统一音频驱动

阿里云营销引擎使用 `OpenVideoScript.type=AUDIO` 和 `audioUrl` 提交最终音频；官方照片数字人的音频驱动限制小于 60 秒，因此首版将有效口播硬限制为不超过 58 秒。

HeyGen v3 使用 `audio_url` 或 `audio_asset_id`，与 `script + voice_id` 互斥。两个适配器都必须上传并使用同一个 `narration.wav`，从而保证切换服务商时声音、时长和字幕不变。

参考：

- [阿里云数字人离线合成 OpenAPI](https://help.aliyun.com/zh/me/getting-started/digital-human-offline-synthesis-openapi)
- [HeyGen Create Video](https://developers.heygen.com/reference/create-video)

### 8.5 混音

数字人原片保留最终口播音频。Remotion 只添加背景音乐和视觉包装；背景音乐在人声出现时自动压低，不得覆盖口播。合成阶段不得重新生成配音或改变旁白速度，否则字幕时间轴和数字人口型将失配。

## 9. 数据流

1. 读取 `project.json`，验证必填字段和人像授权确认。
2. 检查照片格式、分辨率、正面可见性、单人脸和目标画幅适配性。
3. 检查本地依赖、服务商凭证、账户套餐及无水印资格。
4. 将主题或原始文案收敛为结构化 `script.json`，生成 3 秒钩子、核心内容、CTA、分段字幕和视觉提示。
5. 根据 TTS 字符数、数字人目标时长和账户计费规则生成总费用估算，等待用户确认脚本与费用。
6. 分段生成配音和词级时间戳，合并为唯一的 `narration.wav`，生成 `captions.json`、SRT 和 ASS。
7. 检查实际音频时长；超过 58 秒或偏离目标超过 8% 时先调整脚本和配音，不提交数字人任务。
8. 创建或复用照片数字人，上传最终音频并提交异步任务，将服务商、任务 ID、时间、预计费用、音频校验值和状态写入 `state.json`。
9. 使用任务 ID 轮询；运行中断后从 `state.json` 恢复，不重复提交。
10. 下载数字人原片，记录来源 URL、文件大小和 SHA-256 校验值。
11. 将原片、字幕、品牌设置和素材映射写入 Remotion 项目。
12. 渲染 MP4，并验证画幅、编码、帧率、音轨、时长、口型、字幕同步、黑帧、静音区间和抽帧画面。
13. 交付成片、结构化脚本、分段音频、最终旁白、SRT/ASS、状态、成本记录和工程源文件。

## 10. 服务商路由

- `provider: auto` 且已配置可用的阿里云环境时，选择 `aliyun-me`。
- 用户明确选择高表现力方案、海外环境或阿里云不可用时，选择 `heygen`。
- 服务商不可用时，只报告备用方案和新的预计费用，不自动产生第二次费用。
- 付费任务已创建后，所有恢复操作优先使用原任务 ID。

## 11. Remotion 成片设计

默认模板生成 9:16 竖屏视频，包含：

- 开头 3 秒大标题钩子。
- 数字人主体安全区，字幕不得遮挡嘴部和主要面部区域。
- 可插入产品图片、界面截图和 B-roll 的内容区。
- 与口播分句对齐的动态字幕。
- 可选 Logo、品牌色、背景纹理和低音量背景音乐。
- 结尾 CTA 与可循环收尾。

数字人原片是可复用付费资产。本地包装失败时必须保留原片，修复 Remotion 或 FFmpeg 后重新渲染，不得再次调用数字人 API。

## 12. 异常处理与费用保护

### 提交前

照片无人脸、多个人脸、分辨率不足、授权未确认、凭证缺失、余额或套餐不满足、无水印资格无法确认时停止执行，不调用付费 API。

### API 调用

- 认证失败、余额不足和审核拒绝直接报告。
- 429 和临时 5xx 使用带抖动的指数退避。
- 只有能够确认任务尚未创建时才重试提交请求。
- 任务状态和原始响应中的敏感字段不得写入日志。
- 内容审核失败时不尝试改写以规避规则，只请求用户修改素材或文案。

### 下载与合成

- 下载链接返回后立即保存本地副本并计算 SHA-256。
- 临时 URL 过期时使用已有任务 ID 重新查询结果，不重新创建任务。
- 编码、字体、素材或 Remotion 错误只触发本地修复和重渲染。
- 抽取四角和中部关键帧，检查水印、面部异常、字幕遮挡和画面裁切。

## 13. 测试策略

### RED：技能基线

在技能存在前运行至少三个代表性场景，记录代理是否遗漏授权、费用确认、无水印条件、任务恢复或重复扣费保护。

### GREEN：实现验证

- 单元测试覆盖配置解析、授权门槛、成本估算、路由、状态恢复、重试和日志脱敏。
- 配音测试覆盖分段合并、停顿、词级时间戳偏移、58 秒上限、8% 时长偏差和字幕降级算法。
- 适配器使用模拟 HTTP 响应测试提交、轮询、限流、余额不足、审核失败、超时和 URL 过期。
- 使用本地假服务商返回测试视频，实际运行 Remotion 与 FFmpeg 完成无付费端到端测试。

### 可选真实测试

只有同时满足以下条件才运行：

- 设置 `RUN_PAID_API_TESTS=1`。
- 提供有效凭证与已授权人像。
- 用户确认预计费用。
- 单次测试时长不超过 10 秒。

### 验收标准

- 中断后可从任务 ID 恢复，不重复提交和扣费。
- 默认正确选择阿里云，显式条件下可选择 HeyGen。
- 无真实凭证时所有模拟测试可运行。
- 输出为 1080×1920、30 FPS、H.264/AAC MP4。
- 两个服务商均使用与字幕时间轴匹配的同一条最终音频。
- 成片无平台水印、无黑帧、包含有效音轨，字幕不遮挡数字人面部。
- 密钥、签名和临时凭证不会出现在文件、日志或 Git 中。

## 14. 交付完成条件

- Skill 目录通过官方 `quick_validate.py` 校验。
- Python 测试、TypeScript 类型检查、Remotion 测试渲染和 FFmpeg 验证全部通过。
- `SKILL.md` 清晰说明触发条件、完整工作流、成本确认、授权要求和常见错误。
- 两个适配器具备一致的调用入口，默认路径不依赖本地 GPU。
- `script.json`、分段音频、最终旁白、`captions.json`、SRT 和 ASS 可稳定生成并保持时间一致。
- 所有示例仅使用占位凭证，不包含个人数据或真实密钥。
