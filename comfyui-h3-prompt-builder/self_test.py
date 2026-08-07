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

    def test_retries_when_stop_with_empty_content(self):
        fake, calls = self._fake_urlopen([
            {"choices": [{"message": {"content": ""}, "finish_reason": "stop"}]},
            {"choices": [{"message": {"content": "done"}, "finish_reason": "stop"}]},
        ])
        with unittest.mock.patch.object(nodes.urllib.request, "urlopen", side_effect=fake):
            result = nodes.call_llm("https://api.deepseek.com", "k", "m", "sys", "user", max_tokens=8192)
        self.assertEqual(result, "done")
        self.assertEqual(calls["n"], 2)

    def test_thinking_disabled_in_payload(self):
        captured = {}

        def fake(request, timeout=120):
            captured["body"] = json.loads(request.data.decode("utf-8"))

            class FakeResp:
                def read(self):
                    return json.dumps({"choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}]}).encode("utf-8")

                def __enter__(self):
                    return self

                def __exit__(self, *args):
                    return False

            return FakeResp()

        with unittest.mock.patch.object(nodes.urllib.request, "urlopen", side_effect=fake):
            nodes.call_llm("https://api.deepseek.com", "k", "m", "sys", "user")
        self.assertEqual(captured["body"]["thinking"], {"type": "disabled"})


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
        self.assertIn("图库第 1 张", note)
        self.assertNotIn("你的图", note)

    def test_per_shot_wiring(self):
        out = manju_nodes.build_per_shot_wiring(self.STORYBOARD, self.MAPPING)
        self.assertIn("Shot 1:", out)
        self.assertIn("Shot 2:", out)
        self.assertIn("角色A", out)
        self.assertIn("图库第 1 张", out)
        self.assertNotIn("你的图", out)

    def test_per_shot_wiring_invalid(self):
        self.assertEqual(manju_nodes.build_per_shot_wiring("bad", "{}"), "")


class TestManjuSystemPrompt(unittest.TestCase):
    def test_rules_exist_and_extra_injected(self):
        sp = manju_nodes.build_manju_system_prompt("manju_storyboard.txt", "【本集预设】{}")
        self.assertIn("分镜导演", sp)
        self.assertIn("本集预设", sp)


class TestManjuNodes(unittest.TestCase):
    def test_input_types(self):
        for cls in (
            manju_nodes.ManjuPreset,
            manju_nodes.ManjuScriptToStoryboard,
            manju_nodes.ManjuResourceMapping,
            manju_nodes.ManjuShotPrompt,
            manju_nodes.ManjuLlmConfig,
        ):
            it = cls.INPUT_TYPES()
            self.assertIn("required", it)

    def test_preset_node(self):
        node = manju_nodes.ManjuPreset()
        out = node.build("古风", "9:16", "120", "自动（英文结构+保留原文）")
        self.assertIn("duration", out[0])

    def test_mapping_node(self):
        node = manju_nodes.ManjuResourceMapping()
        out = node.build("角色A=图1", "")
        self.assertIn("角色A", out[0])

    def test_storyboard_node_empty_script(self):
        node = manju_nodes.ManjuScriptToStoryboard()
        out = node.build("", "{}", api_key="")
        self.assertIn("请输入剧本", out[0])

    def test_shot_prompt_node_bad_json(self):
        node = manju_nodes.ManjuShotPrompt()
        out = node.build("not json", "{}", 1, api_key="")
        self.assertIn("错误：", out[0])


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
        out = node.build("", self.ASSETS, "关闭")
        mapping = json.loads(out[0])
        self.assertEqual(mapping["角色A"], 1)
        self.assertEqual(mapping["场景A"], 2)
        self.assertEqual(mapping["道具A"], 3)
        self.assertIn("角色A=图1", out[1])

    def test_image_prompts(self):
        node = manju_nodes.ManjuResourceMapping()
        out = node.build("", self.ASSETS, "离线模板")
        self.assertIn("角色A", out[2])
        self.assertIn("黑发少年", out[2])
        self.assertIn("设定图", out[2])
        self.assertIn("三视图", out[2])


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
            captured.append(args[4])
            return "P"

        node = manju_nodes.ManjuShotPrompt()
        with unittest.mock.patch.object(manju_nodes, "call_llm", side_effect=fake_llm):
            node.build(sb_json, TestManjuRefs.MAPPING, 1, api_key="k")
        self.assertIn("仅禁字幕", captured[0])

    def test_storyboard_content_in_user_message(self):
        captured = []

        def fake_llm(*args, **kwargs):
            captured.append((args[3], args[4]))
            return '{"storyboard": {"shots": []}, "assets": {}}'

        node = manju_nodes.ManjuScriptToStoryboard()
        with unittest.mock.patch.object(manju_nodes, "call_llm", side_effect=fake_llm):
            node.build("第一集测试剧本", "{}", api_key="k")
        system, user_msg = captured[0]
        self.assertNotIn("第一集测试剧本", system)
        self.assertIn("第一集测试剧本", user_msg)
        self.assertIn("剧本原文", user_msg)

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

    def test_per_shot_wiring_output(self):
        node = manju_nodes.ManjuResourceMapping()
        out = node.build("", TestAutoSuggest.ASSETS, "关闭", TestManjuRefs.STORYBOARD)
        self.assertIn("Shot 1:", out[3])

    def test_per_shot_wiring_empty_without_storyboard(self):
        node = manju_nodes.ManjuResourceMapping()
        out = node.build("", TestAutoSuggest.ASSETS, "关闭")
        self.assertEqual(out[3], "")


class TestShotSelect(unittest.TestCase):
    def test_filtered_mapping_shot1(self):
        node = manju_nodes.ManjuResourceMapping()
        out = node.build("", TestAutoSuggest.ASSETS, "关闭", TestManjuRefs.STORYBOARD, 1)
        mapping = json.loads(out[0])
        self.assertEqual(mapping, {"角色A": 1, "场景A": 2})
        self.assertIn("角色A=图1", out[1])
        self.assertNotIn("角色B", out[1])
        self.assertIn("Shot 1:", out[3])
        self.assertNotIn("Shot 2:", out[3])

    def test_default_zero_full(self):
        node = manju_nodes.ManjuResourceMapping()
        out = node.build("", TestAutoSuggest.ASSETS, "关闭", TestManjuRefs.STORYBOARD, 0)
        self.assertIn("Shot 1:", out[3])
        self.assertIn("Shot 2:", out[3])

    def test_out_of_range(self):
        node = manju_nodes.ManjuResourceMapping()
        out = node.build("", TestAutoSuggest.ASSETS, "关闭", TestManjuRefs.STORYBOARD, 99)
        self.assertIn("错误：镜头序号超出范围", out[3])
        self.assertIn("道具A", out[0])

    def test_image_prompts_unchanged(self):
        node = manju_nodes.ManjuResourceMapping()
        out = node.build("", TestAutoSuggest.ASSETS, "离线模板", TestManjuRefs.STORYBOARD, 1)
        self.assertIn("道具A", out[2])

    def test_input_types_has_shot_index(self):
        it = manju_nodes.ManjuResourceMapping.INPUT_TYPES()
        self.assertEqual(it["optional"]["shot_index"][1].get("default"), 0)

    def test_derive_assets_when_missing(self):
        node = manju_nodes.ManjuResourceMapping()
        out = node.build("", "", "关闭", TestManjuRefs.STORYBOARD, 1)
        mapping = json.loads(out[0])
        self.assertIn("角色A", mapping)
        self.assertIn("场景A", mapping)
        self.assertIn("Shot 1:", out[3])


class TestImagePromptMode(unittest.TestCase):
    def test_default_mode(self):
        it = manju_nodes.ManjuResourceMapping.INPUT_TYPES()
        self.assertEqual(it["optional"]["image_prompt_mode"][1].get("default"), "关闭")

    def test_off_mode_empty(self):
        node = manju_nodes.ManjuResourceMapping()
        out = node.build("", TestAutoSuggest.ASSETS, "关闭")
        self.assertEqual(out[2], "")

    def test_rules_file_content(self):
        content = manju_nodes.read_text_file(os.path.join(manju_nodes.RULES_DIR, "manju_image_prompt.txt"))
        for keyword in ("三视图", "面部特写", "双手自然垂下"):
            self.assertIn(keyword, content)

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

        def call():
            if timeout_arg is None:
                return nodes.call_llm("https://api.deepseek.com/chat/completions", "k", "m", "s", "u")
            return nodes.call_llm("https://api.deepseek.com/chat/completions", "k", "m", "s", "u", timeout=timeout_arg)

        return captured, call

    def test_config_timeout_used(self):
        captured, call = self._patch_llm({"thinking_disabled": True, "request_timeout": 240})
        with unittest.mock.patch("urllib.request.urlopen", side_effect=self._fake_urlopen(captured)), \
                unittest.mock.patch.object(nodes, "load_config", return_value={"thinking_disabled": True, "request_timeout": 240}):
            call()
        self.assertEqual(captured["timeout"], 240)

    def test_explicit_timeout_wins(self):
        captured, call = self._patch_llm({"thinking_disabled": True}, timeout_arg=77)
        with unittest.mock.patch("urllib.request.urlopen", side_effect=self._fake_urlopen(captured)), \
                unittest.mock.patch.object(nodes, "load_config", return_value={"thinking_disabled": True}):
            call()
        self.assertEqual(captured["timeout"], 77)

    def _fake_urlopen(self, captured):
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

        return fake_urlopen


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


if __name__ == "__main__":
    unittest.main(verbosity=2)
