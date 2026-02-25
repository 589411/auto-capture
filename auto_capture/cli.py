"""CLI entry point for auto-capture."""

from __future__ import annotations

import argparse
import signal
import sys
from pathlib import Path

from . import __version__
from .annotate import annotate_click, get_window_origin
from .capture import CaptureSession, find_window_id, list_windows
from .config import Config


def print_windows():
    """Print all available windows."""
    windows = list_windows()
    if not windows:
        print("找不到任何視窗。")
        return

    print(f"{'Window ID':>10}  {'Owner':<30}  {'Name'}")
    print("-" * 70)
    for win in windows:
        print(f"{win['window_id']:>10}  {win['owner']:<30}  {win['name']}")


BANNER = r"""
  ╔══════════════════════════════════════════════════════╗
  ║              🎯 auto-capture v{version}                ║
  ║     macOS 自動截圖工具 — 點擊即截圖，附標註框       ║
  ╚══════════════════════════════════════════════════════╝
""".strip()

EXAMPLES = """
使用範例：
  auto-capture --list-windows                          列出可用視窗
  auto-capture -w "Chrome" -o ~/Desktop/captures/      擷取 Chrome 視窗
  auto-capture -w "OpenClaw" -o ./out/ --manual-only   僅手動截圖（不監聽點擊）
  auto-capture -w "Finder" --no-annotate               不加標註框
  auto-capture -w "Safari" --box-color "#00FF00"       綠色標註框
  auto-capture -w "Arc" --delay 300                    點擊後等 300ms 再截圖

搭配 LaunchDock 使用：
  auto-capture -w "OpenClaw" -o ~/Desktop/captures/deploy-openclaw-cloud/
  cd ~/Documents/github/launchdock
  ./scripts/add-image.sh deploy-openclaw-cloud ~/Desktop/captures/deploy-openclaw-cloud/*.png
""".strip()


class CustomHelpFormatter(argparse.RawDescriptionHelpFormatter):
    """Custom formatter that shows banner + examples."""

    def _format_usage(self, usage, actions, groups, prefix):
        return ""


def main(argv: list[str] | None = None):
    """Main CLI entry point."""
    epilog = f"\n{EXAMPLES}"
    parser = argparse.ArgumentParser(
        prog="auto-capture",
        description=BANNER.format(version=__version__) + "\n\n  macOS 自動截圖工具 — 點擊時自動擷取視窗截圖並標註",
        epilog=epilog,
        formatter_class=CustomHelpFormatter,
    )
    parser.add_argument("--version", "-V", action="version", version=f"%(prog)s {__version__}")

    parser.add_argument(
        "--window", "-w",
        help="目標視窗名稱（模糊比對 owner 或 window name）",
    )
    parser.add_argument(
        "--window-id",
        type=int,
        help="直接指定 window ID（跳過名稱搜尋）",
    )
    parser.add_argument(
        "--output", "-o",
        default="./captures",
        help="輸出目錄（預設: ./captures/）",
    )
    parser.add_argument(
        "--manual-only",
        action="store_true",
        help="僅手動觸發截圖（不監聽滑鼠點擊）",
    )
    parser.add_argument(
        "--no-annotate",
        action="store_true",
        help="不在截圖上加標註框",
    )
    parser.add_argument(
        "--list-windows",
        action="store_true",
        help="列出所有可用視窗後退出",
    )
    parser.add_argument(
        "--box-color",
        help="標註框顏色（如 #FF3B30）",
    )
    parser.add_argument(
        "--box-size",
        type=int,
        help="標註框大小 (px)",
    )
    parser.add_argument(
        "--delay",
        type=int,
        help="點擊後延遲截圖 (ms)",
    )
    parser.add_argument(
        "--format",
        choices=["png", "jpg"],
        help="輸出格式（預設: png）",
    )
    parser.add_argument(
        "--config",
        help="設定檔路徑（預設: ~/.auto-capture.toml）",
    )

    args = parser.parse_args(argv)

    # 無參數時顯示互動式提示
    if len(sys.argv) == 1 and argv is None:
        print(BANNER.format(version=__version__))
        print()
        print("  💡 快速開始：")
        print("  ─────────────────────────────────────────────")
        print("  1. 先列出可用視窗：  auto-capture --list-windows")
        print("  2. 開始錄製：        auto-capture -w \"視窗名稱\" -o 輸出目錄/")
        print("  3. 點擊滑鼠自動截圖，按 Ctrl+C 停止")
        print()
        print("  📖 完整說明：        auto-capture --help")
        print()
        sys.exit(0)

    # --list-windows mode
    if args.list_windows:
        print_windows()
        return

    # Load config
    config_path = Path(args.config) if args.config else None
    config = Config.load(config_path)

    # Override config with CLI args
    if args.no_annotate:
        config.annotation.enabled = False
    if args.box_color:
        config.annotation.color = args.box_color
    if args.box_size:
        config.annotation.size = args.box_size
    if args.delay is not None:
        config.capture.delay_ms = args.delay
    if args.format:
        config.capture.format = args.format

    # Resolve window ID
    window_id = args.window_id
    if window_id is None:
        if not args.window:
            parser.error("必須指定 --window 或 --window-id")
        window_id = find_window_id(args.window)
        if window_id is None:
            print(f"❌ 找不到符合「{args.window}」的視窗。")
            print("可用視窗：")
            print_windows()
            sys.exit(1)

    output_dir = Path(args.output)

    # Callback: annotate after capture
    def on_capture(path: Path, click_pos: tuple[float, float] | None):
        if click_pos and config.annotation.enabled:
            try:
                origin = get_window_origin(window_id)
                annotate_click(
                    image_path=path,
                    click_pos=click_pos,
                    window_origin=origin,
                    config=config.annotation,
                )
            except Exception as e:
                print(f"⚠️  標註失敗: {e}")

        print(f"📸 {path.name}" + (f"  @ ({click_pos[0]:.0f}, {click_pos[1]:.0f})" if click_pos else "  (手動)"))

    # Create and run session
    session = CaptureSession(
        window_id=window_id,
        output_dir=output_dir,
        fmt=config.capture.format,
        delay_ms=config.capture.delay_ms,
        manual_only=args.manual_only,
        on_capture=on_capture,
    )

    # 開始前顯示設定摘要
    print()
    print(BANNER.format(version=__version__))
    print()
    print(f"  📋 設定摘要")
    print(f"  ─────────────────────────────────────────────")
    print(f"  🪟 目標視窗：    {args.window or f'ID {window_id}'} (ID: {window_id})")
    print(f"  📁 輸出目錄：    {output_dir.resolve()}")
    print(f"  🖱️  觸發模式：    {'僅手動 (hotkey)' if args.manual_only else '自動 (滑鼠點擊) + 手動'}")
    print(f"  🎨 標註框：      {'關閉' if not config.annotation.enabled else f'{config.annotation.color} {config.annotation.shape} {config.annotation.size}px'}")
    print(f"  ⏱️  延遲：        {config.capture.delay_ms}ms")
    print(f"  📷 格式：        {config.capture.format}")
    print()
    print(f"  ⌨️  按 Ctrl+C 停止錄製")
    print(f"  ─────────────────────────────────────────────")
    print()

    # Handle Ctrl+C gracefully
    def signal_handler(sig, frame):
        session.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)

    try:
        session.start()
    except PermissionError as e:
        print(f"\n❌ {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
