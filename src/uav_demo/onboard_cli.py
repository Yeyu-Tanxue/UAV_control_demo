"""Command-line entry point for companion-computer visual control."""

from __future__ import annotations

import argparse
import asyncio
import logging
from collections.abc import Sequence
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MODEL = (
    REPO_ROOT
    / "output/training-runs/rail-segmentation"
    / "l4r_spring_yolo26n_sanity/weights/best.pt"
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Local camera -> local YOLO rail geometry -> PX4 body velocity"
        )
    )
    parser.add_argument(
        "--backend",
        choices=("dry-run", "mavsdk"),
        default="dry-run",
    )
    parser.add_argument("--confirm-sitl", action="store_true")
    parser.add_argument("--confirm-flight", action="store_true")
    parser.add_argument(
        "--system-address",
        default="udpin://0.0.0.0:14540",
    )
    parser.add_argument(
        "--camera-source",
        choices=("gazebo", "picamera2", "directory"),
        default="directory",
    )
    parser.add_argument(
        "--camera-source-dir",
        type=Path,
        default=Path("/tmp/uav_demo_camera"),
    )
    parser.add_argument("--model", type=Path, default=DEFAULT_MODEL)
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--imgsz", type=int, default=640)
    parser.add_argument("--confidence", type=float, default=0.15)
    parser.add_argument("--frames-per-decision", type=int, default=3)
    parser.add_argument("--min-valid-frames", type=int, default=2)
    parser.add_argument("--control-steps", type=int, default=8)
    parser.add_argument("--takeoff-altitude", type=float, default=2.0)
    parser.add_argument("--forward-speed", type=float, default=0.12)
    parser.add_argument("--command-duration", type=float, default=0.75)
    parser.add_argument("--settle-time", type=float, default=0.50)
    parser.add_argument("--max-consecutive-misses", type=int, default=3)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("captures/visual_control"),
    )
    parser.add_argument(
        "--dry-run-time-scale",
        type=float,
        default=0.0,
    )
    return parser


async def _run(
    args: argparse.Namespace,
    parser: argparse.ArgumentParser,
) -> None:
    if args.backend == "mavsdk" and not (
        args.confirm_sitl or args.confirm_flight
    ):
        parser.error(
            "--backend mavsdk requires --confirm-sitl or --confirm-flight"
        )
    if args.confirm_sitl and args.confirm_flight:
        parser.error("choose only one of --confirm-sitl and --confirm-flight")
    if args.backend == "dry-run" and (
        args.confirm_sitl or args.confirm_flight
    ):
        parser.error("confirmation flags are only valid with MAVSDK")
    if args.dry_run_time_scale < 0:
        parser.error("--dry-run-time-scale must be non-negative")
    if args.backend == "mavsdk" and args.dry_run_time_scale != 0:
        parser.error("--dry-run-time-scale is only valid with dry-run")
    if not args.model.exists():
        parser.error(f"local model does not exist: {args.model}")
    if args.camera_source in ("gazebo", "directory"):
        if not args.camera_source_dir.is_dir():
            parser.error(
                "camera source directory does not exist: "
                f"{args.camera_source_dir}"
            )

    from .backends.dry_run import DryRunController
    from .onboard_vision import (
        DirectoryFrameSource,
        GazeboSpoolFrameSource,
        LocalYoloRailDetector,
        OnboardRailRecognizer,
        Picamera2FrameSource,
    )
    from .vision_control import VisionControlConfig
    from .visual_mission import VisualMissionConfig, VisualMissionRunner

    if args.backend == "mavsdk":
        from .backends.mavsdk_px4 import MavsdkPx4Controller

        controller = MavsdkPx4Controller(args.system_address)
        sleep = asyncio.sleep
    else:
        controller = DryRunController()

        async def sleep(delay_s: float) -> None:
            await asyncio.sleep(delay_s * args.dry_run_time_scale)

    if args.camera_source == "picamera2":
        frame_source = Picamera2FrameSource()
    elif args.camera_source == "gazebo":
        frame_source = GazeboSpoolFrameSource(args.camera_source_dir)
    else:
        frame_source = DirectoryFrameSource(
            args.camera_source_dir,
            loop=True,
        )

    detector = LocalYoloRailDetector(
        args.model,
        confidence=args.confidence,
        image_size=args.imgsz,
        device=args.device,
    )
    recognizer = OnboardRailRecognizer(
        frame_source,
        detector,
        frames_per_decision=args.frames_per_decision,
        min_valid_frames=args.min_valid_frames,
        output_root=args.output_dir,
    )
    mission = VisualMissionRunner(
        controller,
        recognizer,
        VisualMissionConfig(
            control_steps=args.control_steps,
            takeoff_altitude_m=args.takeoff_altitude,
            command_duration_s=args.command_duration,
            settle_time_s=args.settle_time,
            max_consecutive_misses=args.max_consecutive_misses,
        ),
        VisionControlConfig(
            forward_speed_m_s=args.forward_speed,
        ),
        sleep,
    )
    try:
        await mission.run()
    finally:
        close = getattr(frame_source, "close", None)
        if close is not None:
            close()


def main(argv: Sequence[str] | None = None) -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    parser = _parser()
    args = parser.parse_args(argv)
    try:
        asyncio.run(_run(args, parser))
    except KeyboardInterrupt:
        logging.getLogger(__name__).warning("Interrupted by operator")
        raise SystemExit(130) from None


if __name__ == "__main__":
    main()
