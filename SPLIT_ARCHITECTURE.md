# Split Architecture Deployment Guide

This guide explains how to deploy separate diarization and transcription endpoints to take full advantage of RunPod's Model Store, which is limited to one cached model per endpoint.

## Why Split Architecture?

### Problem
RunPod's Model Store (Beta) can only cache **one model per endpoint**. This project uses two large models:
- **Parakeet-TDT** (~2GB) for transcription
- **Pyannote Speaker Diarization** (~1GB) for speaker identification

### Solution
Deploy as **two separate endpoints**:
1. **Diarization Endpoint**: Caches `pyannote/speaker-diarization-3.1`
2. **Transcription Endpoint**: Caches `nvidia/parakeet-tdt-0.6b-v2`

### Benefits

| Metric | Single Endpoint | Split Architecture |
|--------|----------------|-------------------|
| **Cold Start** | 60-120s (download both) | 5-10s each (both cached) |
| **GPU Memory** | ~8GB (both loaded) | ~4GB each (separate) |
| **Scaling** | Same for both tasks | Independent per task |
| **Cost** | Download billing | No download billing |
| **Flexibility** | All-or-nothing | Use only what you need |

## Architecture Options

### Option 1: Client-Side Orchestration (Recommended for Production)
Your application calls both endpoints and merges results.

**Pros**: Maximum flexibility, parallel execution, no extra endpoint
**Cons**: Client handles orchestration logic

### Option 2: Orchestrator Endpoint
Deploy a lightweight orchestrator that calls both endpoints.

**Pros**: Simple client integration, single API call
**Cons**: Extra endpoint to manage, sequential execution

### Option 3: Single Endpoint (Original)
One endpoint with both models (only one cached).

**Pros**: Simplest deployment
**Cons**: Slower cold starts, only one model cached

## Deployment Guide

### Step 1: Build Docker Images

```bash
# Build diarization endpoint
docker build -f Dockerfile.diarization -t your-username/parakeet-diarization:latest .
docker push your-username/parakeet-diarization:latest

# Build transcription endpoint
docker build -f Dockerfile.transcription -t your-username/parakeet-transcription:latest .
docker push your-username/parakeet-transcription:latest

# Optional: Build orchestrator
docker build -f Dockerfile.orchestrator -t your-username/parakeet-orchestrator:latest .
docker push your-username/parakeet-orchestrator:latest
```

### Step 2: Deploy Diarization Endpoint

1. Go to [RunPod Console](https://www.runpod.io/console/serverless) → Serverless → New Endpoint

2. **Basic Configuration**:
   - **Name**: `parakeet-diarization`
   - **Container Image**: `your-username/parakeet-diarization:latest`
   - **GPU Type**: RTX 3090, RTX 4090, A4000
   - **Container Disk**: 8 GB

3. **Model Store Configuration** (IMPORTANT):
   - **Model**: `pyannote/speaker-diarization-3.1`
   - This caches the diarization model on host machines

4. **Environment Variables**:
   ```
   HUGGINGFACE_ACCESS_TOKEN=your_hf_token_here
   ```
   Note: Must accept terms at https://huggingface.co/pyannote/speaker-diarization-3.1

5. **Worker Settings**:
   - **Min Workers**: 0
   - **Max Workers**: 3-5
   - **Idle Timeout**: 5 seconds
   - **Max Execution Time**: 300 seconds

6. **Deploy** and note the **Endpoint ID**

### Step 3: Deploy Transcription Endpoint

1. Create another endpoint: **New Endpoint**

2. **Basic Configuration**:
   - **Name**: `parakeet-transcription`
   - **Container Image**: `your-username/parakeet-transcription:latest`
   - **GPU Type**: RTX 3090, RTX 4090, A4000
   - **Container Disk**: 10 GB

3. **Model Store Configuration** (IMPORTANT):
   - **Model**: `nvidia/parakeet-tdt-0.6b-v2`
   - This caches the Parakeet transcription model

4. **Environment Variables**:
   ```
   MODEL_ID=nvidia/parakeet-tdt-0.6b-v2
   CHUNK_DURATION=500
   ```

5. **Worker Settings**:
   - **Min Workers**: 0
   - **Max Workers**: 3-5
   - **Idle Timeout**: 5 seconds
   - **Max Execution Time**: 600 seconds

6. **Deploy** and note the **Endpoint ID**

### Step 4 (Optional): Deploy Orchestrator Endpoint

If using the orchestrator pattern:

1. **Basic Configuration**:
   - **Name**: `parakeet-orchestrator`
   - **Container Image**: `your-username/parakeet-orchestrator:latest`
   - **GPU Type**: None needed (CPU only)
   - **Container Disk**: 2 GB

2. **Environment Variables**:
   ```
   DIARIZATION_ENDPOINT_ID=your_diarization_endpoint_id
   TRANSCRIPTION_ENDPOINT_ID=your_transcription_endpoint_id
   RUNPOD_API_KEY=your_runpod_api_key
   ```

3. **Worker Settings**:
   - **Min Workers**: 0
   - **Max Workers**: 5-10 (lightweight, can handle more)
   - **Idle Timeout**: 5 seconds
   - **Max Execution Time**: 900 seconds

4. **Deploy**

## Usage Examples

### Option 1: Client-Side Orchestration (Python)

```python
import requests
import base64

DIARIZATION_ENDPOINT = "https://api.runpod.ai/v2/YOUR_DIAR_ID/runsync"
TRANSCRIPTION_ENDPOINT = "https://api.runpod.ai/v2/YOUR_TRANS_ID/runsync"
API_KEY = "your_api_key"

def transcribe_with_diarization(audio_url):
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {API_KEY}"
    }

    # Step 1: Get diarization
    diar_payload = {
        "input": {
            "audio": audio_url
        }
    }

    print("Getting speaker diarization...")
    diar_response = requests.post(DIARIZATION_ENDPOINT, json=diar_payload, headers=headers)
    diar_result = diar_response.json()

    if "output" not in diar_result:
        return {"error": "Diarization failed"}

    diarization = diar_result["output"]
    print(f"Found {diarization['num_speakers']} speakers")

    # Step 2: Get transcription with diarization
    trans_payload = {
        "input": {
            "audio": audio_url,
            "response_format": "verbose_json",
            "timestamps": True,
            "diarization_segments": diarization["segments"]
        }
    }

    print("Getting transcription...")
    trans_response = requests.post(TRANSCRIPTION_ENDPOINT, json=trans_payload, headers=headers)
    trans_result = trans_response.json()

    if "output" not in trans_result:
        return {"error": "Transcription failed"}

    return trans_result["output"]

# Use it
result = transcribe_with_diarization("https://example.com/audio.mp3")
print(result["text"])

# Print with speakers
for segment in result.get("segments", []):
    print(f"Speaker {segment['speaker']}: {segment['text']}")
```

### Option 2: Using the Orchestrator

```python
import requests

ORCHESTRATOR_ENDPOINT = "https://api.runpod.ai/v2/YOUR_ORCH_ID/runsync"
API_KEY = "your_api_key"

def transcribe_with_orchestrator(audio_url):
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {API_KEY}"
    }

    payload = {
        "input": {
            "audio": audio_url,
            "response_format": "verbose_json",
            "diarize": True,
            "timestamps": True
        }
    }

    response = requests.post(ORCHESTRATOR_ENDPOINT, json=payload, headers=headers)
    result = response.json()

    return result.get("output", result)

# Use it
result = transcribe_with_orchestrator("https://example.com/audio.mp3")
print(result["text"])
```

### Option 3: Transcription Only (Skip Diarization)

```python
import requests

TRANSCRIPTION_ENDPOINT = "https://api.runpod.ai/v2/YOUR_TRANS_ID/runsync"
API_KEY = "your_api_key"

def transcribe_only(audio_url):
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {API_KEY}"
    }

    payload = {
        "input": {
            "audio": audio_url,
            "response_format": "json",
            "timestamps": False
        }
    }

    response = requests.post(TRANSCRIPTION_ENDPOINT, json=payload, headers=headers)
    result = response.json()

    return result.get("output", result)

result = transcribe_only("https://example.com/audio.mp3")
print(result["text"])
```

## Performance Comparison

### Cold Start Times (First Request)

| Architecture | Diarization | Transcription | Total |
|--------------|-------------|---------------|-------|
| **Split (parallel)** | 5-10s | 5-10s | **10s** (parallel) |
| **Split (sequential)** | 5-10s | 5-10s | **15-20s** |
| **Orchestrator** | 5-10s | 5-10s | **15-20s** |
| **Single (both cached)** | N/A | N/A | 60-120s (1 not cached) |
| **Single (1 cached)** | N/A | N/A | 30-60s |

### Cost Comparison (per minute of audio)

| Architecture | GPU Time | Approx Cost |
|--------------|----------|-------------|
| **Split (RTX 3090)** | 10-15s | $0.002-0.003 |
| **Split (A4000)** | 10-15s | $0.003-0.005 |
| **Single (RTX 3090)** | 12-18s | $0.002-0.004 |

Note: Split architecture slightly more expensive due to separate calls, but faster cold starts save money overall.

## When to Use Each Architecture

### Use Split Architecture When:
- ✅ Cold start time is critical (<10s required)
- ✅ You have variable load (need independent scaling)
- ✅ You want to use transcription without diarization sometimes
- ✅ Both models need to be cached for best performance

### Use Orchestrator When:
- ✅ You want split benefits with simple client code
- ✅ You always need both diarization and transcription
- ✅ You're okay with sequential execution

### Use Single Endpoint When:
- ✅ Simple deployment is more important than cold start time
- ✅ You have low volume (<10 requests/day)
- ✅ You keep Min Workers > 0 (workers stay warm)
- ✅ Cold starts of 30-60s are acceptable

## Cost Optimization Tips

1. **Parallel Execution**: Call both endpoints simultaneously for 50% faster results
2. **Skip When Not Needed**: Only call diarization if you need speaker labels
3. **Right-Size GPUs**:
   - Diarization: RTX 3090 sufficient for most workloads
   - Transcription: RTX 3090 for <10min audio, A4000+ for longer
4. **Adjust Idle Timeout**: Balance between responsiveness and idle costs
5. **Monitor Usage**: Track which endpoint gets more load and scale accordingly

## Monitoring

Track these metrics for each endpoint:
- Cold start frequency
- Average execution time
- GPU utilization
- Cost per request
- Error rate

Adjust Min/Max Workers based on actual usage patterns.

## Troubleshooting

### "Model not loaded yet"
- Wait 5-10 seconds on first request
- Verify Model field is set in endpoint configuration

### High latency
- Check if calling endpoints sequentially (switch to parallel)
- Verify both models are cached via Model Store
- Consider increasing Min Workers to keep warm

### Diarization fails
- Ensure HUGGINGFACE_ACCESS_TOKEN is set
- Verify you accepted terms for pyannote/speaker-diarization-3.1
- Check audio format is supported (WAV, MP3, etc.)

### Orchestrator timeout
- Increase Max Execution Time for orchestrator endpoint
- Check that child endpoints are responding
- Verify RUNPOD_API_KEY is valid

## Next Steps

1. Deploy both diarization and transcription endpoints
2. Test individually to verify Model Store is working
3. Implement client-side orchestration or deploy orchestrator
4. Monitor performance and adjust scaling settings
5. Optimize costs based on usage patterns

## Resources

- [RunPod Model Store Docs](https://docs.runpod.io/serverless/endpoints/model-caching)
- [Parakeet Model](https://huggingface.co/nvidia/parakeet-tdt-0.6b-v2)
- [Pyannote Diarization](https://huggingface.co/pyannote/speaker-diarization-3.1)
