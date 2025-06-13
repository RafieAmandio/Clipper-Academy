# Improved FastAPI Project Structure

```
clipper_academy/
├── app/
│   ├── __init__.py
│   ├── main.py                     # FastAPI app initialization
│   ├── config/
│   │   ├── __init__.py
│   │   ├── settings.py             # Environment configuration
│   │   └── logging.py              # Logging configuration
│   ├── core/
│   │   ├── __init__.py
│   │   ├── dependencies.py         # Dependency injection
│   │   ├── exceptions.py           # Custom exceptions
│   │   └── middleware.py           # Custom middleware
│   ├── api/
│   │   ├── __init__.py
│   │   ├── deps.py                 # API dependencies
│   │   └── v1/
│   │       ├── __init__.py
│   │       ├── api.py              # API router aggregator
│   │       └── endpoints/
│   │           ├── __init__.py
│   │           ├── clips.py        # Clip-related endpoints
│   │           ├── health.py       # Health check endpoints
│   │           └── analysis.py     # Content analysis endpoints
│   ├── models/
│   │   ├── __init__.py
│   │   ├── requests.py             # Pydantic request models
│   │   ├── responses.py            # Pydantic response models
│   │   └── enums.py                # Enums and constants
│   ├── services/
│   │   ├── __init__.py
│   │   ├── base.py                 # Base service class
│   │   ├── auto_clipper.py         # Auto clipping logic
│   │   ├── zapcap.py               # ZapCap integration
│   │   ├── content_analyzer.py     # Content analysis
│   │   ├── transcription.py        # Audio transcription
│   │   └── video_processing.py     # Video processing utilities
│   ├── utils/
│   │   ├── __init__.py
│   │   ├── file_utils.py           # File handling utilities
│   │   ├── video_utils.py          # Video processing utilities
│   │   ├── download_utils.py       # Social media download utilities
│   │   └── validation.py          # Input validation helpers
│   └── storage/
│       ├── __init__.py
│       ├── base.py                 # Base storage interface
│       └── local.py                # Local file storage
├── tests/
│   ├── __init__.py
│   ├── conftest.py                 # Pytest configuration
│   ├── unit/
│   │   ├── __init__.py
│   │   ├── test_services/
│   │   ├── test_utils/
│   │   └── test_models/
│   └── integration/
│       ├── __init__.py
│       └── test_api/
├── data/
│   ├── uploads/                    # Temporary uploads
│   ├── clips/                      # Generated clips
│   ├── temp/                       # Temporary processing files
│   └── results/                    # Final results
├── scripts/
│   ├── setup.py                    # Setup/installation script
│   └── migrate.py                  # Data migration scripts
├── docs/
│   ├── api.md                      # API documentation
│   └── setup.md                    # Setup instructions
├── .env.example                    # Environment variables template
├── .gitignore
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
├── pyproject.toml                  # Poetry/pip configuration
└── README.md
```

## **Key Improvements:**

### 1. **Proper Separation of Concerns**
- **API Layer**: Only handles HTTP requests/responses
- **Service Layer**: Contains business logic
- **Utils Layer**: Reusable utility functions
- **Models Layer**: Data validation and serialization

### 2. **Configuration Management**
```python
# app/config/settings.py
from pydantic_settings import BaseSettings
from typing import Optional

class Settings(BaseSettings):
    # API Configuration
    app_name: str = "Auto Clipper API"
    app_version: str = "1.0.0"
    debug: bool = False
    
    # OpenAI Configuration
    openai_api_key: str
    
    # ZapCap Configuration
    zapcap_api_key: Optional[str] = None
    zapcap_template_id: Optional[str] = None
    
    # Storage Configuration
    upload_dir: str = "data/uploads"
    clips_dir: str = "data/clips"
    temp_dir: str = "data/temp"
    results_dir: str = "data/results"
    
    # Processing Configuration
    max_file_size: int = 500 * 1024 * 1024  # 500MB
    max_clip_duration: int = 120  # seconds
    min_clip_duration: int = 10   # seconds
    
    class Config:
        env_file = ".env"
```

### 3. **Dependency Injection**
```python
# app/core/dependencies.py
from functools import lru_cache
from app.config.settings import Settings
from app.services.auto_clipper import AutoClipperService
from app.services.zapcap import ZapCapService

@lru_cache()
def get_settings() -> Settings:
    return Settings()

def get_auto_clipper_service(settings: Settings = Depends(get_settings)) -> AutoClipperService:
    return AutoClipperService(settings)

def get_zapcap_service(settings: Settings = Depends(get_settings)) -> ZapCapService:
    return ZapCapService(settings)
```

### 4. **Pydantic Models for Validation**
```python
# app/models/requests.py
from pydantic import BaseModel, HttpUrl, Field
from typing import Optional
from app.models.enums import AspectRatio

class ClipFromURLRequest(BaseModel):
    url: HttpUrl
    use_zapcap: bool = False
    zapcap_template_id: Optional[str] = None
    aspect_ratio: AspectRatio = AspectRatio.NINE_SIXTEEN

class ClipFromFileRequest(BaseModel):
    file_path: str = Field(..., description="Local file path")
    use_zapcap: bool = False
    zapcap_template_id: Optional[str] = None
    aspect_ratio: AspectRatio = AspectRatio.NINE_SIXTEEN
```

### 5. **Clean API Structure**
```python
# app/api/v1/endpoints/clips.py
from fastapi import APIRouter, Depends, UploadFile, File
from app.services.auto_clipper import AutoClipperService
from app.models.requests import ClipFromURLRequest
from app.models.responses import ClipResponse
from app.core.dependencies import get_auto_clipper_service

router = APIRouter()

@router.post("/upload", response_model=ClipResponse)
async def create_clips_from_upload(
    video: UploadFile = File(...),
    use_zapcap: bool = Form(False),
    aspect_ratio: AspectRatio = Form(AspectRatio.NINE_SIXTEEN),
    service: AutoClipperService = Depends(get_auto_clipper_service)
):
    return await service.process_video_upload(video, use_zapcap, aspect_ratio)
```

### 6. **Service Layer Refactoring**
```python
# app/services/base.py
from abc import ABC, abstractmethod
from app.config.settings import Settings

class BaseService(ABC):
    def __init__(self, settings: Settings):
        self.settings = settings
        self._setup_directories()
    
    def _setup_directories(self):
        """Create necessary directories"""
        import os
        directories = [
            self.settings.upload_dir,
            self.settings.clips_dir,
            self.settings.temp_dir,
            self.settings.results_dir
        ]
        for directory in directories:
            os.makedirs(directory, exist_ok=True)
```

### 7. **Error Handling**
```python
# app/core/exceptions.py
from fastapi import HTTPException

class ClipperException(Exception):
    """Base exception for clipper operations"""
    pass

class TranscriptionError(ClipperException):
    """Error during audio transcription"""
    pass

class VideoProcessingError(ClipperException):
    """Error during video processing"""
    pass

# app/core/middleware.py
from fastapi import Request, HTTPException
from fastapi.responses import JSONResponse

async def exception_handler(request: Request, exc: ClipperException):
    return JSONResponse(
        status_code=500,
        content={"error": str(exc), "type": exc.__class__.__name__}
    )
```

### 8. **Testing Structure**
```python
# tests/conftest.py
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.config.settings import Settings

@pytest.fixture
def test_settings():
    return Settings(
        openai_api_key="test-key",
        upload_dir="test_data/uploads",
        clips_dir="test_data/clips"
    )

@pytest.fixture
def client():
    return TestClient(app)
```

## **Migration Strategy:**

1. **Phase 1**: Create new structure and move configuration
2. **Phase 2**: Refactor services into smaller, focused classes
3. **Phase 3**: Create API models and update endpoints
4. **Phase 4**: Add proper error handling and logging
5. **Phase 5**: Add comprehensive tests
6. **Phase 6**: Add Docker and deployment configuration

## **Benefits of New Structure:**

1. **Maintainability**: Clear separation of concerns
2. **Testability**: Each component can be tested independently
3. **Scalability**: Easy to add new features and services
4. **Configuration**: Centralized and type-safe configuration
5. **Error Handling**: Consistent error responses
6. **Documentation**: Auto-generated API docs with proper models
7. **Deployment**: Production-ready with Docker support

Would you like me to start implementing this refactored structure? 