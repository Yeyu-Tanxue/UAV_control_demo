"""Offline YOLO + rail-plane projection, with independent mesh/pose references."""
from dataclasses import asdict,replace
from pathlib import Path
from datetime import datetime
import json
import math
import re
import sys
import cv2
import numpy as np
from scipy.spatial.transform import Rotation
from ultralytics import YOLO
from audit_rail_dimensions import measure

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from uav_demo.camera_geometry import load_gazebo_camera_geometry
from uav_demo.ground_projection import DynamicGroundProjector,VehicleState
from uav_demo.metric_rail_geometry import MetricRailGeometry


def main():
    source=ROOT/'captures/projection/20260911_234616'
    output=ROOT/'captures/metric_rail'/datetime.now().strftime('%Y%m%d_%H%M%S')
    output.mkdir(parents=True,exist_ok=False)
    dimensions=measure()
    models=ROOT/'simulation/gazebo/models'
    g=load_gazebo_camera_geometry(models/'mono_cam/model.sdf',models/'x500_mono_cam/model.sdf')
    projector=DynamicGroundProjector(g.intrinsics,g.mount)
    fitter=MetricRailGeometry(projector,dimensions['crown_centre_spacing_m'])
    model=YOLO(str(ROOT/'output/training-runs/rail-segmentation/l4r_spring_yolo26n_sanity/weights/best.pt'))
    records=[]
    for info in json.loads((source/'summary.json').read_text()):
        index=info['index']; image=cv2.imread(str(source/f'{index:02d}_raw.png'))
        # This archived 20260911 batch stored FLU roll with an erroneous minus.
        # Correct it on read; retain the original capture metadata unchanged.
        state=VehicleState(index,-info['roll_rad'],info['pitch_rad'],0,
            info['body_agl_z0']-dimensions['rail_top_z_m'],'gazebo_body_above_mesh_rail_top','simulation_snapshot')
        result=model.predict(image,imgsz=640,conf=.15,device='cpu',retina_masks=True,verbose=False)[0]
        candidates=[]
        if result.masks is not None:
            for mask,confidence in zip(result.masks.data,result.boxes.conf):
                mask=mask.cpu().numpy()
                estimate,binary=fitter.estimate(mask,state)
                if estimate is not None: candidates.append((float(confidence),estimate,binary))
        bev=projector.birdseye(image,state)
        old=projector.birdseye(image,replace(state,body_agl_m=info['body_agl_z0']))
        text=(source/f'{index:02d}_truth.txt').read_text()
        block=text.split('name: "x500_mono_cam_0"')[1].split('\npose {')[0]
        qblock=re.search(r'orientation \{([^}]+)\}',block).group(1)
        q=[float(m.group(1)) if (m:=re.search(r'\b'+f+r': ([^\s]+)',qblock)) else 0 for f in 'xyzw']
        yaw=Rotation.from_quat(q).as_euler('xyz')[2]
        rail_y=sum(dimensions['negative_rail_y_range_m']+dimensions['positive_rail_y_range_m'])/4
        truth_offset=(info['base_world_xyz'][1]-rail_y)/math.cos(yaw)
        record={'index':index,'rail_plane_z_m':dimensions['rail_top_z_m'],
            'body_above_rail_m':state.body_agl_m,'ground_truth_lateral_m':truth_offset,
            'ground_truth_heading_deg':math.degrees(yaw),'accepted':bool(candidates)}
        if candidates:
            confidence,estimate,binary=max(candidates,key=lambda c:c[0])
            record.update(confidence=confidence,estimate=asdict(estimate),
                lateral_error_vs_truth_m=estimate.lateral_error_m-truth_offset,
                heading_error_vs_truth_deg=estimate.heading_error_deg-math.degrees(yaw))
            bev[binary>0]=(bev[binary>0]*.6+np.array([0,100,0])).clip(0,255).astype(np.uint8)
            slope=math.tan(math.radians(estimate.heading_error_deg))
            for row in range(400):
                col=round((estimate.lateral_error_m+slope*(8-row*.02)+2)/.02)
                if 0<=col<200: cv2.circle(bev,(col,row),1,(0,0,255),-1)
        # White line: expected rail centre from mesh and Gazebo pose.
        for row in range(400):
            col=round((truth_offset+math.tan(yaw)*(8-row*.02)+2)/.02)
            if 0<=col<200: bev[row,col]=(255,255,255)
        panel=np.full((530,1080,3),25,np.uint8)
        panel[40:520,0:640]=image
        panel[40:440,660:860]=old
        panel[40:440,880:1080]=bev
        cv2.putText(panel,'Raw                       Z=0 BEV      Rail-plane + YOLO',(10,25),cv2.FONT_HERSHEY_SIMPLEX,.7,(255,255,255),1)
        label=(f"offset={estimate.lateral_error_m:+.3f}m heading={estimate.heading_error_deg:+.2f}deg"
               if candidates else 'YOLO geometry rejected')
        cv2.putText(panel,label,(650,480),cv2.FONT_HERSHEY_SIMPLEX,.45,(255,255,255),1)
        cv2.putText(panel,'red=YOLO white=truth',(660,505),cv2.FONT_HERSHEY_SIMPLEX,.5,(255,255,255),1)
        for name,img in [('panel',panel),('rail_bev',bev)]:
            if not cv2.imwrite(str(output/f'{index:02d}_{name}.png'),img): raise RuntimeError('save failed')
        records.append(record)
    (output/'report.json').write_text(json.dumps({'mesh':dimensions,'frames':records},indent=2))
    print(output,flush=True)
    print(json.dumps(records,indent=2),flush=True)

if __name__=='__main__': main()
