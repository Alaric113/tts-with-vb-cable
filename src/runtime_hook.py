import sys
import os
from datetime import datetime

# It's crucial to use a path that is guaranteed to be writable.
# The user's home directory is a safe choice.
log_path = os.path.join(os.path.expanduser("~"), "jumouth_debug_log.txt")

try:
    # Open the log file in 'w' mode first to clear previous logs.
    with open(log_path, "w", encoding="utf-8") as f:
        f.write(f"--- JuMouth Debug Log [{datetime.now()}] ---\n\n")

    # Re-open stdout and stderr to append to this file.
    # This is a common technique for capturing all output from a frozen app.
    sys.stdout = sys.stderr = open(log_path, "a", encoding="utf-8", buffering=1) # Use line buffering

    print(f"--- System Information ---")
    print(f"Python Version: {sys.version}")
    print(f"Platform: {sys.platform}")
    print(f"Executable: {sys.executable}")
    print(f"Frozen: {getattr(sys, 'frozen', False)}")
    print(f"MEIPASS: {getattr(sys, '_MEIPASS', 'Not found')}")
    
    print("\n--- sys.path ---")
    for p in sys.path:
        print(p)

    print("\n--- os.environ['PATH'] ---")
    for p in os.environ.get("PATH", "").split(os.pathsep):
        print(p)

    # List files in the temporary _MEIPASS directory, which is where the app is unpacked.
    meipass_dir = getattr(sys, '_MEIPASS', None)
    if meipass_dir and os.path.isdir(meipass_dir):
        print(f"\n--- Files in _MEIPASS ({meipass_dir}) ---")
        try:
            # We are particularly interested in numpy, scipy, and their .libs directories
            paths_to_check = [
                '.', 
                'numpy', 
                'numpy/core',
                'scipy', 
                'scipy/linalg',
                'scipy/.libs', 
                'numpy/.libs'
            ]
            for p_to_check in paths_to_check:
                full_path = os.path.join(meipass_dir, p_to_check)
                if os.path.isdir(full_path):
                    print(f"\n--- Listing for: {full_path} ---")
                    try:
                        files = os.listdir(full_path)
                        for f_name in files[:20]: # List up to 20 files
                            print(f"    {f_name}")
                        if len(files) > 20:
                            print(f"    ... and {len(files) - 20} more files")
                    except Exception as e:
                        print(f"    Error listing files: {e}")
                else:
                    print(f"\n--- Directory not found: {full_path} ---")

        except Exception as e:
            print(f"Error listing files in _MEIPASS: {e}")

    print("\n--- End of Debug Info ---")
    print("Runtime hook finished. Control is now being passed to the main script...")

except Exception as e:
    # If the hook itself fails, try to write that to the log.
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(f"\n\nFATAL ERROR IN RUNTIME HOOK: {e}\n")

