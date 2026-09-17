"""Vision-only hover-recognize-control mission loop."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from enum import Enum, auto

from .interfaces import FlightController, Recognizer, SleepFn
from .vision_control import (
    RailEstimate,
    VisionControlConfig,
    map_estimate_to_command,
)


class VisualMissionState(Enum):
    IDLE = auto()
    CONNECTING = auto()
    TAKING_OFF = auto()
    HOVERING = auto()
    RECOGNIZING = auto()
    APPLYING_VISION_COMMAND = auto()
    LANDING = auto()
    COMPLETE = auto()
    FAILED = auto()


class VisionLost(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class VisualMissionConfig:
    control_steps: int = 8
    takeoff_altitude_m: float = 2.0
    command_duration_s: float = 0.75
    settle_time_s: float = 0.50
    retry_hold_s: float = 0.50
    max_consecutive_misses: int = 3
    connection_timeout_s: float = 30.0
    takeoff_timeout_s: float = 30.0
    landing_timeout_s: float = 30.0

    def __post_init__(self) -> None:
        if not 1 <= self.control_steps <= 100:
            raise ValueError("control_steps must be between 1 and 100")
        if not 0.5 <= self.takeoff_altitude_m <= 5.0:
            raise ValueError(
                "takeoff_altitude_m must be between 0.5 and 5.0"
            )
        if not 0.1 <= self.command_duration_s <= 2.0:
            raise ValueError(
                "command_duration_s must be between 0.1 and 2.0"
            )
        if not 0.0 <= self.settle_time_s <= 10.0:
            raise ValueError("settle_time_s must be between 0 and 10")
        if not 1 <= self.max_consecutive_misses <= 10:
            raise ValueError(
                "max_consecutive_misses must be between 1 and 10"
            )


class VisualMissionRunner:
    """Move only after local vision produces a valid rail estimate."""

    def __init__(
        self,
        controller: FlightController,
        recognizer: Recognizer,
        mission_config: VisualMissionConfig,
        control_config: VisionControlConfig,
        sleep: SleepFn = asyncio.sleep,
    ) -> None:
        self._controller = controller
        self._recognizer = recognizer
        self._mission_config = mission_config
        self._control_config = control_config
        self._sleep = sleep
        self._logger = logging.getLogger(__name__)
        self.state = VisualMissionState.IDLE
        self.history = [self.state]

    def _transition(self, state: VisualMissionState) -> None:
        self.state = state
        self.history.append(state)
        self._logger.info("Visual mission state -> %s", state.name)

    async def run(self) -> None:
        try:
            self._transition(VisualMissionState.CONNECTING)
            await self._controller.connect(
                self._mission_config.connection_timeout_s
            )
            self._transition(VisualMissionState.TAKING_OFF)
            await self._controller.takeoff(
                self._mission_config.takeoff_altitude_m,
                self._mission_config.takeoff_timeout_s,
            )
            await self._controller.start_offboard_hold()
            await self._controller.hold()
            await self._sleep(self._mission_config.settle_time_s)

            completed_steps = 0
            consecutive_misses = 0
            while completed_steps < self._mission_config.control_steps:
                cycle = completed_steps + 1
                self._transition(VisualMissionState.HOVERING)
                await self._controller.hold()
                self._transition(VisualMissionState.RECOGNIZING)
                result = await self._recognizer.recognize(cycle)
                if not result.accepted:
                    consecutive_misses += 1
                    await self._controller.hold()
                    if (
                        consecutive_misses
                        >= self._mission_config.max_consecutive_misses
                    ):
                        raise VisionLost(
                            "local rail recognition failed "
                            f"{consecutive_misses} consecutive times"
                        )
                    await self._sleep(
                        self._mission_config.retry_hold_s
                    )
                    continue

                consecutive_misses = 0
                estimate = RailEstimate(
                    confidence=result.confidence,
                    lateral_error_norm=result.lateral_error_norm,
                    heading_error_deg=result.heading_error_deg,
                    valid_rows=result.valid_rows,
                    near_center_x_norm=(
                        0.5 + 0.5 * result.lateral_error_norm
                    ),
                    far_center_x_norm=0.5,
                    near_width_norm=0.0,
                    geometry_quality=1.0,
                    source_id=result.source_id,
                )
                command = map_estimate_to_command(
                    estimate,
                    self._control_config,
                )
                self._logger.info(
                    "Vision command %d: forward=%.3f right=%+.3f "
                    "yaw=%+.2f",
                    cycle,
                    command.forward_m_s,
                    command.right_m_s,
                    command.yaw_rate_deg_s,
                )
                self._transition(
                    VisualMissionState.APPLYING_VISION_COMMAND
                )
                await self._controller.set_body_velocity(
                    command.forward_m_s,
                    command.right_m_s,
                    command.yaw_rate_deg_s,
                )
                await self._sleep(
                    self._mission_config.command_duration_s
                )
                await self._controller.hold()
                completed_steps += 1
                await self._sleep(self._mission_config.settle_time_s)

            self._transition(VisualMissionState.LANDING)
            await self._controller.stop_offboard()
            await self._controller.land(
                self._mission_config.landing_timeout_s
            )
            self._transition(VisualMissionState.COMPLETE)
        except BaseException:
            self._transition(VisualMissionState.FAILED)
            self._logger.exception(
                "Visual mission failed; requesting hold and landing"
            )
            cleanup_task = asyncio.create_task(
                self._controller.safe_stop_and_land(
                    self._mission_config.landing_timeout_s
                )
            )
            while not cleanup_task.done():
                try:
                    await asyncio.shield(cleanup_task)
                except asyncio.CancelledError:
                    continue
                except Exception:
                    self._logger.exception(
                        "Automatic safety landing also failed"
                    )
                    break
            raise
