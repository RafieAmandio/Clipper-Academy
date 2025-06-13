import os
import tempfile
import shutil
import subprocess
import json
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional, Union, Tuple, TYPE_CHECKING
from io import BytesIO
import cv2
import numpy as np
from openai import OpenAI
import re
import logging
import asyncio
import concurrent.futures

if TYPE_CHECKING:
    from fastapi import UploadFile
else:
    try:
        from fastapi import UploadFile
    except ImportError:
        UploadFile = None

from fastapi import HTTPException

from zapcap_service import zapcap_service
from content_analyzer import ContentAnalyzer

logger = logging.getLogger(__name__)

class AutoClipperService:
    """Service for automatically creating short clips from videos with AI analysis"""
    
    def __init__(self, openai_api_key: str = None):
        self.openai_api_key = openai_api_key or os.getenv("OPENAI_API_KEY")
        if not self.openai_api_key:
            logger.warning("OpenAI API key not provided. Service will not work until API key is set.")
            self.client = None
            self.content_analyzer = None
        else:
            # Debug: Print masked API key
            masked_key = f"{self.openai_api_key[:8]}...{self.openai_api_key[-4:]}" if len(self.openai_api_key) > 12 else "***"
            logger.info(f"OpenAI API key loaded: {masked_key}")
            self.client = OpenAI(api_key=self.openai_api_key)
            self.content_analyzer = ContentAnalyzer(openai_api_key=self.openai_api_key)
        
        # Create output directories
        self.clips_dir = "clips"
        self.temp_dir = "temp"
        os.makedirs(self.clips_dir, exist_ok=True)
        os.makedirs(self.temp_dir, exist_ok=True)
    
    def _ensure_client(self):
        """Ensure OpenAI client is initialized"""
        if self.client is None:
            self.openai_api_key = os.getenv("OPENAI_API_KEY")
            if not self.openai_api_key:
                raise ValueError("OpenAI API key is required but not found in environment variables")
            
            # Debug: Print masked API key
            masked_key = f"{self.openai_api_key[:8]}...{self.openai_api_key[-4:]}" if len(self.openai_api_key) > 12 else "***"
            logger.info(f"Initializing OpenAI client with key: {masked_key}")
            self.client = OpenAI(api_key=self.openai_api_key)
            self.content_analyzer = ContentAnalyzer(openai_api_key=self.openai_api_key)
    
    def format_timestamp(self, seconds: float) -> str:
        """Convert seconds to MM:SS format"""
        minutes = int(seconds // 60)
        seconds = int(seconds % 60)
        return f"{minutes:02d}:{seconds:02d}"
    
    async def save_upload_file(self, upload_file) -> str:
        """Save uploaded file to temp directory"""
        try:
            filename = getattr(upload_file, 'filename', 'video.mp4')
            file_extension = os.path.splitext(filename or "video.mp4")[1]
            temp_file_path = os.path.join(self.temp_dir, f"upload_{int(datetime.now().timestamp())}{file_extension}")
            
            with open(temp_file_path, 'wb') as temp_file:
                content = await upload_file.read()
                temp_file.write(content)
            
            logger.info(f"File saved to: {temp_file_path}")
            return temp_file_path
            
        except Exception as e:
            logger.error(f"Error saving upload file: {e}")
            raise HTTPException(status_code=500, detail=f"Failed to save uploaded file: {e}")
    
    def get_video_from_url(self, url: str) -> str:
        """Download video from social media URL"""
        try:
            self._ensure_client()
            platform = self.content_analyzer.detect_platform(url)
            post_id = self.content_analyzer.extract_post_id_from_url(url, platform) or 'unknown'
            
            # Use content analyzer to download video
            data, video_file, post_dir, platform, post_id, metrics = self.content_analyzer.scrape_social_media(
                url, self.temp_dir, download_media=True
            )
            
            if not video_file or not os.path.exists(video_file):
                raise HTTPException(status_code=404, detail="Failed to download video from URL")
            
            logger.info(f"Downloaded video from {platform}: {video_file}")
            return video_file
            
        except Exception as e:
            logger.error(f"Error downloading video from URL: {e}")
            raise HTTPException(status_code=500, detail=f"Failed to download video: {e}")
    
    def extract_audio_for_transcription(self, video_path: str) -> str:
        """Extract audio from video for transcription"""
        try:
            audio_path = os.path.join(self.temp_dir, f"audio_{int(datetime.now().timestamp())}.wav")
            
            # Extract audio with ffmpeg
            cmd = [
                'ffmpeg', '-y', '-i', video_path, '-vn',
                '-acodec', 'pcm_s16le', '-ar', '16000', '-ac', '1',
                audio_path
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            logger.info(f"Audio extracted to: {audio_path}")
            return audio_path
            
        except subprocess.CalledProcessError as e:
            logger.error(f"FFmpeg error: {e.stderr}")
            raise HTTPException(status_code=500, detail=f"Failed to extract audio: {e.stderr}")
        except Exception as e:
            logger.error(f"Error extracting audio: {e}")
            raise HTTPException(status_code=500, detail=f"Failed to extract audio: {e}")
    
    def split_audio_for_transcription(self, audio_path: str, max_size_mb: int = 20) -> List[str]:
        """Split large audio files into smaller chunks for transcription"""
        try:
            import math
            
            # Get audio file size
            file_size = os.path.getsize(audio_path)
            max_size_bytes = max_size_mb * 1024 * 1024
            
            if file_size <= max_size_bytes:
                return [audio_path]  # No splitting needed
            
            # Calculate number of chunks needed
            num_chunks = math.ceil(file_size / max_size_bytes)
            logger.info(f"Audio file ({file_size / (1024*1024):.1f}MB) exceeds limit, splitting into {num_chunks} chunks")
            
            # Get video duration to calculate chunk duration
            video_info = self.get_video_info_from_audio(audio_path)
            total_duration = video_info.get('duration', 0)
            chunk_duration = total_duration / num_chunks
            
            chunk_paths = []
            for i in range(num_chunks):
                start_time = i * chunk_duration
                end_time = min((i + 1) * chunk_duration, total_duration)
                
                chunk_filename = f"audio_chunk_{i}_{int(datetime.now().timestamp())}.wav"
                chunk_path = os.path.join(self.temp_dir, chunk_filename)
                
                # Extract audio chunk
                cmd = [
                    'ffmpeg', '-y', '-i', audio_path,
                    '-ss', str(start_time), '-to', str(end_time),
                    '-vn', '-acodec', 'pcm_s16le', '-ar', '16000', '-ac', '1',
                    chunk_path
                ]
                
                result = subprocess.run(cmd, capture_output=True, text=True, check=True)
                chunk_paths.append(chunk_path)
                
                chunk_size = os.path.getsize(chunk_path)
                logger.info(f"Created chunk {i+1}/{num_chunks}: {chunk_size / (1024*1024):.1f}MB ({start_time:.1f}s - {end_time:.1f}s)")
            
            return chunk_paths
            
        except Exception as e:
            logger.error(f"Error splitting audio: {e}")
            raise HTTPException(status_code=500, detail=f"Failed to split audio: {e}")
    
    def get_video_info_from_audio(self, audio_path: str) -> Dict:
        """Get duration from audio file"""
        try:
            cmd = [
                'ffprobe', '-v', 'quiet', '-print_format', 'json',
                '-show_format', audio_path
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            info = json.loads(result.stdout)
            
            duration = float(info['format']['duration'])
            return {'duration': duration}
            
        except Exception as e:
            logger.error(f"Error getting audio info: {e}")
            return {'duration': 0}
    
    def transcribe_chunk_sync(self, chunk_path: str, chunk_index: int, start_offset: float) -> Dict:
        """Synchronous transcription of a single chunk for parallel processing"""
        try:
            logger.info(f"Transcribing chunk {chunk_index + 1}...")
            
            with open(chunk_path, "rb") as audio_file:
                chunk_transcript = self.client.audio.transcriptions.create(
                    model="whisper-1",
                    file=audio_file,
                    response_format="verbose_json",
                    timestamp_granularities=["word"]
                )
            
            # Debug: Print raw response for this chunk
            logger.info(f"=== RAW OPENAI RESPONSE FOR CHUNK {chunk_index + 1} ===")
            logger.info(f"Response type: {type(chunk_transcript)}")
            logger.info(f"Response object: {chunk_transcript}")
            
            chunk_data_dict = chunk_transcript.model_dump()
            
            # Debug: Print processed data for this chunk
            logger.info(f"=== PROCESSED DATA FOR CHUNK {chunk_index + 1} ===")
            logger.info(f"Data dict type: {type(chunk_data_dict)}")
            logger.info(f"Data dict keys: {list(chunk_data_dict.keys()) if chunk_data_dict else 'None'}")
            logger.info(f"Data dict: {chunk_data_dict}")
            logger.info("=" * 50)
            
            # Skip if transcript is empty or None
            if not chunk_data_dict:
                logger.warning(f"Empty transcript for chunk {chunk_index + 1}, skipping...")
                return None
            
            # Adjust timestamps by adding chunk start offset
            segments = chunk_data_dict.get('segments', [])
            if segments:
                for segment in segments:
                    if segment:  # Additional null check
                        segment['start'] += start_offset
                        segment['end'] += start_offset
            
            # Handle words with null checks
            words = chunk_data_dict.get('words', [])
            if words:
                for word in words:
                    if word:  # Additional null check
                        word['start'] += start_offset
                        word['end'] += start_offset
            
            # Return processed chunk data
            result = {
                'chunk_index': chunk_index,
                'segments': segments or [],
                'words': words or [],
                'text': chunk_data_dict.get('text', ''),
                'success': True
            }
            
            logger.info(f"Chunk {chunk_index + 1} processed: {len(segments or [])} segments, {len(words or [])} words")
            return result
            
        except Exception as chunk_error:
            logger.error(f"Error transcribing chunk {chunk_index + 1}: {chunk_error}")
            return {
                'chunk_index': chunk_index,
                'segments': [],
                'words': [],
                'text': '',
                'success': False,
                'error': str(chunk_error)
            }
    
    async def transcribe_chunks_parallel(self, chunk_info: List[Dict]) -> List[Dict]:
        """Transcribe multiple audio chunks in parallel"""
        logger.info(f"Starting parallel transcription of {len(chunk_info)} chunks...")
        
        # Create tasks for parallel execution
        loop = asyncio.get_event_loop()
        with concurrent.futures.ThreadPoolExecutor(max_workers=min(5, len(chunk_info))) as executor:
            # Create futures for each chunk
            futures = []
            for i, chunk_data in enumerate(chunk_info):
                future = loop.run_in_executor(
                    executor,
                    self.transcribe_chunk_sync,
                    chunk_data['path'],
                    i,
                    chunk_data['start_offset']
                )
                futures.append(future)
            
            # Wait for all chunks to complete
            results = await asyncio.gather(*futures, return_exceptions=True)
            
            # Process results
            successful_results = []
            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    logger.error(f"Chunk {i + 1} failed with exception: {result}")
                elif result and result.get('success', False):
                    successful_results.append(result)
                else:
                    logger.warning(f"Chunk {i + 1} returned empty or failed result")
            
            logger.info(f"Parallel transcription completed: {len(successful_results)}/{len(chunk_info)} chunks successful")
            return successful_results
    
    async def transcribe_with_timestamps(self, audio_path: str) -> Dict:
        """Transcribe audio with word-level timestamps, handling large files by chunking"""
        try:
            self._ensure_client()
            
            # Debug: Print current API key being used
            current_key = self.client.api_key if self.client else "None"
            masked_key = f"{current_key[:8]}...{current_key[-4:]}" if current_key and len(current_key) > 12 else "***"
            logger.info(f"Making transcription API call with key: {masked_key}")
            
            # Split audio if too large
            audio_chunks = self.split_audio_for_transcription(audio_path)
            
            if len(audio_chunks) == 1:
                # Single file transcription
                with open(audio_chunks[0], "rb") as audio_file:
                    transcript = self.client.audio.transcriptions.create(
                        model="whisper-1",
                        file=audio_file,
                        response_format="verbose_json",
                        timestamp_granularities=["word"]
                    )
                
                # Debug: Print raw response for single file
                logger.info(f"=== RAW OPENAI RESPONSE (SINGLE FILE) ===")
                logger.info(f"Response type: {type(transcript)}")
                logger.info(f"Response object: {transcript}")
                
                result = transcript.model_dump()
                
                # Debug: Print processed data for single file
                logger.info(f"=== PROCESSED DATA (SINGLE FILE) ===")
                logger.info(f"Data dict type: {type(result)}")
                logger.info(f"Data dict keys: {list(result.keys()) if result else 'None'}")
                logger.info(f"Data dict: {result}")
                logger.info("=" * 50)
                
                logger.info("Transcription completed with timestamps")
                return result
            
            else:
                # Multi-chunk transcription with parallel processing
                logger.info(f"Transcribing {len(audio_chunks)} audio chunks in parallel...")
                
                # Get chunk durations for timestamp adjustment
                chunk_info = []
                total_duration = 0
                
                for chunk_path in audio_chunks:
                    chunk_duration_info = self.get_video_info_from_audio(chunk_path)
                    chunk_duration = chunk_duration_info.get('duration', 0)
                    chunk_info.append({
                        'path': chunk_path,
                        'start_offset': total_duration,
                        'duration': chunk_duration
                    })
                    total_duration += chunk_duration
                
                # Transcribe all chunks in parallel
                chunk_results = await self.transcribe_chunks_parallel(chunk_info)
                
                if not chunk_results:
                    raise ValueError("All audio chunks failed to transcribe")
                
                # Merge results from all successful chunks
                all_segments = []
                all_words = []
                full_text = ""
                
                # Sort results by chunk index to maintain order
                chunk_results.sort(key=lambda x: x.get('chunk_index', 0))
                
                for result in chunk_results:
                    # Add segments
                    all_segments.extend(result.get('segments', []))
                    
                    # Add words
                    all_words.extend(result.get('words', []))
                    
                    # Append text
                    chunk_text = result.get('text', '')
                    if chunk_text:
                        if full_text:
                            full_text += " " + chunk_text
                        else:
                            full_text = chunk_text
                
                logger.info(f"Parallel transcription successful: {len(chunk_results)} chunks processed")
                
                # Clean up chunk files
                for chunk_path in audio_chunks:
                    if chunk_path != audio_path and os.path.exists(chunk_path):
                        try:
                            os.remove(chunk_path)
                            logger.info(f"Cleaned up audio chunk: {chunk_path}")
                        except OSError:
                            pass
                
                # Return merged transcript
                merged_transcript = {
                    'text': full_text,
                    'segments': all_segments,
                    'words': all_words,
                    'language': 'en'  # Default language
                }
                
                logger.info(f"Multi-chunk transcription completed: {len(all_segments)} segments, {len(all_words)} words")
                return merged_transcript
                
        except Exception as e:
            logger.error(f"Error transcribing audio: {e}")
            raise HTTPException(status_code=500, detail=f"Failed to transcribe audio: {e}")
    
    def analyze_clip_segments(self, transcript_data: Dict, video_duration: float) -> List[Dict]:
        """Use AI to analyze transcript and identify clip-worthy segments"""
        try:
            self._ensure_client()
            # Prepare transcript text with timestamps
            words = transcript_data.get('words', [])
            if not words:
                # Fallback to segments if words not available
                segments = transcript_data.get('segments', [])
                transcript_text = ""
                for segment in segments:
                    start_time = self.format_timestamp(segment['start'])
                    end_time = self.format_timestamp(segment['end'])
                    text = segment['text'].strip()
                    transcript_text += f"[{start_time}-{end_time}] {text}\n"
            else:
                transcript_text = ""
                for word in words:
                    start_time = self.format_timestamp(word['start'])
                    end_time = self.format_timestamp(word['end'])
                    text = word['word'].strip()
                    transcript_text += f"[{start_time}-{end_time}] {text}\n"
            
            # AI prompt for clip analysis
            prompt = f"""
            Analyze this video transcript with timestamps and identify the most engaging segments that would make good TikTok clips (30-60 seconds each).

            Video Duration: {self.format_timestamp(video_duration)}

            Transcript with timestamps:
            {transcript_text}

            Instructions:
            1. Identify 2-5 segments that would make compelling short clips
            2. Each segment should be 30-60 seconds long
            3. Look for: hooks, punchlines, key moments, emotional peaks, educational insights, entertaining parts
            4. Provide start and end times in MM:SS format
            5. Give each clip a catchy title and brief description

            Return ONLY a JSON array in this exact format:
            [
                {{
                    "title": "Catchy clip title",
                    "description": "Brief description of why this segment is engaging",
                    "start_time": "MM:SS",
                    "end_time": "MM:SS",
                    "duration": 45,
                    "engagement_score": 8.5
                }}
            ]
            """
            
            response = self.client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": "You are a video editing expert who identifies engaging content segments."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3
            )
            
            # Parse AI response
            response_text = response.choices[0].message.content.strip()
            
            # Extract JSON from response
            json_match = re.search(r'\[.*\]', response_text, re.DOTALL)
            if json_match:
                clips_data = json.loads(json_match.group())
                logger.info(f"AI identified {len(clips_data)} potential clips")
                return clips_data
            else:
                raise ValueError("Could not parse AI response")
                
        except Exception as e:
            logger.error(f"Error analyzing clip segments: {e}")
            raise HTTPException(status_code=500, detail=f"Failed to analyze clip segments: {e}")
    
    def time_to_seconds(self, time_str: str) -> float:
        """Convert MM:SS format to seconds"""
        try:
            parts = time_str.split(':')
            if len(parts) == 2:
                minutes, seconds = parts
                return int(minutes) * 60 + int(seconds)
            elif len(parts) == 3:
                hours, minutes, seconds = parts
                return int(hours) * 3600 + int(minutes) * 60 + int(seconds)
            else:
                return float(time_str)
        except:
            return 0.0
    
    def get_video_info(self, video_path: str) -> Dict:
        """Get video information using ffprobe"""
        try:
            cmd = [
                'ffprobe', '-v', 'quiet', '-print_format', 'json',
                '-show_format', '-show_streams', video_path
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            info = json.loads(result.stdout)
            
            video_stream = None
            for stream in info['streams']:
                if stream['codec_type'] == 'video':
                    video_stream = stream
                    break
            
            duration = float(info['format']['duration'])
            width = int(video_stream['width']) if video_stream else 1920
            height = int(video_stream['height']) if video_stream else 1080
            
            return {
                'duration': duration,
                'width': width,
                'height': height,
                'aspect_ratio': width / height
            }
            
        except Exception as e:
            logger.error(f"Error getting video info: {e}")
            raise HTTPException(status_code=500, detail=f"Failed to get video info: {e}")
    
    def create_clip(self, video_path: str, start_time: float, end_time: float, 
                   output_path: str, aspect_ratio: str = "9:16") -> str:
        """Create a video clip with specified aspect ratio"""
        try:
            cmd = ['ffmpeg', '-y', '-i', video_path]
            
            # Set time range
            cmd.extend(['-ss', str(start_time), '-to', str(end_time)])
            
            # Handle different aspect ratios
            if aspect_ratio == "original":
                # Keep original format but re-encode for consistency
                cmd.extend(['-c:v', 'libx264', '-preset', 'fast', '-crf', '23'])
                cmd.extend(['-c:a', 'aac', '-b:a', '128k'])
            
            elif aspect_ratio == "9:16":  # TikTok/Instagram Reels/YouTube Shorts
                video_info = self.get_video_info(video_path)
                
                if video_info['aspect_ratio'] > (9/16):
                    # Video is wider than 9:16, need to crop sides
                    target_width = int(video_info['height'] * (9/16))
                    x_offset = (video_info['width'] - target_width) // 2
                    filter_complex = f"crop={target_width}:{video_info['height']}:{x_offset}:0,scale=1080:1920"
                else:
                    # Video is taller than 9:16 or already correct, scale and pad if needed
                    filter_complex = "scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2:black"
                
                cmd.extend(['-vf', filter_complex])
                cmd.extend(['-c:v', 'libx264', '-preset', 'fast', '-crf', '23'])
                cmd.extend(['-c:a', 'aac', '-b:a', '128k'])
            
            elif aspect_ratio == "16:9":  # YouTube horizontal
                video_info = self.get_video_info(video_path)
                
                if video_info['aspect_ratio'] < (16/9):
                    # Video is taller than 16:9, need to crop top/bottom
                    target_height = int(video_info['width'] * (9/16))
                    y_offset = (video_info['height'] - target_height) // 2
                    filter_complex = f"crop={video_info['width']}:{target_height}:0:{y_offset},scale=1920:1080"
                else:
                    # Video is wider than 16:9 or already correct, scale and pad if needed
                    filter_complex = "scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2:black"
                
                cmd.extend(['-vf', filter_complex])
                cmd.extend(['-c:v', 'libx264', '-preset', 'fast', '-crf', '23'])
                cmd.extend(['-c:a', 'aac', '-b:a', '128k'])
            
            elif aspect_ratio == "1:1":  # Square (Instagram posts)
                video_info = self.get_video_info(video_path)
                
                # Always crop to square from center
                min_dimension = min(video_info['width'], video_info['height'])
                x_offset = (video_info['width'] - min_dimension) // 2
                y_offset = (video_info['height'] - min_dimension) // 2
                filter_complex = f"crop={min_dimension}:{min_dimension}:{x_offset}:{y_offset},scale=1080:1080"
                
                cmd.extend(['-vf', filter_complex])
                cmd.extend(['-c:v', 'libx264', '-preset', 'fast', '-crf', '23'])
                cmd.extend(['-c:a', 'aac', '-b:a', '128k'])
            
            else:
                raise ValueError(f"Unsupported aspect ratio: {aspect_ratio}")
            
            cmd.append(output_path)
            
            logger.info(f"Creating clip with {aspect_ratio} aspect ratio: {start_time}s to {end_time}s")
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            
            if os.path.exists(output_path):
                logger.info(f"Clip created successfully: {output_path}")
                return output_path
            else:
                raise FileNotFoundError("Clip file was not created")
                
        except subprocess.CalledProcessError as e:
            logger.error(f"FFmpeg error creating clip: {e.stderr}")
            raise HTTPException(status_code=500, detail=f"Failed to create clip: {e.stderr}")
        except Exception as e:
            logger.error(f"Error creating clip: {e}")
            raise HTTPException(status_code=500, detail=f"Failed to create clip: {e}")
    
    async def process_video(self, video_input: Union[str, "UploadFile"], 
                          use_zapcap: bool = False, 
                          zapcap_template_id: Optional[str] = None,
                          aspect_ratio: str = "9:16") -> Dict:
        """Main processing function for auto clipping"""
        temp_files = []
        
        try:
            # Step 1: Get video file
            # Check if it's an UploadFile-like object (has filename and read method)
            if hasattr(video_input, 'filename') and hasattr(video_input, 'read'):
                logger.info(f"Processing uploaded file: {video_input.filename}")
                video_path = await self.save_upload_file(video_input)
                temp_files.append(video_path)
            elif isinstance(video_input, str) and video_input.startswith(('http://', 'https://')):
                logger.info(f"Processing URL: {video_input}")
                video_path = self.get_video_from_url(video_input)
                temp_files.append(video_path)
            else:
                logger.info(f"Processing file path: {video_input}")
                if not os.path.exists(video_input):
                    raise HTTPException(status_code=404, detail="Video file not found")
                video_path = video_input
            
            # Step 2: Get video information
            video_info = self.get_video_info(video_path)
            logger.info(f"Video info: {video_info['duration']:.1f}s, {video_info['width']}x{video_info['height']}")
            
            # Step 3: Extract audio and transcribe
            audio_path = self.extract_audio_for_transcription(video_path)
            temp_files.append(audio_path)
            
            # Get audio chunks for potential cleanup
            audio_chunks = self.split_audio_for_transcription(audio_path)
            # Add chunks to temp_files for cleanup (except original audio_path which is already added)
            for chunk_path in audio_chunks:
                if chunk_path != audio_path:
                    temp_files.append(chunk_path)
            
            transcript_data = await self.transcribe_with_timestamps(audio_path)
            
            # Step 4: Analyze for clip segments
            clip_segments = self.analyze_clip_segments(transcript_data, video_info['duration'])
            
            if not clip_segments:
                raise HTTPException(status_code=400, detail="No suitable clip segments found")
            
            # Step 5: Create clips
            created_clips = []
            timestamp = int(datetime.now().timestamp())
            
            for i, segment in enumerate(clip_segments):
                start_seconds = self.time_to_seconds(segment['start_time'])
                end_seconds = self.time_to_seconds(segment['end_time'])
                
                # Validate clip duration
                clip_duration = end_seconds - start_seconds
                if clip_duration < 10 or clip_duration > 120:
                    logger.warning(f"Skipping clip {i+1}: duration {clip_duration}s is out of range")
                    continue
                
                # Create clip filename
                safe_title = re.sub(r'[^\w\s-]', '', segment['title']).strip()
                safe_title = re.sub(r'[-\s]+', '_', safe_title)[:50]
                clip_filename = f"clip_{timestamp}_{i+1}_{safe_title}.mp4"
                clip_path = os.path.join(self.clips_dir, clip_filename)
                
                # Create the clip
                self.create_clip(video_path, start_seconds, end_seconds, clip_path, aspect_ratio)
                
                clip_info = {
                    'clip_number': i + 1,
                    'title': segment['title'],
                    'description': segment['description'],
                    'start_time': segment['start_time'],
                    'end_time': segment['end_time'],
                    'duration': clip_duration,
                    'engagement_score': segment.get('engagement_score', 0),
                    'file_path': clip_path,
                    'file_name': clip_filename,
                    'aspect_ratio': aspect_ratio
                }
                
                created_clips.append(clip_info)
            
            if not created_clips:
                raise HTTPException(status_code=400, detail="No valid clips could be created")
            
            # Step 6: Process all clips with ZapCap in parallel if requested
            if use_zapcap:
                logger.info(f"Processing {len(created_clips)} clips with ZapCap in parallel...")
                zapcap_results = await self.process_clips_with_zapcap_parallel(created_clips, zapcap_template_id)
                
                # Update clips with ZapCap results
                for clip in created_clips:
                    clip_number = clip['clip_number']
                    if clip_number in zapcap_results:
                        zapcap_result = zapcap_results[clip_number]
                        if 'error' in zapcap_result:
                            clip['zapcap_error'] = zapcap_result['error']
                        else:
                            clip['zapcap_result'] = zapcap_result
            
            # Prepare response
            result = {
                'success': True,
                'message': f'Successfully created {len(created_clips)} clips',
                'total_clips': len(created_clips),
                'clips': created_clips,
                'original_video_info': video_info,
                'transcript': transcript_data.get('text', ''),
                'processing_summary': {
                    'video_duration': video_info['duration'],
                    'clips_created': len(created_clips),
                    'total_clip_duration': sum(clip['duration'] for clip in created_clips),
                    'zapcap_processed': use_zapcap,
                    'aspect_ratio': aspect_ratio
                }
            }
            
            logger.info(f"Auto clipping completed: {len(created_clips)} clips created")
            return result
            
        except Exception as e:
            logger.error(f"Error in auto clipping process: {e}")
            raise
        finally:
            # Clean up temporary files
            for temp_file in temp_files:
                if os.path.exists(temp_file):
                    try:
                        os.remove(temp_file)
                        logger.info(f"Cleaned up temp file: {temp_file}")
                    except OSError as e:
                        logger.warning(f"Could not clean up temp file {temp_file}: {e}")

    async def process_clips_with_zapcap_parallel(self, clip_infos: List[Dict], zapcap_template_id: Optional[str]) -> Dict[int, Dict]:
        """Process multiple clips with ZapCap simultaneously"""
        if not clip_infos:
            return {}
        
        logger.info(f"Starting simultaneous ZapCap processing for {len(clip_infos)} clips...")
        
        # Prepare all clips for simultaneous upload
        upload_tasks = []
        clip_data = []
        
        for clip_info in clip_infos:
            clip_number = clip_info['clip_number']
            clip_path = clip_info['file_path']
            clip_filename = clip_info['file_name']
            
            # Read file content for this clip
            with open(clip_path, 'rb') as f:
                file_content = f.read()
                file_obj = BytesIO(file_content)
                
                # Create a mock UploadFile-like object
                class MockUploadFile:
                    def __init__(self, filename, file_obj, size):
                        self.filename = filename
                        self.file = file_obj
                        self.size = size
                    
                    async def read(self):
                        return self.file.getvalue()
                
                upload_file = MockUploadFile(
                    filename=clip_filename,
                    file_obj=file_obj,
                    size=len(file_content)
                )
                
                # Store clip data and create task
                clip_data.append({
                    'clip_number': clip_number,
                    'upload_file': upload_file
                })
                
                # Create ZapCap processing task
                task = zapcap_service.process_video(
                    upload_file,
                    template_id=zapcap_template_id,
                    language="id",
                    auto_approve=True
                )
                upload_tasks.append(task)
        
        logger.info(f"Sending {len(upload_tasks)} clips to ZapCap simultaneously...")
        
        # Execute all ZapCap requests simultaneously
        try:
            results = await asyncio.gather(*upload_tasks, return_exceptions=True)
        except Exception as e:
            logger.error(f"Error in simultaneous ZapCap processing: {e}")
            results = [e] * len(upload_tasks)
        
        # Process results into a dictionary keyed by clip number
        zapcap_results = {}
        successful_count = 0
        
        for i, result in enumerate(results):
            clip_number = clip_data[i]['clip_number']
            
            if isinstance(result, Exception):
                logger.error(f"ZapCap processing failed for clip {clip_number} with exception: {result}")
                zapcap_results[clip_number] = {'error': str(result)}
            elif result and isinstance(result, dict) and result.get('success', False):
                zapcap_results[clip_number] = {
                    'video_id': result['video_id'],
                    'task_id': result['task_id'],
                    'captioned_video_name': result['video_name'],
                    'captioned_video_path': result['result_file_path'],
                    'processing_time': result['processing_time']
                }
                successful_count += 1
                logger.info(f"ZapCap processing completed for clip {clip_number}")
            else:
                logger.error(f"ZapCap processing failed for clip {clip_number}: Invalid response")
                zapcap_results[clip_number] = {'error': 'Invalid response from ZapCap'}
        
        logger.info(f"Simultaneous ZapCap processing completed: {successful_count}/{len(clip_infos)} clips successful")
        return zapcap_results

# Create a function to get service instance instead of global instantiation
def get_auto_clipper_service():
    """Get AutoClipperService instance"""
    return AutoClipperService() 