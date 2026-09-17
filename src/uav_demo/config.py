from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class MissionConfig:
    """Conservative limits for the first SITL-only demo."""

    cycles: int = 2
    takeoff_altitude_m: float = 2.0
    recognition_delay_s: float = 3.0
    forward_speed_m_s: float = 0.2
    approach_distance_m: float = 2.0
    forward_distance_m: float = 2.0
    settle_time_s: float = 2.0
    connection_timeout_s: float = 30.0
    takeoff_timeout_s: float = 30.0
    landing_timeout_s: float = 30.0

    def __post_init__(self) -> None:
        if not 1 <= self.cycles <= 20:
            raise ValueError("cycles must be between 1 and 20")
        if not 0.5 <= self.takeoff_altitude_m <= 5.0:
            raise ValueError("takeoff_altitude_m must be between 0.5 and 5.0")
        if not 0.0 <= self.recognition_delay_s <= 60.0:
            raise ValueError("recognition_delay_s must be between 0 and 60")
        if not 0.05 <= self.forward_speed_m_s <= 1.0:
            raise ValueError("forward_speed_m_s must be between 0.05 and 1.0")
        if not 0.0 <= self.approach_distance_m <= 5.0:
            raise ValueError("approach_distance_m must be between 0 and 5.0")
        if not 0.05 <= self.forward_distance_m <= 5.0:
            raise ValueError("forward_distance_m must be between 0.05 and 5.0")
        if not 0.0 <= self.settle_time_s <= 30.0:
            raise ValueError("settle_time_s must be between 0 and 30")
        for name in (
            "connection_timeout_s",
            "takeoff_timeout_s",
            "landing_timeout_s",
        ):
            if getattr(self, name) <= 0:
                raise ValueError(f"{name} must be positive")

    @property
    def forward_duration_s(self) -> float:
        return self.forward_distance_m / self.forward_speed_m_s

    @property
    def approach_duration_s(self) -> float:
        return self.approach_distance_m / self.forward_speed_m_s
