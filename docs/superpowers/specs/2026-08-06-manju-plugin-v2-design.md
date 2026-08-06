# 漫剧插件 v2 设计文档

- 日期：2026-08-06
- 状态：已批准（用户在需求清单上逐项选择），待用户审阅本文件后进入实现计划
- 载体：现有插件 `ComfyUI-H3-Prompt-Builder`，本次全部改动在 `manju_nodes.py`、`rules/`、`config.json`、`__init__.py`、`README.md`、`self_test.py`

## 1. 范围（用户逐项确认）

### 做
1. 预设节点新增「音频与文字策略」（默认：禁字幕+无BGM）。
2. 新增「LLM 配置」节点（api_key/model/base_url/temperature 填一次，JSON 输出复用）。
3. 剧本→分镜节点新增 `fixed_storyboard_json`（粘贴已有分镜 → 跳过 LLM，本地反推资源清单）。
4. 分镜→镜头提示词节点：`shot_index` 步进 +1、可选「导出全部」开关、读取分镜内的策略并注入提示词。
5. 资源映射节点：`mapping_text` 留空时按资源清单自动生成建议映射；新增可选「生成设定图提示词」开关。
6. 分镜 LLM 低温度：config.json 新增 `manju_temperature: 0.2`。
7. 规则文件按策略强制：镜头提示词 `non_diegetic_music: N/A` + 画面无字幕/文字/水印（按策略）。

### 不做
- 首尾帧链式衔接（用户明确拒绝，靠镜头语言与时长控制）。
- 视频/音频资源类型扩展（暂缓）。
- 全自动按镜头选图直连 R2V（维持接线说明 + 手动连图）。
- 修改现有 `H3PromptBuilder` 节点（其 api_key/model/base_url 字段保持现状）。

## 2. 改动明细

### 2.1 config.json

新增字段：

```json
{
  "manju_temperature": 0.2
}
```

用途：分镜 LLM 调用温度（降低前后不一致）；镜头提示词仍用 `temperature`（0.4）。

### 2.2 预设节点（ManjuPreset）

新增输入 `audio_text_policy`（枚举）：

```text
["禁字幕+无BGM", "仅禁BGM", "仅禁字幕", "保留默认"]，默认 "禁字幕+无BGM"
```

`build_preset_json(style, aspect_ratio, duration, output_language, audio_text_policy)` 的 preset JSON 增加字段：

```json
{
  "style": "古风",
  "aspect_ratio": "9:16",
  "duration": 180,
  "output_language": "自动（英文结构+保留原文）",
  "audio_text_policy": "禁字幕+无BGM"
}
```

### 2.3 新增「LLM 配置」节点（ManjuLlmConfig）

- 输入（均为 STRING，留空读 config.json）：`api_key`、`model`、`base_url`、`temperature`。
- 输出：`llm_config`（STRING JSON）：

```json
{"api_key": "", "model": "", "base_url": "", "temperature": 0.4}
```

- 分类 `MiniMax H3 / 漫剧`，显示名「漫剧：LLM 配置」。
- 空字符串表示「回退到 config.json / 节点单独输入」。

### 2.4 LLM 参数解析（本地函数 `resolve_llm_config`）

```python
def resolve_llm_config(api_key, model, base_url, llm_config_json=""):
    # 优先级：节点单独 api_key/model/base_url > llm_config_json > config.json
    # 返回 (key, model_name, endpoint, temperature_or_None, config)
```

- 三个 LLM 节点（剧本→分镜、分镜→镜头提示词、以及后续新增的 LLM 节点）统一走该函数。
- `temperature`：llm_config 提供则用之；否则分镜节点用 `config.manju_temperature`（0.2），镜头提示词节点用 `config.temperature`（0.4）。

### 2.5 剧本→分镜节点（ManjuScriptToStoryboard）

新增可选输入：

| 输入 | 类型 | 默认 | 说明 |
|---|---|---|---|
| llm_config | STRING 多行 | "" | LLM 配置 JSON |
| fixed_storyboard_json | STRING 多行 | "" | 已有分镜 JSON；非空且合法时跳过 LLM |

行为：
- `fixed_storyboard_json` 非空：解析（非法则返回错误）；资源清单由本地 `derive_assets_from_storyboard(storyboard)` 反推（角色/场景/道具 id 去重 + 出场镜头号，description 为空字符串）；摘要本地生成；**不调用 LLM**。
- 正常路径：LLM 生成后，从 preset JSON 读取 `audio_text_policy` 并写入分镜顶层字段 `_policy`；若 preset 未提供，默认 `"禁字幕+无BGM"`。
- 固定分镜路径：分镜无 `_policy` 时补默认策略。

本地函数：

```python
def derive_assets_from_storyboard(storyboard_json):
    # 返回 assets JSON 字符串：从 shots 中收集 characters/scenes/props 的唯一 id 与出场镜头号
```

### 2.6 分镜→镜头提示词节点（ManjuShotPrompt）

改动：
- `shot_index` INT 增加 `"step": 1`（上下箭头步进）。
- 新增可选输入 `llm_config`（STRING 多行）、`export_all`（BOOLEAN，默认 False）。
- 从分镜 JSON 读取 `_policy`（缺省 `"禁字幕+无BGM"`），注入本镜数据 JSON 的 `"policy"` 字段，由规则文件执行。
- `export_all=True`：遍历全部镜头，逐镜调用 LLM，输出拼接文本：

```text
=== Shot 1 ===
<h3_prompt>
--- 接线 ---
<wiring_note>

=== Shot 2 ===
...
```

两个输出分别为全部提示词文本、全部接线说明文本；中途失败则返回已生成部分 + 错误行。

### 2.7 资源映射节点（ManjuResourceMapping）

改动：
- 新增可选输入 `generate_image_prompts`（BOOLEAN，默认 False）。
- 输出从 1 个扩为 3 个：`mapping_json`（原有）、`suggested_mapping_text`、`image_prompts`。
- `mapping_text` 为空且 assets_json 合法 → 自动建议映射：顺序 = characters → scenes → props，编号从 1 递增，`suggested_mapping_text` 输出可读文本（`角色A=图1` 每行一条），`mapping_json` 同时按建议生成。
- `mapping_text` 非空 → 以用户文本为准，`suggested_mapping_text` 输出空字符串。
- `generate_image_prompts=True` 且 assets_json 合法 → `image_prompts` 输出设定图提示词（本地模板，不调 LLM）：

```text
角色A：<description>，漫剧角色设定图，竖屏9:16，半身立绘，简洁背景，高清
场景A：<description>，漫剧场景空镜图，竖屏9:16，无人物，干净构图
道具A：<description>，漫剧道具特写图，竖屏9:16，简洁背景
```

description 为空时退化为仅 id。

### 2.8 规则文件

`rules/manju_storyboard.txt` 追加：

```text
【画面文字策略】
- 读取本集预设的 audio_text_policy。
- 策略含「禁字幕」时：分镜不得安排任何画面内文字（字幕、标题、弹窗、水印、装饰文字），台词只作为语音存在。
- 策略为「保留默认」时可正常安排画面文字。
```

`rules/manju_shot_prompt.txt` 追加：

```text
【音频与文字策略】
- 读取本镜数据的 policy 字段。
- 策略含「无BGM」时：non_diegetic_music 必须写 N/A。
- 策略含「禁字幕」时：detailed_description 明确画面不出现任何字幕、文字、标题、水印、装饰文字。
- 策略为「保留默认」时正常处理。
```

### 2.9 注册与文档

- `__init__.py` 注册新节点 `ManjuLlmConfig`（显示名「漫剧：LLM 配置」）。
- README 漫剧章节补充：LLM 配置节点用法、固定分镜复用、导出全部、音频文字策略、设定图提示词、自动建议映射。

## 3. 错误处理

| 场景 | 行为 |
|---|---|
| fixed_storyboard_json 非法 JSON | 返回错误提示，不调用 LLM |
| llm_config 非法 JSON | 忽略并附加警告（不阻断） |
| export_all 中途失败 | 返回已生成部分 + 错误行 |
| mapping_text 与 assets_json 均缺失 | mapping_json={} + 警告，suggested 为空 |
| 分镜无 _policy | 默认「禁字幕+无BGM」 |

## 4. 测试（扩展 self_test.py）

- `build_preset_json` 含 `audio_text_policy`。
- `derive_assets_from_storyboard`：唯一 id、出场镜头号正确。
- 自动建议映射：空 mapping_text + assets → mapping_json 编号 1..N、suggested 非空。
- `resolve_llm_config` 优先级：节点字段 > llm_config > config（mock config）。
- `fixed_storyboard_json` 路径：mock call_llm 抛异常仍成功（证明未调用），输出为粘贴的分镜。
- `export_all`：mock call_llm 返回固定文本，输出含 `=== Shot 1 ===` 与全部接线。
- 策略注入：mock call_llm 捕获 system prompt 含 policy。
- `image_prompts` 生成：含资源 id 与描述。
- `ManjuLlmConfig` 节点 INPUT_TYPES 与输出 JSON。
- `shot_index` 含 step=1。

## 5. 部署与交付

- 部署：整个插件目录复制到 `F:\comfyui\ComfyUI-aki-v2\ComfyUI\custom_nodes\ComfyUI-H3-Prompt-Builder`；config.json 保留已填 key（不入 git），新增 `manju_temperature`。
- LLM 实弹验证：固定分镜路径（不花钱）、自动建议映射、策略注入后的镜头提示词（`non_diegetic_music: N/A`）、导出全部（小剧本 2-3 镜）。
- 交付：README 更新 + 手动验证清单。
