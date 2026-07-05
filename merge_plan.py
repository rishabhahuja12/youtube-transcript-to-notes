with open('temp_plan.md', 'r', encoding='utf-8') as f:
    plan = f.read()

arch_start = plan.find('## Architecture')
stage12_start = plan.find('## Stage 1:')
stage3_start = plan.find('## Stage 3:')

microservices_arch = """## Architecture

```
yt_transcriptor/
├── src/                    # ← UNTOUCHED backend package
├── gateway/                # ← NEW: Microservices layer
│   ├── gateway.py          # API Gateway (Port 8000)
│   ├── pipeline_service.py # Port 8001
│   ├── chat_service.py     # Port 8002
│   └── content_service.py  # Port 8003
├── launcher.py             # ← NEW: Starts all 4 services + pywebview
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
│   ├── test_gateway.py     # ← NEW: Microservice tests
│   └── (existing tests)
├── rules.md                # ← UPDATED for new stack
├── AGENTS.md               # ← UPDATED for new stack
└── requirements.txt        # ← UPDATED with fastapi, uvicorn, pywebview, httpx
```

### Distribution Modes

| Mode | Command | What happens |
|------|---------|-------------|
| **Dev** | `python launcher.py --dev` + `npm run dev` | Gateway on :8000, Vite on :5173 |
| **Desktop .exe** | `python launcher.py` | Starts all 4 microservices + opens pywebview window |

---

"""

microservices_stages12 = """## Stage 1: Content Service (Port 8003) & Chat Service (Port 8002)

### Deliverables

#### [NEW] `gateway/content_service.py`
FastAPI application (Port 8003) with these endpoints:
| Method | Endpoint | Backend Function | Response |
|--------|----------|-----------------|----------|
| `GET` | `/content/library` | `load_recent_outputs()` | `[{title, path, date, badges}]` |
| `POST` | `/content/library/add` | `add_recent_output(path)` | `{success: true}` |
| `GET` | `/content/course/{id}/files` | `os.listdir()` | `[{name, type, size}]` |
| `GET` | `/content/course/{id}/notes/{file}` | Read `.md` file | `{content: "markdown..."}` |
| `GET` | `/content/course/{id}/graph` | Read `_knowledge_graph.html` | `{html: "..."}` |
| `GET` | `/content/course/{id}/keyframes` | List `.jpg/.png` files | `[{name, url}]` |
| `GET` | `/settings/pool` | `get_provider_pool_or_legacy()` | `[{provider, model, masked_key}]` |
| `POST` | `/settings/pool` | `store_provider_pool()` | `{success: true}` |
| `GET` | `/settings/health` | Check Ollama/Playwright | `{ollama, playwright}` |
| `POST` | `/pdf/export` | Playwright PDF conversion | `{path: "output.pdf"}` |

- Static file serving: `/static/{id}/{filename}` for keyframe images.
- CORS: Allow `localhost:8000` (Gateway).

#### [NEW] `gateway/chat_service.py`
FastAPI application (Port 8002) with these endpoints:
| Method | Endpoint | Backend Function | Response |
|--------|----------|-----------------|----------|
| `POST` | `/chat/send` | `ChatSession.send()` | `{response: "..."}` |
| `POST` | `/chat/clear` | Reset session | `{success: true}` |

### Acceptance Criteria
- [ ] API keys never sent unmasked.
- [ ] Chat history preserved correctly in local state.

### Agent Prompts
**Code Writer**: Implement Stage 1 from the plan. Create `gateway/content_service.py` and `gateway/chat_service.py`. Write tests.
**Code Reviewer**: Review the two microservices.
**Project Manager**: Validate against the plan.

---

## Stage 2: Pipeline Service (8001) & API Gateway (8000)

### Deliverables

#### [NEW] `gateway/pipeline_service.py`
FastAPI application (Port 8001):
| Method | Endpoint | Purpose |
|--------|----------|---------|
| `POST` | `/pipeline/start` | Starts pipeline in background thread |
| `POST` | `/pipeline/cancel` | Sets `cancel_event` |
| `WS` | `/pipeline/stream` | Streams `on_log` and `on_progress` |

#### [NEW] `gateway/gateway.py`
FastAPI application (Port 8000):
- **Reverse Proxy**: Uses `httpx.AsyncClient` to route:
  - `/api/content/*` → `localhost:8003`
  - `/api/settings/*` → `localhost:8003`
  - `/api/chat/*` → `localhost:8002`
  - `/api/pipeline/*` → `localhost:8001`
- **WebSocket Proxy**: Proxies WS connections to `localhost:8001`.
- **CORS**: Locks origins to `localhost:5173` and `localhost:8000`.

### Acceptance Criteria
- [ ] Gateway correctly routes HTTP and WS traffic.
- [ ] Pipeline logs stream in real-time.

### Agent Prompts
**Code Writer**: Implement Stage 2. Create `gateway.py` and `pipeline_service.py`.
**Code Reviewer**: Review reverse proxy logic.
**Project Manager**: Validate against the plan.

---

"""

final_plan = plan[:arch_start] + microservices_arch + microservices_stages12 + plan[stage3_start:]

with open(r'C:\Users\asus\.gemini\antigravity-cli\brain\7b8f0200-690a-4db9-9472-3f018df83bed\implementation_plan.md', 'w', encoding='utf-8') as f:
    f.write(final_plan)

print('Success')
