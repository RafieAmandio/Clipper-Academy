import os
import re
import json
import asyncio
from datetime import datetime
from typing import Dict, List, Union, Optional
from io import BytesIO
import logging

from fastapi import UploadFile, Request
from openai import OpenAI

from app.services.base import BaseService
from app.config.settings import Settings
from app.services.transcription import TranscriptionService
from app.services.video_processing import VideoProcessingService
from app.services.content_analyzer import ContentAnalyzerService
from app.services.zapcap import ZapCapService
from app.core.exceptions import VideoProcessingError, TranscriptionError, ContentAnalysisError
from app.utils.url_utils import file_path_to_url


class AutoClipperService(BaseService):
    """Main orchestrator service for automatic video clipping with AI analysis"""
    
    def __init__(self, settings: Settings, openai_client: OpenAI):
        """Initialize auto clipper service
        
        Args:
            settings: Application settings
            openai_client: Shared OpenAI client
        """
        super().__init__(settings)
        
        # Initialize component services with shared OpenAI client
        self.transcription_service = TranscriptionService(settings, openai_client)
        self.video_processing_service = VideoProcessingService(settings)
        self.content_analyzer_service = ContentAnalyzerService(settings, openai_client)
        self.zapcap_service = ZapCapService(settings)
    
    def analyze_clip_segments(self, transcript_data: Dict, video_duration: float) -> List[Dict]:
        """Use AI to analyze transcript and identify clip-worthy segments
        
        Args:
            transcript_data: Transcription data with timestamps
            video_duration: Total video duration in seconds
            
        Returns:
            List of clip segment information
        """
        try:
            # self.content_analyzer_service._ensure_client()  # Removed, not needed
            
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
                        Analyze this video transcript and identify the most viral-worthy TikTok clips (30-60 seconds each). PRIORITIZE segments with explosive opening hooks in the first 3-5 seconds that instantly grab attention.

                        Video Duration: {self.format_timestamp(video_duration)}

                        Transcript with timestamps:
                        {transcript_text}

                        HOOK CRITERIA (Critical for first 5 seconds):
                        - Shocking statements or controversial opinions
                        - Bold claims or predictions
                        - Questions that create curiosity gaps
                        - Surprising facts or statistics
                        - Dramatic story openings
                        - Emotional triggers (anger, excitement, surprise)
                        - "You won't believe..." or "This will change your mind..." moments
                        - Counter-intuitive reveals
                        - Personal confessions or vulnerable moments

                        SEGMENT SELECTION RULES:
                        1. Find 2-5 segments with the STRONGEST opening hooks
                        2. Each clip must be 30-60 seconds maximum
                        3. Prioritize segments that:
                        - Start with immediate impact (no slow build-up)
                        - Have clear payoffs within 60 seconds
                        - Create emotional reactions (shock, laughter, anger, curiosity)
                        - Are self-contained stories or insights
                        - End with satisfying conclusions or cliffhangers

                        ENGAGEMENT MULTIPLIERS:
                        - Controversial takes (+2 points)
                        - Personal stories with universal appeal (+2 points)
                        - Educational content with "mind-blown" moments (+1.5 points)
                        - Comedy with quick punchlines (+1.5 points)
                        - Behind-the-scenes revelations (+1 point)
                        - Relatable struggles or wins (+1 point)

                        AVOID:
                        - Segments that require context from earlier in the video
                        - Slow introductions or explanations
                        - Technical content without clear benefits
                        - Long setups without quick payoffs

                        Return ONLY a JSON array in this exact format:
                        [
                            {{
                                "title": "Catchy, curiosity-driven title that creates FOMO",
                                "description": "Why this will stop scrollers dead - focus on the hook and emotional payoff",
                                "start_time": "MM:SS",
                                "end_time": "MM:SS",
                                "duration": 45,
                                "engagement_score": 8.5
                            }}
                        ]

                        Sort results by engagement_score (highest first), prioritizing segments with the strongest opening hooks.
                        """
            
            response = self.content_analyzer_service.client.chat.completions.create(
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
                self.logger.info(f"AI identified {len(clips_data)} potential clips")
                return clips_data
            else:
                raise ContentAnalysisError("Could not parse AI response for clip analysis")
                
        except Exception as e:
            self.logger.error(f"Error analyzing clip segments: {e}")
            raise ContentAnalysisError(f"Failed to analyze clip segments: {e}")
    
    async def get_video_from_url(self, url: str) -> str:
        """Download video from social media URL using content analyzer
        
        Args:
            url: Social media URL
            
        Returns:
            Path to downloaded video file
        """
        try:
            data, video_file, post_dir, platform, post_id, metrics = self.content_analyzer_service.download_social_media_video(
                url, self.settings.temp_dir
            )
            
            if not video_file or not os.path.exists(video_file):
                raise VideoProcessingError("Failed to download video from URL")
            
            self.logger.info(f"Downloaded video from {platform}: {video_file}")
            return video_file
            
        except Exception as e:
            self.logger.error(f"Error downloading video from URL: {e}")
            raise VideoProcessingError(f"Failed to download video: {e}")
    
    async def process_clips_with_zapcap_parallel(self, clip_infos: List[Dict], zapcap_template_id: Optional[str]) -> Dict[int, Dict]:
        """Process multiple clips with ZapCap simultaneously
        
        Args:
            clip_infos: List of clip information
            zapcap_template_id: Optional template ID
            
        Returns:
            Dictionary mapping clip numbers to ZapCap results
        """
        if not clip_infos:
            return {}
        
        self.logger.info(f"Starting simultaneous ZapCap processing for {len(clip_infos)} clips...")
        
        # Prepare all clips for simultaneous upload
        upload_tasks = []
        clip_data = []
        
        for clip_info in clip_infos:
            clip_number = clip_info['clip_number']
            clip_path = clip_info['file_path']
            clip_filename = clip_info['file_name']
            
            self.logger.info(f"Processing clip {clip_number}:")
            self.logger.info(f"  - File path: {clip_path}")
            self.logger.info(f"  - File name: {clip_filename}")
            
            # Read file content for this clip
            with open(clip_path, 'rb') as f:
                file_content = f.read()
                self.logger.info(f"  - File size: {len(file_content)} bytes")
                self.logger.info(f"  - First 32 bytes: {file_content[:32].hex()}")
                
                # Create a mock UploadFile-like object
                class MockUploadFile:
                    def __init__(self, filename, content, size):
                        self.filename = filename
                        self._content = content
                        self.size = size
                        self._position = 0
                        self.logger = logging.getLogger(__name__)
                    
                    async def read(self):
                        # Return a copy of the content to prevent sharing
                        content_copy = self._content[:]
                        self.logger.info(f"MockUploadFile.read() called for {self.filename}")
                        self.logger.info(f"  - Content size: {len(content_copy)} bytes")
                        self.logger.info(f"  - First 32 bytes: {content_copy[:32].hex()}")
                        return content_copy
                    
                    async def seek(self, offset):
                        self._position = offset
                        self.logger.info(f"MockUploadFile.seek({offset}) called for {self.filename}")
                    
                    async def close(self):
                        self.logger.info(f"MockUploadFile.close() called for {self.filename}")
                        pass
                
                upload_file = MockUploadFile(
                    filename=clip_filename,
                    content=file_content,
                    size=len(file_content)
                )
                
                # Store clip data and create task
                clip_data.append({
                    'clip_number': clip_number,
                    'upload_file': upload_file
                })
                
                # Create ZapCap processing task
                task = self.zapcap_service.process_video(
                    upload_file,
                    template_id=zapcap_template_id,
                    language="id",
                    auto_approve=True
                )
                upload_tasks.append(task)
        
        self.logger.info(f"Sending {len(upload_tasks)} clips to ZapCap simultaneously...")
        
        # Execute all ZapCap requests simultaneously
        try:
            results = await asyncio.gather(*upload_tasks, return_exceptions=True)
        except Exception as e:
            self.logger.error(f"Error in simultaneous ZapCap processing: {e}")
            results = [e] * len(upload_tasks)
        
        # Process results into a dictionary keyed by clip number
        zapcap_results = {}
        successful_count = 0
        
        for i, result in enumerate(results):
            clip_number = clip_data[i]['clip_number']
            
            if isinstance(result, Exception):
                self.logger.error(f"ZapCap processing failed for clip {clip_number} with exception: {result}")
                zapcap_results[clip_number] = {'error': str(result)}
            elif result and isinstance(result, dict) and result.get('success', False):
                self.logger.info(f"ZapCap processing successful for clip {clip_number}:")
                self.logger.info(f"  - Video ID: {result.get('video_id')}")
                self.logger.info(f"  - Task ID: {result.get('task_id')}")
                self.logger.info(f"  - Result path: {result.get('result_file_path')}")
                
                zapcap_results[clip_number] = {
                    'video_id': result['video_id'],
                    'task_id': result['task_id'],
                    'captioned_video_name': result['video_name'],
                    'captioned_video_path': result['result_file_path'],
                    'processing_time': result['processing_time']
                }
                successful_count += 1
                self.logger.info(f"ZapCap processing completed for clip {clip_number}")
            else:
                self.logger.error(f"ZapCap processing failed for clip {clip_number}: Invalid response")
                zapcap_results[clip_number] = {'error': 'Invalid response from ZapCap'}
        
        self.logger.info(f"Simultaneous ZapCap processing completed: {successful_count}/{len(clip_infos)} clips successful")
        return zapcap_results
    
    async def process_video(self, video_input: Union[str, UploadFile], 
                          use_zapcap: bool = False, 
                          zapcap_template_id: Optional[str] = None,
                          aspect_ratio: str = "9:16",
                          request: Request = None) -> Dict:
        """Main processing function for auto clipping
        
        Args:
            video_input: Video source (UploadFile, URL, or file path)
            use_zapcap: Whether to use ZapCap for captions
            zapcap_template_id: Custom ZapCap template ID
            aspect_ratio: Target aspect ratio for clips
            request: FastAPI Request object for URL generation
        
        Returns:
            Complete processing results
        """
        temp_files = []
        
        try:
            # Step 1: Get video file
            if hasattr(video_input, 'filename') and hasattr(video_input, 'read'):
                self.logger.info(f"Processing uploaded file: {video_input.filename}")
                video_path = await self.video_processing_service.save_upload_file(video_input)
                temp_files.append(video_path)
            elif isinstance(video_input, str) and video_input.startswith(('http://', 'https://')):
                self.logger.info(f"Processing URL: {video_input}")
                video_path = await self.get_video_from_url(video_input)
                temp_files.append(video_path)
            else:
                self.logger.info(f"Processing file path: {video_input}")
                if not os.path.exists(video_input):
                    raise VideoProcessingError("Video file not found")
                video_path = video_input
            
            # Step 2: Get video information
            video_info = self.video_processing_service.get_video_info(video_path)
            self.logger.info(f"Video info: {video_info['duration']:.1f}s, {video_info['width']}x{video_info['height']}")
            
            # Step 3: Transcribe video
            transcript_data = await self.transcription_service.transcribe_video(video_path)
            
            # Step 4: Analyze for clip segments
            clip_segments = self.analyze_clip_segments(transcript_data, video_info['duration'])
            
            if not clip_segments:
                raise ContentAnalysisError("No suitable clip segments found")
            
            # Step 5: Create clips
            created_clips = []
            timestamp = int(datetime.now().timestamp())
            
            for i, segment in enumerate(clip_segments):
                start_seconds = self.video_processing_service.time_to_seconds(segment['start_time'])
                end_seconds = self.video_processing_service.time_to_seconds(segment['end_time'])
                
                # Validate clip duration
                clip_duration = end_seconds - start_seconds
                if clip_duration < self.settings.min_clip_duration or clip_duration > self.settings.max_clip_duration:
                    self.logger.warning(f"Skipping clip {i+1}: duration {clip_duration}s is out of range")
                    continue
                
                # Create clip filename
                safe_title = self.video_processing_service.get_safe_filename(segment['title'])
                clip_filename = f"clip_{timestamp}_{i+1}_{safe_title}.mp4"
                clip_path = os.path.join(self.settings.clips_dir, clip_filename)
                
                # Create the clip
                self.video_processing_service.create_video_clip(
                    video_path, start_seconds, end_seconds, clip_path, aspect_ratio
                )
                
                # Convert file path to URL if request is provided
                clip_url = file_path_to_url(clip_path, request) if request else clip_path
                clip_info = {
                    'clip_number': i + 1,
                    'title': segment['title'],
                    'description': segment['description'],
                    'start_time': segment['start_time'],
                    'end_time': segment['end_time'],
                    'duration': clip_duration,
                    'engagement_score': segment.get('engagement_score', 0),
                    'file_path': clip_path,  # Keep the actual file path
                    'url': clip_url,  # Store the URL separately
                    'file_name': clip_filename,
                    'aspect_ratio': aspect_ratio
                }
                
                created_clips.append(clip_info)
            
            if not created_clips:
                raise VideoProcessingError("No valid clips could be created")
            
            # Step 6: Process all clips with ZapCap in parallel if requested
            if use_zapcap:
                self.logger.info(f"Processing {len(created_clips)} clips with ZapCap in parallel...")
                zapcap_results = await self.process_clips_with_zapcap_parallel(created_clips, zapcap_template_id)
                
                # Update clips with ZapCap results
                for clip in created_clips:
                    clip_number = clip['clip_number']
                    if clip_number in zapcap_results:
                        zapcap_result = zapcap_results[clip_number]
                        if 'error' in zapcap_result:
                            clip['zapcap_error'] = zapcap_result['error']
                        else:
                            # Convert ZapCap result file path to URL
                            if 'captioned_video_path' in zapcap_result and request:
                                zapcap_result['captioned_video_url'] = file_path_to_url(zapcap_result['captioned_video_path'], request)
                            clip['zapcap_result'] = zapcap_result
            
            # Prepare response
            # Convert original video path to URL if request is provided
            video_url = file_path_to_url(video_path, request) if request else video_path
            result = {
                'success': True,
                'message': f'Successfully created {len(created_clips)} clips',
                'total_clips': len(created_clips),
                'clips': created_clips,
                'original_video_info': video_info,
                'original_video_path': video_path,  # Keep the actual file path
                'original_video_url': video_url,  # Store the URL separately
                'transcript': transcript_data.get('text', ''),
                'processing_summary': {
                    'video_duration': video_info['duration'],
                    'clips_created': len(created_clips),
                    'total_clip_duration': sum(clip['duration'] for clip in created_clips),
                    'zapcap_processed': use_zapcap,
                    'aspect_ratio': aspect_ratio
                }
            }
            
            self.logger.info(f"Auto clipping completed: {len(created_clips)} clips created")
            return result
            
        except Exception as e:
            self.logger.error(f"Error in auto clipping process: {e}")
            raise
        finally:
            # Clean up temporary files
            for temp_file in temp_files:
                if os.path.exists(temp_file):
                    try:
                        os.remove(temp_file)
                        self.logger.info(f"Cleaned up temp file: {temp_file}")
                    except OSError as e:
                        self.logger.warning(f"Could not clean up temp file {temp_file}: {e}") 