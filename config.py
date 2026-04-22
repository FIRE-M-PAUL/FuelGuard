"""Compatibility shim: configuration lives in ``backend.config.settings``."""
from backend.config.settings import Config, TestConfig, validate_production_config

__all__ = ["Config", "TestConfig", "validate_production_config"]
