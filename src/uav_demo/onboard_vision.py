"""Frame sources and local YOLO rail recognition for the companion computer."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from statistics import median
from typing import Any, Protocol

from .interfaces import RecognitionResult
from .vision_control import RailEstimate, RailMaskGeometry


@dataclass(frozen=True, slots=True)
class CapturedFrame:
    image: Any
    source_id: str
    timestamp_s: float | None = None
    clock: str = "unspecified"
    timestamp_quality: str = "unavailable"
    source_timestamp_s: float | None = None
    source_clock: str = "unspecified"


class FrameSource(Protocol):
    async def capture(self) -> CapturedFrame: ...


def _read_image(path: Path):
    import cv2

    image = cv2.imread(str(path))
    if image is None:
        raise RuntimeError(f"Could not decode camera frame: {path}")
    return image


class DirectoryFrameSource:
    """Deterministic local replay source used before live SITL/flight."""

    def __init__(self, source_dir: Path, loop: bool = False) -> None:
        patterns = ("*.png", "*.jpg", "*.jpeg")
        self._paths = sorted(
            path
            for pattern in patterns
            for path in source_dir.glob(pattern)
            if path.stat().st_size > 0
        )
        if not self._paths:
            raise ValueError(f"No images found in {source_dir}")
        self._loop = loop
        self._index = 0

    async def capture(self) -> CapturedFrame:
        if self._index >= len(self._paths):
            if not self._loop:
                raise RuntimeError("Replay source is exhausted")
            self._index = 0
        path = self._paths[self._index]
        self._index += 1
        image = await asyncio.to_thread(_read_image, path)
        return CapturedFrame(image=image, source_id=str(path))


class GazeboSpoolFrameSource:
    """Read the newest Gazebo frame locally; no image leaves this process."""

    def __init__(self, source_dir: Path, timeout_s: float = 3.0) -> None:
        self._source_dir = source_dir
        self._timeout_s = timeout_s
        self._last_mtime_ns = 0

    def _newest(self) -> Path | None:
        candidates = [
            path
            for pattern in ("*.png", "*.jpg", "*.jpeg")
            for path in self._source_dir.glob(pattern)
            if path.stat().st_size > 0
            and path.stat().st_mtime_ns > self._last_mtime_ns
        ]
        return max(
            candidates,
            key=lambda path: path.stat().st_mtime_ns,
            default=None,
        )

    async def capture(self) -> CapturedFrame:
        deadline = time.monotonic() + self._timeout_s
        last_decode_error: RuntimeError | None = None
        while time.monotonic() < deadline:
            path = self._newest()
            if path is None:
                await asyncio.sleep(0.05)
                continue
            try:
                image = await asyncio.to_thread(_read_image, path)
            except RuntimeError as exc:
                # Gazebo writes directly to the spool path. The newest file can
                # briefly exist before its PNG payload is complete, so do not
                # consume its timestamp until OpenCV can decode it.
                last_decode_error = exc
                await asyncio.sleep(0.05)
                continue
            mtime_ns = path.stat().st_mtime_ns
            self._last_mtime_ns = mtime_ns
            # Gazebo's image saver exposes host file-write time, not the
            # simulated exposure timestamp. Convert it to the host monotonic
            # clock so bracketing telemetry can be interpolated.
            stamp = time.monotonic() - max(
                0.0, (time.time_ns() - mtime_ns) / 1e9
            )
            return CapturedFrame(
                image=image,
                source_id=str(path),
                timestamp_s=stamp,
                clock="host_monotonic_approximate",
                timestamp_quality="gazebo_file_write_time",
            )
        detail = (
            f"; latest frame was incomplete ({last_decode_error})"
            if last_decode_error is not None
            else ""
        )
        raise TimeoutError(
            f"No decodable new Gazebo camera frame appeared in "
            f"{self._source_dir}{detail}"
        )


class Picamera2FrameSource:
    """Capture BGR frames directly from a Raspberry Pi CSI camera."""

    def __init__(self, width: int = 640, height: int = 480) -> None:
        try:
            from picamera2 import Picamera2
        except ImportError as exc:
            raise RuntimeError(
                "Picamera2 is not installed. Install the Raspberry Pi OS "
                "python3-picamera2 package."
            ) from exc
        camera = Picamera2()
        camera.configure(
            camera.create_video_configuration(
                main={"size": (width, height), "format": "BGR888"}
            )
        )
        camera.start()
        self._camera = camera

    async def capture(self) -> CapturedFrame:
        started = time.monotonic()
        image = await asyncio.to_thread(
            self._camera.capture_array,
            "main",
        )
        finished = time.monotonic()
        return CapturedFrame(
            image=image,
            source_id=f"picamera2:{time.time_ns()}",
            timestamp_s=(started + finished) / 2,
            clock="host_monotonic_approximate",
            timestamp_quality="capture_call_midpoint",
        )

    def close(self) -> None:
        self._camera.stop()


class LocalYoloRailDetector:
    """Run YOLO segmentation in this process on the companion computer."""

    def __init__(
        self,
        model_path: Path,
        confidence: float = 0.15,
        image_size: int = 640,
        device: str = "cpu",
        geometry: RailMaskGeometry | None = None,
    ) -> None:
        try:
            from ultralytics import YOLO
        except ImportError as exc:
            raise RuntimeError(
                "ultralytics is required for local rail recognition"
            ) from exc
        self._model = YOLO(str(model_path))
        self._confidence = confidence
        self._image_size = image_size
        self._device = device
        self._geometry = geometry or RailMaskGeometry()

    def detect(self, frame: CapturedFrame) -> RailEstimate | None:
        results = self._model.predict(
            source=frame.image,
            imgsz=self._image_size,
            conf=self._confidence,
            device=self._device,
            max_det=3,
            verbose=False,
        )
        if not results:
            return None
        result = results[0]
        if result.masks is None or result.boxes is None:
            return None

        candidates: list[RailEstimate] = []
        mask_count = min(len(result.masks.data), len(result.boxes))
        for index in range(mask_count):
            confidence = float(result.boxes.conf[index].item())
            mask = result.masks.data[index].detach().cpu().numpy()
            estimate = self._geometry.estimate(
                mask,
                confidence,
                frame.source_id,
            )
            if estimate is not None:
                candidates.append(estimate)
        return max(
            candidates,
            key=lambda item: (
                item.confidence * (0.5 + 0.5 * item.geometry_quality)
            ),
            default=None,
        )


class OnboardRailRecognizer:
    """Aggregate several locally inferred frames into one control observation."""

    def __init__(
        self,
        frame_source: FrameSource,
        detector: LocalYoloRailDetector,
        frames_per_decision: int = 3,
        min_valid_frames: int = 2,
        output_root: Path | None = None,
    ) -> None:
        if not 1 <= min_valid_frames <= frames_per_decision:
            raise ValueError(
                "min_valid_frames must be within frames_per_decision"
            )
        self._frame_source = frame_source
        self._detector = detector
        self._frames_per_decision = frames_per_decision
        self._min_valid_frames = min_valid_frames
        self._logger = logging.getLogger(__name__)
        self.output_dir: Path | None = None
        if output_root is not None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            self.output_dir = output_root.resolve() / timestamp

    async def recognize(self, cycle: int) -> RecognitionResult:
        estimates: list[RailEstimate] = []
        for _ in range(self._frames_per_decision):
            frame = await self._frame_source.capture()
            estimate = await asyncio.to_thread(
                self._detector.detect,
                frame,
            )
            if estimate is not None:
                estimates.append(estimate)

        accepted = len(estimates) >= self._min_valid_frames
        if not accepted:
            self._logger.warning(
                "Vision cycle %d rejected: %d/%d valid local detections",
                cycle,
                len(estimates),
                self._frames_per_decision,
            )
            return RecognitionResult(
                accepted=False,
                label="rail_not_stable",
                confidence=max(
                    (item.confidence for item in estimates),
                    default=0.0,
                ),
            )

        result = RecognitionResult(
            accepted=True,
            label="local_rail_geometry",
            confidence=float(
                median(item.confidence for item in estimates)
            ),
            lateral_error_norm=float(
                median(item.lateral_error_norm for item in estimates)
            ),
            heading_error_deg=float(
                median(item.heading_error_deg for item in estimates)
            ),
            valid_rows=int(
                median(item.valid_rows for item in estimates)
            ),
            source_id=estimates[-1].source_id,
        )
        self._logger.info(
            "Vision cycle %d local result: "
            "conf=%.3f lateral=%+.3f heading=%+.2f deg",
            cycle,
            result.confidence,
            result.lateral_error_norm,
            result.heading_error_deg,
        )
        if self.output_dir is not None:
            self.output_dir.mkdir(parents=True, exist_ok=True)
            record = {
                "cycle": cycle,
                "result": asdict(result),
                "frames": [asdict(item) for item in estimates],
            }
            with (self.output_dir / "decisions.jsonl").open(
                "a",
                encoding="utf-8",
            ) as handle:
                handle.write(
                    json.dumps(record, ensure_ascii=False) + "\n"
                )
        return result
