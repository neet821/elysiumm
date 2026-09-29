"""Compatibility exports for the direct music provider adapters."""

from .direct import DirectMusicProvider
from .netease import NeteaseProviderAdapter
from .qq import QQProviderAdapter

__all__ = ["DirectMusicProvider", "NeteaseProviderAdapter", "QQProviderAdapter"]
