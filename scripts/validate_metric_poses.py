"""Render stationary Gazebo cameras at known poses, then evaluate metric YOLO.

No PX4 or flight commands. Generated world and images are retained for audit.
"""
import copy
from dataclasses import asdict
from datetime import datetime
import json
import math
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
import tempfile
import xml.etree.ElementTree as ET

import cv2
import numpy as np
from scipy.spatial.transform import Rotation
from audit_rail_dimensions import measure

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from uav_demo.camera_geometry import load_gazebo_camera_geometry
from uav_demo.ground_projection import DynamicGroundProjector,VehicleState
from uav_demo.metric_rail_geometry import MetricRailGeometry


def main():
    output=ROOT/'captures/pose_validation'/datetime.now().strftime('%Y%m%d_%H%M%S')
    output.mkdir(parents=True,exist_ok=False)
    print(output,flush=True)
    # Gazebo filenames contain '::', which Windows-backed /mnt/e cannot store.
    spool=Path(tempfile.mkdtemp(prefix='metric_pose_'))
    dimensions=measure()
    models=ROOT/'simulation/gazebo/models'
    geometry=load_gazebo_camera_geometry(models/'mono_cam/model.sdf',models/'x500_mono_cam/model.sdf')
    projector=DynamicGroundProjector(geometry.intrinsics,geometry.mount)
    fitter=MetricRailGeometry(projector,dimensions['crown_centre_spacing_m'])
    # y is ENU left; heading is ENU yaw. AGL here is body above rail crown.
    cases=[('center',0,0,2,0,0),('left_40cm',.4,0,2,0,0),
           ('right_40cm',-.4,0,2,0,0),('yaw_plus10',0,10,2,0,0),
           ('yaw_minus10',0,-10,2,0,0),('yaw_plus20',0,20,2,0,0),
           ('yaw_minus20',0,-20,2,0,0),('low_1p5m',0,0,1.5,0,0),
           ('high_3m',0,0,3,0,0),('roll_plus10',0,0,2,10,0),
           ('roll_minus10',0,0,2,-10,0),('pitch_plus10',0,0,2,0,10),
           ('pitch_minus10',0,0,2,0,-10),('combined',.3,-10,2.5,8,-8)]
    tree=ET.parse(ROOT/'simulation/gazebo/worlds/rail_demo_realistic.sdf')
    world=tree.getroot().find('world'); world.set('name','metric_pose_validation')
    # Explicit rendering plugin; same rendering engine as the PX4 config.
    for filename,name in [('gz-sim-physics-system','Physics'),
                          ('gz-sim-user-commands-system','UserCommands'),
                          ('gz-sim-scene-broadcaster-system','SceneBroadcaster'),
                          ('gz-sim-sensors-system','Sensors')]:
        plugin=ET.SubElement(world,'plugin',filename=filename,name='gz::sim::systems::'+name)
        if name=='Sensors': ET.SubElement(plugin,'render_engine').text='ogre2'
    sensor_template=ET.parse(models/'mono_cam/model.sdf').find('./model/link/sensor')
    for name,y,yaw,height,roll,pitch in cases:
        directory=output/name; directory.mkdir()
        (spool/name).mkdir()
        model=ET.SubElement(world,'model',name=name)
        ET.SubElement(model,'static').text='true'
        # FLU and FRD share +X: roll keeps its sign; pitch changes sign.
        angles=[math.radians(roll),math.radians(-pitch),math.radians(yaw)]
        body_rotation=Rotation.from_euler('xyz',angles)
        body=np.array([-10.,y,height+dimensions['rail_top_z_m']])
        camera=body+body_rotation.apply(geometry.mount.translation_body_m)
        camera_rotation=body_rotation*Rotation.from_euler('xyz',[0,geometry.mount.pitch_rad,0])
        ET.SubElement(model,'pose').text=' '.join(map(str,[*camera,*camera_rotation.as_euler('xyz')]))
        link=ET.SubElement(model,'link',name='camera_link')
        sensor=copy.deepcopy(sensor_template)
        sensor.find('update_rate').text='1'
        sensor.find('./camera/save/path').text=str(spool/name)
        link.append(sensor)
    world_path=output/'validation_world.sdf'
    tree.write(world_path,encoding='utf-8',xml_declaration=True)
    env=os.environ.copy()
    env['GZ_SIM_RESOURCE_PATH']=str(models)
    env.pop('GZ_SIM_SERVER_CONFIG_PATH',None)
    env['GZ_PARTITION']='metric_validation_'+output.name
    with (output/'gazebo.log').open('w') as log:
        process=subprocess.Popen(['gz','sim','-r','-s',str(world_path)],env=env,
                                 stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
        subscribers=[]
        try:
            discovery_deadline=time.monotonic()+120
            required=['/world/metric_pose_validation/model/'+case[0]+'/link/camera_link/sensor/imager/camera_info' for case in cases]
            while True:
                if process.poll() is not None: raise RuntimeError('Gazebo exited before camera discovery')
                listing=subprocess.run(['gz','topic','-l'],env=env,capture_output=True,text=True,timeout=10)
                if all(topic in listing.stdout.splitlines() for topic in required): break
                if time.monotonic()>discovery_deadline: raise TimeoutError('camera topic discovery timeout')
                time.sleep(1)
            # Sensors render on demand even with save enabled. Keep explicit
            # subscriptions alive until each camera has produced a frame.
            for case in cases:
                topic='/world/metric_pose_validation/model/'+case[0]+'/link/camera_link/sensor/imager/camera_info'
                subscribers.append(subprocess.Popen(['gz','topic','-e','-t',topic],
                    env=env,stdout=subprocess.DEVNULL,stderr=log,start_new_session=True))
            deadline=time.monotonic()+180
            while True:
                ready=all(any((spool/c[0]).glob('*.png')) for c in cases)
                if ready:
                    time.sleep(3)
                    break
                if process.poll() is not None: raise RuntimeError('Gazebo exited; inspect gazebo.log')
                if time.monotonic()>deadline: raise TimeoutError('render timeout; inspect gazebo.log')
                time.sleep(1)
        finally:
            for subscriber in subscribers:
                if subscriber.poll() is None:
                    os.killpg(subscriber.pid,signal.SIGTERM)
                    try: subscriber.wait(timeout=3)
                    except subprocess.TimeoutExpired:
                        os.killpg(subscriber.pid,signal.SIGKILL); subscriber.wait()
            if process.poll() is None:
                os.killpg(process.pid,signal.SIGTERM)
                try: process.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid,signal.SIGKILL); process.wait()
    from ultralytics import YOLO
    detector=YOLO(str(ROOT/'output/training-runs/rail-segmentation/l4r_spring_yolo26n_sanity/weights/best.pt'))
    records=[]; panels=[]
    rail_y=sum(dimensions['negative_rail_y_range_m']+dimensions['positive_rail_y_range_m'])/4
    for name,y,yaw,height,roll,pitch in cases:
        paths=sorted((spool/name).glob('*.png'),key=lambda p:p.stat().st_mtime_ns)
        image=next((img for p in reversed(paths) if (img:=cv2.imread(str(p))) is not None),None)
        if image is None: raise RuntimeError('no complete image for '+name)
        if not cv2.imwrite(str(output/name/'raw.png'),image): raise RuntimeError('save failed')
        state=VehicleState(0,math.radians(roll),math.radians(pitch),0,height,'known_static_camera','simulation_static')
        truth=(y-rail_y)/math.cos(math.radians(yaw))
        results=detector.predict(image,conf=.15,imgsz=640,device='cpu',retina_masks=True,verbose=False)[0]
        candidates=[]
        if results.masks is not None:
            for mask,conf in zip(results.masks.data,results.boxes.conf):
                estimate,binary=fitter.estimate(mask.cpu().numpy(),state)
                if estimate is not None: candidates.append((float(conf),estimate,binary))
        record=dict(case=name,body_y_m=y,yaw_enu_deg=yaw,body_above_rail_m=height,
                    roll_frd_deg=roll,pitch_frd_deg=pitch,truth_lateral_m=truth,
                    truth_heading_deg=yaw,accepted=bool(candidates))
        bev=projector.birdseye(image,state)
        if candidates:
            conf,estimate,binary=max(candidates,key=lambda x:x[0])
            record.update(confidence=conf,estimate=asdict(estimate),
                          lateral_abs_error_m=abs(estimate.lateral_error_m-truth),
                          heading_abs_error_deg=abs(estimate.heading_error_deg-yaw))
            record['within_demo_tolerance']=record['lateral_abs_error_m']<=.1 and record['heading_abs_error_deg']<=3
            bev[binary>0]=(bev[binary>0]*.6+[0,90,0]).clip(0,255).astype(np.uint8)
        for row in range(400):
            x=8-row*.02
            col=round((truth+math.tan(math.radians(yaw))*x+2)/.02)
            if 0<=col<200: bev[row,col]=(255,255,255)
            if candidates:
                col=round((estimate.lateral_error_m+math.tan(math.radians(estimate.heading_error_deg))*x+2)/.02)
                if 0<=col<200: cv2.circle(bev,(col,row),1,(0,0,255),-1)
        panel=np.full((450,660,3),25,np.uint8)
        panel[45:375,:440]=cv2.resize(image,(440,330))
        panel[45:445,450:650]=bev
        cv2.putText(panel,name,(10,25),cv2.FONT_HERSHEY_SIMPLEX,.65,(255,255,255),1)
        label=(f"error {record['lateral_abs_error_m']:.3f}m / {record['heading_abs_error_deg']:.2f}deg"
               if candidates else 'REJECTED: insufficient valid geometry')
        cv2.putText(panel,label,(10,410),cv2.FONT_HERSHEY_SIMPLEX,.5,(255,255,255),1)
        cv2.imwrite(str(output/name/'result.png'),panel)
        panels.append(cv2.resize(panel,(440,300)))
        records.append(record)
        print(name,label,flush=True)
    while len(panels)%2: panels.append(np.zeros_like(panels[0]))
    montage=np.vstack([np.hstack(panels[i:i+2]) for i in range(0,len(panels),2)])
    cv2.imwrite(str(output/'overview.jpg'),montage)
    report={'thresholds':{'lateral_m':.1,'heading_deg':3},'mesh':dimensions,'cases':records}
    (output/'report.json').write_text(json.dumps(report,indent=2))
    lines=['# 固定机位多姿态验证','', '| Case | Accepted | Lateral error m | Heading error deg |',
           '|---|---|---|---|']
    for r in records:
        lines.append(f"| {r['case']} | {r['accepted']} | {r.get('lateral_abs_error_m','—')} | {r.get('heading_abs_error_deg','—')} |")
    lines+=['','静态 Gazebo 图像，非实际飞行；红线为 YOLO，白线为真值。',
            '每工况一帧，无帧间融合。拒绝不等于正确识别，须单独统计；没有修改模型权重或控制器。']
    (output/'README.md').write_text('\n'.join(lines),encoding='utf-8')
    print('RESULT '+str(output),flush=True)


if __name__=='__main__': main()
