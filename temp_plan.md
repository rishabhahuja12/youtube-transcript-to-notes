# Implementation Plan: React + FastAPI UI Migration

> **Goal**: Replace the monolithic CustomTkinter `app.py` with a modern **React (Vite) + FastAPI + pywebview** architecture that can be published as both an `.exe` desktop app and a web preview.

> [!IMPORTANT]
> The entire `src/` package remains **100% untouched**. This is a UI-layer replacement only.

---

## Architecture

```
yt_transcriptor/
├── src/                    # ← UNTOUCHED backend package
│
├── server.py               # ← NEW: FastAPI server wrapping src/
├── launcher.py             # ← NEW: Starts server + pywebview window
│
├── frontend/               # ← NEW: React (Vite) app
│   ├── src/
│   │   ├── components/     # Reusable UI components
│   │   ├── pages/          # Full-page views
│   │   ├── context/        # React Context providers
│   │   ├── utils/          # api.js, helpers
│   │   ├── App.jsx
│   │   ├── App.css
│   │   └── main.jsx
│   ├── public/
│   ├── index.html
│   ├── package.json
│   └── vite.config.js
│
├── app_legacy.py           # ← RENAMED from app.py (kept as fallback)
├── tests/
│   ├── test_server.py      # ← NEW: FastAPI endpoint tests
│   └── (existing tests)
├── rules.md                # ← UPDATED for new stack
├── AGENTS.md               # ← UPDATED for new stack
└── requirements.txt        # ← UPDATED with fastapi, uvicorn, pywebview
```

### Distribution Modes

| Mode | Command | What happens |
|------|---------|-------------|
| **Dev** | `python server.py` + `cd frontend && npm run dev` | FastAPI on :8000, Vite on :5173 with hot reload |
| **Web Preview** | `python server.py` | FastAPI serves built React from `frontend/dist/` on :8000 |
| **Desktop .exe** | `python launcher.py` | Starts server + opens pywebview native window |
| **Packaged .exe** | Run `build_exe.py` | PyInstaller bundles everything into a single `.exe` |

---

## Stage 1: FastAPI Server — Core REST Endpoints

### Deliverables

#### [NEW] `server.py`
FastAPI application with these REST endpoints:

| Method | Endpoint | Backend Function | Response |
|--------|----------|-----------------|----------|
| `GET` | `/api/library` | `load_recent_outputs()` | `[{title, path, date, badges}]` |
| `POST` | `/api/library/add` | `add_recent_output(path)` | `{success: true}` |
| `GET` | `/api/course/{course_id}/files` | `os.listdir()` | `[{name, type, size}]` |
| `GET` | `/api/course/{course_id}/notes/{file}` | Read `.md` file | `{content: "markdown..."}` |
| `GET` | `/api/course/{course_id}/graph` | Read `_knowledge_graph.html` | `{html: "..."}` |
| `GET` | `/api/course/{course_id}/keyframes` | List `.jpg/.png` files | `[{name, url}]` |
| `GET` | `/api/settings/pool` | `get_provider_pool_or_legacy()` | `[{provider, model, masked_key, capability}]` |
| `POST` | `/api/settings/pool` | `store_provider_pool()` | `{success: true}` |
| `GET` | `/api/settings/health` | Check Ollama/Playwright/Keyring | `{ollama, playwright, keyring}` |
| `POST` | `/api/pipeline/cancel` | `cancel_event.set()` | `{success: true}` |
| `POST` | `/api/chat/send` | `ChatSession.send()` | `{response: "..."}` |
| `POST` | `/api/chat/clear` | Reset session | `{success: true}` |
| `POST` | `/api/pdf/export` | Playwright PDF conversion | `{path: "output.pdf"}` |

- Path validation: All `course_id` params must be validated against `recent_outputs` to prevent path traversal.
- Static file serving: `/static/{course_id}/{filename}` for keyframe images.
- CORS: Only allow `http://localhost:5173` and `http://localhost:8000`.
- Pydantic models for all request/response bodies.

#### [NEW] `tests/test_server.py`
- Test all REST endpoints using `httpx.AsyncClient`.
- Test path traversal prevention (e.g., `course_id=../../etc`).
- Test CORS headers.

#### [UPDATE] `requirements.txt`
- Add: `fastapi`, `uvicorn[standard]`, `httpx` (for tests), `pywebview`.

### Acceptance Criteria
- [ ] All REST endpoints return correct data from existing `src/` functions.
- [ ] Path traversal attacks on `course_id` return 403.
- [ ] CORS only allows localhost origins.
- [ ] All existing 73 backend tests still pass.
- [ ] New `test_server.py` tests pass.

### Agent Prompts

**Code Writer**: Implement Stage 1 from the implementation plan. Create `server.py` with all REST endpoints listed. Create `tests/test_server.py`. Update `requirements.txt`. Read `rules.md` for standards. Run `py_compile`, `pytest tests/`, then commit and push.

**Code Reviewer**: Review `server.py` and `tests/test_server.py`. Check: CORS locked to localhost only, path traversal prevention on course_id, API keys never sent to frontend (only masked), Pydantic models used, proper HTTP status codes, type hints, docstrings, line length <= 100.

**Project Manager**: Validate Stage 1 delivery against the plan. Verify all REST endpoints exist and return correct shapes. Verify path traversal test exists. Verify CORS config. Verify no regressions in existing tests. Quote evidence from code.

---

## Stage 2: FastAPI Server — WebSocket Endpoints

### Deliverables

#### [MODIFY] `server.py`
Add WebSocket endpoints:

| Endpoint | Purpose | Message Format |
|----------|---------|---------------|
| `ws://localhost:8000/ws/pipeline` | Real-time pipeline logs + progress | `{type: "log", msg: "..."}` or `{type: "progress", current: 3, total: 5, step: "Extracting..."}` or `{type: "complete", success: true, course_path: "..."}` |

Add pipeline start endpoint:
| Method | Endpoint | Purpose |
|--------|----------|---------|
| `POST` | `/api/pipeline/start` | Starts pipeline in background thread, streams to WebSocket |

- The pipeline's `on_log` callback sends messages to the WebSocket.
- The pipeline's `on_progress` callback sends progress updates.
- On completion, send `{type: "complete", ...}` with the course directory path.

#### [UPDATE] `tests/test_server.py`
- Add WebSocket connection tests.
- Test pipeline start/cancel flow.

### Acceptance Criteria
- [ ] WebSocket connects and receives real-time log messages.
- [ ] Progress updates include current step number, total, and description.
- [ ] Pipeline completion message includes the output directory path.
- [ ] Cancel endpoint stops a running pipeline.
- [ ] WebSocket handles client disconnect gracefully (no server crash).

### Agent Prompts

**Code Writer**: Implement Stage 2 from the implementation plan. Add WebSocket endpoint `/ws/pipeline` and POST `/api/pipeline/start` to `server.py`. The pipeline's `on_log` and `on_progress` callbacks must forward messages via WebSocket. Update `tests/test_server.py`. Run tests, commit and push.

**Code Reviewer**: Review the WebSocket implementation. Check: WebSocket error handling (client disconnect), thread safety of WebSocket sends from pipeline background thread, cancel event properly set, no API keys in WebSocket messages, proper async/threading patterns.

**Project Manager**: Validate Stage 2. Verify WebSocket message format matches spec. Verify pipeline start/cancel/complete flow. Verify no regressions.

---

## Stage 3: React App Shell — Sidebar, Footer, Routing, Design System

### Deliverables

#### [NEW] `frontend/` (React Vite app)
Initialize with `npx -y create-vite@latest ./ --template react` inside `frontend/`.

#### [NEW] `frontend/src/index.css`
Design system with all CSS custom properties from `rules.md` Section 7.

#### [NEW] `frontend/src/utils/api.js`
Centralized API utility module:
- `fetchLibrary()`, `fetchCourse(id)`, `fetchNotes(id, file)`, etc.
- `connectPipelineWebSocket(onMessage)` — WebSocket connection with auto-reconnect.
- Base URL: `http://localhost:8000`.

#### [NEW] `frontend/src/context/AppContext.jsx`
React Context providing:
- `currentScreen` (library / new_pipeline / course / settings / utilities)
- `activeCourseDir`
- `pipelineStatus` (idle / running / complete / error)
- `pipelineLogs` array
- `pipelineProgress` object

#### [NEW] `frontend/src/components/Sidebar.jsx`
- 4 nav items: 📚 Library, 🚀 New Pipeline, ⚙️ Settings, 🔧 Utilities
- Active state with accent left border bar
- Bottom: Ollama status pill (fetches `/api/settings/health` on mount)

#### [NEW] `frontend/src/components/FooterDock.jsx`
- Progress bar (width driven by pipeline progress)
- Step label text
- Collapsible console log drawer (scrollable, monospace, auto-scroll)
- Only visible when pipeline is running or has recent output

#### [NEW] `frontend/src/App.jsx`
- Wraps everything in `AppProvider`
- Left sidebar + main content area + footer dock
- Routes to correct page based on `currentScreen`

### Acceptance Criteria
- [ ] `npm run dev` starts with zero errors.
- [ ] `npm run build` completes with zero errors.
- [ ] Sidebar renders 4 nav items with correct active states.
- [ ] Clicking nav items switches the main content area.
- [ ] Footer dock renders progress bar and collapsible log drawer.
- [ ] Design tokens applied consistently (no hardcoded colors).
- [ ] Ollama status pill reflects actual backend health.

### Agent Prompts

**Code Writer**: Implement Stage 3 from the implementation plan. Initialize the Vite React app in `frontend/`. Create the design system in `index.css`, the API utility in `api.js`, the AppContext, Sidebar, FooterDock, and App shell. Verify with `npm run build`. Commit and push.

**Code Reviewer**: Review all frontend files. Check: CSS uses only custom properties (no hardcoded colors), api.js centralizes all fetch calls, no inline styles, functional components only, proper error handling in api.js, no secrets in frontend code.

**Project Manager**: Validate Stage 3. Verify sidebar has exactly 4 items (Library, New Pipeline, Settings, Utilities). Verify footer dock has progress bar and collapsible console. Verify design tokens match rules.md. Verify `npm run build` succeeds.

---

## Stage 4: React Pages — Library + New Pipeline

### Deliverables

#### [NEW] `frontend/src/pages/Library.jsx`
- Fetches course list from `/api/library`.
- Renders grid of `CourseCard` components.
- Each card shows: title, date, directory, feature badges (📸 Vision, 🕸️ KAG, 📄 PDF).
- Click card → sets `activeCourseDir` and switches to Course Workspace.
- Empty state: "Start your first course" CTA button → navigates to New Pipeline.

#### [NEW] `frontend/src/components/CourseCard.jsx`
- Dark card with 12px radius, 1px border.
- Title, subtitle (directory path), date, and badge pills.
- Hover effect (subtle border glow).

#### [NEW] `frontend/src/pages/NewPipeline.jsx`
- Segmented input selector: YouTube URL / Local Files.
- 3 `PowerUpCard` toggle components with time-cost hints:
  - 📸 Vision Engine (+ ~35s)
  - 🕸️ Knowledge Graph (+ ~15s)
  - 📄 Auto PDF Export (+ ~5s)
- Topic/Title input field.
- Output directory text input (with note: "Enter full path").
- "🚀 Start Pipeline Processing" button.
- On click: POST to `/api/pipeline/start`, connect WebSocket, show progress in FooterDock.
- On pipeline complete: Auto-navigate to Course Workspace.

#### [NEW] `frontend/src/components/PowerUpCard.jsx`
- Toggle card with icon, title, description, time hint.
- Active state: accent border glow + filled background.
- Click to toggle on/off.

### Acceptance Criteria
- [ ] Library page fetches and displays course cards.
- [ ] Empty state renders when no courses exist.
- [ ] Clicking a course card opens its workspace.
- [ ] New Pipeline page has input selector, 3 power-up cards, and start button.
- [ ] Start button triggers pipeline via API and shows real-time progress.
- [ ] On completion, auto-navigates to the new course workspace.

### Agent Prompts

**Code Writer**: Implement Stage 4. Create Library.jsx, NewPipeline.jsx, CourseCard.jsx, PowerUpCard.jsx. Wire up API calls to backend endpoints. Test WebSocket integration with FooterDock. Verify `npm run build`. Commit and push.

**Code Reviewer**: Review Library and NewPipeline pages. Check: API calls go through api.js, no hardcoded URLs, proper loading/error states, power-up cards use CSS classes not inline styles, WebSocket auto-reconnect on disconnect, no secrets exposed.

**Project Manager**: Validate Stage 4. Verify Library renders course cards with badges. Verify empty state exists. Verify New Pipeline has exactly 3 power-up cards with time hints. Verify pipeline start triggers WebSocket and auto-navigates on completion.

---

## Stage 5: React Pages — Course Workspace (5 Tabs)

### Deliverables

#### [NEW] `frontend/src/pages/CourseWorkspace.jsx`
Header: Course title + "📂 Open Output Folder" button + "← Back to Library".
5 tab navigation:

**Tab 1: 📝 Notes**
- Fetches markdown from `/api/course/{id}/notes/{file}`.
- Renders via `react-markdown` + `remark-gfm` + `rehype-highlight`.
- Dropdown to switch between `_Detailed_Notes.md` and `_Practical_Notes.md`.

**Tab 2: 💬 Chat**
- ChatGPT-style interface with `ChatBubble` components.
- Model selector dropdown (llama3, phi3, qwen2.5:3b, etc.).
- Sends messages via POST `/api/chat/send`.
- "Clear Chat" button via POST `/api/chat/clear`.
- Chat history preserved in React state across tab switches.

**Tab 3: 🕸️ Graph**
- Fetches graph HTML from `/api/course/{id}/graph`.
- Renders Mermaid diagrams inline using the `mermaid` JS library.
- Fallback: "No Knowledge Graph generated" message.

**Tab 4: 📄 PDF**
- Theme selector: 3 `ThemeCard` components (Textbook, ChatGPT Dark, Minimal Mono).
- "👁️ Preview PDF" and "📥 Export PDF" buttons.
- Calls POST `/api/pdf/export` with theme selection.

**Tab 5: 🖼️ Keyframes**
- Fetches keyframe list from `/api/course/{id}/keyframes`.
- CSS Grid gallery of actual `<img>` thumbnails.
- Fallback: "No keyframes extracted" message.

#### [NEW] `frontend/src/components/ChatBubble.jsx`
- Styled message bubble (user = right-aligned, AI = left-aligned).
- Renders markdown inside messages via `react-markdown`.

#### [NEW] `frontend/src/components/ThemeCard.jsx`
- Visual swatch card showing theme preview colors.
- Click to select, active state with accent border.

### Acceptance Criteria
- [ ] All 5 tabs render correctly with real data from backend.
- [ ] Notes tab renders rich Markdown (headers, code blocks, tables, lists).
- [ ] Chat tab sends/receives messages, preserves history across tab switches.
- [ ] Graph tab renders Mermaid diagrams inline (not external browser).
- [ ] PDF tab exports PDFs with correct theme applied.
- [ ] Keyframes tab shows actual image thumbnails in a grid.
- [ ] "Back to Library" button works correctly.

### Agent Prompts

**Code Writer**: Implement Stage 5. Create CourseWorkspace.jsx with 5 tabs, ChatBubble.jsx, ThemeCard.jsx. Install `react-markdown`, `remark-gfm`, `rehype-highlight`, `mermaid`. Wire all API calls. Verify `npm run build`. Commit and push.

**Code Reviewer**: Review CourseWorkspace and all sub-components. Check: Markdown rendering uses react-markdown (no dangerouslySetInnerHTML), chat messages sanitized, Mermaid rendered client-side only, keyframe images loaded from backend /static/ endpoint, no API keys in frontend, all images have alt text.

**Project Manager**: Validate Stage 5. Verify all 5 tabs exist and function. Verify Markdown renders rich formatting. Verify chat preserves history. Verify Mermaid renders inline. Verify keyframes show actual images. Verify PDF export works with all 3 themes.

---

## Stage 6: Settings, Utilities, Launcher & Build

### Deliverables

#### [NEW] `frontend/src/pages/Settings.jsx`
- Tab 1: Text Models pool (add/remove API keys with masked display).
- Tab 2: Vision Models pool (add/remove API keys).
- System Health cards: Keyring, Playwright, Ollama status.

#### [NEW] `frontend/src/pages/Utilities.jsx`
- "Convert External .md to PDF" tool.
- File path input + theme selector + Preview/Export buttons.
- Playwright auto-installer button with status indicator.

#### [NEW] `launcher.py`
- Starts FastAPI server via `uvicorn` in a background thread.
- Opens `pywebview` native window pointing to `http://127.0.0.1:8000`.
- Graceful shutdown on window close.

#### [RENAME] `app.py` → `app_legacy.py`

#### [UPDATE] `server.py`
- In production mode, serve React build from `frontend/dist/` as static files.
- Fallback route: serve `index.html` for client-side routing.

#### [NEW] `build_exe.py` (optional, for future)
- Script using PyInstaller to bundle into single `.exe`.
- Includes: Python runtime, FastAPI, `frontend/dist/`, all `src/` modules.

### Acceptance Criteria
- [ ] Settings page manages API keys with masked display.
- [ ] System Health cards show live status.
- [ ] Utilities page provides standalone MD-to-PDF conversion.
- [ ] `python launcher.py` opens a native window with the full React UI.
- [ ] `python server.py` serves the built React app at `localhost:8000`.
- [ ] Legacy `app_legacy.py` still launches the old UI if needed.
- [ ] All tests pass. Frontend builds. Zero regressions.

### Agent Prompts

**Code Writer**: Implement Stage 6. Create Settings.jsx, Utilities.jsx, launcher.py. Rename app.py to app_legacy.py. Update server.py to serve frontend/dist/ in production. Verify everything works end-to-end. Run all tests. Commit and push.

**Code Reviewer**: Review Settings, Utilities, launcher.py, and server.py production mode. Check: API keys never sent unmasked to frontend, pywebview binds to localhost only, static file serving doesn't expose files outside frontend/dist/, launcher graceful shutdown, no security regressions.

**Project Manager**: Validate Stage 6. Verify Settings manages keys. Verify Utilities has MD-to-PDF tool. Verify launcher.py opens native window. Verify server.py serves React build. Verify app_legacy.py still works. Verify zero regressions across all 73+ tests. This is the FINAL stage — be extra harsh.
