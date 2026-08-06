# 漫剧插件 v2 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 `ComfyUI-H3-Prompt-Builder` 的漫剧节点上实现 v2 优化：音频文字策略、LLM 配置节点、固定分镜复用、导出全部、自动建议映射、设定图提示词、分镜低温度、镜头序号步进。

**Architecture:** 全部改动集中在 `manju_nodes.py`（新增 `resolve_llm_config` / `derive_assets_from_storyboard` / `_build_image_prompts` / `_policy_from_preset`，改造 4 个节点类，新增 `ManjuLlmConfig`）、`rules/*.txt`（策略段落）、`config.json`（`manju_temperature`）、`__init__.py`（注册新节点）、`self_test.py`（新测试）、`README.md`。

**Tech Stack:** Python 3 标准库；ComfyUI 自定义节点规范。

**Spec:** `docs/superpowers/specs/2026-08-06-manju-plugin-v2-design.md`

---

### Task 1: config.json + 规则文件策略段落

**Files:**
- Modify: `comfyui-h3-prompt-builder/config.json`
- Modify: `comfyui-h3-prompt-builder/rules/manju_storyboard.txt`
- Modify: `comfyui-h3-prompt-builder/rules/manju_shot_prompt.txt`

- [ ] **Step 1: config.json 增加 manju_temperature**

`comfyui-h3-prompt-builder/config.json` 整体替换为：

```json
{
  "base_url": "https://api.deepseek.com/chat/completions",
  "model": "deepseek-v4-flash",
  "api_key": "",
  "temperature": 0.4,
  "max_tokens": 32768,
  "manju_temperature": 0.2
}
```

- [ ] **Step 2: manju_storyboard.txt 追加画面文字策略**

在 `comfyui-h3-prompt-builder/rules/manju_storyboard.txt` 末尾追加：

```text

【画面文字策略】
- 读取本集预设的 audio_text_policy。
- 策略含「禁字幕」时：分镜不得安排任何画面内文字（字幕、标题、弹窗、水印、装饰文字），台词只作为语音存在。
- 策略为「保留默认」时可正常安排画面文字。
```

- [ ] **Step 3: manju_shot_prompt.txt 追加音频文字策略**

在 `comfyui-h3-prompt-builder/rules/manju_shot_prompt.txt` 末尾追加：

```text

【音频与文字策略】
- 读取本镜数据的 policy 字段。
- 策略含「无BGM」时：non_diegetic_music 必须写 N/A。
- 策略含「禁字幕」时：detailed_description 明确画面不出现任何字幕、文字、标题、水印、装饰文字。
- 策略为「保留默认」时正常处理。
```

- [ ] **Step 4: 验证 JSON 可解析**

Run: `python -c "import json; json.load(open('comfyui-h3-prompt-builder/config.json', encoding='utf-8-sig')); print('config ok')"`
Expected: `config ok`

- [ ] **Step 5: Commit**

```bash
git add comfyui-h3-prompt-builder/config.json comfyui-h3-prompt-builder/rules/manju_storyboard.txt comfyui-h3-prompt-builder/rules/manju_shot_prompt.txt
git commit -m "feat: add manju policy config and rules"
```

---

### Task 2: manju_nodes.py 本地逻辑（TDD）

**Files:**
- Modify: `comfyui-h3-prompt-builder/self_test.py`（先加测试）
- Modify: `comfyui-h3-prompt-builder/manju_nodes.py`（后写实现）

- [ ] **Step 1: 追加失败测试**

在 `self_test.py` 的 `TestManjuNodes` 类之后、`if __name__` 块之前插入：

```python
class TestManjuV2Preset(unittest.TestCase):
    def test_preset_policy(self):
        out = manju_nodes.build_preset_json("古风", "9:16", "120", "自动（英文结构+保留原文）", "仅禁BGM")
        self.assertEqual(json.loads(out)["audio_text_policy"], "仅禁BGM")


class TestDeriveAssets(unittest.TestCase):
    def test_derive_assets(self):
        out = manju_nodes.derive_assets_from_storyboard(TestManjuRefs.STORYBOARD)
        assets = json.loads(out)
        self.assertEqual([c["id"] for c in assets["characters"]], ["角色A", "角色B"])
        self.assertEqual(assets["scenes"][0]["id"], "场景A")
        self.assertEqual(assets["props"][0]["id"], "道具A")
        self.assertIn(2, assets["props"][0]["shots"])


class TestResolveLlm(unittest.TestCase):
    def test_llm_config_overrides_config(self):
        k, m, u, t, cfg, warn = manju_nodes.resolve_llm_config(
            "", "", "", '{"api_key":"k1","model":"m1","base_url":"https://x","temperature":0.3}'
        )
        self.assertEqual(k, "k1")
        self.assertEqual(m, "m1")
        self.assertEqual(u, "https://x")
        self.assertEqual(t, 0.3)
        self.assertIsNone(warn)

    def test_node_field_wins_over_llm_config(self):
        k, _, _, _, _, _ = manju_nodes.resolve_llm_config("k2", "", "", '{"api_key":"k1"}')
        self.assertEqual(k, "k2")

    def test_invalid_llm_config_warns(self):
        _, _, _, _, _, warn = manju_nodes.resolve_llm_config("", "", "", "not json")
        self.assertIn("llm_config", warn)


class TestAutoSuggest(unittest.TestCase):
    ASSETS = json.dumps({
        "characters": [{"id": "角色A", "description": "黑发少年", "shots": [1]}],
        "scenes": [{"id": "场景A", "description": "教室", "shots": [1]}],
        "props": [{"id": "道具A", "description": "盒子", "shots": [1]}],
    }, ensure_ascii=False)

    def test_auto_suggest_mapping(self):
        node = manju_nodes.ManjuResourceMapping()
        out = node.build("", self.ASSETS, False)
        mapping = json.loads(out[0])
        self.assertEqual(mapping["角色A"], 1)
        self.assertEqual(mapping["场景A"], 2)
        self.assertEqual(mapping["道具A"], 3)
        self.assertIn("角色A=图1", out[1])

    def test_image_prompts(self):
        node = manju_nodes.ManjuResourceMapping()
        out = node.build("", self.ASSETS, True)
        self.assertIn("角色A", out[2])
        self.assertIn("黑发少年", out[2])
        self.assertIn("设定图", out[2])


```

- [ ] **Step 2: 运行测试，确认失败**

Run: `python comfyui-h3-prompt-builder/self_test.py`
Expected: FAIL（`AttributeError: module 'manju_nodes' has no attribute 'resolve_llm_config'` 等）

- [ ] **Step 3: 实现本地逻辑（替换/追加代码）**

**3a. 在 `manju_nodes.py` 的常量区追加：**

```python
AUDIO_TEXT_POLICIES = ["禁字幕+无BGM", "仅禁BGM", "仅禁字幕", "保留默认"]
DEFAULT_MANJU_POLICY = "禁字幕+无BGM"
```

**3b. 替换 `build_preset_json`：**

```python
def build_preset_json(style, aspect_ratio, duration, output_language, audio_text_policy=DEFAULT_MANJU_POLICY):
    """组装漫剧预设 JSON。"""
    preset = {
        "style": style,
        "aspect_ratio": aspect_ratio,
        "duration": None if duration == "自动" else int(duration),
        "output_language": output_language,
        "audio_text_policy": audio_text_policy,
    }
    return json.dumps(preset, ensure_ascii=False, indent=2)
```

**3c. 替换 `_llm_args` 为 `resolve_llm_config`：**

```python
def resolve_llm_config(api_key, model, base_url, llm_config_json=""):
    """解析 LLM 参数。优先级：节点单独字段 > llm_config JSON > config.json。"""
    config = load_config()
    overrides = {}
    warning = None
    text = (llm_config_json or "").strip()
    if text:
        try:
            overrides = json.loads(text)
        except Exception:
            warning = "llm_config 不是合法 JSON，已忽略"

    def first(*values):
        for value in values:
            if value is not None and str(value).strip() != "":
                return str(value).strip()
        return None

    key = first(api_key, overrides.get("api_key"), config.get("api_key"))
    model_name = first(model, overrides.get("model"), config.get("model")) or "deepseek-v4-flash"
    endpoint = first(base_url, overrides.get("base_url"), config.get("base_url")) or "https://api.deepseek.com/chat/completions"
    temperature = overrides.get("temperature")
    if temperature is not None:
        try:
            temperature = float(temperature)
        except Exception:
            temperature = None
    return key, model_name, endpoint, temperature, config, warning
```

**3d. 在 `resolve_llm_config` 后追加本地函数：**

```python
def derive_assets_from_storyboard(storyboard_json):
    """从分镜 JSON 反推资源清单（离线，description 为空）。"""
    storyboard = _load_json(storyboard_json, "storyboard_json")
    assets = {"characters": [], "scenes": [], "props": []}
    seen = {"characters": set(), "scenes": set(), "props": set()}

    def add(category, item_id, shot_id):
        if not item_id:
            return
        if item_id in seen[category]:
            item = next(x for x in assets[category] if x["id"] == item_id)
            if shot_id not in item["shots"]:
                item["shots"].append(shot_id)
            return
        seen[category].add(item_id)
        assets[category].append({"id": item_id, "description": "", "shots": [shot_id]})

    for shot in storyboard.get("shots", []):
        shot_id = shot.get("shot_id")
        for cid in shot.get("characters", []):
            add("characters", cid, shot_id)
        add("scenes", shot.get("scene"), shot_id)
        for pid in shot.get("props", []):
            add("props", pid, shot_id)
    return json.dumps(assets, ensure_ascii=False, indent=2)


def _build_image_prompts(assets):
    """根据资源清单生成设定图提示词（本地模板）。"""
    lines = []
    for item in assets.get("characters", []):
        desc = item.get("description", "") or ""
        lines.append("%s：%s，漫剧角色设定图，竖屏9:16，半身立绘，简洁背景，高清" % (item.get("id", "角色"), desc))
    for item in assets.get("scenes", []):
        desc = item.get("description", "") or ""
        lines.append("%s：%s，漫剧场景空镜图，竖屏9:16，无人物，干净构图" % (item.get("id", "场景"), desc))
    for item in assets.get("props", []):
        desc = item.get("description", "") or ""
        lines.append("%s：%s，漫剧道具特写图，竖屏9:16，简洁背景" % (item.get("id", "道具"), desc))
    return "\n".join(lines)


def _policy_from_preset(preset_json, default=DEFAULT_MANJU_POLICY):
    if preset_json and preset_json.strip():
        try:
            preset = json.loads(preset_json)
            return preset.get("audio_text_policy") or default
        except Exception:
            pass
    return default
```

- [ ] **Step 4: 运行测试，确认通过**

Run: `python comfyui-h3-prompt-builder/self_test.py`
Expected: 34 项全部 PASS（29 + TestManjuV2Preset 1 + TestDeriveAssets 1 + TestResolveLlm 3）

> 说明：TestAutoSuggest 依赖资源映射节点的新签名，随 Task 3 一起加入并验证；Task 2 的 Step 1 代码块虽已包含该测试类，实际执行时先跳过（见 Task 3 Step 0）。

- [ ] **Step 5: Commit**

```bash
git add comfyui-h3-prompt-builder/manju_nodes.py comfyui-h3-prompt-builder/self_test.py
git commit -m "feat: add manju v2 local logic (resolve/derive/suggest/image prompts)"
```

---

### Task 3: 节点改造 + ManjuLlmConfig 注册

**Files:**
- Modify: `comfyui-h3-prompt-builder/manju_nodes.py`
- Modify: `comfyui-h3-prompt-builder/__init__.py`

- [ ] **Step 0: 追加依赖节点改造的测试（预期先失败）**

在 `self_test.py` 的 `TestResolveLlm` 类之后、`if __name__` 块之前插入 `TestAutoSuggest`（见 Task 2 Step 1 的代码块）与 `TestManjuV2Nodes`：

```python
class TestManjuV2Nodes(unittest.TestCase):
    def test_fixed_storyboard_skips_llm(self):
        node = manju_nodes.ManjuScriptToStoryboard()
        with unittest.mock.patch.object(manju_nodes, "call_llm", side_effect=AssertionError("不应调用 LLM")):
            out = node.build("随便的剧本", "{}", api_key="", model="", base_url="",
                             llm_config="", fixed_storyboard_json=TestManjuRefs.STORYBOARD)
        sb = json.loads(out[0])
        self.assertEqual(len(sb["shots"]), 2)
        self.assertEqual(sb["_policy"], "禁字幕+无BGM")
        assets = json.loads(out[1])
        self.assertEqual([c["id"] for c in assets["characters"]], ["角色A", "角色B"])

    def test_export_all(self):
        node = manju_nodes.ManjuShotPrompt()
        with unittest.mock.patch.object(manju_nodes, "call_llm", return_value="MOCK_PROMPT"):
            out = node.build(TestManjuRefs.STORYBOARD, TestManjuRefs.MAPPING, 1,
                             api_key="k", export_all=True)
        self.assertIn("=== Shot 1 ===", out[0])
        self.assertIn("=== Shot 2 ===", out[0])
        self.assertIn("MOCK_PROMPT", out[0])
        self.assertIn("Shot 1 接线：", out[1])

    def test_policy_injected(self):
        sb = json.loads(TestManjuRefs.STORYBOARD)
        sb["_policy"] = "仅禁字幕"
        sb_json = json.dumps(sb, ensure_ascii=False)
        captured = []

        def fake_llm(*args, **kwargs):
            captured.append(args[3])
            return "P"

        node = manju_nodes.ManjuShotPrompt()
        with unittest.mock.patch.object(manju_nodes, "call_llm", side_effect=fake_llm):
            node.build(sb_json, TestManjuRefs.MAPPING, 1, api_key="k")
        self.assertIn("仅禁字幕", captured[0])

    def test_llm_config_node(self):
        node = manju_nodes.ManjuLlmConfig()
        out = node.build("", "m1", "https://x", "")
        cfg = json.loads(out[0])
        self.assertEqual(cfg["model"], "m1")
        self.assertNotIn("temperature", cfg)
        out2 = node.build("", "m1", "https://x", "0.3")
        self.assertEqual(json.loads(out2[0])["temperature"], 0.3)

    def test_shot_index_step(self):
        it = manju_nodes.ManjuShotPrompt.INPUT_TYPES()
        self.assertEqual(it["required"]["shot_index"][1].get("step"), 1)
```

同时把 `TestManjuNodes.test_input_types` 中的 4 元组改为包含 `manju_nodes.ManjuLlmConfig`：

```python
        for cls in (
            manju_nodes.ManjuPreset,
            manju_nodes.ManjuScriptToStoryboard,
            manju_nodes.ManjuResourceMapping,
            manju_nodes.ManjuShotPrompt,
            manju_nodes.ManjuLlmConfig,
        ):
```

Run: `python comfyui-h3-prompt-builder/self_test.py`
Expected: 7 项失败（TestAutoSuggest 2 + TestManjuV2Nodes 5），其余 34 项通过

- [ ] **Step 1: 改造 ManjuPreset**

替换整个 `class ManjuPreset`：

```python
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
                "audio_text_policy": (AUDIO_TEXT_POLICIES, {"default": DEFAULT_MANJU_POLICY}),
            }
        }

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("preset_json",)
    FUNCTION = "build"
    CATEGORY = "MiniMax H3 / 漫剧"

    def build(self, style, aspect_ratio, duration, output_language, audio_text_policy=DEFAULT_MANJU_POLICY):
        return (build_preset_json(style, aspect_ratio, duration, output_language, audio_text_policy),)
```

- [ ] **Step 2: 改造 ManjuResourceMapping**

替换整个 `class ManjuResourceMapping`：

```python
class ManjuResourceMapping:
    """漫剧资源映射：解析映射文本；留空时按资源清单自动建议。"""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "mapping_text": ("STRING", {"multiline": True, "default": ""}),
            },
            "optional": {
                "assets_json": ("STRING", {"multiline": True, "default": ""}),
                "generate_image_prompts": ("BOOLEAN", {"default": False}),
            },
        }

    RETURN_TYPES = ("STRING", "STRING", "STRING")
    RETURN_NAMES = ("mapping_json", "suggested_mapping_text", "image_prompts")
    FUNCTION = "build"
    CATEGORY = "MiniMax H3 / 漫剧"

    def build(self, mapping_text, assets_json="", generate_image_prompts=False):
        suggested = ""
        image_prompts = ""
        text = (mapping_text or "").strip()
        assets = {}
        assets_valid = False
        if assets_json and assets_json.strip():
            try:
                assets = json.loads(assets_json)
                assets_valid = True
            except Exception:
                assets_valid = False
        if not text and assets_valid:
            lines = []
            mapping = {}
            number = 1
            for category in ("characters", "scenes", "props"):
                for item in assets.get(category, []):
                    item_id = item.get("id", "")
                    if not item_id:
                        continue
                    mapping[item_id] = number
                    lines.append("%s=图%d" % (item_id, number))
                    number += 1
            if lines:
                suggested = "\n".join(lines)
                mapping_json = parse_mapping_text(suggested, assets_json)
            else:
                mapping_json = parse_mapping_text("", assets_json)
        else:
            mapping_json = parse_mapping_text(text, assets_json)
        if generate_image_prompts and assets_valid:
            image_prompts = _build_image_prompts(assets)
        return (mapping_json, suggested, image_prompts)
```

- [ ] **Step 3: 改造 ManjuScriptToStoryboard**

替换整个 `class ManjuScriptToStoryboard`：

```python
class ManjuScriptToStoryboard:
    """漫剧：剧本 → 分镜剧本 + 资源清单 + 摘要；支持固定分镜复用（跳过 LLM）。"""

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
                "llm_config": ("STRING", {"multiline": True, "default": ""}),
                "fixed_storyboard_json": ("STRING", {"multiline": True, "default": ""}),
            },
        }

    RETURN_TYPES = ("STRING", "STRING", "STRING")
    RETURN_NAMES = ("storyboard_json", "assets_json", "summary")
    FUNCTION = "build"
    CATEGORY = "MiniMax H3 / 漫剧"

    def build(self, script, preset_json, api_key="", model="", base_url="", llm_config="", fixed_storyboard_json=""):
        policy = _policy_from_preset(preset_json)
        if (fixed_storyboard_json or "").strip():
            try:
                storyboard = json.loads(fixed_storyboard_json)
            except Exception:
                return ("固定分镜 JSON 不是合法 JSON。", "{}", "")
            if "_policy" not in storyboard:
                storyboard["_policy"] = policy
            storyboard_json = json.dumps(storyboard, ensure_ascii=False, indent=2)
            assets_json = derive_assets_from_storyboard(storyboard_json)
            return (storyboard_json, assets_json, _build_summary(storyboard))

        script = (script or "").strip()
        if not script:
            return ("请输入剧本。", "{}", "")
        key, model_name, endpoint, temperature, config, warning = resolve_llm_config(api_key, model, base_url, llm_config)
        if not key:
            return ("未配置 API Key：请在 LLM 配置节点、节点 api_key 输入框或 config.json 中填写。", "{}", "")
        extra = "【本集预设】\n" + (preset_json or "{}") + "\n\n【剧本原文】\n" + script
        system = build_manju_system_prompt("manju_storyboard.txt", extra)
        temp = temperature if temperature is not None else config.get("manju_temperature", 0.2)
        try:
            raw = call_llm(
                endpoint, key, model_name, system, "请根据以上剧本与预设生成分镜 JSON。",
                temperature=temp,
                max_tokens=config.get("max_tokens", 32768),
            )
        except Exception as exc:
            return ("LLM 调用失败：%s" % (exc,), "{}", "")
        parsed = _extract_json(raw)
        if parsed is None:
            return ("分镜 JSON 解析失败，请重试。模型输出：%s" % raw[:300], "{}", "")
        storyboard = parsed.get("storyboard", parsed)
        storyboard["_policy"] = policy
        storyboard_json = json.dumps(storyboard, ensure_ascii=False, indent=2)
        assets_json = json.dumps(parsed.get("assets", {}), ensure_ascii=False, indent=2)
        summary = _build_summary(storyboard)
        if warning:
            summary = warning + "\n" + summary
        return (storyboard_json, assets_json, summary)
```

- [ ] **Step 4: 改造 ManjuShotPrompt**

替换整个 `class ManjuShotPrompt`：

```python
class ManjuShotPrompt:
    """漫剧：分镜 → 该镜 H3 提示词 + 接线说明；支持导出全部。"""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "storyboard_json": ("STRING", {"multiline": True, "default": ""}),
                "mapping_json": ("STRING", {"multiline": True, "default": "{}"}),
                "shot_index": ("INT", {"default": 1, "min": 1, "max": 999, "step": 1}),
            },
            "optional": {
                "api_key": ("STRING", {"default": ""}),
                "model": ("STRING", {"default": ""}),
                "base_url": ("STRING", {"default": ""}),
                "llm_config": ("STRING", {"multiline": True, "default": ""}),
                "export_all": ("BOOLEAN", {"default": False}),
            },
        }

    RETURN_TYPES = ("STRING", "STRING")
    RETURN_NAMES = ("h3_prompt", "wiring_note")
    FUNCTION = "build"
    CATEGORY = "MiniMax H3 / 漫剧"

    def build(self, storyboard_json, mapping_json, shot_index, api_key="", model="", base_url="", llm_config="", export_all=False):
        try:
            storyboard = _load_json(storyboard_json, "storyboard_json")
            _load_json(mapping_json, "mapping_json")
        except ValueError as exc:
            return ("错误：%s" % (exc,), "")
        policy = storyboard.get("_policy") or DEFAULT_MANJU_POLICY
        key, model_name, endpoint, temperature, config, warning = resolve_llm_config(api_key, model, base_url, llm_config)
        if not key:
            return ("未配置 API Key：请在 LLM 配置节点、节点 api_key 输入框或 config.json 中填写。", "")
        temp = temperature if temperature is not None else config.get("temperature", 0.4)

        def gen_one(idx):
            refs = compute_shot_refs(storyboard_json, mapping_json, idx)
            wiring = build_wiring_note(storyboard_json, mapping_json, idx)
            extra = "【本镜数据】\n" + json.dumps(
                {"shot": refs["shot"], "tags": refs["tags"], "missing": refs["missing"], "policy": policy},
                ensure_ascii=False, indent=2,
            )
            system = build_manju_system_prompt("manju_shot_prompt.txt", extra)
            prompt = call_llm(
                endpoint, key, model_name, system, "请按规则生成该镜头的 H3 提示词。",
                temperature=temp,
                max_tokens=config.get("max_tokens", 32768),
            )
            return prompt, wiring

        if export_all:
            parts_prompt = []
            parts_wiring = []
            error_lines = []
            for idx in range(1, len(storyboard.get("shots", [])) + 1):
                try:
                    prompt, wiring = gen_one(idx)
                except Exception as exc:
                    error_lines.append("Shot %d 失败：%s" % (idx, exc))
                    break
                parts_prompt.append("=== Shot %d ===\n%s" % (idx, prompt))
                parts_wiring.append("=== Shot %d ===\n%s" % (idx, wiring))
            if error_lines:
                parts_prompt.append("\n".join(error_lines))
                parts_wiring.append("\n".join(error_lines))
            all_prompt = "\n\n".join(parts_prompt)
            all_wiring = "\n\n".join(parts_wiring)
            if warning:
                all_prompt = warning + "\n" + all_prompt
            return (all_prompt, all_wiring)

        try:
            prompt, wiring = gen_one(shot_index)
        except ValueError as exc:
            return ("错误：%s" % (exc,), "")
        except Exception as exc:
            return ("LLM 调用失败：%s" % (exc,), "")
        if warning:
            wiring = warning + "\n" + wiring
        return (prompt, wiring)
```

- [ ] **Step 5: 追加 ManjuLlmConfig 类**

在 `manju_nodes.py` 末尾追加：

```python
class ManjuLlmConfig:
    """漫剧 LLM 配置：填一次，输出 JSON 供其他节点复用。"""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "api_key": ("STRING", {"default": ""}),
                "model": ("STRING", {"default": ""}),
                "base_url": ("STRING", {"default": ""}),
                "temperature": ("STRING", {"default": ""}),
            }
        }

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("llm_config",)
    FUNCTION = "build"
    CATEGORY = "MiniMax H3 / 漫剧"

    def build(self, api_key, model, base_url, temperature):
        cfg = {
            "api_key": (api_key or "").strip(),
            "model": (model or "").strip(),
            "base_url": (base_url or "").strip(),
        }
        temp_text = (temperature or "").strip()
        if temp_text:
            try:
                cfg["temperature"] = float(temp_text)
            except Exception:
                pass
        return (json.dumps(cfg, ensure_ascii=False, indent=2),)
```

- [ ] **Step 6: 注册 ManjuLlmConfig（__init__.py）**

`comfyui-h3-prompt-builder/__init__.py` 整体替换为：

```python
from .manju_nodes import (
    ManjuLlmConfig,
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
    "ManjuLlmConfig": ManjuLlmConfig,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "H3PromptBuilder": "H3 Prompt Builder（提示词生成）",
    "ManjuPreset": "漫剧预设",
    "ManjuScriptToStoryboard": "漫剧：剧本→分镜",
    "ManjuResourceMapping": "漫剧：资源映射",
    "ManjuShotPrompt": "漫剧：分镜→镜头提示词",
    "ManjuLlmConfig": "漫剧：LLM 配置",
}

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS"]
```

- [ ] **Step 7: 运行全部测试**

Run: `python comfyui-h3-prompt-builder/self_test.py`
Expected: 41 项全部 PASS（34 + TestAutoSuggest 2 + TestManjuV2Nodes 5）

- [ ] **Step 8: Commit**

```bash
git add comfyui-h3-prompt-builder/manju_nodes.py comfyui-h3-prompt-builder/self_test.py comfyui-h3-prompt-builder/__init__.py
git commit -m "feat: manju v2 nodes (llm config, fixed storyboard, export all, policy)"
```

---

### Task 4: README + 全量测试

**Files:**
- Modify: `comfyui-h3-prompt-builder/README.md`

- [ ] **Step 1: README 漫剧章节追加 v2 说明**

在 `README.md` 的「漫剧分镜流水线（4 节点）」章节末尾追加：

```markdown

### v2 新功能

- **漫剧：LLM 配置**：api_key/model/base_url/temperature 填一次输出 JSON，接到剧本→分镜与分镜→镜头提示词的 `llm_config` 输入即可复用；优先级：节点单独输入 > llm_config > config.json。
- **音频与文字策略**（预设节点）：默认「禁字幕+无BGM」，镜头提示词强制 `non_diegetic_music: N/A` 且画面无字幕/文字/水印。
- **固定分镜复用**：剧本→分镜节点的 `fixed_storyboard_json` 粘贴已有分镜后跳过 LLM（不花钱、前后一致），资源清单自动反推。
- **导出全部**：分镜→镜头提示词节点打开 `export_all` 一次性输出全部镜头的提示词与接线说明。
- **自动建议映射**：资源映射节点的 `mapping_text` 留空时，按资源清单自动生成 `角色A=图1` 建议（输出在 `suggested_mapping_text`）。
- **设定图提示词**：资源映射节点打开 `generate_image_prompts`，输出角色/场景/道具的设定图提示词（离线）。
- **分镜低温度**：config.json 的 `manju_temperature: 0.2` 降低分镜随机性；`shot_index` 支持步进。
```

- [ ] **Step 2: 全量测试**

Run: `python comfyui-h3-prompt-builder/self_test.py`
Expected: 41 项全部 PASS

- [ ] **Step 3: Commit**

```bash
git add comfyui-h3-prompt-builder/README.md
git commit -m "docs: document manju v2 features"
```

---

### Task 5: 部署 + LLM 实弹验证

**Files:**
- Deploy: 复制插件目录 → `F:\comfyui\ComfyUI-aki-v2\ComfyUI\custom_nodes\ComfyUI-H3-Prompt-Builder`

- [ ] **Step 1: 复制部署（children 覆盖，避免嵌套目录）**

```powershell
$src = 'C:\Users\Administrator\Documents\ChatGPT\minimax h3 prompt\comfyui-h3-prompt-builder'
$dst = 'F:\comfyui\ComfyUI-aki-v2\ComfyUI\custom_nodes\ComfyUI-H3-Prompt-Builder'
Copy-Item -Path (Join-Path $src '*') -Destination $dst -Recurse -Force
```

部署副本 config.json 用 Python 重写（保留用户 key + 新增 manju_temperature，UTF-8 无 BOM）：

```python
import json
cfg = {"base_url": "https://api.deepseek.com/chat/completions", "model": "deepseek-v4-flash",
       "api_key": "<用户在对话中提供的 key>", "temperature": 0.4, "max_tokens": 32768,
       "manju_temperature": 0.2}
open("config.json", "w", encoding="utf-8").write(json.dumps(cfg, ensure_ascii=False, indent=2))
```

- [ ] **Step 2: 部署副本离线测试**

Run（部署副本目录）: `python self_test.py`
Expected: 41 项全部 PASS

- [ ] **Step 3: LLM 实弹验证（复用已生成分镜，跳过剧本→分镜 LLM）**

Run（部署副本目录，UTF-8 管道）:

```python
import json
import manju_nodes

# 固定分镜路径（不调用 LLM）：用已有 manju_sb.json
sb_json = open(r"C:\Users\Administrator\AppData\Local\Temp\manju_sb.json", encoding="utf-8").read()
node = manju_nodes.ManjuScriptToStoryboard()
out = node.build("", "{}", api_key="", model="", base_url="", llm_config="", fixed_storyboard_json=sb_json)
sb = json.loads(out[0])
print("shots:", len(sb["shots"]), "policy:", sb.get("_policy"))
assets = json.loads(out[1])
print("characters:", [c["id"] for c in assets["characters"]])
print("scenes:", [s["id"] for s in assets["scenes"]])

# 自动建议映射
mapping_node = manju_nodes.ManjuResourceMapping()
m_out = mapping_node.build("", out[1], False)
print("suggested:\n", m_out[1])

# 镜头提示词（策略注入：non_diegetic_music 应为 N/A）
shot_node = manju_nodes.ManjuShotPrompt()
shot_out = shot_node.build(out[0], m_out[0], 5, api_key="", model="", base_url="", llm_config="", export_all=False)
print("wiring:", shot_out[1][:120])
print("prompt_prefix:", repr(shot_out[0][:60]))
print("has_N/A_music:", "non_diegetic_music:\nN/A" in shot_out[0] or "non_diegetic_music: N/A" in shot_out[0])
```

Expected: 固定分镜路径无 LLM 调用、建议映射含 `角色A=图1`、镜头提示词以 `subject_definitions:` 开头且含 N/A 音乐。

- [ ] **Step 4: 导出全部小规模验证（2 镜，mock 或真实 LLM）**

用真实 LLM 对 2 个镜头跑一次 `export_all=True`（消耗少量 token），确认输出含 `=== Shot 1 ===` 与 `=== Shot 2 ===`。

---

### Task 6: 手动验证清单（交付给用户）

- [ ] 重启 ComfyUI，确认「漫剧：LLM 配置」节点出现
- [ ] 预设节点出现「音频与文字策略」下拉
- [ ] LLM 配置节点填一次 → 接到两个 LLM 节点，节点单独输入可留空
- [ ] 剧本→分镜：`fixed_storyboard_json` 粘贴旧分镜 → 不调 LLM、资源清单自动反推
- [ ] 资源映射：mapping_text 留空 → 自动建议；打开设定图提示词开关 → 输出图像提示词
- [ ] 分镜→镜头提示词：shot_index 步进；export_all 打开 → 全部镜头提示词
- [ ] 输出提示词含 `non_diegetic_music: N/A` 且无字幕/文字要求

---

## 自检（计划 vs 规格）

- 规格 2.1 config `manju_temperature` → Task 1 ✓
- 规格 2.2 预设 policy → Task 2 3b + Task 3 Step 1 ✓
- 规格 2.3/2.4 LLM 配置节点与 `resolve_llm_config` → Task 2 3c + Task 3 Step 5/6 ✓
- 规格 2.5 固定分镜复用 → Task 2 3d `derive_assets_from_storyboard` + Task 3 Step 3 ✓
- 规格 2.6 导出全部/步进/策略注入 → Task 3 Step 4 ✓
- 规格 2.7 自动建议映射/设定图提示词 → Task 2 3d + Task 3 Step 2 ✓
- 规格 2.8 规则策略段落 → Task 1 Step 2/3 ✓
- 规格 2.9 注册与文档 → Task 3 Step 6 + Task 4 ✓
- 规格 3 错误处理 → fixed 非法 JSON、llm_config 警告、export_all 中途失败、policy 缺省 ✓
- 规格 4 测试清单 → Task 2/3/4 self_test ✓
