# 数字人口播短视频 Skill

把已获授权的人像照片、产品资料和口播主题，生成 9:16 无平台水印的数字人口播短视频。MVP 采用云 API 完成配音和数字人生成，本地使用 Remotion 合成字幕、品牌元素并验证成片，不要求本地 GPU。

> “无水印”依赖供应商账号本身具备无水印输出能力。本项目不会移除、遮挡或裁切供应商水印。

## MVP 能力

- 结构化口播脚本：钩子、痛点、方案/证据、CTA。
- CosyVoice 分段配音、真实字级时间戳、响度标准化和字幕生成。
- Aliyun Marketing Engine 为经济默认，HeyGen 为显式备选。
- Remotion 1080×1920 / 30 FPS 合成与媒体质量验证。
- 脚本、TTS 费用和数字人费用分开审批，所有付费调用 fail-closed。
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

## Skill 使用

完整工作流、脚本 JSON 契约、审批哈希、恢复规则和产物说明见 [SKILL.md](SKILL.md)。供应商配置见 [provider-setup.md](references/provider-setup.md)，故障恢复见 [troubleshooting.md](references/troubleshooting.md)。

## 安全边界

只处理已获授权的人像、声音、音乐、字体、Logo 和产品声明。不得用于冒充、虚假代言、未经授权的声音克隆或伪造产品功效。真实付费 API 调用前必须由用户明确批准当前精确哈希与费用。

## 验证

```powershell
python -m unittest discover -s tests -p "test_*.py"
npm --prefix template run typecheck
npm --prefix template run render:test
```

许可证见 [LICENSE](LICENSE)。
