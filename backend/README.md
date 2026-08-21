# Kotai — Local Voice Assistant (LiveKit + Ollama + Kokoro TTS + faster-whisper)

A fully local, real-time voice assistant. You talk into your browser, and an AI
persona ("Alex" by default) talks back — with **no cloud APIs and no per-use cost**.

Everything runs on your own machine:

| Stage | Technology | Where it runs |
|-------|-----------|---------------|
| 🎙️ **Speech‑to‑Text (STT)** | faster‑whisper / CTranslate2 (`small` model) | in the agent process, **CPU** |
| 🧠 **Language Model (LLM)** | **Ollama** serving `qwen2.5:1.5b` | Ollama service, **GPU** if available |
| 🔊 **Text‑to‑Speech (TTS)** | **Kokoro** (Kokoro‑TTS‑Local, 54 voices) | in the agent process, GPU/CPU |
| 📞 **Real‑time transport** | **LiveKit** (dev server) | local `livekit-server` |
| 💻 **User interface** | **agent‑starter‑react** (Next.js) | local web app on `:3000` |

> **Note for returning users:** earlier versions of this project experimented with
> Kyutai TTS/STT and a vLLM server. The current, working stack is the table above:
> **faster‑whisper STT + Kokoro TTS + Ollama LLM**. You do **not** need Kyutai or vLLM.

---

## Table of Contents
1. [How it works](#how-it-works)
2. [Prerequisites](#1-prerequisites)
3. [Step 2 — System packages](#2-system-packages)
4. [Step 3 — Install Ollama (the LLM engine)](#3-install-ollama-the-llm-engine)
5. [Step 4 — Install the LiveKit server](#4-install-the-livekit-server)
6. [Step 5 — Install Node.js + pnpm (for the web UI)](#5-install-nodejs--pnpm-for-the-web-ui)
7. [Step 6 — Set up the Python backend (the agent)](#6-set-up-the-python-backend-the-agent)
8. [Step 7 — Set up the React frontend](#7-set-up-the-react-frontend)
9. [Step 8 — Run everything](#8-run-everything)
10. [Using it](#9-using-it)
11. [Configuration](#configuration)
12. [Troubleshooting](#troubleshooting)
13. [Project structure](#project-structure)

---

## How it works

```
  You speak ─▶ Browser (localhost:3000) ─▶ LiveKit server (:7880)
                                                  │  audio
                                                  ▼
                                          Python agent (agent.py)
                                                  │
              ┌───────────────────────────────────┼───────────────────────────────────┐
              ▼                                    ▼                                     ▼
   faster-whisper STT                     Ollama LLM (:11434)                      Kokoro TTS
   (audio ➜ text)                  (qwen2.5:1.5b: text ➜ reply)            (reply text ➜ audio)
              └───────────────────────────────────┴───────────────────────────────────┘
                                                  │  audio
                                                  ▼
                                    Browser plays the reply
```

---

## 1. Prerequisites

**Operating system:** Linux or Windows + WSL2 (Ubuntu). These instructions assume
Ubuntu / WSL2. macOS works too but the Ollama/LiveKit install commands differ.

**Hardware:**
- ~8 GB free disk space.
- An **NVIDIA GPU is recommended** (this project was tested on an RTX 4070). It is
  used by Ollama to make replies fast. Without a GPU it still works, but use an even
  smaller model and expect slower replies.

**You will install, step by step below:**
- Python **3.11** (via Miniconda)
- **Ollama** (the LLM engine) — install the **official** build, *not* the snap.
- **LiveKit** server
- **Node.js 18+** and **pnpm**

> ⚠️ **Do not install Ollama from snap** (`snap install ollama`). The snap version is
> sandboxed: it cannot use your GPU and cannot download new models without permission
> errors. Use the official install script in Step 3.

---

## 2. System packages

Open a terminal and run:

```bash
sudo apt update
sudo apt install -y git curl wget build-essential ffmpeg libsndfile1
```

- `ffmpeg`, `libsndfile1` — audio handling for Kokoro / soundfile / pydub.

---

## 3. Install Ollama (the LLM engine)

Official install (sets up a GPU‑enabled background service automatically):

```bash
curl -fsSL https://ollama.com/install.sh | sh
```

You should see `Nvidia GPU detected.` near the end if you have a supported GPU.

**Pull the language model** this project uses (small + fast, ~1 GB):

```bash
ollama pull qwen2.5:1.5b
```

**Verify it runs on the GPU:**

```bash
ollama run qwen2.5:1.5b "say hi in 5 words"   # type /bye to exit
ollama ps                                      # PROCESSOR column should say "100% GPU"
```

If `ollama ps` says `100% CPU`, see [Troubleshooting](#troubleshooting).

---

## 4. Install the LiveKit server

LiveKit handles the real‑time audio between your browser and the agent.

```bash
curl -sSL https://get.livekit.io | bash       # installs `livekit-server`
curl -sSL https://get.livekit.io/cli | bash   # installs `lk` (optional CLI)
```

Verify:
```bash
livekit-server --version
```

We will run it in **dev mode**, which uses the built‑in test credentials
`devkey` / `secret` (already configured in the `.env.local` files in this project).

---

## 5. Install Node.js + pnpm (for the web UI)

```bash
# Node.js 22 (via NodeSource)
curl -fsSL https://deb.nodesource.com/setup_22.x | sudo -E bash -
sudo apt install -y nodejs

# pnpm package manager
sudo npm install -g pnpm

node --version    # should print v22.x
pnpm --version
```

---

## 6. Set up the Python backend (the agent)

We use **Miniconda** with a dedicated Python 3.11 environment so nothing conflicts
with the rest of your system.

**a) Install Miniconda** (skip if you already have conda/anaconda):
```bash
wget https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh -O ~/miniconda.sh
bash ~/miniconda.sh -b -p ~/miniconda
~/miniconda/bin/conda init bash
# close and reopen your terminal so `conda` is available
```

**b) Create and activate a clean environment:**
```bash
conda create -y -n kotai python=3.11
conda activate kotai
```

**c) Install the Python dependencies.** From the `backend/` folder of this project:
```bash
cd backend          # the folder containing agent.py and requirements.txt
pip install -r requirements.txt
```
This pulls LiveKit, faster‑whisper, Kokoro, torch, etc. It is a few GB and takes a
while the first time.

**d) Download the LiveKit helper models** (Silero VAD + turn detector — one time):
```bash
python agent.py download-files
```

**e) Check the config file** `backend/.env.local` already contains the LiveKit dev
credentials (no changes needed for local use):
```env
LIVEKIT_URL=ws://localhost:7880
LIVEKIT_API_KEY=devkey
LIVEKIT_API_SECRET=secret
```

> The Kokoro TTS model (`Kokoro-TTS-Local/kokoro-v1_0.pth`) and its 54 voice files are
> already included in this package — nothing to download for TTS.

---

## 7. Set up the React frontend

```bash
cd frontend         # the agent-starter-react folder
pnpm install
```

Its `frontend/.env.local` is already set to the same LiveKit dev credentials:
```env
LIVEKIT_API_KEY=devkey
LIVEKIT_API_SECRET=secret
LIVEKIT_URL=ws://localhost:7880
```

---

## 8. Run everything

You need **three** terminals running at once. (Ollama is already running in the
background as a service from Step 3 — check with `ollama ps`.)

**Terminal 1 — LiveKit server:**
```bash
livekit-server --dev
```
Wait for `starting LiveKit server { "portHttp": 7880 ... }`.

**Terminal 2 — the agent** (activate the env first):
```bash
conda activate kotai
cd backend
python agent.py dev
```
Wait for `registered worker`. When you talk, this terminal prints the live transcript
(`👤 USER` / `🤖 AGENT`) and timing (`📊 TIMINGS | ... LLM: 0.4s ...`).

**Terminal 3 — the frontend:**
```bash
cd frontend
pnpm dev
```
Wait for `Ready` and `Local: http://localhost:3000`.

**(Optional) Terminal 4 — watch the LLM in real time:**
```bash
journalctl -u ollama -f
```

---

## 9. Using it

1. Open **http://localhost:3000** in Chrome/Edge.
2. Click to **connect / start a call** and **allow microphone access**.
3. Start talking. Alex greets you and replies out loud.

The very first reply after you connect may take a couple of seconds while the model
warms up; after that, replies are fast.

---

## Configuration

All in `backend/agent.py` unless noted.

- **Change the persona** — edit near the top:
  ```python
  SELECTED_PERSONA = "alex"   # options: maya, alex, zara, diego, luna, kai
  ```
  or run `python select_persona.py <name>` (run `python select_persona.py list` to see all).
  Each persona has its own personality and Kokoro voice.

- **Change the LLM model** — pull another model (`ollama pull <model>`), then update
  **both** places in `agent.py` that say `qwen2.5:1.5b` (the connection test and the
  `openai.LLM(model=...)` call). Keep it a *small* model for real‑time voice
  (1–3B params). Bigger models = slower replies.

- **Change the voice** — set a different `voice_id` for a persona in `personas.py`
  (e.g. `af_bella`, `bm_george`, `am_michael` — see the list in `kokoro_tts_impl.py`).

- **Change the STT model size** — in `agent.py`, the `CTranslate2STT(model_size="small", ...)`
  call. Options: `tiny`, `base`, `small`, `medium`, `large-v3` (bigger = more accurate, slower).

---

## Troubleshooting

**No spoken reply / agent log shows `LLM: 0.00s` and Ollama returns HTTP 500.**
The model is too slow (usually because it's running on CPU) and the agent cancels the
reply. Check `ollama ps`:
- If it says `100% CPU`, your GPU isn't being used. Make sure you installed the
  **official** Ollama (not snap), and that `nvidia-smi` works. Reinstall via Step 3.
- Or switch to an even smaller model (e.g. `ollama pull llama3.2:1b`) and point
  `agent.py` at it.

**`ollama ps` shows `100% CPU` even with a GPU.**
You probably have the **snap** Ollama. Remove it and use the official build:
```bash
sudo snap remove ollama
curl -fsSL https://ollama.com/install.sh | sh
```

**`address already in use` on port 7880 / 3000 / 11434.**
Something is already running there. Find and stop it:
```bash
ss -ltnp | grep -E ':7880|:3000|:11434'
kill -9 <pid>
```

**Python import error: `numpy.dtype size changed` / `_ARRAY_API not found` / `numpy.core.multiarray failed to import`.**
A package was compiled against an old NumPy. Rebuild the offenders against the
installed NumPy 2.x:
```bash
pip install --upgrade --force-reinstall --no-cache-dir h5py bottleneck
```
(Using a *fresh* conda env as in Step 6 normally avoids this entirely.)

**`Failed to import Kokoro TTS components` / `No module named 'kokoro'`.**
Dependencies didn't install. Re‑run `pip install -r requirements.txt` inside the
activated `kotai` environment.

**Microphone not working in the browser.**
Use `http://localhost:3000` (not the network IP) — browsers only allow mic access on
`localhost` or HTTPS. Check the site's mic permission.

**The agent connects but never greets you.**
Make sure all three services are up and Ollama has the model:
`ollama list` should show `qwen2.5:1.5b`.

---

## Project structure

```
Kotai-VoiceAgent/
├── README.md                     ← this guide
├── backend/                      ← the Python voice agent
│   ├── agent.py                  ← main entry point (STT + LLM + TTS pipeline)
│   ├── requirements.txt          ← Python dependencies
│   ├── .env.local                ← LiveKit dev credentials
│   ├── ctranslate2_stt.py        ← faster-whisper STT integration
│   ├── kokoro_tts_impl.py        ← Kokoro TTS integration
│   ├── personas.py               ← the 6 voice personas
│   ├── select_persona.py         ← helper to switch persona
│   ├── minimal_logging.py        ← clean conversation logging
│   └── Kokoro-TTS-Local/         ← Kokoro model (kokoro-v1_0.pth) + 54 voices
└── frontend/                     ← agent-starter-react (Next.js web UI)
    ├── package.json
    ├── .env.local
    └── app/ components/ hooks/ lib/ ...
```

## License

MIT — see `LICENSE`.

## Acknowledgments
- [LiveKit](https://livekit.io) — real‑time agent framework
- [Ollama](https://ollama.com) — local LLM serving
- [Kokoro‑TTS](https://huggingface.co/hexgrad/Kokoro-82M) — neural TTS voices
- [faster‑whisper](https://github.com/SYSTRAN/faster-whisper) — fast local STT
