from .nodes import H3PromptBuilder

NODE_CLASS_MAPPINGS = {
    "H3PromptBuilder": H3PromptBuilder,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "H3PromptBuilder": "H3 Prompt Builder（提示词生成）",
}

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS"]
