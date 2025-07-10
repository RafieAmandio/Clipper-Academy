# Clipper Academy Backend

A FastAPI-based backend for AI-powered video clip generation, supporting both UV (preferred) and traditional venv for cross-platform development.

## 🚀 Features

### Core Functionality

- **AI-Powered Clip Generation**: Automatically identifies viral-worthy segments from videos
- **Multi-Platform Support**: TikTok, Instagram, YouTube URL processing
- **Smart Aspect Ratio Conversion**: 9:16, 16:9, 1:1, and original ratios
- **ZapCap Integration**: Automatic caption generation with custom templates
- **Async Processing**: Background task processing with status tracking

### Advanced Object Detection & Smart Cropping

- **Face Detection**: Haar Cascade-based face detection for optimal framing
- **Multi-Face Support**: Detects and handles multiple faces in the same frame
- **Video Call Style Layout**: Grid layout for group videos and interviews
- **Smart Cropping Modes**:
  - **Single Face**: Centers on the most confident face detection
  - **Grid Layout**: Displays all faces in a professional video call style grid
  - **Auto Mode**: Automatically selects layout based on face count

### Layout Modes

- **`grid`** (Default): Video call style layout for multiple faces
  - 2 faces: Side-by-side layout
  - 3 faces: 2 on top, 1 centered on bottom
  - 4 faces: 2x2 grid layout
  - 5-6 faces: 3x2 grid layout
  - 7-9 faces: 3x3 grid layout
  - 10+ faces: Dynamic grid sizing
- **`single`**: Traditional smart cropping for single speaker content
- **`auto`**: Automatic selection based on face count

## 🚀 Quick Start

### Prerequisites

- **Python 3.8+**
- **FFmpeg** (for video processing)
- **yt-dlp** (for video downloading)

### Installation Options

This project supports two package management approaches:

1. **UV (Recommended)** - Fast, modern Python package manager
2. **Traditional venv** - Standard Python virtual environment

## 📦 Option 1: Using UV (Recommended)

UV is a fast Python package manager written in Rust. It's particularly well-suited for Windows development and provides better dependency resolution.

### Install UV

**Windows:**

```powershell
# Using PowerShell
irm https://astral.sh/uv/install.ps1 | iex

# Or using pip
pip install uv
```

**macOS/Linux:**

```bash
# Using curl
curl -LsSf https://astral.sh/uv/install.sh | sh

# Or using pip
pip install uv
```

### Setup with UV

```bash
# Clone the repository
git clone <repository-url>
cd Clipper-Academy/backend

# Setup environment (creates .venv and installs dependencies)
python run.py --setup

# Or manually with UV
uv venv
uv pip install -r requirements.txt

# Run the application
python run.py
```

## 🐍 Option 2: Using Traditional venv

Traditional virtual environments work on all platforms and are the fallback option.

### Setup with venv

```bash
# Clone the repository
git clone <repository-url>
cd Clipper-Academy/backend

# Setup environment (creates venv and installs dependencies)
python run.py --setup

# Or manually
python -m venv venv

# Activate virtual environment
# Windows:
venv\Scripts\activate
# macOS/Linux:
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Run the application
python run.py
```

## 🏃‍♂️ Running the Application

### Unified Python Script (All Platforms)

The `run.py` script automatically detects your system and available package managers (UV or venv) and works on Windows, macOS, and Linux:

```bash
# Basic run
python run.py

# Development with auto-reload
python run.py --reload --debug

# Production mode
python run.py --env production

# Check environment
python run.py --check

# Setup environment
python run.py --setup
```

## 🔧 Configuration

### Environment Variables

Create a `.env` file in the backend directory:

```env
# Required
OPENAI_API_KEY=your_openai_api_key_here

# Optional
ZAPCAP_API_KEY=your_zapcap_api_key_here
ZAPCAP_TEMPLATE_ID=d2018215-2125-41c1-940e-f13b411fff5c

# Application Settings
DEBUG=false
LOG_LEVEL=info
MAX_FILE_SIZE=524288000
MAX_WORKERS=4

# Directories
UPLOAD_DIR=data/uploads
CLIPS_DIR=data/clips
TEMP_DIR=data/temp
RESULTS_DIR=data/results
```

### API Keys

1. **OpenAI API Key**: Required for AI-powered content analysis

   - Get from [OpenAI Platform](https://platform.openai.com/api-keys)

2. **ZapCap API Key**: Optional for enhanced video processing
   - Get from [ZapCap](https://zapcap.ai)

## 📁 Project Structure

```
backend/
├── app/                    # Main application code
│   ├── api/v1/            # API endpoints
│   ├── config/            # Configuration
│   ├── core/              # Core functionality
│   ├── models/            # Pydantic models
│   ├── services/          # Business logic
│   └── utils/             # Utilities
├── data/                  # Runtime data
├── tests/                 # Test files
├── pyproject.toml         # UV/Modern Python config
├── requirements.txt       # Traditional pip requirements
├── run.py                 # Cross-platform runner
├── run.sh                 # Unix/Linux runner
├── run.bat                # Windows runner
└── README.md              # This file
```

## 🧪 Development

### Running Tests

**With UV:**

```bash
uv run pytest
```

**With venv:**

```bash
# Activate venv first
source venv/bin/activate  # or venv\Scripts\activate on Windows
pytest
```

### Code Quality

**With UV:**

```bash
uv run black .
uv run isort .
uv run flake8 .
```

**With venv:**

```bash
# Activate venv first
black .
isort .
flake8 .
```

## 🐳 Docker

For containerized deployment:

```bash
# Build and run with Docker Compose
docker-compose up --build

# Or build manually
docker build -t clipper-academy .
docker run -p 8000:8000 clipper-academy
```

## 🔍 Troubleshooting

### Common Issues

**1. UV not found on Windows**

```powershell
# Install UV using PowerShell
irm https://astral.sh/uv/install.ps1 | iex

# Restart your terminal and try again
```

**2. Permission denied on Unix systems**

```bash
# Make scripts executable
chmod +x run.sh

# Or run with Python directly
python run.py
```

**3. Virtual environment issues**

```bash
# Remove existing environment and recreate
rm -rf .venv venv
python run.py --setup
```

**4. Missing system dependencies**

```bash
# Ubuntu/Debian
sudo apt-get update
sudo apt-get install ffmpeg python3-pip
pip3 install yt-dlp

# macOS
brew install ffmpeg yt-dlp

# Windows
# Download FFmpeg from https://ffmpeg.org/download.html
# Install yt-dlp: pip install yt-dlp
```

### Environment Check

Run a comprehensive environment check:

```bash
python run.py --check
```

This will verify:

- ✅ Python version (3.8+)
- ✅ System dependencies (FFmpeg, yt-dlp)
- ✅ Environment variables
- ✅ Application module
- ✅ Package manager (UV or venv)

## 📚 API Documentation

Once the server is running, visit:

- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Run tests: `python run.py --check`
5. Submit a pull request

## 📄 License

This project is licensed under the MIT License - see the LICENSE file for details.

## 🆘 Support

If you encounter issues:

1. Check the troubleshooting section above
2. Run `python run.py --check` to diagnose issues
3. Check the logs in the `logs/` directory
4. Open an issue on GitHub with detailed information

## 🔄 Migration Guide

### From venv to UV

If you're currently using venv and want to switch to UV:

```bash
# Remove old environment
rm -rf venv

# Install UV (see installation instructions above)

# Setup with UV
python run.py --setup
```

### From UV to venv

If you need to switch back to venv:

```bash
# Remove UV environment
rm -rf .venv

# Setup with venv
python run.py --setup
```

The `run.py` script will automatically detect which package manager is available and use the appropriate one.

## 📦 Package Management Details

### UV Configuration

UV uses `requirements.txt` for dependency management, ensuring compatibility with traditional pip workflows while providing faster installation speeds.

### Virtual Environment Locations

- **UV**: Creates `.venv/` directory
- **Traditional venv**: Creates `venv/` directory

Both approaches are fully supported and can coexist in the same project.
