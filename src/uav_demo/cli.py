import argparse
import asyncio
import logging
from collections.abc import Sequence

from .backends.dry_run import DryRunController
from .config import MissionConfig
from .mission import MissionRunner
from .recognition import TimedMockRecognizer


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="PX4 hover-recognize-forward demo (SITL only for now)"
    )
    parser.add_argument(
        "--backend",
        choices=("dry-run", "mavsdk"),
        default="dry-run",
        help="dry-run logs commands; mavsdk sends them to PX4 SITL",
    )
    parser.add_argument(
        "--confirm-sitl",
        action="store_true",
        help="required acknowledgement before the MAVSDK backend is enabled",
    )
    parser.add_argument(
        "--system-address",
        default="udpin://0.0.0.0:14540",
        help="MAVSDK connection address",
    )
    parser.add_argument("--cycles", type=int, default=2)
    parser.add_argument("--takeoff-altitude", type=float, default=2.0)
    parser.add_argument("--recognition-delay", type=float, default=3.0)
    parser.add_argument("--forward-speed", type=float, default=0.2)
    parser.add_argument("--forward-distance", type=float, default=0.5)
    parser.add_argument("--settle-time", type=float, default=2.0)
    parser.add_argument(
        "--dry-run-time-scale",
        type=float,
        default=0.0,
        help="multiply waits in dry-run mode; 0 runs immediately",
    )
    return parser


async def _run(args: argparse.Namespace, parser: argparse.ArgumentParser) -> None:
    if args.backend == "mavsdk" and not args.confirm_sitl:
        parser.error("--backend mavsdk requires --confirm-sitl")
    if args.dry_run_time_scale < 0:
        parser.error("--dry-run-time-scale must be non-negative")
    if args.backend == "mavsdk" and args.dry_run_time_scale != 0:
        parser.error("--dry-run-time-scale is only valid with the dry-run backend")

    config = MissionConfig(
        cycles=args.cycles,
        takeoff_altitude_m=args.takeoff_altitude,
        recognition_delay_s=args.recognition_delay,
        forward_speed_m_s=args.forward_speed,
        forward_distance_m=args.forward_distance,
        settle_time_s=args.settle_time,
    )

    if args.backend == "dry-run":
        controller = DryRunController()

        async def sleep(delay_s: float) -> None:
            await asyncio.sleep(delay_s * args.dry_run_time_scale)

    else:
        from .backends.mavsdk_px4 import MavsdkPx4Controller

        controller = MavsdkPx4Controller(args.system_address)
        sleep = asyncio.sleep

    recognizer = TimedMockRecognizer(config.recognition_delay_s, sleep)
    mission = MissionRunner(controller, recognizer, config, sleep)
    await mission.run()


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
