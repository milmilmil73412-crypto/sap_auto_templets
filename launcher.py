import sys
import os
import threading
import webbrowser
import time


def _open_browser():
    time.sleep(5)
    webbrowser.open("http://localhost:8501")


def main():
    if getattr(sys, "frozen", False):
        # PyInstaller onedir: exe is at dist/App/App.exe
        # _MEIPASS is dist/App/_internal/ (all collected files)
        meipass = sys._MEIPASS
        app_path = os.path.join(meipass, "app.py")
        os.chdir(os.path.dirname(sys.executable))
    else:
        base_dir = os.path.dirname(os.path.abspath(__file__))
        app_path = os.path.join(base_dir, "app.py")
        os.chdir(base_dir)

    threading.Thread(target=_open_browser, daemon=True).start()

    sys.argv = [
        "streamlit",
        "run",
        app_path,
        "--server.port=8501",
        "--server.headless=true",
        "--browser.gatherUsageStats=false",
    ]

    from streamlit.web import cli as stcli
    stcli.main()


if __name__ == "__main__":
    main()
