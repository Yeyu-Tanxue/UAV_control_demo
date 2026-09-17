"""Fixed camera geometry for the Gazebo rail-following demo.

This module intentionally stops before vehicle attitude and height are used.
It owns only the two time-invariant parts of the projection model:

* camera intrinsics and lens distortion; and
* the rigid transform from the Gazebo camera link to ``base_link``.

Gazebo/SDF camera links look along +X with +Y left and +Z up.  Image
algorithms use the OpenCV optical convention (+X right, +Y down, +Z forward),
so that axis conversion is made explicit here instead of being hidden in the
future dynamic homography implementation.
"""

from __future__ import annotations

import math
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path


Vector3 = tuple[float, float, float]
Matrix3 = tuple[Vector3, Vector3, Vector3]
Distortion5 = tuple[float, float, float, float, float]


class CameraGeometryError(ValueError):
    """Raised when an SDF camera definition is missing or inconsistent."""


def _matmul(left: Matrix3, right: Matrix3) -> Matrix3:
    return tuple(
        tuple(
            sum(left[row][k] * right[k][column] for k in range(3))
            for column in range(3)
        )
        for row in range(3)
    )  # type: ignore[return-value]


def _transpose(matrix: Matrix3) -> Matrix3:
    return tuple(
        tuple(matrix[column][row] for column in range(3))
        for row in range(3)
    )  # type: ignore[return-value]


def _matvec(matrix: Matrix3, vector: Vector3) -> Vector3:
    return tuple(
        sum(matrix[row][column] * vector[column] for column in range(3))
        for row in range(3)
    )  # type: ignore[return-value]


def _rpy_rotation(roll_rad: float, pitch_rad: float, yaw_rad: float) -> Matrix3:
    """Return the SDF ``Rz(yaw) @ Ry(pitch) @ Rx(roll)`` rotation."""

    cr, sr = math.cos(roll_rad), math.sin(roll_rad)
    cp, sp = math.cos(pitch_rad), math.sin(pitch_rad)
    cy, sy = math.cos(yaw_rad), math.sin(yaw_rad)
    return (
        (cy * cp, cy * sp * sr - sy * cr, cy * sp * cr + sy * sr),
        (sy * cp, sy * sp * sr + cy * cr, sy * sp * cr - cy * sr),
        (-sp, cp * sr, cp * cr),
    )


# Convert a vector expressed in an SDF camera link into OpenCV optical axes.
#
#     x_optical (right)   = -y_link
#     y_optical (down)    = -z_link
#     z_optical (forward) =  x_link
OPTICAL_FROM_CAMERA_LINK: Matrix3 = (
    (0.0, -1.0, 0.0),
    (0.0, 0.0, -1.0),
    (1.0, 0.0, 0.0),
)


@dataclass(frozen=True, slots=True)
class CameraIntrinsics:
    """Pinhole intrinsics with Brown-Conrady distortion coefficients."""

    width_px: int
    height_px: int
    fx_px: float
    fy_px: float
    cx_px: float
    cy_px: float
    # OpenCV order: k1, k2, p1, p2, k3.
    distortion: Distortion5 = (0.0, 0.0, 0.0, 0.0, 0.0)

    def __post_init__(self) -> None:
        if self.width_px <= 0 or self.height_px <= 0:
            raise CameraGeometryError("image dimensions must be positive")
        if self.fx_px <= 0.0 or self.fy_px <= 0.0:
            raise CameraGeometryError("focal lengths must be positive")
        if len(self.distortion) != 5:
            raise CameraGeometryError("distortion must contain k1,k2,p1,p2,k3")

    @classmethod
    def from_horizontal_fov(
        cls,
        width_px: int,
        height_px: int,
        horizontal_fov_rad: float,
        *,
        distortion: Distortion5 = (0.0, 0.0, 0.0, 0.0, 0.0),
    ) -> "CameraIntrinsics":
        """Build the square-pixel pinhole model used by the Gazebo camera."""

        if not 0.0 < horizontal_fov_rad < math.pi:
            raise CameraGeometryError("horizontal FOV must be between 0 and pi")
        focal_px = width_px / (2.0 * math.tan(horizontal_fov_rad / 2.0))
        return cls(
            width_px=width_px,
            height_px=height_px,
            fx_px=focal_px,
            fy_px=focal_px,
            cx_px=width_px / 2.0,
            cy_px=height_px / 2.0,
            distortion=distortion,
        )

    @property
    def matrix(self) -> Matrix3:
        return (
            (self.fx_px, 0.0, self.cx_px),
            (0.0, self.fy_px, self.cy_px),
            (0.0, 0.0, 1.0),
        )

    @property
    def horizontal_fov_rad(self) -> float:
        return 2.0 * math.atan(self.width_px / (2.0 * self.fx_px))

    @property
    def vertical_fov_rad(self) -> float:
        return 2.0 * math.atan(self.height_px / (2.0 * self.fy_px))


@dataclass(frozen=True, slots=True)
class CameraMount:
    """Fixed pose of the SDF camera link relative to the Gazebo body frame.

    ``translation_body_m`` is the camera centre expressed in ``base_link``.
    The RPY angles follow SDF and rotate camera-link vectors into body axes.
    Both link and body frames use +X forward, +Y left and +Z up.
    """

    translation_body_m: Vector3
    roll_rad: float
    pitch_rad: float
    yaw_rad: float
    parent_frame: str = "base_link"
    child_frame: str = "camera_link"

    @property
    def body_from_camera_link_rotation(self) -> Matrix3:
        return _rpy_rotation(self.roll_rad, self.pitch_rad, self.yaw_rad)

    @property
    def body_from_optical_rotation(self) -> Matrix3:
        camera_link_from_optical = _transpose(OPTICAL_FROM_CAMERA_LINK)
        return _matmul(
            self.body_from_camera_link_rotation,
            camera_link_from_optical,
        )

    @property
    def optical_from_body_rotation(self) -> Matrix3:
        return _transpose(self.body_from_optical_rotation)

    @property
    def optical_axis_body(self) -> Vector3:
        """Return the image centre ray (+Z optical) in body axes."""

        return _matvec(self.body_from_optical_rotation, (0.0, 0.0, 1.0))

    @property
    def optical_right_body(self) -> Vector3:
        return _matvec(self.body_from_optical_rotation, (1.0, 0.0, 0.0))

    @property
    def optical_down_body(self) -> Vector3:
        return _matvec(self.body_from_optical_rotation, (0.0, 1.0, 0.0))


@dataclass(frozen=True, slots=True)
class GazeboCameraGeometry:
    """The fixed geometry and stream settings read from the two SDF files."""

    intrinsics: CameraIntrinsics
    mount: CameraMount
    update_rate_hz: float
    near_clip_m: float
    far_clip_m: float


def _required_text(parent: ET.Element, path: str, description: str) -> str:
    text = parent.findtext(path)
    if text is None or not text.strip():
        raise CameraGeometryError(f"missing {description}: {path}")
    return text.strip()


def _read_pose(text: str, description: str) -> tuple[float, ...]:
    try:
        values = tuple(float(value) for value in text.split())
    except ValueError as exc:
        raise CameraGeometryError(f"invalid {description}: {text!r}") from exc
    if len(values) != 6:
        raise CameraGeometryError(f"{description} must contain x y z roll pitch yaw")
    return values


def load_gazebo_camera_geometry(
    sensor_model_path: str | Path,
    vehicle_model_path: str | Path,
    *,
    sensor_name: str = "imager",
    camera_model_uri: str = "model://mono_cam",
    joint_name: str = "CameraJoint",
    body_origin_in_model_m: Vector3 = (0.0, 0.0, 0.24),
) -> GazeboCameraGeometry:
    """Read and cross-check the demo camera intrinsics and fixed mount."""

    sensor_root = ET.parse(Path(sensor_model_path)).getroot()
    sensor = sensor_root.find(f"./model/link/sensor[@name='{sensor_name}']")
    if sensor is None:
        raise CameraGeometryError(f"camera sensor {sensor_name!r} was not found")
    camera = sensor.find("camera")
    if camera is None:
        raise CameraGeometryError("camera sensor has no <camera> block")

    width = int(_required_text(camera, "./image/width", "image width"))
    height = int(_required_text(camera, "./image/height", "image height"))
    horizontal_fov = float(
        _required_text(camera, "horizontal_fov", "horizontal FOV")
    )
    intrinsics = CameraIntrinsics.from_horizontal_fov(
        width,
        height,
        horizontal_fov,
    )

    vehicle_root = ET.parse(Path(vehicle_model_path)).getroot()
    vehicle_model = vehicle_root.find("model")
    if vehicle_model is None:
        raise CameraGeometryError("vehicle SDF has no <model> block")
    camera_include = next(
        (
            include
            for include in vehicle_model.findall("include")
            if include.findtext("uri") == camera_model_uri
        ),
        None,
    )
    if camera_include is None:
        raise CameraGeometryError(f"include {camera_model_uri!r} was not found")
    include_pose_text = _required_text(camera_include, "pose", "camera include pose")
    include_pose = _read_pose(include_pose_text, "camera include pose")

    joint = vehicle_model.find(f"./joint[@name='{joint_name}']")
    if joint is None:
        raise CameraGeometryError(f"fixed joint {joint_name!r} was not found")
    if joint.get("type") != "fixed":
        raise CameraGeometryError(f"joint {joint_name!r} must be fixed")
    joint_pose_text = _required_text(joint, "pose", "camera joint pose")
    joint_pose = _read_pose(joint_pose_text, "camera joint pose")
    if any(abs(left - right) > 1e-9 for left, right in zip(include_pose, joint_pose)):
        raise CameraGeometryError("camera include pose and fixed-joint pose disagree")

    parent_frame = _required_text(joint, "parent", "camera joint parent")
    child_frame = _required_text(joint, "child", "camera joint child")
    mount = CameraMount(
        # PX4 x500_base is merged at Z=0.24; include pose is model-relative.
        translation_body_m=tuple(include_pose[i] - body_origin_in_model_m[i] for i in range(3)),
        roll_rad=include_pose[3],
        pitch_rad=include_pose[4],
        yaw_rad=include_pose[5],
        parent_frame=parent_frame,
        child_frame=child_frame,
    )

    return GazeboCameraGeometry(
        intrinsics=intrinsics,
        mount=mount,
        update_rate_hz=float(
            _required_text(sensor, "update_rate", "camera update rate")
        ),
        near_clip_m=float(_required_text(camera, "./clip/near", "near clip")),
        far_clip_m=float(_required_text(camera, "./clip/far", "far clip")),
    )
