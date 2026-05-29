"""
LLM Module - Language model interface via Ollama
"""

from llm.ollama import call_chat, call_llm, stream_chat

__all__ = [
    "call_chat",
    "call_llm",
    "stream_chat",
]
