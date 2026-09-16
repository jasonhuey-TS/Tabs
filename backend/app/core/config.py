from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache
from typing import Literal


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # App
    APP_NAME: str = "SaaS Manager"
    APP_ENV: Literal["development", "staging", "production"] = "development"
    DEBUG: bool = False
    SECRET_KEY: str = "change-me-in-production"
    API_V1_PREFIX: str = "/api/v1"

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://saas_manager:saas_manager@localhost:5432/saas_manager"
    DB_POOL_SIZE: int = 10
    DB_MAX_OVERFLOW: int = 20

    # Redis / Celery
    REDIS_URL: str = "redis://localhost:6379/0"
    CELERY_BROKER_URL: str = "redis://localhost:6379/0"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/1"

    # Auth (JWT)
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30

    # SSO integrations
    OKTA_DOMAIN: str = ""
    OKTA_API_TOKEN: str = ""
    OKTA_SYNC_INTERVAL_HOURS: int = 6

    AZURE_TENANT_ID: str = ""
    AZURE_CLIENT_ID: str = ""
    AZURE_CLIENT_SECRET: str = ""
    AZURE_SYNC_INTERVAL_HOURS: int = 6

    # File storage (S3-compatible)
    S3_BUCKET: str = "saas-manager-contracts"
    S3_ENDPOINT_URL: str = ""  # leave empty for AWS, set for MinIO etc.
    AWS_ACCESS_KEY_ID: str = ""
    AWS_SECRET_ACCESS_KEY: str = ""
    AWS_REGION: str = "us-east-1"

    # Notifications
    SLACK_WEBHOOK_URL: str = ""
    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USERNAME: str = ""
    SMTP_PASSWORD: str = ""
    EMAIL_FROM: str = "saas-manager@yourcompany.com"

    # Renewal alerts — days before expiry to fire
    RENEWAL_ALERT_DAYS: list[int] = [90, 60, 30, 14, 7]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
