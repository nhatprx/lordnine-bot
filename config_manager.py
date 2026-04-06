"""
Config Manager — Type-safe configuration with validation and defaults.

Replaces raw json.load() calls with a validated dataclass.
Backward-compatible: reads existing config.json format.

Usage:
    from config_manager import load_config, save_config
    
    cfg = load_config()
    print(cfg.port)         # 9222
    print(cfg.threshold)    # 0.54
    
    cfg.port = 9223
    save_config(cfg)
"""
import os
import json
import logging
from dataclasses import dataclass, field, asdict

logger = logging.getLogger(__name__)

CONFIG_FILE = "config.json"


@dataclass
class AppConfig:
    """Application configuration with defaults and validation."""
    debug_visual: bool = True
    port: int = 9222
    tab: int = 0
    threshold: float = 0.54
    log_lines: int = 100

    def validate(self):
        """Clamp values to valid ranges."""
        self.port = max(1024, min(65535, self.port))
        self.tab = max(0, self.tab)
        self.threshold = max(0.1, min(1.0, self.threshold))
        self.log_lines = max(20, min(1000, self.log_lines))
        return self


def load_config(filepath=None) -> AppConfig:
    """Load config from file with fallback to defaults.
    
    Args:
        filepath: Override config file path. Default: config.json
        
    Returns:
        Validated AppConfig instance.
    """
    path = filepath or CONFIG_FILE
    if not os.path.exists(path):
        return AppConfig()
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        # Only pass known fields to avoid TypeError on unknown keys
        known_fields = {f for f in AppConfig.__dataclass_fields__}
        filtered = {k: v for k, v in data.items() if k in known_fields}
        cfg = AppConfig(**filtered)
        return cfg.validate()
    except Exception as e:
        logger.warning(f"Config load failed, using defaults: {e}")
        return AppConfig()


def save_config(cfg: AppConfig, filepath=None):
    """Save config to file.
    
    Args:
        cfg: AppConfig instance to save.
        filepath: Override config file path. Default: config.json
    """
    path = filepath or CONFIG_FILE
    try:
        # Merge with existing data to preserve unknown fields
        existing = {}
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    existing = json.load(f)
            except Exception:
                pass
        existing.update(asdict(cfg))
        with open(path, "w", encoding="utf-8") as f:
            json.dump(existing, f, indent=2)
    except Exception as e:
        logger.warning(f"Config save failed: {e}")
