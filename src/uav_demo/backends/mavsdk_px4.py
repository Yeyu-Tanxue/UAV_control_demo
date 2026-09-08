import asyncio
import logging
from collections.abc import AsyncIterable, Callable
from typing import Any, TypeVar


T = TypeVar("T")


class MavsdkPx4Controller:
    """Narrow MAVSDK adapter for PX4 SITL.

    MAVSDK is imported lazily so dry-run mode and unit tests need no external
    package or running mavsdk_server.
    """

    def __init__(self, system_address: str) -> None:
        try:
            from mavsdk import System
            from mavsdk.offboard import OffboardError, VelocityBodyYawspeed
        except ImportError as exc:
            raise RuntimeError(
                "MAVSDK is not installed. Run ./scripts/setup_python.sh first."
            ) from exc

        self._VelocityBodyYawspeed = VelocityBodyYawspeed
        self._OffboardError = OffboardError
        self._drone = System()
        self._system_address = system_address
        self._logger = logging.getLogger(__name__)
        self._armed = False
        self._offboard_started = False

    async def _wait_for(
        self,
        stream: AsyncIterable[T],
        predicate: Callable[[T], bool],
        timeout_s: float,
        description: str,
    ) -> T:
        async def consume() -> T:
            async for item in stream:
                if predicate(item):
                    return item
            raise RuntimeError(f"telemetry stream ended while waiting for {description}")

        try:
            return await asyncio.wait_for(consume(), timeout=timeout_s)
        except TimeoutError as exc:
            raise TimeoutError(
                f"timed out after {timeout_s:.1f}s waiting for {description}"
            ) from exc

    async def connect(self, timeout_s: float) -> None:
        self._logger.info("Connecting to PX4 at %s", self._system_address)
        await self._drone.connect(system_address=self._system_address)
        await self._wait_for(
            self._drone.core.connection_state(),
            lambda state: state.is_connected,
            timeout_s,
            "PX4 connection",
        )
        self._logger.info("PX4 connected; waiting for global/home position")
        await self._wait_for(
            self._drone.telemetry.health(),
            lambda health: (
                health.is_global_position_ok and health.is_home_position_ok
            ),
            timeout_s,
            "global and home position estimates",
        )

    async def takeoff(self, altitude_m: float, timeout_s: float) -> None:
        await self._drone.action.set_takeoff_altitude(altitude_m)
        await self._drone.action.arm()
        self._armed = True
        self._logger.info("Armed; taking off to %.2f m", altitude_m)
        await self._drone.action.takeoff()
        minimum_altitude = max(0.5, altitude_m - 0.35)
        await self._wait_for(
            self._drone.telemetry.position(),
            lambda position: position.relative_altitude_m >= minimum_altitude,
            timeout_s,
            f"relative altitude >= {minimum_altitude:.2f} m",
        )

    def _velocity(self, forward_m_s: float) -> Any:
        return self._VelocityBodyYawspeed(forward_m_s, 0.0, 0.0, 0.0)

    async def start_offboard_hold(self) -> None:
        await self._drone.offboard.set_velocity_body(self._velocity(0.0))
        try:
            await self._drone.offboard.start()
        except self._OffboardError as exc:
            raise RuntimeError(f"PX4 rejected Offboard start: {exc}") from exc
        self._offboard_started = True
        self._logger.info("Offboard mode started with zero body velocity")

    async def hold(self) -> None:
        await self._drone.offboard.set_velocity_body(self._velocity(0.0))

    async def move_forward(self, speed_m_s: float) -> None:
        self._logger.info("Commanding %.2f m/s forward in body frame", speed_m_s)
        await self._drone.offboard.set_velocity_body(self._velocity(speed_m_s))

    async def stop_offboard(self) -> None:
        if not self._offboard_started:
            return
        try:
            await self._drone.offboard.stop()
        except self._OffboardError as exc:
            raise RuntimeError(f"PX4 rejected Offboard stop: {exc}") from exc
        finally:
            self._offboard_started = False

    async def land(self, timeout_s: float) -> None:
        if not self._armed:
            return
        self._logger.info("Landing")
        await self._drone.action.land()
        await self._wait_for(
            self._drone.telemetry.in_air(),
            lambda in_air: not in_air,
            timeout_s,
            "touchdown",
        )
        self._armed = False

    async def safe_stop_and_land(self, timeout_s: float) -> None:
        if self._offboard_started:
            try:
                await self.hold()
            except Exception:
                self._logger.exception("Could not send zero-velocity safety setpoint")
            try:
                await self.stop_offboard()
            except Exception:
                self._logger.exception("Could not stop Offboard mode")

        if not self._armed:
            return
        try:
            await self.land(timeout_s)
        except Exception:
            # Never disarm on a timeout: delayed telemetry does not prove that
            # the vehicle has touched down. PX4 keeps executing the Land command
            # and the operator must take over in QGC if necessary.
            self._logger.exception(
                "Landing was not confirmed; PX4 remains armed in Land mode. "
                "Take over in QGC and do not disarm until touchdown is confirmed."
            )
