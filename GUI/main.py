"""
Pose2Sim GUI - Web-based Launcher
Uses Flask as backend and pywebview for native desktop window.
Falls back to opening in browser if pywebview is not available.
"""
import sys
import os
import threading
import webbrowser
from pathlib import Path

# Support PyInstaller bundled paths
if getattr(sys, 'frozen', False):
    # Running as compiled exe
    BASE_DIR = Path(sys._MEIPASS)
    os.chdir(os.path.dirname(sys.executable))
else:
    BASE_DIR = Path(__file__).parent.parent

# Add project root to path
sys.path.insert(0, str(BASE_DIR))

PORT = 5789

def main():
    from GUI.web_app import run_server
    
    # Start Flask in a background thread
    server_thread = threading.Thread(target=run_server, args=(PORT,), daemon=True)
    server_thread.start()
    
    url = f'http://127.0.0.1:{PORT}'
    
    # Try to use pywebview for native window
    try:
        import webview
        print(f"[Pose2Sim] Launching native window...")
        webview.create_window(
            'Pose2Sim',
            url,
            width=1400,
            height=900,
            min_size=(1000, 600),
            resizable=True,
        )
        webview.start()
    except ImportError:
        print(f"[Pose2Sim] pywebview not found. Opening in browser...")
        print(f"[Pose2Sim] If you want a native window, install: pip install pywebview")
        print(f"[Pose2Sim] App running at: {url}")
        webbrowser.open(url)
        
        # Keep main thread alive
        try:
            server_thread.join()
        except KeyboardInterrupt:
            print("\n[Pose2Sim] Shutting down...")


if __name__ == "__main__":
    main()
