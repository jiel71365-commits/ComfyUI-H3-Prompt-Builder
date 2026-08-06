# 漫剧插件 v2.1 设计文档（逐镜接线汇总 + 措辞优化）

- 日期：2026-08-07
- 状态：已批准（用户选择方案 A+B），待用户审阅本文件后进入实现计划
- 载体：现有插件 `ComfyUI-H3-Prompt-Builder`

## 1. 背景

资源映射自动建议的全局图号（如 `系统界面=图11`）会超过 H3 单次生成 9 张参考图的上限，造成「是不是要连 11 个槽位」的误解。实际上 H3 的 9 张上限是「每次生成（每镜）」的限制，图库可以有超过 9 张图；问题在于展示方式。

## 2. 范围（用户选择 A+B）

### A. 逐镜接线汇总

- 资源映射节点（ManjuResourceMapping）新增**可选输入** `storyboard_json`（STRING 多行，默认 ""）。
- 节点新增**第 4 个输出** `per_shot_wiring`（STRING）：遍历分镜全部镜头，每镜一行列出本镜要连接的参考图（资源名为主、图库编号为辅），离线本地计算，不调用 LLM。
- 输出格式：

```text
Shot 1: <Picture 1>=角色A（图库第 1 张）
Shot 2: <Picture 1>=角色A（图库第 1 张）、<Picture 2>=清晨教室（图库第 3 张）
...
```

- 缺映射资源追加在行尾：`（缺映射：角色B、道具A）`。
- `storyboard_json` 为空或非法时，`per_shot_wiring` 输出空字符串。

### B. 措辞优化

- `build_wiring_note` 中「你的图%d」改为「图库第 %d 张」，以**资源名**为主、图号仅作图库索引说明。
- 新格式：`<Picture 1>=角色A（图库第 1 张）`。

## 3. 本地函数

`manju_nodes.py` 新增：

```python
def build_per_shot_wiring(storyboard_json, mapping_json):
    """逐镜接线汇总（离线）：每镜一行，列出该镜需要连接的参考图。"""
```

复用 `compute_shot_refs` 与 `build_wiring_note`；非法 JSON / 无镜头时返回空字符串或错误行（不崩溃）。

## 4. 节点接口变化

`ManjuResourceMapping`：

| 输入 | 类型 | 默认 | 说明 |
|---|---|---|---|
| mapping_text | STRING 多行 | "" | 不变 |
| assets_json | STRING 多行 | "" | 不变 |
| generate_image_prompts | BOOLEAN | False | 不变 |
| storyboard_json（新增） | STRING 多行 | "" | 用于生成逐镜接线汇总 |

| 输出 | 顺序 | 说明 |
|---|---|---|
| mapping_json | 1 | 不变 |
| suggested_mapping_text | 2 | 不变 |
| image_prompts | 3 | 不变 |
| per_shot_wiring（新增） | 4 | 逐镜接线汇总 |

## 5. 测试

- `build_wiring_note` 新措辞：断言包含 `图库第 1 张`（替换原 `你的图1` 断言）。
- `build_per_shot_wiring`：含 `Shot 1:` 与 `Shot 2:` 行、资源名、缺映射提示；非法 JSON 返回空字符串。
- `ManjuResourceMapping`：传入 `storyboard_json` 时第 4 输出非空；不传时为空。
- 全量自检保持 41 项 + 新增 3–4 项。

## 6. 文档

- README 漫剧章节更新资源映射节点说明（新增输入/输出与逐镜接线用途）。

## 7. 不做

- 不限制分镜资源数量（方案 C 暂缓）。
- 不增强 >9 张的拆分建议（方案 D 暂缓）。
