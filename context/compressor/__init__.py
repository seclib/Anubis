"""Context compressor contract."""

from anubis.context.compressor.compressor import ContextCompressor as AdvancedContextCompressor
from anubis.context.interfaces import ContextCompressor

__all__ = ["AdvancedContextCompressor", "ContextCompressor"]
