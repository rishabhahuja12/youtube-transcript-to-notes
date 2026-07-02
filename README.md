# YouTube Transcript to Notes

A desktop application that transforms YouTube video transcripts into structured, detailed revision notes and practical cheat-sheets using AI.

## What It Does

1. **Parses** raw YouTube transcript files (with timestamps) and chapter outlines
2. **Segments** the transcript into chapters using timestamp boundaries
3. **Deduplicates** overlapping caption windows for clean text
4. **Generates** two types of study materials via your chosen LLM:
   - **Detailed Revision Notes** — chapter-by-chapter deep-dive with summaries, key concepts, formulas, examples, pitfalls, and quick-revision recaps
   - **Practical Cheat-Sheet** — a consolidated reference guide with comparison tables, diagrams, shortcuts, and step-by-step instructions
5. **Converts** the generated Markdown files to PDF (optional)

## Prerequisites

- Python 3.10+
- An LLM provider (any one of the following):
  - [Ollama](https://ollama.com/) running locally (free, no API key needed)
  - [Grok API](https://console.x.ai/) (free tier available)
  - [OpenRouter](https://openrouter.ai/) (free models available, e.g. DeepSeek R1)
  - [Groq](https://console.groq.com/) (free tier, very fast)
  - Any OpenAI-compatible endpoint

## Setup

### 1. Clone the Repository

```bash
git clone https://github.com/rishabhahuja12/youtube-transcript-to-notes.git
cd youtube-transcript-to-notes
```

### 2. Create a Virtual Environment

```bash
python -m venv .venv
```

### 3. Install Dependencies

```bash
# Windows
.venv\Scripts\pip install customtkinter

# macOS / Linux
.venv/bin/pip install customtkinter
```

### 4. Configure Your LLM Provider

Copy the example config and fill in your details:

```bash
cp .env.example .env
```

Open `.env` in any text editor and set your provider:

```env
# For local Ollama (no API key needed):
PROVIDER=Ollama
ENDPOINT_URL=http://localhost:11434
API_KEY=
MODEL_NAME=llama3

# For Grok API:
PROVIDER=OpenAI Compatible
ENDPOINT_URL=https://api.x.ai/v1
API_KEY=xai-your-key-here
MODEL_NAME=grok-beta

# For OpenRouter (free DeepSeek R1):
PROVIDER=OpenAI Compatible
ENDPOINT_URL=https://openrouter.ai/api/v1
API_KEY=sk-or-v1-your-key-here
MODEL_NAME=deepseek/deepseek-r1:free

# For Groq (free tier):
PROVIDER=OpenAI Compatible
ENDPOINT_URL=https://api.groq.com/openai/v1
API_KEY=gsk_your-key-here
MODEL_NAME=llama-3.3-70b-versatile
```

> **Security Note:** The `.env` file is gitignored and will never be committed to the repository. Your API keys stay local on your machine only.

### 5. Run the Application

```bash
# Windows
.venv\Scripts\python app.py

# macOS / Linux
.venv/bin/python app.py
```

On first launch, if no `.env` is found, a setup help popup will guide you through the configuration.

## Usage

1. **Select your files** in the app:
   - **Transcript File** — the raw `.txt` transcript with timestamps
   - **Timestamps File** — the chapter outline / timestamps list
   - **Output Directory** — where the generated notes will be saved

2. **Click "Start Processing Pipeline"**
   - The app reads your LLM config from `.env`
   - Parses and segments the transcript
   - Calls the LLM for each chapter to generate detailed notes
   - Generates a practical summary cheat-sheet
   - Saves `Course_Detailed_Notes.md` and `Course_Practical_Notes.md`

3. **(Optional) Convert to PDF**
   - Click **"Install PDF Library"** (one-time, installs `markdown-pdf`)
   - Click **"Convert & Save PDF"** to pick a `.md` file and export as PDF

## Project Structure

```
youtube-transcript-to-notes/
├── app.py              # Main desktop application
├── .env.example        # Template for LLM configuration
├── .env                # Your local config (gitignored)
├── .gitignore          # Git ignore rules
├── skills.md           # Pipeline skill definition and templates
├── scripts/
│   ├── parse_outline.py        # Standalone outline parser
│   └── segment_transcript.py   # Standalone transcript segmenter
└── README.md
```

## How the LLM Config Works

- **No credentials are ever shown in the UI or committed to git.**
- LLM provider settings are stored in a `.env` file in the project root.
- The app reads this file at runtime when you click "Start Processing Pipeline".
- A read-only status panel in the UI shows the currently loaded provider/model (API keys are masked).
- You can click **"Edit .env"** in the app to open the file, or **"Refresh LLM Config"** after editing.

## License

MIT
