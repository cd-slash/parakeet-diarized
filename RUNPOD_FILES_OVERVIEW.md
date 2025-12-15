# RunPod Files Overview

Quick reference guide to all RunPod-related files in this project.

## File Purpose

### Handler Files (Python)
| File | Purpose | Used In |
|------|---------|---------|
| `runpod_handler.py` | Single endpoint with both models | Single endpoint |
| `runpod_handler_diarization.py` | Diarization only | Split architecture |
| `runpod_handler_transcription.py` | Transcription only | Split architecture |
| `runpod_handler_orchestrator.py` | Orchestrates split endpoints | Orchestrator |

### Dockerfile Files
| File | Purpose | Size | GPU |
|------|---------|------|-----|
| `Dockerfile` | Single endpoint image | ~2GB | Yes |
| `Dockerfile.diarization` | Diarization only image | ~1.5GB | Yes |
| `Dockerfile.transcription` | Transcription only image | ~2GB | Yes |
| `Dockerfile.orchestrator` | Orchestrator image | ~200MB | No |

### Documentation Files
| File | What It Covers |
|------|----------------|
| `QUICK_START_RUNPOD.md` | 5-minute single endpoint deployment |
| `RUNPOD_DEPLOYMENT.md` | Comprehensive single endpoint guide |
| `SPLIT_ARCHITECTURE.md` | Split endpoint deployment guide |
| `DEPLOYMENT_COMPARISON.md` | Architecture comparison and decision guide |
| `RUNPOD_SUMMARY.md` | Complete overview of all options |
| `RUNPOD_FILES_OVERVIEW.md` | This file |

### Build Scripts
| File | Purpose |
|------|---------|
| `build-docker.sh` | Helper script to build and push Docker images |
| `.dockerignore` | Excludes unnecessary files from builds |

## Quick Architecture Guide

### Single Endpoint
```
Files needed:
├── Dockerfile
├── runpod_handler.py
└── All project files (*.py, diarization/)

Deploy:
1 endpoint with Model Store: nvidia/parakeet-tdt-0.6b-v2
```

### Split Architecture
```
Diarization endpoint:
├── Dockerfile.diarization
├── runpod_handler_diarization.py
├── audio.py
└── diarization/

Transcription endpoint:
├── Dockerfile.transcription
├── runpod_handler_transcription.py
├── audio.py
├── transcription.py
├── models.py
└── config.py

Deploy:
- Endpoint 1 with Model Store: pyannote/speaker-diarization-3.1
- Endpoint 2 with Model Store: nvidia/parakeet-tdt-0.6b-v2
```

### With Orchestrator
```
All split architecture files PLUS:
├── Dockerfile.orchestrator
└── runpod_handler_orchestrator.py

Deploy:
- Same 2 endpoints as split architecture
- Plus 1 orchestrator endpoint (no Model Store)
```

## Build Commands Reference

### Build Single Endpoint
```bash
docker build -t your-username/parakeet:latest .
docker push your-username/parakeet:latest
```

### Build Split Architecture
```bash
# Diarization
docker build -f Dockerfile.diarization -t your-username/parakeet-diar:latest .
docker push your-username/parakeet-diar:latest

# Transcription
docker build -f Dockerfile.transcription -t your-username/parakeet-trans:latest .
docker push your-username/parakeet-trans:latest
```

### Build All (Using Script)
```bash
./build-docker.sh --username your-username --all --push
```

## Handler API Reference

### Single Endpoint Input
```json
{
  "input": {
    "audio": "url or base64",
    "audio_format": "mp3",
    "language": "en",
    "response_format": "json",
    "timestamps": true,
    "diarize": true
  }
}
```

### Diarization Endpoint Input
```json
{
  "input": {
    "audio": "url or base64",
    "audio_format": "mp3",
    "num_speakers": 2
  }
}
```

### Diarization Output
```json
{
  "segments": [
    {"start": 0.0, "end": 2.5, "speaker": "1"}
  ],
  "num_speakers": 2,
  "duration": 10.5
}
```

### Transcription Endpoint Input
```json
{
  "input": {
    "audio": "url or base64",
    "audio_format": "mp3",
    "language": "en",
    "response_format": "json",
    "timestamps": true,
    "diarization_segments": [...]  // Optional, from diarization endpoint
  }
}
```

### Orchestrator Input
```json
{
  "input": {
    "audio": "url or base64",
    "audio_format": "mp3",
    "language": "en",
    "response_format": "json",
    "diarize": true,
    "timestamps": true
  }
}
```

## Environment Variables

### Single Endpoint
- `HUGGINGFACE_ACCESS_TOKEN` - Required for diarization
- `MODEL_ID` - Optional, defaults to nvidia/parakeet-tdt-0.6b-v2
- `CHUNK_DURATION` - Optional, defaults to 500 seconds
- `TEMP_DIR` - Optional, defaults to /tmp/parakeet

### Diarization Endpoint
- `HUGGINGFACE_ACCESS_TOKEN` - Required

### Transcription Endpoint
- `MODEL_ID` - Optional, defaults to nvidia/parakeet-tdt-0.6b-v2
- `CHUNK_DURATION` - Optional, defaults to 500 seconds

### Orchestrator
- `DIARIZATION_ENDPOINT_ID` - Required
- `TRANSCRIPTION_ENDPOINT_ID` - Required
- `RUNPOD_API_KEY` - Required

## Model Store Configuration

### Single Endpoint
```
Model: nvidia/parakeet-tdt-0.6b-v2
```

### Split Architecture - Diarization
```
Model: pyannote/speaker-diarization-3.1
```
Note: Requires HuggingFace token and accepting terms

### Split Architecture - Transcription
```
Model: nvidia/parakeet-tdt-0.6b-v2
```

### Orchestrator
```
No Model Store (CPU only)
```

## File Dependencies

### Diarization Handler Dependencies
- `audio.py` - Audio processing utilities
- `diarization/__init__.py` - Diarization logic

### Transcription Handler Dependencies
- `audio.py` - Audio processing utilities
- `transcription.py` - Transcription logic
- `models.py` - Data models
- `config.py` - Configuration

### Orchestrator Dependencies
- None (calls other endpoints via HTTP)

## Choosing Files for Your Deployment

### I want simplest deployment
→ Use: `Dockerfile` + `runpod_handler.py`
→ Docs: `QUICK_START_RUNPOD.md`

### I want best performance
→ Use: `Dockerfile.diarization` + `Dockerfile.transcription`
→ Plus: `runpod_handler_diarization.py` + `runpod_handler_transcription.py`
→ Docs: `SPLIT_ARCHITECTURE.md`

### I want best performance + simple client
→ Use: All split files + `Dockerfile.orchestrator` + `runpod_handler_orchestrator.py`
→ Docs: `SPLIT_ARCHITECTURE.md`

### I'm not sure
→ Read: `DEPLOYMENT_COMPARISON.md`

## Testing Locally

Before deploying to RunPod, test handlers locally:

```bash
# Install RunPod SDK
pip install runpod

# Test single endpoint
python runpod_handler.py

# Test diarization
python runpod_handler_diarization.py

# Test transcription
python runpod_handler_transcription.py

# Test orchestrator (requires endpoints deployed)
python runpod_handler_orchestrator.py
```

Note: Local testing requires GPU and dependencies installed.

## Common Issues

### "Cannot find module 'audio'"
→ Ensure `audio.py` is in the same directory
→ Check Dockerfile COPY commands include required files

### "HUGGINGFACE_ACCESS_TOKEN not set"
→ Set environment variable in RunPod endpoint configuration
→ Required for diarization

### "Model not found"
→ Verify Model Store field is set correctly
→ Check model ID matches HuggingFace repository

### Large Docker image size
→ Use split architecture for smaller images
→ Check .dockerignore is excluding unnecessary files

## Next Steps

1. Choose architecture using `DEPLOYMENT_COMPARISON.md`
2. Build Docker images using `build-docker.sh`
3. Deploy to RunPod using appropriate guide
4. Test with sample audio
5. Monitor and optimize

## Quick Links

- [Quick Start](QUICK_START_RUNPOD.md) - Single endpoint in 5 min
- [Full Guide](RUNPOD_DEPLOYMENT.md) - Comprehensive single endpoint
- [Split Guide](SPLIT_ARCHITECTURE.md) - Split architecture details
- [Comparison](DEPLOYMENT_COMPARISON.md) - Choose right option
- [Summary](RUNPOD_SUMMARY.md) - Complete overview
