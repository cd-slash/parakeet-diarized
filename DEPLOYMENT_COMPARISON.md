# RunPod Deployment Options Comparison

Quick reference guide to help you choose the right deployment architecture.

## Overview

This project can be deployed in three different ways on RunPod:

1. **Single Endpoint** - One endpoint with both models
2. **Split Architecture** - Separate diarization and transcription endpoints
3. **Orchestrator** - Lightweight coordinator calling split endpoints

## Quick Comparison

| Feature | Single Endpoint | Split Architecture | Orchestrator |
|---------|----------------|-------------------|--------------|
| **Endpoints to Deploy** | 1 | 2 | 3 |
| **Cached Models** | 1 (Parakeet) | 2 (both) | 2 (both) |
| **Cold Start Time** | 30-60s | 5-10s each | 15-20s total |
| **Setup Complexity** | Simple | Medium | Medium |
| **Client Complexity** | Simple | Medium | Simple |
| **Deployment Time** | 5 min | 15 min | 20 min |
| **Best For** | Low volume | Production | Easy integration |

## Detailed Comparison

### Single Endpoint

**Files**:
- `Dockerfile` + `runpod_handler.py`

**Deployment**:
```bash
docker build -t parakeet-transcription .
# Deploy 1 endpoint with Model Store: nvidia/parakeet-tdt-0.6b-v2
```

**Pros**:
- ✅ Simplest deployment (1 endpoint)
- ✅ Simple client code (1 API call)
- ✅ Easy to manage and monitor
- ✅ Good for testing/development

**Cons**:
- ❌ Only 1 model cached (Parakeet)
- ❌ Diarization model downloaded on each cold start (~30-60s)
- ❌ Larger memory footprint per worker
- ❌ Can't scale diarization independently

**When to Use**:
- Low volume (<10 requests/day)
- Cold starts acceptable (30-60s)
- Simple deployment preferred
- Testing and development

**Cost**: ~$0.002-0.004 per minute of audio

---

### Split Architecture

**Files**:
- `Dockerfile.diarization` + `runpod_handler_diarization.py`
- `Dockerfile.transcription` + `runpod_handler_transcription.py`

**Deployment**:
```bash
docker build -f Dockerfile.diarization -t parakeet-diarization .
docker build -f Dockerfile.transcription -t parakeet-transcription .
# Deploy 2 endpoints with Model Store:
# - Endpoint 1: pyannote/speaker-diarization-3.1
# - Endpoint 2: nvidia/parakeet-tdt-0.6b-v2
```

**Pros**:
- ✅ Both models cached (5-10s cold starts each)
- ✅ Independent scaling (optimize each separately)
- ✅ Smaller workers (less GPU memory)
- ✅ Can skip diarization when not needed
- ✅ Best performance and cost for high volume

**Cons**:
- ❌ More endpoints to manage
- ❌ Client handles orchestration
- ❌ Audio sent twice (or stored centrally)
- ❌ More complex deployment

**When to Use**:
- Production workloads
- Cold starts critical (<10s required)
- Variable load patterns
- Need to scale diarization independently
- High volume (>100 requests/day)

**Cost**: ~$0.002-0.003 per minute of audio

---

### Orchestrator

**Files**:
- `Dockerfile.diarization` + `runpod_handler_diarization.py`
- `Dockerfile.transcription` + `runpod_handler_transcription.py`
- `Dockerfile.orchestrator` + `runpod_handler_orchestrator.py`

**Deployment**:
```bash
docker build -f Dockerfile.diarization -t parakeet-diarization .
docker build -f Dockerfile.transcription -t parakeet-transcription .
docker build -f Dockerfile.orchestrator -t parakeet-orchestrator .
# Deploy 3 endpoints (2 with Model Store + 1 orchestrator)
```

**Pros**:
- ✅ Both models cached (5-10s each)
- ✅ Simple client code (1 API call)
- ✅ All benefits of split architecture
- ✅ Easy to add logic/caching/retry in orchestrator

**Cons**:
- ❌ Most complex deployment (3 endpoints)
- ❌ Sequential execution (15-20s cold start)
- ❌ Extra orchestrator costs (minimal, CPU-only)
- ❌ Another point of failure

**When to Use**:
- Want split benefits with simple client
- Need centralized logic/caching
- Always need both diarization + transcription
- Okay with sequential execution

**Cost**: ~$0.003-0.005 per minute of audio (includes orchestrator)

## Cold Start Performance

```
Single Endpoint:
├─ Worker starts: 2-5s
├─ Load Parakeet (cached): 3-5s
├─ Download Pyannote: 20-40s  ⚠️
└─ Total: 30-60s

Split Architecture (parallel):
├─ Diarization worker: 2-5s
│  └─ Load Pyannote (cached): 3-5s
├─ Transcription worker: 2-5s
│  └─ Load Parakeet (cached): 3-5s
└─ Total: 10s (parallel) ✅

Orchestrator (sequential):
├─ Orchestrator starts: 1-2s
├─ Call diarization: 5-10s
├─ Call transcription: 5-10s
└─ Total: 15-20s
```

## Cost Analysis

### Per Request Cost Breakdown

**Assumptions**:
- 2 minute audio file
- RTX 3090 GPU ($0.00034/sec)

**Single Endpoint**:
- Diarization: 5-8 seconds = $0.0017-0.0027
- Transcription: 3-5 seconds = $0.0010-0.0017
- **Total**: $0.0027-0.0044 per request

**Split Architecture** (parallel):
- Diarization endpoint: 5-8 seconds = $0.0017-0.0027
- Transcription endpoint: 3-5 seconds = $0.0010-0.0017
- **Total**: $0.0027-0.0044 per request (same as single)

**Split Architecture** (sequential):
- Same costs but slower by 50%

**Orchestrator**:
- Diarization: 5-8 seconds = $0.0017-0.0027
- Transcription: 3-5 seconds = $0.0010-0.0017
- Orchestrator: <1 second CPU = $0.0001
- **Total**: $0.0028-0.0045 per request

### Monthly Cost Estimate

| Volume | Single | Split (parallel) | Split (sequential) | Orchestrator |
|--------|--------|------------------|-------------------|--------------|
| 100 requests/mo | $0.27-0.44 | $0.27-0.44 | $0.27-0.44 | $0.28-0.45 |
| 1,000 requests/mo | $2.70-4.40 | $2.70-4.40 | $2.70-4.40 | $2.80-4.50 |
| 10,000 requests/mo | $27-44 | $27-44 | $27-44 | $28-45 |

**Note**: Split architecture saves money on cold starts by eliminating model download billing.

## Recommendations

### For Development/Testing
→ **Single Endpoint**
- Simplest to set up and test
- Good enough for low volume
- Easy to debug

### For Production (Low-Medium Volume)
→ **Single Endpoint with Min Workers > 0**
- Keep 1-2 workers warm to avoid cold starts
- Simpler than split architecture
- Acceptable costs at low-medium volume

### For Production (High Volume)
→ **Split Architecture with Client Orchestration**
- Best cold start performance
- Independent scaling
- Most cost-effective at scale
- Call endpoints in parallel

### For Production (Need Simple Client)
→ **Orchestrator**
- Single API call from client
- Both models cached
- Easy to maintain

## Migration Path

Start simple, scale as needed:

1. **Start**: Single Endpoint
   - Test functionality
   - Understand your usage patterns

2. **Optimize**: Add Model Store
   - Cache Parakeet model
   - Reduces cold starts to 30-60s

3. **Scale**: Split Architecture
   - Deploy when volume increases
   - Cache both models
   - Get <10s cold starts

4. **Simplify**: Add Orchestrator
   - If client orchestration is complex
   - Centralize logic

## Decision Tree

```
Need <10s cold starts?
├─ No → Single Endpoint
└─ Yes → Cache both models?
    ├─ No → Single Endpoint (1 cached)
    └─ Yes → Need simple client?
        ├─ Yes → Orchestrator
        └─ No → Split Architecture
```

## Quick Start Commands

### Single Endpoint
```bash
docker build -t you/parakeet:latest .
docker push you/parakeet:latest
# Deploy 1 endpoint
# Model Store: nvidia/parakeet-tdt-0.6b-v2
```

### Split Architecture
```bash
docker build -f Dockerfile.diarization -t you/parakeet-diar:latest .
docker build -f Dockerfile.transcription -t you/parakeet-trans:latest .
docker push you/parakeet-diar:latest
docker push you/parakeet-trans:latest
# Deploy 2 endpoints
# Diar Model Store: pyannote/speaker-diarization-3.1
# Trans Model Store: nvidia/parakeet-tdt-0.6b-v2
```

### With Orchestrator
```bash
# Build all three
docker build -f Dockerfile.diarization -t you/parakeet-diar:latest .
docker build -f Dockerfile.transcription -t you/parakeet-trans:latest .
docker build -f Dockerfile.orchestrator -t you/parakeet-orch:latest .
docker push you/parakeet-diar:latest
docker push you/parakeet-trans:latest
docker push you/parakeet-orch:latest
# Deploy 3 endpoints
```

## Documentation Links

- **Single Endpoint**: See [RUNPOD_DEPLOYMENT.md](RUNPOD_DEPLOYMENT.md)
- **Split Architecture**: See [SPLIT_ARCHITECTURE.md](SPLIT_ARCHITECTURE.md)
- **Quick Start**: See [QUICK_START_RUNPOD.md](QUICK_START_RUNPOD.md)
