# Clipper Academy API - Usage Guide

## Quick Start

### 1. First Time Setup
```bash
# Make the script executable (already done)
chmod +x run.sh

# Setup environment and install dependencies
./run.sh --setup
```

### 2. Configure API Keys
Edit the `.env` file created by setup:
```bash
# Edit .env file
vim .env
# or
nano .env
```

Set your API keys:
```env
OPENAI_API_KEY=your_openai_api_key_here
ZAPCAP_API_KEY=your_zapcap_api_key_here
```

### 3. Check Environment
```bash
# Verify everything is configured correctly
./run.sh --check
```

### 4. Run the API
```bash
# Development mode (default)
./run.sh

# Or with auto-reload for development
./run.sh --reload

# Production mode
./run.sh --env production
```

## Command Options

### Basic Usage
```bash
./run.sh [OPTIONS]
```

### Available Options
- `-e, --env ENV` - Environment (development|production|docker) [default: development]
- `-h, --host HOST` - Host to bind to [default: 0.0.0.0]
- `-p, --port PORT` - Port to listen on [default: 8000]
- `-w, --workers NUM` - Number of worker processes (production mode) [default: 4]
- `-r, --reload` - Enable auto-reload (development mode)
- `-d, --debug` - Enable debug mode
- `-c, --check` - Check dependencies and environment only
- `-s, --setup` - Setup environment and install dependencies
- `--help` - Show help message

## Common Commands

### Development
```bash
# Basic development server
./run.sh

# Development with auto-reload and debug
./run.sh --reload --debug

# Custom port
./run.sh --port 3000

# Check environment before running
./run.sh --check && ./run.sh
```

### Production
```bash
# Production mode with multiple workers
./run.sh --env production

# Production on custom port with more workers
./run.sh --env production --port 80 --workers 8

# Production with specific host
./run.sh --env production --host 192.168.1.100
```

### Troubleshooting
```bash
# Setup environment again
./run.sh --setup

# Check what's wrong
./run.sh --check

# Debug mode for detailed logs
./run.sh --debug

# Force reinstall dependencies
rm -rf venv && ./run.sh --setup
```

## Prerequisites

### System Requirements
- Python 3.8+
- FFmpeg and FFprobe
- yt-dlp

### macOS Installation
```bash
# Install Homebrew if not already installed
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# Install dependencies
brew install python ffmpeg yt-dlp
```

### Ubuntu/Debian Installation
```bash
sudo apt-get update
sudo apt-get install python3 python3-pip python3-venv ffmpeg
pip3 install yt-dlp
```

## Environment Variables

### Required
- `OPENAI_API_KEY` - Your OpenAI API key for transcription and AI analysis

### Optional
- `ZAPCAP_API_KEY` - ZapCap API key for automated captioning
- `ZAPCAP_TEMPLATE_ID` - Custom ZapCap template ID
- `DEBUG` - Enable debug mode (true/false)
- `LOG_LEVEL` - Logging level (debug/info/warning/error)
- `MAX_FILE_SIZE` - Maximum file size in bytes
- `MAX_WORKERS` - Maximum number of workers

## API Endpoints

Once running, access:
- **API Docs**: http://localhost:8000/docs
- **Alternative Docs**: http://localhost:8000/redoc
- **Health Check**: http://localhost:8000/api/v1/health/status

## Directory Structure

The script creates these directories:
- `data/uploads/` - Temporary uploaded files
- `data/clips/` - Generated video clips
- `data/temp/` - Temporary processing files
- `data/results/` - Final processed results
- `logs/` - Application logs

## Common Issues

### 1. "Python 3 is not installed"
Install Python 3.8+ using your system package manager or from python.org

### 2. "Missing system dependencies"
Install FFmpeg and yt-dlp using the commands shown for your OS

### 3. "OpenAI API key is required"
Set your OpenAI API key in the .env file or export it:
```bash
export OPENAI_API_KEY="your_key_here"
```

### 4. "Cannot import FastAPI app module"
Make sure you're in the correct directory and have the right project structure

### 5. Port already in use
Use a different port:
```bash
./run.sh --port 8001
```

## Logs

Logs are written to:
- Console output (colored)
- `logs/` directory (when configured)

View logs in real-time:
```bash
# Run with debug for detailed logs
./run.sh --debug

# Or tail log files
tail -f logs/clipper_academy.log
```

## Stopping the Server

- Press `Ctrl+C` to stop the development server
- For production, use process management tools like systemd or supervisor

## Testing

After starting the server, test with:
```bash
# Health check
curl http://localhost:8000/api/v1/health/status

# Upload a test video (requires video file)
curl -X POST "http://localhost:8000/api/v1/clips/upload" \
  -F "video=@test_video.mp4" \
  -F "aspect_ratio=9:16"
```

## Support

- Check the API documentation at `/docs` endpoint
- Review error messages in console output
- Use `--check` to diagnose environment issues
- Enable `--debug` for detailed logging 