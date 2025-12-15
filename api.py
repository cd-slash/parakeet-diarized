import os
import logging
import warnings
from typing import List, Optional, Dict, Any, Union
from pathlib import Path

from fastapi import FastAPI, File, UploadFile, Form, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse
import torch

from models import WhisperSegment, TranscriptionResponse, ModelInfo, ModelList
from audio import convert_audio_to_wav, split_audio_into_chunks
from transcription import load_model, format_srt, format_vtt, transcribe_audio_chunk
from diarization import Diarizer
from config import get_config

# Initialize logging
logger = logging.getLogger(__name__)

# Global variable for model
asr_model = None

# Get configuration
config = get_config()

def create_app() -> FastAPI:
    """
    Create and configure the FastAPI application

    Returns:
        Configured FastAPI app
    """
    app = FastAPI(title="Parakeet Whisper-Compatible API")

    # Add CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.on_event("startup")
    async def startup_event():
        """Initialize resources during startup"""
        global asr_model

        try:
            # Check CUDA availability
            if torch.cuda.is_available():
                logger.info(f"CUDA available: {torch.cuda.get_device_name(0)}")
            else:
                logger.warning("CUDA not available, using CPU (this will be slow)")

            # Load the ASR model
            model_id = config.model_id
            asr_model = load_model(model_id)
            logger.info(f"Model {model_id} loaded successfully")

            # Initialize diarization if token is available
            hf_token = config.get_hf_token()
            if hf_token:
                logger.info("HuggingFace access token found, speaker diarization will be available")
            else:
                logger.info("No HuggingFace access token, speaker diarization will be disabled")

        except Exception as e:
            logger.error(f"Error during startup: {str(e)}")
            # We don't want to fail startup completely, as the health endpoint should still work

    @app.post("/v1/audio/transcriptions")
    async def transcribe_audio(
        file: UploadFile = File(...),
        model: str = Form("whisper-1"),
        language: Optional[str] = Form(None),
        prompt: Optional[str] = Form(None),
        response_format: str = Form("json"),
        temperature: float = Form(0.0),
        timestamps: bool = Form(False),
        timestamp_granularities: Optional[List[str]] = Form(None),
        vad_filter: bool = Form(False),
        word_timestamps: bool = Form(False),
        diarize: bool = Form(True)
    ):
        """
        Transcribe audio file using the Parakeet-TDT model

        This endpoint is compatible with the OpenAI Whisper API
        """

        global asr_model

        if not asr_model:
            raise HTTPException(status_code=503, detail="Model not loaded yet. Please try again in a few moments.")

        # Process parameters
        logger.info(f"Transcription requested: {file.filename}, format: {response_format}")

        # Track files and directories to clean up
        temp_file = None
        wav_file = None
        audio_chunks = []
        chunk_dirs_to_cleanup = set()

        try:
            # Save uploaded file to temp location
            temp_dir = Path(config.temp_dir)
            temp_dir.mkdir(parents=True, exist_ok=True)

            temp_file = temp_dir / f"upload_{os.urandom(8).hex()}{Path(file.filename).suffix}"
            with open(temp_file, "wb") as f:
                content = await file.read()
                f.write(content)

            # Convert to WAV format
            wav_file = convert_audio_to_wav(str(temp_file))

            # Split audio into chunks if it's too long
            chunk_duration = config.chunk_duration
            audio_chunks = split_audio_into_chunks(wav_file, chunk_duration=chunk_duration)

            # Track chunk directories for cleanup
            for chunk in audio_chunks:
                chunk_dir = os.path.dirname(chunk)
                if chunk_dir and chunk_dir != os.path.dirname(wav_file):
                    chunk_dirs_to_cleanup.add(chunk_dir)

            # Initialize diarization if requested
            diarizer = None
            if diarize:
                hf_token = config.get_hf_token()
                if hf_token:
                    diarizer = Diarizer(access_token=hf_token)
                else:
                    logger.warning("Diarization requested but no HuggingFace token available")

            # Process speaker diarization if requested
            # Run diarization FIRST on GPU, then unload before transcription
            diarization_result = None
            if diarizer:
                logger.info("Performing speaker diarization on GPU")
                diarization_result = diarizer.diarize(wav_file)
                logger.info(f"Diarization found {diarization_result.num_speakers} speakers")

                # Unload diarization pipeline from GPU to free memory for transcription
                diarizer.cleanup()
                logger.info("Diarization pipeline unloaded from GPU")

            # Process each chunk
            all_text = []
            all_segments = []

            for i, chunk_path in enumerate(audio_chunks):
                logger.info(f"Processing chunk {i+1}/{len(audio_chunks)}")

                # Clear GPU cache before processing each chunk to avoid OOM
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()

                # Transcribe the chunk
                chunk_text, chunk_segments = transcribe_audio_chunk(
                    asr_model,
                    chunk_path,
                    language=language,
                    word_timestamps=word_timestamps
                )

                # Add offset to timestamps if not the first chunk
                if i > 0:
                    offset = i * chunk_duration
                    for segment in chunk_segments:
                        segment.start += offset
                        segment.end += offset

                all_text.append(chunk_text)
                all_segments.extend(chunk_segments)

            # Combine results
            full_text = " ".join(all_text)

            # Apply diarization if available
            if diarizer and diarization_result and diarization_result.segments:
                logger.info(f"Found {diarization_result.num_speakers} speakers")
                all_segments = diarizer.merge_with_transcription(diarization_result, all_segments)
                logger.info("Speaker diarization applied to segments (speaker info in segment metadata only)")
            else:
                logger.warning("Diarization not applied or returned no speakers")


            # Create response
            response = TranscriptionResponse(
                text=full_text,
                segments=all_segments if timestamps or response_format == "verbose_json" else None,
                language=language,
                duration=sum(len(segment.text.split()) for segment in all_segments) / 150 if all_segments else 0,
                model="parakeet-tdt-0.6b-v2"
            )

            # Return in requested format
            if response_format == "json":
                return response.dict()
            elif response_format == "text":
                return PlainTextResponse(full_text)
            elif response_format == "srt":
                return PlainTextResponse(format_srt(all_segments))
            elif response_format == "vtt":
                return PlainTextResponse(format_vtt(all_segments))
            elif response_format == "verbose_json":
                return response.dict()
            else:
                raise HTTPException(status_code=400, detail=f"Unsupported response format: {response_format}")

        except Exception as e:
            logger.error(f"Error during transcription: {str(e)}")
            raise HTTPException(status_code=500, detail=str(e))

        finally:
            # Always clean up temporary files, even if there was an error
            import shutil
            try:
                if temp_file and os.path.exists(temp_file):
                    os.unlink(temp_file)
                    logger.debug(f"Cleaned up temp file: {temp_file}")
            except Exception as e:
                logger.warning(f"Failed to clean up temp file: {e}")

            try:
                if wav_file and wav_file != str(temp_file) and os.path.exists(wav_file):
                    os.unlink(wav_file)
                    logger.debug(f"Cleaned up WAV file: {wav_file}")
            except Exception as e:
                logger.warning(f"Failed to clean up WAV file: {e}")

            # Clean up chunk files
            for chunk in audio_chunks:
                try:
                    if chunk != wav_file and os.path.exists(chunk):
                        os.unlink(chunk)
                except Exception as e:
                    logger.warning(f"Failed to clean up chunk {chunk}: {e}")

            # Clean up chunk directories
            for chunk_dir in chunk_dirs_to_cleanup:
                try:
                    if os.path.exists(chunk_dir):
                        shutil.rmtree(chunk_dir)
                        logger.debug(f"Cleaned up chunk directory: {chunk_dir}")
                except Exception as e:
                    logger.warning(f"Failed to clean up chunk directory {chunk_dir}: {e}")

    @app.get("/health")
    async def health_check():
        """
        Check the health of the API and the loaded model
        """
        global asr_model

        return {
            "status": "ok",
            "version": "1.0.0",
            "model_loaded": asr_model is not None,
            "model_id": config.model_id,
            "cuda_available": torch.cuda.is_available(),
            "gpu_info": torch.cuda.get_device_name(0) if torch.cuda.is_available() else None,
            "config": config.as_dict()
        }

    @app.get("/v1/models")
    async def list_models():
        """
        List available models (compatibility with OpenAI API)
        """
        models = [
            ModelInfo(
                id="whisper-1",
                created=1677649963,
                owned_by="parakeet",
                root="whisper-1",
                permission=[{"id": "modelperm-1", "object": "model_permission", "created": 1677649963,
                           "allow_create_engine": False, "allow_sampling": True, "allow_logprobs": True,
                           "allow_search_indices": False, "allow_view": True, "allow_fine_tuning": False,
                           "organization": "*", "group": None, "is_blocking": False}]
            )
        ]

        return ModelList(data=models)

    return app
