"""SITL-only stationary hover capture with Gazebo ground-truth geometry."""
import asyncio
from datetime import datetime
import json
from pathlib import Path
import re
import subprocess
import sys

import cv2
import numpy as np
from scipy.spatial.transform import Rotation

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"src"))
from uav_demo.backends.mavsdk_px4 import MavsdkPx4Controller
from uav_demo.camera_geometry import load_gazebo_camera_geometry
from uav_demo.ground_projection import DynamicGroundProjector, VehicleState
from uav_demo.onboard_vision import GazeboSpoolFrameSource

ROOT = Path(__file__).resolve().parents[1]


def truth():
    raw = subprocess.check_output(["gz","topic","-e","-n","1","-t",
        "/world/rail_demo_realistic/dynamic_pose/info"],text=True,timeout=10)
    model = raw.split('name: "x500_mono_cam_0"',1)[1].split('\npose {',1)[0]
    def vector(section,fields):
        block = re.search(section+r" \{([^}]+)\}",model).group(1)
        return [float(m.group(1)) if (m := re.search(r"\b"+f+r": ([^\s]+)",block)) else 0 for f in fields]
    position = np.array(vector("position","xyz"))
    rotation = Rotation.from_quat(vector("orientation","xyzw"))
    body = position+rotation.apply([0,0,.24])
    roll,pitch,yaw = rotation.as_euler("xyz")
    return raw,body,VehicleState(0,roll,-pitch,-yaw,float(body[2]),"gazebo_base_link_above_z0","simulation_snapshot")


async def main():
    # Refuse to run unless this exact Gazebo world has been observed.
    truth()
    out = ROOT/"captures/projection"/datetime.now().strftime("%Y%m%d_%H%M%S")
    out.mkdir(parents=True,exist_ok=False)
    models = ROOT/"simulation/gazebo/models"
    g = load_gazebo_camera_geometry(models/"mono_cam/model.sdf",models/"x500_mono_cam/model.sdf")
    projector = DynamicGroundProjector(g.intrinsics,g.mount)
    controller = MavsdkPx4Controller("udpin://0.0.0.0:14540")
    source = GazeboSpoolFrameSource(Path("/tmp/uav_demo_camera"))
    records = []
    try:
        await controller.connect(60)
        await controller.takeoff(2.45,60)
        await controller.start_offboard_hold()
        await asyncio.sleep(5)
        for i in range(5):
            raw,body,state = await asyncio.to_thread(truth)
            frame = await source.capture()
            bev = projector.birdseye(frame.image,state)
            for x in range(0,201,50):
                cv2.line(bev,(min(x,199),0),(min(x,199),399),(100,100,100),1)
            for y in range(0,400,50):
                cv2.line(bev,(0,y),(199,y),(100,100,100),1)
            cv2.line(bev,(100,0),(100,399),(0,0,255),1)
            panel = np.full((500,870,3),30,np.uint8)
            panel[40:500,:640] = cv2.resize(frame.image,(640,460))
            panel[40:440,660:860] = bev
            cv2.putText(panel,"Gazebo image | BEV: 1 m grid, red=heading",(10,25),cv2.FONT_HERSHEY_SIMPLEX,.6,(255,255,255),1)
            for name,img in [("raw",frame.image),("bev",bev),("panel",panel)]:
                if not cv2.imwrite(str(out/f"{i:02d}_{name}.png"),img):
                    raise RuntimeError("image save failed")
            (out/f"{i:02d}_truth.txt").write_text(raw)
            records.append({"index":i,"base_world_xyz":body.tolist(),"body_agl_z0":state.body_agl_m,
                "roll_rad":state.roll_rad,"pitch_rad":state.pitch_rad,"plane_z":0,
                "camera_body_xyz":g.mount.translation_body_m,
                "time_quality":"stationary_hover_nearby_snapshots_not_exposure_synchronised"})
            await asyncio.sleep(.3)
    finally:
        await controller.safe_stop_and_land(60)
        (out/"summary.json").write_text(json.dumps(records,indent=2))
        print(out,flush=True)


if __name__ == "__main__":
    asyncio.run(main())
