import asyncio
import httpx
import logging
import os
from fastapi import FastAPI, Request, Response, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask
import websockets
from websockets.exceptions import ConnectionClosed

app = FastAPI(
    title="API Gateway", 
    description="Reverse Proxy for yt_transcriptor services", 
    version="1.0.0"
)

# Crucial CORS setup
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173", 
        "http://localhost:8000",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:8000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

client = httpx.AsyncClient()

@app.on_event("shutdown")
async def shutdown_event() -> None:
    """Close the httpx AsyncClient on shutdown."""
    await client.aclose()

async def proxy_request(request: Request, target_url: str) -> Response:
    """Forward an HTTP request to the designated target microservice URL."""
    url = httpx.URL(target_url, query=request.url.query.encode("utf-8"))
    
    # Read the request body
    body = await request.body()
    
    # Forward the request using httpx
    req = client.build_request(
        method=request.method,
        url=url,
        headers=request.headers.raw,
        content=body,
    )
    
    try:
        response = await client.send(req, stream=True)
        return Response(
            content=await response.aread(),
            status_code=response.status_code,
            headers={k: v for k, v in response.headers.items() if k.lower() != 'content-encoding'}
        )
    except httpx.RequestError as e:
        return Response(status_code=502, content=f"Gateway Error: {str(e)}")


@app.api_route("/api/content/{path:path}", methods=["GET", "POST", "PUT", "DELETE"])
async def route_content(request: Request, path: str) -> Response:
    return await proxy_request(request, f"http://localhost:8003/content/{path}")

@app.api_route("/api/settings/{path:path}", methods=["GET", "POST", "PUT", "DELETE"])
async def route_settings(request: Request, path: str) -> Response:
    return await proxy_request(request, f"http://localhost:8003/settings/{path}")
    
@app.api_route("/api/pdf/{path:path}", methods=["GET", "POST", "PUT", "DELETE"])
async def route_pdf(request: Request, path: str) -> Response:
    return await proxy_request(request, f"http://localhost:8003/pdf/{path}")

@app.api_route("/api/chat/{path:path}", methods=["GET", "POST", "PUT", "DELETE"])
async def route_chat(request: Request, path: str) -> Response:
    return await proxy_request(request, f"http://localhost:8002/chat/{path}")

@app.api_route("/api/pipeline/{path:path}", methods=["GET", "POST", "PUT", "DELETE"])
async def route_pipeline(request: Request, path: str) -> Response:
    return await proxy_request(request, f"http://localhost:8001/pipeline/{path}")

@app.api_route("/static/{path:path}", methods=["GET", "POST", "PUT", "DELETE"])
async def route_static(request: Request, path: str) -> Response:
    return await proxy_request(request, f"http://localhost:8003/static/{path}")

@app.websocket("/ws/pipeline")
async def websocket_pipeline(websocket: WebSocket) -> None:
    await websocket.accept()
    try:
        async with websockets.connect("ws://localhost:8001/pipeline/stream") as target_ws:
            async def forward_to_client():
                try:
                    while True:
                        msg = await target_ws.recv()
                        await websocket.send_text(msg)
                except ConnectionClosed:
                    pass
                except WebSocketDisconnect:
                    pass
                except Exception as e:
                    logging.error(f"Error in websocket forwarding to client: {e}")
                    pass

            task = asyncio.create_task(forward_to_client())

            try:
                while True:
                    data = await websocket.receive_text()
                    await target_ws.send(data)
            except WebSocketDisconnect:
                task.cancel()
            except ConnectionClosed:
                task.cancel()
            except Exception as e:
                logging.error(f"Error in websocket forwarding to target: {e}")
                task.cancel()
    except Exception as e:
        logging.error(f"WebSocket connection failed: {e}")
        await websocket.close(code=1011, reason=str(e))

# Mount React static files in production
_BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FRONTEND_DIST = os.path.join(_BASE, "frontend", "dist")

if os.path.isdir(FRONTEND_DIST):
    app.mount("/assets", StaticFiles(directory=os.path.join(FRONTEND_DIST, "assets")), name="assets")

    @app.get("/{full_path:path}")
    async def serve_react_app(full_path: str) -> FileResponse:
        """Serve the React app or index.html for client-side routing.
        
        Args:
            full_path: The requested path.
            
        Returns:
            FileResponse: The requested static file or index.html.
        """
        index_file = os.path.join(FRONTEND_DIST, "index.html")
        file_path = os.path.abspath(os.path.join(FRONTEND_DIST, full_path))
        
        # Path Traversal protection
        if not file_path.startswith(os.path.abspath(FRONTEND_DIST)):
            return FileResponse(index_file)
            
        if os.path.isfile(file_path):
            return FileResponse(file_path)
        return FileResponse(index_file)
