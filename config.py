import argparse
import os
from typing import Optional
from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class WhisperSettings(BaseSettings):
    # --- MQTT Connection ---

    mqtt_host: str = Field(
        default="localhost",
        description="Mosquitto broker IP/Hostname",
    )
    mqtt_port: int = Field(
        default=1883,
        description="Mosquitto broker port",
    )
    mqtt_user: Optional[str] = Field(
        default=None, description="Username used to authenticate with mqtt broker"
    )
    mqtt_password: Optional[str] = Field(
        default=None, description="Password used to authenticate with mqtt broker"
    )
    # --- Object Storage (S3 Compatible) ---
    s3_endpoint: str = Field(
        default="http://localhost:3900", description="URL to your S3-compatible storage"
    )
    s3_access_key: str = Field(default="your-access-key", description="S3 Access Key")
    s3_secret_key: SecretStr = Field(
        default="your-secret-key", description="S3 Secret Key"
    )
    s3_bucket: str = Field(
        default="voice-commands", description="The bucket where audio files are stored"
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
    parser = argparse.ArgumentParser(description="Whisper Transcription Worker")

    parser.add_argument("--mqtt-host", help="Mosquitto broker IP/Hostname")
    parser.add_argument("--mqtt-port", type=int, help="Mosquitto broker port")
    parser.add_argument("--mqtt-user")
    parser.add_argument("--mqtt-password")

    parser.add_argument("--s3-endpoint", help="URL to S3 storage")
    parser.add_argument("--s3-access-key", help="S3 Access Key")
    parser.add_argument("--s3-secret-key", help="S3 Secret Key")
    parser.add_argument("--s3-bucket", help="S3 Bucket Name")

    parser.add_argument("--whisper-model", help="Whisper model size to load")
    parser.add_argument("--device", help="Compute device ('cuda' or 'cpu')")
    parser.add_argument("--models-dir", help="Directory cache for downloaded models")
    parser.add_argument(
        "--log-level", help="Logging Level (DEBUG, INFO, WARNING, ERROR)"
    )

    args, unknown = parser.parse_known_args()

    cli_args = {k.replace("-", "_"): v for k, v in vars(args).items() if v is not None}
    return WhisperSettings(**cli_args)


settings = get_settings()
