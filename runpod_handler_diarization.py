"""
RunPod Serverless Handler - Diarization Only

This handler provides speaker diarization as a standalone service.
Use in combination with the transcription handler for optimal Model Store usage.

Input format:
{
    "input": {
        "audio": "https://example.com/audio.mp3" or "base64_encoded_audio_data",
        "audio_format": "mp3" (required if using base64),
        "num_speakers": 2 (optional, hint for number of speakers)
    }
}

Output format:
{
    "segments": [
        {"start": 0.0, "end": 2.5, "speaker": "1"},
        {"start": 2.5, "end": 5.0, "speaker": "2"}
    ],
    "num_speakers": 2,
    "duration": 5.0
}
"""

import os
import logging
import base64
import tempfile
import shutil
from pathlib import Path
from typing import Dict, Any, Optional
import requests
import torch

import runpod

from audio import convert_audio_to_wav
from diarization import Diarizer

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Global variables
diarizer = None


def initialize():
    """Initialize the diarization model on worker startup"""
    global diarizer

    try:
        # Check for HuggingFace token
        hf_token = os.environ.get("HUGGINGFACE_ACCESS_TOKEN")
        if not hf_token:
            logger.error("HUGGINGFACE_ACCESS_TOKEN not set - diarization will not work!")
            raise ValueError("HUGGINGFACE_ACCESS_TOKEN environment variable is required")

        # Log CUDA availability
        if torch.cuda.is_available():
            logger.info(f"CUDA available: {torch.cuda.get_device_name(0)}")
        else:
            logger.warning("CUDA not available, using CPU (will be slow)")

        # Initialize diarizer
        logger.info("Initializing speaker diarization model...")
        diarizer = Diarizer(access_token=hf_token)
        logger.info("Diarization model loaded successfully")

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


def handler(job: Dict[str, Any]) -> Dict[str, Any]:
    """
    RunPod handler function for speaker diarization

    Args:
        job: Job data from RunPod

    Returns:
        Diarization results with speaker segments
    """
    global diarizer

    if not diarizer:
        return {"error": "Diarization model not initialized"}

    job_input = job.get("input", {})

    # Validate input
    if not job_input.get("audio"):
        return {"error": "Missing required 'audio' field in input"}

    # Extract parameters
    audio_input = job_input.get("audio")
    audio_format = job_input.get("audio_format")
    num_speakers = job_input.get("num_speakers")

    # Track files and directories to clean up
    temp_file = None
    wav_file = None
    temp_dir = None

    try:
        # Create temporary directory
        temp_dir = tempfile.mkdtemp(prefix="runpod_diarization_")
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

        # Perform diarization
        logger.info("Starting speaker diarization...")
        diarization_result = diarizer.diarize(wav_file, num_speakers=num_speakers)

        if not diarization_result.segments:
            logger.warning("No speakers detected in audio")
            return {
                "segments": [],
                "num_speakers": 0,
                "duration": 0.0
            }

        # Calculate total duration
        max_end = max(seg.end for seg in diarization_result.segments) if diarization_result.segments else 0.0

        # Format response
        result = {
            "segments": [
                {
                    "start": seg.start,
                    "end": seg.end,
                    "speaker": seg.speaker
                }
                for seg in diarization_result.segments
            ],
            "num_speakers": diarization_result.num_speakers,
            "duration": max_end
        }

        logger.info(f"Diarization complete: {diarization_result.num_speakers} speakers, {len(diarization_result.segments)} segments")
        return result

    except Exception as e:
        logger.error(f"Error during diarization: {str(e)}")
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

        try:
            if temp_dir and os.path.exists(temp_dir):
                shutil.rmtree(temp_dir)
        except Exception as e:
            logger.warning(f"Failed to clean up temp directory: {e}")


if __name__ == "__main__":
    # Initialize the model on startup
    logger.info("Initializing diarization worker...")
    initialize()
    logger.info("Worker initialized, starting RunPod serverless handler")

    # Start the RunPod handler
    runpod.serverless.start({"handler": handler})
