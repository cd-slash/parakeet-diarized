#!/usr/bin/env python3
"""
Test script for RunPod Load Balancing endpoint

This uses the standard Whisper API format with multipart/form-data
for direct file uploads (no base64 encoding needed).

Usage:
    export RUNPOD_API_KEY="your_api_key"
    python test_load_balancing.py <audio_file>

Example:
    export RUNPOD_API_KEY="your_api_key_here"
    python test_load_balancing.py ~/Downloads/yt_test.wav
"""

import requests
import sys
import os
import time

# Configuration - Your Load Balancing endpoint URL
ENDPOINT = "https://vz38j7u4dcv529.api.runpod.ai"
TRANSCRIPTION_PATH = "/v1/audio/transcriptions"

def main():
    # Get API key from environment
    api_key = os.environ.get("RUNPOD_API_KEY")
    if not api_key:
        print("Error: RUNPOD_API_KEY environment variable not set")
        print("\nSet it with:")
        print('  export RUNPOD_API_KEY="your_api_key_here"')
        sys.exit(1)

    # Get audio file path from command line
    if len(sys.argv) < 2:
        print("Usage: python test_load_balancing.py <audio_file>")
        print("\nExample:")
        print("  python test_load_balancing.py ~/Downloads/yt_test.wav")
        sys.exit(1)

    audio_path = os.path.expanduser(sys.argv[1])

    # Check if file exists
    if not os.path.exists(audio_path):
        print(f"Error: File not found: {audio_path}")
        sys.exit(1)

    # Get file size
    file_size_mb = os.path.getsize(audio_path) / 1024 / 1024
    print(f"Reading {audio_path}...")
    print(f"File size: {file_size_mb:.2f} MB")

    # Send the request
    print("\n" + "="*60)
    print("RUNPOD LOAD BALANCING ENDPOINT TEST")
    print("="*60)
    print(f"Endpoint: {ENDPOINT}{TRANSCRIPTION_PATH}")
    print(f"Method: POST with multipart/form-data")
    print(f"File: {os.path.basename(audio_path)}")
    print("="*60)
    print("\nNote: First request may take 30-90s (cold start + model loading)")
    print("Subsequent requests will be much faster (<10s with Model Store)\n")

    start_time = time.time()

    try:
        # Open file and prepare request
        with open(audio_path, 'rb') as audio_file:
            # Prepare multipart/form-data request (standard Whisper API format)
            files = {
                'file': (os.path.basename(audio_path), audio_file, 'audio/wav')
            }

            # Form data parameters
            data = {
                'model': 'whisper-1',  # For API compatibility
                'response_format': 'verbose_json',
                'timestamps': 'true',
                'diarize': 'true',
            }

            # Add authentication header
            headers = {
                "Authorization": f"Bearer {api_key}"
            }

            print("Sending request...")
            response = requests.post(
                f"{ENDPOINT}{TRANSCRIPTION_PATH}",
                files=files,
                data=data,
                headers=headers,
                timeout=600  # 10 minute timeout
            )
        response.raise_for_status()

        elapsed_time = time.time() - start_time

        result = response.json()

        print("\n" + "="*60)
        print("TRANSCRIPTION RESULT")
        print("="*60)
        print("\n" + result.get("text", "No text returned"))
        print("\n" + "="*60)
        print("METADATA")
        print("="*60)
        print(f"Request time: {elapsed_time:.2f}s")
        print(f"Audio duration: {result.get('duration', 0):.2f}s")
        print(f"Model: {result.get('model', 'unknown')}")
        print(f"Language: {result.get('language', 'auto')}")
        print(f"Segments: {len(result.get('segments', []))}")

        # Print segments with timestamps
        segments = result.get("segments", [])
        if segments:
            print("\n" + "="*60)
            print("SEGMENTS (with timestamps)")
            print("="*60)

            # Show first 5 segments
            show_count = min(5, len(segments))
            for seg in segments[:show_count]:
                start = seg.get('start', 0)
                end = seg.get('end', 0)
                text = seg.get('text', '')
                speaker = seg.get('speaker')

                timestamp = f"[{start:6.2f}s - {end:6.2f}s]"
                if speaker:
                    print(f"{timestamp} Speaker {speaker}: {text}")
                else:
                    print(f"{timestamp} {text}")

            if len(segments) > show_count:
                print(f"\n... and {len(segments) - show_count} more segments")

        print("\n" + "="*60)
        print("SUCCESS")
        print("="*60)

    except requests.exceptions.Timeout:
        print("\n" + "="*60)
        print("ERROR: Request timed out (>600s)")
        print("="*60)
        print("The audio file may be too large or the endpoint is not responding.")
        sys.exit(1)

    except requests.exceptions.HTTPError as e:
        print("\n" + "="*60)
        print(f"ERROR: HTTP {e.response.status_code}")
        print("="*60)
        print(f"Response: {e.response.text}")
        sys.exit(1)

    except requests.exceptions.RequestException as e:
        print("\n" + "="*60)
        print(f"ERROR: Request failed")
        print("="*60)
        print(str(e))
        sys.exit(1)

    except Exception as e:
        print("\n" + "="*60)
        print(f"ERROR: Unexpected error")
        print("="*60)
        print(str(e))
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
