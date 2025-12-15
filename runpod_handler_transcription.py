"""
RunPod Serverless Handler - Transcription Only

This handler provides audio transcription without diarization.
Use in combination with the diarization handler for optimal Model Store usage.

Input format:
{
    "input": {
        "audio": "https://example.com/audio.mp3" or "base64_encoded_audio_data",
        "audio_format": "mp3" (required if using base64),
        "language": "en" (optional),
        "response_format": "json|text|srt|vtt|verbose_json" (default: "json"),
        "timestamps": true|false (default: false),
        "word_timestamps": true|false (default: false),
        "temperature": 0.0 (default),
        "diarization_segments": [...] (optional, from diarization endpoint)
    }
}

Output format:
{
    "text": "Full transcription",
    "segments": [
        {"id": 0, "start": 0.0, "end": 2.5, "text": "...", "speaker": "1"}
    ],
    "language": "en",
    "duration": 10.5,
    "model": "parakeet-tdt-0.6b-v2"
}
"""

import os
import logging
import base64
import tempfile
import shutil
from pathlib import Path
from typing import Dict, Any, Optional, List
import requests
import torch

import runpod

from audio import convert_audio_to_wav, split_audio_into_chunks
from transcription import load_model, format_srt, format_vtt, transcribe_audio_chunk
from config import get_config
from models import WhisperSegment

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Global variables
asr_model = None
config = None


def initialize():
    """Initialize the model and configuration on worker startup"""
    global asr_model, config

    try:
        # Get configuration
        config = get_config()

        # Log CUDA availability
        if torch.cuda.is_available():
            logger.info(f"CUDA available: {torch.cuda.get_device_name(0)}")
        else:
            logger.warning("CUDA not available, using CPU (will be slow)")

        # Load the ASR model
        model_id = config.model_id
        logger.info(f"Loading model: {model_id}")
        asr_model = load_model(model_id)
        logger.info(f"Model {model_id} loaded successfully")

    except Exception as e:
        logger.error(f"Error during initialization: {str(e)}")
        raise


def download_audio(url: str, output_path: str) -> str:
    """Download audio file from URL"""
    try:
        logger.info(f"Downloading audio from: {url}")
        response = requests.get(url, timeout=300)
        response.raise_for_status()

        with open(output_path, 'wb') as f:
            f.write(response.content)

        logger.info(f"Audio downloaded: {output_path}")
        return output_path
    except Exception as e:
        logger.error(f"Error downloading audio: {str(e)}")
        raise


def decode_base64_audio(base64_data: str, output_path: str, audio_format: str) -> str:
    """Decode base64-encoded audio data"""
    try:
        logger.info(f"Decoding base64 audio data (format: {audio_format})")

        # Remove data URL prefix if present
        if ',' in base64_data:
            base64_data = base64_data.split(',', 1)[1]

        # Decode base64 data
        audio_bytes = base64.b64decode(base64_data)

        # Add extension if not present
        if not output_path.endswith(f'.{audio_format}'):
            output_path = f"{output_path}.{audio_format}"

        with open(output_path, 'wb') as f:
            f.write(audio_bytes)

        logger.info(f"Audio decoded: {output_path}")
        return output_path
    except Exception as e:
        logger.error(f"Error decoding base64 audio: {str(e)}")
        raise


def merge_diarization_with_transcription(diarization_segments: List[Dict],
                                        transcription_segments: List[WhisperSegment]) -> List[WhisperSegment]:
    """
    Merge diarization results with transcription segments

    Args:
        diarization_segments: List of diarization segments from diarization endpoint
        transcription_segments: List of transcription segments

    Returns:
        Merged list with speaker information
    """
    if not diarization_segments:
        return transcription_segments

    # For each transcription segment, find the dominant speaker
    for segment in transcription_segments:
        start = segment.start
        end = segment.end

        # Find overlapping diarization segments
        overlapping = []
        for diar_seg in diarization_segments:
            # Calculate overlap
            overlap_start = max(start, diar_seg['start'])
            overlap_end = min(end, diar_seg['end'])

            if overlap_end > overlap_start:
                duration = overlap_end - overlap_start
                overlapping.append((diar_seg['speaker'], duration))

        # Assign the speaker with most overlap
        if overlapping:
            overlapping.sort(key=lambda x: x[1], reverse=True)
            setattr(segment, "speaker", overlapping[0][0])
        else:
            setattr(segment, "speaker", "unknown")

    return transcription_segments


def handler(job: Dict[str, Any]) -> Dict[str, Any]:
    """
    RunPod handler function for audio transcription

    Args:
        job: Job data from RunPod

    Returns:
        Transcription results
    """
    global asr_model, config

    job_input = job.get("input", {})

    # Validate input
    if not job_input.get("audio"):
        return {"error": "Missing required 'audio' field in input"}

    # Extract parameters
    audio_input = job_input.get("audio")
    audio_format = job_input.get("audio_format")
    language = job_input.get("language")
    response_format = job_input.get("response_format", "json")
    timestamps = job_input.get("timestamps", False)
    temperature = job_input.get("temperature", 0.0)
    word_timestamps = job_input.get("word_timestamps", False)
    diarization_segments = job_input.get("diarization_segments")

    # Validate response format
    valid_formats = ["json", "text", "srt", "vtt", "verbose_json"]
    if response_format not in valid_formats:
        return {"error": f"Invalid response_format. Must be one of: {', '.join(valid_formats)}"}

    # Track files and directories to clean up
    temp_file = None
    wav_file = None
    audio_chunks = []
    chunk_dirs_to_cleanup = set()
    temp_dir = None

    try:
        # Create temporary directory
        temp_dir = tempfile.mkdtemp(prefix="runpod_transcription_")
        logger.info(f"Created temp directory: {temp_dir}")

        # Download or decode audio
        temp_file = os.path.join(temp_dir, "input_audio")

        if audio_input.startswith("http://") or audio_input.startswith("https://"):
            # Download from URL
            temp_file = download_audio(audio_input, temp_file)
        else:
            # Assume base64 encoded
            if not audio_format:
                return {"error": "audio_format is required when using base64-encoded audio"}
            temp_file = decode_base64_audio(audio_input, temp_file, audio_format)

        # Convert to WAV format
        wav_file = convert_audio_to_wav(temp_file)
        logger.info(f"Converted to WAV: {wav_file}")

        # Split audio into chunks if needed
        chunk_duration = config.chunk_duration
        audio_chunks = split_audio_into_chunks(wav_file, chunk_duration=chunk_duration)
        logger.info(f"Split into {len(audio_chunks)} chunks")

        # Track chunk directories for cleanup
        for chunk in audio_chunks:
            chunk_dir = os.path.dirname(chunk)
            if chunk_dir and chunk_dir != os.path.dirname(wav_file):
                chunk_dirs_to_cleanup.add(chunk_dir)

        # Process each chunk
        all_text = []
        all_segments = []

        for i, chunk_path in enumerate(audio_chunks):
            logger.info(f"Processing chunk {i+1}/{len(audio_chunks)}")

            # Clear GPU cache to avoid OOM
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
        logger.info(f"Transcription complete: {len(full_text)} characters")

        # Apply diarization if provided
        if diarization_segments:
            logger.info("Merging diarization with transcription")
            all_segments = merge_diarization_with_transcription(diarization_segments, all_segments)

        # Format response based on requested format
        if response_format == "text":
            result = {"text": full_text}
        elif response_format == "srt":
            result = {"text": format_srt(all_segments)}
        elif response_format == "vtt":
            result = {"text": format_vtt(all_segments)}
        elif response_format == "verbose_json":
            result = {
                "text": full_text,
                "language": language,
                "duration": sum((seg.end - seg.start) for seg in all_segments),
                "model": "parakeet-tdt-0.6b-v2",
                "segments": [
                    {
                        "id": seg.id,
                        "start": seg.start,
                        "end": seg.end,
                        "text": seg.text,
                        "speaker": getattr(seg, "speaker", None)
                    }
                    for seg in all_segments
                ]
            }
        else:  # json format
            result = {"text": full_text}
            if timestamps or diarization_segments:
                result["segments"] = [
                    {
                        "id": seg.id,
                        "start": seg.start,
                        "end": seg.end,
                        "text": seg.text,
                        "speaker": getattr(seg, "speaker", None)
                    }
                    for seg in all_segments
                ]

        logger.info("Transcription job completed successfully")
        return result

    except Exception as e:
        logger.error(f"Error during transcription: {str(e)}")
        return {"error": str(e)}

    finally:
        # Clean up temporary files
        try:
            if temp_file and os.path.exists(temp_file):
                os.unlink(temp_file)
        except Exception as e:
            logger.warning(f"Failed to clean up temp file: {e}")

        try:
            if wav_file and wav_file != temp_file and os.path.exists(wav_file):
                os.unlink(wav_file)
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
            except Exception as e:
                logger.warning(f"Failed to clean up chunk directory {chunk_dir}: {e}")

        # Clean up temp directory
        try:
            if temp_dir and os.path.exists(temp_dir):
                shutil.rmtree(temp_dir)
        except Exception as e:
            logger.warning(f"Failed to clean up temp directory: {e}")


if __name__ == "__main__":
    # Initialize the model on startup
    logger.info("Initializing transcription worker...")
    initialize()
    logger.info("Worker initialized, starting RunPod serverless handler")

    # Start the RunPod handler
    runpod.serverless.start({"handler": handler})
