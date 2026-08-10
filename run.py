"""Start the TicketDesk backend and frontend together and open the app in a browser.

Usage:
    python run.py
"""

import os
import subprocess
import sys
import time
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
FRONTEND_DIR = ROOT / "frontend"
BACKEND_PORT = 8000
FRONTEND_PORT = 5500


def main():
    env = os.environ.copy()
    env.setdefault("DATABASE_URL", "sqlite:///./ticketdesk.db")

    backend = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "src.main:app",
            "--port",
            str(BACKEND_PORT),
        ],
        cwd=ROOT,
        env=env,
    )

    frontend = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "http.server",
            str(FRONTEND_PORT),
        ],
        cwd=FRONTEND_DIR,
    )

    print(f"Backend:  http://localhost:{BACKEND_PORT}")
    print(f"Frontend: http://localhost:{FRONTEND_PORT}")
    print("Press Ctrl+C to stop both servers.")

    time.sleep(2)
    webbrowser.open(f"http://localhost:{FRONTEND_PORT}")

    try:
        backend.wait()
    except KeyboardInterrupt:
        pass
    finally:
        for proc in (backend, frontend):
            if proc.poll() is None:
                proc.terminate()

        for proc in (backend, frontend):
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()


if __name__ == "__main__":
    main()
