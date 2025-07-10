#!/usr/bin/env python3
"""
Clipper Academy API Runner - Cross-Platform Python Script
This script provides a unified interface for running the FastAPI application
on both Windows and Unix systems, supporting both UV and traditional venv.
"""

import os
import sys
import subprocess
import argparse
import platform
import shutil
from pathlib import Path
from typing import Optional, List, Dict, Any
import json

# Colors for output
class Colors:
    RED = '\033[0;31m'
    GREEN = '\033[0;32m'
    YELLOW = '\033[1;33m'
    BLUE = '\033[0;34m'
    NC = '\033[0m'  # No Color

def print_status(message: str) -> None:
    """Print a status message with green color."""
    print(f"{Colors.GREEN}[INFO]{Colors.NC} {message}")

def print_warning(message: str) -> None:
    """Print a warning message with yellow color."""
    print(f"{Colors.YELLOW}[WARN]{Colors.NC} {message}")

def print_error(message: str) -> None:
    """Print an error message with red color."""
    print(f"{Colors.RED}[ERROR]{Colors.NC} {message}")

def print_header() -> None:
    """Print the application header."""
    print(f"{Colors.BLUE}================================={Colors.NC}")
    print(f"{Colors.BLUE} Clipper Academy API Runner{Colors.NC}")
    print(f"{Colors.BLUE}================================={Colors.NC}")

def show_usage() -> None:
    """Show usage information."""
    print("Usage: python run.py [OPTIONS]")
    print("")
    print("Unified runner for all platforms (Windows, Linux, macOS) and both UV and venv.")
    print("")
    print("Options:")
    print("  -e, --env ENV          Environment (development|production|docker) [default: development]")
    print("  -h, --host HOST        Host to bind to [default: 0.0.0.0]")
    print("  -p, --port PORT        Port to listen on [default: 8000]")
    print("  -w, --workers NUM      Number of worker processes (production mode) [default: 4]")
    print("  -r, --reload           Enable auto-reload (development mode)")
    print("  -d, --debug            Enable debug mode")
    print("  -c, --check            Check dependencies and environment only")
    print("  -s, --setup            Setup environment and install dependencies")
    print("  --help                 Show this help message")
    print("")
    print("Examples:")
    print("  python run.py                     # Run in development mode")
    print("  python run.py --env production    # Run in production mode")
    print("  python run.py --setup             # Setup environment only")
    print("  python run.py --check             # Check environment only")
    print("  python run.py --reload --debug    # Development with auto-reload and debug")

def command_exists(command: str) -> bool:
    """Check if a command exists in the system PATH."""
    return shutil.which(command) is not None

def check_python() -> bool:
    """Check if Python is available and has the correct version."""
    try:
        version = sys.version_info
        if version.major < 3 or (version.major == 3 and version.minor < 8):
            print_error(f"Python 3.8+ is required. Found: {version.major}.{version.minor}")
            return False
        print_status(f"Python version: {version.major}.{version.minor}.{version.micro} ✓")
        return True
    except Exception as e:
        print_error(f"Error checking Python version: {e}")
        return False

def check_uv() -> bool:
    """Check if UV package manager is available."""
    if command_exists("uv"):
        print_status("UV package manager found ✓")
        return True
    else:
        print_warning("UV not found, will use traditional venv")
        return False

def check_system_dependencies() -> bool:
    """Check if required system dependencies are available."""
    print_status("Checking system dependencies...")
    
    missing_deps = []
    
    # Check FFmpeg
    if not command_exists("ffmpeg"):
        missing_deps.append("ffmpeg")
    else:
        try:
            result = subprocess.run(["ffmpeg", "-version"], 
                                  capture_output=True, text=True, check=True)
            version_line = result.stdout.split('\n')[0]
            version = version_line.split()[2] if len(version_line.split()) > 2 else "Available"
            print_status(f"FFmpeg: {version} ✓")
        except subprocess.CalledProcessError:
            missing_deps.append("ffmpeg")
    
    # Check FFprobe
    if not command_exists("ffprobe"):
        missing_deps.append("ffprobe")
    else:
        print_status("FFprobe: Available ✓")
    
    # Note: yt-dlp is checked as a Python package, not system dependency
    print_status("yt-dlp: Will check as Python package ✓")
    
    if missing_deps:
        print_error(f"Missing system dependencies: {' '.join(missing_deps)}")
        print_warning("Install missing dependencies:")
        
        system = platform.system().lower()
        if system == "darwin":  # macOS
            print("  brew install ffmpeg")
        elif system == "linux":
            if command_exists("apt-get"):
                print("  sudo apt-get update")
                print("  sudo apt-get install ffmpeg")
            elif command_exists("yum"):
                print("  sudo yum install ffmpeg")
        elif system == "windows":
            print("  Download FFmpeg from: https://ffmpeg.org/download.html")
        else:
            print(f"  Please install: {' '.join(missing_deps)}")
        return False
    
    return True

def check_python_dependencies() -> bool:
    """Check if required Python packages are available."""
    print_status("Checking Python dependencies...")
    
    # Determine which Python to use
    python_cmd = None
    if check_uv():
        # Use UV's Python
        try:
            result = subprocess.run(["uv", "run", "python", "--version"], 
                                  capture_output=True, text=True, check=True)
            print_status("Using UV Python environment ✓")
            python_cmd = ["uv", "run", "python"]
        except subprocess.CalledProcessError:
            print_warning("UV available but failed to run Python, using system Python")
            python_cmd = [sys.executable]
    else:
        # Use system Python
        python_cmd = [sys.executable]
    
    required_packages = [
        "fastapi",
        "uvicorn", 
        "openai",
        "opencv-python",
        "numpy",
        "aiofiles",
        "python-multipart",
        "requests",
        "python-dotenv",
        "Pillow",
        "ffmpeg-python",
        "yt-dlp",
        "tiktok-api",
        "instagram-private-api",
        "google-api-python-client",
        "google-auth-oauthlib",
        "google-auth-httplib2",
        "typing-extensions"
    ]
    
    missing_packages = []
    
    for package in required_packages:
        try:
            # Use the appropriate Python to check imports
            check_script = f"""
import sys
try:
"""
            
            if package == "opencv-python":
                check_script += """
    import cv2
    print(f"{package}: Available ✓")
"""
            elif package == "ffmpeg-python":
                check_script += """
    import ffmpeg
    print(f"{package}: Available ✓")
"""
            elif package == "yt-dlp":
                check_script += """
    import yt_dlp
    print(f"{package}: {yt_dlp.version.__version__} ✓")
"""
            elif package == "tiktok-api":
                check_script += """
    import tiktok_api
    print(f"{package}: Available ✓")
"""
            elif package == "instagram-private-api":
                check_script += """
    import instagram_private_api
    print(f"{package}: Available ✓")
"""
            elif package == "google-api-python-client":
                check_script += """
    import googleapiclient
    print(f"{package}: Available ✓")
"""
            elif package == "google-auth-oauthlib":
                check_script += """
    import google_auth_oauthlib
    print(f"{package}: Available ✓")
"""
            elif package == "google-auth-httplib2":
                check_script += """
    import google_auth_httplib2
    print(f"{package}: Available ✓")
"""
            elif package == "typing-extensions":
                check_script += """
    import typing_extensions
    print(f"{package}: Available ✓")
"""
            else:
                check_script += f"""
    import {package.replace("-", "_")}
    print(f"{package}: Available ✓")
"""
            
            check_script += """
except ImportError:
    print(f"{package}: Missing")
    sys.exit(1)
"""
            
            result = subprocess.run(python_cmd + ["-c", check_script], 
                                  capture_output=True, text=True)
            
            if result.returncode == 0:
                print_status(result.stdout.strip())
            else:
                missing_packages.append(package)
                print_warning(f"{package}: Missing")
                
        except Exception as e:
            missing_packages.append(package)
            print_warning(f"{package}: Error checking - {e}")
    
    if missing_packages:
        print_error(f"Missing Python packages: {' '.join(missing_packages)}")
        print_warning("Install missing packages:")
        if check_uv():
            print("  uv pip install " + " ".join(missing_packages))
        else:
            print("  pip install " + " ".join(missing_packages))
        return False
    
    return True

def create_directories(project_dir: Path) -> None:
    """Create necessary application directories."""
    print_status("Creating application directories...")
    
    dirs = [
        "data",
        "data/uploads",
        "data/clips",
        "data/temp",
        "data/results",
        "logs"
    ]
    
    for dir_name in dirs:
        dir_path = project_dir / dir_name
        if not dir_path.exists():
            dir_path.mkdir(parents=True, exist_ok=True)
            print_status(f"Created directory: {dir_name} ✓")
        else:
            print_status(f"Directory exists: {dir_name} ✓")

def check_environment_variables(project_dir: Path) -> bool:
    """Check and load environment variables."""
    print_status("Checking environment variables...")
    
    # Load .env file if it exists
    env_file = project_dir / ".env"
    if env_file.exists():
        print_status("Loading .env file ✓")
        try:
            with open(env_file, 'r') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#') and '=' in line:
                        key, value = line.split('=', 1)
                        key = key.strip()
                        value = value.strip().strip('"\'')
                        os.environ[key] = value
        except Exception as e:
            print_warning(f"Error loading .env file: {e}")
    else:
        print_warning(".env file not found. Using environment variables.")
    
    # Check required environment variables
    required_vars = ["OPENAI_API_KEY"]
    optional_vars = ["ZAPCAP_API_KEY", "ZAPCAP_TEMPLATE_ID"]
    missing_required = []
    
    for var in required_vars:
        if not os.getenv(var):
            missing_required.append(var)
        else:
            print_status(f"{var}: Set ✓")
    
    for var in optional_vars:
        if not os.getenv(var):
            print_warning(f"{var}: Not set (optional)")
        else:
            print_status(f"{var}: Set ✓")
    
    if missing_required:
        print_error(f"Missing required environment variables: {' '.join(missing_required)}")
        print_warning("Set them in .env file or export them:")
        for var in missing_required:
            print(f"  export {var}=\"your_{var.lower()}_key_here\"")
        return False
    
    return True

def install_dependencies(project_dir: Path) -> bool:
    """Install Python dependencies using UV or traditional venv."""
    print_status("Installing Python dependencies...")
    
    if check_uv():
        print_status("Using UV package manager...")
        
        # Check if virtual environment exists
        venv_path = project_dir / ".venv"
        if venv_path.exists():
            print_status("UV virtual environment exists ✓")
        else:
            print_status("Creating UV virtual environment...")
            try:
                subprocess.run(["uv", "venv"], cwd=project_dir, check=True)
            except subprocess.CalledProcessError as e:
                print_error(f"Failed to create UV virtual environment: {e}")
                return False
        
        # Install dependencies
        print_status("Installing dependencies with UV...")
        try:
            # Use requirements.txt instead of editable install to avoid build issues
            requirements_file = project_dir / "requirements.txt"
            if requirements_file.exists():
                subprocess.run(["uv", "pip", "install", "-r", str(requirements_file)], cwd=project_dir, check=True)
            else:
                # Fallback to core dependencies if requirements.txt doesn't exist
                core_deps = [
                    "fastapi[all]",
                    "uvicorn[standard]",
                    "openai",
                    "opencv-python",
                    "numpy",
                    "aiofiles",
                    "python-multipart",
                    "requests",
                    "python-dotenv"
                ]
                subprocess.run(["uv", "pip", "install"] + core_deps, cwd=project_dir, check=True)
            
            print_status("Dependencies installed with UV ✓")
            return True
        except subprocess.CalledProcessError as e:
            print_error(f"Failed to install dependencies with UV: {e}")
            return False
    else:
        print_status("Using traditional venv...")
        
        # Check if virtual environment should be used
        venv_path = project_dir / "venv"
        if not venv_path.exists():
            print_status("Creating virtual environment...")
            try:
                subprocess.run([sys.executable, "-m", "venv", str(venv_path)], check=True)
            except subprocess.CalledProcessError as e:
                print_error(f"Failed to create virtual environment: {e}")
                return False
        
        # Activate virtual environment
        print_status("Activating virtual environment...")
        if platform.system().lower() == "windows":
            activate_script = venv_path / "Scripts" / "activate.bat"
            python_exe = venv_path / "Scripts" / "python.exe"
        else:
            activate_script = venv_path / "bin" / "activate"
            python_exe = venv_path / "bin" / "python"
        
        if not python_exe.exists():
            print_error("Virtual environment Python executable not found")
            return False
        
        # Install/upgrade pip
        try:
            subprocess.run([str(python_exe), "-m", "pip", "install", "--upgrade", "pip"], check=True)
        except subprocess.CalledProcessError as e:
            print_error(f"Failed to upgrade pip: {e}")
            return False
        
        # Install dependencies
        requirements_file = project_dir / "requirements.txt"
        if requirements_file.exists():
            print_status("Installing from requirements.txt...")
            try:
                subprocess.run([str(python_exe), "-m", "pip", "install", "-r", str(requirements_file)], check=True)
            except subprocess.CalledProcessError as e:
                print_error(f"Failed to install requirements: {e}")
                return False
        else:
            print_status("Installing core dependencies...")
            core_deps = [
                "fastapi[all]",
                "uvicorn[standard]",
                "openai",
                "opencv-python",
                "numpy",
                "aiofiles",
                "python-multipart",
                "requests",
                "python-dotenv"
            ]
            try:
                subprocess.run([str(python_exe), "-m", "pip", "install"] + core_deps, check=True)
            except subprocess.CalledProcessError as e:
                print_error(f"Failed to install core dependencies: {e}")
                return False
        
        print_status("Dependencies installed ✓")
        return True

def check_app_module(project_dir: Path) -> tuple[bool, str]:
    """Check if the FastAPI app module exists and can be imported."""
    print_status("Checking application module...")

    # Ensure app/ is a package
    app_dir = project_dir / "app"
    init_file = app_dir / "__init__.py"
    if not init_file.exists():
        print_warning("app/__init__.py not found. Creating it to ensure package importability.")
        try:
            init_file.touch()
            print_status("Created app/__init__.py ✓")
        except Exception as e:
            print_error(f"Failed to create app/__init__.py: {e}")
            return False, ""

    # Set working directory to backend (project_dir)
    os.chdir(project_dir)
    sys.path.insert(0, str(project_dir))

    # Try importing app.main:app
    main_file = app_dir / "main.py"
    if main_file.exists():
        try:
            # Try importing using subprocess, but print diagnostics if it fails
            result = subprocess.run([
                sys.executable, "-c",
                "import sys; print('sys.path:', sys.path); from app.main import app; print('app import success')"
            ], capture_output=True, text=True)
            if result.returncode == 0 and "app import success" in result.stdout:
                print_status("App module found: app.main (current structure) ✓")
                return True, "app.main:app"
            else:
                print_error("Failed to import app.main:app")
                print_error(f"stdout: {result.stdout}")
                print_error(f"stderr: {result.stderr}")
                return False, ""
        except Exception as e:
            print_error(f"Exception during import: {e}")
            return False, ""

    # Legacy structure fallback
    main_file_legacy = project_dir / "main.py"
    if main_file_legacy.exists():
        try:
            result = subprocess.run([
                sys.executable, "-c",
                "import sys; print('sys.path:', sys.path); from main import app; print('app import success')"
            ], capture_output=True, text=True)
            if result.returncode == 0 and "app import success" in result.stdout:
                print_status("App module found: main.py (legacy structure) ✓")
                return True, "main:app"
            else:
                print_error("Failed to import main:app")
                print_error(f"stdout: {result.stdout}")
                print_error(f"stderr: {result.stderr}")
                return False, ""
        except Exception as e:
            print_error(f"Exception during legacy import: {e}")
            return False, ""

    print_error("Cannot import FastAPI app module")
    print_warning("Expected structure:")
    print("  Option 1: ./main.py (with 'app = FastAPI()')")
    print("  Option 2: ./app/main.py (with 'app = FastAPI()')")
    return False, ""

def run_application(project_dir: Path, app_module: str, args: Dict[str, Any]) -> None:
    """Run the FastAPI application."""
    print_status("Starting Clipper Academy API...")
    print_status(f"Environment: {args['env']}")
    print_status(f"Host: {args['host']}")
    print_status(f"Port: {args['port']}")
    
    # Change to project directory
    os.chdir(project_dir)
    
    if check_uv():
        print_status("Using UV to run application...")
        uvicorn_cmd = ["uv", "run", "uvicorn", app_module, 
                      "--host", args['host'], "--port", str(args['port'])]
        
        if args['env'] == 'development' and args['reload']:
            uvicorn_cmd.append("--reload")
        if args['env'] == 'development' and args['debug']:
            uvicorn_cmd.append("--log-level")
            uvicorn_cmd.append("debug")
        elif args['env'] == 'production':
            uvicorn_cmd.extend(["--workers", str(args['workers']), "--log-level", "info"])
        elif args['env'] == 'docker':
            uvicorn_cmd = ["uv", "run", "uvicorn", app_module, "--host", "0.0.0.0", "--port", "8000"]
        
        print_status(f"Command: {' '.join(uvicorn_cmd)}")
        print_status(f"API Documentation: http://{args['host']}:{args['port']}/docs")
        print_status(f"Alternative docs: http://{args['host']}:{args['port']}/redoc")
        print()
        
        subprocess.run(uvicorn_cmd)
    else:
        # Use traditional venv
        venv_path = project_dir / "venv"
        if venv_path.exists():
            if platform.system().lower() == "windows":
                python_exe = venv_path / "Scripts" / "python.exe"
            else:
                python_exe = venv_path / "bin" / "python"
            
            if python_exe.exists():
                # Set debug environment variable
                if args['debug']:
                    os.environ['DEBUG'] = 'true'
                    os.environ['LOG_LEVEL'] = 'debug'
                
                # Build uvicorn command
                uvicorn_cmd = [str(python_exe), "-m", "uvicorn", app_module,
                              "--host", args['host'], "--port", str(args['port'])]
                
                if args['env'] == 'development':
                    if args['reload']:
                        uvicorn_cmd.append("--reload")
                    if args['debug']:
                        uvicorn_cmd.extend(["--log-level", "debug"])
                elif args['env'] == 'production':
                    uvicorn_cmd.extend(["--workers", str(args['workers']), "--log-level", "info"])
                elif args['env'] == 'docker':
                    uvicorn_cmd = [str(python_exe), "-m", "uvicorn", app_module, 
                                 "--host", "0.0.0.0", "--port", "8000"]
                
                print_status(f"Command: {' '.join(uvicorn_cmd)}")
                print_status(f"API Documentation: http://{args['host']}:{args['port']}/docs")
                print_status(f"Alternative docs: http://{args['host']}:{args['port']}/redoc")
                print()
                
                subprocess.run(uvicorn_cmd)
            else:
                print_error("Virtual environment Python executable not found")
                sys.exit(1)
        else:
            print_error("Virtual environment not found")
            sys.exit(1)

def run_environment_check(project_dir: Path) -> bool:
    """Run a comprehensive environment check."""
    print_status("Running comprehensive environment check...")
    
    checks_passed = 0
    total_checks = 7  # Updated to include Python dependencies
    
    # Check 1: Python
    if check_python():
        checks_passed += 1
    
    # Check 2: System dependencies
    if check_system_dependencies():
        checks_passed += 1
    
    # Check 3: Python dependencies
    if check_python_dependencies():
        checks_passed += 1
    
    # Check 4: Directories
    create_directories(project_dir)
    checks_passed += 1
    
    # Check 5: Environment variables
    if check_environment_variables(project_dir):
        checks_passed += 1
    
    # Check 6: App module
    app_ok, app_module = check_app_module(project_dir)
    if app_ok:
        checks_passed += 1
    
    # Check 7: API health (if server is running)
    print_status("Checking if API is already running...")
    try:
        import urllib.request
        import urllib.error
        
        # Try to connect to the API
        url = f"http://localhost:8000/api/v1/health/status"
        try:
            with urllib.request.urlopen(url, timeout=2) as response:
                if response.getcode() == 200:
                    print_status("API is already running and responding ✓")
                    checks_passed += 1
                else:
                    print_warning("API is running but not responding correctly")
        except urllib.error.URLError:
            # Try legacy health endpoint
            url = f"http://localhost:8000/health"
            try:
                with urllib.request.urlopen(url, timeout=2) as response:
                    if response.getcode() == 200:
                        print_status("API is already running (legacy health endpoint) ✓")
                        checks_passed += 1
                    else:
                        print_warning("API is not currently running")
            except urllib.error.URLError:
                print_warning("API is not currently running")
    except Exception as e:
        print_warning(f"Could not check API status: {e}")
    
    print()
    print_status(f"Environment check complete: {checks_passed}/{total_checks} checks passed")
    
    if checks_passed == total_checks:
        print_status("✅ Environment is ready for production!")
        return True
    elif checks_passed >= 5:  # Updated threshold
        print_warning("⚠️  Environment is mostly ready, but has some issues")
        return False
    else:
        print_error("❌ Environment has significant issues")
        return False

def setup_environment(project_dir: Path) -> None:
    """Setup the Clipper Academy environment."""
    print_status("Setting up Clipper Academy environment...")
    
    # Create .env file if it doesn't exist
    env_file = project_dir / ".env"
    if not env_file.exists():
        print_status("Creating .env file template...")
        env_content = """# Clipper Academy API Configuration
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
"""
        with open(env_file, 'w') as f:
            f.write(env_content)
        print_status(".env file created ✓")
        print_warning("Please edit .env file and add your API keys")
    
    # Create directories
    create_directories(project_dir)
    
    # Install dependencies
    if not install_dependencies(project_dir):
        print_error("Failed to install dependencies")
        sys.exit(1)
    
    print_status("Setup complete! ✅")
    print_warning("Don't forget to:")
    print("  1. Set your OPENAI_API_KEY in .env file")
    print("  2. Set your ZAPCAP_API_KEY in .env file (optional)")
    print("  3. Run 'python run.py --check' to verify everything is working")

def main():
    """Main function."""
    parser = argparse.ArgumentParser(description="Clipper Academy API Runner")
    parser.add_argument("-e", "--env", default="development", 
                       choices=["development", "production", "docker"],
                       help="Environment (default: development)")
    parser.add_argument("--host", default="0.0.0.0", help="Host to bind to (default: 0.0.0.0)")
    parser.add_argument("-p", "--port", type=int, default=8000, help="Port to listen on (default: 8000)")
    parser.add_argument("-w", "--workers", type=int, default=4, help="Number of worker processes (default: 4)")
    parser.add_argument("-r", "--reload", action="store_true", help="Enable auto-reload (development mode)")
    parser.add_argument("-d", "--debug", action="store_true", help="Enable debug mode")
    parser.add_argument("-c", "--check", action="store_true", help="Check dependencies and environment only")
    parser.add_argument("-s", "--setup", action="store_true", help="Setup environment and install dependencies")
    
    args = parser.parse_args()
    
    # Convert args to dict for easier handling
    args_dict = vars(args)
    
    print_header()
    
    # Get project directory
    project_dir = Path(__file__).parent.absolute()
    
    # Handle special modes
    if args.setup:
        setup_environment(project_dir)
        return
    
    if args.check:
        success = run_environment_check(project_dir)
        sys.exit(0 if success else 1)
    
    # Normal startup sequence
    print_status(f"Starting up in {args.env} mode...")
    
    # Run essential checks
    if not check_python():
        sys.exit(1)
    
    if not check_system_dependencies():
        print_warning("Some system dependencies are missing. The API may not work properly.")
        response = input("Continue anyway? (y/N): ")
        if response.lower() != 'y':
            sys.exit(1)
    
    create_directories(project_dir)
    
    if not check_environment_variables(project_dir):
        print_error("Environment variables not properly configured")
        print_warning("Run 'python run.py --setup' to create .env template")
        sys.exit(1)
    
    app_ok, app_module = check_app_module(project_dir)
    if not app_ok:
        sys.exit(1)
    
    # All checks passed, start the application
    run_application(project_dir, app_module, args_dict)

if __name__ == "__main__":
    main() 