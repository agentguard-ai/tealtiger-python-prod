#!/bin/bash
# Test script for TealTiger Python SDK Docker images

set -e

echo "🐳 Testing TealTiger Python SDK Docker Images"
echo "=============================================="

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Test function
test_image() {
    local variant=$1
    local dockerfile=$2
    
    echo ""
    echo "Testing $variant variant..."
    
    # Build image
    echo "  Building image..."
    docker build -t tealtiger/python-sdk:test-$variant -f $dockerfile . > /dev/null 2>&1
    
    if [ $? -eq 0 ]; then
        echo -e "  ${GREEN}✓${NC} Build successful"
    else
        echo -e "  ${RED}✗${NC} Build failed"
        return 1
    fi
    
    # Test import
    echo "  Testing imports..."
    docker run --rm tealtiger/python-sdk:test-$variant \
        python -c "import tealtiger; from tealtiger import TealOpenAI, GuardrailEngine; print('OK')" > /dev/null 2>&1
    
    if [ $? -eq 0 ]; then
        echo -e "  ${GREEN}✓${NC} Imports successful"
    else
        echo -e "  ${RED}✗${NC} Import failed"
        return 1
    fi
    
    # Check image size
    local size=$(docker images tealtiger/python-sdk:test-$variant --format "{{.Size}}")
    echo "  Image size: $size"
    
    # Cleanup
    docker rmi tealtiger/python-sdk:test-$variant > /dev/null 2>&1
    
    echo -e "  ${GREEN}✓${NC} $variant variant passed all tests"
}

# Run tests
test_image "production" "Dockerfile"
test_image "dev" "Dockerfile.dev"
test_image "alpine" "Dockerfile.alpine"
test_image "jupyter" "Dockerfile.jupyter"

echo ""
echo -e "${GREEN}✓${NC} All Docker images tested successfully!"
echo ""
echo "Next steps:"
echo "  1. Push images to registry: docker-compose push"
echo "  2. Test with examples: docker run tealtiger/python-sdk:latest python /app/examples/gemini_basic.py"
echo "  3. See DOCKER.md for more usage examples"
