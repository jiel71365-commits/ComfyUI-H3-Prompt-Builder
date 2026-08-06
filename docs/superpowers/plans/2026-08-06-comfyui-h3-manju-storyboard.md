# ComfyUI H3 漫剧分镜生成插件 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在现有 `ComfyUI-H3-Prompt-Builder` 插件中新增 4 个漫剧节点：预设、剧本→分镜、资源映射、分镜→镜头提示词，实现「一集剧本 → 分镜 JSON + 资源清单 + 逐镜 H3 提示词 + 接线说明」。

**Architecture:** 新增 `manju_nodes.py`（4 节点 + 本地逻辑），复用现有 `nodes.py` 的 `load_config/call_llm/read_text_file` 与 config.json；新增 `rules/manju_storyboard.txt`、`rules/manju_shot_prompt.txt` 两个 LLM 规则文件；`self_test.py` 扩展离线测试。

**Tech Stack:** Python 3 标准库；ComfyUI 自定义节点规范。

**Spec:** `docs/superpowers/specs/2026-08-06-comfyui-h3-manju-storyboard-design.md`

---

## 文件结构

```
comfyui-h3-prompt-builder/            # 现有插件目录（master）
├── __init__.py                       # 追加注册 4 个漫剧节点
├── nodes.py                          # 现有，不动（复用）
├── manju_nodes.py                    # 新增：本地逻辑 + 4 节点
├── rules/
│   ├── manju_storyboard.txt          # 新增：剧本→分镜 LLM 规则
│   └── manju_shot_prompt.txt         # 新增：分镜→H3 提示词 LLM 规则
├── self_test.py                      # 追加漫剧测试
└── README.md                         # 追加漫剧章节
```

部署：整个文件夹复制到 `F:\comfyui\ComfyUI-aki-v2\ComfyUI\custom_nodes\ComfyUI-H3-Prompt-Builder`（config.json 保留已填 key，不入 git）。

---

### Task 1: 漫剧规则文件

**Files:**
- Create: `comfyui-h3-prompt-builder/rules/manju_storyboard.txt`
- Create: `comfyui-h3-prompt-builder/rules/manju_shot_prompt.txt`

- [ ] **Step 1: 创建 manju_storyboard.txt**

```text
你是 AI 漫剧分镜导演。任务：把用户提供的一集剧本转换为结构化分镜剧本（JSON），并自动提取全片需要的角色、场景、道具资产清单。

【输入】
- 剧本原文：对白、旁白、场景描述等。
- 本集预设：风格、画幅、目标时长、输出语言。

【执行步骤】
1. 通读剧本，提取资产：
   - characters：出场角色（id=角色名，description=中文外观/气质描述，shots=出场镜头号数组）
   - scenes：场景（id=场景名，description=中文环境描述，shots=出现镜头号数组）
   - props：道具（id=道具名，description=中文描述，shots=出现镜头号数组）
2. 按时间轴拆分镜头：单镜 2–6 秒；镜头数 × 平均时长 ≈ 目标时长；最后一镜结束时间 = 目标时长；时间范围连续无空档、无重叠。
3. 每个镜头填写：shot_id（从1递增）、time_range（如 "0:00-0:05"）、duration（秒）、scene（场景id）、characters（出场角色id数组）、props（出场道具id数组）、shot_size（景别：特写/近景/中近景/中景/全景/大远景）、camera（机位与运镜，用：固定镜头/推近/拉远/横移/摇摄/跟随/手持微晃 等）、action（画面内容，写实可见的动作）、dialogue（台词原文，无则空字符串）、sfx（音效）、mood（情绪/节奏）、continuity（{"start": 起始状态, "end": 结束状态锁定}）。

【连续性硬规则】
- 镜头 N 的 continuity.end 必须与镜头 N+1 的 continuity.start 一致（人物位置、姿势、视线、朝向、道具所有权与位置）。
- 道具不得凭空出现/消失/换主人/跳位；涉及交接时按因果顺序写（谁先不动、谁接触拿稳、原持有者何时松手）。
- 台词原文逐字保留，标注说话人；台词长度与镜头时长匹配，禁止 3 秒镜头塞一大段对白。
- 每个镜头必须列出实际出场的角色/场景/道具（供资源库引用），未出场的不要写。

【画幅与表演】
- 默认竖屏 9:16 构图意识：人物中近景/特写为主，突出面部表情与眼神；避免全身远景过多。
- 表演符合剧本情绪：表情、肢体、视线方向明确。
- 风格遵循预设（古风/都市/校园/科幻/悬疑/奇幻/甜宠等）。

【输出格式】
只输出一个 JSON 对象，结构如下，不要任何解释或代码块标记：
{
  "storyboard": {
    "episode_title": "第一集",
    "duration_seconds": 180,
    "shots": [ ...每镜一个对象，字段见执行步骤3... ]
  },
  "assets": {
    "characters": [ {"id": "角色A", "description": "...", "shots": [1, 2]} ],
    "scenes": [ {"id": "场景A", "description": "...", "shots": [1]} ],
    "props": [ {"id": "道具A", "description": "...", "shots": [3]} ]
  }
}
```

- [ ] **Step 2: 创建 manju_shot_prompt.txt**

```text
你是 MiniMax H3 视频模型提示词工程师。任务：把一个镜头的分镜数据改写成符合 H3 官方 Ref2VA 规范的提示词。

【输入】
- 本镜数据 JSON：shot（该镜头的分镜字段）、tags（本镜资源标签列表 [["<Picture 1>", "角色A"], ...]）、missing（分镜引用了但未映射的资源名）。

【输出结构（六段式，顺序固定）】
subject_definitions:
<Picture 1> is ...（只定义本镜 tags 中的标签；内容用资源的语义描述，不写"图"字；若该资源对应角色/场景/道具，描述其外观与环境）
...（每个标签一行）
summary:
[reference generation] ...（一句话总结本镜：主体、场景、事件、时长、画幅）
retention_analysis:
<Picture 1> (appears in [Shot 1]): fully_preserved - ...（每个标签一行）
detailed_description:
（先写风格总起句，再写 [Shot 1]；按分镜的景别/机位/动作/台词/情绪展开；台词用 <d>[中文] 原文</d>；画面内可见文字用英文双引号）
overall_soundscape:
（1-4 句英文，全片环境音与物理音效；对白与配乐不写这里；无则写 N/A）
non_diegetic_music:
（1-3 句英文，器乐/速度/节奏/动态；无则写 N/A）

【硬规则】
- 只用本镜 tags 里的标签；分镜中出现但 missing 里的资源不写进 subject_definitions，可在 detailed_description 中忽略。
- 镜头时长不超过 15 秒；时间线连续。
- 竖屏 9:16 构图意识：景别/机位按分镜执行，突出表情与视线。
- 台词逐字保留原文（<d>[中文] ...</d>），不翻译不改写；台词长度与镜头时长匹配。
- 延续分镜 continuity.start 的起始状态，结束落到 continuity.end。
- 运镜写自然英文句：类型 + with small/large amplitude + at slow/fast speed。
- 不新增本镜资源列表外的角色/场景/道具。
- 输出语言按预设：默认结构字段英文、台词/歌词/画面文字保留原语言。
- 只输出提示词正文，不要解释、前言或代码块标记。
```

- [ ] **Step 3: 验证文件存在且非空**

Run:
```bash
Get-ChildItem comfyui-h3-prompt-builder/rules -Filter manju_*.txt | Select-Object Name, Length
```
Expected: 两个文件，每个 Length ≥ 1000。

- [ ] **Step 4: Commit**

```bash
git add comfyui-h3-prompt-builder/rules/manju_storyboard.txt comfyui-h3-prompt-builder/rules/manju_shot_prompt.txt
git commit -m "feat: add manju storyboard and shot prompt rules"
```

---

### Task 2: manju_nodes.py 本地逻辑（TDD）

**Files:**
- Modify: `comfyui-h3-prompt-builder/self_test.py`（先加测试）
- Create: `comfyui-h3-prompt-builder/manju_nodes.py`（后写实现）

- [ ] **Step 1: 追加失败测试**

在 `self_test.py` 的 `import unittest.mock` 之后加 `import manju_nodes  # noqa: E402`，并在文件末尾 `if __name__ == "__main__":` 块之前插入：

```python
class TestManjuPreset(unittest.TestCase):
    def test_build_preset_json(self):
        out = manju_nodes.build_preset_json("古风", "9:16", "180", "自动（英文结构+保留原文）")
        data = json.loads(out)
        self.assertEqual(data["style"], "古风")
        self.assertEqual(data["aspect_ratio"], "9:16")
        self.assertEqual(data["duration"], 180)


class TestManjuMapping(unittest.TestCase):
    def test_parse_basic(self):
        out = manju_nodes.parse_mapping_text("角色A=图1\n场景A=图3", "")
        data = json.loads(out)
        self.assertEqual(data["角色A"], 1)
        self.assertEqual(data["场景A"], 3)

    def test_parse_separators(self):
        out = manju_nodes.parse_mapping_text("角色A：1，角色B：Picture 2，道具A=3", "")
        data = json.loads(out)
        self.assertEqual(data["角色A"], 1)
        self.assertEqual(data["角色B"], 2)
        self.assertEqual(data["道具A"], 3)

    def test_duplicate_number_warning(self):
        out = manju_nodes.parse_mapping_text("角色A=图1\n角色B=图1", "")
        data = json.loads(out)
        self.assertIn("_warnings", data)

    def test_assets_missing_warning(self):
        assets = json.dumps({"characters": [{"id": "角色C", "description": "x", "shots": [1]}]}, ensure_ascii=False)
        out = manju_nodes.parse_mapping_text("角色A=图1", assets)
        data = json.loads(out)
        self.assertTrue(any("角色C" in w for w in data["_warnings"]))


class TestManjuRefs(unittest.TestCase):
    STORYBOARD = json.dumps({
        "episode_title": "测试集",
        "duration_seconds": 12,
        "shots": [
            {"shot_id": 1, "time_range": "0:00-0:05", "duration": 5, "scene": "场景A",
             "characters": ["角色A"], "props": [], "shot_size": "中景", "camera": "固定",
             "action": "角色A走进教室", "dialogue": "你好。", "sfx": "脚步声", "mood": "平静",
             "continuity": {"start": "门口", "end": "讲台前"}},
            {"shot_id": 2, "time_range": "0:05-0:12", "duration": 7, "scene": "场景A",
             "characters": ["角色A", "角色B"], "props": ["道具A"], "shot_size": "近景", "camera": "推近",
             "action": "角色A把道具A递给角色B", "dialogue": "给你。", "sfx": "", "mood": "紧张",
             "continuity": {"start": "讲台前", "end": "角色B拿到道具A"}},
        ],
    }, ensure_ascii=False)
    MAPPING = json.dumps({"角色A": 1, "角色B": 2, "场景A": 3, "道具A": 4}, ensure_ascii=False)

    def test_tags_ordered_and_renumbered(self):
        data = manju_nodes.compute_shot_refs(self.STORYBOARD, self.MAPPING, 2)
        self.assertEqual(data["tags"][0], ["<Picture 1>", "角色A"])
        self.assertEqual(data["tags"][1], ["<Picture 2>", "角色B"])
        self.assertEqual(data["tags"][2], ["<Picture 3>", "场景A"])
        self.assertEqual(data["tags"][3], ["<Picture 4>", "道具A"])
        self.assertEqual(data["missing"], [])

    def test_missing_detected(self):
        mapping = json.dumps({"角色A": 1}, ensure_ascii=False)
        data = manju_nodes.compute_shot_refs(self.STORYBOARD, mapping, 2)
        self.assertIn("角色B", data["missing"])
        self.assertIn("场景A", data["missing"])
        self.assertIn("道具A", data["missing"])

    def test_index_out_of_range(self):
        with self.assertRaises(ValueError):
            manju_nodes.compute_shot_refs(self.STORYBOARD, self.MAPPING, 99)

    def test_wiring_note(self):
        note = manju_nodes.build_wiring_note(self.STORYBOARD, self.MAPPING, 2)
        self.assertIn("<Picture 1>=角色A", note)
        self.assertIn("你的图1", note)


class TestManjuSystemPrompt(unittest.TestCase):
    def test_rules_exist_and_extra_injected(self):
        sp = manju_nodes.build_manju_system_prompt("manju_storyboard.txt", "【本集预设】{}")
        self.assertIn("分镜导演", sp)
        self.assertIn("本集预设", sp)
```

（`self_test.py` 顶部已有的 `import json` 复用；若 `manju_nodes` 未创建，测试运行将报 `ModuleNotFoundError`，即为预期失败。）

- [ ] **Step 2: 运行测试，确认失败**

Run: `python comfyui-h3-prompt-builder/self_test.py`
Expected: FAIL（`ModuleNotFoundError: No module named 'manju_nodes'`）

- [ ] **Step 3: 实现 manju_nodes.py（完整代码）**

`comfyui-h3-prompt-builder/manju_nodes.py`:

```python
"""漫剧分镜生成节点 — 纯标准库实现，复用 nodes.py 的配置与 LLM 调用。"""

import json
import os

try:
    from .nodes import load_config, call_llm, read_text_file
except ImportError:
    from nodes import load_config, call_llm, read_text_file

PLUGIN_DIR = os.path.dirname(os.path.abspath(__file__))
RULES_DIR = os.path.join(PLUGIN_DIR, "rules")

STYLES = ["古风", "都市", "校园", "科幻", "悬疑", "奇幻", "甜宠", "自定义"]
ASPECT_RATIOS = ["9:16", "16:9", "1:1", "4:3", "3:4", "21:9"]
DURATIONS = ["自动", "60", "90", "120", "180", "300"]
OUTPUT_LANGUAGES = ["自动（英文结构+保留原文）", "中文提示词", "全英文"]


def build_preset_json(style, aspect_ratio, duration, output_language):
    """组装漫剧预设 JSON。"""
    preset = {
        "style": style,
        "aspect_ratio": aspect_ratio,
        "duration": None if duration == "自动" else int(duration),
        "output_language": output_language,
    }
    return json.dumps(preset, ensure_ascii=False, indent=2)


def _parse_mapping_line(line):
    for sep in ("=", "："):
        if sep in line:
            name, value = line.split(sep, 1)
            return name.strip(), value.strip()
    return None


def _parse_figure_number(value):
    text = value.strip().lower()
    for prefix in ("图", "picture "):
        if text.startswith(prefix):
            text = text[len(prefix):]
    try:
        return int(text)
    except ValueError:
        return None


def parse_mapping_text(text, assets_json=""):
    """解析 '角色A=图1' 形式的资源映射文本，输出 mapping JSON。"""
    warnings = []
    mapping = {}
    raw = (text or "").strip()
    if raw:
        normalized = raw.replace("，", "\n").replace("、", "\n").replace(",", "\n").replace("；", "\n").replace(";", "\n")
        for line in normalized.splitlines():
            line = line.strip()
            if not line:
                continue
            pair = _parse_mapping_line(line)
            if pair is None:
                warnings.append("无法解析的行：" + line)
                continue
            name, value = pair
            number = _parse_figure_number(value)
            if number is None or number < 1:
                warnings.append("无法解析图号：" + line)
                continue
            if name in mapping:
                warnings.append("重复的资源名：" + name)
            mapping[name] = number
    if assets_json:
        try:
            assets = json.loads(assets_json)
        except Exception:
            warnings.append("assets_json 不是合法 JSON，已跳过校验")
            assets = {}
        known = set()
        for category in ("characters", "scenes", "props"):
            for item in assets.get(category, []):
                known.add(item.get("id", ""))
        for item_id in known:
            if item_id and item_id not in mapping:
                warnings.append("未映射的资源：" + item_id)
    used_numbers = {}
    for name, number in mapping.items():
        if number in used_numbers:
            warnings.append("图号 %d 被多个资源使用：%s / %s" % (number, used_numbers[number], name))
        else:
            used_numbers[number] = name
    out = dict(mapping)
    if warnings:
        out["_warnings"] = warnings
    return json.dumps(out, ensure_ascii=False, indent=2)


def _load_json(value, what):
    if not value or not value.strip():
        raise ValueError(what + " 为空")
    try:
        return json.loads(value)
    except Exception:
        raise ValueError(what + " 不是合法 JSON")


def compute_shot_refs(storyboard_json, mapping_json, shot_index):
    """计算某镜头需要的资源引用（按图号升序，标签重新从 <Picture 1> 编号）。"""
    storyboard = _load_json(storyboard_json, "storyboard_json")
    mapping = _load_json(mapping_json, "mapping_json")
    mapping.pop("_warnings", None)
    shots = storyboard.get("shots", [])
    if not shots:
        raise ValueError("分镜中没有镜头")
    if shot_index < 1 or shot_index > len(shots):
        raise ValueError("镜头序号超出范围（1–%d）" % len(shots))
    shot = shots[shot_index - 1]
    roles = []
    for role in shot.get("characters", []):
        roles.append(role)
    if shot.get("scene"):
        roles.append(shot["scene"])
    for role in shot.get("props", []):
        roles.append(role)
    refs = []
    missing = []
    merged = []
    seen_roles = set()
    used_numbers = {}
    for role in roles:
        if role in seen_roles:
            continue
        seen_roles.add(role)
        number = mapping.get(role)
        if number is None:
            missing.append(role)
            continue
        if number in used_numbers:
            merged.append((role, number, used_numbers[number]))
            continue
        used_numbers[number] = role
        refs.append((number, role))
    refs.sort(key=lambda item: item[0])
    tags = [["<Picture %d>" % i, role] for i, (_, role) in enumerate(refs, 1)]
    return {"refs": refs, "tags": tags, "missing": missing, "merged": merged, "shot": shot}


def build_wiring_note(storyboard_json, mapping_json, shot_index):
    """生成该镜接线说明。"""
    data = compute_shot_refs(storyboard_json, mapping_json, shot_index)
    parts = ["Shot %d 接线：" % shot_index]
    for i, (global_num, role) in enumerate(data["refs"], 1):
        parts.append("<Picture %d>=%s（你的图%d）" % (i, role, global_num))
    if data["missing"]:
        parts.append("缺映射：" + "、".join(data["missing"]))
    for role, number, first_role in data["merged"]:
        parts.append("图号冲突：%s 与 %s 共用图%d，请拆分或换图" % (role, first_role, number))
    if len(data["refs"]) > 9:
        parts.append("警告：本镜引用 %d 张图，超过 H3 上限 9 张，请拆分镜头" % len(data["refs"]))
    return "；".join(parts)


def build_manju_system_prompt(rule_file, extra):
    """组装漫剧 LLM system prompt：规则文件 + 附加数据。"""
    parts = []
    rule = read_text_file(os.path.join(RULES_DIR, rule_file))
    if rule:
        parts.append(rule)
    if extra:
        parts.append(extra)
    return "\n\n".join(parts)


def _extract_json(raw):
    text = (raw or "").strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].strip().startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    try:
        return json.loads(text[start:end + 1])
    except Exception:
        return None


def _build_summary(storyboard):
    shots = storyboard.get("shots", [])
    lines = []
    for shot in shots:
        chars = "、".join(shot.get("characters", []) or [])
        scene = shot.get("scene", "")
        dialogue = shot.get("dialogue", "") or ""
        base = "镜%s %s｜%s｜%s｜%s" % (
            shot.get("shot_id", "?"),
            shot.get("time_range", ""),
            scene,
            chars,
            shot.get("shot_size", ""),
        )
        if dialogue:
            base += "｜台词：" + dialogue
        lines.append(base)
    return "\n".join(lines)


def _llm_args(api_key, model, base_url):
    config = load_config()
    key = (api_key or "").strip() or config.get("api_key", "")
    model_name = (model or "").strip() or config.get("model", "deepseek-v4-flash")
    endpoint = (base_url or "").strip() or config.get("base_url", "https://api.deepseek.com/chat/completions")
    return key, model_name, endpoint, config


class ManjuPreset:
    """漫剧预设：本地组装预设 JSON。"""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "style": (STYLES, {"default": "古风"}),
                "aspect_ratio": (ASPECT_RATIOS, {"default": "9:16"}),
                "duration": (DURATIONS, {"default": "自动"}),
                "output_language": (OUTPUT_LANGUAGES, {"default": "自动（英文结构+保留原文）"}),
            }
        }

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("preset_json",)
    FUNCTION = "build"
    CATEGORY = "MiniMax H3 / 漫剧"

    def build(self, style, aspect_ratio, duration, output_language):
        return (build_preset_json(style, aspect_ratio, duration, output_language),)


class ManjuResourceMapping:
    """漫剧资源映射：本地解析映射文本。"""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "mapping_text": ("STRING", {"multiline": True, "default": "角色A=图1\n场景A=图3"}),
            },
            "optional": {
                "assets_json": ("STRING", {"multiline": True, "default": ""}),
            },
        }

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("mapping_json",)
    FUNCTION = "build"
    CATEGORY = "MiniMax H3 / 漫剧"

    def build(self, mapping_text, assets_json=""):
        return (parse_mapping_text(mapping_text, assets_json),)


class ManjuScriptToStoryboard:
    """漫剧：剧本 → 分镜剧本 + 资源清单 + 摘要。"""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "script": ("STRING", {"multiline": True, "default": "粘贴一集剧本（对白、旁白、场景描述均可）"}),
                "preset_json": ("STRING", {"multiline": True, "default": "{}"}),
            },
            "optional": {
                "api_key": ("STRING", {"default": ""}),
                "model": ("STRING", {"default": ""}),
                "base_url": ("STRING", {"default": ""}),
            },
        }

    RETURN_TYPES = ("STRING", "STRING", "STRING")
    RETURN_NAMES = ("storyboard_json", "assets_json", "summary")
    FUNCTION = "build"
    CATEGORY = "MiniMax H3 / 漫剧"

    def build(self, script, preset_json, api_key="", model="", base_url=""):
        script = (script or "").strip()
        if not script:
            return ("请输入剧本。", "{}", "")
        key, model_name, endpoint, config = _llm_args(api_key, model, base_url)
        if not key:
            return ("未配置 API Key：请在节点 api_key 输入框或 config.json 中填写。", "{}", "")
        extra = "【本集预设】\n" + (preset_json or "{}") + "\n\n【剧本原文】\n" + script
        system = build_manju_system_prompt("manju_storyboard.txt", extra)
        try:
            raw = call_llm(
                endpoint, key, model_name, system, "请根据以上剧本与预设生成分镜 JSON。",
                temperature=config.get("temperature", 0.4),
                max_tokens=config.get("max_tokens", 32768),
            )
        except Exception as exc:
            return ("LLM 调用失败：%s" % (exc,), "{}", "")
        parsed = _extract_json(raw)
        if parsed is None:
            return ("分镜 JSON 解析失败，请重试。模型输出：%s" % raw[:300], "{}", "")
        storyboard = parsed.get("storyboard", parsed)
        storyboard_json = json.dumps(storyboard, ensure_ascii=False, indent=2)
        assets_json = json.dumps(parsed.get("assets", {}), ensure_ascii=False, indent=2)
        return (storyboard_json, assets_json, _build_summary(storyboard))


class ManjuShotPrompt:
    """漫剧：分镜 → 该镜 H3 提示词 + 接线说明。"""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "storyboard_json": ("STRING", {"multiline": True, "default": ""}),
                "mapping_json": ("STRING", {"multiline": True, "default": "{}"}),
                "shot_index": ("INT", {"default": 1, "min": 1, "max": 999}),
            },
            "optional": {
                "api_key": ("STRING", {"default": ""}),
                "model": ("STRING", {"default": ""}),
                "base_url": ("STRING", {"default": ""}),
            },
        }

    RETURN_TYPES = ("STRING", "STRING")
    RETURN_NAMES = ("h3_prompt", "wiring_note")
    FUNCTION = "build"
    CATEGORY = "MiniMax H3 / 漫剧"

    def build(self, storyboard_json, mapping_json, shot_index, api_key="", model="", base_url=""):
        try:
            refs = compute_shot_refs(storyboard_json, mapping_json, shot_index)
        except ValueError as exc:
            return ("错误：%s" % (exc,), "")
        wiring_note = build_wiring_note(storyboard_json, mapping_json, shot_index)
        key, model_name, endpoint, config = _llm_args(api_key, model, base_url)
        if not key:
            return ("未配置 API Key：请在节点 api_key 输入框或 config.json 中填写。", wiring_note)
        extra = "【本镜数据】\n" + json.dumps(
            {"shot": refs["shot"], "tags": refs["tags"], "missing": refs["missing"]},
            ensure_ascii=False, indent=2,
        )
        system = build_manju_system_prompt("manju_shot_prompt.txt", extra)
        try:
            prompt = call_llm(
                endpoint, key, model_name, system, "请按规则生成该镜头的 H3 提示词。",
                temperature=config.get("temperature", 0.4),
                max_tokens=config.get("max_tokens", 32768),
            )
        except Exception as exc:
            return ("LLM 调用失败：%s" % (exc,), wiring_note)
        return (prompt, wiring_note)
```

- [ ] **Step 4: 运行测试，确认通过**

Run: `python comfyui-h3-prompt-builder/self_test.py`
Expected: 原 14 项 + 新增 TestManjuPreset 1 / TestManjuMapping 4 / TestManjuRefs 4 / TestManjuSystemPrompt 1 = 24 项全部 PASS

- [ ] **Step 5: Commit**

```bash
git add comfyui-h3-prompt-builder/manju_nodes.py comfyui-h3-prompt-builder/self_test.py
git commit -m "feat: add manju local logic (preset/mapping/shot refs/wiring)"
```

---

### Task 3: 节点注册 + 接口测试

**Files:**
- Modify: `comfyui-h3-prompt-builder/__init__.py`
- Modify: `comfyui-h3-prompt-builder/self_test.py`

- [ ] **Step 1: 追加接口测试**

在 `self_test.py` 的 TestManjuSystemPrompt 类后、`if __name__` 块前插入：

```python
class TestManjuNodes(unittest.TestCase):
    def test_input_types(self):
        for cls in (
            manju_nodes.ManjuPreset,
            manju_nodes.ManjuScriptToStoryboard,
            manju_nodes.ManjuResourceMapping,
            manju_nodes.ManjuShotPrompt,
        ):
            it = cls.INPUT_TYPES()
            self.assertIn("required", it)

    def test_preset_node(self):
        node = manju_nodes.ManjuPreset()
        out = node.build("古风", "9:16", "120", "自动（英文结构+保留原文）")
        self.assertIn("duration", out[0])

    def test_mapping_node(self):
        node = manju_nodes.ManjuResourceMapping()
        out = node.build("角色A=图1", "")
        self.assertIn("角色A", out[0])

    def test_storyboard_node_empty_script(self):
        node = manju_nodes.ManjuScriptToStoryboard()
        out = node.build("", "{}", api_key="")
        self.assertIn("请输入剧本", out[0])

    def test_shot_prompt_node_bad_json(self):
        node = manju_nodes.ManjuShotPrompt()
        out = node.build("not json", "{}", 1, api_key="")
        self.assertIn("错误：", out[0])
```

- [ ] **Step 2: 运行测试，确认新测试直接通过**

Run: `python comfyui-h3-prompt-builder/self_test.py`
Expected: 29 项全部 PASS（节点类已在 Task 2 完整代码中实现，新增的 5 项接口测试直接通过）

- [ ] **Step 3: 在 manju_nodes.py 末尾追加节点类**

> 说明：Task 2 Step 3 的完整代码块已包含全部 4 个节点类（ManjuPreset / ManjuResourceMapping / ManjuScriptToStoryboard / ManjuShotPrompt）。因此本 Task 的 Step 2 预期应为「新追加的 5 项接口测试直接通过」；若运行发现类缺失，把 Task 2 代码块中的类补全后再继续。本 Task 的重点是节点注册。

- [ ] **Step 4: 更新 __init__.py 注册**

`comfyui-h3-prompt-builder/__init__.py`（整体替换为）:

```python
from .manju_nodes import (
    ManjuPreset,
    ManjuResourceMapping,
    ManjuScriptToStoryboard,
    ManjuShotPrompt,
)
from .nodes import H3PromptBuilder

NODE_CLASS_MAPPINGS = {
    "H3PromptBuilder": H3PromptBuilder,
    "ManjuPreset": ManjuPreset,
    "ManjuScriptToStoryboard": ManjuScriptToStoryboard,
    "ManjuResourceMapping": ManjuResourceMapping,
    "ManjuShotPrompt": ManjuShotPrompt,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "H3PromptBuilder": "H3 Prompt Builder（提示词生成）",
    "ManjuPreset": "漫剧预设",
    "ManjuScriptToStoryboard": "漫剧：剧本→分镜",
    "ManjuResourceMapping": "漫剧：资源映射",
    "ManjuShotPrompt": "漫剧：分镜→镜头提示词",
}

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS"]
```

- [ ] **Step 5: 运行全部测试**

Run: `python comfyui-h3-prompt-builder/self_test.py`
Expected: 全部 PASS（24 + 5 = 29 项）

- [ ] **Step 6: Commit**

```bash
git add comfyui-h3-prompt-builder/__init__.py comfyui-h3-prompt-builder/self_test.py comfyui-h3-prompt-builder/manju_nodes.py
git commit -m "feat: register manju nodes"
```

---

### Task 4: README + 全量测试

**Files:**
- Modify: `comfyui-h3-prompt-builder/README.md`

- [ ] **Step 1: README 追加「漫剧」章节**

在 `README.md` 的「R2V 提示」章节之前插入：

```markdown
## 漫剧分镜流水线（4 节点）

分类：`MiniMax H3 / 漫剧`

1. **漫剧预设**：风格 / 画幅（默认 9:16）/ 单集时长 / 输出语言 → 预设 JSON。
2. **漫剧：剧本→分镜**：粘贴一集剧本 + 预设 JSON → 分镜 JSON + 资源清单 JSON + 摘要。LLM 自动提取角色/场景/道具（中文描述 + 出场镜头号）。
3. **漫剧：资源映射**：填 `角色A=图1`（每行一条，支持 `=`/`：`、`图1`/`Picture 1`/`1`）→ 映射 JSON。可接资源清单做缺失校验。
4. **漫剧：分镜→镜头提示词**：分镜 JSON + 映射 JSON + 镜头序号 → 该镜 H3 提示词 + 接线说明。

使用流程：
- 预设和映射填一次，保存工作流后复用。
- 每个镜头在 R2V 节点上只连接接线说明里列出的图，顺序与 `<Picture N>` 标签一致；不改提示词。
- 镜头数超过 1 时，改「镜头序号」逐镜生成。
- 全部输出用 Show Text / Preview Text 查看。
```

- [ ] **Step 2: 全量测试**

Run: `python comfyui-h3-prompt-builder/self_test.py`
Expected: 29 项全部 PASS

- [ ] **Step 3: Commit**

```bash
git add comfyui-h3-prompt-builder/README.md
git commit -m "docs: add manju pipeline usage"
```

---

### Task 5: 部署 + LLM 实弹验证

**Files:**
- Deploy: 复制插件目录 → `F:\comfyui\ComfyUI-aki-v2\ComfyUI\custom_nodes\ComfyUI-H3-Prompt-Builder`

- [ ] **Step 1: 复制部署**

```powershell
Copy-Item -LiteralPath 'C:\Users\Administrator\Documents\ChatGPT\minimax h3 prompt\comfyui-h3-prompt-builder' -Destination 'F:\comfyui\ComfyUI-aki-v2\ComfyUI\custom_nodes\ComfyUI-H3-Prompt-Builder' -Recurse -Force
```

部署副本 config.json 已含用户 key；如被覆盖，用 Python 重写（UTF-8 无 BOM）：

```python
import json
cfg = {"base_url": "https://api.deepseek.com/chat/completions", "model": "deepseek-v4-flash",
       "api_key": "<用户在对话中提供的 key>", "temperature": 0.4, "max_tokens": 32768}
open("config.json", "w", encoding="utf-8").write(json.dumps(cfg, ensure_ascii=False, indent=2))
```

- [ ] **Step 2: 部署副本离线测试**

Run（部署副本目录）: `python self_test.py`
Expected: 29 项全部 PASS

- [ ] **Step 3: LLM 实弹验证 — 剧本→分镜**

Run（部署副本目录，UTF-8 管道）:

```python
import manju_nodes
node = manju_nodes.ManjuScriptToStoryboard()
out = node.build("第一集：清晨教室，角色A对角色B说：你来了。两人开始对话。", "{}", api_key="", model="", base_url="")
print(out[0][:200])
print(out[1][:200])
```

Expected: `storyboard_json` 与 `assets_json` 为合法 JSON，含 shots 与 assets 字段。

- [ ] **Step 4: LLM 实弹验证 — 分镜→镜头提示词**

用 Step 3 输出的 storyboard_json 与 mapping_json 填入：

```python
import manju_nodes
mapping = manju_nodes.parse_mapping_text("角色A=图1\n角色B=图2\n场景A=图3", "")
node = manju_nodes.ManjuShotPrompt()
out = node.build(storyboard_json, mapping, 1, api_key="", model="", base_url="")
print("wiring:", out[1])
print(out[0][:300])
```

Expected: `wiring_note` 含 `<Picture 1>=角色A（你的图1）`；`h3_prompt` 以 `subject_definitions:` 开头。

---

### Task 6: 手动验证清单（交付给用户）

- [ ] 重启 ComfyUI，确认 `MiniMax H3 / 漫剧` 分类下出现 4 个节点
- [ ] 预设节点输出 JSON 可预览
- [ ] 剧本→分镜：贴一小段剧本运行，分镜/资源清单/摘要三个输出可见
- [ ] 资源映射：填映射文本，mapping JSON 可见
- [ ] 分镜→镜头提示词：接线说明与提示词可见，提示词以 `subject_definitions:` 开头
- [ ] R2V：按接线说明连接图片生成一个镜头

---

## 自检（计划 vs 规格）

- 规格「4 个节点」→ Task 2/3 ✓
- 规格「数据格式（预设/资源清单/分镜/映射 JSON）」→ Task 2 代码中的 schema 与本地函数 ✓
- 规格「本地逻辑可离线测试」→ Task 2 `parse_mapping_text` / `compute_shot_refs` / `build_wiring_note` + 测试 ✓
- 规格「规则文件两个」→ Task 1 ✓
- 规格「错误处理」→ 空剧本/非法 JSON/越界/缺 key/LLM 失败 ✓
- 规格「9 图上限提示」→ `build_wiring_note` 在引用超过 9 张图时输出警告 ✓
- 规格「测试扩展」→ Task 2/3/4 self_test ✓
- 规格「部署与交付」→ Task 5/6 ✓
