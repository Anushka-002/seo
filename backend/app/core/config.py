"""Application settings loaded from environment variables / .env."""

from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Typed runtime configuration. No secrets are hardcoded."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "Seoul"
    version: str = "0.1.0"
    llm_provider: str = "groq"
    groq_api_key: str = ""
    gemini_api_key: str = ""
    serper_api_key: str = ""
    database_url: str = "sqlite:///./data/seoul.db"
    cors_origins: list[str] = ["http://localhost:5173"]
    rate_limit_per_hour: int = 10
    log_level: str = "INFO"
    embedder: str = "sbert"  # sbert | hashing (hashing = offline/test fallback)
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    serp_timeout: float = 10.0
    scrape_timeout: float = 8.0
    scrape_concurrency: int = 5
    min_pages: int = 4
    min_page_words: int = 150
    max_page_bytes: int = 2_000_000
    serp_results: int = 10
    groq_model: str = "llama-3.3-70b-versatile"
    gemini_model: str = "gemini-2.0-flash"  # model names change: override via GEMINI_MODEL
    llm_timeout: float = 45.0
    max_gap_recommendations: int = 8
    max_concurrent_analyses: int = 2
    trusted_proxy_hops: int = 1  # reverse proxies in front of the app (HF Spaces = 1)
    block_private_hosts: bool = True  # SSRF guard for every outbound page fetch
    user_agent: str = "SeoulBot/0.1 (+https://github.com/Anushka-002/seo; SEO research)"

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_origins(cls, v: object) -> object:
        """Allow CORS_ORIGINS as a comma-separated string."""
        if isinstance(v, str) and not v.strip().startswith("["):
            return [o.strip() for o in v.split(",") if o.strip()]
        return v

    @field_validator("llm_provider")
    @classmethod
    def _check_provider(cls, v: str) -> str:
        v = v.lower()
        if v not in {"groq", "gemini"}:
            raise ValueError("llm_provider must be 'groq' or 'gemini'")
        return v

    @property
    def llm_api_key(self) -> str:
        """API key for the selected LLM provider ('' when not configured)."""
        return self.groq_api_key if self.llm_provider == "groq" else self.gemini_api_key

    @property
    def llm_enabled(self) -> bool:
        return bool(self.llm_api_key)

    @property
    def use_serper(self) -> bool:
        """True when a Serper key exists; otherwise DuckDuckGo fallback is used."""
        return bool(self.serper_api_key)


@lru_cache
def get_settings() -> Settings:
    """Cached settings accessor (override in tests via cache_clear)."""
    return Settings()
