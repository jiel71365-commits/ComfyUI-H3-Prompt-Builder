# ComfyUI H3 漫剧分镜生成插件 — 设计文档

- 日期：2026-08-06
- 状态：已批准（用户确认 4 节点方案与资源库思路），待用户审阅本文件后进入实现计划
- 载体：扩展现有插件 `ComfyUI-H3-Prompt-Builder`（不新建插件）
- 部署位置：`F:\comfyui\ComfyUI-aki-v2\ComfyUI\custom_nodes\ComfyUI-H3-Prompt-Builder`

## 1. 背景与目标

在现有 H3 Prompt Builder 插件中新增一套「AI 漫剧」流水线节点：输入一集剧本，自动提取角色/场景/道具资产、生成结构化分镜剧本（JSON），并按「镜头资源库」思路为每个镜头生成符合 H3 官方 Ref2VA 格式的提示词 + 接线说明。

核心原则（用户已确认）：
- 自动化边界 = A：**到提示词为止**，视频生成由用户在 R2V 节点逐个完成。
- 分镜剧本输出格式 = **JSON 为主**（机器可读），附可读摘要。
- 角色/场景/道具图**由用户提供**，插件通过「资源映射」文本（`角色A=图1`）管理标签，**用户不改提示词，按接线说明连图**。
- 每个镜头只引用本镜需要的资源，自动重新编号标签，遵守 H3 上限：≤9 图、≤3 视频、≤3 音频。
- 复用现有插件的 DeepSeek 配置（config.json）、规则文件机制、节点注册与自检结构。

## 2. 范围

### 做
- 4 个新节点：漫剧预设、剧本→分镜、资源映射、分镜→镜头提示词。
- 2 个规则文件：`rules/manju_storyboard.txt`、`rules/manju_shot_prompt.txt`。
- 本地（无 LLM）逻辑：预设 JSON 组装、资源映射文本解析、逐镜资源引用计算、接线说明生成。
- 离线自检扩展（self_test.py），README 增补漫剧用法。

### 不做（后续可扩展）
- 批量自动生成视频、图片/设定图生成、配音/TTS、BGM、最终剪辑。
- 与 ComfyUI-MiniMaxH3-Director（时间线编辑器）的集成。
- 多集批量处理（一次只处理一集）。

## 3. 架构

新增文件全部在现有插件目录内：

```
comfyui-h3-prompt-builder/
├── __init__.py                      # 追加注册 4 个新节点
├── nodes.py                         # 现有（复用 load_config / call_llm / read_text_file）
├── manju_nodes.py                   # 新增：漫剧 4 节点 + 本地逻辑
├── rules/
│   ├── manju_storyboard.txt         # 剧本→分镜 LLM 规则
│   └── manju_shot_prompt.txt        # 分镜→H3 提示词 LLM 规则
├── self_test.py                     # 追加漫剧测试
└── README.md                        # 追加漫剧章节
```

共享：config.json（DeepSeek key/model/base_url/max_tokens）、`nodes.load_config()`、`nodes.call_llm()`、`nodes.read_text_file()`。

## 4. 节点接口

分类统一为 `MiniMax H3 / 漫剧`。

### 4.1 漫剧预设（ManjuPreset）

纯本地，无 LLM。

| 输入 | 类型 | 默认 | 说明 |
|---|---|---|---|
| style | 枚举 | 古风 | 古风/都市/校园/科幻/悬疑/奇幻/甜宠/自定义 |
| aspect_ratio | 枚举 | 9:16 | 9:16 / 16:9 / 1:1 / 4:3 / 3:4 / 21:9 |
| duration | 枚举 | 自动 | 自动 / 60 / 90 / 120 / 180 / 300（秒） |
| output_language | 枚举 | 自动（英文结构+保留原文） | 同现有节点 |

输出 `preset_json`（STRING）：

```json
{
  "style": "古风",
  "aspect_ratio": "9:16",
  "duration": 180,
  "output_language": "自动（英文结构+保留原文）"
}
```

### 4.2 剧本→分镜（ManjuScriptToStoryboard）

LLM 节点。输入剧本 + 预设 JSON，调用 DeepSeek（system prompt = `manju_storyboard.txt` + 预设内容），输出三个 STRING：

- `storyboard_json`：

```json
{
  "episode_title": "第一集",
  "duration_seconds": 180,
  "shots": [
    {
      "shot_id": 1,
      "time_range": "0:00-0:05",
      "duration": 5,
      "scene": "场景A",
      "characters": ["角色A"],
      "props": [],
      "shot_size": "中景",
      "camera": "固定镜头，轻微推近",
      "action": "……画面内容……",
      "dialogue": "……台词原文，无则空字符串……",
      "sfx": "……音效……",
      "mood": "……情绪/节奏……",
      "continuity": {"start": "……起始状态……", "end": "……结束状态锁定，供下一镜继承……"}
    }
  ]
}
```

- `assets_json`（资源清单，LLM 自动提取）：

```json
{
  "characters": [{"id": "角色A", "description": "……中文外观描述……", "shots": [1, 5, 6]}],
  "scenes": [{"id": "场景A", "description": "……", "shots": [1, 2]}],
  "props": [{"id": "道具A", "description": "……", "shots": [3]}]
}
```

- `summary`：可读的中文分镜摘要（每镜一行）。

输入：`script`（STRING 多行，必填）、`preset_json`（STRING，可留空用默认）。

### 4.3 资源映射（ManjuResourceMapping）

纯本地解析，无 LLM。输入映射文本，输出 `mapping_json`（STRING）：

```json
{"角色A": 1, "角色B": 2, "场景A": 3, "道具A": 4}
```

- 输入 `mapping_text`（STRING 多行），格式：`角色A=图1` 每行一条；分隔符支持 `=`、`：`；图号支持 `图1`、`Picture 1`、纯数字 `1`；行间分隔支持换行、逗号、顿号。
- 可选输入 `assets_json`：存在时校验映射覆盖了清单中所有角色/场景/道具，缺失项在输出 JSON 中加 `"_warnings"` 字段。
- 重复图号 → `"_warnings"` 提示（同一张图被多个资源使用，允许但提醒）。

### 4.4 分镜→镜头提示词（ManjuShotPrompt）

LLM 节点。输入分镜 JSON + 映射 JSON + 镜头序号，先本地计算该镜资源引用（`compute_shot_refs`），再调用 DeepSeek（system prompt = `manju_shot_prompt.txt` + 该镜资源标签列表）生成：

- `h3_prompt`：该镜头的 Ref2VA 六段式提示词（`subject_definitions` 中 `<Picture N>` 只含本镜资源；台词 `<d>[中文]…</d>` 保留原文；遵守 ≤15s、画幅、漫剧表演/构图规则）。
- `wiring_note`：接线说明文本，例如：

```text
Shot 3 接线：<Picture 1>=角色A设定图, <Picture 2>=场景A图。音频：无。
```

输入：`storyboard_json`（STRING）、`mapping_json`（STRING）、`shot_index`（INT，默认 1）。

### 4.5 本地逻辑（可离线测试）

`manju_nodes.py` 中以下函数不联网：

- `build_preset_json(style, aspect_ratio, duration, output_language)` → preset JSON 字符串。
- `parse_mapping_text(text, assets_json)` → mapping JSON 字符串（含 `_warnings`）。
- `compute_shot_refs(storyboard_json, mapping_json, shot_index)` → `{"tags": [["<Picture 1>", "角色A"], ...], "missing": [...], "shot": {...}}`。
- `build_wiring_note(storyboard_json, mapping_json, shot_index)` → 接线说明文本。
- `build_manju_system_prompt(rule_file, extra)` → 规则文件 + 附加指令的 system prompt。

## 5. 规则文件要点

### `manju_storyboard.txt`
- 输入：一集剧本 + 预设（风格/画幅/时长）。
- 任务：① 提取角色/场景/道具资产（中文描述 + 出场镜头号）；② 按时间轴拆分为镜头（单镜 2–6 秒，总长 ≈ 目标时长，最后一镜结束点 = 总时长）；③ 每镜字段按 4.2 schema 输出 JSON。
- 连续性规则（参考社区 H3 分镜技能思想，规则文件头注明出处）：每镜写明起始/结束状态锁定，镜头 N 结束状态 = 镜头 N+1 起始状态；道具所有权/位置不得凭空变化；人物视线/朝向/左右手一致。
- 台词：剧本中的对白原文逐字保留，标注说话人；台词长度与镜头时长匹配。
- 每个镜头必须列出出场角色/场景/道具（供资源库引用）。
- 输出必须是合法 JSON，不要额外解释。

### `manju_shot_prompt.txt`
- 输入：单个镜头的分镜内容 + 该镜资源标签列表（`<Picture N>=资源名`）。
- 任务：按 Ref2VA 六段式输出（`subject_definitions` / `summary` / `retention_analysis` / `detailed_description` / `overall_soundscape` / `non_diegetic_music`）。
- `subject_definitions`：只定义本镜用到的 `<Picture N>`，并附资源中文描述。
- `detailed_description`：写实或对应风格；竖屏 9:16 构图意识；景别/机位按分镜；表演按分镜台词与情绪；台词 `<d>[中文]…</d>`；镜头时长 ≤15s。
- 连续性：延续分镜的起始状态；不引入本镜资源列表外的角色/场景。
- 输出语言按预设；只输出提示词正文。

## 6. 错误处理

| 场景 | 行为 |
|---|---|
| script 为空 | 返回提示「请输入剧本」 |
| preset_json / storyboard_json / mapping_json 非法 JSON | 返回可读错误，不崩溃 |
| shot_index 越界 | 返回提示「镜头序号超出范围（1–N）」 |
| 分镜引用未映射的资源 | 接线说明中列出 missing，提示补映射；提示词仍生成但警告 |
| 该镜资源超过 9 图 | 接线说明警告，提示拆分镜头 |
| LLM 调用失败 | 复用现有 call_llm 错误处理（含 max_tokens 自愈） |

## 7. 测试（扩展 self_test.py）

离线可测（不联网）：
- 预设 JSON 组装与字段。
- 映射解析：`=`/`：`、`图1`/`Picture 1`/`1`、多分隔符、重复图号警告、assets 缺失项警告。
- `compute_shot_refs`：按映射生成标签列表、missing 检测、越界返回。
- `build_wiring_note`：输出包含 `<Picture 1>` 与资源名。
- `build_manju_system_prompt`：规则文件存在且注入附加指令。
- 4 个节点的 INPUT_TYPES 结构。

LLM 实弹验证（部署后一次）：剧本→分镜、分镜→镜头提示词各跑一次小样例。

## 8. 部署与交付

- 开发目录：插件源码仍在仓库 `comfyui-h3-prompt-builder/`（master 分支）。
- 部署：复制整个文件夹到 `F:\comfyui\ComfyUI-aki-v2\ComfyUI\custom_nodes\ComfyUI-H3-Prompt-Builder`（config.json 保留已填 key，不入 git）。
- 交付物：4 个新节点可添加；README 漫剧章节含完整接线流程。

## 9. 后续可扩展（本期不做）

- 批量导出全部镜头提示词（一键全量）。
- 与 ComfyUI-MiniMaxH3-Director 时间线导入。
- 配音/音色参考（`<Audio N>`）接入。
- 多集批量处理与分镜版本管理。
