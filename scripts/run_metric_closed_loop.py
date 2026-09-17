"""SITL metric visual loop, with telemetry projection and independent truth log."""
import os
# Ubuntu's Gazebo bindings use legacy generated protobuf descriptors while the
# project venv carries a newer protobuf runtime. Pure-Python parsing supports
# both without changing the environment used by the Raspberry Pi entry point.
os.environ.setdefault('PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION','python')

import argparse
import asyncio
from dataclasses import asdict
from datetime import datetime
import json
import math
from pathlib import Path
import statistics
import sys
import time
import cv2
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from audit_rail_dimensions import measure
from uav_demo.backends.mavsdk_px4 import MavsdkPx4Controller
from uav_demo.camera_geometry import load_gazebo_camera_geometry
from uav_demo.ground_projection import (
    DynamicGroundProjector, VehicleState, VehicleStateBuffer,
)
from uav_demo.gazebo_transport import (
    GazeboPoseTruthBuffer, GazeboTransportFrameSource,
)
from uav_demo.metric_rail_geometry import MetricRailGeometry
from uav_demo.metric_control import metric_command


async def main(args):
    from ultralytics import YOLO
    out=ROOT/'captures/metric_closed_loop'/datetime.now().strftime('%Y%m%d_%H%M%S')
    out.mkdir(parents=True,exist_ok=False)
    print('OUTPUT '+str(out),flush=True)
    dimensions=measure(); rail_z=dimensions['rail_top_z_m']
    rail_y=sum(dimensions['negative_rail_y_range_m']+dimensions['positive_rail_y_range_m'])/4
    models=ROOT/'simulation/gazebo/models'
    geometry=load_gazebo_camera_geometry(models/'mono_cam/model.sdf',models/'x500_mono_cam/model.sdf')
    projector=DynamicGroundProjector(geometry.intrinsics,geometry.mount)
    fitter=MetricRailGeometry(projector,dimensions['crown_centre_spacing_m'],half_width_m=3.)
    model=YOLO(str(ROOT/'output/training-runs/rail-segmentation/l4r_spring_yolo26n_sanity/weights/best.pt'))
    # Warm up before arming, so cold model loading never holds a flight hostage.
    model.predict(np.zeros((480,640,3),np.uint8),device='cpu',verbose=False)
    attitude=None; position=None; local_zero_above_rail=None
    state_buffer=VehicleStateBuffer(capacity=1000,max_gap_s=.3)
    tasks=[]; records=[]; outcomes=[]
    def save(record):
        record['host_monotonic_s']=time.monotonic()
        with (out/'decisions.jsonl').open('a',encoding='utf-8') as f: f.write(json.dumps(record)+'\n')
        records.append(record)
    async def attitudes():
        nonlocal attitude
        async for p in controller._drone.telemetry.attitude_euler():
            now=time.monotonic(); attitude=(now,p)
            if (position is None or local_zero_above_rail is None
                    or now-position[0]>.3):
                continue
            try:
                state_buffer.add(VehicleState(
                    now,math.radians(p.roll_deg),math.radians(p.pitch_deg),
                    math.radians(p.yaw_deg),
                    local_zero_above_rail-position[1].position.down_m,
                    'local_ned_plus_initial_gazebo_ground_datum'))
            except ValueError:
                # Ground/landing can be at or below the selected rail plane.
                continue
    async def positions():
        nonlocal position
        async for p in controller._drone.telemetry.position_velocity_ned(): position=(time.monotonic(),p)
    def infer(image,state):
        result=model.predict(image,device='cpu',conf=.15,imgsz=640,retina_masks=True,verbose=False)[0]
        choices=[]
        if result.masks is not None:
            for mask,conf in zip(result.masks.data,result.boxes.conf):
                estimate,binary=fitter.estimate(mask.cpu().numpy(),state)
                if estimate is not None: choices.append((float(conf),estimate,binary))
        return max(choices,key=lambda x:x[0],default=None)
    image_topic=('/world/rail_demo_realistic/model/x500_mono_cam_0/'
                 'link/camera_link/sensor/imager/image')
    pose_topic='/world/rail_demo_realistic/dynamic_pose/info'
    source=GazeboTransportFrameSource(image_topic)
    truth_buffer=GazeboPoseTruthBuffer(pose_topic)
    controller=MavsdkPx4Controller('udpin://0.0.0.0:14540')
    try:
        world_deadline=time.monotonic()+15
        while truth_buffer.latest() is None:
            if time.monotonic()>world_deadline:
                raise TimeoutError('expected Gazebo vehicle pose unavailable')
            await asyncio.sleep(.02)
        await controller.connect(60)
        tasks=[asyncio.create_task(attitudes()),asyncio.create_task(positions())]
        deadline=time.monotonic()+15
        while attitude is None or position is None:
            if time.monotonic()>deadline: raise TimeoutError('telemetry unavailable')
            await asyncio.sleep(.05)
        # Calibrate the local-NED datum at the same settled ground instant.
        # relative_altitude_m's Home/global estimate drifted in the first run.
        await asyncio.sleep(2)
        ground_truth=truth_buffer.latest()
        if ground_truth is None:
            raise RuntimeError('Gazebo ground truth disappeared')
        ground_body=ground_truth.body_xyz
        local_zero_above_rail=float(ground_body[2])-rail_z+position[1].position.down_m
        save({'phase':'calibration','local_zero_above_rail_m':local_zero_above_rail,
              'ground_body_z_m':float(ground_body[2]),'initial_down_m':position[1].position.down_m,
              'height_source':'local_ned_plus_initial_gazebo_ground_datum'})
        await controller.takeoff(2.45,60)
        await controller.start_offboard_hold()
        await asyncio.sleep(4)
        for trial in range(args.trials):
            if trial:
                # Explicit test initialisation, excluded from vision convergence.
                save({'phase':'test_perturbation','trial':trial,'right_m_s':.12,'seconds':3.3,
                      'yaw_rate_deg_s':5,'yaw_seconds':2})
                await controller.set_body_velocity(0,.12,0); await asyncio.sleep(3.3)
                await controller.hold(); await asyncio.sleep(1)
                await controller.set_body_velocity(0,0,5); await asyncio.sleep(2)
                await controller.hold(); await asyncio.sleep(3)
            stable=0; forward_steps=0; misses=0; converged=False
            for cycle in range(args.cycles):
                await controller.hold(); await asyncio.sleep(1.5)
                estimates=[]; observations=[]
                for j in range(3):
                    frame=await source.capture()
                    now=time.monotonic()
                    if attitude is None or position is None or now-attitude[0]>.6 or now-position[0]>1:
                        raise RuntimeError('stale PX4 telemetry')
                    if (frame.timestamp_s is None
                            or frame.clock!='host_monotonic_approximate'):
                        raise RuntimeError('camera frame has no compatible timestamp')
                    if (frame.source_timestamp_s is None
                            or frame.source_clock!='gazebo_simulation'):
                        raise RuntimeError('camera frame has no simulation timestamp')
                    if now-frame.timestamp_s > .8:
                        raise RuntimeError('stale camera frame')
                    deadline=time.monotonic()+.8
                    while (not state_buffer.samples
                           or state_buffer.samples[-1].timestamp_s<frame.timestamp_s):
                        if time.monotonic()>deadline:
                            raise RuntimeError('no telemetry after camera frame')
                        await asyncio.sleep(.01)
                    state=state_buffer.at(frame.timestamp_s,frame.clock)
                    truth_deadline=time.monotonic()+.8
                    while ((truth_buffer.latest_timestamp() or -math.inf)
                           < frame.source_timestamp_s):
                        if time.monotonic()>truth_deadline:
                            raise RuntimeError('no Gazebo truth after camera frame')
                        await asyncio.sleep(.005)
                    nearby_pose=truth_buffer.at(frame.source_timestamp_s)
                    nearby_body=nearby_pose.body_xyz
                    nearby_yaw=nearby_pose.heading_rad
                    nearby_truth={
                        'simulation_timestamp_s':frame.source_timestamp_s,
                        'time_alignment':'gazebo_simulation_timestamp',
                        'body_xyz':list(nearby_body),
                        'body_above_rail_m':float(nearby_body[2])-rail_z,
                        'lateral_m':
                            (float(nearby_body[1])-rail_y)/math.cos(nearby_yaw),
                        'heading_deg':math.degrees(nearby_yaw)}
                    candidate=await asyncio.to_thread(infer,frame.image,state)
                    observations.append({
                        'state':asdict(state),'file':frame.source_id,
                        'frame_timestamp_s':frame.timestamp_s,
                        'source_timestamp_s':frame.source_timestamp_s,
                        'timestamp_quality':frame.timestamp_quality,
                        'nearby_truth':nearby_truth,
                        'valid':candidate is not None})
                    cv2.imwrite(str(out/f't{trial}_{cycle:02d}_{j}_raw.png'),frame.image)
                    if candidate:
                        estimates.append(candidate[1])
                        if j==2:
                            bev=projector.birdseye(frame.image,state,half_width_m=3.)
                            bev[candidate[2]>0]=(bev[candidate[2]>0]*.6+[0,90,0]).clip(0,255).astype(np.uint8)
                            cv2.imwrite(str(out/f't{trial}_{cycle:02d}_bev.png'),bev)
                reference={
                    'lateral_m':statistics.median(
                        item['nearby_truth']['lateral_m']
                        for item in observations),
                    'heading_deg':statistics.median(
                        item['nearby_truth']['heading_deg']
                        for item in observations),
                    'body_xyz':observations[-1]['nearby_truth']['body_xyz'],
                    'time_alignment':'gazebo_simulation_timestamp'}
                if len(estimates)<2:
                    misses+=1; stable=0
                    await controller.hold()
                    save({'phase':'vision','trial':trial,'cycle':cycle,'accepted':False,
                          'truth':reference,'frames':observations,'command':asdict(metric_command(None))})
                    print(f'trial {trial} cycle {cycle}: rejected',flush=True)
                    if misses>=3: raise RuntimeError('three consecutive metric vision misses')
                    continue
                misses=0
                from dataclasses import replace
                estimate=replace(estimates[-1],
                    lateral_error_m=statistics.median(e.lateral_error_m for e in estimates),
                    heading_error_deg=statistics.median(e.heading_error_deg for e in estimates))
                aligned=abs(estimate.lateral_error_m)<.07 and abs(estimate.heading_error_deg)<2
                stable=stable+1 if aligned else 0
                if stable>=3: converged=True
                command=metric_command(estimate,allow_forward=converged)
                save({'phase':'vision','trial':trial,'cycle':cycle,'accepted':True,
                      'estimate':asdict(estimate),'truth':reference,'frames':observations,
                      'command':asdict(command),'stable_count':stable,
                      'time_quality':'transport_receive_bracketed_px4_telemetry'})
                print(f'trial {trial} cycle {cycle}: vision {estimate.lateral_error_m:+.3f}m {estimate.heading_error_deg:+.2f}deg; truth {reference["lateral_m"]:+.3f}m {reference["heading_deg"]:+.2f}deg',flush=True)
                if abs(estimate.lateral_error_m)>.7 or abs(estimate.heading_error_deg)>15:
                    raise RuntimeError('outside metric control envelope')
                await controller.set_body_velocity(command.forward_m_s,command.right_m_s,command.yaw_rate_deg_s)
                try: await asyncio.sleep(1)
                finally: await controller.hold()
                if command.forward_m_s>0: forward_steps+=1
                if forward_steps>=3: break
            outcomes.append({'trial':trial,'vision_converged':converged,'forward_pulses':forward_steps})
            if not converged: break
        await controller.hold(); await asyncio.sleep(2)
        final_truth=truth_buffer.latest()
        if final_truth is None:
            raise RuntimeError('Gazebo final truth unavailable')
        save({'phase':'final_truth','body_xyz':list(final_truth.body_xyz),
              'heading_deg':math.degrees(final_truth.heading_rad),
              'simulation_timestamp_s':final_truth.timestamp_s})
        await controller.stop_offboard(); await controller.land(60)
        save({'phase':'landed'})
    except BaseException as exc:
        save({'phase':'error','message':str(exc)})
        await controller.safe_stop_and_land(60)
        save({'phase':'landed' if not controller._armed else 'landing_unconfirmed',
              'reason':'error_cleanup'})
        raise
    finally:
        for task in tasks: task.cancel()
        await asyncio.gather(*tasks,return_exceptions=True)
        if not controller._armed:
            # MAVSDK's destructor is not deterministic while grpc holds refs.
            # Release this run's server after confirmed landing / before arming.
            server=controller._drone._server_process
            controller._drone._stop_mavsdk_server()
            if server is not None:
                await asyncio.to_thread(server.wait,5)
        (out/'summary.json').write_text(json.dumps({'outcomes':outcomes,'records':len(records)},indent=2))
        print('RESULT '+str(out),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--confirm-sitl',action='store_true',required=True)
    parser.add_argument('--trials',type=int,choices=[1,2],default=2)
    parser.add_argument('--cycles',type=int,default=25)
    args=parser.parse_args()
    if not 1<=args.cycles<=40: parser.error('cycles must be 1..40')
    asyncio.run(main(args))
