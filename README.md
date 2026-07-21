# 数字人口播短视频技能

把已获授权的人像照片、产品资料和口播主题，生成 9:16 无平台水印的数字人口播短视频。最小可用版本采用云端接口完成配音和数字人生成，本地使用 Remotion 合成字幕、品牌元素并验证成片，不要求本地显卡。

> “无水印”依赖供应商账号本身具备无水印输出能力。本项目不会移除、遮挡或裁切供应商水印。

## 最小可用版本包含的能力

- 结构化口播脚本：钩子、痛点、方案与证据、行动号召。
- CosyVoice 分段配音、真实字级时间戳、响度标准化和字幕生成。
- Aliyun Marketing Engine 为经济默认，HeyGen 为显式备选。
- Remotion 1080×1920 / 30 FPS 合成与媒体质量验证。
- 脚本、配音费用和数字人费用分开审批；审批不完整时，默认拒绝所有付费调用。
- 持久化任务 ID、断点续跑、并发锁和未知提交隔离，避免重复扣费。
- 人像授权、路径边界、凭证脱敏和供应商原片保留。

## 快速开始

```powershell
git clone git@github.com:pzb5471/digital-human-short-video.git
cd digital-human-short-video

python -m venv .venv
.\.venv\Scripts\pip.exe install -r requirements.txt
npm --prefix template install
```

准备 FFmpeg/FFprobe，并按供应商复制和填写环境变量示例：

- `config/aliyun.env.example`
- `config/heygen.env.example`

将 `config/project.example.json` 复制到你的项目目录，放入已获授权的人像和脚本，然后按审批门执行：

```powershell
python scripts/run_pipeline.py plan <项目目录>\project.json
python scripts/run_pipeline.py narrate <项目目录>\project.json --script-approval <script-sha256> --estimate-approval <estimate-sha256>
python scripts/run_pipeline.py submit <项目目录>\project.json --approval-file <项目目录>\paid-approval.json
python scripts/run_pipeline.py resume <项目目录>\project.json
python scripts/run_pipeline.py compose <项目目录>\project.json
python scripts/run_pipeline.py verify <项目目录>\project.json
```

也可以用 `all` 作为可恢复调度器；它不会绕过脚本、费用或数字人付费审批。

## 本地零付费 Showcase 预览

Windows 用户可以使用系统自带的 `Microsoft Huihui Desktop` 中文语音，配合 FFmpeg 和 Remotion 在本地生成不调用任何付费 API 的竖屏预览：

```powershell
python scripts/make_local_portrait_preview.py --image "D:\素材\已授权头像.jpg"
```

输出默认位于 `.runtime/local-preview/`，包括成片 `final.mp4`、封面 `cover.png`、旁白、JSON/SRT/ASS 字幕和验证报告。该模式用于零成本演示完整合成流程，画面采用静态人像轻微推近，不包含真实口型驱动；生产模式仍可按项目配置接入阿里云百炼完成文案与 CosyVoice 配音，并接入数字人视频 API。

本项目以阿里云百炼作为生产级口播文案与 CosyVoice 配音能力来源，并在本地完成字幕、竖屏包装和成片验证。

## 技能使用

完整工作流、脚本 JSON 契约、审批哈希、恢复规则和产物说明见 [SKILL.md](SKILL.md)。供应商配置见 [provider-setup.md](references/provider-setup.md)，故障恢复见 [troubleshooting.md](references/troubleshooting.md)。

## 使用限制与安全边界

只处理已获授权的人像、声音、音乐、字体、标志和产品声明。不得用于冒充、虚假代言、未经授权的声音克隆或伪造产品功效。调用真实付费接口前，必须由用户明确批准当前精确哈希值与费用。

## 验证

```powershell
python -m unittest discover -s tests -p "test_*.py"
npm --prefix template run typecheck
npm --prefix template run render:test
```

许可证见 [LICENSE](LICENSE)。
