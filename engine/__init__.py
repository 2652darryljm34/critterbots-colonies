"""Critterbots: Colonies engine. Standard library only; must run unchanged on CPython 3.8+ and Pyodide."""
from .rules import ENGINE_VERSION
from .match import run_match, BotLoadError
