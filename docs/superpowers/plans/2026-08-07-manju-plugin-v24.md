# 漫剧插件 v2.4 实现计划（设定图提示词拆分 + 分镜质量增强 + 导演审阅）

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 新增独立「漫剧：设定图提示词」节点、资源映射默认关闭图像提示词、升级分镜规则、新增「漫剧：导演审阅」节点（审阅直到 PASS，`max_review_rounds` 兜底），并让 `call_llm` 支持 config 超时。

**Architecture:** 改动集中在 `comfyui-h3-prompt-builder` 插件：`nodes.py` 一处超时默认值、`manju_nodes.py` 新增两个节点类与审阅循环、`rules/` 新增 `manju_review.txt` 并升级 `manju_storyboard.txt`、`__init__.py` 注册节点、`self_test.py` 补测试。分镜 JSON 顶层结构不变，向后兼容现有节点。

**Tech Stack:** Python 3、ComfyUI 自定义节点（标准库 urllib）、unittest + mock。

**仓库根：** `C:\Users\Administrator\Documents\ChatGPT\minimax h3 prompt`（git 根，插件在子目录 `comfyui-h3-prompt-builder\`）。测试命令：`cd comfyui-h3-prompt-builder; python self_test.py`。

---

### 前置：建分支并确认测试基线

- [ ] **Step 1: 建分支**

```bash
cd "C:\Users\Administrator\Documents\ChatGPT\minimax h3 prompt"
git checkout -b codex/v2.4
```

Expected: `Switched to a new branch 'codex/v2.4'`

- [ ] **Step 2: 跑基线测试**

```bash
cd comfyui-h3-prompt-builder
python self_test.py
```

Expected: 59 个测试全部通过（`OK`）。

---

### Task 1: `call_llm` 支持 `request_timeout`

**Files:**
- Modify: `comfyui-h3-prompt-builder/nodes.py:98-103`
- Test: `comfyui-h3-prompt-builder/self_test.py`

- [ ] **Step 1: 写失败测试**（追加到 `self_test.py` 末尾 `TestCallLlmRetry` 之后）

```python
class TestRequestTimeout(unittest.TestCase):
    def _patch_llm(self, cfg, timeout_arg=None):
        captured = {}

        class FakeResp:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def read(self):
                return b'{"choices":[{"message":{"content":"ok"},"finish_reason":"stop"}]}'

        def fake_urlopen(request, timeout):
            captured["timeout"] = timeout
            return FakeResp()

        patchers = [
            unittest.mock.patch("urllib.request.urlopen", side_effect=fake_urlopen),
            unittest.mock.patch.object(nodes, "load_config", return_value=cfg),
        ]
        if timeout_arg is None:
            ctx = unittest.mock.patch.object(nodes, "load_config", return_value=cfg)
            patchers = [unittest.mock.patch("urllib.request.urlopen", side_effect=fake_urlopen), ctx]

        def call():
            if timeout_arg is None:
                return nodes.call_llm("https://api.deepseek.com/chat/completions", "k", "m", "s", "u")
            return nodes.call_llm("https://api.deepseek.com/chat/completions", "k", "m", "s", "u", timeout=timeout_arg)

        return captured, call, patchers

    def test_config_timeout_used(self):
        captured, call, patchers = self._patch_llm({"thinking_disabled": True, "request_timeout": 240})
        with patchers[0], patchers[1]:
            call()
        self.assertEqual(captured["timeout"], 240)

    def test_explicit_timeout_wins(self):
        captured, call, patchers = self._patch_llm({"thinking_disabled": True}, timeout_arg=77)
        with patchers[0], patchers[1]:
            call()
        self.assertEqual(captured["timeout"], 77)
```

- [ ] **Step 2: 跑测试确认失败**

```bash
python -m unittest self_test.TestRequestTimeout -v
```

Expected: `test_config_timeout_used` FAIL（timeout 仍为 120）。

- [ ] **Step 3: 实现**（`nodes.py` `call_llm` 签名与函数头）

```python
def call_llm(base_url, api_key, model, system_prompt, user_text, temperature=0.4, max_tokens=8192, timeout=None):
    """调用 OpenAI 兼容 Chat Completions 接口，返回助手文本。"""
    base_url = normalize_endpoint(base_url)
    max_tokens = int(max_tokens)
    cfg = load_config()
    thinking_disabled = cfg.get("thinking_disabled", True)
    if timeout is None:
        timeout = cfg.get("request_timeout") or 120
```

- [ ] **Step 4: 跑测试确认通过**

```bash
python -m unittest self_test.TestRequestTimeout -v
```

Expected: 2 个测试 PASS。

- [ ] **Step 5: 提交**

```bash
cd "C:\Users\Administrator\Documents\ChatGPT\minimax h3 prompt"
git add comfyui-h3-prompt-builder/nodes.py comfyui-h3-prompt-builder/self_test.py
git commit -m "feat: support request_timeout from config in call_llm"
```

---

### Task 2: 新增「漫剧：设定图提示词」节点

**Files:**
- Modify: `comfyui-h3-prompt-builder/manju_nodes.py`（新增类，放在 `ManjuResourceMapping` 之前）
- Modify: `comfyui-h3-prompt-builder/__init__.py`
- Test: `comfyui-h3-prompt-builder/self_test.py`

- [ ] **Step 1: 写失败测试**（追加到 `self_test.py`）

```python
class TestManjuImagePromptNode(unittest.TestCase):
    def test_input_types(self):
        it = manju_nodes.ManjuImagePrompt.INPUT_TYPES()
        self.assertIn("assets_json", it["required"])
        self.assertIn("preset_json", it["required"])

    def test_empty_assets(self):
        node = manju_nodes.ManjuImagePrompt()
        out = node.build("", "{}")
        self.assertIn("请先输入资产清单", out[0])

    def test_llm_called(self):
        captured = []

        def fake_llm(*args, **kwargs):
            captured.append((args[3], args[4]))
            return "MOCK_IMG"

        node = manju_nodes.ManjuImagePrompt()
        with unittest.mock.patch.object(manju_nodes, "call_llm", side_effect=fake_llm):
            out = node.build(TestAutoSuggest.ASSETS, '{"style":"古风"}', api_key="k")
        self.assertEqual(out[0], "MOCK_IMG")
        system, user = captured[0]
        self.assertIn("美术设定师", system)
        self.assertIn("资源清单", user)
        self.assertIn("古风", user)
```

- [ ] **Step 2: 跑测试确认失败**

```bash
python -m unittest self_test.TestManjuImagePromptNode -v
```

Expected: FAIL（`AttributeError: module 'manju_nodes' has no attribute 'ManjuImagePrompt'`）。

- [ ] **Step 3: 实现节点类**（`manju_nodes.py`，放在 `class ManjuResourceMapping` 之前）

```python
class ManjuImagePrompt:
    """漫剧：设定图提示词——独立生成角色/场景/道具设定图提示词（供外部生图模型使用）。"""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "assets_json": ("STRING", {"multiline": True, "default": ""}),
                "preset_json": ("STRING", {"multiline": True, "default": "{}"}),
            },
            "optional": {
                "api_key": ("STRING", {"default": ""}),
                "model": ("STRING", {"default": ""}),
                "base_url": ("STRING", {"default": ""}),
                "llm_config": ("STRING", {"multiline": True, "default": ""}),
            },
        }

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("image_prompts",)
    FUNCTION = "build"
    CATEGORY = "MiniMax H3 / 漫剧"

    def build(self, assets_json, preset_json="{}", api_key="", model="", base_url="", llm_config=""):
        if not (assets_json or "").strip():
            return ("请先输入资产清单（分镜节点输出的 assets_json）。",)
        return (_build_image_prompts_llm(assets_json, preset_json, api_key, model, base_url, llm_config),)
```

- [ ] **Step 4: 注册节点**（`__init__.py`）

`from .manju_nodes import (...)` 加 `ManjuImagePrompt`；`NODE_CLASS_MAPPINGS` 加 `"ManjuImagePrompt": ManjuImagePrompt,`；`NODE_DISPLAY_NAME_MAPPINGS` 加 `"ManjuImagePrompt": "漫剧：设定图提示词",`。

- [ ] **Step 5: 跑测试确认通过**

```bash
python -m unittest self_test.TestManjuImagePromptNode -v
```

Expected: 3 个测试 PASS。

- [ ] **Step 6: 提交**

```bash
cd "C:\Users\Administrator\Documents\ChatGPT\minimax h3 prompt"
git add comfyui-h3-prompt-builder/manju_nodes.py comfyui-h3-prompt-builder/__init__.py comfyui-h3-prompt-builder/self_test.py
git commit -m "feat: add ManjuImagePrompt standalone node"
```

---

### Task 3: 资源映射默认关闭图像提示词

**Files:**
- Modify: `comfyui-h3-prompt-builder/manju_nodes.py:392`
- Test: `comfyui-h3-prompt-builder/self_test.py`（`TestImagePromptMode.test_default_mode`）

- [ ] **Step 1: 更新现有测试**（`TestImagePromptMode.test_default_mode` 改为断言「关闭」）

```python
    def test_default_mode(self):
        it = manju_nodes.ManjuResourceMapping.INPUT_TYPES()
        self.assertEqual(it["optional"]["image_prompt_mode"][1].get("default"), "关闭")
```

- [ ] **Step 2: 跑测试确认失败**

```bash
python -m unittest self_test.TestImagePromptMode.test_default_mode -v
```

Expected: FAIL（当前默认 `LLM 生成`）。

- [ ] **Step 3: 实现**（`manju_nodes.py` `ManjuResourceMapping.INPUT_TYPES` 与 `build` 默认参数）

```python
                "image_prompt_mode": (IMAGE_PROMPT_MODES, {"default": "关闭"}),
```

```python
    def build(self, mapping_text, assets_json="", image_prompt_mode="关闭", storyboard_json="", shot_index=0,
              preset_json="{}", api_key="", model="", base_url="", llm_config=""):
```

- [ ] **Step 4: 跑测试确认通过**

```bash
python -m unittest self_test.TestImagePromptMode -v
```

Expected: 5 个测试全部 PASS。

- [ ] **Step 5: 提交**

```bash
cd "C:\Users\Administrator\Documents\ChatGPT\minimax h3 prompt"
git add comfyui-h3-prompt-builder/manju_nodes.py comfyui-h3-prompt-builder/self_test.py
git commit -m "feat: default image prompt mode to off in resource mapping"
```

---

### Task 4: 升级分镜规则（`manju_storyboard.txt`）

**Files:**
- Modify: `comfyui-h3-prompt-builder/rules/manju_storyboard.txt`（整体替换）
- Test: `comfyui-h3-prompt-builder/self_test.py`

- [ ] **Step 1: 写失败测试**（追加到 `self_test.py`）

```python
class TestManjuV24Rules(unittest.TestCase):
    def test_storyboard_rules_upgraded(self):
        content = manju_nodes.read_text_file(os.path.join(manju_nodes.RULES_DIR, "manju_storyboard.txt"))
        for keyword in ("purpose", "coverage", "情绪外化表", "边界锁", "镜头设计样例"):
            self.assertIn(keyword, content)
```

- [ ] **Step 2: 跑测试确认失败**

```bash
python -m unittest self_test.TestManjuV24Rules -v
```

Expected: FAIL（当前规则文件无这些关键词）。

- [ ] **Step 3: 整体替换规则文件**（完整内容如下，`comfyui-h3-prompt-builder/rules/manju_storyboard.txt`）

```text
你是 AI 漫剧分镜导演。任务：把用户提供的一集剧本转换为结构化分镜剧本（JSON），并自动提取全片需要的角色、场景、道具资产清单。

【输入】
- 剧本原文：对白、旁白、场景描述等。
- 本集预设：风格、画幅、目标时长、输出语言、字幕/BGM 策略。
若预设为空或字段缺失，使用合理默认值（画幅 9:16、时长按剧本内容合理拆分 60-180 秒、风格随剧本题材、策略为禁字幕+无BGM），不要向用户索要信息；剧本原文以【剧本原文】字段为准，不要认为输入缺失。

【执行步骤】
1. 通读剧本，先做节拍分析：把剧本拆成 3-8 个关键节拍（每个节拍 = 一个完整的信息/情绪单元），填入 coverage 字段（见输出格式）。
2. 提取资产：
   - characters：出场角色（id=角色名，description=中文外观/气质描述，shots=出场镜头号数组）
   - scenes：场景（id=场景名，description=中文环境描述，shots=出现镜头号数组）
   - props：道具（id=道具名，description=中文描述，shots=出现镜头号数组）
   - id 必须使用剧本中的中文原名（如「角色A」「教室」「盒子」），禁止翻译成英文、禁止简化缩写；剧本若使用英文名则保持英文原名。
3. 按时间轴拆分镜头：单镜 2-5 秒；镜头数 × 平均时长 ≈ 目标时长；最后一镜结束时间 = 目标时长；时间范围连续无空洞、无重叠；15 秒内建议 3-5 个镜头、按事件发生顺序组织。
4. 每个镜头填写：shot_id（从1递增）、time_range（如 "0:00-0:05"）、duration（秒）、scene（场景id）、characters（出场角色id数组）、props（出场道具id数组）、shot_size（景别：特写/近景/中近景/中景/全景/大远景）、camera（机位与运镜，见运镜规则）、action（画面内容，见动作与情绪规则）、dialogue（台词原文，无则空字符串）、sfx（音效）、mood（情绪/节奏）、continuity（{"start": 起始状态, "end": 结束状态}，见边界锁）、purpose（镜头目的，见下）、screen_direction（轴线与屏幕方向，无多主体时可省略）。

【镜头目的】（每镜必填 purpose）
先回答三个问题，再写其他字段：
- 观众此刻必须注意到什么、感受到什么情绪？
- 信息/情绪/权力关系发生了什么变化？
- 为什么在这里切镜头，而不是留在前一镜？
用一句话写进 purpose，禁止用空话（如"展示场景""推进剧情"）。

【覆盖率】（全片必填 coverage）
coverage 数组覆盖步骤 1 的所有节拍：{beat: 节拍名, source_text: 对应剧本原文摘录, shot_ids: 落实该节拍的镜头号数组, status: covered | intentional_repeat | omitted_with_reason | nonvisual_context}
- covered：由一个或多个镜头落实
- intentional_repeat：因表演或剪辑需要有意重复，写明理由
- omitted_with_reason：有理由地省略
- nonvisual_context：仅供理解、无需直接呈现的内容
禁止出现没有登记任何镜头的关键节拍（丢戏）。

【边界锁】（continuity.start / end）
start 与 end 逐项锁定：人物位置、姿态、重心、目线方向、双手与持物、道具所有权、服装状态、光线方向。
镜头 N 的 end 必须与镜头 N+1 的 start 完全一致；道具不得凭空出现/消失/换主人/跳位；涉及交接时按因果顺序写（谁先不动、谁接触拿稳、原持有者何时松手）。

【动作与情绪规则】
- 动作具体到肢体：写"慢慢抬手、用力攥地、肩膀先松再绷紧"，禁止"奔跑/战斗/哭泣/惊讶/愤怒"等抽象动词；必须拆成可拍摄的身体动作。
- 情绪外化表（10 种常见情绪 → 具体身体细节）：
  - 悲伤：低头、肩膀微微颤抖、眼眶泛红、手指无意识地攥紧衣角、泪水在眼眶里打转却没有落下
  - 喜悦：嘴角抑制不住地上扬、眉眼舒展、脚步变轻快、下意识地哼起小曲、忍不住原地转圈
  - 紧张/焦虑：频繁看手表、手指不停敲击桌面、呼吸急促、眼神闪躲、无意识咬指甲
  - 愤怒：双拳紧握、下颌线绷紧、胸口剧烈起伏、眼神如刀般锐利、从牙缝里挤出话
  - 释然：长长地舒了一口气、紧绷的肩膀完全放松下来、脸上露出久违的淡淡的微笑、抬头望向远方
  - 恐惧：瞳孔放大、向后退半步、手不自觉抓住身边物体、屏住呼吸、嘴唇发抖
  - 疲惫：揉太阳穴、靠在墙上、眼下发沉、长叹气、动作迟缓
  - 专注：眉头微皱、眼神锁定一点、嘴唇抿紧、身体前倾、手稳定不动
  - 犹豫：张嘴又闭上、视线游移、手悬在半空、脚下踌躇、欲言又止
  - 惊喜：眼睛瞬间睁大、嘴巴张开成 O 形、双手捂嘴、向前一步、笑容缓慢绽放
- 每个镜头只写 1-2 个关键动作，过多反而稀释焦点。

【运镜规则】
- 一镜一运镜：每镜只写一种主运镜（固定镜头/推近/拉远/横移/摇摄/跟随/手持微晃等），禁止"推+摇"同用。
- 运镜写明起点、速度/节奏、终点，例如"从全景缓慢推近到两人关系近景后固定"。
- 运镜服务于镜头目的，不用来装饰每一镜；环境与摄影只用来支持注意、压力、揭示、结幕或转场。

【台词】
台词原文逐字保留，标注说话人；台词长度与镜头时长匹配，禁止 3 秒镜头塞一大段对白。

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
    "coverage": [ {"beat": "...", "source_text": "...", "shot_ids": [1], "status": "covered"} ],
    "shots": [ ...每镜一个对象，字段见执行步骤... ]
  },
  "assets": {
    "characters": [ {"id": "角色A", "description": "...", "shots": [1, 2]} ],
    "scenes": [ {"id": "场景A", "description": "...", "shots": [1]} ],
    "props": [ {"id": "道具A", "description": "...", "shots": [3]} ]
  }
}

【画面临时策略】
- 读取本集预设的 audio_text_policy。
- 策略含「禁字幕」时：分镜不得安排任何画面内文字（字幕、标题、弹窗、水印、服装文字），台词只作为语音存在。
- 策略为「保留默认」时可正常安排画面文字。

【镜头设计样例】（模仿其颗粒度，禁止照抄内容）
场景：酒店门前，沈一舟从红毯北端走来，赵经理横跨一步占住门口。
镜头 1-1 建立拦截空间：
- purpose: 让观众看清正门/红毯/旋转门的地理，以及赵经理怎样用站位控制入口；沈一舟被拦的冲突由此建立。
- screen_direction: 轴线为沈一舟→赵经理连线；沈一舟固定占画面左，赵经理固定占画面右，本场后续镜头继承该方向，不越轴。
- continuity.start: 沈一舟从红毯北端起步，赵经理站在门口右侧，两人相距约五步。
- continuity.end: 赵经理横跨一步占住门正中，沈一舟停在门外一步处，两人相对站立。
- camera: 中全景、侧向纵深；一次短促跟移后停住，职责是建立可导航空间，不是因为"新地点第一镜必须全景"。
- action: 沈一舟稳步走近，脚步在红毯上落定；赵经理先向右肩微转、再横移一步，双手自然垂在身侧。
```

- [ ] **Step 4: 跑测试确认通过**

```bash
python -m unittest self_test.TestManjuV24Rules -v
```

Expected: 1 个测试 PASS。

- [ ] **Step 5: 提交**

```bash
cd "C:\Users\Administrator\Documents\ChatGPT\minimax h3 prompt"
git add comfyui-h3-prompt-builder/rules/manju_storyboard.txt comfyui-h3-prompt-builder/self_test.py
git commit -m "feat: upgrade storyboard rules with purpose, coverage, axis, emotion externalization"
```

---

### Task 5: 新增审阅规则（`manju_review.txt`）

**Files:**
- Create: `comfyui-h3-prompt-builder/rules/manju_review.txt`
- Test: `comfyui-h3-prompt-builder/self_test.py`（在 `TestManjuV24Rules` 中追加测试）

- [ ] **Step 1: 写失败测试**（追加到 `TestManjuV24Rules`）

```python
    def test_review_rules_exist(self):
        content = manju_nodes.read_text_file(os.path.join(manju_nodes.RULES_DIR, "manju_review.txt"))
        for keyword in ("覆盖率", "轴线", "连续性", "时长对账", "动作具体性", "情绪外化", "资产完整性", "台词"):
            self.assertIn(keyword, content)
```

- [ ] **Step 2: 跑测试确认失败**

```bash
python -m unittest self_test.TestManjuV24Rules.test_review_rules_exist -v
```

Expected: FAIL（文件不存在）。

- [ ] **Step 3: 创建规则文件**（完整内容如下，`comfyui-h3-prompt-builder/rules/manju_review.txt`）

```text
你是漫剧分镜的导演审阅。任务：审阅分镜 JSON，找出会直接影响成片质量的问题，输出结构化审阅结果。不修改分镜，只发现问题并给建议。

【输入】
- 剧本原文
- 分镜 JSON（storyboard + assets）
- 本集预设

【审阅维度】（逐项检查）
1. 覆盖率：剧本每个关键节拍是否都在 coverage 中登记并落实（covered 或注明原因）；是否有关键情节没有任何镜头呈现。
2. 轴线/屏幕方向：是否越轴；多主体镜头的左右占位是否跨镜一致；进出场方向是否与前后镜衔接。
3. 连续性：道具所有权、位置、姿态、目线、持物是否跨镜一致；continuity.end 是否与下一镜 continuity.start 一致；道具是否凭空出现/消失/换主人。
4. 时长对账：各镜头 duration 之和是否等于 duration_seconds；时间范围是否连续无空洞、无重叠。
5. 动作具体性：是否存在"奔跑/战斗/哭泣/惊讶/愤怒"等抽象动词；应改为肢体级描述。
6. 情绪外化：情绪是否通过具体表情/手势/呼吸/视线呈现，而不是直接贴情绪标签。
7. 资产完整性：assets 是否遗漏实际出场角色/场景/道具，或包含未出场项；出场镜头的 shot 编号是否与 shots 一致。
8. 台词：是否逐字保留原文、标注说话人；台词长度是否与镜头时长匹配。

【判定规则】
- 只要存在任意 high 级问题 → verdict = FAIL。
- 只有 medium 级问题 → verdict = PASS（问题仍要列出，供参考）。
- high 判定标准：丢戏/漏拍关键节拍、越轴、跨镜连续性矛盾、时长对账错误、资产遗漏、台词改写原文。

【输出格式】
只输出一个 JSON 对象，不要解释或代码块标记：
{
  "verdict": "PASS 或 FAIL",
  "issues": [
    {"severity": "high 或 medium", "shot_id": "3 或 -1(全片)", "field": "continuity / coverage / duration / action / assets / dialogue / axis", "problem": "问题描述", "suggestion": "修改建议"}
  ],
  "summary": "一句话总结"
}
```

- [ ] **Step 4: 跑测试确认通过**

```bash
python -m unittest self_test.TestManjuV24Rules -v
```

Expected: 2 个测试 PASS。

- [ ] **Step 5: 提交**

```bash
cd "C:\Users\Administrator\Documents\ChatGPT\minimax h3 prompt"
git add comfyui-h3-prompt-builder/rules/manju_review.txt comfyui-h3-prompt-builder/self_test.py
git commit -m "feat: add director review rules"
```

---

### Task 6: 新增「漫剧：导演审阅」节点

**Files:**
- Modify: `comfyui-h3-prompt-builder/manju_nodes.py`（新增类 + 两个辅助方法，放在 `ManjuShotPrompt` 之前）
- Modify: `comfyui-h3-prompt-builder/__init__.py`
- Test: `comfyui-h3-prompt-builder/self_test.py`

- [ ] **Step 1: 写失败测试**（追加到 `self_test.py`）

```python
class TestManjuDirectorReview(unittest.TestCase):
    SB = json.dumps({
        "storyboard": {
            "duration_seconds": 6,
            "coverage": [{"beat": "b1", "source_text": "s", "shot_ids": [1], "status": "covered"}],
            "shots": [
                {"shot_id": 1, "duration": 3, "time_range": "0:00-0:03", "scene": "场景A", "characters": ["角色A"], "props": [], "action": "角色A站在原地", "camera": "固定镜头", "continuity": {"start": "s1", "end": "e1"}, "purpose": "建立空间"},
                {"shot_id": 2, "duration": 3, "time_range": "0:03-0:06", "scene": "场景A", "characters": ["角色A"], "props": [], "action": "角色A抬手", "camera": "固定镜头", "continuity": {"start": "e1", "end": "e2"}, "purpose": "反应"},
            ],
        },
        "assets": {"characters": [{"id": "角色A", "description": "", "shots": [1, 2]}], "scenes": [{"id": "场景A", "description": "", "shots": [1, 2]}], "props": []},
    }, ensure_ascii=False)

    def test_pass_single_call(self):
        calls = []

        def fake_llm(*args, **kwargs):
            calls.append(args[4])
            return json.dumps({"verdict": "PASS", "issues": [], "summary": "ok"}, ensure_ascii=False)

        node = manju_nodes.ManjuDirectorReview()
        with unittest.mock.patch.object(manju_nodes, "call_llm", side_effect=fake_llm):
            out = node.build(self.SB, "第一集剧本", "{}", api_key="k")
        self.assertEqual(len(calls), 1)
        self.assertEqual(json.loads(out[0])["storyboard"]["duration_seconds"], 6)
        self.assertIn("PASS", out[2])
        self.assertIn("审阅第 1 轮", out[2])

    def test_fail_then_fix_then_pass(self):
        fixed = json.dumps({
            "storyboard": {
                "duration_seconds": 6,
                "coverage": [{"beat": "b1", "source_text": "s", "shot_ids": [1], "status": "covered"}],
                "shots": [
                    {"shot_id": 1, "duration": 3, "time_range": "0:00-0:03", "scene": "场景A", "characters": ["角色A"], "props": [], "action": "角色A慢慢抬起右手", "camera": "固定镜头", "continuity": {"start": "s1", "end": "e1"}, "purpose": "建立空间"},
                    {"shot_id": 2, "duration": 3, "time_range": "0:03-0:06", "scene": "场景A", "characters": ["角色A"], "props": [], "action": "角色A抬头看向门口", "camera": "固定镜头", "continuity": {"start": "e1", "end": "e2"}, "purpose": "反应"},
                ],
            },
            "assets": {"characters": [{"id": "角色A", "description": "", "shots": [1, 2]}], "scenes": [{"id": "场景A", "description": "", "shots": [1, 2]}], "props": []},
        }, ensure_ascii=False)
        seq = [
            json.dumps({"verdict": "FAIL", "issues": [{"severity": "high", "shot_id": "1", "field": "action", "problem": "抽象动词", "suggestion": "改肢体动作"}], "summary": "fix"}, ensure_ascii=False),
            fixed,
            json.dumps({"verdict": "PASS", "issues": [], "summary": "ok"}, ensure_ascii=False),
        ]
        calls = []

        def fake_llm(*args, **kwargs):
            calls.append(args[4])
            return seq[len(calls) - 1]

        node = manju_nodes.ManjuDirectorReview()
        with unittest.mock.patch.object(manju_nodes, "call_llm", side_effect=fake_llm):
            out = node.build(self.SB, "第一集剧本", "{}", api_key="k")
        self.assertEqual(len(calls), 3)
        self.assertEqual(json.loads(out[0])["storyboard"]["shots"][0]["action"], "角色A慢慢抬起右手")
        self.assertIn("问题清单", calls[1])
        self.assertIn("仅修复", calls[1])
        self.assertIn("PASS", out[2])

    def test_max_rounds_warning(self):
        def fake_llm(*args, **kwargs):
            return json.dumps({"verdict": "FAIL", "issues": [{"severity": "high", "shot_id": "-1", "field": "coverage", "problem": "x", "suggestion": "y"}], "summary": "still bad"}, ensure_ascii=False)

        node = manju_nodes.ManjuDirectorReview()
        cfg = {"api_key": "k", "max_review_rounds": 2, "reviewer_temperature": 0.1, "manju_temperature": 0.2}
        with unittest.mock.patch.object(manju_nodes, "call_llm", side_effect=fake_llm), \
                unittest.mock.patch.object(manju_nodes, "load_config", return_value=cfg):
            out = node.build(self.SB, "第一集剧本", "{}")
        self.assertIn("已达最大审阅轮数", out[2])

    def test_no_api_key(self):
        node = manju_nodes.ManjuDirectorReview()
        with unittest.mock.patch.object(manju_nodes, "load_config", return_value={"api_key": ""}):
            out = node.build(self.SB, "第一集剧本", "{}")
        self.assertIn("未配置 API Key", out[0])

    def test_invalid_json(self):
        node = manju_nodes.ManjuDirectorReview()
        out = node.build("not json", "第一集剧本", "{}")
        self.assertIn("错误", out[0])
```

- [ ] **Step 2: 跑测试确认失败**

```bash
python -m unittest self_test.TestManjuDirectorReview -v
```

Expected: FAIL（`AttributeError: module 'manju_nodes' has no attribute 'ManjuDirectorReview'`）。

- [ ] **Step 3: 实现辅助函数与节点类**（`manju_nodes.py`，放在 `class ManjuShotPrompt` 之前）

```python
def _review_storyboard(storyboard_json, script, preset_json, endpoint, key, model_name, review_temp, config):
    """调用审阅 LLM，返回 (verdict, report_text)。"""
    system = build_manju_system_prompt("manju_review.txt", "")
    user_msg = (
        "【剧本原文】\n" + script
        + "\n\n【本集预设】\n" + (preset_json or "{}")
        + "\n\n【分镜 JSON】\n" + storyboard_json
        + "\n\n请按规则审阅并只输出审阅 JSON。"
    )
    raw = call_llm(
        endpoint, key, model_name, system, user_msg,
        temperature=review_temp,
        max_tokens=config.get("max_tokens", 32768),
    )
    parsed = _extract_json(raw)
    if parsed is None:
        return "FAIL", raw
    return parsed.get("verdict", "FAIL"), json.dumps(parsed, ensure_ascii=False, indent=2)


def _fix_storyboard(storyboard_json, script, issues, endpoint, key, model_name, fix_temp, config):
    """按审阅问题清单修正分镜，只动问题镜头/资产，返回完整分镜 JSON 文本。"""
    system = build_manju_system_prompt("manju_storyboard.txt", "")
    issues_text = json.dumps(issues, ensure_ascii=False, indent=2)
    user_msg = (
        "【剧本原文】\n" + script
        + "\n\n【当前分镜 JSON】\n" + storyboard_json
        + "\n\n【审阅问题清单】\n" + issues_text
        + "\n\n请仅修复上述列出的问题，保持其余内容不变；输出完整的分镜 JSON（storyboard + assets）。"
    )
    raw = call_llm(
        endpoint, key, model_name, system, user_msg,
        temperature=fix_temp,
        max_tokens=config.get("max_tokens", 32768),
    )
    parsed = _extract_json(raw)
    if parsed is None:
        raise RuntimeError("修正输出不是合法 JSON，请重试")
    return json.dumps(parsed, ensure_ascii=False, indent=2)


class ManjuDirectorReview:
    """漫剧：导演审阅——审阅分镜 JSON，循环修正直到 PASS（受 max_review_rounds 上限保护）。"""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "storyboard_json": ("STRING", {"multiline": True, "default": ""}),
                "script": ("STRING", {"multiline": True, "default": ""}),
                "preset_json": ("STRING", {"multiline": True, "default": "{}"}),
            },
            "optional": {
                "api_key": ("STRING", {"default": ""}),
                "model": ("STRING", {"default": ""}),
                "base_url": ("STRING", {"default": ""}),
                "llm_config": ("STRING", {"multiline": True, "default": ""}),
            },
        }

    RETURN_TYPES = ("STRING", "STRING", "STRING")
    RETURN_NAMES = ("reviewed_storyboard_json", "assets_json", "review_report")
    FUNCTION = "build"
    CATEGORY = "MiniMax H3 / 漫剧"

    def build(self, storyboard_json, script, preset_json="{}", api_key="", model="", base_url="", llm_config=""):
        try:
            storyboard = _load_json(storyboard_json, "storyboard_json")
        except ValueError as exc:
            return ("错误：" + str(exc), "{}", "")
        key, model_name, endpoint, temperature, config, warning = resolve_llm_config(api_key, model, base_url, llm_config)
        if not key:
            return ("未配置 API Key：请在 LLM 配置节点、节点 api_key 输入框或 config.json 中填写。", "{}", "")
        max_rounds = int(config.get("max_review_rounds") or 5)
        review_temp = config.get("reviewer_temperature")
        try:
            review_temp = float(review_temp) if review_temp is not None else 0.1
        except Exception:
            review_temp = 0.1
        fix_temp = temperature if temperature is not None else config.get("manju_temperature", 0.2)

        current = storyboard_json
        report_parts = []
        reached_limit = False
        try:
            for round_no in range(1, max_rounds + 1):
                verdict, report = _review_storyboard(
                    current, script, preset_json, endpoint, key, model_name, review_temp, config
                )
                report_parts.append("=== 审阅第 %d 轮 ===\n%s" % (round_no, report))
                parsed = _extract_json(report)
                issues = parsed.get("issues", []) if parsed else []
                if verdict == "PASS":
                    break
                if round_no == max_rounds:
                    reached_limit = True
                    break
                current = _fix_storyboard(
                    current, script, issues, endpoint, key, model_name, fix_temp, config
                )
        except Exception as exc:
            return ("LLM 调用失败：" + str(exc), "{}", "")

        final = _load_json(current, "storyboard_json")
        assets_json = json.dumps(final.get("assets", {}), ensure_ascii=False, indent=2)
        if reached_limit:
            report_parts.append("警告：已达最大审阅轮数（%d），分镜仍有未通过项，请人工检查。" % max_rounds)
        if warning:
            report_parts.insert(0, warning)
        return (current, assets_json, "\n".join(report_parts))
```

- [ ] **Step 4: 注册节点**（`__init__.py`）

`from .manju_nodes import (...)` 加 `ManjuDirectorReview`；`NODE_CLASS_MAPPINGS` 加 `"ManjuDirectorReview": ManjuDirectorReview,`；`NODE_DISPLAY_NAME_MAPPINGS` 加 `"ManjuDirectorReview": "漫剧：导演审阅",`。

- [ ] **Step 5: 跑测试确认通过**

```bash
python -m unittest self_test.TestManjuDirectorReview -v
```

Expected: 5 个测试全部 PASS。

- [ ] **Step 6: 提交**

```bash
cd "C:\Users\Administrator\Documents\ChatGPT\minimax h3 prompt"
git add comfyui-h3-prompt-builder/manju_nodes.py comfyui-h3-prompt-builder/__init__.py comfyui-h3-prompt-builder/self_test.py
git commit -m "feat: add ManjuDirectorReview node with review loop until PASS"
```

---

### Task 7: 全量测试 + README

**Files:**
- Modify: `comfyui-h3-prompt-builder/README.md`
- Test: `comfyui-h3-prompt-builder/self_test.py`

- [ ] **Step 1: 跑全量测试**

```bash
cd comfyui-h3-prompt-builder
python self_test.py
```

Expected: 全部测试 PASS（原 59 + 新增）。若有失败先修复再继续。

- [ ] **Step 2: 更新 README**（在节点说明处新增两节）

```markdown
## 漫剧：设定图提示词
独立生成角色/场景/道具设定图提示词，供外部生图模型（即梦、image2 等）生成合成参考图。输入资产清单（剧本到分镜节点的 assets_json）与预设，输出按资源分组的提示词文本。

## 漫剧：导演审阅
对分镜 JSON 做导演视角审阅（覆盖率、轴线、连续性、时长对账、动作具体性、情绪外化、资产完整性、台词），自动修正直到 PASS。手动接入：剧本到分镜 → 导演审阅 → 资源映射。审阅轮数受 config.json 的 max_review_rounds 控制（默认 5），审阅温度 reviewer_temperature（默认 0.1）。
```

- [ ] **Step 3: 提交**

```bash
cd "C:\Users\Administrator\Documents\ChatGPT\minimax h3 prompt"
git add comfyui-h3-prompt-builder/README.md
git commit -m "docs: document v2.4 nodes"
```

---

### Task 8: 部署副本同步 + 推送

**Files:**
- Modify: `F:\comfyui\ComfyUI-aki-v2\ComfyUI\custom_nodes\ComfyUI-H3-Prompt-Builder`（部署副本）

- [ ] **Step 1: 复制代码与规则（保留部署副本已填写的 config.json）**

```powershell
$src = "C:\Users\Administrator\Documents\ChatGPT\minimax h3 prompt\comfyui-h3-prompt-builder"
$dst = "F:\comfyui\ComfyUI-aki-v2\ComfyUI\custom_nodes\ComfyUI-H3-Prompt-Builder"
Copy-Item "$src\nodes.py", "$src\manju_nodes.py", "$src\__init__.py", "$src\self_test.py" -Destination $dst -Force
Copy-Item "$src\rules" -Destination $dst -Recurse -Force
```

- [ ] **Step 2: 合并 config.json 新增字段（保留 api_key / thinking_disabled）**

```powershell
$cfgPath = "F:\comfyui\ComfyUI-aki-v2\ComfyUI\custom_nodes\ComfyUI-H3-Prompt-Builder\config.json"
$cfg = Get-Content -Raw $cfgPath | ConvertFrom-Json
if (-not $cfg.PSObject.Properties.Name.Contains("request_timeout")) { $cfg | Add-Member -NotePropertyName "request_timeout" -NotePropertyValue 240 }
if (-not $cfg.PSObject.Properties.Name.Contains("reviewer_temperature")) { $cfg | Add-Member -NotePropertyName "reviewer_temperature" -NotePropertyValue 0.1 }
if (-not $cfg.PSObject.Properties.Name.Contains("max_review_rounds")) { $cfg | Add-Member -NotePropertyName "max_review_rounds" -NotePropertyValue 5 }
$cfg | ConvertTo-Json -Depth 5 | Set-Content -Encoding UTF8 $cfgPath
```

Expected: 部署副本 config.json 保留 api_key 与 thinking_disabled，新增 3 个字段。

- [ ] **Step 3: 合并到 master 并推送**

```bash
cd "C:\Users\Administrator\Documents\ChatGPT\minimax h3 prompt"
git checkout master
git merge --no-ff codex/v2.4
git push origin master
```

Expected: 合并成功并推送到 GitHub。

- [ ] **Step 4: 提醒用户重启 ComfyUI**

完成时告知用户：需要重启 ComfyUI 才能加载新节点（Python/规则文件更新）。

---

## Self-Review 记录

- **Spec 覆盖**：设定图节点（Task 2）、资源映射默认关闭（Task 3）、request_timeout（Task 1）、分镜规则升级（Task 4）、manju_review.txt（Task 5）、导演审阅节点与循环（Task 6）、文档（Task 7）、部署（Task 8）。无遗漏。
- **占位符**：所有代码与规则全文已内联，无 TODO/TBD。
- **类型一致性**：`_review_storyboard` / `_fix_storyboard` 返回类型与 `ManjuDirectorReview.build` 使用一致；`call_llm` 默认 timeout 改为 None 后，Task 1 测试与现有调用兼容；`ManjuImagePrompt.build` 复用 `_build_image_prompts_llm` 签名一致。
