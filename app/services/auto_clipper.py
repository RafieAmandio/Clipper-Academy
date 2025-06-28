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
from fastapi.staticfiles import StaticFiles

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
    
    def detect_language_from_transcript(self, transcript_data: Dict) -> str:
        """Detect language from transcript text using simple heuristics
        
        Args:
            transcript_data: Transcription data with text
            
        Returns:
            Detected language code ('id' for Indonesian, 'en' for English, etc.)
        """
        try:
            text = transcript_data.get('text', '').lower()
            
            # Indonesian language indicators
            indonesian_words = [
                'yang', 'dan', 'atau', 'dengan', 'untuk', 'dari', 'ke', 'di', 'pada', 'oleh',
                'ini', 'itu', 'saya', 'kamu', 'mereka', 'kita', 'kami', 'anda', 'dia',
                'adalah', 'akan', 'sudah', 'belum', 'tidak', 'bukan', 'jika', 'karena',
                'tetapi', 'namun', 'jadi', 'maka', 'sehingga', 'ketika', 'saat', 'waktu',
                'hari', 'bulan', 'tahun', 'orang', 'tempat', 'hal', 'benda', 'kerja',
                'kerja', 'bekerja', 'makan', 'minum', 'tidur', 'jalan', 'datang', 'pergi',
                'besar', 'kecil', 'baik', 'buruk', 'bagus', 'jelek', 'mahal', 'murah',
                'cepat', 'lambat', 'panas', 'dingin', 'baru', 'lama', 'muda', 'tua',
                'bisa', 'mau', 'ingin', 'harus', 'perlu', 'boleh', 'semua', 'beberapa',
                'banyak', 'sedikit', 'sangat', 'terlalu', 'agak', 'cukup', 'masih',
                'sudah', 'pernah', 'belum', 'selalu', 'kadang', 'jarang', 'tidak',
                'ya', 'tidak', 'iya', 'nggak', 'gak', 'enggak', 'ga', 'gak', 'ngga',
                'sih', 'dong', 'lah', 'kan', 'tuh', 'nih', 'itu', 'ini', 'situ', 'sini'
            ]
            
            # Count Indonesian words
            indonesian_count = sum(1 for word in indonesian_words if word in text)
            
            # If more than 8 Indonesian words found, likely Indonesian
            if indonesian_count >= 8:
                return 'id'
            
            # Check for common Indonesian phrases
            indonesian_phrases = [
                'apa kabar', 'terima kasih', 'sama sama', 'selamat pagi', 'selamat siang',
                'selamat sore', 'selamat malam', 'bagaimana', 'kenapa', 'mengapa',
                'dimana', 'kapan', 'siapa', 'berapa', 'yang mana', 'yang mana',
                'tidak apa apa', 'tidak masalah', 'baik baik saja', 'sama saja',
                'begitu juga', 'demikian juga', 'oleh karena itu', 'oleh sebab itu',
                'gimana', 'gimana sih', 'gimana ya', 'gimana nih', 'gimana dong',
                'apa sih', 'apa ya', 'apa nih', 'apa dong', 'kenapa sih', 'kenapa ya',
                'kenapa nih', 'kenapa dong', 'dimana sih', 'dimana ya', 'dimana nih',
                'kapan sih', 'kapan ya', 'kapan nih', 'siapa sih', 'siapa ya', 'siapa nih',
                'berapa sih', 'berapa ya', 'berapa nih', 'yang mana sih', 'yang mana ya',
                'tidak apa apa', 'tidak masalah', 'baik baik saja', 'sama saja',
                'begitu juga', 'demikian juga', 'oleh karena itu', 'oleh sebab itu',
                'jadi gimana', 'jadi apa', 'jadi kenapa', 'jadi dimana', 'jadi kapan',
                'jadi siapa', 'jadi berapa', 'jadi yang mana', 'jadi tidak apa apa',
                'jadi tidak masalah', 'jadi baik baik saja', 'jadi sama saja',
                'jadi begitu juga', 'jadi demikian juga', 'jadi oleh karena itu',
                'jadi oleh sebab itu', 'jadi gimana sih', 'jadi gimana ya', 'jadi gimana nih',
                'jadi gimana dong', 'jadi apa sih', 'jadi apa ya', 'jadi apa nih',
                'jadi apa dong', 'jadi kenapa sih', 'jadi kenapa ya', 'jadi kenapa nih',
                'jadi kenapa dong', 'jadi dimana sih', 'jadi dimana ya', 'jadi dimana nih',
                'jadi kapan sih', 'jadi kapan ya', 'jadi kapan nih', 'jadi siapa sih',
                'jadi siapa ya', 'jadi siapa nih', 'jadi berapa sih', 'jadi berapa ya',
                'jadi berapa nih', 'jadi yang mana sih', 'jadi yang mana ya'
            ]
            
            for phrase in indonesian_phrases:
                if phrase in text:
                    return 'id'
            
            # Check for Indonesian slang and informal expressions
            indonesian_slang = [
                'gue', 'gw', 'lo', 'lu', 'elo', 'elu', 'gue', 'gw', 'lo', 'lu', 'elo', 'elu',
                'banget', 'banget', 'banget', 'banget', 'banget', 'banget', 'banget',
                'sih', 'dong', 'lah', 'kan', 'tuh', 'nih', 'itu', 'ini', 'situ', 'sini',
                'gitu', 'gini', 'gitu', 'gini', 'gitu', 'gini', 'gitu', 'gini',
                'aja', 'saja', 'aja', 'saja', 'aja', 'saja', 'aja', 'saja',
                'kok', 'kok', 'kok', 'kok', 'kok', 'kok', 'kok', 'kok',
                'dong', 'dong', 'dong', 'dong', 'dong', 'dong', 'dong', 'dong',
                'lah', 'lah', 'lah', 'lah', 'lah', 'lah', 'lah', 'lah',
                'kan', 'kan', 'kan', 'kan', 'kan', 'kan', 'kan', 'kan',
                'tuh', 'tuh', 'tuh', 'tuh', 'tuh', 'tuh', 'tuh', 'tuh',
                'nih', 'nih', 'nih', 'nih', 'nih', 'nih', 'nih', 'nih'
            ]
            
            slang_count = sum(1 for word in indonesian_slang if word in text)
            if slang_count >= 3:
                return 'id'
            
            # Check for Indonesian sentence endings and patterns
            indonesian_patterns = [
                r'\b\w+sih\b', r'\b\w+dong\b', r'\b\w+lah\b', r'\b\w+kan\b',
                r'\b\w+tuh\b', r'\b\w+nih\b', r'\b\w+aja\b', r'\b\w+kok\b',
                r'\bgimana\b', r'\bgitu\b', r'\bgini\b', r'\baja\b', r'\bsaja\b'
            ]
            
            import re
            pattern_count = 0
            for pattern in indonesian_patterns:
                if re.search(pattern, text):
                    pattern_count += 1
            
            if pattern_count >= 2:
                return 'id'
            
            # Default to English if no clear indicators
            return 'en'
            
        except Exception as e:
            self.logger.warning(f"Language detection failed: {e}")
            return 'en'  # Default fallback
    
    def get_language_specific_prompt(self, language: str, transcript_text: str, video_duration: float) -> str:
        """Get language-specific prompt for clip analysis
        
        Args:
            language: Language code ('id', 'en', etc.)
            transcript_text: Formatted transcript text
            video_duration: Video duration in seconds
            
        Returns:
            Language-specific prompt
        """
        if language == 'id':
            return f"""
Kamu adalah ahli strategi konten TikTok dan editor video yang berpengalaman di Indonesia. Analisis transkrip video ini dan identifikasi klip TikTok yang paling viral-worthy (prefer 20-45 detik, maksimal 60 detik). Tujuanmu adalah menemukan segmen yang akan MENGHEMTI SCROLLER dan menciptakan engagement maksimal.

**PENTING - PETUNJUK KHUSUS UNTUK INDONESIA:**
- Setiap `title` HARUS merangkum konten AKTUAL dari segmen, bukan hanya frase viral generik. Gunakan teks transkrip sebagai inspirasi dan buat judul yang benar-benar merangkum atau "hook" dari segmen spesifik tersebut.
- `description` harus menjelaskan mengapa segmen ini menarik, merujuk pada kata-kata atau cerita aktual dalam transkrip.
- Jika ada beberapa momen viral berdekatan, buat KLIP TERPISAH untuk masing-masing. JANGAN menggabungkan beberapa momen viral menjadi satu klip panjang.
- Lebih suka klip yang lebih pendek dan banyak (20-45 detik) daripada yang panjang dan sedikit. Jika segmen lebih dari 45 detik, coba bagi menjadi dua atau lebih klip yang fokus.
- Jangan pernah menggunakan judul generik atau berulang. Setiap judul harus unik dan spesifik untuk segmen.
- Jika segmen mengandung perubahan topik, emosi, atau hook yang jelas, pisahkan menjadi klip terpisah.
- JANGAN membuat klip yang hanya berisi nasihat generik atau filler; fokus pada momen dengan hook, payoff, atau dampak emosional yang jelas.

Durasi Video: {self.format_timestamp(video_duration)}

Transkrip dengan timestamp:
{transcript_text}

ANALISIS HOOK KRITIS (3-5 detik pertama):
Cari pola hook EXACT ini yang membuat penonton berhenti:

🎯 HOOK KEJUTAN (Prioritas Tertinggi):
- "Saya baru tahu..." + penemuan mengejutkan
- "Inilah mengapa..." + pernyataan kontroversial
- "Yang sebenarnya tentang..." + fakta tak terduga
- "Kamu sudah dibohongi tentang..." + penemuan
- "Saya tidak percaya..." + penemuan mengejutkan
- "Ini akan mengubah segalanya..." + klaim berani

🎯 HOOK RASA INGIN TAHU:
- "Ini yang tidak ada yang bilang..." + rahasia
- "Alasan sebenarnya mengapa..." + kebenaran tersembunyi
- "Yang saya temukan..." + penemuan pribadi
- "Ini yang sebenarnya terjadi..." + di balik layar
- "Mengapa kebanyakan orang gagal dalam..." + masalah + solusi

🎯 HOOK EMOSIONAL:
- Pengakuan pribadi yang relatable
- Cerita yang menciptakan empati langsung
- Pernyataan yang memicu kemarahan/outrage
- Penemuan yang menciptakan kegembiraan
- Pertanyaan yang membuat penonton berpikir "Itu saya!"

🎯 HOOK KONTROVERSI:
- Pendapat tidak populer yang sebenarnya populer
- "Semua orang bilang X, tapi..." + kontra-argumen
- "Industri tidak ingin kamu tahu..." + rahasia
- "Mengapa saya berhenti..." + keputusan mengejutkan
- "Yang saya pelajari dengan susah payah..." + kebenaran pahit

KRITERIA PEMILIHAN SEGMEN:
1. KEKUATAN HOOK (40% skor):
   - Apakah menarik perhatian dalam 3 detik pertama?
   - Apakah langsung relatable atau mengejutkan?
   - Apakah menciptakan gap rasa ingin tahu?
2. KUALITAS KONTEN (30% skor):
   - Apakah payoff sebanding dengan setup?
   - Apakah memenuhi janji hook?
   - Apakah self-contained (tidak butuh konteks)?
3. POTENSI VIRAL (20% skor):
   - Apakah orang ingin share ini?
   - Apakah menciptakan emosi kuat?
   - Apakah timely atau evergreen?
4. KESESUAIAN AUDIENS (10% skor):
   - Apakah berbicara ke audiens spesifik?
   - Apakah autentik dan genuine?
   - Apakah memberikan nilai nyata?

MULTIPLIER ENGAGEMENT (Tambahkan ke viral_score):
+3.0: Take kontroversial yang sebenarnya populer
+2.5: Cerita pribadi dengan daya tarik emosional universal
+2.0: Konten edukasi dengan momen "mind-blown"
+2.0: Revelasi di balik layar
+1.5: Komedi dengan punchline cepat dan relatable
+1.5: Cerita "Bagaimana saya..." sukses/gagal
+1.0: Perjuangan atau kemenangan sehari-hari yang relatable
+1.0: Rahasia industri atau pengetahuan insider
+0.5: Topik trending atau current events

REQUIREMENT STRUKTUR KLIP:
- Setiap klip harus 20-45 detik (maksimal 60 detik)
- Harus punya hook pembuka yang kuat (3-5 detik pertama)
- Harus punya payoff atau kesimpulan yang memuaskan
- Sebaiknya berakhir dengan cliffhanger atau call-to-action
- Harus self-contained (tidak butuh konteks dari sebelumnya)
- Jika dua momen viral berdekatan, buat dua klip terpisah

ATURAN PADDING WAKTU:
- Tambah 2-3 detik SEBELUM waktu mulai yang diidentifikasi untuk flow natural
- Tambah 2-4 detik SETELAH waktu akhir yang diidentifikasi untuk kesimpulan smooth
- Jangan biarkan klip terpotong di tengah kalimat
- Pastikan transisi audio smooth
- Pertimbangkan jeda bicara natural

HINDARI SEGMEN INI:
❌ Introduksi atau penjelasan lambat
❌ Konten teknis tanpa benefit jelas
❌ Segmen yang butuh konteks dari awal video
❌ Setup panjang tanpa payoff cepat
❌ Nasihat generik tanpa cerita pribadi
❌ Konten terlalu promosi atau salesy
❌ Konten yang terlalu niche atau spesifik

KONTEKS KHUSUS INDONESIA:
- Fokus pada humor lokal dan referensi budaya Indonesia
- Pertimbangkan tren TikTok Indonesia saat ini
- Gunakan bahasa yang relatable untuk audiens Indonesia
- Pertimbangkan isu-isu yang relevan dengan masyarakat Indonesia
- Fokus pada konten yang bisa viral di platform lokal (TikTok, Instagram Reels, YouTube Shorts)

Kembalikan HANYA array JSON dalam format exact ini:
[
    {{
        "title": "Judul unik berbasis konten untuk segmen ini (bukan generik)",
        "description": "Penjelasan detail mengapa segmen ini menarik, merujuk pada transkrip.",
        "start_time": "MM:SS",
        "end_time": "MM:SS", 
        "duration": 30,
        "engagement_score": 8.5,
        "viral_score": 9.2,
        "hook_type": "shock|curiosity|emotional|controversy",
        "target_audience": "audiens spesifik yang dituju",
        "emotional_triggers": ["shock", "curiosity", "anger", "excitement", "empathy"],
        "shareability_factor": "mengapa orang akan share ini"
    }}
]

PENTING: Pastikan response kamu HANYA berisi JSON array yang valid. Jangan tambahkan teks lain sebelum atau sesudah JSON. Format harus persis seperti contoh di atas.

PANDUAN SKORING:
- engagement_score: 1-10 (seberapa engaging kontennya)
- viral_score: 1-10 (kemungkinan viral, termasuk multiplier)
- Urutkan berdasarkan viral_score (tertinggi dulu)
- Hanya masukkan segmen dengan viral_score >= 7.0
- Maksimal 7 klip per video (tapi prefer lebih banyak, klip lebih pendek)

Ingat: Kamu bukan hanya mencari konten bagus - kamu mencari konten yang akan membuat orang BERHENTI SCROLLING dan MENONTON SELURUH KLIP. Setiap judul dan deskripsi harus unik dan berbasis pada konten transkrip aktual.

RESPONSE FORMAT:
Hanya kembalikan JSON array, tidak ada teks lain:
"""
        else:
            # English prompt (existing)
            return f"""
You are an expert TikTok content strategist and video editor. Analyze this video transcript and identify the most viral-worthy TikTok clips (prefer 20-45 seconds each, never over 60s). Your goal is to find segments that will STOP SCROLLERS DEAD and create maximum engagement.

**IMPORTANT INSTRUCTIONS:**
- For each clip, the `title` MUST summarize the ACTUAL content of the segment, not just a generic viral phrase. Use the transcript text for inspiration and make the title a true summary or "hook" of the specific segment.
- The `description` must explain why this specific segment is engaging, referencing the actual words or story in the transcript.
- If there are multiple viral moments close together, make SEPARATE clips for each. Do NOT merge multiple viral moments into one long clip.
- Prefer more, shorter clips (20-45s) over fewer, longer ones. If a segment is over 45s, try to split it into two or more focused clips.
- Never use generic or repeated titles. Each title must be unique and specific to the segment.
- If a segment contains a clear change in topic, emotion, or hook, split it into separate clips.
- Do NOT create clips that are just generic advice or filler; focus on moments with a clear hook, payoff, or emotional impact.

Video Duration: {self.format_timestamp(video_duration)}

Transcript with timestamps:
{transcript_text}

CRITICAL HOOK ANALYSIS (First 3-5 seconds):
Look for these EXACT hook patterns that make viewers pause:

🎯 SHOCK HOOKS (Highest Priority):
- "I just found out..." + shocking revelation
- "This is why..." + controversial statement
- "The truth about..." + unexpected fact
- "You've been lied to about..." + revelation
- "I can't believe..." + surprising discovery
- "This will change everything..." + bold claim

🎯 CURIOSITY HOOKS:
- "Here's what nobody tells you..." + secret
- "The real reason why..." + hidden truth
- "What I discovered..." + personal revelation
- "This is what actually happens..." + behind-the-scenes
- "Why most people fail at..." + problem + solution

🎯 EMOTIONAL HOOKS:
- Personal confession that's relatable
- Story that creates immediate empathy
- Statement that triggers anger/outrage
- Revelation that creates excitement
- Question that makes viewer think "That's me!"

🎯 CONTROVERSY HOOKS:
- Unpopular opinion that's actually popular
- "Everyone says X, but..." + counter-argument
- "The industry doesn't want you to know..." + secret
- "Why I stopped..." + surprising decision
- "What I learned the hard way..." + painful truth

SEGMENT SELECTION CRITERIA:
1. HOOK STRENGTH (40% of score):
   - Does it grab attention in first 3 seconds?
   - Is it immediately relatable or shocking?
   - Does it create a curiosity gap?
2. CONTENT QUALITY (30% of score):
   - Is the payoff worth the setup?
   - Does it deliver on the hook's promise?
   - Is it self-contained (no context needed)?
3. VIRAL POTENTIAL (20% of score):
   - Would people want to share this?
   - Does it create strong emotions?
   - Is it timely or evergreen?
4. AUDIENCE FIT (10% of score):
   - Does it speak to a specific audience?
   - Is it authentic and genuine?
   - Does it provide real value?

ENGAGEMENT MULTIPLIERS (Add to viral_score):
+3.0: Controversial takes that are actually popular
+2.5: Personal stories with universal emotional appeal
+2.0: Educational content with "mind-blown" moments
+2.0: Behind-the-scenes revelations
+1.5: Comedy with quick, relatable punchlines
+1.5: "How I..." success/failure stories
+1.0: Relatable daily struggles or wins
+1.0: Industry secrets or insider knowledge
+0.5: Trending topics or current events

CLIP STRUCTURE REQUIREMENTS:
- Each clip must be 20-45 seconds (never over 60s)
- Must have a strong opening hook (first 3-5 seconds)
- Must have a satisfying payoff or conclusion
- Should end with a cliffhanger or call-to-action when possible
- Must be self-contained (no context from earlier needed)
- If two viral moments are close, make two separate clips

TIME PADDING RULES:
- Add 2-3 seconds BEFORE the identified start time for natural flow
- Add 2-4 seconds AFTER the identified end time for smooth conclusion
- Never let clips cut off mid-sentence
- Ensure smooth audio transitions
- Account for natural speech pauses

AVOID THESE SEGMENTS:
❌ Slow introductions or explanations
❌ Technical content without clear benefits
❌ Segments requiring context from earlier in video
❌ Long setups without quick payoffs
❌ Generic advice without personal stories
❌ Overly promotional or salesy content
❌ Content that's too niche or specific

Return ONLY a JSON array in this exact format:
[
    {{
        "title": "A unique, content-based title for this segment (not generic)",
        "description": "Detailed explanation of why this segment is engaging, referencing the transcript.",
        "start_time": "MM:SS",
        "end_time": "MM:SS", 
        "duration": 30,
        "engagement_score": 8.5,
        "viral_score": 9.2,
        "hook_type": "shock|curiosity|emotional|controversy",
        "target_audience": "specific audience this appeals to",
        "emotional_triggers": ["shock", "curiosity", "anger", "excitement", "empathy"],
        "shareability_factor": "why people would share this"
    }}
]

IMPORTANT: Ensure your response contains ONLY a valid JSON array. Do not add any text before or after the JSON. The format must be exactly as shown above.

SCORING GUIDELINES:
- engagement_score: 1-10 (how engaging the content is)
- viral_score: 1-10 (likelihood to go viral, includes multipliers)
- Sort by viral_score (highest first)
- Only include segments with viral_score >= 7.0
- Maximum 7 clips per video (but prefer more, shorter clips)

Remember: You're not just finding good content - you're finding content that will make people STOP SCROLLING and WATCH THE ENTIRE CLIP. Each title and description must be unique and based on the actual transcript content.

RESPONSE FORMAT:
Return only the JSON array, no other text:
"""

    def get_simple_prompt(self, language: str, transcript_text: str, video_duration: float) -> str:
        """Get a simple fallback prompt for clip analysis when main prompt fails
        
        Args:
            language: Language code ('id', 'en', etc.)
            transcript_text: Formatted transcript text
            video_duration: Video duration in seconds
            
        Returns:
            Simple prompt for fallback analysis
        """
        if language == 'id':
            return f"""
Analisis transkrip video ini dan temukan 3-5 segmen yang paling menarik untuk klip TikTok (20-45 detik).

Durasi Video: {self.format_timestamp(video_duration)}

Transkrip:
{transcript_text}

Kembalikan HANYA JSON array dengan format ini:
[
    {{
        "title": "Judul segmen",
        "description": "Deskripsi singkat",
        "start_time": "MM:SS",
        "end_time": "MM:SS",
        "duration": 30,
        "engagement_score": 8.0,
        "viral_score": 8.0,
        "hook_type": "shock",
        "target_audience": "umum",
        "emotional_triggers": ["shock"],
        "shareability_factor": "konten menarik"
    }}
]

Hanya JSON, tidak ada teks lain.
"""
        else:
            return f"""
Analyze this video transcript and find 3-5 most engaging segments for TikTok clips (20-45 seconds).

Video Duration: {self.format_timestamp(video_duration)}

Transcript:
{transcript_text}

Return ONLY JSON array in this format:
[
    {{
        "title": "Segment title",
        "description": "Brief description",
        "start_time": "MM:SS",
        "end_time": "MM:SS",
        "duration": 30,
        "engagement_score": 8.0,
        "viral_score": 8.0,
        "hook_type": "shock",
        "target_audience": "general",
        "emotional_triggers": ["shock"],
        "shareability_factor": "engaging content"
    }}
]

Only JSON, no other text.
"""

    def extract_clips_manually(self, response_text: str) -> List[Dict]:
        """Manually extract clip information from AI response when JSON parsing fails
        
        Args:
            response_text: Raw AI response text
            
        Returns:
            List of extracted clip data
        """
        try:
            clips = []
            
            # Look for patterns that indicate clip information
            # Common patterns in the response
            patterns = [
                r'title["\s]*:["\s]*["\']([^"\']+)["\']',
                r'start_time["\s]*:["\s]*["\']([^"\']+)["\']',
                r'end_time["\s]*:["\s]*["\']([^"\']+)["\']',
                r'duration["\s]*:["\s]*(\d+)',
                r'engagement_score["\s]*:["\s]*([\d.]+)',
                r'viral_score["\s]*:["\s]*([\d.]+)',
                r'description["\s]*:["\s]*["\']([^"\']+)["\']',
                r'hook_type["\s]*:["\s]*["\']([^"\']+)["\']',
                r'target_audience["\s]*:["\s]*["\']([^"\']+)["\']',
                r'shareability_factor["\s]*:["\s]*["\']([^"\']+)["\']'
            ]
            
            # Split response into potential clip sections
            sections = response_text.split('{')
            
            for section in sections:
                if 'title' in section and 'start_time' in section:
                    clip = {}
                    
                    # Extract title
                    title_match = re.search(patterns[0], section)
                    if title_match:
                        clip['title'] = title_match.group(1)
                    
                    # Extract start_time
                    start_match = re.search(patterns[1], section)
                    if start_match:
                        clip['start_time'] = start_match.group(1)
                    
                    # Extract end_time
                    end_match = re.search(patterns[2], section)
                    if end_match:
                        clip['end_time'] = end_match.group(1)
                    
                    # Extract duration
                    duration_match = re.search(patterns[3], section)
                    if duration_match:
                        clip['duration'] = int(duration_match.group(1))
                    
                    # Extract engagement_score
                    engagement_match = re.search(patterns[4], section)
                    if engagement_match:
                        clip['engagement_score'] = float(engagement_match.group(1))
                    
                    # Extract viral_score
                    viral_match = re.search(patterns[5], section)
                    if viral_match:
                        clip['viral_score'] = float(viral_match.group(1))
                    
                    # Extract description
                    desc_match = re.search(patterns[6], section)
                    if desc_match:
                        clip['description'] = desc_match.group(1)
                    
                    # Extract hook_type
                    hook_match = re.search(patterns[7], section)
                    if hook_match:
                        clip['hook_type'] = hook_match.group(1)
                    
                    # Extract target_audience
                    audience_match = re.search(patterns[8], section)
                    if audience_match:
                        clip['target_audience'] = audience_match.group(1)
                    
                    # Extract shareability_factor
                    share_match = re.search(patterns[9], section)
                    if share_match:
                        clip['shareability_factor'] = share_match.group(1)
                    
                    # Only add clip if we have essential fields
                    if 'title' in clip and 'start_time' in clip and 'end_time' in clip:
                        # Set defaults for missing fields
                        clip.setdefault('duration', 30)
                        clip.setdefault('engagement_score', 7.0)
                        clip.setdefault('viral_score', 7.0)
                        clip.setdefault('description', 'Engaging content segment')
                        clip.setdefault('hook_type', 'unknown')
                        clip.setdefault('target_audience', 'general')
                        clip.setdefault('emotional_triggers', [])
                        clip.setdefault('shareability_factor', 'engaging content')
                        
                        clips.append(clip)
                        self.logger.info(f"Manually extracted clip: {clip['title']}")
            
            self.logger.info(f"Manually extracted {len(clips)} clips from response")
            return clips
            
        except Exception as e:
            self.logger.error(f"Error in manual extraction: {e}")
            return []

    def split_long_clips(self, clips_data: List[Dict], video_duration: float) -> List[Dict]:
        """Split long clips into multiple focused clips for better engagement
        
        Args:
            clips_data: List of clip data from AI analysis
            video_duration: Total video duration in seconds
            
        Returns:
            List of clips with long ones split into multiple focused clips
        """
        try:
            split_clips = []
            
            for clip in clips_data:
                start_seconds = self.video_processing_service.time_to_seconds(clip['start_time'])
                end_seconds = self.video_processing_service.time_to_seconds(clip['end_time'])
                duration = end_seconds - start_seconds
                
                # If clip is longer than 45 seconds, try to split it
                if duration > 45:
                    self.logger.info(f"Splitting long clip: {clip['title']} (duration: {duration}s)")
                    
                    # Split into 2-3 parts, each 20-35 seconds
                    num_parts = min(3, max(2, int(duration / 30)))
                    part_duration = duration / num_parts
                    
                    for i in range(num_parts):
                        part_start = start_seconds + (i * part_duration)
                        part_end = start_seconds + ((i + 1) * part_duration)
                        
                        # Ensure we don't exceed video duration
                        part_end = min(part_end, video_duration)
                        
                        # Create new clip part
                        part_clip = clip.copy()
                        part_clip['start_time'] = self.format_timestamp(part_start)
                        part_clip['end_time'] = self.format_timestamp(part_end)
                        part_clip['duration'] = part_end - part_start
                        
                        # Update title and description for the part
                        if num_parts > 1:
                            part_clip['title'] = f"{clip['title']} (Bagian {i+1}/{num_parts})" if clip.get('language') == 'id' else f"{clip['title']} (Part {i+1}/{num_parts})"
                            part_clip['description'] = f"{clip['description']} - {num_parts} bagian, ini adalah bagian {i+1}." if clip.get('language') == 'id' else f"{clip['description']} - {num_parts} parts, this is part {i+1}."
                        
                        # Adjust scores for parts (slightly lower as they're incomplete)
                        part_clip['engagement_score'] = max(1.0, clip.get('engagement_score', 5.0) * 0.9)
                        part_clip['viral_score'] = max(1.0, clip.get('viral_score', 5.0) * 0.9)
                        
                        split_clips.append(part_clip)
                        self.logger.info(f"Created clip part {i+1}/{num_parts}: {part_clip['title']} ({part_clip['duration']:.1f}s)")
                else:
                    # Keep original clip if it's not too long
                    split_clips.append(clip)
            
            self.logger.info(f"Split {len(clips_data)} clips into {len(split_clips)} total clips")
            return split_clips
            
        except Exception as e:
            self.logger.error(f"Error splitting long clips: {e}")
            return clips_data  # Return original clips if splitting fails

    def analyze_clip_segments(self, transcript_data: Dict, video_duration: float) -> List[Dict]:
        """Use AI to analyze transcript and identify clip-worthy segments
        
        Args:
            transcript_data: Transcription data with timestamps
            video_duration: Total video duration in seconds
            
        Returns:
            List of clip segment information
        """
        try:
            # Detect language from transcript
            detected_language = self.detect_language_from_transcript(transcript_data)
            self.logger.info(f"Detected language: {detected_language}")
            
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
            
            # Get language-specific prompt
            prompt = self.get_language_specific_prompt(detected_language, transcript_text, video_duration)
            
            # Try the main analysis first
            try:
                response = self.content_analyzer_service.client.chat.completions.create(
                    model="gpt-4o",
                    messages=[
                        {"role": "system", "content": f"You are a video editing expert who identifies engaging content segments. Respond in {detected_language} if the content is in {detected_language}."},
                        {"role": "user", "content": prompt}
                    ],
                    temperature=0.3
                )
                
                # Parse AI response
                response_text = response.choices[0].message.content.strip()
                self.logger.info(f"AI Response received (first 500 chars): {response_text[:500]}...")
                
            except Exception as e:
                self.logger.warning(f"First AI analysis attempt failed: {e}")
                # Try with a simpler prompt
                simple_prompt = self.get_simple_prompt(detected_language, transcript_text, video_duration)
                
                response = self.content_analyzer_service.client.chat.completions.create(
                    model="gpt-4o",
                    messages=[
                        {"role": "system", "content": f"You are a video editor. Return only valid JSON."},
                        {"role": "user", "content": simple_prompt}
                    ],
                    temperature=0.1
                )
                
                response_text = response.choices[0].message.content.strip()
                self.logger.info(f"Simple AI Response received (first 500 chars): {response_text[:500]}...")
            
            # Try multiple JSON extraction strategies
            clips_data = None
            
            # Strategy 1: Look for JSON array with regex
            json_match = re.search(r'\[.*\]', response_text, re.DOTALL)
            if json_match:
                try:
                    clips_data = json.loads(json_match.group())
                    self.logger.info(f"Successfully parsed JSON array with {len(clips_data)} clips")
                except json.JSONDecodeError as e:
                    self.logger.warning(f"Failed to parse JSON array: {e}")
                    clips_data = None
            
            # Strategy 2: If regex failed, try to find JSON in the entire response
            if not clips_data:
                try:
                    # Look for any JSON-like structure
                    start_idx = response_text.find('[')
                    end_idx = response_text.rfind(']')
                    if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
                        json_str = response_text[start_idx:end_idx + 1]
                        clips_data = json.loads(json_str)
                        self.logger.info(f"Successfully parsed JSON from full response with {len(clips_data)} clips")
                except (json.JSONDecodeError, ValueError) as e:
                    self.logger.warning(f"Failed to parse JSON from full response: {e}")
                    clips_data = None
            
            # Strategy 3: If still no JSON, try to extract structured data manually
            if not clips_data:
                self.logger.warning("JSON parsing failed, attempting manual extraction...")
                try:
                    clips_data = self.extract_clips_manually(response_text)
                    if clips_data:
                        self.logger.info(f"Successfully extracted {len(clips_data)} clips manually")
                except Exception as e:
                    self.logger.error(f"Manual extraction failed: {e}")
                    clips_data = None
            
            if clips_data:
                # Add detected language to each clip
                for clip in clips_data:
                    clip['language'] = detected_language
                
                # Split long clips into multiple focused clips
                clips_data = self.split_long_clips(clips_data, video_duration)
                
                # Apply time padding and validate clips
                processed_clips = []
                for clip in clips_data:
                    # Apply time padding for smoother clips
                    start_seconds = self.video_processing_service.time_to_seconds(clip['start_time'])
                    end_seconds = self.video_processing_service.time_to_seconds(clip['end_time'])
                    
                    # Add padding: 2-3 seconds before, 2-4 seconds after
                    padding_before = min(3, start_seconds)  # Don't go below 0
                    padding_after = min(4, video_duration - end_seconds)  # Don't exceed video duration
                    
                    # Apply padding
                    padded_start = max(0, start_seconds - padding_before)
                    padded_end = min(video_duration, end_seconds + padding_after)
                    
                    # Update clip data with padded times
                    clip['start_time'] = self.format_timestamp(padded_start)
                    clip['end_time'] = self.format_timestamp(padded_end)
                    clip['duration'] = padded_end - padded_start
                    
                    # Ensure viral_score exists (fallback to engagement_score if not)
                    if 'viral_score' not in clip:
                        clip['viral_score'] = clip.get('engagement_score', 5.0)
                    
                    # Ensure other new fields exist with defaults
                    clip.setdefault('hook_type', 'unknown')
                    clip.setdefault('target_audience', 'general')
                    clip.setdefault('emotional_triggers', [])
                    clip.setdefault('shareability_factor', 'engaging content')
                    
                    # Validate clip duration after padding
                    if (clip['duration'] >= self.settings.min_clip_duration and 
                        clip['duration'] <= self.settings.max_clip_duration):
                        processed_clips.append(clip)
                    else:
                        self.logger.warning(f"Skipping clip due to invalid duration after padding: {clip['duration']}s")
                
                # Sort by viral_score (highest first) and limit to 10 clips (increased from 7)
                processed_clips.sort(key=lambda x: x.get('viral_score', 0), reverse=True)
                processed_clips = processed_clips[:10]
                
                self.logger.info(f"AI identified {len(processed_clips)} valid clips after padding, filtering, and splitting")
                return processed_clips
            else:
                # Log the full response for debugging
                self.logger.error(f"Could not parse AI response. Full response: {response_text}")
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
            # Always use the absolute path for reading the file
            clip_path = os.path.join(self.settings.results_dir, clip_info['file_path']) if not os.path.isabs(clip_info['file_path']) else clip_info['file_path']
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
                
                # Create the clip filename
                safe_title = self.video_processing_service.get_safe_filename(segment['title'])
                clip_filename = f"clip_{timestamp}_{i+1}_{safe_title}.mp4"
                clip_path = os.path.join(self.settings.clips_dir, clip_filename)

                # Create the clip
                self.video_processing_service.create_video_clip(
                    video_path, start_seconds, end_seconds, clip_path, aspect_ratio
                )

                # Compute relative path for frontend (relative to 'results/')
                rel_path = os.path.relpath(clip_path, self.settings.results_dir)
                # Compute URL for serving via FastAPI static mount
                clip_url = file_path_to_url(clip_path, request) if request else clip_path
                clip_info = {
                    'clip_number': i + 1,
                    'title': segment['title'],
                    'description': segment['description'],
                    'start_time': segment['start_time'],
                    'end_time': segment['end_time'],
                    'duration': clip_duration,
                    'engagement_score': segment.get('engagement_score', 0),
                    'viral_score': segment.get('viral_score', 0),
                    'hook_type': segment.get('hook_type', 'unknown'),
                    'target_audience': segment.get('target_audience', 'general'),
                    'emotional_triggers': segment.get('emotional_triggers', []),
                    'shareability_factor': segment.get('shareability_factor', 'engaging content'),
                    'file_path': rel_path,  # relative path for frontend
                    'url': clip_url,        # full URL for playback
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

            # --- Save metadata JSON for this batch ---
            import json as _json
            metadata_filename = f"clips_metadata_{timestamp}.json"
            metadata_path = os.path.join(self.settings.results_dir, metadata_filename)
            # Ensure each clip has a 'path' field starting with a slash
            for clip in created_clips:
                if not clip.get('path'):
                    rel_path = os.path.relpath(os.path.join(self.settings.results_dir, clip['file_name']), self.settings.results_dir)
                    clip['path'] = f"/{rel_path}" if not rel_path.startswith("/") else rel_path
                # Always set 'url' to a full URL using file_path_to_url
                if 'file_name' in clip:
                    abs_path = os.path.join(self.settings.clips_dir, clip['file_name'])
                    if request:
                        clip['url'] = file_path_to_url(abs_path, request)
                # Ensure zapcap_result['captioned_video_url'] is a full URL if present
                if 'zapcap_result' in clip and clip['zapcap_result']:
                    zc = clip['zapcap_result']
                    if 'captioned_video_path' in zc and request:
                        zc['captioned_video_url'] = file_path_to_url(zc['captioned_video_path'], request)
                    clip['zapcap_result'] = zc
            with open(metadata_path, "w", encoding="utf-8") as f:
                _json.dump(created_clips, f, ensure_ascii=False, indent=2)
            metadata_url = None
            if request:
                # Serve via /data/results/...
                base_url = str(request.base_url).rstrip("/")
                metadata_url = f"{base_url}/data/results/{metadata_filename}"

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
                },
                'clips_metadata_json': metadata_url or metadata_path
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