#!/usr/bin/env python3
import argparse
import json
import os
import re
import sqlite3
import subprocess
import sys
import threading
import time
from datetime import datetime
from typing import Optional, Tuple

try:
    import cv2
except Exception:  # pragma: no cover - runtime fallback for headless environments
    cv2 = None

import numpy as np
import requests
try:
    from mss import mss
except Exception:
    mss = None

from ai_core import AIModelDB, SimpleAIModel
from agent_core import AgentMemory, DecisionEngine
from device_profiles import get_screen_preset


def resolve_action_name(resource: dict, default_action: str = "click") -> str:
    action = str(resource.get("action", "") or "").strip().lower()
    if action in {"click", "tap", "swipe", "drag"}:
        return action
    return default_action


def resolve_action_sequence(action_spec: Optional[str], default_action: str = "click") -> list[str]:
    if not action_spec:
        return [default_action]
    cleaned = action_spec.strip()
    if not cleaned:
        return [default_action]
    if "->" in cleaned:
        parts = [p.strip() for p in cleaned.split("->") if p.strip()]
    else:
        parts = [p.strip() for p in re.split(r"[;|]", cleaned) if p.strip()]
    if not parts:
        return [default_action]
    normalized = []
    for part in parts:
        if part.lower().startswith("wait"):
            normalized.append(part.lower())
        elif part.lower() in {"click", "tap", "swipe", "drag"}:
            normalized.append(part.lower())
        else:
            normalized.append(default_action)
    return normalized


def preprocess_resources(resources: list[dict]) -> list[dict]:
    for resource in resources:
        if resource.get("mode") == "hsv":
            try:
                resource["_hsv_lower"] = np.array(json.loads(resource.get("hsv_lower", "[0, 0, 0]")), dtype=np.uint8)
                resource["_hsv_upper"] = np.array(json.loads(resource.get("hsv_upper", "[179, 255, 255]")), dtype=np.uint8)
            except Exception:
                resource["_hsv_lower"] = np.array([0, 0, 0], dtype=np.uint8)
                resource["_hsv_upper"] = np.array([179, 255, 255], dtype=np.uint8)
    return resources

class LocalResourceDB:
    def __init__(self, db_path: str = "assistant.db"):
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.lock = threading.Lock()
        self._init_db()

    def _init_db(self) -> None:
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS resources (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                mode TEXT NOT NULL DEFAULT 'hsv',
                hsv_lower TEXT,
                hsv_upper TEXT,
                template_path TEXT,
                threshold REAL NOT NULL DEFAULT 0.8,
                action TEXT NOT NULL DEFAULT 'collect',
                description TEXT,
                notes TEXT,
                priority INTEGER NOT NULL DEFAULT 0
            )
            """
        )
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                resource_name TEXT NOT NULL,
                status TEXT NOT NULL,
                details TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS learned_samples (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                resource_name TEXT NOT NULL,
                hsv_value TEXT NOT NULL,
                success INTEGER NOT NULL DEFAULT 0,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        self.conn.commit()

    def seed_defaults(self) -> None:
        defaults = [
            ("wood", "hsv", "[20, 100, 100]", "[40, 255, 255]", None, 0.8, "collect", "Wood", "Use for wood nodes", 3),
            ("stone", "hsv", "[0, 100, 100]", "[20, 255, 255]", None, 0.8, "collect", "Stone", "Use for stone nodes", 2),
            ("fiber", "hsv", "[35, 100, 100]", "[60, 255, 255]", None, 0.8, "collect", "Fiber", "Use for fiber nodes", 1),
            ("hide", "hsv", "[170, 100, 100]", "[180, 255, 255]", None, 0.8, "collect", "Hide", "Use for hide nodes", 1),
        ]
        for row in defaults:
            name, mode, lower, upper, template_path, threshold, action, description, notes, priority = row
            self.conn.execute(
                """
                INSERT OR IGNORE INTO resources (
                    name, mode, hsv_lower, hsv_upper, template_path, threshold, action, description, notes, priority
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (name, mode, lower, upper, template_path, threshold, action, description, notes, priority),
            )
        self.conn.commit()

    def import_from_json(self, json_path: str) -> None:
        if not os.path.exists(json_path):
            return
        with open(json_path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        for entry in data.get("resources", []):
            self.conn.execute(
                """
                INSERT OR REPLACE INTO resources (
                    name, mode, hsv_lower, hsv_upper, template_path, threshold, action, description, notes, priority
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    entry["name"],
                    entry.get("mode", "hsv"),
                    json.dumps(entry.get("hsv_lower", [])),
                    json.dumps(entry.get("hsv_upper", [])),
                    entry.get("template_path"),
                    entry.get("threshold", 0.8),
                    entry.get("action", "collect"),
                    entry.get("description", ""),
                    entry.get("notes", ""),
                    entry.get("priority", 0),
                ),
            )
        self.conn.commit()

    def list_resources(self):
        rows = self.conn.execute("SELECT name, mode, action, description, priority FROM resources ORDER BY priority DESC, name").fetchall()
        return [dict(row) for row in rows]

    def get_resource(self, name: str):
        row = self.conn.execute(
            "SELECT name, mode, hsv_lower, hsv_upper, template_path, threshold, action, description, notes, priority FROM resources WHERE name = ?",
            (name,),
        ).fetchone()
        return dict(row) if row else None

    def all_resources(self):
        rows = self.conn.execute("SELECT name, mode, hsv_lower, hsv_upper, template_path, threshold, action, description, notes, priority FROM resources ORDER BY priority DESC, name").fetchall()
        return [dict(row) for row in rows]

    def log_event(self, resource_name: str, status: str, details: str) -> None:
        with self.lock:
            self.conn.execute(
                "INSERT INTO events (resource_name, status, details) VALUES (?, ?, ?)",
                (resource_name, status, details),
            )
            self.conn.commit()

    def record_learning(self, resource_name: str, hsv_value: Optional[Tuple[int, int, int]], success: bool) -> None:
        if not hsv_value:
            return
        with self.lock:
            self.conn.execute(
                "INSERT INTO learned_samples (resource_name, hsv_value, success) VALUES (?, ?, ?)",
                (resource_name, json.dumps(list(hsv_value)), 1 if success else 0),
            )
            self.conn.commit()
            self._adapt_resource_from_sample(resource_name, hsv_value, success)

    def _adapt_resource_from_sample(self, resource_name: str, hsv_value: Tuple[int, int, int], success: bool) -> None:
        resource = self.get_resource(resource_name)
        if not resource or resource.get("mode") != "hsv":
            return
        if not success:
            return
        base_lower = np.array(json.loads(resource["hsv_lower"] or "[0, 0, 0]"), dtype=int)
        base_upper = np.array(json.loads(resource["hsv_upper"] or "[179, 255, 255]"), dtype=int)
        sample = np.array(hsv_value, dtype=int)

        new_lower = np.array([
            max(0, min(base_lower[0], sample[0] - 12)),
            max(0, min(base_lower[1], sample[1] - 35)),
            max(0, min(base_lower[2], sample[2] - 35)),
        ], dtype=int)
        new_upper = np.array([
            min(179, max(base_upper[0], sample[0] + 12)),
            min(255, max(base_upper[1], sample[1] + 35)),
            min(255, max(base_upper[2], sample[2] + 35)),
        ], dtype=int)

        self.conn.execute(
            "UPDATE resources SET hsv_lower = ?, hsv_upper = ?, notes = ? WHERE name = ?",
            (
                json.dumps(new_lower.tolist()),
                json.dumps(new_upper.tolist()),
                f"Learned from {self._history_for(resource_name)} samples",
                resource_name,
            ),
        )
        self.conn.commit()

    def _history_for(self, resource_name: str) -> int:
        row = self.conn.execute(
            "SELECT COUNT(*) as cnt FROM learned_samples WHERE resource_name = ?",
            (resource_name,),
        ).fetchone()
        return int(row["cnt"] if row else 0)


class VisionEngine:
    def __init__(self, monitor: int = 1, screenshots_dir: str = "screenshots", fast_actions: bool = False):
        self.monitor = monitor
        self.screenshots_dir = screenshots_dir
        self.fast_actions = fast_actions
        os.makedirs(self.screenshots_dir, exist_ok=True)
        self.sct = mss()
        self.kernel = np.ones((5, 5), np.uint8)

    def capture_frame(self) -> np.ndarray:
        if cv2 is None:
            raise RuntimeError("OpenCV is not available in this environment")
        screenshot = self.sct.grab(self.sct.monitors[self.monitor])
        frame = np.array(screenshot)
        return cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)

    def save_frame(self, frame: np.ndarray, label: str) -> str:
        if cv2 is None:
            raise RuntimeError("OpenCV is not available in this environment")
        filename = os.path.join(self.screenshots_dir, f"{label}_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}.png")
        cv2.imwrite(filename, frame)
        return filename

    def _find_by_hsv(self, hsv: np.ndarray, resource: dict) -> Optional[Tuple[Tuple[int, int], Tuple[int, int, int]]]:
        if cv2 is None:
            return None
        lower = resource.get("_hsv_lower")
        upper = resource.get("_hsv_upper")
        if lower is None or upper is None:
            if not resource.get("hsv_lower") or not resource.get("hsv_upper"):
                return None
            lower = np.array(json.loads(resource["hsv_lower"] or "[0, 0, 0]"), dtype=np.uint8)
            upper = np.array(json.loads(resource["hsv_upper"] or "[179, 255, 255]"), dtype=np.uint8)
        mask = cv2.inRange(hsv, lower, upper)
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, self.kernel)
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, self.kernel)

        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not contours:
            return None

        largest = max(contours, key=cv2.contourArea)
        if cv2.contourArea(largest) < 100:
            return None

        x, y, w, h = cv2.boundingRect(largest)
        roi = hsv[y:y + h, x:x + w]
        mean_hsv = cv2.mean(roi)
        return ((x + w // 2, y + h // 2), (int(mean_hsv[0]), int(mean_hsv[1]), int(mean_hsv[2])))

    def _find_by_template(self, frame: np.ndarray, resource: dict) -> Optional[Tuple[Tuple[int, int], Tuple[int, int, int]]]:
        if cv2 is None:
            return None
        template = resource.get("_template")
        if template is None:
            template_path = resource.get("template_path")
            if not template_path or not os.path.exists(template_path):
                return None
            template = cv2.imread(template_path, cv2.IMREAD_COLOR)
            if template is None:
                return None
            resource["_template"] = template
        result = cv2.matchTemplate(frame, template, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, max_loc = cv2.minMaxLoc(result)
        if max_val < float(resource.get("threshold", 0.8)):
            return None
        x, y = max_loc
        h, w = template.shape[:2]
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        roi = hsv[y:y + h, x:x + w]
        mean_hsv = cv2.mean(roi)
        return ((x + w // 2, y + h // 2), (int(mean_hsv[0]), int(mean_hsv[1]), int(mean_hsv[2])))

    def find_resource(self, frame: np.ndarray, resource: dict) -> Optional[Tuple[Tuple[int, int], Tuple[int, int, int]]]:
        if resource.get("mode") == "template":
            return self._find_by_template(frame, resource)
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        return self._find_by_hsv(hsv, resource)

    def _get_pyautogui(self):
        try:
            import pyautogui
        except Exception as exc:  # pragma: no cover - environment-dependent
            raise RuntimeError(f"pyautogui is not available: {exc}") from exc
        return pyautogui

    def click(self, point: Tuple[int, int]) -> None:
        try:
            pyautogui = self._get_pyautogui()
        except Exception as exc:
            print(str(exc))
            return
        duration = 0.05 if getattr(self, "fast_actions", False) else 0.1
        pyautogui.moveTo(point[0], point[1], duration=duration)
        pyautogui.click(point[0], point[1])

    def perform_action(self, action_name: str, point: Tuple[int, int], screen_size: Optional[Tuple[int, int]] = None) -> bool:
        try:
            pyautogui = self._get_pyautogui()
        except Exception as exc:
            print(str(exc))
            return False

        if action_name in {"swipe", "drag"}:
            width = screen_size[0] if screen_size and screen_size[0] else 1280
            height = screen_size[1] if screen_size and screen_size[1] else 720
            swipe_end = (min(width - 1, point[0] + 120), max(0, point[1] - 80))
            duration = 0.05 if getattr(self, "fast_actions", False) else 0.1
            drag_duration = 0.15 if getattr(self, "fast_actions", False) else 0.3
            pyautogui.moveTo(point[0], point[1], duration=duration)
            pyautogui.dragTo(swipe_end[0], swipe_end[1], duration=drag_duration, button='left')
            return True

        if action_name.startswith("wait"):
            match = re.search(r"wait(?:\s*[:=]\s*)?(\d+(?:\.\d+)?)", action_name)
            if match:
                time.sleep(float(match.group(1)))
            else:
                time.sleep(0.3)
            return True

        pyautogui.moveTo(point[0], point[1], duration=0.1)
        pyautogui.click(point[0], point[1])
        return True

    def execute_sequence(self, action_spec: Optional[str], point: Tuple[int, int], screen_size: Optional[Tuple[int, int]] = None) -> bool:
        for action_name in resolve_action_sequence(action_spec):
            if not self.perform_action(action_name, point, screen_size=screen_size):
                return False
        return True


class NoRootVisionEngine(VisionEngine):
    def __init__(self, monitor: int = 1, screenshots_dir: str = "screenshots", fast_actions: bool = False):
        super().__init__(monitor=monitor, screenshots_dir=screenshots_dir, fast_actions=fast_actions)

    def capture_frame(self) -> np.ndarray:
        return super().capture_frame()

    def click(self, point: Tuple[int, int]) -> None:
        return super().click(point)

    def perform_action(self, action_name: str, point: Tuple[int, int], screen_size: Optional[Tuple[int, int]] = None) -> bool:
        return super().perform_action(action_name, point, screen_size=screen_size)


class ADBController:
    def __init__(self, device: Optional[str] = None, wifi_host: Optional[str] = None):
        self.device = device
        self.wifi_host = wifi_host
        if self.wifi_host:
            self.connect_wifi()

    def adb_args(self) -> list[str]:
        args = ["adb"]
        if self.device:
            args.extend(["-s", self.device])
        elif self.wifi_host:
            args.extend(["-s", self.wifi_host])
        return args

    def run(self, cmd: list[str], capture_output: bool = True) -> subprocess.CompletedProcess:
        return subprocess.run(self.adb_args() + cmd, capture_output=capture_output, check=False)

    def connect_wifi(self) -> bool:
        if not self.wifi_host:
            return False
        proc = subprocess.run(["adb", "connect", self.wifi_host], capture_output=True, text=True)
        return proc.returncode == 0

    def tap(self, x: int, y: int) -> bool:
        proc = self.run(["shell", "input", "tap", str(int(x)), str(int(y))])
        return proc.returncode == 0

    def swipe(self, x1: int, y1: int, x2: int, y2: int, duration_ms: int = 150) -> bool:
        proc = self.run(["shell", "input", "swipe", str(int(x1)), str(int(y1)), str(int(x2)), str(int(y2)), str(int(duration_ms))])
        return proc.returncode == 0

    def screencap(self) -> Optional[np.ndarray]:
        if cv2 is None:
            return None
        proc = self.run(["exec-out", "screencap", "-p"])
        if proc.returncode != 0 or not proc.stdout:
            return None
        image_data = np.frombuffer(proc.stdout, dtype=np.uint8)
        frame = cv2.imdecode(image_data, cv2.IMREAD_COLOR)
        return frame


class ADBVisionEngine(VisionEngine):
    def __init__(self, device: Optional[str] = None, wifi_host: Optional[str] = None, screenshots_dir: str = "screenshots", fast_actions: bool = False):
        super().__init__(monitor=1, screenshots_dir=screenshots_dir, fast_actions=fast_actions)
        self.adb = ADBController(device=device, wifi_host=wifi_host)

    def capture_frame(self) -> Optional[np.ndarray]:
        return self.adb.screencap()

    def _get_pyautogui(self):
        raise RuntimeError("ADB mode does not use pyautogui")

    def click(self, point: Tuple[int, int]) -> None:
        self.adb.tap(point[0], point[1])

    def perform_action(self, action_name: str, point: Tuple[int, int], screen_size: Optional[Tuple[int, int]] = None) -> bool:
        if action_name in {"swipe", "drag"}:
            width = screen_size[0] if screen_size and screen_size[0] else 1280
            height = screen_size[1] if screen_size and screen_size[1] else 720
            swipe_end = (min(width - 1, point[0] + 120), max(0, point[1] - 80))
            duration = 50 if self.fast_actions else 150
            return self.adb.swipe(point[0], point[1], swipe_end[0], swipe_end[1], duration_ms=duration)

        if action_name.startswith("wait"):
            match = re.search(r"wait(?:\s*[:=]\s*)?(\d+(?:\.\d+)?)", action_name)
            if match:
                time.sleep(float(match.group(1)))
            else:
                time.sleep(0.3)
            return True

        return self.adb.tap(point[0], point[1])


class VideoVisionEngine(VisionEngine):
    def __init__(self, video_path: str, screenshots_dir: str = "screenshots"):
        if cv2 is None:
            raise RuntimeError("OpenCV is required for video capture mode")
        self.video_path = video_path
        self.screenshots_dir = screenshots_dir
        os.makedirs(self.screenshots_dir, exist_ok=True)
        self.cap = cv2.VideoCapture(video_path)
        if not self.cap.isOpened():
            raise RuntimeError(f"Unable to open video file: {video_path}")
        self.kernel = np.ones((5, 5), np.uint8)

    def capture_frame(self) -> Optional[np.ndarray]:
        ret, frame = self.cap.read()
        if not ret or frame is None:
            return None
        return frame

    def __del__(self):
        try:
            if hasattr(self, "cap") and self.cap is not None:
                self.cap.release()
        except Exception:
            pass


class RemoteSync:
    def __init__(self, base_url: Optional[str] = None, token: Optional[str] = None):
        self.base_url = base_url or os.getenv("REMOTE_SYNC_URL")
        self.token = token or os.getenv("REMOTE_SYNC_TOKEN")

    def push(self, resource_name: str, status: str, details: str) -> None:
        if not self.base_url:
            return
        payload = {"resource_name": resource_name, "status": status, "details": details}
        headers = {"Content-Type": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        try:
            requests.post(self.base_url, json=payload, headers=headers, timeout=5)
        except Exception as exc:
            print(f"Remote sync failed: {exc}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Albion Online helper with priority selection and screenshots")
    parser.add_argument("--resource", default=None, help="Specific resource name to target")
    parser.add_argument("--once", action="store_true", help="Run one detection cycle")
    parser.add_argument("--db", default="assistant.db", help="Path to local SQLite DB")
    parser.add_argument("--ai-db", default="ai_model.db", help="Path to AI memory SQLite DB")
    parser.add_argument("--ai-memory-backup", default=None, help="Path to backup AI memory SQLite DB")
    parser.add_argument("--ai-memory-restore", default=None, help="Path to restore AI memory from backup SQLite DB")
    parser.add_argument("--ai-memory-export-json", default=None, help="Export AI memory to JSON file")
    parser.add_argument("--ai-memory-import-json", default=None, help="Import AI memory from JSON file")
    parser.add_argument("--config", default="albion_resources.json", help="Path to JSON resource definitions")
    parser.add_argument("--monitor", type=int, default=1, help="MSS monitor index")
    parser.add_argument("--device", default="poco_f5", help="Screen preset name, e.g. poco_f5")
    parser.add_argument("--video", default=None, help="Path to video file for video capture mode")
    parser.add_argument("--mode", default="no-root", choices=["no-root", "adb", "adb-wifi", "video"], help="Execution mode: no-root, adb, adb-wifi, or video")
    parser.add_argument("--adb", action="store_true", help="Use ADB mode for Android device control")
    parser.add_argument("--adb-device", default=None, help="ADB device serial number")
    parser.add_argument("--adb-wifi", default=None, help="ADB WiFi host:port for wireless debugging")
    parser.add_argument("--interval", type=float, default=0.5, help="Loop interval in seconds")
    parser.add_argument("--fast-actions", action="store_true", help="Use faster cursor movement for actions")
    parser.add_argument("--screenshots", action="store_true", help="Save screenshots for each detection")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    db = LocalResourceDB(args.db)
    db.seed_defaults()
    if args.config and os.path.exists(args.config):
        db.import_from_json(args.config)

    if args.video or args.mode == "video":
        vision = VideoVisionEngine(video_path=args.video or "", screenshots_dir="screenshots", fast_actions=args.fast_actions)
    elif args.mode == "adb-wifi" or args.adb_wifi:
        wifi_host = args.adb_wifi if args.adb_wifi else args.adb_device
        vision = ADBVisionEngine(device=wifi_host, wifi_host=wifi_host, screenshots_dir="screenshots", fast_actions=args.fast_actions)
    elif args.mode == "adb" or args.adb:
        vision = ADBVisionEngine(device=args.adb_device, screenshots_dir="screenshots", fast_actions=args.fast_actions)
    else:
        vision = NoRootVisionEngine(monitor=args.monitor, fast_actions=args.fast_actions)

    sync = RemoteSync()
    memory = AgentMemory("agent_memory.db")
    decision_engine = DecisionEngine(memory)
    ai_db = AIModelDB(args.ai_db)
    ai_model = SimpleAIModel(ai_db)

    if args.ai_memory_restore:
        ai_db.restore(args.ai_memory_restore)
        print(f"Restored AI memory from {args.ai_memory_restore}")
    if args.ai_memory_import_json:
        ai_db.import_json(args.ai_memory_import_json)
        print(f"Imported AI memory from {args.ai_memory_import_json}")

    preset = get_screen_preset(args.device)
    print(f"Using screen preset: {preset['name']} ({preset['resolution']}, {preset['aspect_ratio']})")
    print("Loaded resources:")
    for resource in db.list_resources():
        print(f" - {resource['name']} (priority={resource['priority']}): {resource['description']}")

    print("Starting priority loop. Press Ctrl+C to stop.")
    resources = db.all_resources()
    if args.resource:
        resources = [r for r in resources if r["name"] == args.resource]
    resources = preprocess_resources(resources)
    if not resources:
        print("No resources configured")
        return 1

    while True:
        frame = vision.capture_frame()
        if frame is None:
            print("No more frames available")
            break

        chosen = decision_engine.choose_resource(resources, ai_model=ai_model)
        if chosen is None:
            print("No resources configured")
            break

        detection = vision.find_resource(frame, chosen)
        if detection:
            point, hsv_mean = detection
            print(f"AI chose {chosen['name']} at {point} with HSV {hsv_mean}")
            if args.screenshots:
                vision.save_frame(frame, chosen['name'])
            action_name = resolve_action_name(chosen)
            action_spec = chosen.get("action")
            if isinstance(action_spec, str) and ("->" in action_spec or ";" in action_spec or "|" in action_spec):
                action_ok = vision.execute_sequence(action_spec, point, screen_size=(frame.shape[1], frame.shape[0]))
                action_label = action_spec
            else:
                action_ok = vision.perform_action(action_name, point, screen_size=(frame.shape[1], frame.shape[0]))
                action_label = action_name
            if action_ok:
                print(f"Executed action: {action_label}")
            else:
                vision.click(point)
            db.log_event(chosen['name'], "detected", json.dumps({"point": point, "hsv_mean": hsv_mean, "action": action_label}))
            db.record_learning(chosen['name'], hsv_mean, success=True)
            ai_model.train_from_sample(chosen['name'], 'screen', 'capture', hsv_mean, True)
            sync.push(chosen['name'], "detected", json.dumps({"point": point, "hsv_mean": hsv_mean}))
        else:
            print(f"{chosen['name']} not found")
            db.log_event(chosen['name'], "missed", "No resource found")

        if args.once:
            break
        time.sleep(max(0.1, args.interval))

    if args.ai_memory_backup:
        ai_db.backup(args.ai_memory_backup)
        print(f"Backed up AI memory to {args.ai_memory_backup}")
    if args.ai_memory_export_json:
        ai_db.export_json(args.ai_memory_export_json)
        print(f"Exported AI memory to {args.ai_memory_export_json}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
