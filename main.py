import os
import gc
import tempfile
import uvicorn
from contextlib import asynccontextmanager

from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.responses import JSONResponse
from faster_whisper import WhisperModel

# ==========================================
# 1. IMPORT YOUR CONFIGURATION
# ==========================================
# Assuming you saved the previous snippet as 'config.py'
from config import settings

# ==========================================
# 2. DIRECTORY & CACHE SETUP
# ==========================================
os.makedirs(settings.models_dir, exist_ok=True)
os.environ["HF_HOME"] = os.path.join(settings.models_dir, "huggingface")

whisper_model = None

# Automatically drop to int8 quantization if running on CPU to save RAM
COMPUTE_TYPE = "float16" if settings.device == "cuda" else "int8"


@asynccontextmanager
async def lifespan(app: FastAPI):
    global whisper_model
    print(f"Data directory configured at: {settings.models_dir}")
    print(
        f"Loading faster-whisper '{settings.whisper_model}' model on {settings.device}..."
    )

    whisper_model = WhisperModel(
        settings.whisper_model,
        device=settings.device,
        compute_type=COMPUTE_TYPE,
        download_root=os.path.join(settings.models_dir, "faster-whisper"),
    )
    yield
    del whisper_model
    gc.collect()


app = FastAPI(title="Faster-Whisper OpenAI-Compatible API", lifespan=lifespan)


@app.post("/v1/audio/transcriptions")
async def create_transcription(
    file: UploadFile = File(...),
    model: str = Form("whisper-1"),
    language: str = Form(None),
    response_format: str = Form("json"),
    temperature: float = Form(0.0),
    vad_filter: bool = Form(True),
):
    global whisper_model

    if not file.filename:
        raise HTTPException(status_code=400, detail="No file uploaded")

    with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as temp_audio:
        temp_audio.write(await file.read())
        temp_audio_path = temp_audio.name

    try:
        vad_kwargs = {}
        if vad_filter:
            vad_kwargs = {
                "vad_filter": True,
                "vad_parameters": dict(
                    min_silence_duration_ms=500, speech_pad_ms=400, threshold=0.5
                ),
            }

        segments_generator, info = whisper_model.transcribe(
            temp_audio_path,
            language=language,
            temperature=temperature,
            beam_size=5,
            **vad_kwargs,
        )

        segments = list(segments_generator)
        full_text = " ".join([seg.text.strip() for seg in segments])

        if response_format == "verbose_json":
            openai_segments = []
            for seg in segments:
                openai_segments.append(
                    {
                        "id": seg.id,
                        "seek": seg.seek,
                        "start": seg.start,
                        "end": seg.end,
                        "text": seg.text.strip(),
                        "tokens": seg.tokens,
                        "temperature": seg.temperature,
                        "avg_logprob": seg.avg_logprob,
                        "compression_ratio": seg.compression_ratio,
                        "no_speech_prob": seg.no_speech_prob,
                    }
                )

            return JSONResponse(
                {
                    "task": "transcribe",
                    "language": info.language,
                    "duration": info.duration,
                    "text": full_text.strip(),
                    "segments": openai_segments,
                }
            )

        else:
            return JSONResponse({"text": full_text.strip()})

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if os.path.exists(temp_audio_path):
            os.remove(temp_audio_path)


# ==========================================
# 3. PROGRAMMATIC EXECUTION
# ==========================================
# Replace the old if __name__ == "__main__": block with this:
def main():
    print(f"Starting Whisper API on {settings.host}:{settings.port}...")
    uvicorn.run(
        "main:app",
        host=settings.host,
        port=settings.port,
        log_level=settings.log_level.lower(),
    )


if __name__ == "__main__":
    main()
