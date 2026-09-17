import asyncio
import unittest

from uav_demo.interfaces import RecognitionResult
from uav_demo.vision_control import VisionControlConfig
from uav_demo.visual_mission import (
    VisualMissionConfig,
    VisualMissionRunner,
    VisualMissionState,
    VisionLost,
)


class FakeVisionController:
    def __init__(self) -> None:
        self.events: list[object] = []

    async def connect(self, timeout_s: float) -> None:
        self.events.append("connect")

    async def takeoff(self, altitude_m: float, timeout_s: float) -> None:
        self.events.append("takeoff")

    async def start_offboard_hold(self) -> None:
        self.events.append("offboard")

    async def hold(self) -> None:
        self.events.append("hold")

    async def move_forward(self, speed_m_s: float) -> None:
        raise AssertionError("visual mission must not call legacy move_forward")

    async def set_body_velocity(
        self,
        forward_m_s: float,
        right_m_s: float,
        yaw_rate_deg_s: float,
    ) -> None:
        self.events.append(
            ("vision", forward_m_s, right_m_s, yaw_rate_deg_s)
        )

    async def stop_offboard(self) -> None:
        self.events.append("stop")

    async def land(self, timeout_s: float) -> None:
        self.events.append("land")

    async def safe_stop_and_land(self, timeout_s: float) -> None:
        self.events.append("safe_land")


class AcceptRailRecognizer:
    async def recognize(self, cycle: int) -> RecognitionResult:
        return RecognitionResult(
            accepted=True,
            label="local_rail_geometry",
            confidence=0.6,
            lateral_error_norm=-0.05,
            heading_error_deg=2.0,
            valid_rows=24,
        )


class RejectRailRecognizer:
    async def recognize(self, cycle: int) -> RecognitionResult:
        return RecognitionResult(False, "rail_not_stable", 0.0)


async def no_wait(_: float) -> None:
    await asyncio.sleep(0)


class VisualMissionTests(unittest.IsolatedAsyncioTestCase):
    async def test_every_motion_command_comes_from_vision(self) -> None:
        controller = FakeVisionController()
        runner = VisualMissionRunner(
            controller,
            AcceptRailRecognizer(),
            VisualMissionConfig(
                control_steps=2,
                settle_time_s=0.0,
            ),
            VisionControlConfig(),
            no_wait,
        )

        await runner.run()

        commands = [
            event
            for event in controller.events
            if isinstance(event, tuple) and event[0] == "vision"
        ]
        self.assertEqual(len(commands), 2)
        self.assertTrue(all(command[1] > 0 for command in commands))
        self.assertEqual(runner.state, VisualMissionState.COMPLETE)

    async def test_repeated_vision_loss_never_moves_and_lands(self) -> None:
        controller = FakeVisionController()
        runner = VisualMissionRunner(
            controller,
            RejectRailRecognizer(),
            VisualMissionConfig(
                control_steps=1,
                settle_time_s=0.0,
                retry_hold_s=0.0,
                max_consecutive_misses=2,
            ),
            VisionControlConfig(),
            no_wait,
        )

        with self.assertRaises(VisionLost):
            await runner.run()

        self.assertFalse(
            any(isinstance(event, tuple) for event in controller.events)
        )
        self.assertEqual(controller.events[-1], "safe_land")
        self.assertEqual(runner.state, VisualMissionState.FAILED)


if __name__ == "__main__":
    unittest.main()
