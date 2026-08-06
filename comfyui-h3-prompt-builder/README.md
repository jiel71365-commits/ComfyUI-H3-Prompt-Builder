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
