"""Waves and levels: what a game client reads.

The app exposes exactly two things to the platform: `router`, which the platform mounts
without knowing what is on it, and `get_wave_repository`, the port a deployment or a test
points at real storage.
"""

from wavemaker.apps.content.adapters.http import get_wave_repository, router

__all__ = ["get_wave_repository", "router"]
