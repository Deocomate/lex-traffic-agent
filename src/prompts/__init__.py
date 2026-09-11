"""
Chỉ dẫn hệ thống. Persona của miền đến từ Domain Pack; engine chỉ bổ sung phần chung.
"""

from src.prompts.system_vi import RETRIEVAL_SIGNAL_GUIDE, get_system_prompt, get_system_prompt_vi

__all__ = ["RETRIEVAL_SIGNAL_GUIDE", "get_system_prompt", "get_system_prompt_vi"]
