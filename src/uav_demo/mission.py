import asyncio
import logging
from enum import Enum, auto

from .config import MissionConfig
from .interfaces import FlightController, Recognizer, SleepFn


class MissionState(Enum):
    IDLE = auto()
    CONNECTING = auto()
    TAKING_OFF = auto()
    POSITIONING = auto()
    HOVERING = auto()
    RECOGNIZING = auto()
    MOVING_FORWARD = auto()
    SETTLING = auto()
    LANDING = auto()
    COMPLETE = auto()
    FAILED = auto()


class RecognitionRejected(RuntimeError):
    pass


class MissionRunner:
    def __init__(
        self,
        controller: FlightController,
        recognizer: Recognizer,
        config: MissionConfig,
        sleep: SleepFn = asyncio.sleep,
    ) -> None:
        self._controller = controller
        self._recognizer = recognizer
        self._config = config
        self._sleep = sleep
        self._logger = logging.getLogger(__name__)
        self.state = MissionState.IDLE
        self.history = [self.state]

    def _transition(self, state: MissionState) -> None:
        self.state = state
        self.history.append(state)
        self._logger.info("Mission state -> %s", state.name)

    async def run(self) -> None:
        try:
            self._transition(MissionState.CONNECTING)
            await self._controller.connect(self._config.connection_timeout_s)

            self._transition(MissionState.TAKING_OFF)
            await self._controller.takeoff(
                self._config.takeoff_altitude_m,
                self._config.takeoff_timeout_s,
            )
            await self._controller.start_offboard_hold()

            if self._config.approach_distance_m > 0:
                self._transition(MissionState.POSITIONING)
                await self._controller.move_forward(self._config.forward_speed_m_s)
                await self._sleep(self._config.approach_duration_s)
                self._transition(MissionState.SETTLING)
                await self._controller.hold()
                await self._sleep(self._config.settle_time_s)

            for cycle in range(1, self._config.cycles + 1):
                self._transition(MissionState.HOVERING)
                await self._controller.hold()

                self._transition(MissionState.RECOGNIZING)
                result = await self._recognizer.recognize(cycle)
                if not result.accepted:
                    raise RecognitionRejected(
                        f"cycle {cycle} rejected recognition result: {result.label}"
                    )

                self._transition(MissionState.MOVING_FORWARD)
                await self._controller.move_forward(
                    self._config.forward_speed_m_s
                )
                await self._sleep(self._config.forward_duration_s)

                self._transition(MissionState.SETTLING)
                await self._controller.hold()
                await self._sleep(self._config.settle_time_s)

            self._transition(MissionState.LANDING)
            await self._controller.stop_offboard()
            await self._controller.land(self._config.landing_timeout_s)
            self._transition(MissionState.COMPLETE)
        except BaseException:
            self._transition(MissionState.FAILED)
            self._logger.exception("Mission failed; requesting hold and landing")
            cleanup_task = asyncio.create_task(
                self._controller.safe_stop_and_land(
                    self._config.landing_timeout_s
                )
            )
            while not cleanup_task.done():
                try:
                    await asyncio.shield(cleanup_task)
                except asyncio.CancelledError:
                    # A repeated Ctrl+C must not cancel the in-progress landing.
                    continue
                except Exception:
                    self._logger.exception("Automatic safety landing also failed")
                    break

            if cleanup_task.done() and not cleanup_task.cancelled():
                cleanup_error = cleanup_task.exception()
                if cleanup_error is not None:
                    self._logger.error(
                        "Automatic safety landing ended with an error",
                        exc_info=(
                            type(cleanup_error),
                            cleanup_error,
                            cleanup_error.__traceback__,
                        ),
                    )
            raise
