import asyncio
import unittest

from tests.test_mission import AcceptRecognizer, FakeController
from uav_demo.config import MissionConfig
from uav_demo.mission import MissionRunner, MissionState


class MissionPositioningTests(unittest.IsolatedAsyncioTestCase):
    async def test_positions_over_track_before_first_recognition(self) -> None:
        controller = FakeController()
        waits: list[float] = []

        async def fake_sleep(delay_s: float) -> None:
            waits.append(delay_s)
            await asyncio.sleep(0)

        runner = MissionRunner(
            controller,
            AcceptRecognizer(),
            MissionConfig(
                cycles=1,
                recognition_delay_s=0.0,
                forward_speed_m_s=0.2,
                approach_distance_m=2.0,
                forward_distance_m=0.5,
                settle_time_s=1.0,
            ),
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
                "forward:0.2",
                "hold",
                "hold",
                "forward:0.2",
                "hold",
                "stop",
                "land",
            ],
        )
        self.assertEqual(waits, [10.0, 1.0, 2.5, 1.0])
        self.assertLess(
            runner.history.index(MissionState.POSITIONING),
            runner.history.index(MissionState.RECOGNIZING),
        )


if __name__ == "__main__":
    unittest.main()
