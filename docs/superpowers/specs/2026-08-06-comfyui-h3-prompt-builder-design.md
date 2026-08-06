# ComfyUI H3 Prompt Builder — 设计文档

- 日期：2026-08-06
- 状态：已批准（用户已确认设计要点），待用户审阅本文件后进入实现计划
- 安装位置：`F:\comfyui\ComfyUI-aki-v2\ComfyUI\custom_nodes\ComfyUI-H3-Prompt-Builder`
- 用户环境：ComfyUI-aki（Windows），平时使用 R2V 工作流，本地运行 MiniMax H3

## 1. 背景与目标

把已整理的 MiniMax H3 提示词规则库（官方 `h3-prompt-writing` 格式 + 8 个官方风格技能要点）做成 ComfyUI 自定义节点：输入大白话/素材说明，输出符合官方格式的 H3 提示词，可直接接入 R2V / T2V / I2V 节点的 prompt 输入口。

目标约束（用户指定）：
- 形态 C：混合模式 = 离线模板骨架 + LLM 改写，一个节点内切换。
- LLM 走 DeepSeek，默认模型 `deepseek-v4-flash`，端点与模型名可配置。
- 简单易懂、易操作：以「输入 text → 输出 text」为原则，尽量少填参数。
- R2V 优先：提示词中参考素材按官方标签 `<Picture 1>` `<Video 1>` `<Audio 1>` 指代，与 R2V 节点素材连接顺序对应。

## 2. 范围

### 做
- 一个自定义节点 `H3PromptBuilder`（LLM 改写 / 模板骨架双模式）。
- 内置规则文件：官方基础格式精简版 + 8 个风格技能规则（可编辑的纯文本）。
- `config.json`：API Key、模型名、端点、温度、max_tokens 默认值。
- 离线自检脚本 `self_test.py`（不联网）。
- 中文 README 使用说明。

### 不做（后续可扩展，明确排除）
- 锚点图/定帧图/分镜图生成（由其他图像节点或外部工具完成）。
- BGM / 旁白 / 最终合片。
- 多节点端到端流水线编排（用户自行在 ComfyUI 画布串联）。
- LLM 视觉输入（节点只处理文本；参考素材在 R2V 节点上直接连接）。

## 3. 架构与组件

```
ComfyUI-H3-Prompt-Builder/
├── __init__.py          # 注册 NODE_CLASS_MAPPINGS / NODE_DISPLAY_NAME_MAPPINGS
├── nodes.py             # 节点类：INPUT_TYPES / build() / LLM 调用 / 模板拼装
├── config.json          # base_url / model / api_key / temperature / max_tokens
├── rules/
│   ├── base_system_prompt.txt   # 官方格式精简规则（中英混合，字段名英文）
│   └── styles/
│       ├── minimalist_product_ad.txt
│       ├── animation_3d.txt
│       ├── papercraft_stop_motion.txt
│       ├── paper_collage.txt
│       ├── mv_subtitle.txt
│       ├── brand_promo.txt
│       ├── co_op_game_intro.txt
│       └── handdrawn_live.txt
├── self_test.py         # 离线自检（py_compile、模板拼装、config 读取）
├── README.md            # 中文安装与使用说明
└── .gitignore           # __pycache__/
```

依赖：仅 Python 标准库（`urllib.request`、`json`、`os`），不引入第三方包，避免 ComfyUI 环境冲突。

## 4. 节点接口

节点显示名：`H3 Prompt Builder（提示词生成）`；分类：`MiniMax H3`。

### 输入（required）

| 参数 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| text | STRING（多行） | 引导文案 | 大白话需求或分镜/素材说明 |
| mode | 枚举 | `LLM 改写` | `LLM 改写` / `模板骨架` |
| generation_mode | 枚举 | `auto` | auto / T2VA / I2VA / FL2VA / L2VA / Ref2VA；LLM 模式用 auto 由模型判断，模板模式用于选择骨架 |
| style | 枚举 | `通用` | 通用 + 8 个风格技能 |
| duration | 枚举 | `自动` | 自动 / 4–15 秒 |
| aspect_ratio | 枚举 | `自动` | 自动 / 21:9 / 16:9 / 4:3 / 1:1 / 3:4 / 9:16 |
| output_language | 枚举 | `自动（英文结构+保留原文）` | 自动 / 中文提示词 / 全英文 |

### 输入（optional，留空即读 config.json）

| 参数 | 类型 | 说明 |
|---|---|---|
| api_key | STRING | DeepSeek API Key |
| model | STRING | 模型名，默认 `deepseek-v4-flash` |
| base_url | STRING | OpenAI 兼容端点，默认 `https://api.deepseek.com/chat/completions` |

### 输出

| 输出 | 类型 | 说明 |
|---|---|---|
| h3_prompt | STRING | 最终 H3 提示词（或错误信息文本） |

## 5. 行为设计

### 5.1 LLM 改写模式

1. 组装 system prompt = `base_system_prompt.txt` +（style ≠ 通用时）对应风格规则文件 + 输出语言指令 +「只输出提示词正文，不解释」。
2. user message = 用户 `text`。
3. POST `{base_url}`，JSON：`{"model": model, "messages": [...], "temperature": config.temperature, "max_tokens": config.max_tokens, "stream": false}`；Header：`Authorization: Bearer <api_key>`、`Content-Type: application/json`；超时 120s。
4. 解析 `choices[0].message.content` 作为输出。
5. 失败时把可读错误（HTTP 状态 + 响应摘要，不含 API Key）返回给输出框，不抛异常。

### 5.2 模板骨架模式（离线）

按 `generation_mode` 拼装官方结构：
- T2VA：三字段（`integrated_multimodal_description` / `overall_soundscape` / `non_diegetic_music`），用户文本插入主文。
- I2VA：图片对齐指令第一行 + 三字段。
- FL2VA / L2VA：对应对齐指令 + 三字段。
- Ref2VA：六段骨架（`subject_definitions` / `summary` / `retention_analysis` / `detailed_description` / `overall_soundscape` / `non_diegetic_music`）带占位说明。
- duration / aspect_ratio 非自动时，在文件头追加一行目标参数说明。
- soundscape / music 给占位，默认 `N/A` 可改。

### 5.3 输出语言

- 默认：结构字段英文，台词/歌词/画面文字保留原语言（官方规则）。
- `中文提示词`：LLM 模式在 system prompt 中要求整体中文输出（保留官方字段骨架）。
- `全英文`：要求全英文输出。

## 6. R2V 兼容

- LLM 模式 system prompt 明确要求：引用素材一律用 `<Picture N>` `<Video N>` `<Audio N>` 标签，编号按用户在需求文本中描述的顺序；R2V 节点上连接顺序需与此一致。
- README 中给出 R2V 节点接线提示（标签顺序 = 连接顺序、`ref_image_size: match/max`、时长 17 帧/块网格）。

## 7. 错误处理

| 场景 | 行为 |
|---|---|
| text 为空 | 返回提示「请输入需求文本」 |
| LLM 模式无 API Key | 返回提示，指导填节点或 config.json |
| HTTP 错误 / 网络错误 / 模型名错误 | 返回 `LLM 调用失败：<可读原因>`，不含密钥 |
| 模板模式 | 永不联网，纯本地拼装 |
| 规则文件缺失 | 跳过对应文件并在输出附加警告，不崩溃 |

## 8. 测试

1. `self_test.py`（离线）：语法编译检查、config.json 读取、模板骨架各模式输出包含关键字段、8 个风格规则文件可读。
2. LLM 实弹冒烟测试（装好后执行一次）：用最小请求验证 `deepseek-v4-flash` 在默认端点可用；失败则反馈用户确认端点/模型名。
3. 手动验证：放入 `custom_nodes` → 重启 ComfyUI → 添加节点 → LLM 模式与模板模式各跑一次 → 输出接入 R2V 节点 prompt 口。

## 9. 后续可扩展（本期不做）

- 模板模式智能化（按风格自动补镜头/文案规则）。
- 多输出（prompt + 检查清单）。
- 参考素材自动编号（从 R2V 节点读取连接顺序）。
- 打包为可分享的 zip / git 仓库。
