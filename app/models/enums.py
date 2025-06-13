from enum import Enum


class AspectRatio(str, Enum):
    """Supported aspect ratios for video clips"""
    NINE_SIXTEEN = "9:16"      # TikTok, Instagram Reels, YouTube Shorts
    SIXTEEN_NINE = "16:9"      # YouTube horizontal
    ONE_ONE = "1:1"            # Square (Instagram posts)
    ORIGINAL = "original"      # Keep original aspect ratio


class ProcessingStatus(str, Enum):
    """Processing status values"""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class Platform(str, Enum):
    """Supported social media platforms"""
    TIKTOK = "tiktok"
    INSTAGRAM = "instagram"
    YOUTUBE = "youtube"
    UNKNOWN = "unknown"


class ClipQuality(str, Enum):
    """Video quality settings"""
    LOW = "low"           # 480p
    MEDIUM = "medium"     # 720p
    HIGH = "high"         # 1080p
    ULTRA = "ultra"       # 4K


class ZapCapLanguage(str, Enum):
    """Supported languages for ZapCap captions"""
    ENGLISH = "en"
    INDONESIAN = "id"
    SPANISH = "es"
    FRENCH = "fr"
    GERMAN = "de"
    PORTUGUESE = "pt"
    ITALIAN = "it"
    DUTCH = "nl"
    RUSSIAN = "ru"
    JAPANESE = "ja"
    KOREAN = "ko"
    CHINESE_SIMPLIFIED = "zh-CN"
    CHINESE_TRADITIONAL = "zh-TW"


class ContentCategory(str, Enum):
    """Content categories for classification"""
    EDUCATION = "education"
    ENTERTAINMENT = "entertainment"
    MOTIVATION = "motivation"
    COMEDY = "comedy"
    TUTORIAL = "tutorial"
    REVIEW = "review"
    NEWS = "news"
    LIFESTYLE = "lifestyle"
    GAMING = "gaming"
    MUSIC = "music"
    SPORTS = "sports"
    COOKING = "cooking"
    TRAVEL = "travel"
    TECHNOLOGY = "technology"
    BUSINESS = "business"
    HEALTH = "health"
    FITNESS = "fitness"
    BEAUTY = "beauty"
    FASHION = "fashion"
    UNCATEGORIZED = "uncategorized"


# Constants
MIN_CLIP_DURATION = 10  # seconds
MAX_CLIP_DURATION = 120  # seconds
DEFAULT_MAX_CLIPS = 5
DEFAULT_MAX_FRAMES = 15
MAX_FILE_SIZE = 500 * 1024 * 1024  # 500MB
SUPPORTED_VIDEO_FORMATS = ['.mp4', '.mov', '.avi', '.mkv', '.webm']
SUPPORTED_AUDIO_FORMATS = ['.mp3', '.wav', '.m4a', '.aac'] 