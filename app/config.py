# -*- coding: utf-8 -*-
import os
from typing import List
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field


class AISettings(BaseSettings):
    minimax_key: str = Field(default="", alias="MINIMAX_KEY")
    minimax_base_url: str = "https://api.minimaxi.com/v1"
    minimax_model: str = "MiniMax-M2.7-highspeed"
    minimax_max_tokens: int = 2048
    minimax_temperature: float = 0.7

    kimi_key: str = Field(default="", alias="KIMI_API_KEY")
    kimi_base_url: str = "https://api.moonshot.cn/v1"
    kimi_model: str = "kimi-latest"
    kimi_max_tokens: int = 4096

    ollama_base_url: str = "http://127.0.0.1:11434"
    ollama_model: str = "qwen2.5-coder:7b"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "WinGo"
    app_version: str = "4.0.0"
    host: str = "0.0.0.0"
    port: int = 38888
    debug: bool = False

    project_root: str = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    projects_dir: str = Field(default="")
    memory_dir: str = Field(default="")
    logs_dir: str = Field(default="")

    ai: AISettings = Field(default_factory=AISettings)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if not self.projects_dir:
            self.projects_dir = os.path.join(self.project_root, "projects")
        if not self.memory_dir:
            self.memory_dir = os.path.join(self.project_root, "memory")
        if not self.logs_dir:
            self.logs_dir = os.path.join(self.project_root, "logs")
        os.makedirs(self.projects_dir, exist_ok=True)
        os.makedirs(self.memory_dir, exist_ok=True)
        os.makedirs(self.logs_dir, exist_ok=True)


settings = Settings()
