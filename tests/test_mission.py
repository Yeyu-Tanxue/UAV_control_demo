import asyncio
import unittest

from uav_demo.config import MissionConfig
from uav_demo.interfaces import RecognitionResult
from uav_demo.mission import MissionRunner, MissionState, RecognitionRejected


class FakeController:
    def __init__(self) -> None:
        self.events: list[str] = []

    async def connect(self, timeout_s: float) -> None:
        self.events.append("connect")

    async def takeoff(self, altitude_m: float, timeout_s: float) -> None:
        self.events.append(f"takeoff:{altitude_m}")

    async def start_offboard_hold(self) -> None:
        self.events.append("offboard")

    async def hold(self) -> None:
        self.events.append("hold")

    async def move_forward(self, speed_m_s: float) -> None:
        self.events.append(f"forward:{speed_m_s}")

    async def stop_offboard(self) -> None:
        self.events.append("stop")

    async def land(self, timeout_s: float) -> None:
        self.events.append("land")

    async def safe_stop_and_land(self, timeout_s: float) -> None:
        self.events.append("safe_land")


class BlockingSafetyController(FakeController):
    def __init__(self) -> None:
        super().__init__()
        self.safety_started = asyncio.Event()
        self.allow_safety_finish = asyncio.Event()

    async def safe_stop_and_land(self, timeout_s: float) -> None:
        self.events.append("safe_land_started")
        self.safety_started.set()
        await self.allow_safety_finish.wait()
        self.events.append("safe_land_finished")


class AcceptRecognizer:
    async def recognize(self, cycle: int) -> RecognitionResult:
        return RecognitionResult(True, "clear", 1.0)


class RejectRecognizer:
    async def recognize(self, cycle: int) -> RecognitionResult:
        return RecognitionResult(False, "unknown", 0.2)


class BlockingRecognizer:
    def __init__(self) -> None:
        self.started = asyncio.Event()

    async def recognize(self, cycle: int) -> RecognitionResult:
        self.started.set()
        await asyncio.Event().wait()
        raise AssertionError("blocking recognizer should have been cancelled")


class MissionRunnerTests(unittest.IsolatedAsyncioTestCase):
    async def test_two_complete_cycles_then_land(self) -> None:
        controller = FakeController()
        waits: list[float] = []

        async def fake_sleep(delay_s: float) -> None:
            waits.append(delay_s)
            await asyncio.sleep(0)

        config = MissionConfig(
            cycles=2,
            recognition_delay_s=0.0,
            forward_speed_m_s=0.2,
            forward_distance_m=0.5,
            settle_time_s=1.0,
        )
        runner = MissionRunner(
            controller,
            AcceptRecognizer(),
            config,
            fake_sleep,
        )

        await runner.run()

        self.assertEqual(runner.state, MissionState.COMPLETE)
        self.assertEqual(
            controller.events,
            [
                "connect",
                "takeoff:2.0",
                "offboard",
                "hold",
                "forward:0.2",
                "hold",
                "hold",
                "forward:0.2",
                "hold",
                "stop",
                "land",
            ],
        )
        self.assertEqual(waits, [2.5, 1.0, 2.5, 1.0])

    async def test_rejected_recognition_triggers_safety_landing(self) -> None:
        controller = FakeController()
        config = MissionConfig(cycles=1, recognition_delay_s=0.0)
        runner = MissionRunner(controller, RejectRecognizer(), config)

        with self.assertRaises(RecognitionRejected):
            await runner.run()

        self.assertEqual(runner.state, MissionState.FAILED)
        self.assertEqual(controller.events[-1], "safe_land")
        self.assertNotIn("forward:0.2", controller.events)

    async def test_cancellation_triggers_safety_landing(self) -> None:
        controller = BlockingSafetyController()
        recognizer = BlockingRecognizer()
        runner = MissionRunner(
            controller,
            recognizer,
            MissionConfig(cycles=1, recognition_delay_s=0.0),
        )

        task = asyncio.create_task(runner.run())
        await recognizer.started.wait()
        task.cancel()

        await controller.safety_started.wait()
        self.assertFalse(task.done())

        # A second operator interrupt must not cancel the landing cleanup.
        task.cancel()
        await asyncio.sleep(0)
        self.assertFalse(task.done())
        controller.allow_safety_finish.set()

        with self.assertRaises(asyncio.CancelledError):
            await task

        self.assertEqual(runner.state, MissionState.FAILED)
        self.assertEqual(controller.events[-1], "safe_land_finished")


if __name__ == "__main__":
    unittest.main()
