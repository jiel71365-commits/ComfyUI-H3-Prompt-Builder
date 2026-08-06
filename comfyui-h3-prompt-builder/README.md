# ComfyUI H3 Prompt Builder

把大白话需求改写成符合 MiniMax H3 官方格式的提示词，直接接入 R2V / T2V / I2V 节点的 prompt 输入口。

## 安装

1. 把整个文件夹复制到 `ComfyUI/custom_nodes/ComfyUI-H3-Prompt-Builder`。
2. 重启 ComfyUI（或用 Manager 刷新）。
3. 编辑 `config.json` 填入你的 API Key（也可以不填，在节点输入框里填）。

## 使用

右键添加节点：`MiniMax H3` → `H3 Prompt Builder（提示词生成）`。

节点参数：
- `text`：你的需求（主体/场景/动作/风格），或素材说明（例如：图1是人物参考，视频1是动作参考）。
- `mode`：`LLM 改写`（默认，联网调用 DeepSeek）或 `模板骨架`（离线，生成官方结构骨架）。
- `generation_mode`：`auto` 让模型自动判断，或手动指定 T2VA/I2VA/FL2VA/L2VA/Ref2VA（模板骨架模式必填）。
- `style`：通用或 8 个官方风格规则（产品广告/3D动画/纸艺定格/纸拼贴/MV字幕/品牌宣传/游戏片头/手绘实拍）。
- `duration` / `aspect_ratio`：目标时长与画幅，默认自动。
- `output_language`：默认英文结构+保留台词原文，可选全中文/全英文。
- `api_key` / `model` / `base_url`：留空使用 `config.json` 默认值（默认模型 `deepseek-v4-flash`，默认端点 `https://api.deepseek.com/chat/completions`）。
- `base_url` 填 `https://api.deepseek.com`（不带路径）也可以，插件会自动补全 `/chat/completions`；留空则用 config.json 默认值。

输出 `h3_prompt`（STRING）接到 H3 节点的 prompt 输入即可。

## 漫剧分镜流水线（4 节点）

分类：`MiniMax H3 / 漫剧`

1. **漫剧预设**：风格 / 画幅（默认 9:16）/ 单集时长 / 输出语言 → 预设 JSON。
2. **漫剧：剧本→分镜**：粘贴一集剧本 + 预设 JSON → 分镜 JSON + 资源清单 JSON + 摘要。LLM 自动提取角色/场景/道具（中文描述 + 出场镜头号）。
3. **漫剧：资源映射**：填 `角色A=图1`（每行一条，支持 `=`/`：`、`图1`/`Picture 1`/`1`）→ 映射 JSON。可接资源清单做缺失校验；`mapping_text` 留空时自动生成建议；接 `storyboard_json` 后第 4 个输出 `per_shot_wiring` 给出每镜接线汇总（图号显示为「图库第 N 张」，只是图库索引，每镜连接数 ≤9）。
4. **漫剧：分镜→镜头提示词**：分镜 JSON + 映射 JSON + 镜头序号 → 该镜 H3 提示词 + 接线说明。

使用流程：
- 预设和映射填一次，保存工作流后复用。
- 每个镜头在 R2V 节点上只连接接线说明里列出的图，顺序与 `<Picture N>` 标签一致；不改提示词。
- 镜头数超过 1 时，改「镜头序号」逐镜生成。
- 全部输出用 Show Text / Preview Text 查看。

### v2 新功能

- **漫剧：LLM 配置**：api_key/model/base_url/temperature 填一次输出 JSON，接到剧本→分镜与分镜→镜头提示词的 `llm_config` 输入即可复用；优先级：节点单独输入 > llm_config > config.json。
- **音频与文字策略**（预设节点）：默认「禁字幕+无BGM」，镜头提示词强制 `non_diegetic_music: N/A` 且画面无字幕/文字/水印。
- **固定分镜复用**：剧本→分镜节点的 `fixed_storyboard_json` 粘贴已有分镜后跳过 LLM（不花钱、前后一致），资源清单自动反推。
- **导出全部**：分镜→镜头提示词节点打开 `export_all` 一次性输出全部镜头的提示词与接线说明。
- **自动建议映射**：资源映射节点的 `mapping_text` 留空时，按资源清单自动生成 `角色A=图1` 建议（输出在 `suggested_mapping_text`）。
- **设定图提示词**：资源映射节点打开 `generate_image_prompts`，输出角色/场景/道具的设定图提示词（离线）。
- **分镜低温度**：config.json 的 `manju_temperature: 0.2` 降低分镜随机性；`shot_index` 支持步进。

## R2V 提示

- 提示词里的 `<Picture 1>` `<Video 1>` `<Audio 1>` 标签顺序，必须和你在 R2V 节点上连接参考素材的顺序一致。
- 给每个素材写明用途（人物/风格/动作/运镜/音色），效果更好。
- `ref_image_size`：`match` 快、`max` 保真（最大 2048 短边）。
- 时长按 17 帧/块 @24fps 网格吸附。

## 离线自检

```bash
python self_test.py
```

## 配置项（config.json）

| 字段 | 默认 | 说明 |
|---|---|---|
| base_url | https://api.deepseek.com/chat/completions | OpenAI 兼容端点（可换中转地址） |
| model | deepseek-v4-flash | 模型名 |
| api_key | 空 | API Key（也可在节点输入框填） |
| temperature | 0.4 | 采样温度 |
| max_tokens | 32768 | 最大输出 token（含推理 token；推理型模型建议不低于 16384） |

## 常见问题

- **提示「未配置 API Key」**：在节点 `api_key` 输入框或 `config.json` 里填 key。
- **提示「LLM 调用失败：HTTP 404」**：检查 `model`/`base_url` 是否正确（中转站模型名可能不同）。
- **提示「模型未返回正文」**：推理过程占满了 `max_tokens`。插件会自动加倍重试一次，仍失败就调大 `config.json` 的 `max_tokens`（默认已设为 32768）。
- **模板骨架模式**：不联网、不花钱，输出的是需要手工补全的骨架。
