# RunPod Serverless Dockerfile for Parakeet Transcription Service
# This Dockerfile creates an optimized image for GPU-accelerated audio transcription
# with NVIDIA Parakeet-TDT and Pyannote speaker diarization

FROM nvidia/cuda:12.1.0-cudnn8-runtime-ubuntu22.04

# Set environment variables
ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    CUDA_HOME=/usr/local/cuda \
    PATH=/usr/local/cuda/bin:$PATH \
    LD_LIBRARY_PATH=/usr/local/cuda/lib64:$LD_LIBRARY_PATH \
    HF_HOME=/runpod-volume/huggingface-cache \
    HUGGINGFACE_HUB_CACHE=/runpod-volume/huggingface-cache/hub \
    TRANSFORMERS_CACHE=/runpod-volume/huggingface-cache/hub \
    TORCH_HOME=/runpod-volume/torch-cache

# Install system dependencies
RUN apt-get update && apt-get install -y \
    python3.10 \
    python3.10-dev \
    python3-pip \
    git \
    ffmpeg \
    libsndfile1 \
    libsndfile1-dev \
    sox \
    libsox-dev \
    wget \
    curl \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Create symbolic link for python
RUN ln -sf /usr/bin/python3.10 /usr/bin/python

# Upgrade pip
RUN python -m pip install --upgrade pip setuptools wheel

# Set working directory
WORKDIR /app

# Copy requirements file first for better caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Install RunPod SDK and requests (for downloading audio from URLs)
RUN pip install --no-cache-dir runpod requests

# Copy application code
COPY *.py ./
COPY diarization/ ./diarization/

# Create directories for temporary files and model cache
RUN mkdir -p /tmp/parakeet /root/.cache/huggingface /root/.cache/torch

# OPTION 1: Use RunPod Model Store (Recommended)
# When using RunPod's Model Store, models are pre-cached at /runpod-volume/huggingface-cache/hub/
# Configure your RunPod endpoint with model: nvidia/parakeet-tdt-0.6b-v2
# This eliminates cold start time and reduces costs
# No need to pre-download the model in the Docker image!

# OPTION 2: Embed model in Docker image (Fallback)
# Uncomment the lines below to pre-download the model into the Docker image
# This increases image size but ensures the model is always available
# Use this if NOT using RunPod Model Store
# RUN python -c "from nemo.collections.asr.models import EncDecCTCModelBPE; \
#     print('Downloading Parakeet model...'); \
#     model = EncDecCTCModelBPE.from_pretrained('nvidia/parakeet-tdt-0.6b-v2'); \
#     print('Model downloaded successfully')"

# Note: Pyannote speaker diarization model requires HuggingFace token at runtime
# It cannot be pre-downloaded without accepting terms on HuggingFace
# For diarization: Set HUGGINGFACE_ACCESS_TOKEN environment variable when deploying
# If using gated models in Model Store, provide your HF token in endpoint configuration

# Set the entrypoint to the RunPod handler
CMD ["python", "-u", "runpod_handler.py"]
