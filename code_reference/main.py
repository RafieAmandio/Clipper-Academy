from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional
import logging
import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Debug: Print OpenAI related environment variables
print("=== ENVIRONMENT DEBUG ===")
for key, value in os.environ.items():
    if "OPENAI" in key:
        masked_value = f"{value[:8]}...{value[-4:]}" if value and len(value) > 12 else "***"
        print(f"{key}: {masked_value}")
print("========================")

from auto_clipper_service import get_auto_clipper_service

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Auto Clipper API",
    description="AI-powered video clipping service with transcription and analysis",
    version="1.0.0"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
async def root():
    return {"message": "Auto Clipper API is running"}

@app.post("/clip/upload")
async def clip_from_upload(
    video: UploadFile = File(...),
    use_zapcap: bool = Form(False),
    zapcap_template_id: Optional[str] = Form(None),
    aspect_ratio: str = Form("9:16")
):
    """
    Create clips from uploaded video file
    
    - **video**: Video file to process
    - **use_zapcap**: Whether to add captions using ZapCap service
    - **zapcap_template_id**: Custom ZapCap template ID (optional)
    - **aspect_ratio**: Output aspect ratio - "9:16" (TikTok/Reels), "16:9" (YouTube), "1:1" (Square), "original"
    """
    try:
        logger.info(f"Processing uploaded video: {video.filename}")
        
        # Validate file type
        if not video.filename.lower().endswith(('.mp4', '.mov', '.avi', '.mkv', '.webm')):
            raise HTTPException(status_code=400, detail="Unsupported video format")
        
        # Validate aspect ratio
        valid_ratios = ["9:16", "16:9", "1:1", "original"]
        if aspect_ratio not in valid_ratios:
            raise HTTPException(status_code=400, detail=f"Invalid aspect ratio. Must be one of: {valid_ratios}")
        
        auto_clipper_service = get_auto_clipper_service()
        result = await auto_clipper_service.process_video(
            video_input=video,
            use_zapcap=use_zapcap,
            zapcap_template_id=zapcap_template_id,
            aspect_ratio=aspect_ratio
        )
        
        return JSONResponse(content=result)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error processing uploaded video: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to process video: {str(e)}")

@app.post("/clip/url")
async def clip_from_url(
    url: str = Form(...),
    use_zapcap: bool = Form(False),
    zapcap_template_id: Optional[str] = Form(None),
    aspect_ratio: str = Form("9:16")
):
    """
    Create clips from social media URL (TikTok, Instagram)
    
    - **url**: Social media URL to download and process
    - **use_zapcap**: Whether to add captions using ZapCap service
    - **zapcap_template_id**: Custom ZapCap template ID (optional)
    - **aspect_ratio**: Output aspect ratio - "9:16" (TikTok/Reels), "16:9" (YouTube), "1:1" (Square), "original"
    """
    try:
        logger.info(f"Processing video from URL: {url}")
        
        # Basic URL validation
        if not url.startswith(('http://', 'https://')):
            raise HTTPException(status_code=400, detail="Invalid URL format")
        
        # Validate aspect ratio
        valid_ratios = ["9:16", "16:9", "1:1", "original"]
        if aspect_ratio not in valid_ratios:
            raise HTTPException(status_code=400, detail=f"Invalid aspect ratio. Must be one of: {valid_ratios}")
        
        auto_clipper_service = get_auto_clipper_service()
        result = await auto_clipper_service.process_video(
            video_input=url,
            use_zapcap=use_zapcap,
            zapcap_template_id=zapcap_template_id,
            aspect_ratio=aspect_ratio
        )
        
        return JSONResponse(content=result)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error processing video from URL: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to process video: {str(e)}")

@app.post("/clip/filepath")
async def clip_from_filepath(
    file_path: str = Form(...),
    use_zapcap: bool = Form(False),
    zapcap_template_id: Optional[str] = Form(None),
    aspect_ratio: str = Form("9:16")
):
    """
    Create clips from local file path
    
    - **file_path**: Local path to video file
    - **use_zapcap**: Whether to add captions using ZapCap service
    - **zapcap_template_id**: Custom ZapCap template ID (optional)
    - **aspect_ratio**: Output aspect ratio - "9:16" (TikTok/Reels), "16:9" (YouTube), "1:1" (Square), "original"
    """
    try:
        logger.info(f"Processing video from file path: {file_path}")
        
        # Validate file exists
        if not os.path.exists(file_path):
            raise HTTPException(status_code=404, detail="Video file not found")
        
        # Validate file type
        if not file_path.lower().endswith(('.mp4', '.mov', '.avi', '.mkv', '.webm')):
            raise HTTPException(status_code=400, detail="Unsupported video format")
        
        # Validate aspect ratio
        valid_ratios = ["9:16", "16:9", "1:1", "original"]
        if aspect_ratio not in valid_ratios:
            raise HTTPException(status_code=400, detail=f"Invalid aspect ratio. Must be one of: {valid_ratios}")
        
        auto_clipper_service = get_auto_clipper_service()
        result = await auto_clipper_service.process_video(
            video_input=file_path,
            use_zapcap=use_zapcap,
            zapcap_template_id=zapcap_template_id,
            aspect_ratio=aspect_ratio
        )
        
        return JSONResponse(content=result)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error processing video from file path: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to process video: {str(e)}")

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "service": "Auto Clipper API",
        "version": "1.0.0",
        "directories": {
            "clips": os.path.exists("clips"),
            "temp": os.path.exists("temp"),
            "results": os.path.exists("results"),
            "uploads": os.path.exists("uploads")
        }
    }

@app.get("/info")
async def get_service_info():
    """Get service information and features"""
    return {
        "service": "Auto Clipper API",
        "version": "1.0.0",
        "description": "AI-powered video clipping service with transcription and segment analysis",
        "features": [
            "Video upload processing",
            "Social media URL downloading (TikTok, Instagram)",
            "Local file path processing",
            "AI transcription with timestamps (Whisper)",
            "Parallel chunk processing for large files",
            "AI-powered clip segment analysis (GPT-4)",
            "Multiple aspect ratio support (9:16, 16:9, 1:1, original)",
            "ZapCap integration for automated captions",
            "Automatic 30-60 second clip generation",
            "Smart clip titling and engagement scoring"
        ],
        "requirements": {
            "openai_api_key": "Required for transcription and AI analysis",
            "zapcap_api_key": "Optional for automated captioning",
            "ffmpeg": "Required for video/audio processing",
            "yt-dlp": "Required for social media URL downloads"
        },
        "performance": {
            "parallel_transcription": "Multiple audio chunks processed simultaneously",
            "parallel_zapcap": "Multiple clips captioned simultaneously",
            "max_concurrent_chunks": "Up to 5 chunks in parallel",
            "large_file_support": "Automatic chunking for files >25MB"
        }
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000) 