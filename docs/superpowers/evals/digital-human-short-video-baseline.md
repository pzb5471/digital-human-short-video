# Digital Human Short Video — RED Baseline

This is the pre-skill baseline. Each response below was produced by an isolated blind evaluator that received only its scenario prompt. The evaluators did not receive the design document or a future `SKILL.md`.

## Results

### `new-30s-video`

| Required item | Result | Evidence / omission |
| --- | --- | --- |
| 授权确认 | PASS | Confirms image, voice, product materials, and font authorization. |
| 脚本确认 | PASS | Provides a storyboard and editable script. |
| 逐项成本估算 | FAIL | 仅称 Edge TTS 免费、云 GPU 按小时计费；没有逐项成本估算。 |
| 付费前确认 | FAIL | 没有付款或产生计费前的显式确认关卡。 |
| 同一旁白驱动口型和字幕 | FAIL | `voice.wav` drives the talking head, but subtitles are manually made/Whisper-derived; it does not require that the same narration drive both. |
| 无水印资格检查 | FAIL | 检查最终画面有无水印，但没有在选择服务前检查无水印资格/套餐。 |
| 最终媒体验证 | PASS | Supplies `ffprobe` commands and acceptance criteria. |

**Scenario result: FAIL — 遗漏逐项成本估算、付费前确认、统一旁白驱动口型和字幕、无水印资格检查。**

### `resume-paid-job`

| Required item | Result | Evidence / omission |
| --- | --- | --- |
| 读取state.json | FAIL | Uses an unspecified `load_checkpoint()` / “持久化状态”; never specifies `state.json`. |
| 复用原task_id | PASS | Explicitly retains and queries the existing `task_id`. |
| 禁止自动重提 | PASS | Repeatedly says not to submit/create a new task. |
| 临时URL过期时重新查询原任务 | FAIL | Mentions recording URL expiry but gives no expiry recovery path that re-queries the original task. |
| 保留付费原片 | FAIL | Downloads to `output.mp4`; does not require preserving the paid original asset. |

**Scenario result: FAIL — 遗漏读取 `state.json`、URL 过期后重新查询原任务、保留付费原片。**

### `script-voice-captions`

| Required item | Result | Evidence / omission |
| --- | --- | --- |
| 结构化script.json | FAIL | Gives prose script only; no structured `script.json`. |
| 分段TTS | FAIL | Gives voice guidance only; no segmented TTS workflow. |
| 词级时间戳 | FAIL | Provides phrase-level SRT intervals, not word-level timestamps. |
| narration.wav哈希 | FAIL | Does not name `narration.wav` or provide a hash. |
| 同一音频提交两个服务商 | PASS | Explicitly says to upload the same final WAV/MP3 to both services. |
| 12到16字换行 | FAIL | No line-length rule. |
| 58秒硬限制 | FAIL | Targets 45 seconds but provides no 58-second hard limit. |

**Scenario result: FAIL — 遗漏结构化 `script.json`、分段 TTS、词级时间戳、`narration.wav` 哈希、12到16字换行、58秒硬限制。**

## RED verification conclusion

All three blind responses have FAIL/遗漏 findings. The required RED condition is met; no 429 pressure-condition rerun is needed.

## Appendix A — raw blind responses

The following appendices preserve each evaluator response verbatim, grouped by scenario.

### `new-30s-video` raw response

+````markdown
# 30 秒 9:16 数字人口播短视频执行方案

可以采用“授权人像 + 本地口播驱动 + 本地剪辑合成”的工作流。它不依赖带片尾或平台水印的在线生成平台；前提是确认所用人像、声音、产品素材和字体均已获授权，并在发布前按投放平台的合成内容标识规则处理。

## 目标产物

- `final_9x16.mp4`：1080×1920、30 秒、H.264 + AAC、无第三方平台水印。
- `voice.wav`：约 30 秒中文配音。
- `talking_head.mp4`：由授权单人肖像驱动生成的透明或普通背景口播片段。
- `subtitles.srt`：逐句字幕。
- `project/`：脚本、源素材和可复现命令。

## 推荐的经济适用技术路线

1. 写约 90～110 个汉字的口播稿；普通中文口播以约 180～220 字/分钟计，30 秒应避免写得过满。
2. 用本地 TTS 生成声音，例如 Edge TTS（免费）或已授权的商业 TTS。若产品需要真人感，可改用获授权的声音克隆服务，但必须得到说话者明确许可。
3. 用开源 talking-head 模型在本机/云 GPU 生成口型驱动视频，例如 SadTalker 或 LivePortrait；输入为授权头像和 `voice.wav`。建议选清晰、正脸、肩部以上、光线均匀的人像。
4. 用 FFmpeg 合成 9:16 背景、产品图/短视频、口播窗口、字幕和轻量 BGM。产品图与卖点文字应来自商家素材，不能虚构功效或价格。
5. 导出前检查时长、音画同步、字幕安全区、肖像效果和元数据；最终文件不添加任何生成平台标识或水印。若法规或投放平台要求 AI 内容标识，应使用符合要求的说明，不应通过去除他人水印规避规则。

## 示例分镜与文案（替换方括号内容）

0–3 秒：人物出镜，产品特写。

> 还在为[痛点]烦恼吗？

3–12 秒：产品主视觉 + 第一卖点。

> 这款[产品名]，主打[卖点一]，日常使用更省心。

12–21 秒：切两张细节图/使用场景。

> 它还有[卖点二]和[卖点三]，从[具体场景]到[具体场景]都很方便。

21–27 秒：人物回到画面中央，展示优惠或行动信息。

> 现在就到[店铺/链接]了解详情，选择适合你的[产品类别]。

27–30 秒：产品定帧、品牌名与合规提示。

> [品牌名]，让[核心价值]更简单。

## 目录准备

```powershell
mkdir project, project\assets, project\output
Set-Content -Encoding utf8 project\script.txt @'
还在为[痛点]烦恼吗？这款[产品名]，主打[卖点一]，日常使用更省心。它还有[卖点二]和[卖点三]，从[具体场景]到[具体场景]都很方便。现在就到[店铺]了解详情，选择适合你的[产品类别]。[品牌名]，让[核心价值]更简单。
'@
```

将授权肖像放到 `project/assets/portrait.png`，产品主图放到 `project/assets/product.png`。如需展示产品动态素材，另放入 `product_broll.mp4`。

## 可复现命令

### 1. 安装基础工具

以下命令以 Windows、已安装 Python 3.10+、Git 与 FFmpeg 为例。需要 NVIDIA GPU 才能以较低成本、较快速度运行口播模型；没有 GPU 时可租用按小时计费的云 GPU，并在完成后关机。

```powershell
winget install Gyan.FFmpeg
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install edge-tts
git clone https://github.com/OpenTalker/SadTalker.git project\SadTalker
cd project\SadTalker
pip install -r requirements.txt
```

模型仓库与依赖版本会更新，首次运行前按其 README 下载官方预训练权重到指定目录；只从项目官方发布页取得权重。

### 2. 生成配音

```powershell
cd ..\..
@'
import asyncio
import edge_tts

async def main():
    text = open("project/script.txt", encoding="utf-8").read()
    speaker = edge_tts.Communicate(text, voice="zh-CN-XiaoxiaoNeural", rate="-5%")
    await speaker.save("project/assets/voice.mp3")

asyncio.run(main())
'@ | Set-Content -Encoding utf8 project\tts.py
python project\tts.py
ffmpeg -y -i project\assets\voice.mp3 -ar 44100 -ac 1 project\assets\voice.wav
ffprobe -v error -show_entries format=duration -of default=nw=1:nk=1 project\assets\voice.wav
```

若时长明显偏离 30 秒，优先删改文案，其次调整 TTS `rate`；不要靠强行拉伸口播视频来掩盖口型不同步。

### 3. 生成人像口播

```powershell
cd project\SadTalker
python inference.py --driven_audio ..\assets\voice.wav --source_image ..\assets\portrait.png --result_dir ..\output --enhancer gfpgan
cd ..\..
```

从 `project/output` 中找到生成的视频（文件名随模型版本而不同），复制或重命名为 `project/assets/talking_head.mp4`。如模型输出时长与配音不一致，先检查音频采样率和人像输入，再重新生成。

### 4. 生成字幕

经济方案可先依据分镜人工创建字幕；上线前必须校对专名、数字和禁用宣传语。示例：

```text
1
00:00:00,000 --> 00:00:03,000
还在为[痛点]烦恼吗？

2
00:00:03,000 --> 00:00:12,000
这款[产品名]，主打[卖点一]，日常使用更省心。
```

保存为 UTF-8 编码的 `project/assets/subtitles.srt`。也可用本地 Whisper 自动转写后人工修订：

```powershell
pip install -U openai-whisper
whisper project\assets\voice.wav --language Chinese --task transcribe --output_format srt --output_dir project\assets
```

### 5. 合成竖屏成片

下面命令制作深色背景、顶部产品图、底部口播画面及内嵌字幕。Windows 下含字体路径的 `subtitles` 参数转义较敏感；若报错，使用正斜杠并确认字体存在。

```powershell
ffmpeg -y `
  -loop 1 -i project/assets/product.png `
  -i project/assets/talking_head.mp4 `
  -i project/assets/voice.wav `
  -filter_complex "[0:v]scale=1080:720:force_original_aspect_ratio=decrease,pad=1080:720:(ow-iw)/2:(oh-ih)/2,setsar=1[top];color=c=0x101826:s=1080x1920:d=30[bg];[1:v]scale=960:960:force_original_aspect_ratio=decrease,pad=960:960:(ow-iw)/2:(oh-ih)/2,setsar=1[person];[bg][top]overlay=0:120[tmp];[tmp][person]overlay=60:850,subtitles=project/assets/subtitles.srt:force_style='FontName=Microsoft YaHei,FontSize=18,PrimaryColour=&H00FFFFFF,OutlineColour=&H00101826,BorderStyle=1,Outline=3,Alignment=2,MarginV=120'[v]" `
  -map "[v]" -map 2:a -t 30 -r 30 `
  -c:v libx264 -preset medium -crf 20 -pix_fmt yuv420p `
  -c:a aac -b:a 192k -movflags +faststart project/output/final_9x16.mp4
```

如果生成的人像原视频已有配音，以上命令仅映射新生成的 `voice.wav`，避免叠音。若要用产品 B-roll 替换顶部静态图，可将第一个输入替换为视频，并按实际时长设置循环或裁剪。

## 交付前验收

```powershell
ffprobe -v error -select_streams v:0 -show_entries stream=width,height,r_frame_rate,duration -of default=nw=1 project\output\final_9x16.mp4
ffprobe -v error -show_entries format=duration -of default=nw=1:nk=1 project\output\final_9x16.mp4
```

验收标准：分辨率为 1080×1920；时长为 29.5–30.5 秒；人脸无明显抖动或口型漂移；字幕位于底部安全区且可读；产品、价格和功效表述与已提供资料一致；输出画面没有第三方平台角标、片尾或水印。保留源图、授权记录、配音文件、脚本和工程目录，方便复审与二次剪辑。

````

### `resume-paid-job` raw response

+````markdown
# 续跑已提交的阿里云数字人任务（避免重复扣费）

不要重新调用“提交/创建数字人视频任务”的接口，也不要重新上传并创建任务。已有 `task_id` 代表已付费的异步任务；中断后应只恢复“查询状态 → 等待 → 下载结果”这段流程。

1. 保留原始的 `task_id`、地域（region）、业务类型/接口版本，以及用于提交任务的同一账号和凭证。
2. 调用对应数字人服务的**任务查询接口**，传入已有 `task_id`。查询不会创建新任务，也不应触发新的生成计费。记录返回的状态、错误码、结果视频 URL 和过期时间。
3. 按状态处理：
   - `SUCCESS` / `COMPLETED`：直接下载返回的视频 URL，校验文件大小和可播放性后结束。
   - `RUNNING` / `PROCESSING` / `PENDING`：仅轮询同一个查询接口（建议 15–30 秒一次，并设置最长等待时间）；不要触发提交接口。
   - `FAILED`：保存错误码和请求 ID，联系阿里云工单/技术支持核查该已付费任务是否可重试或退款。在确认前不要自行新建任务。
   - `NOT_FOUND`：先核对 region、账号、接口产品和 `task_id` 是否完全一致；这通常是上下文不一致，不应立刻重提。
4. 进程重启时，从持久化状态读取 `task_id`；若任务已成功但尚未下载，则只执行下载。下载成功后把状态标记为 `downloaded`，防止重复处理。

示例伪代码（将 `query_task` 替换为当前所用阿里云数字人 API 的查询调用）：

```python
import time

task_id = load_checkpoint()["task_id"]  # 已提交任务的 ID，绝不重新生成

while True:
    result = query_task(task_id=task_id)  # 只能是“查询任务”接口
    status = result["status"]

    if status in {"SUCCESS", "COMPLETED"}:
        video_url = result["video_url"]
        download_once(video_url, destination="output.mp4")
        save_checkpoint({"task_id": task_id, "status": "downloaded"})
        break
    if status in {"FAILED", "NOT_FOUND"}:
        raise RuntimeError(f"Do not resubmit: {status}; requestId={result.get('request_id')}")

    time.sleep(20)
```

为彻底避免重复扣费，给恢复脚本加一个硬性保护：代码中不得出现提交任务的调用；如果 checkpoint 缺少 `task_id`，立刻停止并人工恢复该值，而不是自动创建新任务。

````

### `script-voice-captions` raw response

+````markdown
# 45秒中文数字人口播方案

## 脚本（约45秒）

你有没有发现，很多工作明明花了很多时间，却总是看不到明显结果？

问题往往不在努力不够，而在于没有把目标拆成今天就能完成的一小步。

从现在开始，先写下一个最重要的目标，再问自己：我今天能为它做什么？哪怕只完成十分钟，也是在向前。

别等状态完美，行动本身会带来状态。

现在，就从第一小步开始。

## 配音建议

- 语言：普通话，女声或男声均可，选择自然、温和、坚定的青年音色。
- 语速：约每分钟 190～210 字，整体控制在 45 秒左右。
- 情绪：开头以提问引起注意；中段理性、鼓励；结尾稍作停顿并增强号召力。
- 停顿：每段之间停顿 0.4～0.7 秒；“别等状态完美”前停顿 0.5 秒。

## 逐词高亮字幕（SRT示例）

> 说明：逐词高亮建议通过字幕播放器的卡拉OK/逐词效果实现。字幕文本和配音必须使用同一份最终脚本，且时间码以最终音频为准。

```srt
1
00:00:00,000 --> 00:00:05,500
你 有没有 发现 很多 工作 明明 花了 很多 时间

2
00:00:05,500 --> 00:00:10,000
却 总是 看不到 明显 结果

3
00:00:10,000 --> 00:00:16,500
问题 往往 不在 努力 不够 而在于 没有 把 目标 拆成

4
00:00:16,500 --> 00:00:22,000
今天 就能 完成 的 一小步

5
00:00:22,000 --> 00:00:29,000
从 现在 开始 先 写下 一个 最重要 的 目标 再 问 自己

6
00:00:29,000 --> 00:00:35,500
我 今天 能 为 它 做 什么 哪怕 只 完成 十分钟 也 是 在 向前

7
00:00:35,500 --> 00:00:40,500
别 等 状态 完美 行动 本身 会 带来 状态

8
00:00:40,500 --> 00:00:45,000
现在 就 从 第一 小步 开始
```

## 阿里云与 HeyGen 切换一致性建议

1. 固定使用同一条最终生成的音频，不要分别在阿里云和 HeyGen 内部重新合成语音。将该 WAV/MP3 分别上传到两个平台进行口型驱动，可保证音色和时长一致。
2. 使用同一份脚本文字和同一份字幕文件；字幕在后期剪辑软件中统一叠加，而不是使用平台自动字幕。
3. 建议导出 48 kHz、16-bit、单声道 WAV 作为母版，两个平台均使用该母版。最终视频按同一帧率导出，例如 25 fps。
4. 若必须切换平台合成配音，应记录并锁定音色名称、模型版本、语速、音调、情绪和停顿参数；但不同平台的音色无法做到完全一致，因此优先采用外部统一音频。
5. 完成后对照音频波形和字幕时间码，检查首尾时长均为 45 秒，并确认逐词高亮与发音同步。

````
