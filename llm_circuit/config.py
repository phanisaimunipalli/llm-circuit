from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Anthropic
    anthropic_api_key: str = ""
    anthropic_upstream_url: str = "https://api.anthropic.com"

    # Fallback (Ollama)
    fallback_ollama_url: str = "http://localhost:11434"
    fallback_model: str = "qwen2.5:14b"

    # Circuit breaker
    failure_threshold: int = 3       # failures before tripping OPEN
    recovery_timeout: int = 30       # seconds before attempting HALF_OPEN
    health_check_interval: int = 5   # seconds between health polls

    # Proxy server
    proxy_host: str = "127.0.0.1"
    proxy_port: int = 8742
    log_level: str = "INFO"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
