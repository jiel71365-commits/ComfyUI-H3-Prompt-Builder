# ComfyUI H3 Prompt Builder 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现一个 ComfyUI 自定义节点「H3 Prompt Builder」，输入大白话/素材说明，输出符合官方格式的 MiniMax H3 提示词，支持 LLM 改写（DeepSeek）与离线模板骨架两种模式，可直接接入 R2V/T2V/I2V 节点。

**Architecture:** 单节点 + 纯标准库（urllib）。`nodes.py` 承载全部逻辑（配置读取、规则组装、LLM 调用、模板拼装、节点类）；`rules/` 存放官方格式精简规则与 8 个风格规则（纯文本可编辑）；`config.json` 保存 API 默认值；`self_test.py` 提供离线测试。源码维护在工作区仓库 `comfyui-h3-prompt-builder/`，通过复制目录部署到 ComfyUI `custom_nodes`。

**Tech Stack:** Python 3（标准库 urllib/json/os/unittest），ComfyUI 自定义节点规范（NODE_CLASS_MAPPINGS）。

**Spec:** `docs/superpowers/specs/2026-08-06-comfyui-h3-prompt-builder-design.md`

---

## 文件结构

```
comfyui-h3-prompt-builder/            # 源码（本仓库，版本控制）
├── __init__.py                       # 节点注册
├── nodes.py                          # 全部逻辑（配置/规则/LLM/模板/节点类）
├── config.json                       # base_url/model/api_key/temperature/max_tokens
├── rules/
│   ├── base_system_prompt.txt        # 官方格式精简规则（LLM 模式 system prompt 基础）
│   └── styles/                       # 8 个风格规则文件
│       ├── minimalist_product_ad.txt
│       ├── animation_3d.txt
│       ├── papercraft_stop_motion.txt
│       ├── paper_collage.txt
│       ├── mv_subtitle.txt
│       ├── brand_promo.txt
│       ├── co_op_game_intro.txt
│       └── handdrawn_live.txt
├── self_test.py                      # 离线测试（unittest）
├── README.md                         # 中文使用说明
└── .gitignore                        # __pycache__/

部署：复制整个目录到 F:\comfyui\ComfyUI-aki-v2\ComfyUI\custom_nodes\ComfyUI-H3-Prompt-Builder
```

依赖约束：`nodes.py` 与 `__init__.py` 不得 import comfy / torch / requests，保证可独立测试。

---

### Task 1: 脚手架（目录、.gitignore、config.json）

**Files:**
- Create: `comfyui-h3-prompt-builder/.gitignore`
- Create: `comfyui-h3-prompt-builder/config.json`

- [ ] **Step 1: 创建目录**

```bash
mkdir -p comfyui-h3-prompt-builder/rules/styles
```

- [ ] **Step 2: 创建 .gitignore**

`comfyui-h3-prompt-builder/.gitignore`:

```text
__pycache__/
*.pyc
```

- [ ] **Step 3: 创建 config.json**

`comfyui-h3-prompt-builder/config.json`:

```json
{
  "base_url": "https://api.deepseek.com/chat/completions",
  "model": "deepseek-v4-flash",
  "api_key": "",
  "temperature": 0.4,
  "max_tokens": 8192
}
```

> 敏感说明：`api_key` 留空提交；部署到 ComfyUI 后由实现步骤填入用户提供的 key（不写入 git）。用户也可以在节点 `api_key` 输入框直接填，优先级高于 config.json。

- [ ] **Step 4: 验证文件存在且 JSON 可解析**

Run:
```bash
python -c "import json; json.load(open('comfyui-h3-prompt-builder/config.json', encoding='utf-8')); print('config ok')"
```
Expected: `config ok`

- [ ] **Step 5: Commit**

```bash
git add comfyui-h3-prompt-builder/.gitignore comfyui-h3-prompt-builder/config.json
git commit -m "chore: scaffold h3 prompt builder plugin"
```

---

### Task 2: 规则文件（官方格式精简版 + 8 个风格）

**Files:**
- Create: `comfyui-h3-prompt-builder/rules/base_system_prompt.txt`
- Create: `comfyui-h3-prompt-builder/rules/styles/*.txt`（8 个）

- [ ] **Step 1: 创建 base_system_prompt.txt**

`comfyui-h3-prompt-builder/rules/base_system_prompt.txt`:

```text
你是 MiniMax H3 视频模型提示词生成引擎。任务：把用户的大白话需求改写为符合官方规范的 H3 提示词。

【模式判定】
根据用户描述的参考素材判断生成模式：
- 无参考素材：T2VA（纯文生）
- 1 张图作首帧：I2VA；1 张图作尾帧：L2VA
- 2 张图（首+尾帧）：FL2VA
- 图/视频/音频混合（图≤9、视频≤3 每段 2-15 秒、音频≤3、总数≤12）：Ref2VA（全能参考）
判断不了时默认 T2VA，并保留用户的素材说明。

【基础模式（T2VA/I2VA/FL2VA/L2VA）输出结构】
- 有图片时必须先输出对齐指令（第一行，后空一行）：
  - I2VA: For the target video, at 0.00 seconds into the target video, <Picture 1> (from [Shot 1]) is fully referenced.
  - FL2VA: How the reference pictures align with the target video — Picture 1 (from Shot 1) aligns with the 0.00-second mark of the target video; Picture 2 (from [Shot N]) aligns with the S.SS-second mark of the target video.
  - L2VA: How the reference pictures align with the target video — <Picture 1> (from [Shot N]) aligns with the S.SS-second mark of the target video.
- 然后按顺序输出三个字段：
  integrated_multimodal_description: [Shot 1] ...（主文：沿时间轴写画面、动作、镜头、台词、画面内声音；[Shot 1] 无时间戳，后续镜头 [Shot 2] At 00:03.500, the camera cuts to ...，时间严格递增且在视频时长内）
  overall_soundscape: ...（1-4 句英文，概括全片环境音与物理音效；对白/配乐不写这里；全片无声才写 N/A）
  non_diegetic_music: ...（1-3 句英文，只写器乐、速度、节奏、动态；没有写 N/A）

【全能参考模式（Ref2VA）输出结构】
按顺序输出六个部分：
  subject_definitions:（定义 <Subject N>/<Picture N>/<Video N>/<Audio N> 标签及角色）
  summary:（以 [任务类型] 开头，如 [reference generation]；可组合如 [video editing + audio reuse]）
  retention_analysis:（每个标签一行：fully_preserved/partially_preserved/attribute_transfer/weak_reference；音频用 fully_copy/partially_copy/reference/weak_reference）
  detailed_description:（350-500 英文词；先写风格总起句再进 [Shot 1]；在标签首次出现处插入标签）
  overall_soundscape: ...
  non_diegetic_music: ...

【标签规则】
- 引用素材一律用 <Picture N>/<Video N>/<Audio N> 标签，编号按用户描述的顺序；R2V 节点上素材连接顺序必须与此一致。
- 标签一旦定义，各段保持一致，不得悬空（定义了必须用）。
- 人物/场景/风格等可复用内容抽象为 <Subject N>；图片作为具体帧/构图锚点时单列 <Picture N>；原视频被编辑/续写/参考结构时用 <Video N>；音频被复制或参考时用 <Audio N>。

【镜头与运镜】
- 切镜必须带来新信息；普通切镜用 the camera cuts to / the shot cuts to / transitions to / changes to / switches to；用户明确要求才用 dissolve/fade/wipe；MV 类默认只硬切。
- 运镜写自然句：类型（Push In/Pull Out、Pan/Truck/Tilt/Pedestal、Arc Shot、Tracking Shot、Static Shot、Shake Slightly/Strongly、POV、Roll）+ 幅度（with small/large amplitude）+ 速度（at slow/fast speed）。
- 环绕运镜写 truck+pan 组合，不写「环绕运镜」。

【说话人与台词】
- 说话人统一编号 (S1)(S2)，跨镜头不变；多人同时说 (S1,S2)。
- 台词格式：<d>[Language] 原文</d>，逐字保留不翻译；画外音写 says in an off-screen voiceover: <d>...</d> 并注明对应角色嘴巴不动；跨镜头台词用 <scenetrans>；被视频结束截断用 <cutoff>。

【画面文字】
- 画面可见文字（招牌/标题/按钮/字幕）用英文双引号 "..." 逐字写出，不翻译。

【写作纪律】
- 少写比喻，只写看得见的画面；台词长度与镜头时长匹配；明确时长（4-15 秒）与画幅；负面要求（不要什么）逐条写清楚；用户要求无 BGM 时 non_diegetic_music 写 N/A。
```

- [ ] **Step 2: 创建 8 个风格规则文件**

`comfyui-h3-prompt-builder/rules/styles/minimalist_product_ad.txt`:

```text
【极简产品广告（Apple 风）规则】
- 默认 10 秒，画幅 16:9 或用户指定；白科技/暗边光/品牌色场/生活场景四选一。
- 画面文案：3-5 个英文单词、单行、最多 32 字符；同一时刻只允许一行；双色规则（前半黑/白，后半用产品真实主色）；禁止上下两行、禁止副标题位置。
- 产品本体颜色/材质必须与参考图一致，只允许改背景与光线。
- 转场由真实产品动作驱动（开盖/旋转/磁吸/滑动/高光扫过），禁止白闪、随机粒子、假 UI 装饰。
- 负空间开场，避免镜像舞台、玻璃桌面、空开场；结尾必须是产品+单行文案的稳定收尾，禁止四宫格/分屏/产品墙。
- 音频：H3 原生音频，科技感 BGM（约 100BPM，块状和弦+拨弦+空气噪声底，结尾 0.5s 内骤停）。
```

`comfyui-h3-prompt-builder/rules/styles/animation_3d.txt`:

```text
【3D 动画短片规则】
- 默认 Pixar 风 3D：C4D+Octane 质感、夸张几何简化、2.5-3 头身 Q 版比例、SSS 皮肤（耳尖/脸颊透光）、挤压拉伸的夸张表演。
- 禁止写实真人、2D 平涂、塑料玩具皮肤、僵硬摆拍、面无表情。
- 角色一致性：发型、服装配色、标志性道具逐条写出，跨镜头保持不变。
- 时长超过 15 秒必须拆成多镜头生成再拼接；每镜头写清逐秒指令。
- 镜头表六要素：镜头编号与时长、连续性交接、参考锚点、Hook 类型、逐秒描述、音频与台词。
```

`comfyui-h3-prompt-builder/rules/styles/papercraft_stop_motion.txt`:

```text
【纸艺定格动画规则】
- 材质：分层卡纸、可见纸纤维/折痕/切边/厚度、层间真实投影、前景遮挡、多层视差。
- 运动：定格感（阶梯式动作、小停顿、轻微回弹、纸机关滑动/翻页/拉条），禁止顺滑 CG、液体变形、高速环绕。
- 场景：前景/中景/背景/远背景至少四层；主体在中景。
- 分镜密度：15 秒约 4 镜、30 秒约 5-6 镜、60 秒约 7-9 镜；每镜只讲一个知识点。
- 声音：纸翻、剪刀、纸板滑动、软木咔嗒、胶带撕；音乐跟随题材文化。
- 负面：塑料 3D、光泽 CG、写实真人、矢量平涂、赛博霓虹、玻璃金属材质、光滑边缘、无纸纤维、无层间阴影。
```

`comfyui-h3-prompt-builder/rules/styles/paper_collage.txt`:

```text
【纸拼贴动画规则】
- 视觉：平坦大胆色场 + 黑白半色调剪贴 + 少量彩色卡纸点缀 + 奶油色描边 + 柔和纸影；干净精致手撕纸边。
- 默认 16:9，每段约 4 秒；运动 = 纸片逐件拼装（出现→滑入/弹入→轻弹→按平→停顿→锁定）。
- 音频默认：只保留拼贴 SFX（纸滑、弹入、按平、轻响、纸沙沙），不加 BGM、不加旁白、不加字幕（除非用户明确要求）。
- 画面禁止可读文字/假字母/UI/水印/logo。
- 负面：平滑数字位移、全局淡入、做旧发黄纸、咖啡纸底。
```

`comfyui-h3-prompt-builder/rules/styles/mv_subtitle.txt`:

```text
【MV / 歌词字幕规则】
- 歌词锁定：用户提供的歌词逐字保留，不得改写；无歌词时先创作原创歌词并锁定。
- 画幅锁定（9:16/16:9/1:1/21:9 等）贯穿全片；时长超过 15 秒拆 2-5 秒/镜的多镜头拼接，全局一条 Master Audio。
- 剪辑：只允许硬切（hard cut），禁止淡入淡出；hi-hat→微震/跳帧，snare→放大/硬切/肩部下压，808→低频压屏/变形。
- 排版：文字是空间中的动态图形层，不是字幕条；可被人物遮挡但不得遮眼/遮嘴型；演唱时画面文字必须逐字等于演唱歌词；每镜头只有一个主文字事件。
- 场景切换由音乐冲击触发（bass hit/808/snare/歌词重音），保持同一视觉预设与光线语言。
```

`comfyui-h3-prompt-builder/rules/styles/brand_promo.txt`:

```text
【品牌宣传片规则】
- 默认 15-30 秒；logo、字体、颜色、产品信息必须来自用户提供的官方/授权素材，禁止 AI 复刻 logo 与包装。
- 结构：品牌钩子 → 用户意图/场景 → 产品机制 → 能力/场景 → 成果/证据 → 产品收尾 → logo+CTA。
- 节奏：15 秒约 5-8 拍；一拍一个主动作，次级元素延迟进入；2-3 个能量峰值 + 静音制动点。
- 文案与 CTA 逐字写死；字幕默认不加；音频默认 H3 原生。
- 禁止：假 HUD、玻璃卡片、装饰文字墙、未核实的数据指标、全片同一种缓动。
```

`comfyui-h3-prompt-builder/rules/styles/co_op_game_intro.txt`:

```text
【联机游戏片头规则】
- 固定菜单框架：左上玩家信息卡、右侧竖排菜单（Start New Game / Continue 高亮 / Settings / Exit）、底部警示胶带、Continue 为视觉焦点；风格可换但框架保持。
- 调色板不超过 5 色，高对比色块；红色仅用于危险/退出；按钮单行、统一圆角与尺寸；字体粗无衬线全大写，标题单行不换行。
- 角色参考图只提取身份锚点（脸型轮廓/发型/眼镜/比例），按选定风格重绘，不继承原图写实质感。
- 画面 UI 文字必须逐字写出原文；禁止乱码/错拼；按钮状态（悬停/点击）变化要明确。
```

`comfyui-h3-prompt-builder/rules/styles/handdrawn_live.txt`:

```text
【手绘发光动画×实拍融合规则】
- 固定结构：15 秒、16:9；实拍空间出现平面手绘发光动画，动画与真实手/物体在 0-3 秒清晰接触，作为同一存在连续变形（保留前一形态痕迹），相机总是慢半拍追赶，13-15 秒空间级变形 + 可爱余韵。
- 质感：蜡笔/粉笔/彩铅/粉彩，线条轻抖、涂抹不均、毛边、逐帧重画感。
- 拍摄者参与：伸手、抓、追、开门、接住、被恶作剧。
- 禁止：3DCG、毛绒玩具感、均匀矢量线、平滑霓虹、恐怖怪物、巨大眼睛、裂嘴、牙齿、威吓、扑咬、突然黑屏、跳吓；禁止凭空出现新角色；禁止跳到别的场景。
```

- [ ] **Step 3: 验证规则文件齐全且非空**

Run:
```bash
Get-ChildItem comfyui-h3-prompt-builder/rules -Recurse -File | Where-Object { $_.Length -lt 50 } | Select-Object FullName
```
Expected: 无输出（所有文件 ≥50 字节）；`Get-ChildItem ... | Measure-Object` 数量 = 9（1 个 base + 8 个 styles）。

- [ ] **Step 4: Commit**

```bash
git add comfyui-h3-prompt-builder/rules
git commit -m "feat: add h3 prompt rules (official format + 8 styles)"
```

---

### Task 3: nodes.py 核心逻辑（配置/规则/对齐指令/模板/LLM）

**Files:**
- Create: `comfyui-h3-prompt-builder/self_test.py`（先写测试）
- Create: `comfyui-h3-prompt-builder/nodes.py`（后写实现）

- [ ] **Step 1: 写失败测试（self_test.py 初版）**

`comfyui-h3-prompt-builder/self_test.py`:

```python
"""离线自检：不联网，检查插件结构与核心逻辑。用法：python self_test.py"""

import os
import sys
import unittest

PLUGIN_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PLUGIN_DIR)

import nodes  # noqa: E402


class TestConfig(unittest.TestCase):
    def test_config_loads(self):
        cfg = nodes.load_config()
        self.assertIn("base_url", cfg)
        self.assertIn("model", cfg)
        self.assertIn("api_key", cfg)

    def test_rules_exist(self):
        base = nodes.read_text_file(os.path.join(nodes.RULES_DIR, "base_system_prompt.txt"))
        self.assertTrue(base and len(base) > 100, "base rules missing or too short")
        for name, fname in nodes.STYLE_KEYS.items():
            if fname is None:
                continue
            content = nodes.read_text_file(os.path.join(nodes.STYLES_DIR, fname))
            self.assertTrue(content and len(content) > 50, "style file empty: " + fname)


class TestTemplate(unittest.TestCase):
    def test_t2va(self):
        out = nodes.build_template("一个女孩在雨夜街道撑伞。", "T2VA", "自动", "自动")
        self.assertIn("integrated_multimodal_description: [Shot 1]", out)
        self.assertIn("overall_soundscape:", out)
        self.assertIn("non_diegetic_music:", out)

    def test_i2va_has_alignment(self):
        out = nodes.build_template("女孩继续向前走。", "I2VA", "自动", "自动")
        self.assertIn("For the target video, at 0.00 seconds", out)

    def test_fl2va_has_alignment_and_duration(self):
        out = nodes.build_template("从站立到蹲下。", "FL2VA", "8", "16:9")
        self.assertIn("How the reference pictures align", out)
        self.assertIn("8.00-second", out)
        self.assertIn("Duration: 8 seconds.", out)

    def test_ref2va_six_sections(self):
        out = nodes.build_template("把视频1中的人物换成图1。", "Ref2VA", "自动", "自动")
        for section in (
            "subject_definitions:",
            "summary:",
            "retention_analysis:",
            "detailed_description:",
            "overall_soundscape:",
            "non_diegetic_music:",
        ):
            self.assertIn(section, out)


class TestSystemPrompt(unittest.TestCase):
    def test_style_rules_injected(self):
        sp = nodes.build_system_prompt("极简产品广告", "自动（英文结构+保留原文）")
        self.assertIn("产品", sp)

    def test_language_instruction(self):
        sp = nodes.build_system_prompt("通用", "中文提示词")
        self.assertIn("中文", sp)


if __name__ == "__main__":
    unittest.main(verbosity=2)
```

- [ ] **Step 2: 运行测试，确认失败（nodes 模块不存在）**

Run: `python comfyui-h3-prompt-builder/self_test.py`
Expected: FAIL（`ModuleNotFoundError: No module named 'nodes'`，因为 nodes.py 尚未创建；测试先于实现失败）

- [ ] **Step 3: 实现 nodes.py（完整代码）**

`comfyui-h3-prompt-builder/nodes.py`:

```python
"""H3 Prompt Builder — ComfyUI 自定义节点（纯标准库实现）。"""

import json
import os
import urllib.error
import urllib.request

PLUGIN_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(PLUGIN_DIR, "config.json")
RULES_DIR = os.path.join(PLUGIN_DIR, "rules")
STYLES_DIR = os.path.join(RULES_DIR, "styles")

STYLE_KEYS = {
    "通用": None,
    "极简产品广告": "minimalist_product_ad.txt",
    "3D 动画短片": "animation_3d.txt",
    "纸艺定格解说": "papercraft_stop_motion.txt",
    "纸拼贴解说": "paper_collage.txt",
    "MV 字幕": "mv_subtitle.txt",
    "品牌宣传片": "brand_promo.txt",
    "联机游戏片头": "co_op_game_intro.txt",
    "手绘实拍融合": "handdrawn_live.txt",
}

MODES = ["LLM 改写", "模板骨架"]
GENERATION_MODES = ["auto", "T2VA", "I2VA", "FL2VA", "L2VA", "Ref2VA"]
DURATIONS = ["自动", "4", "5", "6", "7", "8", "9", "10", "11", "12", "13", "14", "15"]
ASPECT_RATIOS = ["自动", "21:9", "16:9", "4:3", "1:1", "3:4", "9:16"]
OUTPUT_LANGUAGES = ["自动（英文结构+保留原文）", "中文提示词", "全英文"]


def load_config():
    """读取 config.json，缺失字段用默认值补全。"""
    defaults = {
        "base_url": "https://api.deepseek.com/chat/completions",
        "model": "deepseek-v4-flash",
        "api_key": "",
        "temperature": 0.4,
        "max_tokens": 8192,
    }
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            for key in defaults:
                cfg.setdefault(key, defaults[key])
            return cfg
        except Exception:
            pass
    return dict(defaults)


def read_text_file(path):
    """读取 UTF-8 文本文件，不存在返回 None。"""
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return f.read().strip()


def build_system_prompt(style, output_language):
    """组装 LLM 模式 system prompt：官方规则 + 风格规则 + 语言要求。"""
    parts = []
    base = read_text_file(os.path.join(RULES_DIR, "base_system_prompt.txt"))
    if base:
        parts.append(base)
    style_file = STYLE_KEYS.get(style)
    if style_file:
        style_rules = read_text_file(os.path.join(STYLES_DIR, style_file))
        if style_rules:
            parts.append("【本片风格规则（必须遵守）】\n" + style_rules)
        else:
            parts.append("（警告：风格规则文件缺失：" + style_file + "）")
    if output_language == "中文提示词":
        parts.append("输出要求：整体用中文输出，但保留官方字段名（integrated_multimodal_description 等）与标签格式；台词/歌词/画面文字写中文原文。")
    elif output_language == "全英文":
        parts.append("Output requirement: write the entire prompt in English; keep dialogue, lyrics, and visible scene text in their original language.")
    else:
        parts.append("输出要求：结构字段用英文，台词/歌词/画面可见文字保留原语言。")
    parts.append("只输出最终提示词正文本身，不要任何解释、前言、代码块标记或额外说明。")
    return "\n\n".join(parts)


def call_llm(base_url, api_key, model, system_prompt, user_text, temperature=0.4, max_tokens=8192, timeout=120):
    """调用 OpenAI 兼容 Chat Completions 接口，返回助手文本。"""
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_text},
        ],
        "temperature": float(temperature),
        "max_tokens": int(max_tokens),
        "stream": False,
    }
    request = urllib.request.Request(
        base_url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": "Bearer " + api_key,
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as err:
        detail = ""
        try:
            detail = err.read().decode("utf-8")[:300]
        except Exception:
            pass
        raise RuntimeError("HTTP %s: %s" % (err.code, detail))
    except urllib.error.URLError as err:
        raise RuntimeError("网络错误: %s" % (err.reason,))
    try:
        return body["choices"][0]["message"]["content"].strip()
    except (KeyError, IndexError, TypeError):
        raise RuntimeError("响应格式异常: " + json.dumps(body, ensure_ascii=False)[:300])


def alignment_line(generation_mode, duration):
    """按生成模式返回图片对齐指令第一行；T2VA/auto 返回 None。"""
    if generation_mode == "I2VA":
        return "For the target video, at 0.00 seconds into the target video, <Picture 1> (from [Shot 1]) is fully referenced."
    if generation_mode == "FL2VA":
        return (
            "How the reference pictures align with the target video — Picture 1 (from Shot 1) aligns with the "
            "0.00-second mark of the target video; Picture 2 (from [Shot N]) aligns with the "
            "{:.2f}-second mark of the target video.".format(duration)
        )
    if generation_mode == "L2VA":
        return (
            "How the reference pictures align with the target video — <Picture 1> (from [Shot N]) aligns with the "
            "{:.2f}-second mark of the target video.".format(duration)
        )
    return None


def build_template(text, generation_mode, duration, aspect_ratio):
    """离线模板骨架：按 generation_mode 拼装官方结构。"""
    text = (text or "").strip()
    if not text:
        return "（模板骨架模式）请输入需求文本。"
    duration_num = 15.0
    header_parts = []
    if duration != "自动":
        duration_num = float(duration)
        header_parts.append("Duration: %s seconds." % duration)
    if aspect_ratio != "自动":
        header_parts.append("Aspect ratio: %s." % aspect_ratio)
    header = ""
    if header_parts:
        header = "# " + " ".join(header_parts) + "\n\n"

    if generation_mode == "Ref2VA":
        return header + (
            "subject_definitions:\n"
            "<Subject 1> is ...（定义可复用内容，例如：图1中的人物，需保持的外貌特征）\n"
            "<Picture 1> is ...（若某张图作为具体帧/构图锚点）\n"
            "<Video 1> is ...（若原视频被编辑/续写/参考结构）\n"
            "<Audio 1> is ...（若音频被复制或参考）\n\n"
            "summary:\n"
            "[reference generation] ...（任务类型可组合，如 [video editing + audio reuse]）\n\n"
            "retention_analysis:\n"
            "<Subject 1> (appears in [Shot 1]): fully_preserved - ...（每行一个标签）\n\n"
            "detailed_description:\n"
            + text + "\n\n"
            "overall_soundscape:\n...（全片环境音与物理音效，1-4 句）\n\n"
            "non_diegetic_music:\nN/A"
        )

    body = (
        "integrated_multimodal_description: [Shot 1] " + text + "\n\n"
        "overall_soundscape: ...（全片环境音与物理音效，1-4 句；不要则写 N/A）\n\n"
        "non_diegetic_music: N/A"
    )
    line = alignment_line(generation_mode, duration_num)
    if line:
        return header + line + "\n\n" + body
    return header + body
```

- [ ] **Step 4: 运行测试，确认通过**

Run: `python comfyui-h3-prompt-builder/self_test.py`
Expected: 全部 PASS（TestConfig 2 项、TestTemplate 4 项、TestSystemPrompt 2 项）

- [ ] **Step 5: Commit**

```bash
git add comfyui-h3-prompt-builder/nodes.py comfyui-h3-prompt-builder/self_test.py
git commit -m "feat: add h3 prompt core logic (config/rules/template/llm)"
```

---

### Task 4: 节点类 + 注册

**Files:**
- Modify: `comfyui-h3-prompt-builder/self_test.py`（追加节点接口测试）
- Create: `comfyui-h3-prompt-builder/__init__.py`

- [ ] **Step 1: 追加失败测试（节点类尚不存在）**

在 `comfyui-h3-prompt-builder/self_test.py` 中，把以下测试类插入到文件末尾 `if __name__ == "__main__":` 块**之前**（放在其他测试类之后）：

```python
class TestNodeInterface(unittest.TestCase):
    def test_input_types(self):
        it = nodes.H3PromptBuilder.INPUT_TYPES()
        self.assertIn("required", it)
        self.assertIn("text", it["required"])
        self.assertIn("mode", it["required"])
        self.assertIn("optional", it)
        self.assertIn("api_key", it["optional"])

    def test_template_dispatch(self):
        node = nodes.H3PromptBuilder()
        out = node.build("一只猫在窗台上晒太阳。", "模板骨架", "T2VA", "通用", "自动", "自动", "自动（英文结构+保留原文）")
        self.assertIn("integrated_multimodal_description", out[0])

    def test_llm_without_key_returns_message(self):
        node = nodes.H3PromptBuilder()
        out = node.build("一个女孩撑伞。", "LLM 改写", "auto", "通用", "自动", "自动", "自动（英文结构+保留原文）", api_key="")
        self.assertIn("未配置 API Key", out[0])
```

- [ ] **Step 2: 运行测试，确认失败**

Run: `python comfyui-h3-prompt-builder/self_test.py`
Expected: FAIL（`AttributeError: module 'nodes' has no attribute 'H3PromptBuilder'`）

- [ ] **Step 3: 在 nodes.py 末尾追加节点类**

在 `comfyui-h3-prompt-builder/nodes.py` 文件末尾追加：

```python
class H3PromptBuilder:
    """ComfyUI 节点：输入 text，输出 H3 提示词。"""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "text": ("STRING", {"multiline": True, "default": "描述需求：主体、场景、动作、风格；如有参考素材请写明每个素材的用途（例如：图1是人物参考，视频1是动作参考）。"}),
                "mode": (MODES, {"default": "LLM 改写"}),
                "generation_mode": (GENERATION_MODES, {"default": "auto"}),
                "style": (list(STYLE_KEYS.keys()), {"default": "通用"}),
                "duration": (DURATIONS, {"default": "自动"}),
                "aspect_ratio": (ASPECT_RATIOS, {"default": "自动"}),
                "output_language": (OUTPUT_LANGUAGES, {"default": "自动（英文结构+保留原文）"}),
            },
            "optional": {
                "api_key": ("STRING", {"default": ""}),
                "model": ("STRING", {"default": ""}),
                "base_url": ("STRING", {"default": ""}),
            },
        }

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("h3_prompt",)
    FUNCTION = "build"
    CATEGORY = "MiniMax H3"

    def build(self, text, mode, generation_mode, style, duration, aspect_ratio, output_language, api_key="", model="", base_url=""):
        if mode == "LLM 改写":
            return self._build_llm(text, style, output_language, api_key, model, base_url)
        return (build_template(text, generation_mode, duration, aspect_ratio),)

    def _build_llm(self, text, style, output_language, api_key, model, base_url):
        text = (text or "").strip()
        if not text:
            return ("请输入需求文本。",)
        config = load_config()
        key = (api_key or "").strip() or config.get("api_key", "")
        if not key:
            return ("未配置 API Key：请在节点 api_key 输入框或 config.json 中填写。",)
        model_name = (model or "").strip() or config.get("model", "deepseek-v4-flash")
        endpoint = (base_url or "").strip() or config.get("base_url", "https://api.deepseek.com/chat/completions")
        system_prompt = build_system_prompt(style, output_language)
        try:
            output = call_llm(
                endpoint,
                key,
                model_name,
                system_prompt,
                text,
                temperature=config.get("temperature", 0.4),
                max_tokens=config.get("max_tokens", 8192),
            )
            return (output,)
        except Exception as exc:
            return ("LLM 调用失败：%s" % (exc,),)
```

- [ ] **Step 4: 创建 __init__.py**

`comfyui-h3-prompt-builder/__init__.py`:

```python
from .nodes import H3PromptBuilder

NODE_CLASS_MAPPINGS = {
    "H3PromptBuilder": H3PromptBuilder,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "H3PromptBuilder": "H3 Prompt Builder（提示词生成）",
}

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS"]
```

- [ ] **Step 5: 运行测试，确认通过**

Run: `python comfyui-h3-prompt-builder/self_test.py`
Expected: 全部 PASS（TestConfig 2、TestTemplate 4、TestSystemPrompt 2、TestNodeInterface 3，共 11 项）

- [ ] **Step 6: Commit**

```bash
git add comfyui-h3-prompt-builder/__init__.py comfyui-h3-prompt-builder/nodes.py comfyui-h3-prompt-builder/self_test.py
git commit -m "feat: add H3PromptBuilder node and registration"
```

---

### Task 5: README + 全量测试收尾

**Files:**
- Create: `comfyui-h3-prompt-builder/README.md`

- [ ] **Step 1: 创建 README.md**

`comfyui-h3-prompt-builder/README.md`:

```markdown
# ComfyUI H3 Prompt Builder

把大白话需求改写成符合 MiniMax H3 官方格式的提示词，直接接入 R2V / T2V / I2V 节点的 prompt 输入口。

## 安装

1. 把整个文件夹复制到 `ComfyUI/custom_nodes/ComfyUI-H3-Prompt-Builder`。
2. 重启 ComfyUI（或用 Manager 刷新）。
3. 编辑 `config.json` 填入你的 API Key（也可以不填，在节点输入框里填）。

## 使用

右键添加节点：`MiniMax H3` → `H3 Prompt Builder（提示词生成）`。

节点参数：
- `text`：你的需求（主体/场景/动作/风格），或素材说明（例如：图1是人物参考，视频1是动作参考）。
- `mode`：`LLM 改写`（默认，联网调用 DeepSeek）或 `模板骨架`（离线，生成官方结构骨架）。
- `generation_mode`：`auto` 让模型自动判断，或手动指定 T2VA/I2VA/FL2VA/L2VA/Ref2VA（模板骨架模式必填）。
- `style`：通用或 8 个官方风格规则（产品广告/3D动画/纸艺定格/纸拼贴/MV字幕/品牌宣传/游戏片头/手绘实拍）。
- `duration` / `aspect_ratio`：目标时长与画幅，默认自动。
- `output_language`：默认英文结构+保留台词原文，可选全中文/全英文。
- `api_key` / `model` / `base_url`：留空使用 `config.json` 默认值（默认模型 `deepseek-v4-flash`，默认端点 `https://api.deepseek.com/chat/completions`）。

输出 `h3_prompt`（STRING）接到 H3 节点的 prompt 输入即可。

## R2V 提示

- 提示词里的 `<Picture 1>` `<Video 1>` `<Audio 1>` 标签顺序，必须和你在 R2V 节点上连接参考素材的顺序一致。
- 给每个素材写明用途（人物/风格/动作/运镜/音色），效果更好。
- `ref_image_size`：`match` 快、`max` 保真（最大 2048 短边）。
- 时长按 17 帧/块 @24fps 网格吸附。

## 离线自检

```bash
python self_test.py
```

## 配置项（config.json）

| 字段 | 默认 | 说明 |
|---|---|---|
| base_url | https://api.deepseek.com/chat/completions | OpenAI 兼容端点（可换中转地址） |
| model | deepseek-v4-flash | 模型名 |
| api_key | 空 | API Key（也可在节点输入框填） |
| temperature | 0.4 | 采样温度 |
| max_tokens | 8192 | 最大输出 token |

## 常见问题

- **提示「未配置 API Key」**：在节点 `api_key` 输入框或 `config.json` 里填 key。
- **提示「LLM 调用失败：HTTP 404」**：检查 `model`/`base_url` 是否正确（中转站模型名可能不同）。
- **模板骨架模式**：不联网、不花钱，输出的是需要手工补全的骨架。
```

- [ ] **Step 2: 全量测试**

Run: `python comfyui-h3-prompt-builder/self_test.py`
Expected: 全部 PASS（11 项）

- [ ] **Step 3: Commit**

```bash
git add comfyui-h3-prompt-builder/README.md
git commit -m "docs: add plugin readme"
```

---

### Task 6: 部署到 ComfyUI + LLM 实弹冒烟

**Files:**
- Deploy: 复制 `comfyui-h3-prompt-builder/` → `F:\comfyui\ComfyUI-aki-v2\ComfyUI\custom_nodes\ComfyUI-H3-Prompt-Builder`
- Modify（部署副本，不入 git）: `config.json` 的 `api_key` 填入用户提供的 key

- [ ] **Step 1: 复制到 custom_nodes**

```powershell
Copy-Item -LiteralPath 'C:\Users\Administrator\Documents\ChatGPT\minimax h3 prompt\comfyui-h3-prompt-builder' -Destination 'F:\comfyui\ComfyUI-aki-v2\ComfyUI\custom_nodes\ComfyUI-H3-Prompt-Builder' -Recurse -Force
```

- [ ] **Step 2: 部署副本 config.json 填入 API Key（敏感值，不写 git）**

用 Python 或编辑器把部署副本 `F:\comfyui\ComfyUI-aki-v2\ComfyUI\custom_nodes\ComfyUI-H3-Prompt-Builder\config.json` 的 `"api_key"` 改为用户在对话中提供的 key。

- [ ] **Step 3: LLM 实弹冒烟测试（最小请求）**

Run（工作目录 = 部署副本目录，不打印 key）:
```bash
python -c "import nodes; c=nodes.load_config(); r=nodes.call_llm(c['base_url'], c['api_key'], c['model'], '只回复两个字：成功', '连通性测试', temperature=0, max_tokens=10); print('SMOKE_OK:', r[:40])"
```
Expected: `SMOKE_OK: 成功`（若报错，反馈用户确认端点/模型名，例如中转地址或 `deepseek-chat`）

- [ ] **Step 4: 验证部署副本自检通过**

Run（部署副本目录）: `python self_test.py`
Expected: 全部 PASS（11 项）

---

### Task 7: 手动验证清单（交付给用户）

- [ ] 重启 ComfyUI，确认节点出现在 `MiniMax H3` 分类
- [ ] 添加节点，`mode=模板骨架`，填一句需求，输出出现三字段骨架
- [ ] 添加节点，`mode=LLM 改写`，`style=通用`，填需求，输出完整提示词
- [ ] R2V 工作流：把 `h3_prompt` 接到 `MiniMaxH3ReferenceToVideo` 的 prompt 输入；参考素材连接顺序与提示词标签一致

---

## 自检（计划 vs 规格）

- 规格「节点接口」→ Task 4（INPUT_TYPES / build 分发）✓
- 规格「LLM 改写模式」→ Task 3 `build_system_prompt`/`call_llm` + Task 4 `_build_llm` ✓
- 规格「模板骨架模式」→ Task 3 `build_template`/`alignment_line` ✓
- 规格「R2V 兼容」→ Task 5 README + Task 7 验证清单 ✓
- 规格「错误处理」→ `call_llm` 异常转可读消息、无 key 提示、空文本提示 ✓
- 规格「测试」→ Task 3/4/5 `self_test.py` + Task 6 冒烟 ✓
- 规格「不做」→ 无任务涉及锚点图/BGM/合片 ✓
