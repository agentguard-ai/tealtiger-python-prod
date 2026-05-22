# TealTiger Python SDK - Docker Guide

This guide covers how to use TealTiger Python SDK with Docker.

## Quick Start

### Pull and Run

```bash
# Pull the latest image
docker pull ghcr.io/tealtiger/python-sdk:latest

# Run interactively
docker run -it --rm \
  -e OPENAI_API_KEY=your-key \
  ghcr.io/tealtiger/python-sdk:latest \
  python
```

### Run Examples

```bash
# Run a specific example
docker run --rm \
  -e OPENAI_API_KEY=your-key \
  ghcr.io/tealtiger/python-sdk:latest \
  python /app/examples/gemini_basic.py
```

## Available Images

### Production (Slim)
- **Image:** `ghcr.io/tealtiger/python-sdk:latest`
- **Size:** ~200MB
- **Use:** Production deployments
- **Includes:** TealTiger SDK, examples

### Development
- **Image:** `ghcr.io/tealtiger/python-sdk:dev`
- **Size:** ~400MB
- **Use:** Development and testing
- **Includes:** SDK + dev tools (pytest, mypy, black)

### Alpine (Minimal)
- **Image:** `ghcr.io/tealtiger/python-sdk:alpine`
- **Size:** ~150MB
- **Use:** Minimal deployments
- **Includes:** TealTiger SDK on Alpine Linux

### Jupyter Notebook
- **Image:** `ghcr.io/tealtiger/python-sdk:jupyter`
- **Size:** ~600MB
- **Use:** Interactive experimentation
- **Includes:** SDK + Jupyter Lab



## Usage Examples

### Interactive Python Shell

```bash
docker run -it --rm \
  -e OPENAI_API_KEY=sk-xxx \
  ghcr.io/tealtiger/python-sdk:latest \
  python

# In Python:
>>> from tealtiger import TealOpenAI
>>> client = TealOpenAI(api_key="sk-xxx")
>>> # Start using TealTiger!
```

### Mount Your Code

```bash
# Mount current directory
docker run --rm \
  -v $(pwd):/workspace \
  -w /workspace \
  -e OPENAI_API_KEY=sk-xxx \
  ghcr.io/tealtiger/python-sdk:latest \
  python my_script.py
```

### Jupyter Notebook

```bash
# Start Jupyter Lab
docker run -p 8888:8888 \
  -e OPENAI_API_KEY=sk-xxx \
  -v $(pwd)/notebooks:/app/notebooks \
  ghcr.io/tealtiger/python-sdk:jupyter

# Open browser to http://localhost:8888
```

### Development Environment

```bash
# Start dev container with bash
docker run -it --rm \
  -v $(pwd):/app \
  -e OPENAI_API_KEY=sk-xxx \
  ghcr.io/tealtiger/python-sdk:dev \
  bash

# Inside container:
$ pytest tests/
$ black src/
$ mypy src/
```

## Docker Compose

Create `docker-compose.yml`:

```yaml
version: '3.8'

services:
  tealtiger:
    image: ghcr.io/tealtiger/python-sdk:latest
    environment:
      - OPENAI_API_KEY=${OPENAI_API_KEY}
    volumes:
      - ./workspace:/workspace
    working_dir: /workspace
```

Run with:
```bash
docker-compose run tealtiger python my_script.py
```



## CI/CD Integration

### GitHub Actions

```yaml
jobs:
  test:
    runs-on: ubuntu-latest
    container:
      image: ghcr.io/tealtiger/python-sdk:latest
    steps:
      - uses: actions/checkout@v3
      - run: python -m pytest tests/
```

### GitLab CI

```yaml
test:
  image: ghcr.io/tealtiger/python-sdk:latest
  script:
    - python -m pytest tests/
```

## Building Locally

### Build Production Image

```bash
cd packages/tealtiger-python
docker build -t tealtiger/python-sdk:latest .
```

### Build All Variants

```bash
# Production
docker build -t tealtiger/python-sdk:latest -f Dockerfile .

# Development
docker build -t tealtiger/python-sdk:dev -f Dockerfile.dev .

# Alpine
docker build -t tealtiger/python-sdk:alpine -f Dockerfile.alpine .

# Jupyter
docker build -t tealtiger/python-sdk:jupyter -f Dockerfile.jupyter .
```

### Using Docker Compose

```bash
# Build all images
docker-compose build

# Run specific service
docker-compose run tealtiger-python python
docker-compose run tealtiger-python-dev bash
docker-compose up tealtiger-jupyter
```

## Environment Variables

| Variable | Description | Required |
|----------|-------------|----------|
| `OPENAI_API_KEY` | OpenAI API key | For OpenAI |
| `ANTHROPIC_API_KEY` | Anthropic API key | For Anthropic |
| `GOOGLE_API_KEY` | Google Gemini API key | For Gemini |
| `AWS_ACCESS_KEY_ID` | AWS access key | For Bedrock |
| `AWS_SECRET_ACCESS_KEY` | AWS secret key | For Bedrock |
| `COHERE_API_KEY` | Cohere API key | For Cohere |
| `MISTRAL_API_KEY` | Mistral API key | For Mistral |



## Security Best Practices

### Non-Root User

All images run as non-root user `tealtiger` (UID 1000) for security.

### Resource Limits

```bash
# Limit CPU and memory
docker run --rm \
  --cpus="0.5" \
  --memory="512m" \
  -e OPENAI_API_KEY=sk-xxx \
  ghcr.io/tealtiger/python-sdk:latest \
  python my_script.py
```

### Read-Only Filesystem

```bash
# Run with read-only filesystem
docker run --rm \
  --read-only \
  --tmpfs /tmp:size=100M \
  -e OPENAI_API_KEY=sk-xxx \
  ghcr.io/tealtiger/python-sdk:latest \
  python my_script.py
```

## Troubleshooting

### Image Pull Fails

```bash
# Try Docker Hub instead of GHCR
docker pull docker.io/tealtiger/python-sdk:latest
```

### Permission Denied

```bash
# Run as current user
docker run --rm \
  --user $(id -u):$(id -g) \
  -v $(pwd):/workspace \
  ghcr.io/tealtiger/python-sdk:latest \
  python my_script.py
```

### Import Errors

```bash
# Verify installation
docker run --rm ghcr.io/tealtiger/python-sdk:latest \
  python -c "import tealtiger; print(tealtiger.__version__)"
```

## Support

- **Documentation:** https://github.com/agentguard-ai/tealtiger-python-prod
- **Issues:** https://github.com/agentguard-ai/tealtiger-python-prod/issues
- **Docker Hub:** https://hub.docker.com/r/tealtiger/python-sdk
- **GHCR:** https://github.com/orgs/tealtiger/packages

---

**Last Updated:** March 6, 2026  
**Version:** 1.0.0
