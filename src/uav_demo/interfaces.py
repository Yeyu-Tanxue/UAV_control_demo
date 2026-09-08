from dataclasses import dataclass
from typing import Awaitable, Callable, Protocol


SleepFn = Callable[[float], Awaitable[None]]


@dataclass(frozen=True, slots=True)
class RecognitionResult:
    accepted: bool
    label: str
    confidence: float


class Recognizer(Protocol):
    async def recognize(self, cycle: int) -> RecognitionResult: ...


class FlightController(Protocol):
    async def connect(self, timeout_s: float) -> None: ...

    async def takeoff(self, altitude_m: float, timeout_s: float) -> None: ...

    async def start_offboard_hold(self) -> None: ...

    async def hold(self) -> None: ...

    async def move_forward(self, speed_m_s: float) -> None: ...

    async def stop_offboard(self) -> None: ...

    async def land(self, timeout_s: float) -> None: ...

    async def safe_stop_and_land(self, timeout_s: float) -> None: ...
