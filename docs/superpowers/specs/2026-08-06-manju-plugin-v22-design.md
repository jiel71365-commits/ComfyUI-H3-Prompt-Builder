# 漫剧插件 v2.2 设计文档（资源映射镜头选择）

- 日期：2026-08-07
- 状态：已批准（用户确认设计要点），待用户审阅本文件后进入实现计划
- 载体：现有插件 `ComfyUI-H3-Prompt-Builder`，改动集中在 `manju_nodes.py`、`self_test.py`、`README.md`

## 1. 背景

全局资源映射可能包含 11+ 个资源（图号超过 H3 单次 9 张上限），逐镜生成提示词时希望拿到「只含本镜资源」的精简映射，避免全局映射干扰。

## 2. 范围

### 做
- `ManjuResourceMapping` 新增可选输入 `shot_index`（INT，默认 0，范围 0–999）。
- `shot_index = 0`（默认）或未接分镜 JSON：保持现有行为（全部镜头）。
- `shot_index > 0` 且接入分镜 JSON：
  - `suggested_mapping_text`：只列该镜用到的资源（图号仍为图库编号，如 `角色A=图1`、`清晨教室=图3`）。
  - `mapping_json`：只含该镜资源（更精简、更准确）。
  - `per_shot_wiring`：只输出该镜一行接线。
  - `image_prompts`：保持不变（设定图提示词跟资源走，不跟镜头走）。
- `shot_index` 越界：`per_shot_wiring` 输出错误提示「镜头序号超出范围（1–N）」，其余输出保持全部镜头。

### 不做
- 不改分镜→镜头提示词节点的行为（它本来就按镜头取资源）。
- 不做前端动态下拉（ComfyUI INT 输入即可满足）。

## 3. 实现要点

`ManjuResourceMapping.build` 在现有逻辑末尾追加：

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
```

## 4. 测试

- 过滤：`shot_index=1` 时 `mapping_json` 只含该镜资源（如 角色A/场景A），图号保持全局编号；`suggested_mapping_text` 与 `per_shot_wiring` 均为该镜。
- 默认：`shot_index=0` 时输出与现状一致（含全部镜头）。
- 越界：`per_shot_wiring` 含错误提示，其余输出保持全部。

## 5. 文档

- README 资源映射节点说明追加 `shot_index` 用法（0=全部，N=只看第 N 镜）。
