# auto-capture

macOS 自動截圖工具 — 一邊操作一邊自動擷取螢幕截圖，並在點擊位置加上標註框。

專為 [LaunchDock](https://github.com/589411/launchdock) 教學文章截圖設計，也可獨立使用。

## 功能

- **Window capture**：擷取指定視窗（非全螢幕）
- **Click trigger**：監聽滑鼠點擊，自動觸發截圖
- **Hotkey trigger**：手動按快捷鍵截圖（預設 `Ctrl+Shift+S`）
- **Click annotation**：在截圖上用框線標註點擊位置（大小、顏色可調）
- **Sequential naming**：按序號命名 `001.png`, `002.png`, …

## 系統需求

- macOS 12+
- Python 3.10+
- 需授予「輔助使用」(Accessibility) 權限

## 安裝

```bash
# 從原始碼安裝（開發模式）
git clone https://github.com/589411/auto-capture.git
cd auto-capture
pip install -e .

# 或用 pipx（推薦，隔離環境）
pipx install .
```

## 快速開始

```bash
# 擷取「OpenClaw」視窗，點擊時自動截圖
auto-capture --window "OpenClaw" --output ~/Desktop/captures/

# 僅手動觸發（不監聽點擊）
auto-capture --window "OpenClaw" --output ~/Desktop/captures/ --manual-only

# 列出可用視窗
auto-capture --list-windows
```

## 與 LaunchDock 搭配

```bash
# 1. 開始錄製
auto-capture --window "OpenClaw" --output ~/Desktop/captures/deploy-openclaw-cloud/

# 2. 照教學文章操作，工具會自動截圖

# 3. 操作完成後按 Ctrl+C 停止

# 4. 回到 launchdock repo，將截圖配對到文章
cd ~/Documents/github/launchdock
./scripts/add-image.sh deploy-openclaw-cloud ~/Desktop/captures/deploy-openclaw-cloud/*.png
```

## 設定

可透過 `~/.auto-capture.toml` 或命令列參數調整：

```toml
[annotation]
enabled = true
shape = "rectangle"   # rectangle | circle
color = "#FF3B30"     # 標註框顏色
line_width = 3        # 線寬 (px)
size = 40             # 框大小 (px)
padding = 8           # 框與點擊位置的間距

[capture]
format = "png"
delay_ms = 100        # 點擊後延遲截圖（等 UI 反應）

[hotkey]
trigger = "ctrl+shift+s"
```

## 命令列參數

| 參數 | 說明 | 預設值 |
|---|---|---|
| `--window` / `-w` | 目標視窗名稱（模糊比對） | 必填 |
| `--output` / `-o` | 輸出目錄 | `./captures/` |
| `--manual-only` | 僅手動觸發，不監聽點擊 | `false` |
| `--no-annotate` | 不加標註框 | `false` |
| `--list-windows` | 列出可用視窗後退出 | - |
| `--box-color` | 標註框顏色 | `#FF3B30` |
| `--box-size` | 標註框大小 (px) | `40` |
| `--delay` | 點擊後延遲 (ms) | `100` |
| `--format` | 輸出格式 (png/jpg) | `png` |
| `--config` | 設定檔路徑 | `~/.auto-capture.toml` |

## 權限設定

首次執行時，macOS 會要求授予「輔助使用」權限：

1. 系統設定 → 隱私與安全性 → 輔助使用
2. 將你的 Terminal app（Terminal / iTerm2 / VS Code）加入清單並勾選
3. 重新啟動終端機

## 授權

MIT License
