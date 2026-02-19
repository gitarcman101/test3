"""
Configuration loader utility
"""

import yaml
import os
from pathlib import Path
from dotenv import load_dotenv
from typing import Dict, Any

class ConfigLoader:
    """Load and manage configuration from YAML and environment variables"""
    
    def __init__(self, config_path: str = "config/config.yaml"):
        self.config_path = Path(config_path)
        self.config: Dict[str, Any] = {}
        self.env_vars: Dict[str, str] = {}
        
    def load(self) -> Dict[str, Any]:
        """Load configuration from YAML and .env files"""
        # Load environment variables
        load_dotenv("config/.env")
        
        # Load YAML configuration
        if self.config_path.exists():
            with open(self.config_path, 'r', encoding='utf-8') as f:
                self.config = yaml.safe_load(f)
        else:
            raise FileNotFoundError(f"Config file not found: {self.config_path}")
        
        # Store environment variables
        self.env_vars = {
            'ANTHROPIC_API_KEY': os.getenv('ANTHROPIC_API_KEY', ''),
            'NOTION_API_KEY': os.getenv('NOTION_API_KEY', ''),
            'AIRTABLE_API_KEY': os.getenv('AIRTABLE_API_KEY', ''),
            'STIBEE_API_KEY': os.getenv('STIBEE_API_KEY', ''),
            'SLACK_BOT_TOKEN': os.getenv('SLACK_BOT_TOKEN', ''),
            'SLACK_CHANNEL_ID': os.getenv('SLACK_CHANNEL_ID', ''),
        }
        
        return self.config
    
    def get(self, key: str, default: Any = None) -> Any:
        """Get configuration value by dot notation key (e.g., 'newsletter.name')"""
        keys = key.split('.')
        value = self.config
        
        for k in keys:
            if isinstance(value, dict):
                value = value.get(k, default)
            else:
                return default
        
        return value
    
    def get_env(self, key: str, default: str = '') -> str:
        """Get environment variable"""
        return self.env_vars.get(key, default)

# Global config instance
config = ConfigLoader()
