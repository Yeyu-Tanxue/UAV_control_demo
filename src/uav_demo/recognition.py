import logging

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
