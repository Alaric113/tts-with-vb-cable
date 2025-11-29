# -*- coding: utf-8 -*-
# 檔案: create_manifest.py
# 功用: 為應用程式建立一個用於部分更新的 manifest.json 檔案。

import os
import sys
import json
import hashlib
from pathlib import Path

def calculate_sha256(file_path):
    """計算檔案的 SHA256 雜湊值。"""
    sha256 = hashlib.sha256()
    try:
        with open(file_path, "rb") as f:
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256.update(byte_block)
        return sha256.hexdigest()
    except Exception as e:
        print(f"錯誤: 無法計算檔案 {file_path} 的雜湊值: {e}")
        return None

def create_manifest(target_dir, version):
    """
    掃描目標目錄，為所有檔案建立一個 manifest.json。

    :param target_dir: 要掃描的應用程式建置目錄。
    :param version: 要寫入 manifest 的版本號。
    """
    target_path = Path(target_dir)
    if not target_path.is_dir():
        print(f"錯誤: 目標目錄 '{target_dir}' 不存在或不是一個目錄。")
        return

    print(f"正在為版本 {version} 掃描目錄: {target_path.resolve()}")

    manifest_data = {
        "version": version,
        "files": {}
    }

    files_to_process = [f for f in target_path.rglob('*') if f.is_file()]
    total_files = len(files_to_process)
    
    for i, file_path in enumerate(files_to_process):
        # 排除 manifest.json 本身和此腳本
        if file_path.name == "manifest.json" or file_path.name == "create_manifest.py":
            continue

        relative_path = file_path.relative_to(target_path).as_posix()
        
        # 顯示進度
        progress = (i + 1) / total_files * 100
        print(f"[{progress:6.2f}%] 正在處理: {relative_path}", end='\r')

        file_hash = calculate_sha256(file_path)
        if file_hash:
            manifest_data["files"][relative_path] = file_hash

    # 清除最後的進度列
    print(" " * 80, end='\r')

    output_path = target_path / "manifest.json"
    try:
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(manifest_data, f, indent=4, ensure_ascii=False)
        print(f"\n成功建立 manifest.json 檔案於: {output_path.resolve()}")
    except Exception as e:
        print(f"\n錯誤: 無法寫入 manifest.json 檔案: {e}")

def main():
    if len(sys.argv) != 3:
        print("用法: python create_manifest.py <目標目錄> <版本號>")
        print("範例: python create_manifest.py ./dist/JuMouth v1.2.3")
        sys.exit(1)

    target_directory = sys.argv[1]
    app_version = sys.argv[2]

    create_manifest(target_directory, app_version)

if __name__ == "__main__":
    main()
