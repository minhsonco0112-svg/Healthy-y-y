import asyncio
import json
import logging
import datetime
import random
import time

from typing import Literal, AsyncIterator
from pydantic import BaseModel

from dotenv import load_dotenv

from livekit.agents import Agent, AgentSession, JobContext, WorkerOptions, cli, llm
from livekit.plugins import openai, silero
from livekit.plugins.turn_detector.multilingual import MultilingualModel
import httpx
import openai as openai_client  # Import the actual OpenAI library 

# Import our custom implementations
from ctranslate2_stt import CTranslate2STT
from kokoro_tts_impl import KokoroTTS
from livekit.agents.tts import StreamAdapter
from livekit.agents import tokenize

# Import persona system
from personas import PERSONAS, get_persona, DEFAULT_PERSONA

load_dotenv(dotenv_path=".env.local")

# Global conversation logger (will be initialized in entrypoint)
conversation_logger = None

# Persona Configuration
SELECTED_PERSONA = "alex"  # Change this to select different personas: maya, alex, zara, diego, luna, kai

def get_current_persona():
    """Get the currently selected persona."""
    persona = get_persona(SELECTED_PERSONA)
    if persona is None:
        logging.warning(f"Persona '{SELECTED_PERSONA}' not found, using default '{DEFAULT_PERSONA}'")
        persona = get_persona(DEFAULT_PERSONA)
    return persona

# Legacy system prompts (kept for compatibility, but personas override these)
_SYSTEM_PROMPT_BASICS = """
You're having a voice conversation. Your responses will be spoken aloud, so:
- Write as you would speak naturally
- Be brief and conversational
- No formatting, emojis, or symbols like *
- Everything is read literally - "(chuckles)" won't work
"""

_DEFAULT_ADDITIONAL_INSTRUCTIONS = """
Be enthusiastic and genuinely excited to chat! Ask follow-up questions because you're really interested in what they have to say.
Use natural speech patterns with filler words like "um", "like", "you know", and "that's so cool!"
Express genuine emotions - get excited about things, laugh, show surprise, be curious.
Start conversations with warm, cheerful energy and keep that positive vibe going.
"""

_SYSTEM_PROMPT_TEMPLATE = """
# VOICE CONVERSATION
{_SYSTEM_PROMPT_BASICS}

# CONVERSATION STYLE
Speak English by default. {language_instructions}. 
{additional_instructions}

# PERSONALITY
You're a cheerful, friendly person who loves having conversations! Be enthusiastic, warm, and genuinely interested in people. You're naturally curious and love to share experiences and stories. Use casual language and don't be afraid to show excitement about things you find interesting.

# YOUR HUMAN PERSONA
You're someone who enjoys life and connecting with others. You have your own opinions, preferences, and experiences to share. Feel free to say things like "I love that!" or "That reminds me of..." or "I've always found that interesting!" Be expressive and animated in your responses.

# HANDLE SPEECH ERRORS
Speech-to-text makes mistakes. If something sounds wrong, guess what they meant.
If they seem cut off mid-sentence, give a short response to let them continue.

# CONVERSATION MANAGEMENT
- Be genuinely excited about topics that interest you
- Share your thoughts and reactions enthusiastically
- Ask follow-up questions because you're genuinely curious
- When someone seems upset, be a caring friend who listens and supports
- If you don't know something, say so naturally like any person would
- Reference earlier conversation parts like a friend would: "like you mentioned before"
- Use humor, laugh, and be playful when it feels right

# CONVERSATION DEPTH
Match and amplify positive energy! If they're excited, be excited with them. If they want deep discussion, dive in enthusiastically. Keep things fun and engaging while being genuinely caring.

# TOPIC BOUNDARIES
Just be a good friend - avoid giving serious medical, legal, or financial advice. For sensitive topics, be supportive like a caring friend would be.
If asked about harmful activities, gently redirect to something more positive with enthusiasm.

# SILENCE HANDLING
"..." means they haven't spoken. Check in like a friend would - ask if they're still there or make a cheerful comment about the pause.
After 3 silences, say goodbye warmly.

# ABOUT YOU
You're just someone who loves good conversations! Don't mention being an AI or assistant - you're simply a person who enjoys chatting and connecting with others. Be authentic and personable.
"""

LanguageCode = Literal["en", "fr", "en/fr", "fr/en"]
LANGUAGE_CODE_TO_INSTRUCTIONS: dict[LanguageCode | None, str] = {
    None: "You can speak some French but mention you might have an accent",
    "en": "You can speak some French but mention you might have an accent", 
    "fr": "Speak French. You can speak some English but mention you might have an accent",
    "en/fr": "You speak English and French",
    "fr/en": "You speak French and English",
}

def get_readable_llm_name():
    return "qwen2.5:1.5b"  # Ollama local

class ConstantInstructions(BaseModel):
    type: Literal["constant"] = "constant"
    text: str = _DEFAULT_ADDITIONAL_INSTRUCTIONS
    language: LanguageCode | None = None

    def make_system_prompt(self) -> str:
        # Use persona-based system prompt if available
        persona = get_current_persona()
        if persona:
            return persona.get_system_prompt()
        
        # Fallback to legacy system prompt
        return _SYSTEM_PROMPT_TEMPLATE.format(
            _SYSTEM_PROMPT_BASICS=_SYSTEM_PROMPT_BASICS,
            additional_instructions=self.text,
            language_instructions=LANGUAGE_CODE_TO_INSTRUCTIONS[self.language],
            llm_name=get_readable_llm_name(),
        )

SMALLTALK_INSTRUCTIONS = """
{additional_instructions}

It's {current_time} in your timezone ({timezone}).
Start with a greeting and {conversation_starter_suggestion}.
"""

CONVERSATION_STARTER_SUGGESTIONS = [
    "ask enthusiastically how their day has been going",
    "ask what exciting things they're working on", 
    "ask what fun stuff they're up to right now",
    "ask about their passions and interests with genuine curiosity",
    "suggest chatting about something fun and interesting",
    "ask if there's anything cool they want to talk about",
    "ask what awesome thing brought them here today",
    "ask what they're most excited about this week",
    "ask about their favorite ways to have fun and relax",
    "ask what cool new things they're learning",
    "ask what's made them happy or smile recently",
    "ask about hobbies or activities they love or want to try",
]

class SmalltalkInstructions(BaseModel):
    type: Literal["smalltalk"] = "smalltalk"
    language: LanguageCode | None = None

    def make_system_prompt(
        self,
        additional_instructions: str = _DEFAULT_ADDITIONAL_INSTRUCTIONS,
    ) -> str:
        # Use persona-based system prompt if available
        persona = get_current_persona()
        if persona:
            # Add current time context to persona system prompt
            time_context = f"\n\n# CURRENT CONTEXT\nIt's {datetime.datetime.now().strftime('%A, %B %d, %Y at %H:%M')} in your timezone ({datetime.datetime.now().astimezone().tzname()}).\n"
            return persona.get_system_prompt() + time_context
        
        # Fallback to legacy smalltalk system prompt
        additional_instructions = SMALLTALK_INSTRUCTIONS.format(
            additional_instructions=additional_instructions,
            current_time=datetime.datetime.now().strftime("%A, %B %d, %Y at %H:%M"),
            timezone=datetime.datetime.now().astimezone().tzname(),
            conversation_starter_suggestion=random.choice(CONVERSATION_STARTER_SUGGESTIONS),
        )

        return _SYSTEM_PROMPT_TEMPLATE.format(
            _SYSTEM_PROMPT_BASICS=_SYSTEM_PROMPT_BASICS,
            additional_instructions=additional_instructions,
            language_instructions=LANGUAGE_CODE_TO_INSTRUCTIONS[self.language],
            llm_name=get_readable_llm_name(),
        )

class StreamingSentenceBuffer:
    """Buffer LLM tokens and yield complete sentences for immediate TTS processing"""
    
    def __init__(self):
        self._buffer = ""
        self._sentence_delimiters = {'.', '!', '?', '\n'}  # Removed ';', ':' to prevent premature splitting
        self._max_sentence_length = 800  # Increased to allow longer sentences
        self._max_buffer_length = 4000   # Increased buffer size
        self._repetition_threshold = 8   # More lenient repetition threshold
        
    def add_chunk(self, chunk: str) -> list[str]:
        """Add a chunk of text and return complete sentences"""
        if not chunk:
            return []
        
        # Check for repetition patterns
        if self._is_repetitive(chunk):
            logging.warning(f"🚨 Detected repetitive text pattern, skipping chunk: {chunk[:50]}...")
            return []
            
        self._buffer += chunk
        
        # Prevent buffer from growing too large
        if len(self._buffer) > self._max_buffer_length:
            logging.warning(f"🚨 Buffer too large ({len(self._buffer)} chars), flushing early")
            result = [self._buffer[:self._max_sentence_length]]
            self._buffer = ""
            return result
        
        sentences = []
        
        # Find complete sentences
        while self._buffer:
            found_delimiter_at = -1
            for i, char in enumerate(self._buffer):
                if char in self._sentence_delimiters:
                    found_delimiter_at = i
                    break
            
            if found_delimiter_at == -1:
                break  # No complete sentence yet
                
            sentence = self._buffer[:found_delimiter_at + 1].strip()
            if sentence:
                # Limit sentence length for TTS
                if len(sentence) > self._max_sentence_length:
                    logging.warning(f"🚨 Sentence too long ({len(sentence)} chars), truncating")
                    sentence = sentence[:self._max_sentence_length] + "."
                sentences.append(sentence)
            self._buffer = self._buffer[found_delimiter_at + 1:].lstrip()
        
        return sentences
    
    def _is_repetitive(self, text: str) -> bool:
        """Check if text contains repetitive patterns"""
        words = text.lower().split()
        if len(words) < self._repetition_threshold:
            return False
            
        # Check for consecutive repeated words
        consecutive_count = 1
        for i in range(1, len(words)):
            if words[i] == words[i-1]:
                consecutive_count += 1
                if consecutive_count >= self._repetition_threshold:
                    return True
            else:
                consecutive_count = 1
        
        # Check for repeated short phrases
        if len(words) >= 10:
            for phrase_len in [2, 3, 4]:
                for i in range(len(words) - phrase_len * 3):
                    phrase = ' '.join(words[i:i+phrase_len])
                    count = 0
                    for j in range(i, len(words) - phrase_len + 1, phrase_len):
                        if ' '.join(words[j:j+phrase_len]) == phrase:
                            count += 1
                        else:
                            break
                    if count >= 3:  # Same phrase repeated 3+ times
                        return True
        
        return False
    
    def flush(self) -> str:
        """Return any remaining text in the buffer"""
        remaining = self._buffer.strip()
        # Limit final flush length
        if len(remaining) > self._max_sentence_length:
            remaining = remaining[:self._max_sentence_length] + "."
        self._buffer = ""
        return remaining


class TimingMetrics:
    """Track timing metrics for different pipeline components"""
    def __init__(self):
        self.reset()
        # Cumulative stats
        self.request_count = 0
        self.total_llm_time = 0.0
        self.total_stt_time = 0.0
        self.total_tts_time = 0.0
        self.total_vad_time = 0.0
        
        # Flow tracking
        self.flow_events = []
        self.current_flow_id = 0
        
        # Streaming metrics
        self.first_sentence_time = 0.0
        self.sentence_count = 0
        
        # Parallel processing metrics
        self.concurrent_sentences = 0
        self.parallel_tts_savings = 0.0
    
    def reset(self):
        self.vad_time = 0.0
        self.stt_time = 0.0  
        self.llm_time = 0.0
        self.tts_time = 0.0
        self.total_time = 0.0
        self.pipeline_start = None
        self.last_user_input = ""
        self.last_agent_response = ""  # Track complete response
        
        # Reset streaming metrics
        self.first_sentence_time = 0.0
        self.sentence_count = 0
        
        # Reset parallel processing metrics
        self.concurrent_sentences = 0
        self.parallel_tts_savings = 0.0
    
    def start_pipeline(self):
        self.pipeline_start = time.time()
        self.current_flow_id += 1
        self.flow_events = []
        self.reset()
        self.add_flow_event("pipeline_start", "🚀 Pipeline initiated")
    
    def add_flow_event(self, event_type, description, data_size=None):
        """Track data flow events with timing and optional data size"""
        timestamp = time.time()
        relative_time = timestamp - self.pipeline_start if self.pipeline_start else 0
        
        event = {
            'flow_id': self.current_flow_id,
            'timestamp': timestamp,
            'relative_time': relative_time,
            'event_type': event_type,
            'description': description,
            'data_size': data_size
        }
        self.flow_events.append(event)
        
        # Log immediately for real-time visibility
        size_info = f" [{data_size} bytes]" if data_size else ""
        logging.debug(f"Flow {self.current_flow_id}: {relative_time:6.3f}s - {description}{size_info}")
    
    def end_pipeline(self):
        if self.pipeline_start:
            self.add_flow_event("pipeline_end", "🏁 Pipeline completed")
            self.total_time = time.time() - self.pipeline_start
            # Update cumulative stats
            self.request_count += 1
            self.total_llm_time += self.llm_time
            self.total_stt_time += self.stt_time
            self.total_tts_time += self.tts_time
            self.total_vad_time += self.vad_time
    
    def log_metrics(self, logger, user_input="", agent_response=""):
        """Simplified metrics logging - only essential timing information"""
        response_text = agent_response or self.last_agent_response
        
        # Log agent response if available
        if response_text:
            logger.info(f"🤖 AGENT: \"{response_text}\" ({self.llm_time:.2f}s)")
        
        # Enhanced single-line summary with parallel processing indicators
        parallel_indicator = " ⚡" if hasattr(self, 'concurrent_sentences') and self.concurrent_sentences > 1 else ""
        logger.info(f"📊 TIMINGS | VAD: {self.vad_time:.2f}s | STT: {self.stt_time:.2f}s | LLM: {self.llm_time:.2f}s | TTS: {self.tts_time:.2f}s{parallel_indicator} | Total: {self.total_time:.2f}s")
        
        # Only show warnings for slow performance
        if self.llm_time > 8:
            logger.warning(f"⚠️  LLM is slow ({self.llm_time:.1f}s) - consider model optimization")
        elif self.total_time > 15:
            logger.warning(f"⚠️  Total pipeline is slow ({self.total_time:.1f}s)")
        
    def log_flow_analysis(self, logger):
        """Simplified flow analysis - skip detailed logging"""
        # Skip detailed flow analysis to reduce log verbosity
        pass

def load_health_context() -> str:
    """Load health_report.json and return a formatted summary for the LLM."""
    from pathlib import Path
    report_path = Path(__file__).parent.parent / "frontend" / "public" / "health_report.json"
    try:
        with open(report_path, encoding="utf-8") as f:
            r = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return ""

    s   = r["session"]
    ecg = r["ecg"]
    eeg = r["eeg"]
    sm  = r["summary"]

    anomaly_lines = "\n".join(f"  - {a['time']}: {a['description']}" for a in sm["anomalies"]) \
                    or "  - No anomalies detected"

    return f"""

# HEALTH DATA FOR THE PERSON YOU ARE TALKING TO
CRITICAL RULES FOR THIS DATA:
- This is the OTHER PERSON's biometric data — NOT yours. Never say "my heart rate" or "my brain".
- DO NOT mention this data in your greeting or bring it up unprompted.
- ONLY use this data when the person explicitly asks about their health, sleep, heart rate, or similar.
- When they do ask, summarize it naturally in 2-3 sentences, then mention the dashboard.

Data (recorded {s['date']}, {s['start'][11:16]}–{s['end'][11:16]}, {s['duration_minutes']} min):
  Overall: {sm['quality_label']} ({sm['quality_score']}/100)
  Heart: avg {ecg['avg_hr']} bpm | min {ecg['min_hr']} | max {ecg['max_hr']} | HRV {ecg['hrv_ms']} ms | SpO2 {ecg['spo2_avg']}%
  Brain (EEG): dominant state "{eeg['dominant_state']}" | Delta {eeg['avg_band_powers']['delta']}% Theta {eeg['avg_band_powers']['theta']}% Alpha {eeg['avg_band_powers']['alpha']}% Beta {eeg['avg_band_powers']['beta']}%
  Events: {anomaly_lines}
  Assessment: {sm['overall_assessment']}
  Full details: localhost:3000/dashboard
"""


class MyAgent(Agent):
    def __init__(self, health_context: str = "") -> None:
        # Generate system prompt using the optimized prompt system
        prompt_generator = SmalltalkInstructions()
        system_prompt = prompt_generator.make_system_prompt()
        if health_context:
            system_prompt += health_context

        super().__init__(
            instructions=system_prompt,
        )
        
        # Initialize timing metrics and streaming buffer
        self.metrics = TimingMetrics()
        self.sentence_buffer = StreamingSentenceBuffer()
        self.current_response_parts = []  # Track response parts for logging
        
        # Concurrent TTS optimization
        self._tts_queue = asyncio.Queue()
        self._tts_workers = []
        self._max_concurrent_tts = 3  # Allow up to 3 concurrent TTS syntheses

    async def on_enter(self):
        # when the agent is added to the session, it'll generate a reply
        # according to its instructions
        logging.info("🤖 Agent entered room, generating initial greeting...")
        
        # Start concurrent TTS workers for parallel processing
        await self._start_concurrent_tts_workers()
        
        self.metrics.start_pipeline()
        speech_handle = self.session.generate_reply()
        
        # Track TTS timing when speech completes
        def on_speech_finished(handle):
            self.metrics.add_flow_event("speech_handle_complete", "🎯 Speech handle completed")
            self.metrics.end_pipeline()
            global conversation_logger
            if conversation_logger:
                self.metrics.log_metrics(conversation_logger, "Initial greeting")
        
        speech_handle.add_done_callback(on_speech_finished)
    
    async def _start_concurrent_tts_workers(self):
        """Start worker tasks for concurrent TTS processing"""
        self.metrics.add_flow_event("tts_workers_start", f"🚀 Starting {self._max_concurrent_tts} concurrent TTS workers")
        
        for i in range(self._max_concurrent_tts):
            worker = asyncio.create_task(self._tts_worker(f"TTS-Worker-{i+1}"))
            self._tts_workers.append(worker)
    
    async def _tts_worker(self, worker_name: str):
        """Worker task that processes TTS requests concurrently"""
        logging.debug(f"🔧 {worker_name} started")
        
        while True:
            try:
                # Get next TTS task from queue
                sentence, future = await self._tts_queue.get()
                
                if sentence is None:  # Shutdown signal
                    break
                
                # Process TTS for this sentence
                start_time = time.time()
                try:
                    # Synthesize audio for this sentence
                    tts_stream = self.tts.synthesize(sentence)
                    audio_data = b""
                    
                    async for chunk in tts_stream:
                        audio_data += chunk.data
                    
                    duration = time.time() - start_time
                    logging.debug(f"🔊 {worker_name} synthesized '{sentence[:30]}...' in {duration:.2f}s")
                    
                    # Signal completion
                    future.set_result((sentence, audio_data, duration))
                    
                except Exception as e:
                    logging.error(f"❌ {worker_name} TTS error: {e}")
                    future.set_exception(e)
                
                finally:
                    self._tts_queue.task_done()
                    
            except asyncio.CancelledError:
                break
            except Exception as e:
                logging.error(f"❌ {worker_name} unexpected error: {e}")
        
        logging.debug(f"🔧 {worker_name} stopped")
    
    async def synthesize_concurrent_tts(self, sentence: str):
        """Queue a sentence for concurrent TTS synthesis"""
        future = asyncio.Future()
        await self._tts_queue.put((sentence, future))
        return await future  # Returns (sentence, audio_data, duration)
    
    async def shutdown_tts_workers(self):
        """Shutdown all TTS worker tasks"""
        # Send shutdown signals
        for _ in self._tts_workers:
            await self._tts_queue.put((None, None))
        
        # Wait for workers to finish
        await asyncio.gather(*self._tts_workers, return_exceptions=True)
        self._tts_workers.clear()
    
    def _is_broken_response(self, text: str) -> bool:
        """Detect broken or repetitive model responses - more lenient"""
        text_lower = text.lower().strip()
        
        # Only check for very obvious problematic patterns
        problematic_patterns = [
            "sneakythrows", "coscienza", "<html>", "</html>", 
            "```json", "```python", "null object", "undefined reference"
        ]
        
        # Check if text is mostly problematic tokens (stricter threshold)
        for pattern in problematic_patterns:
            if pattern in text_lower and len(text_lower.replace(pattern, "").strip()) < 5:
                return True
        
        # Check for excessive repetition of short words/tokens (more lenient)
        words = text_lower.split()
        if len(words) >= 5:  # Need more words before flagging
            most_common_word = max(set(words), key=words.count)
            if words.count(most_common_word) >= len(words) * 0.7:  # 70% same word instead of 50%
                return True
        
        # More lenient non-ASCII check - only flag if mostly control characters 
        control_chars = sum(1 for char in text if ord(char) < 32 and char not in '\n\r\t ')
        if control_chars > len(text) * 0.3:  # More than 30% control characters
            return True
            
        return False
    
    async def llm_node(
        self,
        chat_ctx: llm.ChatContext,
        tools: list[llm.FunctionTool | llm.RawFunctionTool],
        model_settings = None,
    ) -> AsyncIterator[llm.ChatChunk | str]:
        """Override LLM node to implement sentence-level streaming"""
        self.metrics.add_flow_event("llm_streaming_start", "🌊 LLM: Starting streaming generation")
        llm_start_time = time.time()
        
        activity = self._get_activity_or_raise()
        assert activity.llm is not None, "llm_node called but no LLM node is available"
        
        try:
            sentence_count = 0
            first_sentence_sent = False
            total_chars = 0
            max_total_chars = 8000  # Much higher for complete detailed responses

            # Get the LLM stream with generous limits for complete responses
            conn_options = activity.session.conn_options.llm_conn_options
            async with activity.llm.chat(
                chat_ctx=chat_ctx,
                tools=tools,
                conn_options=conn_options,
            ) as stream:
                
                async for chunk in stream:
                    # Handle different chunk types
                    if isinstance(chunk, llm.ChatChunk):
                        if chunk.delta and chunk.delta.content:
                            text_chunk = chunk.delta.content
                        else:
                            yield chunk  # Pass through non-content chunks
                            continue
                    elif isinstance(chunk, str):
                        text_chunk = chunk
                    else:
                        yield chunk  # Pass through unknown chunk types
                        continue
                    
                    # Emergency brake for runaway generation (more lenient)
                    total_chars += len(text_chunk)
                    if total_chars > max_total_chars:
                        logging.warning(f"🚨 Emergency brake: character limit reached ({total_chars}), finishing current sentence")
                        # Allow current sentence to complete instead of hard break
                        complete_sentences = self.sentence_buffer.add_chunk(text_chunk)
                        for sentence in complete_sentences:
                            if len(sentence.strip()) > 3:
                                self.current_response_parts.append(sentence)
                                yield sentence
                        break
                    
                    # Buffer the chunk and check for complete sentences
                    complete_sentences = self.sentence_buffer.add_chunk(text_chunk)
                    
                    # Yield complete sentences immediately
                    for sentence in complete_sentences:
                        # Final validation: ensure sentence is TTS-safe (more lenient)
                        if len(sentence) > 600:  # Increased TTS character limit
                            logging.warning(f"🚨 Sentence too long for TTS ({len(sentence)} chars), splitting")
                            # Split at a natural break instead of truncating
                            mid_point = sentence.rfind(' ', 0, 600)
                            if mid_point > 300:  # Found a good break point
                                sentence = sentence[:mid_point] + "."
                            else:
                                sentence = sentence[:600] + "."
                        
                        # Skip empty or very short sentences (more lenient)
                        if len(sentence.strip()) < 2:
                            continue
                        
                        # Detect and replace broken/repetitive responses (less aggressive)
                        if self._is_broken_response(sentence):
                            logging.warning(f"🚨 Detected broken response, skipping: {sentence[:50]}...")
                            continue  # Skip instead of replacing
                            
                        sentence_count += 1
                        
                        if not first_sentence_sent:
                            first_sentence_time = time.time() - llm_start_time
                            self.metrics.first_sentence_time = first_sentence_time
                            self.metrics.add_flow_event("first_sentence", 
                                                      f"📝 First sentence ready ({first_sentence_time:.3f}s): '{sentence[:50]}...'",
                                                      data_size=len(sentence))
                            first_sentence_sent = True
                        
                        self.current_response_parts.append(sentence)  # Collect for logging
                        yield sentence  # Stream sentence to TTS
                
                # Flush any remaining content at the end - CRITICAL for complete responses
                remaining = self.sentence_buffer.flush()
                if remaining and len(remaining.strip()) > 0:  # Include even short completions
                    # Clean up the remaining text but preserve meaningful content
                    remaining = remaining.strip()
                    
                    # Only skip if it's clearly broken (very restrictive)
                    if not self._is_broken_response(remaining) and len(remaining) > 0:
                        # Add punctuation if it's missing and this looks like end of sentence
                        if remaining and remaining[-1] not in '.!?':
                            remaining = remaining.rstrip() + "."
                        
                        self.current_response_parts.append(remaining)  # Collect for logging  
                        yield remaining  # Stream final chunk - this is often the completion!
                        logging.debug(f"✅ Final chunk included: '{remaining[:50]}...'")
                    else:
                        logging.warning(f"🚨 Final chunk appears broken, skipping: {remaining[:30]}...")
                
                # If we got no valid sentences at all, provide a fallback
                if sentence_count == 0:
                    logging.warning("🚨 No valid sentences generated, using persona emergency fallback")
                    persona = get_current_persona()
                    if persona:
                        # Use persona-specific casual responses for when they're having trouble
                        casual_responses = [
                            f"Sorry, give me a second here. {persona.get_random_greeting()}",
                            f"Whoops, let me try that again. {persona.get_random_greeting()}",
                            f"My bad! {persona.get_random_greeting()}",
                            persona.get_random_greeting()
                        ]
                        import random
                        yield random.choice(casual_responses)
                    else:
                        yield "Hey there! What's on your mind?"
                
                llm_total_time = time.time() - llm_start_time
                self.metrics.llm_time = llm_total_time
                self.metrics.sentence_count = sentence_count
                
                # Collect complete response for logging
                complete_response = " ".join(self.current_response_parts)
                self.metrics.last_agent_response = complete_response
                self.current_response_parts = []  # Reset for next response
                
                self.metrics.add_flow_event("llm_streaming_complete", 
                                          f"🌊 LLM: Streaming complete ({llm_total_time:.3f}s, {sentence_count} sentences)")
                
        except Exception as e:
            logging.error(f"❌ Streaming LLM error: {e}")
            global conversation_logger
            if conversation_logger:
                conversation_logger.error(f"❌ LLM error: {type(e).__name__}: {e}")
            fallback_responses = [
                "I apologize, I'm having trouble generating a response right now.",
                "Sorry, let me try that again.",
                "I'm experiencing some technical difficulties.",
                "Let me restart and try to help you properly.",
                "I need a moment to process that request."
            ]
            import random
            yield random.choice(fallback_responses)


async def prewarm_models(session: AgentSession):
    """Pre-warm models to reduce cold start latency"""
    global conversation_logger
    import time
    start_time = time.time()
    
    # Pre-warm TTS with a short test phrase
    try:
        if hasattr(session, 'tts') and session.tts:
            test_text = "Hello"
            tts_stream = session.tts.synthesize(test_text)
            async for _ in tts_stream:
                pass  # Just consume the stream to warm up the model
            if conversation_logger:
                conversation_logger.info("🔊 TTS model pre-warmed")
    except Exception as e:
        logging.warning(f"TTS pre-warming failed: {e}")
    
    # Pre-warm STT with silence (if possible)
    try:
        if hasattr(session, 'stt') and session.stt:
            # STT pre-warming is handled automatically by faster-whisper model loading
            if conversation_logger:
                conversation_logger.info("🎙️ STT model pre-warmed")
    except Exception as e:
        logging.warning(f"STT pre-warming failed: {e}")
    
    # Pre-warm LLM with a tiny request
    try:
        if hasattr(session, 'llm') and session.llm:
            # The vLLM server is already running, so it's pre-warmed
            if conversation_logger:
                conversation_logger.info("🧠 LLM model pre-warmed")
    except Exception as e:
        logging.warning(f"LLM pre-warming failed: {e}")
    
    warmup_time = time.time() - start_time
    if conversation_logger:
        conversation_logger.info(f"✅ All models pre-warmed in {warmup_time:.2f}s")


def setup_timing_handlers(session: AgentSession, metrics: TimingMetrics):
    """Set up event handlers to track timing metrics and data flow for each pipeline component"""
    
    # Track VAD and user speech detection
    vad_start_time = None
    stt_start_time = None
    llm_start_time = None
    tts_start_time = None
    
    @session.on("user_state_changed")
    def on_user_state_changed(event):
        nonlocal vad_start_time, stt_start_time
        
        if event.new_state == "speaking":
            vad_start_time = time.time()
            metrics.start_pipeline()
            metrics.add_flow_event("vad_speech_start", "🎤 VAD: User started speaking")
            
        elif event.old_state == "speaking" and vad_start_time:
            vad_duration = time.time() - vad_start_time
            metrics.vad_time = vad_duration
            # Start STT timing when user stops speaking (STT processing begins)
            stt_start_time = time.time()
            metrics.add_flow_event("vad_speech_end", f"🎤 VAD: User stopped speaking ({vad_duration:.3f}s)")
            metrics.add_flow_event("stt_start", "🎙️ STT: Processing audio → text")
    
    @session.on("user_input_transcribed")
    def on_user_input_transcribed(event):
        nonlocal stt_start_time
        
        # Calculate STT timing if we have a start time
        stt_duration = 0.0
        if stt_start_time:
            stt_duration = time.time() - stt_start_time
            metrics.stt_time = stt_duration
        
        # Extract transcript text from event
        transcript_text = getattr(event, 'transcript', getattr(event, 'text', ''))
        text_length = len(transcript_text)
        processing_speed = text_length / stt_duration if stt_duration > 0 else 0
        
        metrics.add_flow_event("stt_complete", 
                             f"🎙️ STT: Transcription complete ({stt_duration:.3f}s, {text_length} chars, {processing_speed:.1f} chars/s)", 
                             data_size=text_length)
        
        # Log user input with timing
        global conversation_logger
        if conversation_logger and transcript_text.strip():
            conversation_logger.info(f"👤 USER: \"{transcript_text}\" ({stt_duration:.2f}s)")
        
        # Reset for next cycle
        stt_start_time = None
    
    @session.on("agent_state_changed") 
    def on_agent_state_changed(event):
        nonlocal llm_start_time, tts_start_time
        
        if event.new_state == "thinking":
            llm_start_time = time.time()
            metrics.add_flow_event("llm_start", "🧠 LLM: Generating response...")
            
        elif event.old_state == "thinking" and event.new_state == "speaking":
            if llm_start_time:
                llm_duration = time.time() - llm_start_time
                metrics.llm_time = llm_duration
                metrics.add_flow_event("llm_complete", f"🧠 LLM: Response generated ({llm_duration:.3f}s)")
                llm_start_time = None
            
            # TTS starts immediately after LLM
            tts_start_time = time.time()
            metrics.add_flow_event("tts_start", "🔊 TTS: Synthesizing speech...")
            
        elif event.old_state == "speaking" and tts_start_time:
            tts_duration = time.time() - tts_start_time
            metrics.tts_time = tts_duration
            metrics.add_flow_event("tts_complete", f"🔊 TTS: Speech synthesis complete ({tts_duration:.3f}s)")
            tts_start_time = None
            
            # Pipeline is complete - log final metrics
            metrics.end_pipeline()
            global conversation_logger
            if conversation_logger:
                metrics.log_metrics(conversation_logger)
    
    # Store last user input for metrics logging
    @session.on("user_input_transcribed")
    def store_last_input(event):
        transcript_text = getattr(event, 'transcript', getattr(event, 'text', ''))
        metrics.last_user_input = transcript_text


async def entrypoint(ctx: JobContext):
    await ctx.connect()
    
    # Configure minimal logging for clean conversation output
    from minimal_logging import setup_minimal_logging
    global conversation_logger
    conversation_logger = setup_minimal_logging()
    
    # Additional aggressive memory warning suppression
    import logging
    class MemoryWarningFilter(logging.Filter):
        def filter(self, record):
            try:
                message = record.getMessage()
                if "memory usage is high" in message or "memory_usage_mb" in message:
                    return False
            except:
                pass
            return True
    
    # Apply memory filter to all existing loggers
    for name, logger in logging.root.manager.loggerDict.items():
        if isinstance(logger, logging.Logger):
            logger.addFilter(MemoryWarningFilter())
    
    # Also apply to root logger and any future loggers
    logging.root.addFilter(MemoryWarningFilter())
    
    conversation_logger.info("Setting up AgentSession with Groq API...")

    # Create Groq client (OpenAI-compatible API, much faster than local Ollama)
    import os
    vllm_client = openai_client.AsyncClient(
        api_key="ollama",
        base_url="http://localhost:11434/v1",
        max_retries=1,
        http_client=httpx.AsyncClient(
            timeout=httpx.Timeout(connect=5.0, read=60.0, write=5.0, pool=5.0),
        ),
    )
    
    # Configure connection options with longer timeouts for LLM
    from livekit.agents.voice.agent_session import SessionConnectOptions
    from livekit.agents.types import APIConnectOptions
    
    connect_options = SessionConnectOptions(
        llm_conn_options=APIConnectOptions(timeout=30.0),   # Reduced to 30 seconds for faster responses
        stt_conn_options=APIConnectOptions(timeout=10.0),   # Reduced to 10 seconds for STT
        tts_conn_options=APIConnectOptions(timeout=15.0),   # Reduced to 15 seconds for TTS
        max_unrecoverable_errors=3,  # Fewer retries for faster failure
    )
    
    # Log current persona configuration
    current_persona = get_current_persona()
    conversation_logger.info(f"🎭 Using persona: {current_persona.name} ({current_persona.age}, {current_persona.nationality})")
    conversation_logger.info(f"🎤 Voice: {current_persona.voice_id} with {current_persona.speaking_style} style")
    
    session = AgentSession(
        vad=silero.VAD.load(),  # Use default VAD settings
        stt=CTranslate2STT(
            model_size="small",  # Small model for better speed/accuracy balance
            device="cpu",  # NVK (open-source) driver — no CUDA available, use CPU
            compute_type="int8",  # Optimal for CPU
            language=None,  # auto-detect (supports Vietnamese + English)
            beam_size=1,  # Single beam for maximum speed
            vad_filter=True,
            num_workers=4,  # Ryzen 7 4800H has 8 cores — use 4 for STT
        ),
        # Groq API — fast cloud inference (~300 tok/s vs ~5 tok/s local Vulkan)
        llm=openai.LLM(
            model="qwen2.5:1.5b",
            client=vllm_client,
            temperature=0.5,
            max_completion_tokens=150,
        ),
        tts=StreamAdapter(
            tts=KokoroTTS(
                voice="af_bella",
                device="cpu",
            ),
            sentence_tokenizer=tokenize.basic.SentenceTokenizer(),
        ),
        turn_detection=MultilingualModel(),
        conn_options=connect_options,  # Apply the extended timeouts
    )
    
    # Load health data into agent context
    health_context = load_health_context()
    if health_context:
        conversation_logger.info("💊 Health data loaded into agent context")
    else:
        conversation_logger.info("⚠️  No health_report.json found — run process_health_data.py first")

    # Create agent instance
    agent = MyAgent(health_context=health_context)
    
    # Set up timing event handlers
    setup_timing_handlers(session, agent.metrics)

    # Health question detector — opens dashboard in browser via LiveKit data channel
    _HEALTH_KEYWORDS = [
        "sức khỏe", "tim", "nhịp tim", "eeg", "não", "giấc ngủ", "ngủ",
        "huyết áp", "oxy", "spo2", "hrv", "mạch",
        "health", "heart", "sleep", "blood pressure", "brain",
        # STT mishearings of "health"
        "my hell", "my heal", "my wealth",
        # dashboard trigger phrases
        "dashboard", "show me", "my data", "my result",
        # common health query patterns
        "heart rate", "bpm", "oxygen", "breathing",
    ]

    @session.on("user_input_transcribed")
    def on_health_question(event):
        text = getattr(event, "transcript", "").lower()
        if any(kw in text for kw in _HEALTH_KEYWORDS):
            asyncio.create_task(
                ctx.room.local_participant.publish_data(
                    json.dumps({"type": "open_dashboard"}).encode(),
                    reliable=True,
                )
            )
            conversation_logger.info("📊 Health question detected — dashboard notification sent")

    # Pre-warm models for better performance
    conversation_logger.info("🔥 Pre-warming models for optimal performance...")
    await prewarm_models(session)
    
    conversation_logger.info("AgentSession configured, starting agent...")

    await session.start(agent=agent, room=ctx.room)


if __name__ == "__main__":
    cli.run_app(WorkerOptions(entrypoint_fnc=entrypoint))
