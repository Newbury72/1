import json
import os
import shutil
import sqlite3
import time
from typing import Optional, Tuple, Dict, Any

import numpy as np
import requests

try:
    import cv2
except Exception:
    cv2 = None


class AIModelDB:
    def __init__(self, db_path: str = "ai_model.db"):
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._init_db()

    def _init_db(self) -> None:
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS ai_weights (
                resource_name TEXT PRIMARY KEY,
                score REAL NOT NULL DEFAULT 0,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS ai_samples (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                resource_name TEXT NOT NULL,
                source_type TEXT NOT NULL,
                source_value TEXT NOT NULL,
                feature_hsv TEXT,
                success INTEGER NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS ai_activity (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_type TEXT NOT NULL,
                event_source TEXT,
                resource_name TEXT,
                detail TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        self.conn.commit()

    def record_training_sample(
        self,
        resource_name: str,
        source_type: str,
        source_value: str,
        hsv_value: Optional[Tuple[int, int, int]],
        success: bool,
    ) -> None:
        feature_hsv = json.dumps(list(hsv_value)) if hsv_value else None
        self.conn.execute(
            "INSERT INTO ai_samples (resource_name, source_type, source_value, feature_hsv, success) VALUES (?, ?, ?, ?, ?)",
            (resource_name, source_type, source_value, feature_hsv, 1 if success else 0),
        )
        self.conn.commit()
        self._update_weight(resource_name, 0.25 if success else -0.1)
        self.log_activity("training_sample", source_type, resource_name, f"success={success}")

    def _update_weight(self, resource_name: str, delta: float) -> None:
        existing = self.conn.execute(
            "SELECT score FROM ai_weights WHERE resource_name = ?",
            (resource_name,),
        ).fetchone()
        if existing:
            new_score = float(existing["score"]) + delta
            self.conn.execute(
                "UPDATE ai_weights SET score = ?, updated_at = ? WHERE resource_name = ?",
                (new_score, time.strftime("%Y-%m-%d %H:%M:%S"), resource_name),
            )
        else:
            new_score = delta
            self.conn.execute(
                "INSERT INTO ai_weights (resource_name, score, updated_at) VALUES (?, ?, ?)",
                (resource_name, new_score, time.strftime("%Y-%m-%d %H:%M:%S")),
            )
        self.conn.commit()

    def get_weight(self, resource_name: str) -> float:
        row = self.conn.execute(
            "SELECT score FROM ai_weights WHERE resource_name = ?",
            (resource_name,),
        ).fetchone()
        return float(row["score"]) if row else 0.0

    def get_samples(self, limit: int = 50):
        rows = self.conn.execute(
            "SELECT resource_name, source_type, source_value, feature_hsv, success, created_at FROM ai_samples ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_summary(self) -> Dict[str, Any]:
        rows = self.conn.execute(
            "SELECT resource_name, COUNT(*) as count, SUM(success) as successes FROM ai_samples GROUP BY resource_name"
        ).fetchall()
        return {row["resource_name"]: {"count": int(row["count"]), "successes": int(row["successes"])} for row in rows}

    def get_weights(self) -> list[Dict[str, Any]]:
        rows = self.conn.execute("SELECT resource_name, score, updated_at FROM ai_weights ORDER BY score DESC").fetchall()
        return [dict(r) for r in rows]

    def get_activity(self, limit: int = 20) -> list[Dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT event_type, event_source, resource_name, detail, created_at FROM ai_activity ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]

    def log_activity(
        self,
        event_type: str,
        event_source: Optional[str] = None,
        resource_name: Optional[str] = None,
        detail: Optional[str] = None,
    ) -> None:
        self.conn.execute(
            "INSERT INTO ai_activity (event_type, event_source, resource_name, detail) VALUES (?, ?, ?, ?)",
            (event_type, event_source, resource_name, detail),
        )
        self.conn.commit()

    def backup(self, backup_path: str) -> None:
        self.conn.commit()
        self.conn.close()
        shutil.copyfile(self.db_path, backup_path)
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.log_activity("backup", backup_path, None, "AI memory backup created")

    def restore(self, source_path: str) -> None:
        if not os.path.exists(source_path):
            raise FileNotFoundError(f"Source AI memory file not found: {source_path}")
        self.conn.close()
        shutil.copyfile(source_path, self.db_path)
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.log_activity("restore", source_path, None, "AI memory restored")

    def export_json(self, json_path: str) -> None:
        weights = [dict(row) for row in self.conn.execute("SELECT resource_name, score, updated_at FROM ai_weights").fetchall()]
        samples = [dict(row) for row in self.conn.execute("SELECT resource_name, source_type, source_value, feature_hsv, success, created_at FROM ai_samples").fetchall()]
        data = {"weights": weights, "samples": samples}
        with open(json_path, "w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2, ensure_ascii=False)
        self.log_activity("export_json", json_path, None, "AI memory exported to JSON")

    def import_json(self, json_path: str) -> None:
        if not os.path.exists(json_path):
            raise FileNotFoundError(f"AI JSON file not found: {json_path}")
        with open(json_path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        weights = data.get("weights", [])
        samples = data.get("samples", [])
        for weight in weights:
            self.conn.execute(
                "INSERT OR REPLACE INTO ai_weights (resource_name, score, updated_at) VALUES (?, ?, ?)",
                (weight["resource_name"], float(weight["score"]), weight.get("updated_at", time.strftime("%Y-%m-%d %H:%M:%S"))),
            )
        for sample in samples:
            self.conn.execute(
                "INSERT INTO ai_samples (resource_name, source_type, source_value, feature_hsv, success, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (
                    sample["resource_name"],
                    sample["source_type"],
                    sample["source_value"],
                    sample.get("feature_hsv"),
                    int(sample["success"]),
                    sample.get("created_at", time.strftime("%Y-%m-%d %H:%M:%S")),
                ),
            )
        self.conn.commit()
        self.log_activity("import_json", json_path, None, "AI memory imported from JSON")


class SimpleAIModel:
    def __init__(self, db: AIModelDB):
        self.db = db

    def predict(self, resource_name: str, base_score: float = 0.0) -> float:
        return base_score + self.db.get_weight(resource_name)

    def train_from_sample(
        self,
        resource_name: str,
        source_type: str,
        source_value: str,
        hsv_value: Optional[Tuple[int, int, int]],
        success: bool,
    ) -> None:
        self.db.record_training_sample(resource_name, source_type, source_value, hsv_value, success)

    def train_from_remote_url(self, remote_url: str, resource_name: str) -> None:
        if not remote_url:
            return
        try:
            response = requests.get(remote_url, timeout=5)
            data = response.json()
            if isinstance(data, dict) and "samples" in data and isinstance(data["samples"], list):
                for entry in data["samples"]:
                    if not isinstance(entry, dict):
                        continue
                    hsv_value = None
                    if "hsv" in entry and isinstance(entry["hsv"], list) and len(entry["hsv"]) == 3:
                        hsv_value = tuple(int(v) for v in entry["hsv"])
                    success = bool(entry.get("success", True))
                    label = entry.get("resource_name", resource_name)
                    self.train_from_sample(label, "remote", remote_url, hsv_value, success)
                return
        except Exception:
            pass
        self.train_from_sample(resource_name, "remote", remote_url, None, True)

    def train_from_video(self, video_path: str, resource_name: str, sample_count: int = 3) -> None:
        if cv2 is None:
            raise RuntimeError("OpenCV is required for video training")
        if not os.path.exists(video_path):
            raise FileNotFoundError(f"Video path not found: {video_path}")

        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            raise RuntimeError(f"Unable to open video file: {video_path}")

        recorded = 0
        while recorded < sample_count:
            ret, frame = cap.read()
            if not ret or frame is None:
                break
            hsv_value = self._extract_hsv_mean(frame)
            self.train_from_sample(resource_name, "video", video_path, hsv_value, True)
            recorded += 1
        cap.release()

    @staticmethod
    def _extract_hsv_mean(frame: Any) -> Tuple[int, int, int]:
        if cv2 is None:
            return (0, 0, 0)
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        mean_hsv = cv2.mean(hsv)
        return (int(mean_hsv[0]), int(mean_hsv[1]), int(mean_hsv[2]))
