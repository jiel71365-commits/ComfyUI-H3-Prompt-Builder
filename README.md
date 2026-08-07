# MiniMax H3 提示词生成 + AI 漫剧分镜流水线（ComfyUI 插件）

一套把「大白话需求」直接变成符合 MiniMax H3 官方规范的提示词，并支持「剧本 → 分镜剧本 → 逐镜 H3 提示词」完整 AI 漫剧工作流的 ComfyUI 自定义节点。

## 项目简介

MiniMax H3 是支持文本/图片/视频/音频多模态输入的视频生成模型（原生带声音、最长 15 秒、24FPS）。它的生成质量高度依赖提示词结构——官方在 `MiniMax-AI/MiniMax-H3` 仓库开源了 `h3-prompt-writing` 提示词技能（T2VA / I2VA / FL2VA / L2VA / Ref2VA 五种模式）和 8 个风格化技能。

本项目把这些官方规范与实战案例沉淀成**可复用的规则库**，并用 ComfyUI 自定义节点包装：

- **H3 Prompt Builder**：输入大白话或分镜描述，输出官方三字段/六段式提示词，直接接入 `MiniMaxH3ImageToVideo` / `MiniMaxH3ReferenceToVideo` 节点的 prompt 输入口。
- **漫剧分镜流水线**：输入一集剧本，自动提取角色/场景/道具资产、生成结构化分镜 JSON、按镜头输出 Ref2VA 提示词 + 接线说明，你只需按说明把参考图连进 R2V 节点。

适合在 ComfyUI 本地跑 MiniMax H3 的创作者（漫剧、短剧、MV、广告、科普动画等）。

## 功能特性

### H3 Prompt Builder（通用）
- 双模式：`LLM 改写`（调用 DeepSeek 按规则库改写）与 `模板骨架`（离线拼装官方结构）。
- 8 个官方风格预设可注入规则：极简产品广告 / 3D 动画 / 纸艺定格 / 纸拼贴 / MV 字幕 / 品牌宣传 / 联机游戏片头 / 手绘实拍融合。
- 输出遵循官方格式：基础模式三字段（`integrated_multimodal_description` / `overall_soundscape` / `non_diegetic_music`），全能参考模式六段式；台词/歌词/画面文字保留原语言。

### 漫剧分镜流水线（6 节点）
| 节点 | 作用 |
|---|---|
| 漫剧预设 | 风格 / 画幅 / 单集时长 / 输出语言 / 音频文字策略 |
| 剧本→分镜 | 剧本 → 分镜 JSON + 资源清单 JSON + 摘要（LLM 自动提取角色/场景/道具） |
| 资源映射 | `角色A=图1` 映射；留空自动建议；`shot_index` 按镜头过滤；设定图提示词 |
| 分镜→镜头提示词 | 按镜头输出 Ref2VA 提示词 + 接线说明；支持导出全部 |
| LLM 配置 | api_key / model / base_url / temperature 填一次复用 |
| H3 Prompt Builder | 通用提示词生成 |

### 实用细节
- **逐镜接线汇总**：每镜一行列出要连接的参考图（图号标注「图库第 N 张」，每镜连接数 ≤ 9）。
- **镜头选择**：资源映射 `shot_index=0` 全部 / `=N` 只看第 N 镜，mapping 更精简准确。
- **固定分镜复用**：粘贴已有分镜 JSON 直接跳过 LLM（不花钱、前后一致），资源清单自动反推。
- **禁字幕 + 无 BGM 策略**：默认开启，提示词强制 `non_diegetic_music: N/A` 且画面无字幕/文字/水印，方便多段剪辑。
- **速度与稳定性**：默认关闭模型思考（`thinking_disabled`）、分镜低温度（0.2）、空正文自动重试、硬超时兜底（120 秒）。
- **离线自检**：54 项 unittest 覆盖本地逻辑，`python self_test.py` 一键验证。

## 安装

1. 把 `comfyui-h3-prompt-builder/` 复制到 `ComfyUI/custom_nodes/ComfyUI-H3-Prompt-Builder`。
2. 重启 ComfyUI（或 Manager 刷新）。
3. 编辑 `config.json` 填入你的 API Key（DeepSeek 或任意 OpenAI 兼容端点）。

```json
{
  "base_url": "https://api.deepseek.com/chat/completions",
  "model": "deepseek-v4-flash",
  "api_key": "你的 key",
  "temperature": 0.4,
  "max_tokens": 32768,
  "manju_temperature": 0.2,
  "thinking_disabled": true
}
```

> `api_key` 只存在于你本机的 config.json，不会提交到仓库。

## 快速上手（漫剧）

1. **漫剧预设**：选风格、画幅（默认 9:16）、时长。
2. **剧本→分镜**：粘贴一集剧本，运行 → 得到分镜 JSON、资源清单、摘要。
3. **资源映射**：接分镜（可留空 mapping 自动建议；`shot_index` 选镜头）→ mapping JSON + 逐镜接线。
4. **分镜→镜头提示词**：mapping + 分镜 + 镜头序号 → 该镜 Ref2VA 提示词 + 接线说明。
5. **R2V**：按接线说明把角色/场景图连进 `MiniMaxH3ReferenceToVideo`，提示词接入 prompt 输入。

全部文本输出用 Show Text / Preview Text 查看。

## 目录结构

```text
├── comfyui-h3-prompt-builder/   # ComfyUI 插件源码
│   ├── nodes.py                 # H3 Prompt Builder 节点与 LLM 调用
│   ├── manju_nodes.py           # 漫剧 5 节点与本地逻辑
│   ├── rules/                   # 官方格式 + 8 风格 + 漫剧分镜规则（可编辑）
│   ├── config.json              # API 默认配置（key 不入 git）
│   └── self_test.py             # 离线自检（54 项）
├── docs/superpowers/            # 设计文档与实现计划
├── H3-提示词生成引擎-规则库.md    # 提示词生成规则手册
└── 八个风格化技能分析.md          # 官方 8 技能分析
```

## 参考与致谢

- 提示词格式依据：[MiniMax-AI/MiniMax-H3](https://github.com/MiniMax-AI/MiniMax-H3) 的 `h3-prompt-writing` 技能与官方风格技能（规则要点已编译进 `rules/`）。
- 模型权重与推理：[HuggingFace MiniMaxAI/MiniMax-H3](https://huggingface.co/MiniMaxAI/MiniMax-H3)、[ComfyUI 官方教程](https://docs.comfy.org/tutorials/video/minimax/minimax-h3)。

## 免责声明

本项目为个人创作工具，规则文件为自行整理；使用 MiniMax H3 模型请遵守其社区许可。请不要把 API Key 提交到公开仓库。
