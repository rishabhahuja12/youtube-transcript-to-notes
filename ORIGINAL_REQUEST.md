# Original User Request

## Initial Request — 2026-07-27T14:09:37+05:30

Complete A-to-Z audit, verification, and code quality refinement of the StudySuite AI (yt_transcriptor) desktop web application, covering all API endpoints, frontend UI buttons, provider pool rate-limits, and automated hook/plugin integrations.

Working directory: E:\rishabh\experimentation\yt_transcriptor
Integrity mode: development

## Requirements

### R1. Comprehensive Backend & API Endpoint Audit
Verify all 5 gateway services on local ports (gateway 8000, pipeline 8001, chat 8002, content/settings 8003, PO Token server 4416). Confirm security invariants: zero cookie usage, OAuth scope youtube.readonly, exact pinned dependencies (yt-dlp==2026.06.09, bgutil-ytdlp-pot-provider==1.3.1), masked API key responses, and robust rate-limit rotation.

### R2. Frontend UI, Button & State Verification
Audit all React frontend pages (NewPipeline.jsx, Settings.jsx, Library.jsx, CourseWorkspace.jsx, Utilities.jsx). Ensure all interactive elements (submit buttons, provider addition forms, inline rate-limit edit inputs, course search/sort filters, tab switching, and job cancellation triggers) operate smoothly without runtime errors.

### R3. Code Cleanliness, Hooks & Plugin Alignment
Ensure clean modular code structure across src/, gateway/, and frontend/. Verify adherence to design tokens (--ink, --panel, --hairline, --highlighter), zero inline style slop, strict docstrings/typehints, active hook execution (hooks.json), and integration with the fastapi-react-ai-pipeline plugin.

## Acceptance Criteria

### Automated Verification
- [ ] Pytest suite executes with 100% pass rate (pytest -q, 122+ tests passed).
- [ ] Frontend compiles cleanly with zero build errors (cd frontend && npm run build).
- [ ] Python syntax and static analysis compile cleanly (python -m compileall -q launcher.py runtime.py src gateway).

### API & Network Reliability
- [ ] All API endpoints (/api/content/library, /api/settings/pool, /api/settings/health, /api/pipeline/start, /api/chat/send) respond correctly via 127.0.0.1:8000.
- [ ] PO Token server ping on 127.0.0.1:4416/ping returns HTTP 200 and version 1.3.1.
- [ ] Frontend API utility (api.js) uses dynamic window.location.origin for zero CORS or 404 port mismatches.

### UI & UX Polish
- [ ] Settings page renders provider state, inline rate-limit editing, and system health checks without freezing.
- [ ] New Pipeline form processes YouTube URLs and local file pickers cleanly with preflight capability validation.
- [ ] Library page features functional title searching, date/status sorting, and status badges.
- [ ] Course Workspace dynamically gates Graph and Keyframes tabs based on detected output badges.

### Repository Hygiene
- [ ] All local scratch files, temp plans, and runtime build artifacts remain excluded via .git/info/exclude.
