"""Timestamped PX4 state and projection onto a horizontal ground plane.

Ground coordinates: origin below body, X heading-forward, Y right, Z down.
PX4 angles are FRD -> NED; yaw cancels in this heading-aligned ground frame.
Times must share one clock. Reception-time alignment is approximate only.
"""
from bisect import bisect_left
from dataclasses import dataclass
import math

import numpy as np

from .camera_geometry import CameraIntrinsics, CameraMount, _rpy_rotation


@dataclass(frozen=True)
class VehicleState:
    timestamp_s: float
    roll_rad: float
    pitch_rad: float
    yaw_rad: float
    body_agl_m: float
    height_source: str = "specified_ground_plane"
    clock: str = "host_monotonic_approximate"

    def __post_init__(self):
        if not all(math.isfinite(v) for v in (
            self.timestamp_s, self.roll_rad, self.pitch_rad,
            self.yaw_rad, self.body_agl_m,
        )) or self.body_agl_m <= 0:
            raise ValueError("finite state and positive body AGL are required")


class VehicleStateBuffer:
    def __init__(self, capacity=500, max_gap_s=0.25):
        if capacity < 2 or max_gap_s <= 0:
            raise ValueError("invalid buffer limits")
        self.capacity, self.max_gap_s = capacity, max_gap_s
        self.samples = []

    def add(self, state):
        if self.samples and (state.timestamp_s <= self.samples[-1].timestamp_s
                             or state.clock != self.samples[-1].clock):
            raise ValueError("state timestamps must increase in the same clock")
        self.samples.append(state)
        self.samples[:] = self.samples[-self.capacity:]

    def at(self, timestamp_s, clock="host_monotonic_approximate"):
        if not math.isfinite(timestamp_s) or not self.samples:
            raise ValueError("no matching state")
        if clock != self.samples[-1].clock:
            raise ValueError("clock mismatch")
        i = bisect_left([s.timestamp_s for s in self.samples], timestamp_s)
        if i < len(self.samples) and self.samples[i].timestamp_s == timestamp_s:
            return self.samples[i]
        if i == 0 or i == len(self.samples):
            raise ValueError("timestamp not bracketed; extrapolation forbidden")
        a, b = self.samples[i-1:i+1]
        if b.timestamp_s - a.timestamp_s > self.max_gap_s:
            raise ValueError("telemetry gap too large")
        if a.height_source != b.height_source:
            raise ValueError("height source changed")
        # Shortest-angle interpolation for the low-tilt hover demo.
        # Large tilt/gimbal-lock flight requires quaternion SLERP instead.
        f = (timestamp_s-a.timestamp_s)/(b.timestamp_s-a.timestamp_s)
        def angle(x, y):
            return x + f * math.atan2(math.sin(y-x), math.cos(y-x))
        return VehicleState(timestamp_s, angle(a.roll_rad,b.roll_rad),
                            angle(a.pitch_rad,b.pitch_rad), angle(a.yaw_rad,b.yaw_rad),
                            a.body_agl_m + f*(b.body_agl_m-a.body_agl_m),
                            a.height_source, a.clock)


class DynamicGroundProjector:
    def __init__(self, intrinsics: CameraIntrinsics, mount: CameraMount):
        self.intrinsics, self.mount = intrinsics, mount

    def _pose(self, state):
        if max(abs(state.roll_rad), abs(state.pitch_rad)) > math.radians(35):
            raise ValueError("outside validated low-tilt demo envelope")
        flu_to_frd = np.diag([1., -1., -1.])
        ground_from_body = np.asarray(_rpy_rotation(state.roll_rad, state.pitch_rad, 0.))
        rotation = ground_from_body @ flu_to_frd @ np.asarray(self.mount.body_from_optical_rotation)
        centre = (np.array([0.,0.,-state.body_agl_m]) +
                  ground_from_body @ flu_to_frd @ np.asarray(self.mount.translation_body_m))
        if centre[2] >= 0:
            raise ValueError("camera must be above ground")
        return rotation, centre

    def ground_to_image_homography(self, state):
        rotation, centre = self._pose(state)
        optical_from_ground = rotation.T
        return np.asarray(self.intrinsics.matrix) @ np.column_stack((
            optical_from_ground[:,0], optical_from_ground[:,1],
            -optical_from_ground @ centre))

    def pixels_to_ground(self, pixels, state):
        import cv2
        pixels = np.asarray(pixels, dtype=float).reshape(-1,2)
        rays = cv2.undistortPoints(pixels.reshape(-1,1,2),
            np.asarray(self.intrinsics.matrix), np.asarray(self.intrinsics.distortion)).reshape(-1,2)
        rotation, centre = self._pose(state)
        directions = np.column_stack((rays, np.ones(len(rays)))) @ rotation.T
        valid = np.isfinite(directions).all(axis=1) & (directions[:,2] > 1e-6)
        result = np.full((len(rays),2), np.nan)
        result[valid] = (centre + directions[valid] *
                        (-centre[2]/directions[valid,2])[:,None])[:,:2]
        return result, valid

    def birdseye(self, image, state, forward_m=8., half_width_m=2., metres_per_pixel=0.02):
        import cv2
        if min(forward_m, half_width_m, metres_per_pixel) <= 0:
            raise ValueError("positive birdseye dimensions required")
        k = self.intrinsics
        if image.shape[:2] != (k.height_px,k.width_px):
            raise ValueError("image size differs from calibration")
        size = (math.ceil(2*half_width_m/metres_per_pixel), math.ceil(forward_m/metres_per_pixel))
        scale = np.array([[0,1/metres_per_pixel,half_width_m/metres_per_pixel],
                          [-1/metres_per_pixel,0,forward_m/metres_per_pixel], [0,0,1.]])
        matrix = scale @ np.linalg.inv(self.ground_to_image_homography(state))
        rectified = cv2.undistort(image,np.asarray(k.matrix),np.asarray(k.distortion))
        warped = cv2.warpPerspective(rectified,matrix,size,flags=cv2.INTER_NEAREST)
        # Exclude points behind the camera, even if projective wrapping lands in-frame.
        rows, cols = np.indices((size[1],size[0]))
        xy1 = np.stack((forward_m-rows*metres_per_pixel,
                       cols*metres_per_pixel-half_width_m,np.ones_like(rows)),axis=-1)
        depth = xy1 @ self.ground_to_image_homography(state)[2]
        warped[depth <= 1e-6] = 0
        return warped
