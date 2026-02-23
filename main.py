import os
import gc
import json
import tempfile
import asyncio
import logging
import boto3
import aiomqtt
from faster_whisper import WhisperModel

from config import settings

# --- Logging Setup ---
logging.basicConfig(
    level=settings.log_level,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("TranscriptionWorker")

# --- Directory & Cache Setup ---
os.makedirs(settings.models_dir, exist_ok=True)
os.environ["HF_HOME"] = os.path.join(settings.models_dir, "huggingface")

# Automatically drop to int8 quantization if running on CPU to save RAM
COMPUTE_TYPE = "float16" if settings.device == "cuda" else "int8"


def download_audio_file(audio_url: str) -> str:
    """Downloads audio securely from S3 object storage into a temp file."""
    # Extract the object key (filename) from the URL
    # E.g., http://endpoint/bucket/my-audio.wav -> my-audio.wav
    object_key = audio_url.split("/")[-1]

    logger.debug(f"Downloading {object_key} from S3 bucket '{settings.s3_bucket}'...")

    s3_client = boto3.client(
        "s3",
        endpoint_url=settings.s3_endpoint,
        aws_access_key_id=settings.s3_access_key,
        aws_secret_access_key=settings.s3_secret_key.get_secret_value(),
    )

    # We use delete=False so boto3 can write to it, and we delete it manually later
    with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as temp_audio:
        s3_client.download_file(settings.s3_bucket, object_key, temp_audio.name)
        return temp_audio.name


def run_transcription(model: WhisperModel, file_path: str) -> str:
    """Runs the blocking faster-whisper model."""
    logger.debug("Starting transcription...")

    vad_kwargs = {
        "vad_filter": True,
        "vad_parameters": dict(
            min_silence_duration_ms=500, speech_pad_ms=400, threshold=0.5
        ),
    }

    segments_generator, info = model.transcribe(
        file_path,
        beam_size=5,
        **vad_kwargs,
    )

    segments = list(segments_generator)
    full_text = " ".join([seg.text.strip() for seg in segments])

    logger.info(
        f"Transcription complete (Language: {info.language}): '{full_text.strip()}'"
    )
    return full_text.strip()


async def main_async():
    logger.info(f"Data directory configured at: {settings.models_dir}")
    logger.info(
        f"Loading faster-whisper '{settings.whisper_model}' model on {settings.device}..."
    )

    # Initialize the model once
    whisper_model = WhisperModel(
        settings.whisper_model,
        device=settings.device,
        compute_type=COMPUTE_TYPE,
        download_root=os.path.join(settings.models_dir, "faster-whisper"),
    )
    logger.info("Model loaded successfully.")

    try:
        async with aiomqtt.Client(
            settings.mqtt_host, port=settings.mqtt_port
        ) as client:
            logger.info(
                f"Connected to MQTT Broker at {settings.mqtt_host}:{settings.mqtt_port}"
            )

            # Subscribe to the topic published by the Satellite
            await client.subscribe("voice/audio/recorded")
            logger.info("Listening for audio tasks on 'voice/audio/recorded'...")

            async for message in client.messages:
                payload = json.loads(message.payload.decode())
                audio_url = payload.get("audio_url")
                room = payload.get("room")

                if not audio_url or not room:
                    logger.warning(
                        "Received invalid payload missing 'audio_url' or 'room'."
                    )
                    continue

                logger.info(f"Task received for room: {room}")
                temp_audio_path = None

                try:
                    # 1. Download the audio from S3
                    temp_audio_path = await asyncio.to_thread(
                        download_audio_file, audio_url
                    )

                    # 2. Transcribe the audio
                    transcription = await asyncio.to_thread(
                        run_transcription, whisper_model, temp_audio_path
                    )

                    # 3. Publish the transcription result
                    if transcription:
                        result_payload = {"room": room, "text": transcription}
                        await client.publish(
                            "voice/asr/text", payload=json.dumps(result_payload)
                        )
                    else:
                        logger.info("Transcription resulted in empty text. Ignoring.")

                except Exception as e:
                    logger.error(f"Error processing transcription task: {e}")

                finally:
                    # 4. Cleanup the temporary file
                    if temp_audio_path and os.path.exists(temp_audio_path):
                        os.remove(temp_audio_path)

    except aiomqtt.MqttError as error:
        logger.error(f"MQTT Error: {error}")
    except KeyboardInterrupt:
        logger.info("Shutting down worker...")
    finally:
        del whisper_model
        gc.collect()


def main():
    """Synchronous wrapper for the setuptools entry point."""
    import asyncio

    try:
        asyncio.run(main_async())
    except KeyboardInterrupt:
        pass
