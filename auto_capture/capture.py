"""Core capture engine — window capture + mouse/hotkey listeners."""

from __future__ import annotations

import subprocess
import time
from pathlib import Path
from typing import Callable

import Quartz
from AppKit import NSWorkspace, NSRunningApplication
from Quartz import (
    CGEventGetLocation,
    CGEventMaskBit,
    CGWindowListCopyWindowInfo,
    kCGEventLeftMouseDown,
    kCGNullWindowID,
    kCGWindowListOptionOnScreenOnly,
    kCGWindowOwnerName,
    kCGWindowOwnerPID,
    kCGWindowNumber,
    kCGWindowName,
    kCGWindowBounds,
    kCGWindowLayer,
)

# Try to import AX API (needs pyobjc-framework-ApplicationServices)
try:
    from ApplicationServices import (
        AXUIElementCreateApplication,
        AXUIElementCopyAttributeValue,
    )
    _HAS_AX = True
except ImportError:
    _HAS_AX = False


# System processes that should be hidden from interactive selection
_SYSTEM_OWNERS = {
    "控制中心", "Window Server", "Dock", "Spotlight", "SystemUIServer",
    "TextInputMenuAgent", "WindowManager", "loginwindow",
    "Notification Center", "通知中心", "背景圖片",
}


def _get_ax_window_titles(pid: int) -> list[str]:
    """Try to get window titles via Accessibility API for a given PID.

    Returns list of window titles (may be empty if no AX permission or module).
    """
    if not _HAS_AX:
        return []
    try:
        app_ref = AXUIElementCreateApplication(pid)
        err, windows = AXUIElementCopyAttributeValue(
            app_ref, "AXWindows", None
        )
        if err != 0 or not windows:
            return []
        titles = []
        for win in windows:
            err, title = AXUIElementCopyAttributeValue(win, "AXTitle", None)
            if err == 0 and title:
                titles.append(str(title))
            else:
                titles.append("")
        return titles
    except Exception:
        return []


def list_windows(include_system: bool = False) -> list[dict]:
    """List all on-screen windows with owner name, window name, and window ID.

    Attempts to get window titles via Accessibility API for better display.
    Falls back to CGWindow info if unavailable.

    Args:
        include_system: If True, include system/background windows.

    Returns:
        List of dicts with keys: owner, name, window_id, bounds, pid
    """
    window_list = CGWindowListCopyWindowInfo(
        kCGWindowListOptionOnScreenOnly, kCGNullWindowID
    )

    # Collect AX titles per PID (cache to avoid repeated queries)
    pid_titles: dict[int, list[str]] = {}
    pid_title_idx: dict[int, int] = {}

    results = []
    for win in window_list:
        owner = win.get(kCGWindowOwnerName, "")
        cg_name = win.get(kCGWindowName, "")
        wid = win.get(kCGWindowNumber, 0)
        pid = win.get(kCGWindowOwnerPID, 0)
        bounds = win.get(kCGWindowBounds, {})
        layer = win.get(kCGWindowLayer, 0)

        if not owner or not wid:
            continue
        if not include_system and owner in _SYSTEM_OWNERS:
            continue
        # Skip background layer windows (layer 0 = normal windows)
        if not include_system and layer != 0:
            continue

        # Try to get a better name via AX API
        name = cg_name
        if not name and pid:
            if pid not in pid_titles:
                pid_titles[pid] = _get_ax_window_titles(pid)
                pid_title_idx[pid] = 0
            ax_titles = pid_titles[pid]
            idx = pid_title_idx[pid]
            if idx < len(ax_titles) and ax_titles[idx]:
                name = ax_titles[idx]
            pid_title_idx[pid] = idx + 1

        # Build bounds info for display
        w = int(bounds.get("Width", 0))
        h = int(bounds.get("Height", 0))
        x = int(bounds.get("X", 0))
        y = int(bounds.get("Y", 0))
        bounds_str = f"{w}x{h} @ ({x},{y})" if w and h else ""

        results.append({
            "owner": owner,
            "name": name or "",
            "window_id": int(wid),
            "pid": pid,
            "bounds": bounds_str,
        })

    return results


def find_window_id(query: str) -> int | None:
    """Find window ID by fuzzy-matching the window owner or name.

    Args:
        query: Substring to match (case-insensitive) against owner or window name.

    Returns:
        Window ID if found, None otherwise.
    """
    query_lower = query.lower()
    windows = list_windows()

    # Exact match on owner first
    for win in windows:
        if win["owner"].lower() == query_lower:
            return win["window_id"]

    # Substring match on owner or name
    for win in windows:
        if query_lower in win["owner"].lower() or query_lower in win["name"].lower():
            return win["window_id"]

    return None


def capture_window(window_id: int, output_path: Path, fmt: str = "png") -> Path:
    """Capture a specific window using macOS screencapture.

    Args:
        window_id: The CGWindowID to capture.
        output_path: Where to save the screenshot.
        fmt: Image format (png or jpg).

    Returns:
        Path to the saved screenshot.

    Raises:
        RuntimeError: If screencapture fails.
    """
    output_path = output_path.with_suffix(f".{fmt}")
    cmd = ["screencapture", "-l", str(window_id), "-o", "-x", str(output_path)]
    # -l <windowID>: capture specific window
    # -o: no shadow
    # -x: no sound

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
    if result.returncode != 0:
        raise RuntimeError(f"screencapture failed: {result.stderr}")

    if not output_path.exists():
        raise RuntimeError(f"Screenshot not saved: {output_path}")

    return output_path


class CaptureSession:
    """Manages a capture session — listens for mouse clicks and captures screenshots.

    Usage:
        session = CaptureSession(
            window_id=12345,
            output_dir=Path("./captures"),
            on_capture=lambda path, pos: print(f"Captured: {path}"),
        )
        session.start()  # blocks until Ctrl+C
    """

    def __init__(
        self,
        window_id: int,
        output_dir: Path,
        fmt: str = "png",
        delay_ms: int = 100,
        manual_only: bool = False,
        on_capture: Callable[[Path, tuple[float, float] | None], None] | None = None,
    ):
        self.window_id = window_id
        self.output_dir = output_dir
        self.fmt = fmt
        self.delay_ms = delay_ms
        self.manual_only = manual_only
        self.on_capture = on_capture

        self._counter = 0
        self._running = False
        self._tap = None

        # Ensure output dir exists
        self.output_dir.mkdir(parents=True, exist_ok=True)

    @property
    def counter(self) -> int:
        return self._counter

    def _next_path(self) -> Path:
        """Generate the next sequential filename."""
        self._counter += 1
        return self.output_dir / f"{self._counter:03d}.{self.fmt}"

    def take_screenshot(self, click_pos: tuple[float, float] | None = None) -> Path:
        """Take a single screenshot.

        Args:
            click_pos: (x, y) screen coordinates of mouse click, or None for manual.

        Returns:
            Path to the saved screenshot.
        """
        if self.delay_ms > 0:
            time.sleep(self.delay_ms / 1000.0)

        output_path = self._next_path()
        result = capture_window(self.window_id, output_path, self.fmt)

        if self.on_capture:
            self.on_capture(result, click_pos)

        return result

    def _event_callback(self, proxy, event_type, event, refcon):
        """CGEventTap callback — triggered on mouse click."""
        if event_type == kCGEventLeftMouseDown:
            location = CGEventGetLocation(event)
            click_pos = (location.x, location.y)
            try:
                self.take_screenshot(click_pos)
            except Exception as e:
                print(f"⚠️  截圖失敗: {e}")

        return event

    def start(self):
        """Start the capture session. Blocks until stopped (Ctrl+C).

        Raises:
            PermissionError: If Accessibility permission is not granted.
        """
        self._running = True

        if not self.manual_only:
            # Create event tap to listen for mouse clicks
            event_mask = CGEventMaskBit(kCGEventLeftMouseDown)

            self._tap = Quartz.CGEventTapCreate(
                Quartz.kCGSessionEventTap,
                Quartz.kCGHeadInsertEventTap,
                Quartz.kCGEventTapOptionListenOnly,  # passive listener
                event_mask,
                self._event_callback,
                None,
            )

            if self._tap is None:
                raise PermissionError(
                    "無法建立事件監聽器。請授予「輔助使用」(Accessibility) 權限：\n"
                    "  系統設定 → 隱私與安全性 → 輔助使用 → 勾選你的 Terminal app\n"
                    "  然後重新啟動終端機。"
                )

            # Create run loop source
            run_loop_source = Quartz.CFMachPortCreateRunLoopSource(None, self._tap, 0)
            Quartz.CFRunLoopAddSource(
                Quartz.CFRunLoopGetCurrent(),
                run_loop_source,
                Quartz.kCFRunLoopCommonModes,
            )
            Quartz.CGEventTapEnable(self._tap, True)

        print(f"🎬 開始錄製 (window ID: {self.window_id})")
        print(f"📁 輸出目錄: {self.output_dir}")
        if not self.manual_only:
            print("🖱️  點擊滑鼠自動截圖")
        print("⌨️  按 Ctrl+C 停止\n")

        try:
            if not self.manual_only:
                # Run the event loop
                Quartz.CFRunLoopRun()
            else:
                # Just wait for Ctrl+C (manual triggers handled by hotkey in cli.py)
                while self._running:
                    time.sleep(0.1)
        except KeyboardInterrupt:
            pass
        finally:
            self.stop()

    def stop(self):
        """Stop the capture session."""
        self._running = False
        if self._tap:
            Quartz.CGEventTapEnable(self._tap, False)
            Quartz.CFRunLoopStop(Quartz.CFRunLoopGetCurrent())
            self._tap = None
        print(f"\n✅ 錄製結束，共擷取 {self._counter} 張截圖")
