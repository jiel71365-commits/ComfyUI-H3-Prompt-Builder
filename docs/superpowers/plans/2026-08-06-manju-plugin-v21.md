# 漫剧插件 v2.1 实现计划（逐镜接线汇总 + 措辞优化）

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 资源映射节点新增「逐镜接线汇总」输出（per_shot_wiring），并把接线说明措辞改为以资源名为主、图号标注为「图库第 N 张」。

**Architecture:** 改动集中在 `manju_nodes.py`：`build_wiring_note` 措辞 + 新增 `build_per_shot_wiring` + `ManjuResourceMapping` 增加输入/输出；`self_test.py` 更新与新增测试；`README.md` 更新。

**Tech Stack:** Python 3 标准库；ComfyUI 自定义节点规范。

**Spec:** `docs/superpowers/specs/2026-08-06-manju-plugin-v21-design.md`

---

### Task 1: build_per_shot_wiring + 措辞优化（TDD）

**Files:**
- Modify: `comfyui-h3-prompt-builder/self_test.py`
- Modify: `comfyui-h3-prompt-builder/manju_nodes.py`

- [ ] **Step 1: 更新/追加测试**

把 `TestManjuRefs.test_wiring_note` 中的断言改为：

```python
    def test_wiring_note(self):
        note = manju_nodes.build_wiring_note(self.STORYBOARD, self.MAPPING, 2)
        self.assertIn("<Picture 1>=角色A", note)
        self.assertIn("图库第 1 张", note)
        self.assertNotIn("你的图", note)
```

在 `TestManjuRefs` 类内追加：

```python
    def test_per_shot_wiring(self):
        out = manju_nodes.build_per_shot_wiring(self.STORYBOARD, self.MAPPING)
        self.assertIn("Shot 1:", out)
        self.assertIn("Shot 2:", out)
        self.assertIn("角色A", out)
        self.assertIn("图库第 1 张", out)
        self.assertNotIn("你的图", out)

    def test_per_shot_wiring_invalid(self):
        self.assertEqual(manju_nodes.build_per_shot_wiring("bad", "{}"), "")
```

- [ ] **Step 2: 运行测试，确认失败**

Run: `python comfyui-h3-prompt-builder/self_test.py`
Expected: FAIL（`module 'manju_nodes' has no attribute 'build_per_shot_wiring'` + `test_wiring_note` 断言失败）

- [ ] **Step 3: 实现**

把 `manju_nodes.py` 中 `build_wiring_note` 的一行改为：

```python
        parts.append("<Picture %d>=%s（图库第 %d 张）" % (i, role, global_num))
```

并在 `build_wiring_note` 函数后追加：

```python
def build_per_shot_wiring(storyboard_json, mapping_json):
    """逐镜接线汇总（离线）：每镜一行，列出该镜需要连接的参考图。"""
    try:
        storyboard = _load_json(storyboard_json, "storyboard_json")
        _load_json(mapping_json, "mapping_json")
    except ValueError:
        return ""
    shots = storyboard.get("shots", [])
    if not shots:
        return ""
    lines = []
    for idx in range(1, len(shots) + 1):
        try:
            data = compute_shot_refs(storyboard_json, mapping_json, idx)
        except ValueError:
            continue
        parts = []
        for i, (global_num, role) in enumerate(data["refs"], 1):
            parts.append("<Picture %d>=%s（图库第 %d 张）" % (i, role, global_num))
        if data["missing"]:
            parts.append("缺映射：" + "、".join(data["missing"]))
        lines.append("Shot %d: %s" % (idx, "、".join(parts)))
    return "\n".join(lines)
```

- [ ] **Step 4: 运行测试，确认通过**

Run: `python comfyui-h3-prompt-builder/self_test.py`
Expected: 43 项全部 PASS（41 + 新增 2）

- [ ] **Step 5: Commit**

```bash
git add comfyui-h3-prompt-builder/manju_nodes.py comfyui-h3-prompt-builder/self_test.py
git commit -m "feat: add per-shot wiring summary and wording polish"
```

---

### Task 2: ManjuResourceMapping 新增输入/输出

**Files:**
- Modify: `comfyui-h3-prompt-builder/manju_nodes.py`
- Modify: `comfyui-h3-prompt-builder/self_test.py`

- [ ] **Step 1: 追加测试**

在 `TestManjuV2Nodes` 类内追加：

```python
    def test_per_shot_wiring_output(self):
        node = manju_nodes.ManjuResourceMapping()
        out = node.build("", TestAutoSuggest.ASSETS, False, TestManjuRefs.STORYBOARD)
        self.assertIn("Shot 1:", out[3])

    def test_per_shot_wiring_empty_without_storyboard(self):
        node = manju_nodes.ManjuResourceMapping()
        out = node.build("", TestAutoSuggest.ASSETS, False)
        self.assertEqual(out[3], "")
```

- [ ] **Step 2: 运行测试，确认失败**

Run: `python comfyui-h3-prompt-builder/self_test.py`
Expected: FAIL（`ManjuResourceMapping.build() got an unexpected keyword argument 'storyboard_json'` 或索引越界）

- [ ] **Step 3: 实现节点改动**

把 `ManjuResourceMapping` 的 `INPUT_TYPES` 中 optional 改为：

```python
            "optional": {
                "assets_json": ("STRING", {"multiline": True, "default": ""}),
                "generate_image_prompts": ("BOOLEAN", {"default": False}),
                "storyboard_json": ("STRING", {"multiline": True, "default": ""}),
            },
```

`RETURN_TYPES` / `RETURN_NAMES` 改为：

```python
    RETURN_TYPES = ("STRING", "STRING", "STRING", "STRING")
    RETURN_NAMES = ("mapping_json", "suggested_mapping_text", "image_prompts", "per_shot_wiring")
```

`build` 方法签名与末尾改为：

```python
    def build(self, mapping_text, assets_json="", generate_image_prompts=False, storyboard_json=""):
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
        per_shot_wiring = ""
        if storyboard_json and storyboard_json.strip():
            per_shot_wiring = build_per_shot_wiring(storyboard_json, mapping_json)
        return (mapping_json, suggested, image_prompts, per_shot_wiring)
```

- [ ] **Step 4: 运行测试，确认通过**

Run: `python comfyui-h3-prompt-builder/self_test.py`
Expected: 45 项全部 PASS（43 + 新增 2）

- [ ] **Step 5: Commit**

```bash
git add comfyui-h3-prompt-builder/manju_nodes.py comfyui-h3-prompt-builder/self_test.py
git commit -m "feat: manju resource mapping per-shot wiring output"
```

---

### Task 3: README + 全量测试

**Files:**
- Modify: `comfyui-h3-prompt-builder/README.md`

- [ ] **Step 1: README 更新**

把 README 漫剧章节中资源映射相关的一行改为：

```markdown
3. **漫剧：资源映射**：填 `角色A=图1`（每行一条，支持 `=`/`：`、`图1`/`Picture 1`/`1`）→ 映射 JSON。可接资源清单做缺失校验；`mapping_text` 留空时自动生成建议；接 `storyboard_json` 后第 4 个输出 `per_shot_wiring` 给出每镜接线汇总（图号显示为「图库第 N 张」，只是图库索引，每镜连接数 ≤9）。
```

- [ ] **Step 2: 全量测试**

Run: `python comfyui-h3-prompt-builder/self_test.py`
Expected: 45 项全部 PASS

- [ ] **Step 3: Commit**

```bash
git add comfyui-h3-prompt-builder/README.md
git commit -m "docs: document per-shot wiring output"
```

---

### Task 4: 部署 + 验证

**Files:**
- Deploy: 复制插件目录到 `F:\comfyui\ComfyUI-aki-v2\ComfyUI\custom_nodes\ComfyUI-H3-Prompt-Builder`

- [ ] **Step 1: 复制部署（children 覆盖）并保持 config.json**

```powershell
$src = 'C:\Users\Administrator\Documents\ChatGPT\minimax h3 prompt\comfyui-h3-prompt-builder'
$dst = 'F:\comfyui\ComfyUI-aki-v2\ComfyUI\custom_nodes\ComfyUI-H3-Prompt-Builder'
Copy-Item -Path (Join-Path $src '*') -Destination $dst -Recurse -Force
```

复制后用 Python 重写部署副本 config.json（保留用户 key，UTF-8 无 BOM）：

```python
import json
cfg = {"base_url": "https://api.deepseek.com/chat/completions", "model": "deepseek-v4-flash",
       "api_key": "<用户在对话中提供的 key>", "temperature": 0.4, "max_tokens": 32768,
       "manju_temperature": 0.2}
open("config.json", "w", encoding="utf-8").write(json.dumps(cfg, ensure_ascii=False, indent=2))
```

- [ ] **Step 2: 部署副本离线测试**

Run（部署副本目录）: `python self_test.py`
Expected: 45 项全部 PASS

- [ ] **Step 3: 实弹验证（离线部分，复用已生成分镜）**

Run（部署副本目录，UTF-8 管道）:

```python
import manju_nodes
sb_json = open(r"C:\Users\Administrator\AppData\Local\Temp\manju_sb.json", encoding="utf-8").read()
mapping_json = manju_nodes.parse_mapping_text("角色A=图1\n角色B=图2\n清晨教室=图3\n盒子=图4", "")
out = manju_nodes.build_per_shot_wiring(sb_json, mapping_json)
print(out.splitlines()[0])
print(out.splitlines()[1])
node = manju_nodes.ManjuResourceMapping()
res = node.build("", "", False, sb_json)
print("4th output non-empty:", len(res[3]) > 0)
```

Expected: 前两行形如 `Shot 1: <Picture 1>=清晨教室（图库第 3 张）`，且不含「你的图」；第 4 输出非空。

---

### Task 5: 手动验证清单（交付给用户）

- [ ] 重启 ComfyUI，资源映射节点出现 `storyboard_json` 输入与 `per_shot_wiring` 输出
- [ ] 接好分镜后查看 per_shot_wiring：每镜一行、每镜连接数 ≤9、图号标注为「图库第 N 张」
- [ ] 分镜→镜头提示词的接线说明同样为「图库第 N 张」措辞

---

## 自检（计划 vs 规格）

- 规格 A（逐镜接线汇总）→ Task 1 `build_per_shot_wiring` + Task 2 节点输入/输出 ✓
- 规格 B（措辞优化）→ Task 1 `build_wiring_note` 措辞 + 测试断言 ✓
- 规格 5 测试 → Task 1/2 self_test ✓
- 规格 6 文档 → Task 3 ✓
- 规格 7 不做（C/D）→ 无相关任务 ✓
