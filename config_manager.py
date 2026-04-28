# -*- coding: utf-8 -*-
"""Lihtne config_manager veebiversioonile.
Loeb seaded samast kaustast failist config.json.
Ühildub vana koodi kasutusega: cfg.get("section", "key", default=...) ja cfg.get("section", default=...).
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class ConfigManager:
    def __init__(self, filename: str = "config.json") -> None:
        self.path = Path(__file__).with_name(filename)
        self.data: dict[str, Any] = {}
        self.load()

    def load(self) -> None:
        try:
            with self.path.open("r", encoding="utf-8") as f:
                self.data = json.load(f)
        except FileNotFoundError:
            self.data = {}
        except Exception:
            self.data = {}

    def get(self, section: str, key: str | None = None, default: Any = None) -> Any:
        section_data = self.data.get(section, default if key is None else {})
        if key is None:
            return section_data
        if isinstance(section_data, dict):
            return section_data.get(key, default)
        return default


cfg = ConfigManager()
