"""
Environment configuration management for Syntax Prime V2.
Single source of truth for all environment variables.
"""

import os
from typing import Optional


class Settings:
    """Application settings from environment variables."""
    
    def __init__(self):
        self.database_url: str = self._get_required("DATABASE_URL")
        self.environment: str = self._get_optional("ENVIRONMENT", "development")
        self.debug: bool = self._get_optional("DEBUG", "false").lower() == "true"
        self.log_level: str = self._get_optional("LOG_LEVEL", "INFO")
        
    def _get_required(self, key: str) -> str:
        """Get required environment variable or raise error."""
        value = os.getenv(key)
        if not value:
            raise ValueError(f"Required environment variable {key} not found")
        return value
    
    def _get_optional(self, key: str, default: str) -> str:
        """Get optional environment variable with default."""
        return os.getenv(key, default)


# Global settings instance
settings = Settings()