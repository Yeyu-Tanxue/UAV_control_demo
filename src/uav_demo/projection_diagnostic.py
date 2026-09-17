"""Read-only MAVSDK + Gazebo PNG projection diagnostic; sends no flight commands."""
import argparse
import asyncio
import json
import math
from pathlib import Path
import time
from dataclasses import asdict

from .camera_geometry import load_gazebo_camera_geometry
from .ground_projection import VehicleState, VehicleStateBuffer, DynamicGroundProjector


async def run(args):
    import cv2
    from mavsdk import System
    from .onboard_vision import GazeboSpoolFrameSource
    geometry = load_gazebo_camera_geometry(
        args.models / "mono_cam/model.sdf",args.models / "x500_mono_cam/model.sdf")
    projector = DynamicGroundProjector(geometry.intrinsics,geometry.mount)
    buffer = VehicleStateBuffer()
    latest_height = None
    drone = System()
    await drone.connect(system_address=args.address)
    async def heights():
        nonlocal latest_height
        async for p in drone.telemetry.position():
            latest_height = (time.monotonic(),p.relative_altitude_m + args.home_above_ground)
    async def attitudes():
        async for p in drone.telemetry.attitude_euler():
            now = time.monotonic()
            if latest_height is None or now-latest_height[0] > 0.5 or latest_height[1] <= 0:
                continue
            buffer.add(VehicleState(now,math.radians(p.roll_deg),math.radians(p.pitch_deg),
                math.radians(p.yaw_deg),latest_height[1],"relative_home_plus_explicit_ground_offset"))
    tasks = [asyncio.create_task(heights()),asyncio.create_task(attitudes())]
    source = GazeboSpoolFrameSource(args.frames)
    args.output.mkdir(parents=True,exist_ok=False)
    try:
        for i in range(args.count):
            frame = await source.capture()
            # File mtime is a host write-time estimate, not exposure/simulation time.
            stamp = time.monotonic() - (time.time()-Path(frame.source_id).stat().st_mtime)
            deadline = time.monotonic()+2
            while not buffer.samples or buffer.samples[-1].timestamp_s < stamp:
                for task in tasks:
                    if task.done():
                        task.result()
                        raise RuntimeError("telemetry stream ended")
                if time.monotonic() > deadline:
                    raise TimeoutError("no bracketing telemetry")
                await asyncio.sleep(0.02)
            try:
                state = buffer.at(stamp)
                bird = projector.birdseye(frame.image,state)
                if not cv2.imwrite(str(args.output/f"{i:04d}_bev.png"),bird):
                    raise RuntimeError("could not save birdseye")
                record = {"frame":frame.source_id,"state":asdict(state),
                          "time_quality":"approximate_file_write_and_telemetry_receive",
                          "homography":projector.ground_to_image_homography(state).tolist()}
            except ValueError as exc:
                record = {"frame":frame.source_id,"rejected":str(exc)}
            with (args.output/"projection.jsonl").open("a",encoding="utf-8") as handle:
                handle.write(json.dumps(record)+"\n")
    finally:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks,return_exceptions=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--models",type=Path,default=Path("simulation/gazebo/models"))
    parser.add_argument("--frames",type=Path,default=Path("/tmp/uav_demo_camera"))
    parser.add_argument("--address",default="udpin://0.0.0.0:14540")
    parser.add_argument("--home-above-ground",type=float,required=True,
                        help="Home altitude minus target plane altitude, metres; must be measured")
    parser.add_argument("--output",type=Path,required=True)
    parser.add_argument("--count",type=int,default=20)
    args = parser.parse_args()
    if not math.isfinite(args.home_above_ground) or args.count < 1:
        parser.error("finite height offset and positive count required")
    asyncio.run(run(args))


if __name__ == "__main__":
    main()
