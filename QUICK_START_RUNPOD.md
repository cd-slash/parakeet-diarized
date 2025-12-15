# Quick Start: Deploy to RunPod with Model Store

This is the fastest way to deploy the Parakeet transcription service on RunPod using the Model Store feature for near-instant cold starts.

## Prerequisites
- RunPod account ([sign up](https://runpod.io))
- Docker Hub account
- HuggingFace account with access token ([get token](https://huggingface.co/settings/tokens))

## Step 1: Build and Push Docker Image

```bash
# Build the image (optimized for Model Store)
docker build -t your-username/parakeet-transcription:latest .

# Push to Docker Hub
docker push your-username/parakeet-transcription:latest
```

The Dockerfile is already configured to use RunPod's Model Store by default.

## Step 2: Create RunPod Endpoint

1. Go to [RunPod Console](https://www.runpod.io/console/serverless) → Serverless
2. Click "New Endpoint"
3. Fill in the configuration:

### Basic Settings
- **Name**: `parakeet-transcription`
- **Container Image**: `your-username/parakeet-transcription:latest`
- **GPU Type**: RTX 3090, RTX 4090, A4000, or A5000
- **Container Disk**: 10 GB

### Model Store (IMPORTANT!)
- **Model**: `nvidia/parakeet-tdt-0.6b-v2`
- This pre-caches the model on host machines for instant cold starts

### Environment Variables
Add these:
```
HUGGINGFACE_ACCESS_TOKEN=your_hf_token_here
```

### Worker Settings
- **Min Workers**: 0
- **Max Workers**: 3
- **Idle Timeout**: 5 seconds
- **Max Execution Time**: 600 seconds

4. Click **Deploy**

## Step 3: Test Your Endpoint

Copy your endpoint ID and API key from the RunPod console, then test:

```bash
curl -X POST https://api.runpod.ai/v2/YOUR_ENDPOINT_ID/run \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -d '{
    "input": {
      "audio": "https://example.com/sample.mp3",
      "response_format": "json",
      "diarize": true,
      "timestamps": true
    }
  }'
```

## Expected Performance

With Model Store enabled:
- **Cold start**: 5-10 seconds
- **Warm request**: <3 seconds
- **Cost per minute of audio**: ~$0.001-0.003

## Troubleshooting

**"Model not loaded yet"**
- Wait 5-10 seconds after first request - model is being loaded

**Diarization not working**
- Check that `HUGGINGFACE_ACCESS_TOKEN` is set correctly
- Accept terms at: https://huggingface.co/pyannote/speaker-diarization-3.1

**Slow cold starts (>30 seconds)**
- Verify Model field is set to `nvidia/parakeet-tdt-0.6b-v2`
- Check RunPod logs to confirm model is being loaded from cache

## Next Steps

- See [RUNPOD_DEPLOYMENT.md](RUNPOD_DEPLOYMENT.md) for detailed documentation
- Check [README.md](README.md) for API usage and examples
- Monitor your endpoint in the RunPod console

## Cost Optimization

- Keep Min Workers at 0 to avoid idle costs
- Use RTX 3090 for best price/performance ratio
- Process audio in batches when possible
- Adjust Max Execution Time based on your longest audio files

## Production Checklist

- [ ] Model Store configured with `nvidia/parakeet-tdt-0.6b-v2`
- [ ] HuggingFace token set for diarization
- [ ] Max Workers set appropriately for load
- [ ] Monitoring/alerts configured
- [ ] Test with various audio formats and lengths
- [ ] Error handling implemented in your application
