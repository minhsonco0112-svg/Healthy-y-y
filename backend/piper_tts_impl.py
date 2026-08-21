"""
Piper TTS implementation for LiveKit.
Fast CPU-optimized neural TTS using ONNX runtime — no GPU required.
"""

import asyncio
import io
import logging
import time
import threading
import wave
from pathlib import Path
from typing import Optional

import numpy as np
from livekit import rtc
from livekit.agents import tts

logger = logging.getLogger(__name__)


class PiperTTS(tts.TTS):
    """
    Piper TTS for LiveKit. ~0.1–0.2s on CPU vs ~15s for Kokoro.
    Models: https://github.com/rhasspy/piper/blob/master/VOICES.md
    """

    def __init__(
        self,
        *,
        model_path: str,
        config_path: Optional[str] = None,
        speaker_id: Optional[int] = None,
        length_scale: float = 1.0,    # >1 = slower speech
        noise_scale: float = 0.667,
        noise_w: float = 0.8,
    ):
        super().__init__(
            capabilities=tts.TTSCapabilities(streaming=False),
            sample_rate=22050,
            num_channels=1,
        )

        self._model_path = model_path
        self._config_path = config_path or f"{model_path}.json"
        self._speaker_id = speaker_id
        self._length_scale = length_scale
        self._noise_scale = noise_scale
        self._noise_w = noise_w
        self._voice = None
        self._actual_sample_rate = 22050
        self._init_lock = threading.Lock()

        logger.info(f"Initializing Piper TTS: {Path(model_path).name}")
        self._init_future = asyncio.create_task(self._initialize())

    async def _initialize(self):
        def _load():
            with self._init_lock:
                if self._voice is not None:
                    return
                from piper import PiperVoice
                logger.info("Loading Piper voice model (ONNX)...")
                self._voice = PiperVoice.load(
                    model_path=self._model_path,
                    config_path=self._config_path,
                )
                self._actual_sample_rate = self._voice.config.sample_rate
                logger.info(f"Piper TTS ready — sample_rate={self._actual_sample_rate}Hz")

        await asyncio.get_event_loop().run_in_executor(None, _load)

    async def _ensure_ready(self):
        if self._voice is None:
            await self._init_future

    def synthesize(self, text: str, *, conn_options=None) -> "PiperTTSChunkedStream":
        return PiperTTSChunkedStream(tts=self, text=text, conn_options=conn_options)


class PiperTTSChunkedStream(tts.ChunkedStream):

    def __init__(self, *, tts: PiperTTS, text: str, conn_options):
        super().__init__(tts=tts, input_text=text, conn_options=conn_options)
        self._tts = tts
        self._text = text

    async def _run(self):
        await self._synthesize()

    async def _synthesize(self):
        try:
            start = time.time()
            await self._tts._ensure_ready()

            text = self._text.strip()
            if not text:
                return

            def _synth_sync():
                buf = io.BytesIO()
                with wave.open(buf, "wb") as wav:
                    self._tts._voice.synthesize(
                        text,
                        wav,
                        speaker_id=self._tts._speaker_id,
                        length_scale=self._tts._length_scale,
                        noise_scale=self._tts._noise_scale,
                        noise_w=self._tts._noise_w,
                    )
                buf.seek(0)
                return buf.read()

            wav_bytes = await asyncio.get_event_loop().run_in_executor(None, _synth_sync)

            with wave.open(io.BytesIO(wav_bytes), "rb") as wav:
                sample_rate = wav.getframerate()
                n_channels = wav.getnchannels()
                n_frames = wav.getnframes()
                pcm_data = wav.readframes(n_frames)

            elapsed = time.time() - start
            logger.debug(f"Piper synthesized {len(text)} chars in {elapsed:.2f}s")

            frame = rtc.AudioFrame(
                data=pcm_data,
                sample_rate=sample_rate,
                num_channels=n_channels,
                samples_per_channel=n_frames,
            )
            self._event_ch.send_nowait(
                tts.SynthesizedAudio(request_id="piper_tts", frame=frame)
            )

        except Exception as e:
            logger.error(f"Piper TTS error: {e}")
            raise

    async def aclose(self):
        await super().aclose()
