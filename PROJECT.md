# Project: StudySuite AI (yt_transcriptor) Audit & Quality Refinement

## Architecture
StudySuite AI is a desktop web application for transcribing YouTube videos, generating AI course notes, knowledge graphs (KAG), keyframes, and running local/cloud AI pipelines.

### Gateway & Service Port Topology:
- Gateway Router: Port 8000 (`gateway.gateway:app`) - Reverse proxy to all sub-services & static frontend host (`frontend/dist`).
- Pipeline Service: Port 8001 (`gateway.pipeline_service:app`) - Manages execution jobs, Whisper transcription, KAG graph generation, keyframe extraction.
- Chat Service: Port 8002 (`gateway.chat_service:app`) - Multi-turn conversational interface over course materials & notes.
- Content & Settings Service: Port 8003 (`gateway.content_service:app`) - Library management, provider pool rate-limiting settings, system health checks.
- PO Token Server: Port 4416 (`bgutil-ytdlp-pot-provider`) - Bundled Node.js PO Token generator for `yt-dlp` YouTube extraction.

## Feature Inventory
| # | Feature | Description | Milestone | Source |
|---|---------|-------------|-----------|--------|
| 1 | Service Port Binding & Routing | Verify 5 ports (8000, 8001, 8002, 8003, 4416) & reverse proxy routing | M1 | R1 |
| 2 | Security Invariants | Zero cookie usage, OAuth `youtube.readonly`, pinned dependencies (`yt-dlp==2026.06.09`, `bgutil-ytdlp-pot-provider==1.3.1`) | M1 | R1 |
| 3 | API Data Privacy & Rate Limits | Masked API key responses in settings API, provider pool failover & rate limit rotation | M1 | R1 |
| 4 | React Frontend Pages & Components | Verify pages (`NewPipeline.jsx`, `Settings.jsx`, `Library.jsx`, `CourseWorkspace.jsx`, `Utilities.jsx`) without freezing | M2 | R2 |
| 5 | Interactive Controls & Dynamic State | Submit buttons, provider forms, inline rate-limit edit inputs, search/sort filters, job cancellation | M2 | R2 |
| 6 | Preflight Validation & Dynamic Tab Gating | Capability preflight checks in NewPipeline, Graph & Keyframes tab gating in CourseWorkspace based on output badges | M2 | R2 |
| 7 | Frontend API Origin | `api.js` dynamic `window.location.origin` resolution for zero CORS/404 port mismatches | M2 | R2 |
| 8 | UI Design Tokens & Styling | CSS design tokens (`--ink`, `--panel`, `--hairline`, `--highlighter`, `--error`), zero inline style slop | M3 | R3 |
| 9 | Code Cleanliness & Modular Structure | Modular layout across `src/`, `gateway/`, `frontend/`, strict docstrings & type hints | M3 | R3 |
| 10 | Hooks & Plugin Alignment | Active hook execution (`hooks.json`) and integration with `fastapi-react-ai-pipeline` plugin | M3 | R3 |
| 11 | Pytest Verification | 100% pass rate across 122+ tests (`pytest -q`) | M4 | Acceptance Criteria |
| 12 | Frontend Compilation | Zero build errors (`cd frontend && npm run build`) | M4 | Acceptance Criteria |
| 13 | Python Static Analysis | Clean compilation across `launcher.py`, `runtime.py`, `src`, `gateway` (`python -m compileall -q`) | M4 | Acceptance Criteria |
| 14 | API & PO Token Server Reliability | Live endpoint verification (`/api/content/library`, `/api/settings/pool`, `/api/settings/health`, `/api/pipeline/start`, `/api/chat/send`, `/ping`) | M4 | Acceptance Criteria |
| 15 | Repository Hygiene | Git excludes in `.git/info/exclude` | M4 | Acceptance Criteria |

## Milestones
| # | Name | Scope | Dependencies | Status |
|---|------|-------|-------------|--------|
| 1 | Comprehensive Backend & API Endpoint Audit (R1) | 5 gateway service ports, security invariants, zero cookies, OAuth scope, pinned deps, API key masking, provider pool rate limiting | none | IN_PROGRESS |
| 2 | Frontend UI, Button & State Verification (R2) | Audit 5 React pages, fix inline styles/hardcoded colors, static import fix in NewPipeline, dynamic origin in api.js, dead code cleanup, tab gating | M1 | PLANNED |
| 3 | Code Cleanliness, Hooks & Plugin Alignment (R3) | CSS design token compliance (--ink, --panel, --hairline, --highlighter, --error), typehints/docstrings, hooks.json, fastapi-react-ai-pipeline | M2 | PLANNED |
| 4 | E2E Testing, Static Analysis & Git Hygiene Pass (Acceptance Criteria) | 122+ pytest suite, npm run build, compileall, endpoint pings, .git/info/exclude hygiene, Victory Audit | M3 | PLANNED |

## Interface Contracts
### Frontend ↔ Gateway (Port 8000)
- GET `/api/content/library` -> List of library courses and metadata
- GET `/api/settings/pool` -> List of AI providers with masked API keys (`key[:8] + "..."`)
- PATCH `/api/settings/pool/{index}/limits` -> Update provider RPM/TPM limits
- GET `/api/settings/health` -> System health status across services & PO token provider
- POST `/api/pipeline/start` -> Start pipeline job with YouTube URL or file path
- POST `/api/chat/send` -> Send message to course workspace chat
- GET `http://127.0.0.1:4416/ping` -> PO Token server status HTTP 200, version `1.3.1`

## Code Layout
- `launcher.py` - Application launcher orchestrating 5 local microservices
- `runtime.py` - Node.js process manager for PO Token server on port 4416
- `gateway/` - FastAPI microservices: `gateway.py` (8000), `pipeline_service.py` (8001), `chat_service.py` (8002), `content_service.py` (8003)
- `src/` - Core business logic: `provider_pool.py`, `llm_client.py`, `youtube.py`, `auth.py`, `pipeline.py`, `database.py`
- `frontend/` - React frontend application with pages `NewPipeline.jsx`, `Settings.jsx`, `Library.jsx`, `CourseWorkspace.jsx`, `Utilities.jsx` and utility `src/utils/api.js`
- `tests/` - Pytest unit and integration test suite (122+ tests)
