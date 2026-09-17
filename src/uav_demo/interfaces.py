from dataclasses import dataclass
from typing import Awaitable, Callable, Protocol


SleepFn = Callable[[float], Awaitable[None]]


@dataclass(frozen=True, slots=True)
class RecognitionResult:
    accepted: bool
    label: str
    confidence: float
    lateral_error_norm: float = 0.0
    heading_error_deg: float = 0.0
    valid_rows: int = 0
    source_id: str = ""


class Recognizer(Protocol):
    async def recognize(self, cycle: int) -> RecognitionResult: ...


class FlightController(Protocol):
    async def connect(self, timeout_s: float) -> None: ...

    async def takeoff(self, altitude_m: float, timeout_s: float) -> None: ...

    async def start_offboard_hold(self) -> None: ...

    async def hold(self) -> None: ...

    async def move_forward(self, speed_m_s: float) -> None: ...

    async def set_body_velocity(
        self,
        forward_m_s: float,
        right_m_s: float,
        yaw_rate_deg_s: float,
    ) -> None: ...

    async def stop_offboard(self) -> None: ...

    async def land(self, timeout_s: float) -> None: ...

    async def safe_stop_and_land(self, timeout_s: float) -> None: ...
