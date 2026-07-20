# YouTube Transcript to Notes Pipeline (v2.0)

A powerful, automated tool for generating highly detailed, structured study notes from YouTube videos. Version 2.0 introduces a modern dark-mode GUI, full autonomous YouTube extraction, intelligent API rate-limiting, and secure credential storage.

## Features

### 🌟 New in v2.0
- **Full YouTube Autonomy**: Paste a YouTube URL, and the app automatically extracts the video ID, fetches the transcript, detects chapter markers (via YouTube chapters, descriptions, or auto-chunking), and generates the notes.
- **Modern Tabbed UI**: Beautiful dark-mode interface powered by `customtkinter` with progress bars, status indicators, and mirrored console logging.
- **Intelligent API Pacing**: An Adaptive Rate Limiter proactively manages Requests Per Minute (RPM) and Tokens Per Minute (TPM) based on your provider (e.g., Groq, OpenRouter, Ollama) so you never hit `429 Too Many Requests` errors.
- **Checkpoint & Resume**: If you cancel or the app crashes halfway, it saves its progress in `.checkpoint.json`. On restart, it skips the chapters it has already processed.
- **Secure Credential Storage**: No more `.env` files lying around. API keys are securely stored in your OS's native Credential Manager (Windows Keyring) via an interactive UI dialog.
- **Pre-flight Estimation**: See estimated time, input tokens, and output tokens before the pipeline starts.

### 📝 Core Capabilities
- **Detailed Notes**: Uses LLMs (Local or Cloud) to generate summary, key concepts, code blocks, syntax formulas, examples, and pitfalls for every single chapter.
- **Practical Cheat-Sheet**: Automatically synthesizes the detailed notes into a highly condensed single-page practical guide.
- **PDF Conversion**: One-click Markdown-to-PDF utility built into the UI.

## Overview
1. **Input**: Provide a YouTube URL or manual transcript/timestamps.
2. **Extraction**: Video transcript and metadata are fetched (requires Google OAuth for YouTube Data API; absolutely **no** cookies are used or scraped).
3. **Generation**: The text is chunked and sent to your configured LLM provider to generate rich notes.
4. **Output**: Markdown notes are saved, with optional generation of PDF documents or Knowledge Graphs.

## Installation

### Prerequisites
- Windows 10/11
- Python 3.10+

### Setup
1. **Clone the repository:**
   ```bash
   git clone https://github.com/rishabhahuja12/youtube-transcript-to-notes.git
   cd youtube-transcript-to-notes
   ```

2. **Create a virtual environment and activate it:**
   ```bash
   python -m venv .venv
   .venv\Scripts\activate
   ```

3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

## Usage

1. **Launch the App:**
   You can run the app via the provided launcher:
   ```bash
   python launcher.py
   ```
   Alternatively, you can run the backend directly:
   ```bash
   uvicorn gateway.gateway:app
   ```

2. **First Run Setup:**
   On your first launch, the app will prompt you to set up your LLM provider on the Settings page. 
   - Select your provider (Groq, Gemini, OpenRouter, Ollama, etc.)
   - Provide your API Key and Model Name.
   - Credentials are saved securely to Windows Credential Manager.

3. **Generate Notes:**
   - **YouTube URL Tab (Recommended):** Paste any YouTube URL (watch, youtu.be, embed, etc.), select an output folder, and click **Start Pipeline**.
   - **Manual Files Tab:** If you have offline transcripts/timestamps, you can manually select them and run the pipeline.

4. **Output:**
   The app will generate two markdown files in your selected output directory:
   - `{slug}_Detailed_Notes.md` (Chapter-by-chapter comprehensive notes)
   - `{slug}_Practical_Notes.md` (Quick cheat-sheet)

## Architecture

The v2.0 architecture was fully refactored for modularity, testability, and UI separation:
- `app.py` / `launcher.py`: UI entry points.
- `src/youtube.py`: YouTube extraction via `youtube-transcript-api` and `yt-dlp`.
- `src/pipeline.py`: Core orchestration, rate-limiting logic, and checkpointing.
- `src/parser.py`: Transcript deduplication, outline parsing, and text alignment.
- `src/llm_client.py`: Raw API communication and token bucket rate limiter.
- `src/credentials.py`: System keyring wrapper for secure storage.

## Testing

To run the unit test suite:
```bash
pytest -q
```

## Troubleshooting

- **Rate Limits?** The app automatically paces itself based on your provider. If you switch from Groq to an unlimited Local Ollama model, go to Settings in the UI to update your provider and remove the pacing restrictions.
- **YouTube Extraction Fails?** Ensure you have the latest `yt-dlp` installed, as YouTube frequently updates their backend. (`pip install -U yt-dlp`)
