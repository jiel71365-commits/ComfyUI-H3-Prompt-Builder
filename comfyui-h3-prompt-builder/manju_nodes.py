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
AUDIO_TEXT_POLICIES = ["禁字幕+无BGM", "仅禁BGM", "仅禁字幕", "保留默认"]
DEFAULT_MANJU_POLICY = "禁字幕+无BGM"


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
