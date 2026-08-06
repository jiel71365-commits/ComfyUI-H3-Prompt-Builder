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
            with open(CONFIG_PATH, "r", encoding="utf-8-sig") as f:
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


def normalize_endpoint(base_url):
    """把用户填的接口地址规范化为 Chat Completions 端点。"""
    url = (base_url or "").strip().rstrip("/")
    if not url:
        return url
    if url.endswith("/chat/completions"):
        return url
    if url.endswith("/v1"):
        return url + "/chat/completions"
    return url + "/chat/completions"


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
    base_url = normalize_endpoint(base_url)
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
        content = body["choices"][0]["message"].get("content") or ""
        content = content.strip()
    except (KeyError, IndexError, TypeError):
        raise RuntimeError("响应格式异常: " + json.dumps(body, ensure_ascii=False)[:300])
    if not content:
        raise RuntimeError(
            "模型未返回正文（推理型模型可能占满了 max_tokens，请调大 config.json 的 max_tokens）"
        )
    return content


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
