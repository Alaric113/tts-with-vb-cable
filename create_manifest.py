import os
import sys
import json
import hashlib
from pathlib import Path

def calculate_sha256(file_path):
    """Calculates the SHA256 hash of a file."""
    sha256 = hashlib.sha256()
    try:
        with open(file_path, "rb") as f:
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256.update(byte_block)
        return sha256.hexdigest()
    except Exception as e:
        print(f"Error: Could not calculate hash for {file_path}: {e}")
        return None

def create_manifest(target_dir, version):
    """
    Scans the target directory and creates a manifest.json for all files.

    :param target_dir: The application build directory to scan.
    :param version: The version number to write into the manifest.
    """
    target_path = Path(target_dir)
    if not target_path.is_dir():
        print(f"Error: Target directory '{target_dir}' does not exist or is not a directory.")
        return

    print(f"Scanning directory for version {version}: {target_path.resolve()}")

    manifest_data = {
        "version": version,
        "files": {}
    }

    files_to_process = []
    # Manually walk the directory to control what gets added
    for root, dirs, files in os.walk(target_path):
        # Skip _internal directory
        if Path(root).name == "_internal":
            dirs[:] = [] # Don't recurse into _internal
            continue
        
        for name in files:
            file_path = Path(root) / name
            files_to_process.append(file_path)

    total_files = len(files_to_process)
    
    for i, file_path in enumerate(files_to_process):
        # Exclude the manifest file itself and this script
        if file_path.name == "manifest.json" or file_path.name == "create_manifest.py":
            continue

        relative_path = file_path.relative_to(target_path).as_posix()
        
        # Display progress
        progress = (i + 1) / total_files * 100
        print(f"[{progress:6.2f}%] Processing: {relative_path}", end='\r')

        file_hash = calculate_sha256(file_path)
        if file_hash:
            manifest_data["files"][relative_path] = file_hash

    # Clear the last progress line
    print(" " * 80, end='\r')

    # Explicitly add _internal.zip to the manifest if it exists
    internal_zip_path = target_path / "_internal.zip"
    if internal_zip_path.exists():
        internal_zip_relative_path = internal_zip_path.relative_to(target_path).as_posix()
        internal_zip_hash = calculate_sha256(internal_zip_path)
        if internal_zip_hash:
            manifest_data["files"][internal_zip_relative_path] = internal_zip_hash
            print(f"\nAdded _internal.zip to manifest: {internal_zip_relative_path}")

    output_path = target_path / "manifest.json"
    try:
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(manifest_data, f, indent=4, ensure_ascii=False)
        print(f"\nSuccessfully created manifest.json at: {output_path.resolve()}")
    except Exception as e:
        print(f"\nError: Could not write manifest.json: {e}")

def main():
    if len(sys.argv) != 3:
        print("Usage: python create_manifest.py <target_directory> <version_number>")
        print("Example: python create_manifest.py ./dist/JuMouth v1.2.3")
        sys.exit(1)

    target_directory = sys.argv[1]
    app_version = sys.argv[2]

    create_manifest(target_directory, app_version)

if __name__ == "__main__":
    main()
