"""
Configuration management for Unreal MCP Server.

Centralized configuration with environment variable support and validation.
"""

import os
from typing import Optional
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class ServerConfig(BaseSettings):
    """Server configuration settings."""
    
    # Server settings
    host: str = Field(default="127.0.0.1", description="Server host")
    port: int = Field(default=55557, description="Server port")
    use_websocket: bool = Field(default=True, description="Use WebSocket instead of TCP")
    
    # Connection settings
    max_connections: int = Field(default=10, description="Maximum concurrent connections")
    connection_timeout: int = Field(default=30, description="Connection timeout in seconds")
    max_retries: int = Field(default=5, description="Maximum retry attempts")
    
    # Performance settings
    enable_caching: bool = Field(default=True, description="Enable caching layer")
    cache_ttl: int = Field(default=3600, description="Default cache TTL in seconds")
    pool_size: int = Field(default=5, description="Connection pool size")
    
    # Authentication settings
    enable_auth: bool = Field(default=False, description="Enable authentication")
    jwt_secret: Optional[str] = Field(default=None, description="JWT secret key")
    jwt_algorithm: str = Field(default="HS256", description="JWT algorithm")
    token_expiry: int = Field(default=3600, description="Token expiry in seconds")
    
    # Rate limiting
    enable_rate_limiting: bool = Field(default=True, description="Enable rate limiting")
    rate_limit_requests: int = Field(default=100, description="Max requests per window")
    rate_limit_window: int = Field(default=60, description="Rate limit window in seconds")
    
    # Monitoring settings
    enable_metrics: bool = Field(default=True, description="Enable Prometheus metrics")
    enable_tracing: bool = Field(default=False, description="Enable OpenTelemetry tracing")
    metrics_port: int = Field(default=9090, description="Prometheus metrics port")
    
    # Logging settings
    log_level: str = Field(default="INFO", description="Logging level")
    log_format: str = Field(
        default="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
        description="Log format"
    )
    
    # Code execution settings
    code_execution_enabled: bool = Field(default=True, description="Enable code execution")
    code_execution_timeout: int = Field(default=30, description="Code execution timeout")
    use_microvm: bool = Field(default=False, description="Use MicroVM instead of Docker")
    
    # Redis settings
    redis_enabled: bool = Field(default=False, description="Use Redis for caching")
    redis_host: str = Field(default="localhost", description="Redis host")
    redis_port: int = Field(default=6379, description="Redis port")
    redis_db: int = Field(default=0, description="Redis database")
    redis_password: Optional[str] = Field(default=None, description="Redis password")
    
    # Unreal Engine settings
    unreal_host: str = Field(default="127.0.0.1", description="Unreal Engine host")
    unreal_port: int = Field(default=55557, description="Unreal Engine port")
    
    # Feature flags
    enable_procedural_generation: bool = Field(default=True, description="Enable procedural generation tools")
    enable_blueprint_modification: bool = Field(default=True, description="Enable Blueprint modification")
    enable_advanced_analysis: bool = Field(default=True, description="Enable advanced Blueprint analysis")
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="UMCP_",
        case_sensitive=False
    )


class DevelopmentConfig(ServerConfig):
    """Development environment configuration."""
    log_level: str = "DEBUG"
    enable_auth: bool = False
    enable_metrics: bool = True
    redis_enabled: bool = False


class ProductionConfig(ServerConfig):
    """Production environment configuration."""
    log_level: str = "INFO"
    enable_auth: bool = True
    enable_metrics: bool = True
    enable_tracing: bool = True
    redis_enabled: bool = True
    use_websocket: bool = True


class TestingConfig(ServerConfig):
    """Testing environment configuration."""
    log_level: str = "DEBUG"
    enable_auth: bool = False
    enable_metrics: bool = False
    redis_enabled: bool = False
    code_execution_enabled: bool = False


def get_config(env: Optional[str] = None) -> ServerConfig:
    """
    Get configuration based on environment.
    
    Args:
        env: Environment name (development, production, testing)
             If None, reads from UMCP_ENV environment variable
    
    Returns:
        Configuration instance
    """
    if env is None:
        env = os.getenv("UMCP_ENV", "development").lower()
    
    config_map = {
        "development": DevelopmentConfig,
        "dev": DevelopmentConfig,
        "production": ProductionConfig,
        "prod": ProductionConfig,
        "testing": TestingConfig,
        "test": TestingConfig,
    }
    
    config_class = config_map.get(env, DevelopmentConfig)
    return config_class()


# Global config instance
_config: Optional[ServerConfig] = None


def load_config(env: Optional[str] = None) -> ServerConfig:
    """Load and cache configuration."""
    global _config
    if _config is None:
        _config = get_config(env)
    return _config


def get_current_config() -> ServerConfig:
    """Get current configuration (loads if not loaded)."""
    return load_config()
