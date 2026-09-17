import asyncio
import json
import logging
import shutil
import time
from datetime import datetime
from pathlib import Path

from .interfaces import RecognitionResult, SleepFn


class TimedMockRecognizer:
    """Temporary recognizer used before the Gazebo camera/CNN is connected."""

    def __init__(self, delay_s: float, sleep: SleepFn) -> None:
        self._delay_s = delay_s
        self._sleep = sleep
        self._logger = logging.getLogger(__name__)

    async def recognize(self, cycle: int) -> RecognitionResult:
        self._logger.info(
            "Cycle %d: mock recognition started (configured delay %.1f s)",
            cycle,
            self._delay_s,
        )
        await self._sleep(self._delay_s)
        result = RecognitionResult(
            accepted=True,
            label="mock_track_clear",
            confidence=1.0,
        )
        self._logger.info(
            "Cycle %d: mock recognition accepted: %s (%.2f)",
            cycle,
            result.label,
            result.confidence,
        )
        return result


class GazeboCameraRecognizer:
    """Copy Gazebo-native camera files created during each recognition hold."""

    def __init__(
        self,
        duration_s: float,
        source_dir: Path,
        output_root: Path,
        sleep: SleepFn = asyncio.sleep,
    ) -> None:
        self._duration_s = duration_s
        self._source_dir = source_dir
        self._sleep = sleep
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.output_dir = output_root.resolve() / timestamp
        self._logger = logging.getLogger(__name__)

    async def recognize(self, cycle: int) -> RecognitionResult:
        cycle_dir = self.output_dir / f"cycle_{cycle:02d}"
        cycle_dir.mkdir(parents=True, exist_ok=True)
        started_ns = time.time_ns()
        self._logger.info(
            "Cycle %d: selecting Gazebo-native frames for %.1f s into %s",
            cycle,
            self._duration_s,
            cycle_dir,
        )
        await self._sleep(self._duration_s)
        ended_ns = time.time_ns()

        # Let the camera finish writing the final frame without including
        # frames created after the recognition window.
        await self._sleep(0.25)
        candidates = sorted(
            path
            for pattern in ("*.png", "*.jpg", "*.jpeg")
            for path in self._source_dir.glob(pattern)
            if started_ns <= path.stat().st_mtime_ns <= ended_ns
            and path.stat().st_size > 0
        )
        frames: list[dict[str, object]] = []
        for index, source in enumerate(candidates, start=1):
            destination = cycle_dir / f"frame_{index:04d}{source.suffix.lower()}"
            shutil.copy2(source, destination)
            frames.append(
                {
                    "file": destination.name,
                    "source_file": source.name,
                    "captured_at": datetime.fromtimestamp(
                        source.stat().st_mtime
                    ).isoformat(timespec="milliseconds"),
                }
            )

        metadata = {
            "source_dir": str(self._source_dir),
            "duration_s": self._duration_s,
            "frame_count": len(frames),
            "frames": frames,
        }
        (cycle_dir / "metadata.json").write_text(
            json.dumps(metadata, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        if not frames:
            raise RuntimeError(
                f"Gazebo saved no camera frames during recognition cycle {cycle}"
            )

        self._logger.info(
            "Cycle %d: saved %d recognition frames to %s",
            cycle,
            len(frames),
            cycle_dir,
        )
        return RecognitionResult(
            accepted=True,
            label="gazebo_frames_saved",
            confidence=1.0,
        )