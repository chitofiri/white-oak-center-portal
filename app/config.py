from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    app_name: str = "White Oak Center Portal"
    environment: str = "development"
    database_url: str = "sqlite:///./whiteoak_dev.db"
    jwt_secret: str
    jwt_algorithm: str = "HS256"
    access_token_minutes: int = 20
    max_pdf_mb: int = 15
    private_upload_dir: str = "./private_uploads"
    bootstrap_admin_email: str | None = None
    bootstrap_admin_password: str | None = None

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

settings = Settings()
