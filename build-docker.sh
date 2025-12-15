#!/bin/bash
# Docker build script for RunPod deployment
# Usage: ./build-docker.sh [OPTIONS]

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Default values
DOCKER_USERNAME=""
TAG="latest"
BUILD_ALL=false
BUILD_SINGLE=false
BUILD_DIARIZATION=false
BUILD_TRANSCRIPTION=false
BUILD_ORCHESTRATOR=false
PUSH=false

# Function to display usage
usage() {
    echo "Usage: $0 [OPTIONS]"
    echo ""
    echo "Options:"
    echo "  -u, --username USERNAME    Docker Hub username (required)"
    echo "  -t, --tag TAG             Docker image tag (default: latest)"
    echo "  -a, --all                 Build all images"
    echo "  -s, --single              Build single endpoint image"
    echo "  -d, --diarization         Build diarization endpoint image"
    echo "  -r, --transcription       Build transcription endpoint image"
    echo "  -o, --orchestrator        Build orchestrator image"
    echo "  -p, --push                Push images to Docker Hub after building"
    echo "  -h, --help                Display this help message"
    echo ""
    echo "Examples:"
    echo "  $0 -u myusername -a -p              # Build and push all images"
    echo "  $0 -u myusername -s                 # Build single endpoint only"
    echo "  $0 -u myusername -d -r -p           # Build and push split architecture"
    exit 1
}

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        -u|--username)
            DOCKER_USERNAME="$2"
            shift 2
            ;;
        -t|--tag)
            TAG="$2"
            shift 2
            ;;
        -a|--all)
            BUILD_ALL=true
            shift
            ;;
        -s|--single)
            BUILD_SINGLE=true
            shift
            ;;
        -d|--diarization)
            BUILD_DIARIZATION=true
            shift
            ;;
        -r|--transcription)
            BUILD_TRANSCRIPTION=true
            shift
            ;;
        -o|--orchestrator)
            BUILD_ORCHESTRATOR=true
            shift
            ;;
        -p|--push)
            PUSH=true
            shift
            ;;
        -h|--help)
            usage
            ;;
        *)
            echo -e "${RED}Unknown option: $1${NC}"
            usage
            ;;
    esac
done

# Check if username is provided
if [ -z "$DOCKER_USERNAME" ]; then
    echo -e "${RED}Error: Docker username is required${NC}"
    usage
fi

# If --all is specified, enable all builds
if [ "$BUILD_ALL" = true ]; then
    BUILD_SINGLE=true
    BUILD_DIARIZATION=true
    BUILD_TRANSCRIPTION=true
    BUILD_ORCHESTRATOR=true
fi

# Check if at least one build option is selected
if [ "$BUILD_SINGLE" = false ] && [ "$BUILD_DIARIZATION" = false ] && [ "$BUILD_TRANSCRIPTION" = false ] && [ "$BUILD_ORCHESTRATOR" = false ]; then
    echo -e "${RED}Error: No build option selected${NC}"
    usage
fi

echo -e "${GREEN}Starting Docker builds...${NC}"
echo ""

# Build single endpoint
if [ "$BUILD_SINGLE" = true ]; then
    IMAGE_NAME="${DOCKER_USERNAME}/parakeet-transcription:${TAG}"
    echo -e "${YELLOW}Building single endpoint: ${IMAGE_NAME}${NC}"
    docker build -t "$IMAGE_NAME" -f Dockerfile .
    echo -e "${GREEN}✓ Single endpoint built successfully${NC}"

    if [ "$PUSH" = true ]; then
        echo -e "${YELLOW}Pushing ${IMAGE_NAME}...${NC}"
        docker push "$IMAGE_NAME"
        echo -e "${GREEN}✓ Pushed successfully${NC}"
    fi
    echo ""
fi

# Build diarization endpoint
if [ "$BUILD_DIARIZATION" = true ]; then
    IMAGE_NAME="${DOCKER_USERNAME}/parakeet-diarization:${TAG}"
    echo -e "${YELLOW}Building diarization endpoint: ${IMAGE_NAME}${NC}"
    docker build -t "$IMAGE_NAME" -f Dockerfile.diarization .
    echo -e "${GREEN}✓ Diarization endpoint built successfully${NC}"

    if [ "$PUSH" = true ]; then
        echo -e "${YELLOW}Pushing ${IMAGE_NAME}...${NC}"
        docker push "$IMAGE_NAME"
        echo -e "${GREEN}✓ Pushed successfully${NC}"
    fi
    echo ""
fi

# Build transcription endpoint
if [ "$BUILD_TRANSCRIPTION" = true ]; then
    IMAGE_NAME="${DOCKER_USERNAME}/parakeet-transcription-only:${TAG}"
    echo -e "${YELLOW}Building transcription endpoint: ${IMAGE_NAME}${NC}"
    docker build -t "$IMAGE_NAME" -f Dockerfile.transcription .
    echo -e "${GREEN}✓ Transcription endpoint built successfully${NC}"

    if [ "$PUSH" = true ]; then
        echo -e "${YELLOW}Pushing ${IMAGE_NAME}...${NC}"
        docker push "$IMAGE_NAME"
        echo -e "${GREEN}✓ Pushed successfully${NC}"
    fi
    echo ""
fi

# Build orchestrator
if [ "$BUILD_ORCHESTRATOR" = true ]; then
    IMAGE_NAME="${DOCKER_USERNAME}/parakeet-orchestrator:${TAG}"
    echo -e "${YELLOW}Building orchestrator: ${IMAGE_NAME}${NC}"
    docker build -t "$IMAGE_NAME" -f Dockerfile.orchestrator .
    echo -e "${GREEN}✓ Orchestrator built successfully${NC}"

    if [ "$PUSH" = true ]; then
        echo -e "${YELLOW}Pushing ${IMAGE_NAME}...${NC}"
        docker push "$IMAGE_NAME"
        echo -e "${GREEN}✓ Pushed successfully${NC}"
    fi
    echo ""
fi

echo -e "${GREEN}All builds completed successfully!${NC}"
echo ""

if [ "$PUSH" = false ]; then
    echo -e "${YELLOW}Images built but not pushed. Use -p flag to push to Docker Hub.${NC}"
fi

echo ""
echo "Next steps:"
if [ "$BUILD_SINGLE" = true ]; then
    echo "  - Single endpoint: Deploy ${DOCKER_USERNAME}/parakeet-transcription:${TAG}"
    echo "    Model Store: nvidia/parakeet-tdt-0.6b-v2"
fi
if [ "$BUILD_DIARIZATION" = true ] && [ "$BUILD_TRANSCRIPTION" = true ]; then
    echo "  - Split architecture:"
    echo "    1. Deploy ${DOCKER_USERNAME}/parakeet-diarization:${TAG}"
    echo "       Model Store: pyannote/speaker-diarization-3.1"
    echo "    2. Deploy ${DOCKER_USERNAME}/parakeet-transcription-only:${TAG}"
    echo "       Model Store: nvidia/parakeet-tdt-0.6b-v2"
fi
if [ "$BUILD_ORCHESTRATOR" = true ]; then
    echo "  - Orchestrator: Deploy ${DOCKER_USERNAME}/parakeet-orchestrator:${TAG}"
    echo "    (No Model Store needed - CPU only)"
fi
echo ""
echo "See RUNPOD_DEPLOYMENT.md and SPLIT_ARCHITECTURE.md for deployment instructions."
