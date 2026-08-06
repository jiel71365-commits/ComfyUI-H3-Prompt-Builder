from .manju_nodes import (
    ManjuLlmConfig,
    ManjuPreset,
    ManjuResourceMapping,
    ManjuScriptToStoryboard,
    ManjuShotPrompt,
)
from .nodes import H3PromptBuilder

NODE_CLASS_MAPPINGS = {
    "H3PromptBuilder": H3PromptBuilder,
    "ManjuPreset": ManjuPreset,
    "ManjuScriptToStoryboard": ManjuScriptToStoryboard,
    "ManjuResourceMapping": ManjuResourceMapping,
    "ManjuShotPrompt": ManjuShotPrompt,
    "ManjuLlmConfig": ManjuLlmConfig,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "H3PromptBuilder": "H3 Prompt Builder（提示词生成）",
    "ManjuPreset": "漫剧预设",
    "ManjuScriptToStoryboard": "漫剧：剧本→分镜",
    "ManjuResourceMapping": "漫剧：资源映射",
    "ManjuShotPrompt": "漫剧：分镜→镜头提示词",
    "ManjuLlmConfig": "漫剧：LLM 配置",
}

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS"]
