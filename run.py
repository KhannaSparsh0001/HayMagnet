import subprocess
import sys
import os

def main():
    print("🚀 Launching HayMagnet Servers in new tabs...")
    
    # Get the absolute path to the directory containing this script
    base_dir = os.path.dirname(os.path.abspath(__file__))
    app_path = os.path.join(base_dir, "app.py")
    
    # Windows Terminal command to open tabs in the current window (-w 0)
    # 'nt' stands for new-tab, ';' separates commands for different tabs
    # We use -d to ensure the tabs open in the correct project directory
    wt_command = [
        "wt", "-w", "0",
        "nt", "--title", "FastAPI Backend", "-d", base_dir, "cmd", "/k", sys.executable, "-m", "uvicorn", "server:app", "--host", "127.0.0.1", "--port", "8000",
        ";", 
        "nt", "--title", "Streamlit Frontend", "-d", base_dir, "cmd", "/k", sys.executable, "-m", "streamlit", "run", app_path
    ]
    
    try:
        # Try to launch in Windows Terminal tabs
        subprocess.Popen(wt_command)
        print("\n✅ Opened backend and frontend in new tabs!")
    except FileNotFoundError:
        # Fallback to separate windows if Windows Terminal isn't installed
        print("\n⚠️ Windows Terminal not found. Falling back to separate windows...")
        subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "server:app", "--host", "127.0.0.1", "--port", "8000"],
            cwd=base_dir,
            creationflags=subprocess.CREATE_NEW_CONSOLE
        )
        subprocess.Popen(
            [sys.executable, "-m", "streamlit", "run", app_path],
            cwd=base_dir,
            creationflags=subprocess.CREATE_NEW_CONSOLE
        )
        print("\n✅ Both terminals have been launched!")

if __name__ == "__main__":
    main()
