"""离线自检：不联网，检查插件结构与核心逻辑。用法：python self_test.py"""

import json
import os
import sys
import unittest
import unittest.mock

PLUGIN_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PLUGIN_DIR)

import nodes  # noqa: E402
import manju_nodes  # noqa: E402


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


class TestEndpoint(unittest.TestCase):
    def test_normalize_endpoint(self):
        self.assertEqual(
            nodes.normalize_endpoint("https://api.deepseek.com"),
            "https://api.deepseek.com/chat/completions",
        )
        self.assertEqual(
            nodes.normalize_endpoint("https://api.deepseek.com/"),
            "https://api.deepseek.com/chat/completions",
        )
        self.assertEqual(
            nodes.normalize_endpoint("https://api.deepseek.com/v1"),
            "https://api.deepseek.com/v1/chat/completions",
        )
        self.assertEqual(
            nodes.normalize_endpoint("https://api.deepseek.com/chat/completions"),
            "https://api.deepseek.com/chat/completions",
        )
        self.assertEqual(nodes.normalize_endpoint(""), "")


class TestCallLlmRetry(unittest.TestCase):
    def _fake_urlopen(self, responses):
        calls = {"n": 0}

        def fake(request, timeout=120):
            calls["n"] += 1
            body = responses[min(calls["n"], len(responses)) - 1]

            class FakeResp:
                def read(self):
                    return json.dumps(body).encode("utf-8")

                def __enter__(self):
                    return self

                def __exit__(self, *args):
                    return False

            return FakeResp()

        return fake, calls

    def test_retries_when_reasoning_exhausts_tokens(self):
        fake, calls = self._fake_urlopen([
            {"choices": [{"message": {"content": ""}, "finish_reason": "length"}]},
            {"choices": [{"message": {"content": "done"}, "finish_reason": "stop"}]},
        ])
        with unittest.mock.patch.object(nodes.urllib.request, "urlopen", side_effect=fake):
            result = nodes.call_llm("https://api.deepseek.com", "k", "m", "sys", "user", max_tokens=8192)
        self.assertEqual(result, "done")
        self.assertEqual(calls["n"], 2)

    def test_raises_when_still_empty(self):
        fake, calls = self._fake_urlopen([
            {"choices": [{"message": {"content": ""}, "finish_reason": "length"}]},
            {"choices": [{"message": {"content": ""}, "finish_reason": "length"}]},
        ])
        with unittest.mock.patch.object(nodes.urllib.request, "urlopen", side_effect=fake):
            with self.assertRaises(RuntimeError) as ctx:
                nodes.call_llm("https://api.deepseek.com", "k", "m", "sys", "user", max_tokens=8192)
        self.assertIn("未返回正文", str(ctx.exception))
        self.assertEqual(calls["n"], 2)


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
        fake_config = {"api_key": "", "model": "x", "base_url": "x", "temperature": 0.4, "max_tokens": 8192}
        with unittest.mock.patch.object(nodes, "load_config", return_value=fake_config):
            out = node.build("一个女孩撑伞。", "LLM 改写", "auto", "通用", "自动", "自动", "自动（英文结构+保留原文）", api_key="")
        self.assertIn("未配置 API Key", out[0])


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


if __name__ == "__main__":
    unittest.main(verbosity=2)
