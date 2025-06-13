#!/bin/bash

# Clipper Academy API Runner Script
# This script sets up the environment and runs the FastAPI application

set -e  # Exit on any error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Script configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$SCRIPT_DIR"
APP_MODULE="app.main:app"
DEFAULT_HOST="0.0.0.0"
DEFAULT_PORT="8000"
DEFAULT_ENV="development"

# Function to print colored output
print_status() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

print_header() {
    echo -e "${BLUE}=================================${NC}"
    echo -e "${BLUE} Clipper Academy API Runner${NC}"
    echo -e "${BLUE}=================================${NC}"
}

# Function to show usage
show_usage() {
    echo "Usage: $0 [OPTIONS]"
    echo ""
    echo "Options:"
    echo "  -e, --env ENV          Environment (development|production|docker) [default: development]"
    echo "  -h, --host HOST        Host to bind to [default: 0.0.0.0]"
    echo "  -p, --port PORT        Port to listen on [default: 8000]"
    echo "  -w, --workers NUM      Number of worker processes (production mode) [default: 4]"
    echo "  -r, --reload           Enable auto-reload (development mode)"
    echo "  -d, --debug            Enable debug mode"
    echo "  -c, --check            Check dependencies and environment only"
    echo "  -s, --setup            Setup environment and install dependencies"
    echo "  --help                 Show this help message"
    echo ""
    echo "Examples:"
    echo "  $0                     # Run in development mode"
    echo "  $0 --env production    # Run in production mode"
    echo "  $0 --setup             # Setup environment only"
    echo "  $0 --check             # Check environment only"
    echo "  $0 --reload --debug    # Development with auto-reload and debug"
}

# Parse command line arguments
ENV="$DEFAULT_ENV"
HOST="$DEFAULT_HOST"
PORT="$DEFAULT_PORT"
WORKERS="4"
RELOAD=false
DEBUG=false
CHECK_ONLY=false
SETUP_ONLY=false

while [[ $# -gt 0 ]]; do
    case $1 in
        -e|--env)
            ENV="$2"
            shift 2
            ;;
        -h|--host)
            HOST="$2"
            shift 2
            ;;
        -p|--port)
            PORT="$2"
            shift 2
            ;;
        -w|--workers)
            WORKERS="$2"
            shift 2
            ;;
        -r|--reload)
            RELOAD=true
            shift
            ;;
        -d|--debug)
            DEBUG=true
            shift
            ;;
        -c|--check)
            CHECK_ONLY=true
            shift
            ;;
        -s|--setup)
            SETUP_ONLY=true
            shift
            ;;
        --help)
            show_usage
            exit 0
            ;;
        *)
            print_error "Unknown option: $1"
            show_usage
            exit 1
            ;;
    esac
done

# Validate environment
if [[ ! "$ENV" =~ ^(development|production|docker)$ ]]; then
    print_error "Invalid environment: $ENV. Must be development, production, or docker"
    exit 1
fi

# Function to check if command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Function to check Python version
check_python() {
    if ! command_exists python3; then
        print_error "Python 3 is not installed"
        return 1
    fi
    
    local python_version=$(python3 --version 2>&1 | cut -d' ' -f2 | cut -d'.' -f1-2)
    local required_version="3.8"
    
    if ! python3 -c "import sys; exit(0 if sys.version_info >= (3, 8) else 1)"; then
        print_error "Python 3.8+ is required. Found: $python_version"
        return 1
    fi
    
    print_status "Python version: $python_version ✓"
    return 0
}

# Function to check system dependencies
check_system_dependencies() {
    print_status "Checking system dependencies..."
    
    local missing_deps=()
    
    # Check FFmpeg
    if ! command_exists ffmpeg; then
        missing_deps+=("ffmpeg")
    else
        print_status "FFmpeg: $(ffmpeg -version 2>&1 | head -n1 | cut -d' ' -f3) ✓"
    fi
    
    # Check FFprobe
    if ! command_exists ffprobe; then
        missing_deps+=("ffprobe")
    else
        print_status "FFprobe: Available ✓"
    fi
    
    # Check yt-dlp
    if ! command_exists yt-dlp; then
        missing_deps+=("yt-dlp")
    else
        print_status "yt-dlp: $(yt-dlp --version) ✓"
    fi
    
    if [ ${#missing_deps[@]} -ne 0 ]; then
        print_error "Missing system dependencies: ${missing_deps[*]}"
        print_warning "Install missing dependencies:"
        
        # macOS installation instructions
        if [[ "$OSTYPE" == "darwin"* ]]; then
            echo "  brew install ffmpeg yt-dlp"
        # Ubuntu/Debian installation instructions
        elif command_exists apt-get; then
            echo "  sudo apt-get update"
            echo "  sudo apt-get install ffmpeg python3-pip"
            echo "  pip3 install yt-dlp"
        # CentOS/RHEL installation instructions
        elif command_exists yum; then
            echo "  sudo yum install ffmpeg python3-pip"
            echo "  pip3 install yt-dlp"
        else
            echo "  Please install: ${missing_deps[*]}"
        fi
        return 1
    fi
    
    return 0
}

# Function to create necessary directories
create_directories() {
    print_status "Creating application directories..."
    
    local dirs=(
        "data"
        "data/uploads"
        "data/clips" 
        "data/temp"
        "data/results"
        "logs"
    )
    
    for dir in "${dirs[@]}"; do
        if [ ! -d "$PROJECT_DIR/$dir" ]; then
            mkdir -p "$PROJECT_DIR/$dir"
            print_status "Created directory: $dir ✓"
        else
            print_status "Directory exists: $dir ✓"
        fi
    done
}

# Function to check and load environment variables
check_environment_variables() {
    print_status "Checking environment variables..."
    
    # Load .env file if it exists
    if [ -f "$PROJECT_DIR/.env" ]; then
        print_status "Loading .env file ✓"
        # Simple .env parsing that avoids shell issues
        while IFS='=' read -r key value; do
            # Skip comments and empty lines
            if [[ $key =~ ^[[:space:]]*# ]] || [[ -z "$key" ]]; then
                continue
            fi
            # Remove leading/trailing whitespace and quotes
            key=$(echo "$key" | xargs)
            value=$(echo "$value" | xargs | sed 's/^"\(.*\)"$/\1/' | sed "s/^'\(.*\)'$/\1/")
            # Export the variable
            if [[ -n "$key" && -n "$value" ]]; then
                export "$key=$value"
            fi
        done < "$PROJECT_DIR/.env"
    else
        print_warning ".env file not found. Using environment variables."
    fi
    
    # Check required environment variables
    local required_vars=("OPENAI_API_KEY")
    local optional_vars=("ZAPCAP_API_KEY" "ZAPCAP_TEMPLATE_ID")
    local missing_required=()
    
    for var in "${required_vars[@]}"; do
        if [ -z "${!var}" ]; then
            missing_required+=("$var")
        else
            print_status "$var: Set ✓"
        fi
    done
    
    for var in "${optional_vars[@]}"; do
        if [ -z "${!var}" ]; then
            print_warning "$var: Not set (optional)"
        else
            print_status "$var: Set ✓"
        fi
    done
    
    if [ ${#missing_required[@]} -ne 0 ]; then
        print_error "Missing required environment variables: ${missing_required[*]}"
        print_warning "Set them in .env file or export them:"
        for var in "${missing_required[@]}"; do
            echo "  export $var=\"your_${var}_key_here\""
        done
        return 1
    fi
    
    return 0
}

# Function to install Python dependencies
install_dependencies() {
    print_status "Installing Python dependencies..."
    
    # Check if virtual environment should be used
    if [ ! -d "$PROJECT_DIR/venv" ] && [ "$ENV" = "development" ]; then
        print_status "Creating virtual environment..."
        python3 -m venv "$PROJECT_DIR/venv"
    fi
    
    # Activate virtual environment if it exists
    if [ -d "$PROJECT_DIR/venv" ]; then
        print_status "Activating virtual environment..."
        source "$PROJECT_DIR/venv/bin/activate"
    fi
    
    # Install/upgrade pip
    python3 -m pip install --upgrade pip
    
    # Install dependencies
    if [ -f "$PROJECT_DIR/requirements.txt" ]; then
        print_status "Installing from requirements.txt..."
        pip install -r "$PROJECT_DIR/requirements.txt"
    else
        print_status "Installing core dependencies..."
        pip install \
            fastapi[all] \
            uvicorn[standard] \
            openai \
            opencv-python \
            numpy \
            aiofiles \
            python-multipart \
            requests \
            python-dotenv
    fi
    
    print_status "Dependencies installed ✓"
}

# Function to check if app module exists
check_app_module() {
    print_status "Checking application module..."
    
    # Change to project directory
    cd "$PROJECT_DIR"
    
    # Check if we have the legacy structure first
    if [ -f "main.py" ]; then
        if python3 -c "from main import app" 2>/dev/null; then
            print_status "App module found: main.py (legacy structure) ✓"
            APP_MODULE="main:app"
            return 0
        fi
    fi
    
    # Check if we have the new app structure
    if [ -f "app/main.py" ]; then
        if python3 -c "from app.main import app" 2>/dev/null; then
            print_status "App module found: app.main (new structure) ✓"
            APP_MODULE="app.main:app"
            return 0
        fi
    fi
    
    # Check if we have code_reference files that can be used temporarily
    if [ -f "code_reference/main.py" ]; then
        print_warning "Found code_reference/main.py - this is reference code"
        print_warning "You may need to move or copy files to the correct location"
    fi
    
    print_error "Cannot import FastAPI app module"
    print_warning "Expected structure:"
    echo "  Option 1: ./main.py (with 'app = FastAPI()')"
    echo "  Option 2: ./app/main.py (with 'app = FastAPI()')"
    return 1
}

# Function to run the application
run_application() {
    print_status "Starting Clipper Academy API..."
    print_status "Environment: $ENV"
    print_status "Host: $HOST"
    print_status "Port: $PORT"
    
    # Change to project directory
    cd "$PROJECT_DIR"
    
    # Activate virtual environment if it exists
    if [ -d "$PROJECT_DIR/venv" ]; then
        source "$PROJECT_DIR/venv/bin/activate"
    fi
    
    # Set debug environment variable
    if [ "$DEBUG" = true ]; then
        export DEBUG=true
        export LOG_LEVEL=debug
    fi
    
    # Build uvicorn command based on environment
    local uvicorn_cmd="uvicorn $APP_MODULE --host $HOST --port $PORT"
    
    case $ENV in
        development)
            if [ "$RELOAD" = true ]; then
                uvicorn_cmd="$uvicorn_cmd --reload"
            fi
            if [ "$DEBUG" = true ]; then
                uvicorn_cmd="$uvicorn_cmd --log-level debug"
            fi
            ;;
        production)
            uvicorn_cmd="$uvicorn_cmd --workers $WORKERS --log-level info"
            ;;
        docker)
            # For Docker, use simpler configuration
            uvicorn_cmd="uvicorn $APP_MODULE --host 0.0.0.0 --port 8000"
            ;;
    esac
    
    print_status "Command: $uvicorn_cmd"
    print_status "API Documentation: http://$HOST:$PORT/docs"
    print_status "Alternative docs: http://$HOST:$PORT/redoc"
    echo ""
    
    # Run the application
    exec $uvicorn_cmd
}

# Function to run full environment check
run_environment_check() {
    print_status "Running comprehensive environment check..."
    
    local checks_passed=0
    local total_checks=6
    
    # Check 1: Python
    if check_python; then
        ((checks_passed++))
    fi
    
    # Check 2: System dependencies
    if check_system_dependencies; then
        ((checks_passed++))
    fi
    
    # Check 3: Directories
    create_directories
    ((checks_passed++))
    
    # Check 4: Environment variables
    if check_environment_variables; then
        ((checks_passed++))
    fi
    
    # Check 5: App module
    if check_app_module; then
        ((checks_passed++))
    fi
    
    # Check 6: API health (if server is running)
    print_status "Checking if API is already running..."
    if curl -s "http://$HOST:$PORT/api/v1/health/status" >/dev/null 2>&1; then
        print_status "API is already running and responding ✓"
        ((checks_passed++))
    elif curl -s "http://$HOST:$PORT/health" >/dev/null 2>&1; then
        print_status "API is already running (legacy health endpoint) ✓"
        ((checks_passed++))
    else
        print_warning "API is not currently running"
    fi
    
    echo ""
    print_status "Environment check complete: $checks_passed/$total_checks checks passed"
    
    if [ $checks_passed -eq $total_checks ]; then
        print_status "✅ Environment is ready for production!"
        return 0
    elif [ $checks_passed -ge 4 ]; then
        print_warning "⚠️  Environment is mostly ready, but has some issues"
        return 1
    else
        print_error "❌ Environment has significant issues"
        return 1
    fi
}

# Function to setup environment
setup_environment() {
    print_status "Setting up Clipper Academy environment..."
    
    # Create .env file if it doesn't exist
    if [ ! -f "$PROJECT_DIR/.env" ]; then
        print_status "Creating .env file template..."
        cat > "$PROJECT_DIR/.env" << EOF
# Clipper Academy API Configuration
OPENAI_API_KEY=your_openai_api_key_here
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
EOF
        print_status ".env file created ✓"
        print_warning "Please edit .env file and add your API keys"
    fi
    
    # Create directories
    create_directories
    
    # Install dependencies
    install_dependencies
    
    print_status "Setup complete! ✅"
    print_warning "Don't forget to:"
    echo "  1. Set your OPENAI_API_KEY in .env file"
    echo "  2. Set your ZAPCAP_API_KEY in .env file (optional)"
    echo "  3. Run '$0 --check' to verify everything is working"
}

# Main execution
main() {
    print_header
    
    # Handle special modes
    if [ "$SETUP_ONLY" = true ]; then
        setup_environment
        exit 0
    fi
    
    if [ "$CHECK_ONLY" = true ]; then
        run_environment_check
        exit $?
    fi
    
    # Normal startup sequence
    print_status "Starting up in $ENV mode..."
    
    # Run essential checks
    if ! check_python; then
        exit 1
    fi
    
    if ! check_system_dependencies; then
        print_warning "Some system dependencies are missing. The API may not work properly."
        read -p "Continue anyway? (y/N): " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            exit 1
        fi
    fi
    
    create_directories
    
    if ! check_environment_variables; then
        print_error "Environment variables not properly configured"
        print_warning "Run '$0 --setup' to create .env template"
        exit 1
    fi
    
    if ! check_app_module; then
        exit 1
    fi
    
    # All checks passed, start the application
    run_application
}

# Trap Ctrl+C and cleanup
trap 'print_warning "Shutting down..."; exit 0' INT

# Run main function
main "$@" 