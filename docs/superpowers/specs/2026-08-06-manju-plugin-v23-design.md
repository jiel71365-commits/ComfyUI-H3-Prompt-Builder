# 漫剧插件 v2.3 设计文档（图像提示词 LLM 生成）

- 日期：2026-08-07
- 状态：已批准（用户确认默认 LLM 生成、角色参考图合成一张、提示词模型无关），待用户审阅本文件后进入实现计划
- 载体：现有插件 `ComfyUI-H3-Prompt-Builder`，改动集中在 `manju_nodes.py`、`rules/manju_image_prompt.txt`（新增）、`self_test.py`、`README.md`

## 1. 背景

资源映射节点的图像提示词目前是本地模板：描述缺失时输出空描述、不结合预设风格、质量不可用。改为默认由 LLM 生成高质量设定图提示词。

## 2. 范围

### 做
- `generate_image_prompts`（BOOLEAN）改为 `image_prompt_mode`（枚举：`LLM 生成` / `离线模板` / `关闭`），**默认 `LLM 生成`**。
- 新增规则文件 `rules/manju_image_prompt.txt`，LLM 模式按此生成。
- LLM 模式输入：资源清单 JSON + 预设 JSON（style / aspect_ratio）；复用现有 LLM 配置（config.json / llm_config / resolve_llm_config）。
- LLM 失败：`image_prompts` 输出错误提示文本，其余输出不受影响。
- 离线模板模式：保留本地生成（改进：注入风格词、角色图改为三视图+面部特写合成描述），零成本保底。
- 关闭：`image_prompts` 为空字符串。

### 不做
- 不接入具体生图模型（提示词模型无关，适配即梦 / image2 / ComfyUI 等，用户自行测试）。
- 不改节点其他输出结构。

## 3. 规则文件定稿（rules/manju_image_prompt.txt）

```text
你是漫剧美术设定师。任务：根据资源清单与漫剧预设，为每个资源生成可直接用于图像生成模型的设定图提示词。

【输入】
- 资源清单 JSON：characters / scenes / props，每项含 id、description、shots。
- 本集预设：style（风格）、aspect_ratio（画幅，统一 9:16 竖屏）。

【输出格式】按资源分组逐条输出，每条一行标题 + 完整提示词：
角色A设定图：<完整提示词>
场景A空镜图：<完整提示词>
道具A特写图：<完整提示词>

【角色设定图（每个角色一条）】
- 必须是一张合成参考表：全身三视图（正面/侧面/背面）并排排版 + 一块面部特写。
- 人物站姿自然，双手自然垂下。
- 写清外貌（发型/脸型/瞳色/肤色）、服装（款式/颜色/材质，细节纹理尽力而为，非必需）、体型与气质。
- 9:16 竖屏，简洁纯色背景，柔和均匀光。
- 风格必须遵循预设：古风→汉服/水墨质感/古典光影；科幻→机能服/霓虹/金属质感；校园→校服/清新日常光；悬疑→暗调/高反差/胶片颗粒。

【场景空镜图】
- 写清环境主体、时间与光线、氛围；明确无人物、无文字、干净构图。

【道具特写图】
- 写清材质、结构、视角、背景。

【兜底】
- description 缺失时，根据资源名与分镜上下文合理补全，不要留空。

【负面块】每条末尾统一附：
不要文字、字幕、水印、logo，不要多余人物，不要变形手指与肢体，不要低质量，不要漫画对话框。

【硬规则】
- 只输出各资源的提示词正文，不解释、不 JSON、不代码块标记。
- 全剧资源风格统一。
- 不出现真实品牌、版权角色。
- 提示词不绑定任何特定生图模型，采用通用中文描述。
```

## 4. 实现要点

`ManjuResourceMapping`：

- `INPUT_TYPES` optional 中 `image_prompt_mode`：

```python
"image_prompt_mode": (["LLM 生成", "离线模板", "关闭"], {"default": "LLM 生成"}),
```

- `build` 签名改为 `(mapping_text, assets_json="", image_prompt_mode="LLM 生成", storyboard_json="", shot_index=0)`。
- `_build_image_prompts(assets, style)`：离线模板模式使用；注入风格词，角色图描述更新为「三视图+面部特写合成参考表」。
- 新增 `_build_image_prompts_llm(assets_json, preset_json, llm_args...)`：system = 规则文件，user = 资源清单 + 预设，返回 LLM 输出。
- LLM 模式：`image_prompts = _build_image_prompts_llm(...)`；异常时输出 `图像提示词生成失败：<原因>`。

## 5. 测试

- `INPUT_TYPES` 含 `image_prompt_mode` 且默认 `LLM 生成`。
- 模板模式：`node.build("", ASSETS, "离线模板", ...)` 输出含「设定图」且角色行含「三视图」。
- LLM 模式：mock `call_llm`，断言 user 消息含资源清单与预设、`image_prompts` 为 mock 返回值。
- 关闭：`image_prompts` 为空。
- 规则文件存在且包含「三视图」「面部特写」「双手自然垂下」。
- 现有测试中 `generate_image_prompts=True` 的调用改为 `"离线模板"`。

## 6. 文档

- README：资源映射节点 `image_prompt_mode` 用法与说明。
