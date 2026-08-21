"""
Kokoro TTS implementation for LiveKit - Offline high-quality TTS service.
This uses the Kokoro-TTS-Local system for completely offline speech synthesis.
"""

import asyncio
import io
import logging
import os
import sys
import tempfile
import time
from typing import Optional, Dict
import threading
from pathlib import Path

import numpy as np
from pydub import AudioSegment
from livekit import rtc
from livekit.agents import tts

# Add Kokoro-TTS-Local to path
kokoro_path = Path(__file__).parent / "Kokoro-TTS-Local"
if str(kokoro_path) not in sys.path:
    sys.path.insert(0, str(kokoro_path))

# Import Kokoro components
try:
    from models import EnhancedKPipeline
except ImportError as e:
    logging.error(f"Failed to import Kokoro TTS components: {e}")
    logging.error("Make sure Kokoro-TTS-Local is properly installed")
    raise

logger = logging.getLogger(__name__)

class KokoroTTS(tts.TTS):
    """
    Kokoro TTS implementation for LiveKit.
    High-quality neural voices with completely offline operation.
    """
    
    def __init__(
        self,
        *,
        voice: str = "af_bella",  # Default to Bella (Grade A-)
        speed: float = 1.0,  # Speech speed multiplier
        device: str = "auto",  # 'cpu', 'cuda', or 'auto'
        model_path: Optional[str] = None,  # Custom model path
        **kwargs,
    ):
        super().__init__(
            capabilities=tts.TTSCapabilities(
                streaming=False,  # Use StreamAdapter for streaming
            ),
            sample_rate=24000,  # Kokoro outputs at 24kHz
            num_channels=1,
        )
        
        self._voice = voice
        self._speed = speed
        self._device = device
        self._model_path = model_path
        self._pipeline = None
        self._init_lock = threading.Lock()
        
        logger.info(f"Initializing Kokoro TTS with voice: {voice}, device: {device}")
        
        # Initialize pipeline in a separate thread to avoid blocking
        self._init_future = asyncio.create_task(self._initialize_pipeline())
    
    async def _initialize_pipeline(self):
        """Initialize the Kokoro pipeline asynchronously."""
        try:
            def _init_sync():
                with self._init_lock:
                    if self._pipeline is None:
                        logger.info("Loading Kokoro TTS pipeline...")
                        self._pipeline = EnhancedKPipeline(
                            lang_code='a',  # American English
                            model=True  # Load the model
                        )
                        # Set device after initialization
                        if self._device != "auto":
                            self._pipeline.device = self._device
                        else:
                            # Auto-detect best device
                            import torch
                            self._pipeline.device = 'cuda' if torch.cuda.is_available() else 'cpu'
                        logger.info(f"Kokoro TTS pipeline loaded successfully on {self._pipeline.device}")
            
            # Run initialization in thread pool to avoid blocking
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, _init_sync)
            
        except Exception as e:
            logger.error(f"Failed to initialize Kokoro TTS pipeline: {e}")
            raise
    
    async def _ensure_pipeline_ready(self):
        """Ensure the pipeline is initialized before use."""
        if self._pipeline is None:
            await self._init_future
    
    def _validate_voice(self, voice: str) -> str:
        """Validate and normalize voice name."""
        # Map common Edge TTS voices to Kokoro equivalents
        voice_mapping = {
            # American English Female
            "en-US-AriaNeural": "af_bella",      # Warm and friendly 
            "en-US-JennyNeural": "af_heart",     # Premium quality
            "en-US-SaraNeural": "af_aoede",      # Smooth and melodic
            "en-US-NancyNeural": "af_nicole",    # Professional
            "en-US-JaneNeural": "af_sarah",      # Casual and approachable
            
            # American English Male  
            "en-US-DavisNeural": "am_adam",      # Strong and confident
            "en-US-JasonNeural": "am_michael",   # Warm and trustworthy
            "en-US-TonyNeural": "am_fenrir",     # Deep and powerful
            "en-US-GuyNeural": "am_eric",        # Professional
            
            # British English Female
            "en-GB-SoniaNeural": "bf_emma",      # Warm and professional
            "en-GB-LibbyNeural": "bf_alice",     # Refined and elegant
            "en-GB-MaisieNeural": "bf_lily",     # Sweet and gentle
            
            # British English Male
            "en-GB-RyanNeural": "bm_george",     # Classic British
            "en-GB-ThomasNeural": "bm_daniel",   # Polished and professional
        }
        
        # Use mapping if available, otherwise use the voice as-is
        mapped_voice = voice_mapping.get(voice, voice)
        
        # Validate that the voice exists in Kokoro's available voices
        available_voices = [
            # American English Female
            "af_heart", "af_alloy", "af_aoede", "af_bella", "af_jessica", 
            "af_kore", "af_nicole", "af_nova", "af_river", "af_sarah", "af_sky",
            # American English Male
            "am_adam", "am_echo", "am_eric", "am_fenrir", "am_liam", 
            "am_michael", "am_onyx", "am_puck", "am_santa",
            # British English Female
            "bf_alice", "bf_emma", "bf_isabella", "bf_lily",
            # British English Male  
            "bm_daniel", "bm_fable", "bm_george", "bm_lewis",
            # Other languages available but focusing on English for now
        ]
        
        if mapped_voice not in available_voices:
            logger.warning(f"Voice '{mapped_voice}' not found, using default 'af_bella'")
            return "af_bella"
        
        return mapped_voice
        
    def synthesize(
        self,
        text: str,
        *,
        conn_options: rtc.RtcConfiguration = rtc.RtcConfiguration(),
    ) -> "KokoroTTSChunkedStream":
        return KokoroTTSChunkedStream(
            text=text,
            tts=self,
            conn_options=conn_options,
        )


class KokoroTTSChunkedStream(tts.ChunkedStream):
    """Chunked stream for Kokoro TTS audio synthesis."""

    def __init__(
        self,
        *,
        tts: KokoroTTS,
        text: str,
        conn_options: rtc.RtcConfiguration,
    ):
        super().__init__(tts=tts, input_text=text, conn_options=conn_options)
        self._tts = tts
        self._text = text

    async def _run(self) -> None:
        """Implementation of abstract _run method."""
        await self._main_task()
        
    async def _main_task(self) -> None:
        """Main synthesis task using Kokoro TTS."""
        try:
            logger.debug(f"Synthesizing with Kokoro: {self._text[:50]}...")
            start_time = time.time()
            
            # Ensure pipeline is ready
            await self._tts._ensure_pipeline_ready()
            
            # Validate and normalize voice
            voice = self._tts._validate_voice(self._tts._voice)
            
            # Clean text for TTS (remove special characters that might cause issues)
            clean_text = self._text.strip()
            if not clean_text:
                logger.warning("Empty text provided for synthesis")
                return
            
            # Generate speech using Kokoro TTS
            def _generate_sync():
                try:
                    # Build voice path - voices are in Kokoro-TTS-Local/voices directory
                    voice_path = Path("Kokoro-TTS-Local/voices").resolve() / f"{voice}.pt"
                    
                    if not voice_path.exists():
                        logger.error(f"Voice file not found: {voice_path}")
                        return None

                    # Use the pipeline as a callable (generator)
                    logger.info(f"Generating speech with voice: {voice_path}")
                    generator = self._tts._pipeline(
                        clean_text,
                        voice=str(voice_path),
                        speed=self._tts._speed,
                        split_pattern=r'\n+'
                    )

                    # Collect all audio segments
                    all_audio = []
                    
                    for gs, ps, audio in generator:
                        if audio is not None:
                            # Convert numpy array to tensor if needed
                            import torch
                            if isinstance(audio, np.ndarray):
                                audio = torch.from_numpy(audio).float()
                            all_audio.append(audio)
                            logger.info(f"Generated segment: {gs}")

                    if all_audio:
                        # Concatenate all audio segments
                        if len(all_audio) == 1:
                            final_audio = all_audio[0]
                        else:
                            import torch
                            final_audio = torch.cat(all_audio, dim=0)
                        
                        # Convert to numpy for processing
                        return final_audio.numpy()
                    else:
                        logger.warning("No audio data generated by Kokoro TTS")
                        return None
                        
                except Exception as e:
                    logger.error(f"Kokoro TTS generation failed: {e}")
                    import traceback
                    traceback.print_exc()
                    return None
            
            # Run synthesis in thread pool to avoid blocking
            loop = asyncio.get_event_loop()
            audio_data = await loop.run_in_executor(None, _generate_sync)
            
            if audio_data is None:
                logger.warning("No audio data generated by Kokoro TTS")
                return
                
            synthesis_time = time.time() - start_time
            logger.debug(f"Kokoro TTS completed in {synthesis_time:.2f}s")
            
            try:
                # Convert audio data to the format expected by LiveKit
                if isinstance(audio_data, np.ndarray):
                    # Kokoro returns float32 audio data, convert to int16 PCM
                    if audio_data.dtype == np.float32:
                        # Ensure audio is in range [-1, 1] and convert to int16
                        audio_data = np.clip(audio_data, -1.0, 1.0)
                        audio_int16 = (audio_data * 32767).astype(np.int16)
                    else:
                        audio_int16 = audio_data.astype(np.int16)
                    
                    # Convert to bytes
                    pcm_data = audio_int16.tobytes()
                    
                    samples_per_channel = len(audio_int16)
                    
                    # Create audio frame with PCM data
                    audio_frame = rtc.AudioFrame(
                        data=pcm_data,
                        sample_rate=24000,  # Kokoro outputs at 24kHz
                        num_channels=1,
                        samples_per_channel=samples_per_channel,
                    )
                    
                elif isinstance(audio_data, bytes):
                    # If Kokoro returns bytes, assume it's already PCM data
                    samples_per_channel = len(audio_data) // 2  # 16-bit = 2 bytes per sample
                    
                    audio_frame = rtc.AudioFrame(
                        data=audio_data,
                        sample_rate=24000,
                        num_channels=1,
                        samples_per_channel=samples_per_channel,
                    )
                    
                else:
                    logger.error(f"Unexpected audio data type: {type(audio_data)}")
                    return
                
            except Exception as decode_error:
                logger.error(f"Failed to process Kokoro audio data: {decode_error}")
                return
            
            await self._emit_audio_frame(audio_frame, request_id="kokoro_tts")
            
        except Exception as e:
            logger.error(f"Error in Kokoro TTS synthesis: {e}")
            raise

    async def _emit_audio_frame(self, frame: rtc.AudioFrame, request_id: str):
        """Emit an audio frame."""
        event = tts.SynthesizedAudio(
            request_id=request_id,
            frame=frame,
        )
        self._event_ch.send_nowait(event)

    async def aclose(self) -> None:
        """Close the stream."""
        await super().aclose()


# Voice mapping for personas - maps Edge TTS voices to best Kokoro equivalents
PERSONA_VOICE_MAPPING = {
    # Maya (American Female, energetic/creative) - AriaNeural -> af_bella (warm and friendly)
    "en-US-AriaNeural": "af_bella",
    
    # Alex (British Male, witty/laid-back) - RyanNeural -> bm_george (classic British)
    "en-GB-RyanNeural": "bm_george", 
    
    # Zara (American Female, enthusiastic) - SaraNeural -> af_aoede (smooth and melodic)
    "en-US-SaraNeural": "af_aoede",
    
    # Diego (Mexican Male, confident) - May need am_fenrir (deep and powerful)
    "es-MX-JorgeNeural": "am_fenrir",
    
    # Luna (Japanese Female, calm) - Use Japanese voice jf_alpha
    "ja-JP-NanamiNeural": "jf_alpha",
    
    # Kai (American Male, energetic) - DavisNeural -> am_michael (warm and trustworthy)
    "en-US-DavisNeural": "am_michael",
    
    # Additional common mappings
    "en-US-JennyNeural": "af_heart",     # Premium quality female
    "en-US-NancyNeural": "af_nicole",    # Professional female
    "en-US-JaneNeural": "af_sarah",      # Casual female
    "en-US-JasonNeural": "am_michael",   # Friendly male
    "en-US-TonyNeural": "am_adam",       # Strong male
    "en-US-GuyNeural": "am_eric",        # Professional male
    "en-GB-SoniaNeural": "bf_emma",      # British female
    "en-GB-LibbyNeural": "bf_alice",     # Refined British female
}

# Available Kokoro voices with quality ratings
KOKORO_VOICES = {
    # American English Female (Grade A to D)
    "af_heart": {"grade": "A", "description": "Premium quality voice", "gender": "female", "language": "en-US"},
    "af_bella": {"grade": "A-", "description": "Warm and friendly", "gender": "female", "language": "en-US"},
    "af_nicole": {"grade": "B-", "description": "Professional and articulate", "gender": "female", "language": "en-US"},
    "af_aoede": {"grade": "C+", "description": "Smooth and melodic", "gender": "female", "language": "en-US"},
    "af_kore": {"grade": "C+", "description": "Bright and energetic", "gender": "female", "language": "en-US"},
    "af_sarah": {"grade": "C+", "description": "Casual and approachable", "gender": "female", "language": "en-US"},
    "af_alloy": {"grade": "C", "description": "Clear and professional", "gender": "female", "language": "en-US"},
    "af_nova": {"grade": "C", "description": "Modern and dynamic", "gender": "female", "language": "en-US"},
    "af_sky": {"grade": "C-", "description": "Light and airy", "gender": "female", "language": "en-US"},
    "af_jessica": {"grade": "D", "description": "Natural and engaging", "gender": "female", "language": "en-US"},
    "af_river": {"grade": "D", "description": "Soft and flowing", "gender": "female", "language": "en-US"},
    
    # American English Male (Grade C+ to F+)
    "am_fenrir": {"grade": "C+", "description": "Deep and powerful", "gender": "male", "language": "en-US"},
    "am_michael": {"grade": "C+", "description": "Warm and trustworthy", "gender": "male", "language": "en-US"},
    "am_puck": {"grade": "C+", "description": "Playful and energetic", "gender": "male", "language": "en-US"},
    "am_echo": {"grade": "D", "description": "Resonant and clear", "gender": "male", "language": "en-US"},
    "am_eric": {"grade": "D", "description": "Professional and authoritative", "gender": "male", "language": "en-US"},
    "am_liam": {"grade": "D", "description": "Friendly and conversational", "gender": "male", "language": "en-US"},
    "am_onyx": {"grade": "D", "description": "Rich and sophisticated", "gender": "male", "language": "en-US"},
    "am_santa": {"grade": "D-", "description": "Holiday-themed voice", "gender": "male", "language": "en-US"},
    "am_adam": {"grade": "F+", "description": "Strong and confident", "gender": "male", "language": "en-US"},
    
    # British English Female (Grade B- to D)
    "bf_emma": {"grade": "B-", "description": "Warm and professional", "gender": "female", "language": "en-GB"},
    "bf_isabella": {"grade": "C", "description": "Sophisticated and clear", "gender": "female", "language": "en-GB"},
    "bf_alice": {"grade": "D", "description": "Refined and elegant", "gender": "female", "language": "en-GB"},
    "bf_lily": {"grade": "D", "description": "Sweet and gentle", "gender": "female", "language": "en-GB"},
    
    # British English Male (Grade C to D+)
    "bm_fable": {"grade": "C", "description": "Storytelling and engaging", "gender": "male", "language": "en-GB"},
    "bm_george": {"grade": "C", "description": "Classic British accent", "gender": "male", "language": "en-GB"},
    "bm_daniel": {"grade": "D", "description": "Polished and professional", "gender": "male", "language": "en-GB"},
    "bm_lewis": {"grade": "D+", "description": "Modern British accent", "gender": "male", "language": "en-GB"},
    
    # Japanese Female (Grade C+ to C-)
    "jf_alpha": {"grade": "C+", "description": "Standard Japanese female", "gender": "female", "language": "ja-JP"},
    "jf_gongitsune": {"grade": "C", "description": "Based on classic tale", "gender": "female", "language": "ja-JP"},
    "jf_tebukuro": {"grade": "C", "description": "Glove story voice", "gender": "female", "language": "ja-JP"},
    "jf_nezumi": {"grade": "C-", "description": "Mouse bride tale voice", "gender": "female", "language": "ja-JP"},
    
    # Japanese Male (Grade C-)
    "jm_kumo": {"grade": "C-", "description": "Spider thread tale voice", "gender": "male", "language": "ja-JP"},
}