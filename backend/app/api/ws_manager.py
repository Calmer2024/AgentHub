"""Compatibility re-export for the realtime WebSocket adapter."""

from ..infrastructure.realtime import ConnectionManager, manager

__all__ = ["ConnectionManager", "manager"]
