# -*- coding: utf-8 -*-
# 檔案: main.py
# 功用: 應用程式的進入點 (Entry Point)。
#      - 這是 PyInstaller 打包的目標。
#      - 它會匯入並執行 src 套件中的主要邏輯。

if __name__ == "__main__":
    # 為了讓 PyInstaller 和直接執行 (python main.py) 都能正確找到模組，
    # 我們直接從 src 套件中匯入並執行 main 函式。
    # Python 會自動將 main.py 所在的目錄加入到 sys.path，
    # 因此可以直接匯入 'src'。
    from src.__main__ import main
    main() 