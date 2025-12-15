# RunPod Serverless Deployment Guide

This guide explains how to deploy the Parakeet Transcription Service as a RunPod serverless endpoint.

## Overview

The RunPod serverless implementation provides on-demand audio transcription with automatic scaling. Workers start when requests arrive and shut down when idle, so you only pay for actual compute time.

## Features

- GPU-accelerated transcription using NVIDIA Parakeet-TDT
- Optional speaker diarization with Pyannote.audio
- Automatic scaling from zero to hundreds of workers
- Per-second billing with no idle costs
- Support for audio URLs and base64-encoded audio
- Multiple output formats (JSON, text, SRT, VTT)

## Prerequisites

1. **RunPod Account**: Sign up at [runpod.io](https://runpod.io)
2. **Docker Hub Account**: For hosting your Docker image (or use RunPod's container registry)
3. **HuggingFace Account**: Required for speaker diarization
   - Create account at [huggingface.co](https://huggingface.co)
   - Generate access token at [HuggingFace Settings](https://huggingface.co/settings/tokens)
   - Accept terms for [pyannote/speaker-diarization-3.1](https://huggingface.co/pyannote/speaker-diarization-3.1)

## Step 1: Build the Docker Image

Build and push the Docker image to a container registry:

```bash
# Build the image
docker build -t your-username/parakeet-transcription:latest .

# Push to Docker Hub
docker push your-username/parakeet-transcription:latest
```

Alternatively, you can use RunPod's container registry or other registries like GitHub Container Registry.

## Step 2: Create a RunPod Serverless Endpoint

### Using the RunPod Web Interface

1. Log in to [RunPod](https://www.runpod.io)
2. Navigate to "Serverless" in the sidebar
3. Click "New Endpoint"
4. Configure the endpoint:
   - **Endpoint Name**: `parakeet-transcription` (or your preference)
   - **Container Image**: `your-username/parakeet-transcription:latest`
   - **GPU Type**: Select NVIDIA GPU (RTX 3090, RTX 4090, A4000, or higher recommended)
   - **Container Disk**: At least 10 GB (smaller if using Model Store)

5. **Model Configuration (RECOMMENDED - Beta Feature)**:
   - **Model (optional)**: `nvidia/parakeet-tdt-0.6b-v2`
   - This uses RunPod's Model Store to pre-cache the model on host machines
   - **Benefits**:
     - Near-instant cold starts (model already downloaded)
     - Smaller Docker images (no need to embed model)
     - Lower costs (no billing during model download)
     - Models shared across workers on the same host
   - **Note**: If model is gated or private, provide your HuggingFace token

6. **Environment Variables**:
   - `HUGGINGFACE_ACCESS_TOKEN`: Your HuggingFace token (required for speaker diarization)
   - `MODEL_ID`: `nvidia/parakeet-tdt-0.6b-v2` (optional, this is the default)
   - `TEMP_DIR`: `/tmp/parakeet` (optional)
   - `CHUNK_DURATION`: `500` (optional, in seconds)

7. **Worker Configuration**:
   - **Min Workers**: 0 (scale to zero when idle)
   - **Max Workers**: 3-10 (adjust based on expected load)
   - **Idle Timeout**: 5 seconds (how long to wait before scaling down)
   - **Max Execution Time**: 300-600 seconds (adjust based on audio length)

8. Click "Deploy"

### Using the RunPod CLI

You can also deploy using the RunPod CLI or API. See [RunPod's documentation](https://docs.runpod.io/serverless/endpoints/manage-endpoints) for details.

## Step 3: Test Your Endpoint

Once deployed, you'll receive an endpoint URL and API key. Test it with a sample request:

### Using cURL

```bash
# Test with an audio URL
curl -X POST https://api.runpod.ai/v2/YOUR_ENDPOINT_ID/run \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -d '{
    "input": {
      "audio": "https://example.com/sample-audio.mp3",
      "response_format": "json",
      "diarize": true,
      "timestamps": true
    }
  }'

# Test with base64-encoded audio
curl -X POST https://api.runpod.ai/v2/YOUR_ENDPOINT_ID/run \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -d '{
    "input": {
      "audio": "BASE64_ENCODED_AUDIO_DATA",
      "audio_format": "mp3",
      "response_format": "verbose_json",
      "diarize": true,
      "language": "en"
    }
  }'
```

### Using Python

```python
import requests
import base64

# Your RunPod endpoint details
ENDPOINT_ID = "your-endpoint-id"
API_KEY = "your-api-key"
RUNPOD_API_URL = f"https://api.runpod.ai/v2/{ENDPOINT_ID}/run"

# Example 1: Transcribe from URL
def transcribe_from_url(audio_url, diarize=True):
    payload = {
        "input": {
            "audio": audio_url,
            "response_format": "json",
            "diarize": diarize,
            "timestamps": True
        }
    }

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {API_KEY}"
    }

    response = requests.post(RUNPOD_API_URL, json=payload, headers=headers)
    return response.json()

# Example 2: Transcribe from local file
def transcribe_from_file(file_path, audio_format="mp3"):
    # Read and encode the audio file
    with open(file_path, "rb") as f:
        audio_data = base64.b64encode(f.read()).decode("utf-8")

    payload = {
        "input": {
            "audio": audio_data,
            "audio_format": audio_format,
            "response_format": "verbose_json",
            "diarize": True,
            "timestamps": True
        }
    }

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {API_KEY}"
    }

    response = requests.post(RUNPOD_API_URL, json=payload, headers=headers)
    return response.json()

# Use the functions
result = transcribe_from_url("https://example.com/audio.mp3")
print(result)
```

## Input Format

The handler accepts the following input parameters:

```json
{
  "input": {
    "audio": "URL or base64-encoded audio data",
    "audio_format": "mp3|wav|m4a|flac|ogg (required for base64)",
    "language": "en (optional language code)",
    "response_format": "json|text|srt|vtt|verbose_json (default: json)",
    "timestamps": true|false (default: false),
    "diarize": true|false (default: true),
    "word_timestamps": true|false (default: false),
    "temperature": 0.0 (sampling temperature, default: 0.0)
  }
}
```

### Parameters

- **audio** (required): Either a publicly accessible URL or base64-encoded audio data
- **audio_format** (required for base64): File format (mp3, wav, m4a, etc.)
- **language** (optional): ISO language code (e.g., "en", "es", "fr")
- **response_format** (optional): Output format
  - `json`: Simple JSON with text only
  - `verbose_json`: Full JSON with segments and metadata
  - `text`: Plain text transcription
  - `srt`: SubRip subtitle format
  - `vtt`: WebVTT subtitle format
- **timestamps** (optional): Include segment timestamps in JSON response
- **diarize** (optional): Enable speaker diarization (requires HuggingFace token)
- **word_timestamps** (optional): Enable word-level timestamps
- **temperature** (optional): Sampling temperature for transcription

## Output Format

### JSON Response
```json
{
  "text": "Full transcription text"
}
```

### Verbose JSON Response
```json
{
  "text": "Full transcription text",
  "language": "en",
  "duration": 123.45,
  "model": "parakeet-tdt-0.6b-v2",
  "segments": [
    {
      "id": 0,
      "start": 0.0,
      "end": 2.5,
      "text": "Segment text",
      "speaker": "1"
    }
  ]
}
```

### Error Response
```json
{
  "error": "Error message description"
}
```

## Performance & Optimization

### Cold Start Time

**With RunPod Model Store (Recommended)**:
- First request: ~5-10 seconds (model already cached on host)
- Subsequent requests: <3 seconds (if worker is warm)
- Model pre-cached before worker starts, so no download time

**Without Model Store (model in Docker image)**:
- First request: ~15-30 seconds (loading model from image)
- Subsequent requests: <5 seconds (if worker is warm)

**Without Model Store (downloading at runtime)**:
- First request: ~60-120 seconds (downloading + loading model)
- Subsequent requests: <5 seconds (if worker is warm)

### Reducing Cold Starts
1. **Use RunPod Model Store** (BEST) - Pre-cache models on host machines
   - Configure in endpoint settings: Model field = `nvidia/parakeet-tdt-0.6b-v2`
   - Near-instant cold starts
   - No download time billed
2. Set **Min Workers** > 0 to keep workers warm (incurs idle costs)
3. Use **Idle Timeout** wisely (balance between responsiveness and cost)
4. For private/custom models not on HuggingFace, embed in Docker image

### GPU Recommendations
- **RTX 3090/4090**: Good for shorter audio (<10 minutes)
- **A4000/A5000**: Better for longer audio and concurrent requests
- **A6000/A100**: Best for high-volume production workloads

### Cost Estimation
- Typical cost: $0.0002-0.0006 per second of GPU time
- 1 minute audio transcription: ~5-10 seconds GPU time = $0.001-0.006
- With diarization: ~10-20 seconds GPU time = $0.002-0.012

## Monitoring & Debugging

### View Logs
1. Go to your endpoint in RunPod dashboard
2. Click "Logs" tab
3. Select a worker to view its logs

### Common Issues

**"Model not loaded yet"**
- Solution: Wait for worker initialization (~30-60 seconds on first request)

**"Diarization requested but no HuggingFace token available"**
- Solution: Set `HUGGINGFACE_ACCESS_TOKEN` environment variable

**"Error downloading audio"**
- Solution: Ensure the audio URL is publicly accessible
- Alternative: Use base64-encoded audio instead

**Out of memory errors**
- Solution: Use smaller GPU, reduce `CHUNK_DURATION`, or process shorter audio files

## Scaling Configuration

### For Light Usage (< 100 requests/day)
- Min Workers: 0
- Max Workers: 1-2
- Idle Timeout: 5 seconds

### For Medium Usage (100-1000 requests/day)
- Min Workers: 0-1
- Max Workers: 3-5
- Idle Timeout: 10 seconds

### For High Usage (> 1000 requests/day)
- Min Workers: 1-2 (keep warm)
- Max Workers: 5-10
- Idle Timeout: 30 seconds

## Model Deployment Options Comparison

| Feature | Model Store (Recommended) | Embedded in Docker | Download at Runtime |
|---------|---------------------------|-------------------|---------------------|
| **Cold Start Time** | 5-10 seconds | 15-30 seconds | 60-120 seconds |
| **Docker Image Size** | ~2GB | ~4GB | ~2GB |
| **Billing for Download** | No | No | Yes |
| **HuggingFace Models** | Yes | Yes | Yes |
| **Private/Custom Models** | HF only | Any model | Any model |
| **Setup Complexity** | Easy (1 field) | Medium | Simple |
| **Best For** | Production use | Private models | Testing only |

## Advanced Configuration

### Using RunPod Model Store for Model Caching

RunPod's Model Store (Beta) is the recommended approach for hosting models from HuggingFace:

**Setup**:
1. In endpoint configuration, add Model: `nvidia/parakeet-tdt-0.6b-v2`
2. For gated models, provide your HuggingFace access token
3. Models are automatically cached at `/runpod-volume/huggingface-cache/hub/`
4. Workers on the same host share the cached model

**Benefits**:
- Cold starts reduced from 60s to 5-10s
- No billing during model download
- Smaller Docker images (no need to embed model)
- Automatic model management by RunPod

**Current Limitations**:
- One model per endpoint
- Only works with HuggingFace models
- Beta feature (may have occasional issues)

**Path Structure**:
```
/runpod-volume/huggingface-cache/hub/models--nvidia--parakeet-tdt-0.6b-v2/snapshots/VERSION_HASH/
```

### Alternative: Embed Model in Docker Image

If NOT using Model Store, uncomment these lines in the Dockerfile:
```dockerfile
RUN python -c "from nemo.collections.asr.models import EncDecCTCModelBPE; \
    print('Downloading Parakeet model...'); \
    model = EncDecCTCModelBPE.from_pretrained('nvidia/parakeet-tdt-0.6b-v2'); \
    print('Model downloaded successfully')"
```

**When to use**:
- Private models not on HuggingFace
- Need guaranteed model availability
- Don't mind larger image size (~4GB vs 2GB)

### Custom Model
Set the `MODEL_ID` environment variable to use a different Parakeet model:
```
MODEL_ID=nvidia/parakeet-tdt-1.1b
```

If using Model Store, also update the Model field in endpoint configuration.

### Custom Chunk Duration
Adjust the `CHUNK_DURATION` (in seconds) to control memory usage:
```
CHUNK_DURATION=300  # Process 5-minute chunks
```

### Disable Diarization by Default
```
ENABLE_DIARIZATION=false
```

## GitHub Integration

RunPod supports automatic deployment from GitHub:

1. Push your code to a GitHub repository
2. In RunPod endpoint settings, connect your GitHub repo
3. RunPod will automatically rebuild and redeploy on git push

## Support & Resources

- **RunPod Documentation**: [docs.runpod.io](https://docs.runpod.io)
- **RunPod Discord**: [discord.gg/runpod](https://discord.gg/runpod)
- **Parakeet Model**: [nvidia/parakeet-tdt-0.6b-v2](https://huggingface.co/nvidia/parakeet-tdt-0.6b-v2)
- **Pyannote Audio**: [github.com/pyannote/pyannote-audio](https://github.com/pyannote/pyannote-audio)

## Next Steps

1. Deploy your endpoint following this guide
2. Test with sample audio files
3. Integrate into your application
4. Monitor usage and adjust scaling settings
5. Optimize costs based on your usage patterns
