"""CLI entry point for auto-capture."""

from __future__ import annotations

import argparse
import signal
import sys
from pathlib import Path

from . import __version__
from .annotate import annotate_click, create_zoom_gif
from .capture import CaptureSession, find_window_id, list_windows, find_frontmost_window_for_pid
from .config import Config
from .redact import redact_image


def print_windows(include_system: bool = False):
    """Print all available windows."""
    windows = list_windows(include_system=include_system)
    if not windows:
        print("找不到任何視窗。")
        return

    print(f"{'Window ID':>10}  {'Owner':<30}  {'Name'}")
    print("-" * 70)
    for win in windows:
        print(f"{win['window_id']:>10}  {win['owner']:<30}  {win['name']}")


def interactive_select_window() -> dict | None:
    """Show an interactive numbered window list and let user pick one.

    Returns:
        Selected window dict, or None if cancelled.
    """
    windows = list_windows(include_system=False)
    if not windows:
        print("找不到任何可用視窗。")
        return None

    # Group display: show each window with index
    print("  🪟 可用視窗：")
    print("  ─────────────────────────────────────────────────────────────────")
    print(f"  {'#':>4}  {'應用程式':<20} {'視窗標題':<30} {'大小'}")
    print(f"  {'':>4}  {'':─<20} {'':─<30} {'':─<16}")

    for i, win in enumerate(windows, 1):
        owner = win['owner']
        name = win['name']
        bounds = win.get('bounds', '')
        # Truncate long names
        if len(owner) > 18:
            owner = owner[:16] + '…'
        display_name = name if name else '(未命名)'
        if len(display_name) > 28:
            display_name = display_name[:26] + '…'
        print(f"  {i:>4}  {owner:<20} {display_name:<30} {bounds}")

    print()
    print(f"  共 {len(windows)} 個視窗（已過濾系統視窗）")
    print()

    while True:
        try:
            raw = input("  輸入編號選擇視窗（q 取消）: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return None

        if raw.lower() in ('q', 'quit', 'exit', ''):
            return None

        try:
            idx = int(raw)
        except ValueError:
            print(f"  ⚠️  請輸入數字 1-{len(windows)}")
            continue

        if 1 <= idx <= len(windows):
            selected = windows[idx - 1]
            name_display = selected['name'] or '(未命名)'
            print(f"  ✅ 已選擇：{selected['owner']} — {name_display} (ID: {selected['window_id']})")
            return selected
        else:
            print(f"  ⚠️  請輸入 1-{len(windows)} 之間的數字")


BANNER = r"""
  ╔══════════════════════════════════════════════════════╗
  ║              🎯 auto-capture v{version}                ║
  ║     macOS 自動截圖工具 — 點擊即截圖，附標註框       ║
  ╚══════════════════════════════════════════════════════╝
""".strip()

EXAMPLES = """
使用範例：
  auto-capture                                         全螢幕截圖（預設）
  auto-capture -o ~/Desktop/captures/                   指定輸出目錄
  auto-capture --redact                                 自動遮蔽敏感資訊
  auto-capture --no-annotate                            不加點擊標記
  auto-capture --no-gif                                 不產生縮放 GIF
  auto-capture --box-color "#00FF00"                    綠色點擊標記
  auto-capture --delay 300                              點擊後等 300ms 再截圖
  auto-capture --window "Chrome"                        只擷取特定視窗
  auto-capture --list-windows                           列出可用視窗

每次點擊會產生：
  001.png  — 全螢幕截圖（含點擊標記）
  001.gif  — 從全螢幕縮放到點擊處的動畫

敏感資訊遮蔽（--redact）：
  自動偵測信用卡號、API key、email 地址等，自動上馬賽克。
  也可在 ~/.auto-capture.toml 設定預設開啟：
    [redact]
    enabled = true

搭配 LaunchDock 使用：
  auto-capture --redact -o ~/Desktop/captures/deploy-openclaw-cloud/
  cd ~/Documents/github/launchdock
  ./scripts/add-image.sh deploy-openclaw-cloud ~/Desktop/captures/deploy-openclaw-cloud/*.gif
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
        help="擷取特定視窗（模糊比對名稱）。不指定則截全螢幕",
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
        "--no-gif",
        action="store_true",
        help="不產生縮放動畫 GIF",
    )
    parser.add_argument(
        "--redact",
        action="store_true",
        help="啟用自動遮蔽敏感資訊（信用卡、API key、email 等）",
    )
    parser.add_argument(
        "--no-redact",
        action="store_true",
        help="停用自動遮蔽（覆蓋設定檔）",
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

    # 無參數時進入互動模式
    is_interactive = (len(sys.argv) == 1 and argv is None)

    if is_interactive:
        print(BANNER.format(version=__version__))
        print()

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
    if args.redact:
        config.redact.enabled = True
    if args.no_redact:
        config.redact.enabled = False

    # Determine capture mode: fullscreen (default) or window-specific
    use_fullscreen = True
    window_id = args.window_id or 0
    window_pid = 0
    window_owner = ""
    window_display_name = "全螢幕"

    if args.window_id:
        use_fullscreen = False
        window_display_name = f"Window ID {args.window_id}"
    elif args.window:
        use_fullscreen = False
        windows = list_windows()
        query = args.window.lower()
        for win in windows:
            if win["owner"].lower() == query:
                window_id = win["window_id"]
                window_pid = win.get("pid", 0)
                window_owner = win["owner"]
                break
        if not window_id:
            for win in windows:
                if query in win["owner"].lower() or query in win["name"].lower():
                    window_id = win["window_id"]
                    window_pid = win.get("pid", 0)
                    window_owner = win["owner"]
                    break
        if not window_id:
            print(f"❌ 找不到符合「{args.window}」的視窗，改用全螢幕模式。")
            use_fullscreen = True
        else:
            window_display_name = window_owner or f"ID {window_id}"

    output_dir = Path(args.output)

    # 互動模式下詢問輸出目錄
    if is_interactive:
        try:
            raw_dir = input(f"  📁 輸出目錄（Enter 使用預設 {output_dir}）: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n  👋 已取消")
            sys.exit(0)
        if raw_dir:
            output_dir = Path(raw_dir).expanduser()

    # Feature flags
    generate_gif = not args.no_gif

    # Callback: annotate after capture
    def on_capture(path: Path, click_pos: tuple[float, float] | None):
        # 0) Redact sensitive info (before annotation/GIF)
        if config.redact.enabled:
            try:
                _, redacted = redact_image(path, config.redact)
                if redacted:
                    names = set(r.pattern_name for r in redacted)
                    print(f"🔒 已遮蔽 {len(redacted)} 處敏感資訊（{', '.join(names)}）")
            except Exception as e:
                print(f"⚠️  遮蔽失敗: {e}")

        if click_pos:
            # Determine origin
            if session.fullscreen:
                origin = (0.0, 0.0)
            else:
                from .annotate import get_window_origin
                current_wid = session.initial_window_id
                origin = get_window_origin(current_wid)

            # 1) Draw click marker on the PNG
            if config.annotation.enabled:
                try:
                    annotate_click(
                        image_path=path,
                        click_pos=click_pos,
                        window_origin=origin,
                        config=config.annotation,
                    )
                except Exception as e:
                    print(f"⚠️  標註失敗: {e}")

            # 2) Generate zoom-to-click GIF
            if generate_gif:
                try:
                    gif_path = create_zoom_gif(
                        image_path=path,
                        click_pos=click_pos,
                        window_origin=origin,
                        color=config.annotation.color,
                    )
                    print(f"🎬 {gif_path.resolve()}")
                except Exception as e:
                    print(f"⚠️  GIF 生成失敗: {e}")

        pos_info = f"  @ ({click_pos[0]:.0f}, {click_pos[1]:.0f})" if click_pos else "  (手動)"
        print(f"📸 {path.resolve()}{pos_info}")

    # Create and run session
    session = CaptureSession(
        output_dir=output_dir,
        window_id=window_id,
        pid=window_pid,
        owner=window_owner,
        fullscreen=use_fullscreen,
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
    print(f"  🖥️  擷取模式：    {window_display_name}")
    print(f"  📁 輸出目錄：    {output_dir.resolve()}")
    print(f"  🖱️  觸發模式：    {'僅手動 (hotkey)' if args.manual_only else '自動 (滑鼠點擊) + 手動'}")
    print(f"  🎨 點擊標記：    {'關閉' if not config.annotation.enabled else f'{config.annotation.color} 漣漪+準星'}")
    print(f"  🎬 縮放 GIF：    {'開啟' if generate_gif else '關閉'}")
    redact_label = '開啟' if config.redact.enabled else '關閉'
    if config.redact.enabled and config.redact.disabled_patterns:
        redact_label += f"（排除: {', '.join(config.redact.disabled_patterns)}）"
    print(f"  🔒 敏感遮蔽：    {redact_label}")
    print(f"  ⏱️  延遲：        {config.capture.delay_ms}ms")
    print(f"  📷 格式：        {config.capture.format} + {'GIF' if generate_gif else ''}")
    print()
    print(f"  ⌨️  按 Ctrl+C 停止錄製")
    print(f"  ─────────────────────────────────────────────")
    print()

    # Handle Ctrl+C gracefully — session.start() already calls stop() in finally
    def signal_handler(sig, frame):
        Quartz_CFRunLoopStop_safe()

    def Quartz_CFRunLoopStop_safe():
        """Stop the run loop so start()'s finally block handles cleanup."""
        try:
            import Quartz as _Q
            _Q.CFRunLoopStop(_Q.CFRunLoopGetCurrent())
        except Exception:
            pass

    signal.signal(signal.SIGINT, signal_handler)

    try:
        session.start()
    except PermissionError as e:
        print(f"\n❌ {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
