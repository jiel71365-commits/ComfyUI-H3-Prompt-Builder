# 漫剧插件 v2.4 设计文档（设定图提示词拆分 + 分镜质量增强 + 导演审阅）

- 日期：2026-08-07
- 状态：待用户审阅（用户已确认方案 B、审阅直到 PASS 为止）
- 载体：现有插件 `ComfyUI-H3-Prompt-Builder`，改动集中在 `manju_nodes.py`、`rules/manju_storyboard.txt`（升级）、`rules/manju_review.txt`（新增）、`config.json`、`self_test.py`、`README.md`

## 1. 背景

1. 「漫剧：资源映射」节点内置的图像提示词生成与资源映射耦合，shot_index 变化会重复触发、大资源清单偶发 120s 超时；需要拆成独立节点，生成一次即可。
2. 用户反馈「剧本 → 分镜」输出质量一般。调研 GitHub 多个分镜技能（worldwonderer/drama-skills、cclank/lanshu-awesome-ai-video-kit、zhlmi/script-forging、rainlib/AI-Storyboard）后，确认最有价值的技法应蒸馏进分镜规则，并增加「导演审阅」环节：初稿 → 审阅 → 修正 → 复核，直到 PASS。

## 2. 范围

### 做
- 新增独立节点「漫剧：设定图提示词」（`ManjuImagePrompt`），输出可用于外部生图模型（即梦 / image2 等）的设定图提示词文本。
- 「漫剧：资源映射」的图像提示词功能改为默认关闭，保留开关兼容旧工作流。
- `config.json` 新增 `request_timeout`（默认 240s）、`reviewer_temperature`（默认 0.1）、`max_review_rounds`（默认 5）。
- 升级 `rules/manju_storyboard.txt`：镜头目的、覆盖率、轴线/屏幕方向、起止边界强化、肢体级动作、情绪外化、一镜一运镜、时间对账、内置 few-shot 样例。
- 新增节点「漫剧：导演审阅」（`ManjuDirectorReview`）与规则文件 `rules/manju_review.txt`；审阅循环直到 PASS，安全上限 `max_review_rounds` 轮。
- 扩展 `self_test.py`，保持现有测试全部通过。

### 不做
- 不在插件内接生图模型（提示词与生图模型无关，用户自行测试）。
- 不在 H3 镜头提示词层增加审阅（六段式规则已成熟，先观察分镜层提升）。
- 不重写分镜 JSON 顶层结构（`storyboard` + `assets` 保持不变，向后兼容现有节点）。
- 不做首尾帧方案（沿用用户既定策略：以镜头语言与时长控制为主）。

## 3. 第一部分：设定图提示词节点（`ManjuImagePrompt`）

### 输入 / 输出
- 输入（required）：`assets_json`（角色/场景/道具清单）、`preset_json`（style 等）
- 输入（optional）：`api_key`、`model`、`base_url`、`llm_config`
- 输出：`image_prompts`（文本，按资源分组：角色设定图 / 场景空镜图 / 道具特写图）
- 复用现有 `resolve_llm_config` 与 `call_llm`，遵守 `request_timeout`。

### 规则
- 复用 `rules/manju_image_prompt.txt`（v2.3 已建立），系统提示词不变。
- 角色设定图：三视图 + 面部特写合成一张参考表；人物自然站立、双手自然垂下；写清外观、服装（含材质细节）、体态与气质；9:16 竖屏、简洁纯色背景、柔和均匀光。
- 场景空镜图：环境主体、时间与光线、氛围；明确无人、无文字、干净构图。
- 道具特写图：材质、结构、视角、背景。
- 每条末尾统一附加负面块（无文字/字幕/水印/logo、无多余人物、无变形手指肢体、无低质量、无漫画对话框）。
- 失败时输出「图像提示词生成失败：<原因>」，不阻塞其他输出。

### 资源映射节点调整
- `generate_image_prompts` / `image_prompt_mode` 默认改为「关闭」；用户可在设定图节点单独生成，一次调用即可。
- 保留旧模式（LLM 生成 / 离线模板 / 关闭）以防旧工作流回退。

## 4. 第二部分：分镜规则升级（`rules/manju_storyboard.txt`）

保持输出 JSON 顶层结构不变，新增/强化以下内容：

### 4.1 每个镜头新增字段
- `purpose`：镜头目的——观众此刻必须注意什么、情绪/信息发生什么变化、为什么在这里切镜头（而非留在前一镜）。
- `screen_direction`：轴线与屏幕方向——谁固定占画面左/右、未越轴、进出场方向（无多主体时可省略）。
- `continuity.start` / `continuity.end` 强化为「边界锁」：位置、姿态、目线、持物、道具所有权逐项对齐；镜头 N 的 end 必须与镜头 N+1 的 start 一致。

### 4.2 全片新增字段
- `coverage`：数组 `[{beat, source_text, shot_ids, status}]`，`status` 取值 `covered` / `intentional_repeat` / `omitted_with_reason` / `nonvisual_context`；剧本每个关键节拍必须登记，防止丢戏。

### 4.3 硬规则强化
- 动作具体到肢体（“慢慢抬手、用力攥地”），禁用“奔跑/战斗/哭泣/惊讶”等抽象词；情绪按「情绪外化表」写成具体表情、手势、呼吸、视线细节（规则内置 10 种常见情绪对照）。
- 一镜一运镜：只写一种主运镜，写明起点、速度/节奏、终点；禁止“推+摇”同用。
- 时间对账：各镜头 `duration` 之和必须等于 `duration_seconds`；时间范围连续无空洞、无重叠；15s 内建议 3–5 个镜头、按事件顺序组织。
- 台词逐字保留并标注说话人；台词长度与镜头时长匹配。
- 规则末尾内置 1 个高质量镜头设计样例（few-shot，参考 drama-skills demo 的颗粒度），供模型模仿。

## 5. 第三部分：导演审阅节点（`ManjuDirectorReview`）

### 输入 / 输出
- 输入（required）：`storyboard_json`（分镜 JSON，含 storyboard + assets）、`script`（剧本原文）、`preset_json`
- 输入（optional）：`api_key`、`model`、`base_url`、`llm_config`
- 输出：`reviewed_storyboard_json`（审阅通过或修正后的分镜 JSON）、`assets_json`（修正后资产）、`review_report`（PASS / 问题清单 / 未决警告）

### 审阅规则（`rules/manju_review.txt`）
以独立「导演审阅」角色执行，检查维度：
1. **覆盖率**：剧本关键节拍是否全部 `covered`，省略项是否注明原因。
2. **轴线/屏幕方向**：是否越轴、左右占位是否跨镜一致。
3. **连续性**：道具所有权、位置、姿态、目线跨镜头衔接；`continuity.end` 与下一镜 `start` 是否一致。
4. **时长对账**：各镜头时长之和是否等于目标时长；是否连续无重叠。
5. **动作具体性**：是否存在抽象动词，应改为肢体级描述。
6. **情绪外化**：情绪是否通过具体表情/手势/呼吸呈现。
7. **资产完整性**：`assets` 是否遗漏实际出场角色/场景/道具，或包含未出场项（对应历史「图11」类问题）。
8. **台词**：是否逐字保留、长度是否匹配。

输出结构化 JSON：
```json
{
  "verdict": "PASS | FAIL",
  "issues": [
    {"severity": "high | medium", "shot_id": "3", "field": "continuity", "problem": "...", "suggestion": "..."}
  ],
  "summary": "一句话总结"
}
```

### 审阅循环（直到 PASS）
1. 调审阅 LLM（`reviewer_temperature`，默认 0.1），解析 `verdict` 与 `issues`。
2. `verdict == PASS`：输出当前分镜 + 审阅报告（含问题清单，medium 及以下不阻塞）。
3. `verdict == FAIL`：调修正 LLM——以 `manju_storyboard.txt` 为系统提示，user 消息含「剧本原文 + 当前分镜 JSON + 审阅问题清单 + 仅修复所列问题、保持其余内容不变」；只动问题镜头/资产，不重写全片。
4. 修正后回到步骤 1 重新审阅；**直到 PASS 为止**。
5. 安全上限：达到 `max_review_rounds`（默认 5，可配置）次审阅仍未 PASS 时，交付当前修正版 + 未决问题清单 + 明确警告（“已达最大审阅轮数，未全部通过”），不无限循环烧 token。
6. 任一轮 LLM 调用失败：返回错误文本，不覆盖输入分镜。

### 数据流
```
剧本 → [漫剧：剧本到分镜] → storyboard_json
     → [漫剧：导演审阅（可选，手动接线）] → reviewed_storyboard_json
     → [漫剧：资源映射] → mapping_json
     → [漫剧：镜头提示词] → H3 提示词
```

## 6. 配置

`config.json` 新增：
```json
{
  "request_timeout": 240,
  "reviewer_temperature": 0.1,
  "max_review_rounds": 5
}
```
- `request_timeout`：所有 LLM 调用的超时上限（覆盖现有硬编码 120s）。
- `reviewer_temperature`：审阅调用专用温度；生成/修正沿用现有 `manju_temperature`。
- `max_review_rounds`：审阅安全上限，默认 5。

## 7. 兼容性

- 分镜 JSON 顶层结构不变；新增字段对 `ManjuResourceMapping`、`ManjuShotPrompt` 透明。
- 审阅节点手动接线，不插即不审，旧工作流零影响。
- 资源映射图像提示词默认关闭；旧工作流可通过模式开关恢复。
- `call_llm` 增加超时参数，向后兼容现有调用。

## 8. 测试

`self_test.py` 新增：
- `ManjuDirectorReview`：
  - 首次审阅 PASS：只调用 1 次，输出与输入一致，report 含 PASS。
  - 首次 FAIL、复核 PASS：调用 3 次（审阅→修正→复核），输出为修正版。
  - 始终 FAIL 至上限：调用次数受 `max_review_rounds` 约束，输出含未决警告。
  - 无 API key：返回错误文本。
  - mock 断言修正请求消息包含问题清单与「仅修复所列问题」指令。
- `ManjuImagePrompt`：
  - mock `call_llm`，断言 user 消息含资产清单与预设；`image_prompts` 等于 mock 返回值。
  - 资源映射默认关闭模式输出空 image_prompts。
- 规则文件存在性：`manju_review.txt` 含各审阅维度关键词；`manju_storyboard.txt` 含 `purpose`、`coverage`、情绪外化、few-shot 样例标记。
- 现有 59 个测试保持通过。

## 9. 文档

- README：新增「漫剧：设定图提示词」「漫剧：导演审阅」节点说明、审阅循环与配置项说明。
