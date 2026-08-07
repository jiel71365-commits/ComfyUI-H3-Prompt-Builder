# 漫剧插件 v2.3 实现计划（图像提示词 LLM 生成）

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 资源映射节点的图像提示词从本地模板升级为三档模式（LLM 生成默认 / 离线模板保底 / 关闭），新增 `rules/manju_image_prompt.txt` 规则文件。

**Architecture:** 改动集中在 `manju_nodes.py`（`image_prompt_mode` 枚举、`_build_image_prompts` 增强、新增 `_build_image_prompts_llm`）、新增 `rules/manju_image_prompt.txt`、`self_test.py`（更新旧调用 + 新增 TestImagePromptMode）、`README.md`。

**Tech Stack:** Python 3 标准库；ComfyUI 自定义节点规范。

**Spec:** `docs/superpowers/specs/2026-08-06-manju-plugin-v23-design.md`

---

### Task 1: 模式改造 + 离线模板增强（TDD）

**Files:**
- Modify: `comfyui-h3-prompt-builder/self_test.py`
- Modify: `comfyui-h3-prompt-builder/manju_nodes.py`

- [ ] **Step 1: 更新旧测试并追加模式测试**

把 `self_test.py` 中所有 `node.build(..., False)` / `node.build(..., True)` 的位置参数第 3 个改为模式字符串：

- `TestAutoSuggest.test_auto_suggest_mapping`：`node.build("", self.ASSETS, False)` → `node.build("", self.ASSETS, "关闭")`
- `TestAutoSuggest.test_image_prompts`：`node.build("", self.ASSETS, True)` → `node.build("", self.ASSETS, "离线模板")`，并追加断言 `self.assertIn("三视图", out[2])`
- `TestShotSelect` 中所有第 3 个参数 `False` → `"关闭"`（test_filtered_mapping_shot1 / test_default_zero_full / test_out_of_range / test_derive_assets_when_missing）
- `TestShotSelect.test_image_prompts_unchanged`：`node.build("", TestAutoSuggest.ASSETS, True, ...)` → `node.build("", TestAutoSuggest.ASSETS, "离线模板", ...)`
- `TestManjuV2Nodes.test_per_shot_wiring_output` / `test_per_shot_wiring_empty_without_storyboard`：`False` → `"关闭"`

在 `TestShotSelect` 类后追加：

```python
class TestImagePromptMode(unittest.TestCase):
    def test_default_mode(self):
        it = manju_nodes.ManjuResourceMapping.INPUT_TYPES()
        self.assertEqual(it["optional"]["image_prompt_mode"][1].get("default"), "LLM 生成")

    def test_off_mode_empty(self):
        node = manju_nodes.ManjuResourceMapping()
        out = node.build("", TestAutoSuggest.ASSETS, "关闭")
        self.assertEqual(out[2], "")

    def test_rules_file_content(self):
        content = manju_nodes.read_text_file(os.path.join(manju_nodes.RULES_DIR, "manju_image_prompt.txt"))
        for keyword in ("三视图", "面部特写", "双手自然垂下"):
            self.assertIn(keyword, content)
```

- [ ] **Step 2: 运行测试，确认失败**

Run: `python comfyui-h3-prompt-builder/self_test.py`
Expected: FAIL（旧参数 `True/False` 传入 `image_prompt_mode` 导致断言失败 / `KeyError: 'image_prompt_mode'` / 规则文件缺失）

- [ ] **Step 3: 新增规则文件**

`comfyui-h3-prompt-builder/rules/manju_image_prompt.txt`：

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

- [ ] **Step 4: 实现节点改造**

`manju_nodes.py`：

**4a. 常量区追加：**

```python
IMAGE_PROMPT_MODES = ["LLM 生成", "离线模板", "关闭"]
```

**4b. `ManjuResourceMapping.INPUT_TYPES` optional 改为：**

```python
            "optional": {
                "assets_json": ("STRING", {"multiline": True, "default": ""}),
                "image_prompt_mode": (IMAGE_PROMPT_MODES, {"default": "LLM 生成"}),
                "storyboard_json": ("STRING", {"multiline": True, "default": ""}),
                "shot_index": ("INT", {"default": 0, "min": 0, "max": 999}),
                "preset_json": ("STRING", {"multiline": True, "default": "{}"}),
                "api_key": ("STRING", {"default": ""}),
                "model": ("STRING", {"default": ""}),
                "base_url": ("STRING", {"default": ""}),
                "llm_config": ("STRING", {"multiline": True, "default": ""}),
            },
```

**4c. `_build_image_prompts` 替换（增强模板，支持风格与三视图）：**

```python
def _build_image_prompts(assets, style=""):
    """根据资源清单生成设定图提示词（本地模板，离线）。"""
    style_suffix = "，%s风格" % style if style else ""
    lines = []
    for item in assets.get("characters", []):
        desc = item.get("description", "") or ""
        lines.append("%s：%s，漫剧角色设定图（全身三视图正面/侧面/背面并排+面部特写，双手自然垂下），竖屏9:16，简洁纯色背景，柔和均匀光，高清%s" % (item.get("id", "角色"), desc, style_suffix))
    for item in assets.get("scenes", []):
        desc = item.get("description", "") or ""
        lines.append("%s：%s，漫剧场景空镜图，竖屏9:16，无人物，干净构图%s" % (item.get("id", "场景"), desc, style_suffix))
    for item in assets.get("props", []):
        desc = item.get("description", "") or ""
        lines.append("%s：%s，漫剧道具特写图，竖屏9:16，简洁背景%s" % (item.get("id", "道具"), desc, style_suffix))
    return "\n".join(lines)
```

**4d. 新增 `_style_from_preset`：**

```python
def _style_from_preset(preset_json):
    if preset_json and preset_json.strip():
        try:
            preset = json.loads(preset_json)
            return preset.get("style") or ""
        except Exception:
            pass
    return ""
```

**4e. `ManjuResourceMapping.build` 签名与逻辑：**

```python
    def build(self, mapping_text, assets_json="", image_prompt_mode="LLM 生成", storyboard_json="", shot_index=0,
              preset_json="{}", api_key="", model="", base_url="", llm_config=""):
        suggested = ""
        image_prompts = ""
        text = (mapping_text or "").strip()
        assets = {}
        assets_valid = False
        assets_str = ""
        if assets_json and assets_json.strip():
            try:
                assets = json.loads(assets_json)
                assets_valid = True
                assets_str = assets_json.strip()
            except Exception:
                assets_valid = False
        if not text and not assets_valid and storyboard_json and storyboard_json.strip():
            try:
                assets = json.loads(derive_assets_from_storyboard(storyboard_json))
                assets_valid = True
                assets_str = json.dumps(assets, ensure_ascii=False)
            except Exception:
                pass
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
        style = _style_from_preset(preset_json)
        if image_prompt_mode == "LLM 生成":
            if assets_valid:
                image_prompts = _build_image_prompts_llm(assets_str, preset_json, api_key, model, base_url, llm_config)
        elif image_prompt_mode == "离线模板" and assets_valid:
            image_prompts = _build_image_prompts(assets, style)
        per_shot_wiring = ""
        if storyboard_json and storyboard_json.strip():
            per_shot_wiring = build_per_shot_wiring(storyboard_json, mapping_json)
        if shot_index > 0 and storyboard_json and storyboard_json.strip():
            try:
                data = compute_shot_refs(storyboard_json, mapping_json, shot_index)
            except ValueError:
                per_shot_wiring = "错误：镜头序号超出范围"
            else:
                filtered = {role: num for num, role in data["refs"]}
                mapping_json = json.dumps(filtered, ensure_ascii=False, indent=2) if filtered else "{}"
                suggested = "\n".join("%s=图%d" % (role, num) for num, role in data["refs"])
                parts = []
                for i, (num, role) in enumerate(data["refs"], 1):
                    parts.append("<Picture %d>=%s（图库第 %d 张）" % (i, role, num))
                if data["missing"]:
                    parts.append("缺映射：" + "、".join(data["missing"]))
                per_shot_wiring = "Shot %d: %s" % (shot_index, "、".join(parts))
        return (mapping_json, suggested, image_prompts, per_shot_wiring)
```

- [ ] **Step 5: 运行测试**

Run: `python comfyui-h3-prompt-builder/self_test.py`
Expected: 57 项全部 PASS（54 + TestImagePromptMode 3）

- [ ] **Step 6: Commit**

```bash
git add comfyui-h3-prompt-builder/manju_nodes.py comfyui-h3-prompt-builder/self_test.py comfyui-h3-prompt-builder/rules/manju_image_prompt.txt
git commit -m "feat: image prompt mode switch and enhanced offline template"
```

---

### Task 2: LLM 图像提示词生成（TDD）

**Files:**
- Modify: `comfyui-h3-prompt-builder/self_test.py`
- Modify: `comfyui-h3-prompt-builder/manju_nodes.py`

- [ ] **Step 1: 追加测试**

在 `TestImagePromptMode` 类内追加：

```python
    def test_llm_mode_calls_llm(self):
        captured = []

        def fake_llm(*args, **kwargs):
            captured.append((args[3], args[4]))
            return "MOCK_IMAGE_PROMPTS"

        node = manju_nodes.ManjuResourceMapping()
        with unittest.mock.patch.object(manju_nodes, "call_llm", side_effect=fake_llm):
            out = node.build("", TestAutoSuggest.ASSETS, "LLM 生成", "", 0, '{"style":"古风"}', api_key="k")
        system, user_msg = captured[0]
        self.assertIn("美术设定师", system)
        self.assertIn("资源清单", user_msg)
        self.assertIn("古风", user_msg)
        self.assertEqual(out[2], "MOCK_IMAGE_PROMPTS")

    def test_llm_mode_failure_message(self):
        node = manju_nodes.ManjuResourceMapping()
        with unittest.mock.patch.object(manju_nodes, "call_llm", side_effect=RuntimeError("boom")):
            out = node.build("", TestAutoSuggest.ASSETS, "LLM 生成", "", 0, "{}", api_key="k")
        self.assertIn("图像提示词生成失败", out[2])
```

- [ ] **Step 2: 运行测试，确认失败**

Run: `python comfyui-h3-prompt-builder/self_test.py`
Expected: FAIL（`module 'manju_nodes' has no attribute '_build_image_prompts_llm'`）

- [ ] **Step 3: 实现 `_build_image_prompts_llm`**

在 `manju_nodes.py` 的 `_build_image_prompts` 后追加：

```python
def _build_image_prompts_llm(assets_json, preset_json, api_key, model, base_url, llm_config):
    """调用 LLM 生成设定图提示词（规则文件 manju_image_prompt.txt）。"""
    key, model_name, endpoint, temperature, config, warning = resolve_llm_config(api_key, model, base_url, llm_config)
    if not key:
        return "图像提示词生成失败：未配置 API Key"
    system = build_manju_system_prompt("manju_image_prompt.txt", "")
    user_msg = (
        "【资源清单】\n" + (assets_json or "{}")
        + "\n\n【本集预设】\n" + (preset_json or "{}")
        + "\n\n请按规则生成全部设定图提示词。"
    )
    try:
        out = call_llm(
            endpoint, key, model_name, system, user_msg,
            temperature=temperature if temperature is not None else config.get("temperature", 0.4),
            max_tokens=config.get("max_tokens", 32768),
        )
        if warning:
            out = warning + "\n" + out
        return out
    except Exception as exc:
        return "图像提示词生成失败：%s" % (exc,)
```

- [ ] **Step 4: 运行测试，确认通过**

Run: `python comfyui-h3-prompt-builder/self_test.py`
Expected: 59 项全部 PASS（57 + 新增 2）

- [ ] **Step 5: Commit**

```bash
git add comfyui-h3-prompt-builder/manju_nodes.py comfyui-h3-prompt-builder/self_test.py
git commit -m "feat: llm image prompt generation"
```

---

### Task 3: README + 全量测试

**Files:**
- Modify: `comfyui-h3-prompt-builder/README.md`

- [ ] **Step 1: README 更新**

README 漫剧章节设定图提示词一行改为：

```markdown
- **设定图提示词**：资源映射节点 `image_prompt_mode` 默认 `LLM 生成`（按规则文件生成角色三视图+面部特写合成表 / 场景空镜 / 道具特写，模型无关），可选 `离线模板`（零成本保底）或 `关闭`。
```

- [ ] **Step 2: 全量测试**

Run: `python comfyui-h3-prompt-builder/self_test.py`
Expected: 59 项全部 PASS

- [ ] **Step 3: Commit**

```bash
git add comfyui-h3-prompt-builder/README.md
git commit -m "docs: document image prompt modes"
```

---

### Task 4: 部署 + 实弹验证

**Files:**
- Deploy: 复制插件目录到 `F:\comfyui\ComfyUI-aki-v2\ComfyUI\custom_nodes\ComfyUI-H3-Prompt-Builder`

- [ ] **Step 1: 复制部署（children 覆盖）并重写 config.json（保留 key / thinking_disabled / manju_temperature）**

```powershell
$src = 'C:\Users\Administrator\Documents\ChatGPT\minimax h3 prompt\comfyui-h3-prompt-builder'
$dst = 'F:\comfyui\ComfyUI-aki-v2\ComfyUI\custom_nodes\ComfyUI-H3-Prompt-Builder'
Copy-Item -Path (Join-Path $src '*') -Destination $dst -Recurse -Force
```

```python
import json
cfg = {"base_url": "https://api.deepseek.com/chat/completions", "model": "deepseek-v4-flash",
       "api_key": "<用户在对话中提供的 key>", "temperature": 0.4, "max_tokens": 32768,
       "manju_temperature": 0.2, "thinking_disabled": True}
open("config.json", "w", encoding="utf-8").write(json.dumps(cfg, ensure_ascii=False, indent=2))
```

- [ ] **Step 2: 部署副本离线测试**

Run（部署副本目录）: `python self_test.py`
Expected: 59 项全部 PASS

- [ ] **Step 3: LLM 实弹验证（生成一次设定图提示词）**

Run（部署副本目录，UTF-8 管道）:

```python
import json
import manju_nodes

assets = json.dumps({
    "characters": [{"id": "角色A", "description": "黑发少年，穿深蓝校服", "shots": [1]}],
    "scenes": [{"id": "清晨教室", "description": "阳光洒进教室", "shots": [1]}],
}, ensure_ascii=False)
node = manju_nodes.ManjuResourceMapping()
out = node.build("", assets, "LLM 生成", "", 0, '{"style":"校园"}', api_key="", model="", base_url="", llm_config="")
print(out[2][:600])
```

Expected: 输出含 `角色A设定图：`、`三视图`、`校园` 风格描述与负面块，无「生成失败」。

---

### Task 5: 手动验证清单（交付给用户）

- [ ] 重启 ComfyUI，资源映射节点出现 `image_prompt_mode` 下拉（默认 LLM 生成）
- [ ] 接资源清单（或仅接分镜）运行，`image_prompts` 输出含角色三视图+面部特写、场景空镜、道具特写与负面块
- [ ] 切到 `离线模板` 验证零成本保底；`关闭` 输出为空
- [ ] 用输出提示词在即梦 / image2 / ComfyUI 生图模型测试出图效果

---

## 自检（计划 vs 规格）

- 规格 2（三档模式默认 LLM）→ Task 1 ✓
- 规格 3（规则文件内容）→ Task 1 Step 3 ✓
- 规格 4（模板增强/LLM 调用/失败处理/输入）→ Task 1 + Task 2 ✓
- 规格 5（测试清单）→ Task 1/2/3 ✓
- 规格 6（README）→ Task 3 ✓
