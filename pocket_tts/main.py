import io
import logging
import os
import sys
import tempfile
import threading
import traceback
from pathlib import Path
from queue import Queue

import typer
import uvicorn
from fastapi import (
    Depends,
    FastAPI,
    File,
    Form,
    HTTPException,
    Request,
    UploadFile,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from typing_extensions import Annotated

from pocket_tts.data.audio import stream_audio_chunks
from pocket_tts.default_parameters import (
    DEFAULT_EOS_THRESHOLD,
    DEFAULT_FRAMES_AFTER_EOS,
    DEFAULT_LSD_DECODE_STEPS,
    DEFAULT_NOISE_CLAMP,
    DEFAULT_TEMPERATURE,
    MAX_TOKEN_PER_CHUNK,
    get_default_text_for_language,
    get_default_voice_for_language,
)
from pocket_tts.models.tts_model import TTSModel, export_model_state
from pocket_tts.utils.logging_utils import enable_logging
from pocket_tts.utils.utils import _ORIGINS_OF_PREDEFINED_VOICES
from stripe_subscription.config import settings
from stripe_subscription.database import Base, engine, get_db
from stripe_subscription.dependencies import (
    get_active_subscription,
    get_current_user,
)
from stripe_subscription.logging import logger
from stripe_subscription.middlewares.check_if_subscribed import (
    SubscriptionMiddleware,
)
from stripe_subscription.middlewares.security import SecurityHeadersMiddleware
from stripe_subscription.models import Plan, Subscription, User
from stripe_subscription.routes import router as stripe_router

cli_app = typer.Typer(
    help="Kyutai Pocket TTS - Text-to-Speech generation tool",
    pretty_exceptions_show_locals=False,
)

# Global model instance
tts_model: TTSModel | None = None

web_app = FastAPI(
    title="Kyutai Pocket TTS API",
    description="Text-to-Speech generation API",
    version="1.0.0",
)

BASE_DIR = Path(__file__).parent
web_app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
templates = Jinja2Templates(directory=str(BASE_DIR / "static" / "templates"))

web_app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
        "https://pod1-10007.internal.kyutai.org",
        "https://kyutai.org",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Check Subscription Middleware
web_app.add_middleware(SubscriptionMiddleware)

# Security Middleware
web_app.add_middleware(SecurityHeadersMiddleware)

# ----- Mount Stripe router -----
web_app.include_router(stripe_router)


# ----- Seed default plans on startup -----
@web_app.on_event("startup")
def startup():
    Base.metadata.create_all(bind=engine)
    db = next(get_db())
    try:
        if db.query(Plan).count() == 0:
            plans = [
                Plan(
                    name="Basic",
                    tier="basic",
                    monthly_price=500,
                    yearly_price=4800,
                    quota_limit=50000,
                    stripe_price_monthly=settings.STRIPE_PRICE_BASIC_MONTHLY_ID,
                    stripe_price_yearly=settings.STRIPE_PRICE_BASIC_YEARLY_ID,
                    is_active=True,
                ),
                Plan(
                    name="Pro",
                    tier="pro",
                    monthly_price=1500,
                    yearly_price=14400,
                    quota_limit=250000,
                    stripe_price_monthly=settings.STRIPE_PRICE_PRO_MONTHLY_ID,
                    stripe_price_yearly=settings.STRIPE_PRICE_PRO_YEARLY_ID,
                    is_active=True,
                ),
                Plan(
                    name="Enterprise",
                    tier="enterprise",
                    monthly_price=5000,
                    yearly_price=48000,
                    quota_limit=1500000,
                    stripe_price_monthly=settings.STRIPE_PRICE_ENTERPRISE_MONTHLY_ID,
                    stripe_price_yearly=settings.STRIPE_PRICE_ENTERPRISE_YEARLY_ID,
                    is_active=True,
                ),
            ]
            db.add_all(plans)
            db.commit()
            logger.info("Default plans seeded with Stripe Price IDs.")
    except Exception as e:
        logger.error(f"Error seeding plans: {str(e)}", exc_info=True)
    finally:
        db.close()


@web_app.exception_handler(ConnectionResetError)
async def connection_reset_handler(request: Request, exc: ConnectionResetError):
    return JSONResponse(
        status_code=499, content={"detail": "Client disconnected", "error": f"{exc}"}
    )


# ----- Endpoints -----
@web_app.get("/")
async def root(request: Request):
    try:
        if tts_model is None:
            return templates.TemplateResponse(
                request,
                "index.jinja2",
                {
                    "default_text": "Model not loaded.",
                    "tts_loaded": False,
                },
            )
        default_text = get_default_text_for_language(str(tts_model.origin))
        return templates.TemplateResponse(
            request,
            "index.jinja2",
            {"default_text": default_text, "tts_loaded": True},
        )
    except Exception:
        # Print full stack trace to server logs
        logging.error("Template rendering failed:\n" + traceback.format_exc())
        # Return a simple error page with the exception message
        return HTMLResponse(
            f"<h1>Template error</h1><pre>{traceback.format_exc()}</pre>"
        )


@web_app.get("/health")
async def health():
    return {"status": "healthy"}


@web_app.get("/success")
async def success_page():
    return HTMLResponse("""
        <html><body>
            <h1>Payment successful!</h1>
            <p>Redirecting to the app...</p>
            <script>setTimeout(() => window.location.href = '/', 2000);</script>
        </body></html>
    """)


# ----- Protected TTS endpoint (fixed parameter order) -----
@web_app.post("/tts")
def text_to_speech(
    request: Request,
    text: str = Form(...),
    voice_url: str | None = Form(default=None),
    voice_wav: UploadFile | None = File(None),
    user: User = Depends(get_current_user),
    sub: Subscription = Depends(get_active_subscription),
    db: Session = Depends(get_db),
):
    # ------------------------------------------------------------------
    # 🔒 LOG: Subscription check passed before any generation starts
    # ------------------------------------------------------------------
    logger.info(
        f"✅ SUBSCRIPTION ACTIVE for user {user.id} ({user.email}) – "
        f"Plan: {sub.plan.name}, Remaining: {sub.quota_limit - sub.characters_used} chars."
    )

    if tts_model is None:
        raise HTTPException(503, "TTS model not loaded")

    if not text.strip():
        raise HTTPException(400, "Text cannot be empty")

    # Check quota
    if sub.characters_used + len(text) > sub.quota_limit:  # type: ignore
        raise HTTPException(429, "Monthly character limit exceeded")

    if voice_url is None and voice_wav is None:
        voice_url = get_default_voice_for_language(str(tts_model.origin))
    if voice_url is not None and voice_wav is not None:
        raise HTTPException(400, "Cannot provide both voice_url and voice_wav")

    # Get voice state
    if voice_url is not None:
        if not (
            voice_url.startswith("http://")
            or voice_url.startswith("https://")
            or voice_url.startswith("hf://")
            or voice_url in _ORIGINS_OF_PREDEFINED_VOICES
        ):
            raise HTTPException(
                400, "voice_url must start with http://, https://, or hf://"
            )
        model_state = tts_model._cached_get_state_for_audio_prompt(voice_url)
    elif voice_wav is not None:
        suffix = Path(voice_wav.filename).suffix if voice_wav.filename else ".wav"
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp_file:
            content = voice_wav.file.read()
            temp_file.write(content)
            temp_file.flush()
            temp_file_path = temp_file.name
        try:
            model_state = tts_model.get_state_for_audio_prompt(
                Path(temp_file_path), truncate=True
            )
        finally:
            os.unlink(temp_file_path)
    else:
        raise HTTPException(500, "This should never happen.")

    # Generator that updates usage after streaming
    def generate_with_usage():
        try:
            for chunk in generate_data_with_state(text, model_state):
                yield chunk
        finally:
            sub.characters_used += len(text)  # type: ignore
            db.commit()
            logger.info(
                f"User {user.id} used {len(text)} chars, total {sub.characters_used}/{sub.quota_limit}"
            )

    # Return with security headers
    return StreamingResponse(
        generate_with_usage(),
        media_type="audio/wav",
        headers={
            "Content-Disposition": "attachment; filename=generated_speech.wav",
            "Transfer-Encoding": "chunked",
            "X-Content-Type-Options": "nosniff",
            "X-Frame-Options": "DENY",
        },
    )


def write_to_queue(queue, text_to_generate, model_state):
    if tts_model is None:
        raise RuntimeError("TTS model not loaded")

    class FileLikeToQueue(io.IOBase):
        def __init__(self, queue):
            self.queue = queue

        def write(self, data):
            self.queue.put(data)

        def flush(self):
            pass

        def close(self):
            self.queue.put(None)

    audio_chunks = tts_model.generate_audio_stream(
        model_state=model_state, text_to_generate=text_to_generate
    )
    stream_audio_chunks(
        FileLikeToQueue(queue), audio_chunks, tts_model.config.mimi.sample_rate
    )


def generate_data_with_state(text_to_generate: str, model_state: dict):
    queue = Queue()
    thread = threading.Thread(
        target=write_to_queue, args=(queue, text_to_generate, model_state)
    )
    thread.start()
    while True:
        data = queue.get()
        if data is None:
            break
        yield data
    thread.join()


# ------------------------------------------------------
# CLI commands (unchanged)
# ------------------------------------------------------
@cli_app.command()
def generate(
    text: Annotated[str | None, typer.Option(help="Text to generate")] = None,
    voice: Annotated[
        str | None, typer.Option(help="Path to audio conditioning file")
    ] = None,
    quiet: Annotated[
        bool, typer.Option("-q", "--quiet", help="Disable logging output")
    ] = False,
    language: Annotated[
        str | None, typer.Option(help="Language for the TTS model")
    ] = None,
    config: Annotated[
        str | None, typer.Option(help="Path to locally-saved model config .yaml file")
    ] = None,
    lsd_decode_steps: Annotated[
        int, typer.Option(help="Number of generation steps")
    ] = DEFAULT_LSD_DECODE_STEPS,
    temperature: Annotated[
        float, typer.Option(help="Temperature for generation")
    ] = DEFAULT_TEMPERATURE,
    noise_clamp: Annotated[
        float | None, typer.Option(help="Noise clamp value")
    ] = DEFAULT_NOISE_CLAMP,
    eos_threshold: Annotated[
        float, typer.Option(help="EOS threshold")
    ] = DEFAULT_EOS_THRESHOLD,
    frames_after_eos: Annotated[
        int | None, typer.Option(help="Number of frames to generate after EOS")
    ] = DEFAULT_FRAMES_AFTER_EOS,
    output_path: Annotated[
        str, typer.Option(help="Output path for generated audio")
    ] = "./tts_output.wav",
    device: Annotated[str, typer.Option(help="Device to use. (cpu | cuda)")] = "cuda",
    max_tokens: Annotated[
        int, typer.Option(help="Maximum number of tokens per chunk.")
    ] = MAX_TOKEN_PER_CHUNK,
    quantize: Annotated[bool, typer.Option(help="Apply int8 quantization")] = False,
):
    """Generate speech using Kyutai Pocket TTS."""
    log_level = logging.ERROR if quiet else logging.INFO
    with enable_logging("pocket_tts", log_level):
        if text is None:
            text = get_default_text_for_language(language)
        if text == "-":
            text = sys.stdin.read()
        if not text.strip():  # type: ignore
            logger.error("No input received from stdin.")
            raise typer.Exit(code=1)
        tts_model = TTSModel.load_model(
            language=language,
            config=config,
            temp=temperature,
            lsd_decode_steps=lsd_decode_steps,
            noise_clamp=noise_clamp,
            eos_threshold=eos_threshold,
            quantize=quantize,
        )
        tts_model.to(device)
        if voice is None:
            voice = get_default_voice_for_language(language)
        model_state_for_voice = tts_model.get_state_for_audio_prompt(voice)
        audio_chunks = tts_model.generate_audio_stream(
            model_state=model_state_for_voice,
            text_to_generate=text,  # type: ignore
            frames_after_eos=frames_after_eos,
            max_tokens=max_tokens,
        )
        stream_audio_chunks(
            output_path, audio_chunks, tts_model.config.mimi.sample_rate
        )
        if output_path != "-":
            logger.info("Results written in %s", output_path)
        logger.info("-" * 20)
        logger.info(
            "If you want to try multiple voices and prompts quickly, try the `serve` command."
        )
        logger.info(
            "If you like Kyutai projects, comment, like, subscribe at https://x.com/kyutai_labs"
        )


@cli_app.command()
def export_voice(
    audio_path: Annotated[str, typer.Argument(help="Audio file or directory")],
    export_path: Annotated[str, typer.Argument(help="Output file or directory")],
    quiet: Annotated[
        bool, typer.Option("-q", "--quiet", help="Disable logging output")
    ] = False,
    language: Annotated[
        str | None, typer.Option(help="Language for the TTS model")
    ] = None,
    config: Annotated[
        str | None, typer.Option(help="Path to locally-saved model config .yaml file")
    ] = None,
):
    """Convert and save audio to .safetensors file."""
    log_level = logging.ERROR if quiet else logging.INFO
    with enable_logging("pocket_tts", log_level):
        tts_model = TTSModel.load_model(language=language, config=config)
        model_state = tts_model.get_state_for_audio_prompt(audio_path, truncate=True)
        export_model_state(model_state, export_path)


@cli_app.command()
def serve(
    host: Annotated[str, typer.Option(help="Host to bind to")] = "localhost",
    port: Annotated[int, typer.Option(help="Port to bind to")] = 8000,
    reload: Annotated[bool, typer.Option(help="Enable auto-reload")] = False,
    language: Annotated[
        str | None, typer.Option(help="Language for the TTS model")
    ] = None,
    config: Annotated[
        str | None, typer.Option(help="Path to locally-saved model config .yaml file")
    ] = None,
    quantize: Annotated[bool, typer.Option(help="Apply int8 quantization")] = False,
    device: Annotated[str, typer.Option(help="Device to use (cpu | cuda)")] = "cuda",
):
    """Start the FastAPI server."""
    global tts_model
    with enable_logging("pocket_tts", logging.INFO, filter_by_name=False):
        tts_model = TTSModel.load_model(
            language=language, config=config, quantize=quantize
        )
        tts_model.to(device=device)
    uvicorn.run("pocket_tts.main:web_app", host=host, port=port, reload=reload)


if __name__ == "__main__":
    cli_app()
