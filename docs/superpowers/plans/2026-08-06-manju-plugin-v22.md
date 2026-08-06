# 漫剧插件 v2.2 实现计划（资源映射镜头选择）

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `ManjuResourceMapping` 新增 `shot_index` 输入（0=全部，N=只处理第 N 镜），单镜模式下 `mapping_json` / `suggested_mapping_text` / `per_shot_wiring` 只针对该镜资源。

**Architecture:** 改动集中在 `manju_nodes.py`（INPUT_TYPES + build 末尾过滤逻辑）、`self_test.py`（新增 TestShotSelect）、`README.md`。

**Tech Stack:** Python 3 标准库；ComfyUI 自定义节点规范。

**Spec:** `docs/superpowers/specs/2026-08-06-manju-plugin-v22-design.md`

---

### Task 1: shot_index 输入与过滤逻辑（TDD）

**Files:**
- Modify: `comfyui-h3-prompt-builder/self_test.py`
- Modify: `comfyui-h3-prompt-builder/manju_nodes.py`

- [ ] **Step 1: 追加失败测试**

在 `self_test.py` 的 `TestManjuV2Nodes` 类之后、`if __name__` 块之前插入：

```python
class TestShotSelect(unittest.TestCase):
    def test_filtered_mapping_shot1(self):
        node = manju_nodes.ManjuResourceMapping()
        out = node.build("", TestAutoSuggest.ASSETS, False, TestManjuRefs.STORYBOARD, 1)
        mapping = json.loads(out[0])
        self.assertEqual(mapping, {"角色A": 1, "场景A": 2})
        self.assertIn("角色A=图1", out[1])
        self.assertNotIn("角色B", out[1])
        self.assertIn("Shot 1:", out[3])
        self.assertNotIn("Shot 2:", out[3])

    def test_default_zero_full(self):
        node = manju_nodes.ManjuResourceMapping()
        out = node.build("", TestAutoSuggest.ASSETS, False, TestManjuRefs.STORYBOARD, 0)
        self.assertIn("Shot 1:", out[3])
        self.assertIn("Shot 2:", out[3])

    def test_out_of_range(self):
        node = manju_nodes.ManjuResourceMapping()
        out = node.build("", TestAutoSuggest.ASSETS, False, TestManjuRefs.STORYBOARD, 99)
        self.assertIn("错误：镜头序号超出范围", out[3])
        self.assertIn("道具A", out[0])

    def test_image_prompts_unchanged(self):
        node = manju_nodes.ManjuResourceMapping()
        out = node.build("", TestAutoSuggest.ASSETS, True, TestManjuRefs.STORYBOARD, 1)
        self.assertIn("道具A", out[2])

    def test_input_types_has_shot_index(self):
        it = manju_nodes.ManjuResourceMapping.INPUT_TYPES()
        self.assertEqual(it["optional"]["shot_index"][1].get("default"), 0)
```

- [ ] **Step 2: 运行测试，确认失败**

Run: `python comfyui-h3-prompt-builder/self_test.py`
Expected: FAIL（`ManjuResourceMapping.build() got an unexpected keyword argument 'shot_index'` / `KeyError: 'shot_index'`）

- [ ] **Step 3: 实现**

`manju_nodes.py` 的 `ManjuResourceMapping.INPUT_TYPES` optional 追加：

```python
                "shot_index": ("INT", {"default": 0, "min": 0, "max": 999}),
```

`build` 方法签名改为：

```python
    def build(self, mapping_text, assets_json="", generate_image_prompts=False, storyboard_json="", shot_index=0):
```

在 `build` 末尾（`per_shot_wiring` 计算之后、`return` 之前）追加：

```python
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

- [ ] **Step 4: 运行测试，确认通过**

Run: `python comfyui-h3-prompt-builder/self_test.py`
Expected: 53 项全部 PASS（48 + TestShotSelect 5）

- [ ] **Step 5: Commit**

```bash
git add comfyui-h3-prompt-builder/manju_nodes.py comfyui-h3-prompt-builder/self_test.py
git commit -m "feat: manju resource mapping shot selection"
```

---

### Task 2: README + 全量测试

**Files:**
- Modify: `comfyui-h3-prompt-builder/README.md`

- [ ] **Step 1: README 更新**

README 漫剧章节资源映射一行末尾追加：

```markdown
`shot_index`：0 = 全部镜头（默认），填 N 时只生成第 N 镜的 mapping（mapping_json / suggested_mapping_text / per_shot_wiring 只含该镜资源，图号仍为图库编号）。
```

- [ ] **Step 2: 全量测试**

Run: `python comfyui-h3-prompt-builder/self_test.py`
Expected: 53 项全部 PASS

- [ ] **Step 3: Commit**

```bash
git add comfyui-h3-prompt-builder/README.md
git commit -m "docs: document shot selection"
```

---

### Task 3: 部署 + 验证

**Files:**
- Deploy: 复制插件目录到 `F:\comfyui\ComfyUI-aki-v2\ComfyUI\custom_nodes\ComfyUI-H3-Prompt-Builder`

- [ ] **Step 1: 复制部署（children 覆盖）并重写 config.json（保留 key + thinking_disabled）**

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
Expected: 53 项全部 PASS

- [ ] **Step 3: 实弹验证（离线部分，复用已生成分镜）**

Run（部署副本目录，UTF-8 管道）:

```python
import manju_nodes
sb_json = open(r"C:\Users\Administrator\AppData\Local\Temp\manju_sb.json", encoding="utf-8").read()
node = manju_nodes.ManjuResourceMapping()
out = node.build("", "", False, sb_json, 2)
print(out[1])          # 建议映射：只含第 2 镜资源
print(out[3])          # 接线：只含 Shot 2 一行
```

Expected: 建议映射与接线均只涉及第 2 镜资源。

---

### Task 4: 手动验证清单（交付给用户）

- [ ] 重启 ComfyUI，资源映射节点出现 `shot_index` 输入
- [ ] `shot_index=0` 行为与之前一致；`shot_index=2` 时三个输出只含第 2 镜资源
- [ ] 越界序号时 per_shot_wiring 显示错误提示

---

## 自检（计划 vs 规格）

- 规格 2（shot_index 语义与过滤范围）→ Task 1 ✓
- 规格 2（image_prompts 不变）→ 过滤块未触碰 image_prompts + test_image_prompts_unchanged ✓
- 规格 2（越界提示）→ Task 1 过滤块 + test_out_of_range ✓
- 规格 4 测试 → Task 1/2 ✓
- 规格 5 文档 → Task 2 ✓
