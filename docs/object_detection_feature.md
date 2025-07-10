# Object Detection Feature for Smart Cropping

## Overview

The Clipper Academy backend now includes advanced object detection capabilities for smart video cropping. This feature automatically detects faces in video content and intelligently crops clips to center the talking person, ensuring optimal framing for social media platforms.

## Features

### Face Detection

- **Haar Cascade Detection**: Uses OpenCV's Haar Cascade classifier for reliable face detection
- **Multi-Face Support**: Detects and handles multiple faces in the same frame
- **Confidence Scoring**: Calculates confidence scores based on face size and position
- **Frame Analysis**: Analyzes multiple frames throughout the video for comprehensive detection
- **YOLOv8 Face Detection**: Uses a YOLOv8 model (default: yolov8n.pt, recommended: keremberke/yolov8n-face)

### Smart Cropping Modes

#### 1. Single Face Mode

- Centers on the most confident face detection
- Traditional smart cropping approach
- Best for videos with one main speaker

#### 2. Grid Layout Mode (Video Call Style)

- **Multiple Face Support**: Detects all faces and displays them in a grid layout
- **Dynamic Grid Sizing**: Automatically adjusts grid based on number of faces detected
- **Professional Layout**: Creates video call style layouts with proper spacing and padding

**Grid Layout Options:**

- **2 Faces**: Side-by-side layout with padding
- **3 Faces**: 2 on top, 1 centered on bottom
- **4 Faces**: 2x2 grid layout
- **5-6 Faces**: 3x2 grid layout
- **7-9 Faces**: 3x3 grid layout
- **10+ Faces**: Dynamic grid sizing with optimal spacing

### Layout Modes

#### `grid` (Default)

- Displays all detected faces in a video call style grid
- Perfect for group videos, interviews, and multi-person content
- Automatically adjusts grid size based on face count

#### `single`

- Shows only the most confident face detection
- Traditional smart cropping behavior
- Best for single speaker content

#### `auto`

- Automatically selects between grid and single based on face count
- Uses grid for 2+ faces, single for 1 face

## API Usage

### Request Parameters

```python
# Object Detection Parameters
enable_object_detection: bool = True          # Enable/disable object detection
object_detection_type: str = "face"          # Detection type (face, none)
smart_cropping_mode: str = "auto"            # Cropping mode (object_centered, center_crop, auto)
max_detection_frames: int = 10               # Frames to analyze (5-30)
face_layout_mode: str = "grid"               # Face layout mode (grid, single, auto)
```

### Example API Calls

#### Upload with Grid Layout

```bash
curl -X POST "http://localhost:8000/api/v1/clips/upload" \
  -F "file=@video.mp4" \
  -F "enable_object_detection=true" \
  -F "object_detection_type=face" \
  -F "face_layout_mode=grid" \
  -F "aspect_ratio=9:16"
```

#### URL Processing with Single Face Mode

```bash
curl -X POST "http://localhost:8000/api/v1/clips/url" \
  -F "url=https://www.tiktok.com/@user/video/1234567890" \
  -F "enable_object_detection=true" \
  -F "object_detection_type=face" \
  -F "face_layout_mode=single" \
  -F "aspect_ratio=9:16"
```

## Technical Implementation

### Object Detection Service

The `ObjectDetectionService` provides:

```python
class ObjectDetectionService(BaseService):
    def detect_faces(self, frame: np.ndarray) -> List[DetectionResult]:
        """Detect faces using Haar Cascade"""

    def calculate_face_layout(self, faces: List[DetectionResult],
                            target_width: int, target_height: int,
                            layout_mode: str = "grid") -> FaceLayoutResult:
        """Calculate optimal layout for multiple faces"""

    def analyze_video_objects(self, video_path: str,
                            detection_type: str = "face",
                            max_frames: int = 10,
                            layout_mode: str = "grid") -> Dict:
        """Analyze objects throughout video"""
```

### Video Processing Integration

The `VideoProcessingService` integrates object detection:

```python
def create_video_clip(self, video_path: str, start_time: float, end_time: float,
                     output_path: str, aspect_ratio: str = "9:16",
                     enable_object_detection: bool = True,
                     object_detection_type: str = "face",
                     max_detection_frames: int = 10,
                     face_layout_mode: str = "grid") -> str:
    """Create clip with smart cropping and face layout"""
```

### Grid Layout Filter Generation

The service generates sophisticated FFmpeg filters for grid layouts:

```python
def _create_grid_layout_filter(self, crop_params: Dict,
                              target_width: int, target_height: int) -> str:
    """Create FFmpeg filter for video call style grid layout"""
```

## Use Cases

### 1. Group Videos & Interviews

- **Perfect for**: Podcasts, group discussions, interviews
- **Layout**: Grid mode automatically arranges all participants
- **Result**: Professional video call style output

### 2. Single Speaker Content

- **Perfect for**: Solo presentations, monologues, tutorials
- **Layout**: Single mode centers on the main speaker
- **Result**: Clean, focused framing

### 3. Dynamic Content

- **Perfect for**: Videos with varying numbers of people
- **Layout**: Auto mode adapts based on face count
- **Result**: Optimal layout for each segment

## Configuration

### Settings

```python
# app/config/settings.py
class Settings(BaseSettings):
    # Object Detection Settings
    smart_cropping_enabled: bool = True
    default_object_detection_type: str = "face"
    default_face_layout_mode: str = "grid"
    max_detection_frames: int = 10

    # Video Processing
    min_clip_duration: int = 10
    max_clip_duration: int = 120
    video_quality_crf: int = 23
    ffmpeg_preset: str = "medium"
```

### Environment Variables

```bash
# Object Detection
SMART_CROPPING_ENABLED=true
DEFAULT_OBJECT_DETECTION_TYPE=face
DEFAULT_FACE_LAYOUT_MODE=grid
MAX_DETECTION_FRAMES=10
```

## Performance Considerations

### Processing Time

- **Face Detection**: ~2-5 seconds per clip (depending on frame count)
- **Grid Layout**: Additional 1-2 seconds for complex layouts
- **Total Overhead**: ~3-7 seconds per clip

### Memory Usage

- **Frame Analysis**: Temporary storage of detection frames
- **Grid Processing**: Minimal additional memory for layout calculations
- **Cleanup**: Automatic cleanup of temporary files

### Optimization Tips

1. **Reduce Detection Frames**: Use 5-10 frames for faster processing
2. **Choose Layout Mode**: Use 'single' for faster processing with one speaker
3. **Batch Processing**: Process multiple clips in parallel

## Error Handling

### Detection Failures

- **No Faces Detected**: Falls back to center crop
- **Low Confidence**: Uses center crop with warning
- **Processing Errors**: Graceful fallback to traditional cropping

### Layout Failures

- **Grid Creation Error**: Falls back to single face mode
- **FFmpeg Filter Error**: Uses center crop
- **Memory Issues**: Reduces grid complexity

## Testing

### Unit Tests

```bash
# Run object detection tests
pytest tests/unit/test_services/test_object_detection.py -v

# Run video processing tests
pytest tests/unit/test_services/test_video_processing.py -v
```

### Integration Tests

```bash
# Run API integration tests
pytest tests/integration/test_api/test_clips_endpoints.py -v
```

## Future Enhancements

### Planned Features

1. **Real-time Face Tracking**: Track faces across frames for smoother layouts
2. **Custom Grid Templates**: User-defined grid layouts
3. **Face Recognition**: Identify and prioritize specific speakers
4. **Emotion Detection**: Optimize layouts based on emotional content
5. **Advanced Filtering**: More sophisticated FFmpeg filters for better quality

### Performance Improvements

1. **GPU Acceleration**: CUDA support for faster detection
2. **Parallel Processing**: Multi-threaded face detection
3. **Caching**: Cache detection results for repeated processing
4. **Optimized Models**: Lighter detection models for faster processing

## Troubleshooting

### Common Issues

#### No Faces Detected

```bash
# Check if Haar Cascade is loaded
python -c "import cv2; print(cv2.data.haarcascades)"
```

#### Grid Layout Not Working

```bash
# Verify FFmpeg version supports complex filters
ffmpeg -filters | grep -E "(split|hstack|vstack|pad)"
```

#### Performance Issues

```bash
# Reduce detection frames
max_detection_frames=5

# Use single mode for faster processing
face_layout_mode=single
```

### Debug Mode

```python
# Enable debug logging
import logging
logging.getLogger('app.services.object_detection').setLevel(logging.DEBUG)
```

## Support

For issues and questions:

1. Check the logs for detailed error messages
2. Verify FFmpeg installation and version
3. Test with different video formats
4. Try different layout modes
5. Contact support with specific error details

**Update 2025:** Clipper Academy now uses YOLOv8 for face detection by default. For best results, use a face-specific YOLOv8 model such as [keremberke/yolov8n-face](https://huggingface.co/keremberke/yolov8n-face). You can configure a custom weights file via the `YOLOV8_FACE_WEIGHTS` setting in your `.env` file.
