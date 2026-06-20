from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional


class Settings(BaseSettings):
    APP_NAME: str = "口腔回访任务服务"
    DEBUG: bool = True

    DATABASE_URL: str = "sqlite:///./dental_callback.db"

    SECRET_KEY: str = "dental-clinic-secret-key-change-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7

    TIMEZONE: str = "Asia/Shanghai"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
