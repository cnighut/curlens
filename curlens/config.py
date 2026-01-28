"""Configuration management for curlens."""

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

DEFAULT_CONFIG_DIR = Path.home() / ".cursor" / "curlens"
DEFAULT_CONFIG_PATH = DEFAULT_CONFIG_DIR / "config.json"

DEFAULT_CONFIG = {
    "summary_model": "grok",
    "search_model": "grok",
    "summary_max_words": 70,
    "search_window_days": 20,
    "summary_db_path": str(DEFAULT_CONFIG_DIR / "summary.db"),
    "hooks_enabled": True,
    "debug": False,
}


@dataclass
class CurlensConfig:
    summary_model: str = "grok"
    search_model: str = "grok"
    summary_max_words: int = 70
    search_window_days: int = 20
    summary_db_path: str = field(default_factory=lambda: str(DEFAULT_CONFIG_DIR / "summary.db"))
    hooks_enabled: bool = True
    debug: bool = False


def load_config(config_path: Optional[Path] = None) -> CurlensConfig:
    """Load configuration from JSON file, creating defaults if missing."""
    path = config_path or DEFAULT_CONFIG_PATH
    
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            json.dump(DEFAULT_CONFIG, f, indent=2)
        return CurlensConfig()
    
    with open(path) as f:
        data = json.load(f)
    
    return CurlensConfig(
        summary_model=data.get("summary_model", DEFAULT_CONFIG["summary_model"]),
        search_model=data.get("search_model", DEFAULT_CONFIG["search_model"]),
        summary_max_words=data.get("summary_max_words", DEFAULT_CONFIG["summary_max_words"]),
        search_window_days=data.get("search_window_days", DEFAULT_CONFIG["search_window_days"]),
        summary_db_path=data.get("summary_db_path", DEFAULT_CONFIG["summary_db_path"]),
        hooks_enabled=data.get("hooks_enabled", DEFAULT_CONFIG["hooks_enabled"]),
        debug=data.get("debug", DEFAULT_CONFIG["debug"]),
    )
