import argparse
import os
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class WhisperSettings(BaseSettings):
    # --- Server Settings ---
    host: str = Field(
        default="127.0.0.1",
        description="Hostname or IP for the FastAPI server to bind to",
    )
    port: int = Field(
        default=8000,
        description="Port for the FastAPI server",
    )

    # --- Model Settings ---
    whisper_model: str = Field(
        default="small",
        description="Whisper model size (tiny, base, small, medium, large-v3, etc.)",
    )
    device: str = Field(
        default="cuda",
        description="Compute device to use ('cuda', 'cpu', or 'auto')",
    )
    models_dir: str = Field(
        default="./models",
        description="Directory to store downloaded Hugging Face and CTranslate2 models",
    )

    # --- System ---
    log_level: str = "INFO"

    # Pydantic Config: Tells it to read from .env files automatically
    model_config = SettingsConfigDict(env_prefix="WHISPER_")


def get_settings() -> WhisperSettings:
    """
    Parses CLI arguments first, then initializes Settings.
    Precedence: CLI Args > Environment Vars > .env file > Defaults
    """
    parser = argparse.ArgumentParser(description="Whisper API Server Configuration")

    # Add arguments for every field you want controllable via CLI
    parser.add_argument("--host", help="Hostname or IP for the server (e.g., 0.0.0.0)")
    parser.add_argument("--port", type=int, help="Port for the FastAPI server")

    parser.add_argument("--whisper-model", help="Whisper model size to load")
    parser.add_argument("--device", help="Compute device ('cuda' or 'cpu')")
    parser.add_argument("--models-dir", help="Directory cache for downloaded models")

    parser.add_argument(
        "--log-level", help="Logging Level (DEBUG, INFO, WARNING, ERROR)"
    )

    args, unknown = parser.parse_known_args()

    # Create a dictionary of only the arguments that were actually provided via CLI
    # We replace hyphens with underscores to match the Pydantic field names
    cli_args = {k.replace("-", "_"): v for k, v in vars(args).items() if v is not None}

    # Initialize Settings
    return WhisperSettings(**cli_args)


# Create a global instance
settings = get_settings()
