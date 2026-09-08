import logging


class DryRunController:
    """Logs flight commands without opening a MAVLink connection."""

    def __init__(self) -> None:
        self.events: list[str] = []
        self._logger = logging.getLogger(__name__)

    def _record(self, event: str) -> None:
        self.events.append(event)
        self._logger.info("DRY RUN: %s", event)

    async def connect(self, timeout_s: float) -> None:
        self._record(f"connect(timeout={timeout_s:.1f}s)")

    async def takeoff(self, altitude_m: float, timeout_s: float) -> None:
        self._record(
            f"arm_and_takeoff(altitude={altitude_m:.2f}m, timeout={timeout_s:.1f}s)"
        )

    async def start_offboard_hold(self) -> None:
        self._record("start_offboard_with_zero_velocity")

    async def hold(self) -> None:
        self._record("body_velocity(forward=0.00m/s)")

    async def move_forward(self, speed_m_s: float) -> None:
        self._record(f"body_velocity(forward={speed_m_s:.2f}m/s)")

    async def stop_offboard(self) -> None:
        self._record("stop_offboard")

    async def land(self, timeout_s: float) -> None:
        self._record(f"land(timeout={timeout_s:.1f}s)")

    async def safe_stop_and_land(self, timeout_s: float) -> None:
        self._record(f"safe_hold_stop_land(timeout={timeout_s:.1f}s)")
