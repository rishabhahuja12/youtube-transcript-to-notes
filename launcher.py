import os
import sys
import threading
import uvicorn
import webview
import time
import argparse

# Path resolution
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.append(SCRIPT_DIR)

def start_backend() -> None:
    """Start the FastAPI gateway on port 8000.
    
    This function configures and runs the Uvicorn server for the main API gateway.
    """
    # Note: Uvicorn doesn't play well when run programmatically without import strings 
    # if there are multiple workers, but for a simple desktop app, it's fine.
    config = uvicorn.Config(
        "gateway.gateway:app", 
        host="127.0.0.1", 
        port=8000, 
        log_level="info",
        reload=False
    )
    server = uvicorn.Server(config)
    server.run()

def start_services() -> list:
    """Start all backend services.
    
    This function spawns the microservices using subprocess.Popen.
    
    Returns:
        list: A list of Popen subprocess objects.
    """
    # Since the gateway routes to 8001, 8002, 8003, we should ideally start them too.
    # The prompt says: "Starts all 4 microservices + opens pywebview window"
    # But usually `launcher.py` might use subprocesses for the other microservices.
    import subprocess
    
    services = [
        {"port": 8001, "module": "gateway.pipeline_service:app"},
        {"port": 8002, "module": "gateway.chat_service:app"},
        {"port": 8003, "module": "gateway.content_service:app"},
    ]
    
    processes = []
    
    for svc in services:
        p = subprocess.Popen(
            [
                sys.executable, "-m", "uvicorn", svc["module"], 
                "--host", "127.0.0.1", "--port", str(svc["port"])
            ],
            cwd=SCRIPT_DIR,
            stdout=sys.stdout,
            stderr=sys.stderr,
            encoding="utf-8",
            errors="replace"
        )
        processes.append(p)
        
    # Start the gateway in a thread so pywebview can run in the main thread
    gateway_thread = threading.Thread(target=start_backend, daemon=True)
    gateway_thread.start()
    
    return processes

def main() -> None:
    """Launch the yt_transcriptor application.
    
    Parses arguments, starts backend services, and opens the pywebview window.
    """
    parser = argparse.ArgumentParser(description="Launch yt_transcriptor")
    parser.add_argument("--dev", action="store_true", help="Run in dev mode (no pywebview)")
    args = parser.parse_args()

    # Start backend services
    processes = start_services()
    
    if args.dev:
        print("Running in dev mode. Backend started on port 8000.")
        print("Run `npm run dev` in the frontend/ folder to start the Vite server.")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            pass
    else:
        # Give services a moment to start
        time.sleep(2)
        
        # Open pywebview
        window = webview.create_window(
            "YT Transcriptor - AI Study Suite",
            "http://localhost:8000",
            width=1200,
            height=800,
            min_size=(800, 600)
        )
        
        webview.start(private_mode=True)

    # Cleanup subprocesses
    for p in processes:
        p.terminate()

if __name__ == "__main__":
    main()
