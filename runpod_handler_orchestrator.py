"""
RunPod Serverless Handler - Orchestrator

This handler orchestrates calls to separate diarization and transcription endpoints.
Use this when you want a single endpoint but need both diarization and transcription
models cached via RunPod Model Store.

Requirements:
- Set DIARIZATION_ENDPOINT_ID and TRANSCRIPTION_ENDPOINT_ID environment variables
- Set RUNPOD_API_KEY environment variable

Input format (same as single endpoint):
{
    "input": {
        "audio": "https://example.com/audio.mp3" or "base64_encoded_audio_data",
        "audio_format": "mp3" (required if using base64),
        "language": "en" (optional),
        "response_format": "json|text|srt|vtt|verbose_json" (default: "json"),
        "timestamps": true|false (default: false),
        "diarize": true|false (default: true),
        "word_timestamps": true|false (default: false),
        "temperature": 0.0 (default)
    }
}
"""

import os
import logging
import time
from typing import Dict, Any, Optional
import requests

import runpod

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Global configuration
DIARIZATION_ENDPOINT = None
TRANSCRIPTION_ENDPOINT = None
RUNPOD_API_KEY = None


def initialize():
    """Initialize configuration on worker startup"""
    global DIARIZATION_ENDPOINT, TRANSCRIPTION_ENDPOINT, RUNPOD_API_KEY

    # Get endpoint URLs and API key
    diar_id = os.environ.get("DIARIZATION_ENDPOINT_ID")
    trans_id = os.environ.get("TRANSCRIPTION_ENDPOINT_ID")
    RUNPOD_API_KEY = os.environ.get("RUNPOD_API_KEY")

    if not diar_id or not trans_id:
        raise ValueError("DIARIZATION_ENDPOINT_ID and TRANSCRIPTION_ENDPOINT_ID must be set")

    if not RUNPOD_API_KEY:
        raise ValueError("RUNPOD_API_KEY must be set")

    DIARIZATION_ENDPOINT = f"https://api.runpod.ai/v2/{diar_id}/runsync"
    TRANSCRIPTION_ENDPOINT = f"https://api.runpod.ai/v2/{trans_id}/runsync"

    logger.info(f"Diarization endpoint: {DIARIZATION_ENDPOINT}")
    logger.info(f"Transcription endpoint: {TRANSCRIPTION_ENDPOINT}")


def call_runpod_endpoint(url: str, payload: Dict[str, Any], timeout: int = 600) -> Dict[str, Any]:
    """
    Call a RunPod endpoint synchronously

    Args:
        url: Endpoint URL
        payload: Request payload
        timeout: Request timeout in seconds

    Returns:
        Response from endpoint
    """
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {RUNPOD_API_KEY}"
    }

    try:
        logger.info(f"Calling endpoint: {url}")
        response = requests.post(url, json=payload, headers=headers, timeout=timeout)
        response.raise_for_status()

        result = response.json()

        # Check for errors in response
        if "error" in result:
            logger.error(f"Endpoint returned error: {result['error']}")
            return {"error": result["error"]}

        # Extract output from RunPod response format
        if "output" in result:
            return result["output"]

        return result

    except requests.exceptions.Timeout:
        logger.error(f"Timeout calling endpoint: {url}")
        return {"error": "Endpoint request timed out"}
    except requests.exceptions.RequestException as e:
        logger.error(f"Error calling endpoint: {str(e)}")
        return {"error": f"Failed to call endpoint: {str(e)}"}
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        return {"error": str(e)}


def handler(job: Dict[str, Any]) -> Dict[str, Any]:
    """
    RunPod orchestrator handler

    Calls diarization and transcription endpoints in parallel (if diarization enabled),
    then merges the results.

    Args:
        job: Job data from RunPod

    Returns:
        Combined transcription and diarization results
    """
    job_input = job.get("input", {})

    # Validate input
    if not job_input.get("audio"):
        return {"error": "Missing required 'audio' field in input"}

    # Extract parameters
    audio = job_input.get("audio")
    audio_format = job_input.get("audio_format")
    language = job_input.get("language")
    response_format = job_input.get("response_format", "json")
    timestamps = job_input.get("timestamps", False)
    diarize = job_input.get("diarize", True)
    word_timestamps = job_input.get("word_timestamps", False)
    temperature = job_input.get("temperature", 0.0)

    try:
        diarization_result = None

        # Step 1: Call diarization endpoint if enabled
        if diarize:
            logger.info("Calling diarization endpoint...")
            diar_payload = {
                "input": {
                    "audio": audio,
                    "audio_format": audio_format
                }
            }

            diarization_result = call_runpod_endpoint(DIARIZATION_ENDPOINT, diar_payload, timeout=600)

            if "error" in diarization_result:
                logger.warning(f"Diarization failed: {diarization_result['error']}")
                # Continue with transcription even if diarization fails
                diarization_result = None
            else:
                logger.info(f"Diarization complete: {diarization_result.get('num_speakers', 0)} speakers detected")

        # Step 2: Call transcription endpoint
        logger.info("Calling transcription endpoint...")
        trans_payload = {
            "input": {
                "audio": audio,
                "audio_format": audio_format,
                "language": language,
                "response_format": response_format,
                "timestamps": timestamps or diarize,  # Need timestamps if diarizing
                "word_timestamps": word_timestamps,
                "temperature": temperature
            }
        }

        # Add diarization results if available
        if diarization_result and "segments" in diarization_result:
            trans_payload["input"]["diarization_segments"] = diarization_result["segments"]

        transcription_result = call_runpod_endpoint(TRANSCRIPTION_ENDPOINT, trans_payload, timeout=900)

        if "error" in transcription_result:
            return {"error": f"Transcription failed: {transcription_result['error']}"}

        # Step 3: Return combined results
        logger.info("Orchestration complete")
        return transcription_result

    except Exception as e:
        logger.error(f"Error in orchestrator: {str(e)}")
        return {"error": str(e)}


if __name__ == "__main__":
    # Initialize configuration on startup
    logger.info("Initializing orchestrator...")
    initialize()
    logger.info("Orchestrator initialized, starting RunPod serverless handler")

    # Start the RunPod handler
    runpod.serverless.start({"handler": handler})
