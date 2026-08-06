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


if __name__ == "__main__":
    unittest.main(verbosity=2)
