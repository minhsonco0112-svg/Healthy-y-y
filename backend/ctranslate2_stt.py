"""
Custom STT implementation using CTranslate2 and faster-whisper
"""

import asyncio
import gc
import io
import logging
import numpy as np
import wave
from typing import AsyncIterable, Optional, Union
from dataclasses import dataclass

from faster_whisper import WhisperModel
from livekit import rtc
from livekit.agents import stt, utils
from livekit.agents.types import DEFAULT_API_CONNECT_OPTIONS, APIConnectOptions
from livekit.agents.utils import AudioBuffer

logger = logging.getLogger(__name__)


@dataclass
class CTranslate2STTOptions:
    model_size: str = "large-v3"
    device: str = "cuda"
    compute_type: str = "float16"
    language: str = "en"
    beam_size: int = 5
    vad_filter: bool = True
    vad_parameters: Union[dict, None] = None


class CTranslate2STT(stt.STT):
    def __init__(
        self,
        *,
        model_size: str = "large-v3",
        device: str = "cuda",
        compute_type: str = "float16",
        language: str = "en",
        beam_size: int = 5,
        vad_filter: bool = True,
        vad_parameters: Union[dict, None] = None,
        num_workers: int = 1,  # Limit CPU workers to reduce memory
    ):
        """
        Create a new instance of CTranslate2 STT using faster-whisper.
        
        Args:
            model_size: Size of the Whisper model ("tiny", "base", "small", "medium", "large-v2", "large-v3")
            device: Device to run on ("cuda", "cpu")
            compute_type: Precision ("float16", "int8", "int8_float16", "float32")
            language: Language code for transcription
            beam_size: Beam size for decoding
            vad_filter: Whether to use VAD filtering
            vad_parameters: Additional VAD parameters
        """
        super().__init__(
            capabilities=stt.STTCapabilities(streaming=False, interim_results=False)
        )
        
        self._opts = CTranslate2STTOptions(
            model_size=model_size,
            device=device,
            compute_type=compute_type,
            language=language,
            beam_size=beam_size,
            vad_filter=vad_filter,
            vad_parameters=vad_parameters or {}
        )
        self._num_workers = num_workers
        
        # Initialize the model - this will download if not cached
        logger.info(f"Loading CTranslate2 Whisper model: {model_size} on {device} with {compute_type}")
        try:
            self._model = WhisperModel(
                model_size,
                device=device,
                compute_type=compute_type,
                num_workers=num_workers,  # Limit workers to reduce memory usage
                download_root=None,  # Use default cache location
                local_files_only=False
            )
            logger.info(f"CTranslate2 Whisper model loaded successfully (memory optimized with {num_workers} workers)")
        except Exception as e:
            logger.error(f"Failed to load CTranslate2 model: {e}")
            raise

    def stream(
        self,
        *,
        language: Union[str, None] = None,
        conn_options: APIConnectOptions = DEFAULT_API_CONNECT_OPTIONS,
    ) -> "CTranslate2SpeechStream":
        """Create a new speech stream for transcription."""
        effective_language = language or self._opts.language
        return CTranslate2SpeechStream(
            stt=self,
            language=effective_language,
            conn_options=conn_options,
        )

    async def _transcribe_audio_buffer(
        self,
        buffer: AudioBuffer,
        language: str,
    ) -> stt.SpeechEvent:
        """Transcribe audio buffer using faster-whisper."""
        try:
            # Convert AudioBuffer to numpy array
            audio_data = self._audio_buffer_to_numpy(buffer)
            
            # Run transcription in thread pool to avoid blocking
            segments, info = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: self._model.transcribe(
                    audio_data,
                    language=language if language != "auto" else None,
                    beam_size=self._opts.beam_size,
                    vad_filter=self._opts.vad_filter,
                    vad_parameters=self._opts.vad_parameters
                )
            )
            
            # Combine all segments into a single transcript
            transcript_text = ""
            for segment in segments:
                transcript_text += segment.text
            
            transcript_text = transcript_text.strip()
            
            logger.debug(f"Transcribed: '{transcript_text}' (language: {info.language}, confidence: {info.language_probability:.2f})")
            
            # Clean up audio data to free memory
            del audio_data
            gc.collect()
            
            return stt.SpeechEvent(
                type=stt.SpeechEventType.FINAL_TRANSCRIPT,
                alternatives=[
                    stt.SpeechData(
                        text=transcript_text,
                        language=info.language,
                        confidence=info.language_probability,
                    )
                ],
            )
            
        except Exception as e:
            logger.error(f"CTranslate2 transcription error: {e}")
            return stt.SpeechEvent(
                type=stt.SpeechEventType.FINAL_TRANSCRIPT,
                alternatives=[
                    stt.SpeechData(
                        text="",
                        language=language,
                        confidence=0.0,
                    )
                ],
            )

    async def _recognize_impl(
        self,
        buffer: AudioBuffer,
        *,
        language: Union[str, None] = None,
        conn_options: APIConnectOptions,
    ) -> stt.SpeechEvent:
        """Implementation required by the STT base class."""
        effective_language = language or self._opts.language
        return await self._transcribe_audio_buffer(buffer, effective_language)

    def _audio_buffer_to_numpy(self, buffer: AudioBuffer) -> np.ndarray:
        """Convert AudioBuffer to numpy array for faster-whisper."""
        # AudioBuffer is Union[list[AudioFrame], AudioFrame]
        if isinstance(buffer, list):
            # If it's a list of AudioFrames, concatenate them
            audio_frames = buffer
        else:
            # If it's a single AudioFrame, make it a list
            audio_frames = [buffer]
        
        # Collect all audio data
        audio_data = []
        for frame in audio_frames:
            # AudioFrame.data contains the raw audio bytes
            frame_data = np.frombuffer(frame.data, dtype=np.int16)
            audio_data.append(frame_data)
        
        # Concatenate all frames
        if audio_data:
            audio_np = np.concatenate(audio_data)
        else:
            audio_np = np.array([], dtype=np.int16)
        
        # Convert to float32 and normalize to [-1, 1] range
        audio_np = audio_np.astype(np.float32) / 32768.0
        
        return audio_np


class CTranslate2SpeechStream(stt.SpeechStream):
    def __init__(
        self,
        *,
        stt: CTranslate2STT,
        language: str,
        conn_options: APIConnectOptions,
    ):
        super().__init__(stt=stt, conn_options=conn_options)
        self._stt = stt
        self._language = language
        self._audio_frames = []  # List of AudioFrame objects
        
    @utils.log_exceptions(logger=logger)
    async def _main_task(self) -> None:
        """Main task for processing audio stream."""
        try:
            async for audio_frame in self._input:
                # Add frame to buffer
                self._audio_frames.append(audio_frame)
                
                # Process accumulated audio for ultra-low latency
                # Process every 2-3 frames for minimum latency
                if len(self._audio_frames) >= 2:  # Process every 2 frames for minimum latency
                    # Create a speech event using the current buffer
                    event = await self._stt._transcribe_audio_buffer(
                        self._audio_frames, self._language
                    )
                    
                    if event.alternatives:
                        # Send the result
                        self._input_done(event)
                        
                    # Clear buffer after processing and force garbage collection
                    self._audio_frames.clear()
                    gc.collect()  # Force memory cleanup
                    
        except Exception as e:
            logger.error(f"Error in CTranslate2 speech stream: {e}")
            self._input_done()

    def update_options(self, *, language: str) -> None:
        """Update stream options."""
        self._language = language