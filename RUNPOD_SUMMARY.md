# RunPod Serverless - Complete Summary

Complete overview of RunPod deployment options for the Parakeet Transcription Service.

## What's Been Created

### Handlers (Python Files)
1. **runpod_handler.py** - Single endpoint with both models
2. **runpod_handler_diarization.py** - Diarization only
3. **runpod_handler_transcription.py** - Transcription only
4. **runpod_handler_orchestrator.py** - Orchestrates split endpoints

### Dockerfiles
1. **Dockerfile** - Single endpoint (original)
2. **Dockerfile.diarization** - Diarization only
3. **Dockerfile.transcription** - Transcription only
4. **Dockerfile.orchestrator** - Lightweight orchestrator

### Documentation
1. **QUICK_START_RUNPOD.md** - 5-minute deployment guide
2. **RUNPOD_DEPLOYMENT.md** - Comprehensive single endpoint guide
3. **SPLIT_ARCHITECTURE.md** - Detailed split deployment guide
4. **DEPLOYMENT_COMPARISON.md** - Architecture comparison
5. **RUNPOD_SUMMARY.md** - This file

## Three Deployment Architectures

### 1. Single Endpoint (Simplest)

**What**: One endpoint with both transcription and diarization

**Files Needed**:
- `Dockerfile`
- `runpod_handler.py`

**Deployment**:
```bash
docker build -t parakeet:latest .
docker push parakeet:latest
# Create 1 endpoint with Model Store: nvidia/parakeet-tdt-0.6b-v2
```

**Performance**:
- Cold start: 30-60s (diarization model not cached)
- Warm request: <5s
- Cost: ~$0.002-0.004/min of audio

**Best For**: Testing, low volume, simple deployment

---

### 2. Split Architecture (Best Performance)

**What**: Separate endpoints for diarization and transcription

**Files Needed**:
- `Dockerfile.diarization` + `runpod_handler_diarization.py`
- `Dockerfile.transcription` + `runpod_handler_transcription.py`

**Deployment**:
```bash
docker build -f Dockerfile.diarization -t parakeet-diar:latest .
docker build -f Dockerfile.transcription -t parakeet-trans:latest .
docker push parakeet-diar:latest
docker push parakeet-trans:latest
# Create 2 endpoints:
# - Diarization: pyannote/speaker-diarization-3.1
# - Transcription: nvidia/parakeet-tdt-0.6b-v2
```

**Performance**:
- Cold start: 5-10s each (both models cached!)
- Parallel execution: 10s total
- Sequential execution: 15-20s total
- Cost: ~$0.002-0.003/min of audio

**Best For**: Production, high volume, need fast cold starts

---

### 3. Orchestrator (Simple Client)

**What**: Split architecture + orchestrator endpoint for simple client integration

**Files Needed**:
- Everything from Split Architecture, plus:
- `Dockerfile.orchestrator` + `runpod_handler_orchestrator.py`

**Deployment**:
```bash
# Build split endpoints (as above) PLUS:
docker build -f Dockerfile.orchestrator -t parakeet-orch:latest .
docker push parakeet-orch:latest
# Create 3 endpoints total
```

**Performance**:
- Cold start: 15-20s (sequential calls)
- Warm request: <8s
- Cost: ~$0.003-0.005/min of audio

**Best For**: Production with simple client, centralized logic

## Key Benefits of Model Store

RunPod's Model Store (Beta) pre-caches HuggingFace models on host machines:

| Without Model Store | With Model Store |
|---------------------|------------------|
| Download model each cold start | Model already on host |
| 60-120 second cold starts | 5-10 second cold starts |
| Pay for download time | No download billing |
| Larger Docker images | Smaller images |

**Limitation**: Only **one model per endpoint** - that's why split architecture is powerful!

## Quick Decision Guide

```
┌─ Need <10 second cold starts?
│  ├─ NO → Single Endpoint
│  └─ YES → Continue...
│
├─ High volume (>100 req/day)?
│  ├─ NO → Single Endpoint (keep 1 worker warm)
│  └─ YES → Continue...
│
├─ Need simple client code?
│  ├─ YES → Orchestrator
│  └─ NO → Split Architecture
```

## Cost Comparison (2 min audio, RTX 3090)

| Architecture | GPU Time | Cost/Request |
|--------------|----------|--------------|
| Single | 8-13s | $0.0027-0.0044 |
| Split (parallel) | 8-13s | $0.0027-0.0044 |
| Split (sequential) | 8-13s | $0.0027-0.0044 |
| Orchestrator | 8-13s + CPU | $0.0028-0.0045 |

**Note**: Similar costs, but split architecture has much faster cold starts and better scaling.

## Setup Steps

### For Single Endpoint (5 minutes)

1. Build and push Docker image
2. Create RunPod endpoint
3. Set Model Store: `nvidia/parakeet-tdt-0.6b-v2`
4. Set env var: `HUGGINGFACE_ACCESS_TOKEN`
5. Deploy

See: [QUICK_START_RUNPOD.md](QUICK_START_RUNPOD.md)

### For Split Architecture (15 minutes)

1. Build and push 2 Docker images
2. Create diarization endpoint
   - Set Model Store: `pyannote/speaker-diarization-3.1`
   - Set env var: `HUGGINGFACE_ACCESS_TOKEN`
3. Create transcription endpoint
   - Set Model Store: `nvidia/parakeet-tdt-0.6b-v2`
4. Call both from your client (examples provided)

See: [SPLIT_ARCHITECTURE.md](SPLIT_ARCHITECTURE.md)

### For Orchestrator (20 minutes)

1. Complete split architecture setup (above)
2. Build and push orchestrator image
3. Create orchestrator endpoint (CPU only, no Model Store)
4. Set env vars:
   - `DIARIZATION_ENDPOINT_ID`
   - `TRANSCRIPTION_ENDPOINT_ID`
   - `RUNPOD_API_KEY`
5. Call orchestrator from your client

See: [SPLIT_ARCHITECTURE.md](SPLIT_ARCHITECTURE.md)

## API Examples

### Single Endpoint
```python
import requests

response = requests.post(
    "https://api.runpod.ai/v2/YOUR_ENDPOINT/runsync",
    headers={"Authorization": "Bearer YOUR_KEY"},
    json={
        "input": {
            "audio": "https://example.com/audio.mp3",
            "diarize": True,
            "response_format": "json"
        }
    }
)
result = response.json()["output"]
```

### Split Architecture (Client Orchestration)
```python
import requests

headers = {"Authorization": "Bearer YOUR_KEY"}

# Call both in parallel
diar = requests.post(DIAR_ENDPOINT, headers=headers,
    json={"input": {"audio": "https://example.com/audio.mp3"}})

trans = requests.post(TRANS_ENDPOINT, headers=headers,
    json={"input": {
        "audio": "https://example.com/audio.mp3",
        "diarization_segments": diar.json()["output"]["segments"]
    }})

result = trans.json()["output"]
```

### Orchestrator
```python
import requests

response = requests.post(
    "https://api.runpod.ai/v2/YOUR_ORCH_ENDPOINT/runsync",
    headers={"Authorization": "Bearer YOUR_KEY"},
    json={
        "input": {
            "audio": "https://example.com/audio.mp3",
            "diarize": True,
            "response_format": "json"
        }
    }
)
result = response.json()["output"]
```

## File Reference

### Use Single Endpoint
- `Dockerfile`
- `runpod_handler.py`
- Documentation: `QUICK_START_RUNPOD.md`, `RUNPOD_DEPLOYMENT.md`

### Use Split Architecture
- `Dockerfile.diarization`
- `Dockerfile.transcription`
- `runpod_handler_diarization.py`
- `runpod_handler_transcription.py`
- Documentation: `SPLIT_ARCHITECTURE.md`

### Use Orchestrator
- All split architecture files, plus:
- `Dockerfile.orchestrator`
- `runpod_handler_orchestrator.py`
- Documentation: `SPLIT_ARCHITECTURE.md`

### Reference
- `DEPLOYMENT_COMPARISON.md` - Detailed comparison of all options
- `.dockerignore` - Files to exclude from builds

## Common Questions

**Q: Which architecture should I use?**
A: For production → Split Architecture. For testing → Single Endpoint.

**Q: Can I cache both models with single endpoint?**
A: No, Model Store is limited to 1 model per endpoint. That's why split architecture exists.

**Q: Is split architecture more expensive?**
A: No, similar costs but much faster cold starts and better scaling.

**Q: Do I need the orchestrator?**
A: No, it's optional. Use if you want simple client code. Otherwise, orchestrate from your application.

**Q: Can I skip diarization?**
A: Yes! With split architecture, just call transcription endpoint. With single/orchestrator, set `diarize: false`.

**Q: How do I update models?**
A: Change Model Store field in endpoint settings. For split architecture, update each endpoint independently.

**Q: What GPU should I use?**
A: RTX 3090 for most workloads. A4000+ for long audio or high concurrency.

## Monitoring & Scaling

Track these metrics:
- Cold start frequency
- Average execution time
- GPU utilization
- Cost per request
- Error rate

Adjust Min/Max Workers based on usage patterns.

## Next Steps

1. **Choose architecture** using [DEPLOYMENT_COMPARISON.md](DEPLOYMENT_COMPARISON.md)
2. **Deploy** using the appropriate guide
3. **Test** with sample audio
4. **Monitor** performance
5. **Optimize** scaling settings
6. **Scale** as needed

## Getting Help

- Check documentation files for detailed guides
- Review example code in handlers
- Test locally before deploying to RunPod
- Monitor RunPod logs for debugging

## Summary Table

| Aspect | Single | Split | Orchestrator |
|--------|--------|-------|--------------|
| **Endpoints** | 1 | 2 | 3 |
| **Dockerfiles** | 1 | 2 | 3 |
| **Cold Start** | 30-60s | 5-10s | 15-20s |
| **Complexity** | Low | Medium | Medium |
| **Client Code** | Simple | Medium | Simple |
| **Cost** | $ | $ | $ |
| **Scalability** | Good | Best | Best |
| **Best Use** | Testing | Production | Simple API |

Choose based on your requirements and see the linked documentation for detailed setup instructions!
