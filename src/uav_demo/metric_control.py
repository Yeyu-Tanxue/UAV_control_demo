"""Bounded body commands from metric visual track-relative errors."""
import math
from dataclasses import dataclass
from .vision_control import BodyVelocityCommand


@dataclass(frozen=True)
class MetricControlConfig:
    lateral_gain: float = .55
    heading_gain: float = .65
    max_right_m_s: float = .12
    max_yaw_deg_s: float = 6.
    forward_m_s: float = .10
    aligned_lateral_m: float = .07
    aligned_heading_deg: float = 2.

    def __post_init__(self):
        if not all(math.isfinite(v) and v>0 for v in vars(self).values()):
            raise ValueError('positive finite control configuration required')


def metric_command(estimate, config=MetricControlConfig(), allow_forward=False):
    if estimate is None:
        return BodyVelocityCommand(0.,0.,0.)
    lateral=estimate.lateral_error_m
    heading=estimate.heading_error_deg
    if not math.isfinite(lateral) or not math.isfinite(heading):
        return BodyVelocityCommand(0.,0.,0.)
    if abs(lateral)>.7 or abs(heading)>15:
        return BodyVelocityCommand(0.,0.,0.)
    right=max(-config.max_right_m_s,min(config.max_right_m_s,config.lateral_gain*lateral))
    yaw=max(-config.max_yaw_deg_s,min(config.max_yaw_deg_s,config.heading_gain*heading))
    aligned=abs(lateral)<config.aligned_lateral_m and abs(heading)<config.aligned_heading_deg
    forward=config.forward_m_s if allow_forward and aligned else 0.
    return BodyVelocityCommand(forward,right,yaw)
