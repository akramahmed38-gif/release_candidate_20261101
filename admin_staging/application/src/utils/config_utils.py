# pylint: disable=invalid-name

"""
Utilities for loading and handling configuration files.
"""

import os
from typing import Optional
from pathlib import Path
from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict, YamlConfigSettingsSource
from utils.logging_utils import setup_logger

logger = setup_logger(
    log_file=__file__,
    log_to_console=False,
    file_mode="a",
)
BASE_DIR = Path(__file__).resolve().parents[2]
PORTAL_ROOT = BASE_DIR.parent
ENV_PATH = BASE_DIR / ".env"
CONFIG_YAML_PATH = BASE_DIR / "config" / "config.yaml"


def _load_dotenv_into_environ(env_path: Path) -> None:
    """
    Best-effort dotenv loader so other modules can use `os.getenv(...)` consistently.

    Pydantic reads `env_file`, but does not populate `os.environ`. Some parts of the
    app (OTP SMTP settings, admin password) rely on `os.getenv`, so we load `.env`
    into process env without overriding any existing env vars.
    """
    if not env_path.exists():
        return

    try:
        for raw_line in env_path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            if not key or key in os.environ:
                continue
            os.environ[key] = value.strip().strip('"').strip("'")
    except Exception:
        return


_load_dotenv_into_environ(ENV_PATH)


def _as_abs(path_value: str) -> str:
    path_obj = Path(path_value)
    if path_obj.is_absolute():
        return str(path_obj)
    return str((BASE_DIR / path_obj).resolve())


def _as_abs_sqlite_db(path_value: str) -> str:
    path_obj = Path(path_value)
    if path_obj.is_absolute():
        return str(path_obj)

    if path_obj.parts and path_obj.parts[0] in {".", ".."}:
        return str((BASE_DIR / path_obj).resolve())

    db_root_raw = (os.getenv("PORTAL_DATABASES_DIR", "databases") or "databases").strip()
    db_root_path = Path(db_root_raw)
    if not db_root_path.is_absolute():
        db_root_path = (PORTAL_ROOT / db_root_path).resolve()
    return str((db_root_path / path_obj).resolve())


class Settings(BaseSettings):
    """
    Application configuration container that loads required credentials and metadata
    from env, .env, YAML, or secrets files.
    """

    # .env
    FILE_ALLOWED_TYPES: list[str] = Field(default_factory=lambda: [
        "application/pdf",
        "application/msword",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/vnd.ms-excel",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ])


    # .yaml
    APP_NAME: str = Field(...)
    APP_VERSION: str = Field(...)

    PATH_LOGS: str = Field(...)
    PATH_DATA_ROOT: str = Field(...)
    PATH_ASSETS_ROOT: str = Field(...)
    PATH_MODELS_ROOT: str = Field(...)
    PATH_OUTPUT_ROOT: str = Field(...)

    SQLITE_DB_PATH: str = Field(...)

    FILE_MAX_SIZE: int = Field(...)
    FILE_DEFAULT_CHUNK_SIZE: int = Field(...)
    


    model_config = SettingsConfigDict(
        env_file=str(ENV_PATH),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls,
        init_settings,
        env_settings,
        dotenv_settings,
        file_secret_settings,
    ):
        return (
            init_settings,  # kwargs passed directly to Settings()
            env_settings,  # Environment variables
            dotenv_settings,  # .env file
            YamlConfigSettingsSource(
                settings_cls,
                yaml_file=CONFIG_YAML_PATH,
                yaml_file_encoding="utf-8",
            ),  # YAML file
            file_secret_settings,
        )


def get_settings() -> Settings:
    """
    Constructs and returns a validated Settings object that centralizes configuration
    for the application.
    Returns:
        Settings: A validated Settings instance containing application configuration.
    """

    logger.info("Loading application settings.")
    settings = Settings()  # type: ignore
    settings.PATH_LOGS = _as_abs(settings.PATH_LOGS)
    settings.PATH_DATA_ROOT = _as_abs(settings.PATH_DATA_ROOT)
    settings.PATH_ASSETS_ROOT = _as_abs(settings.PATH_ASSETS_ROOT)
    settings.PATH_MODELS_ROOT = _as_abs(settings.PATH_MODELS_ROOT)
    settings.PATH_OUTPUT_ROOT = _as_abs(settings.PATH_OUTPUT_ROOT)
    settings.SQLITE_DB_PATH = _as_abs_sqlite_db(settings.SQLITE_DB_PATH)
    return settings


def main():
    """Entry Point for the Program."""
    print(f"Welcome from `{os.path.basename(__file__).split('.')[0]}` Module.\n")
    # Usage

    settings = get_settings()

    print(settings.APP_NAME)  # From config.yaml
    print(settings.APP_VERSION)  # From config.yaml

if __name__ == "__main__":
    main()
