"""Compare BEV windows on saved failed frames, without flight."""
from pathlib import Path
import json
import sys
import cv2
import numpy as np
from ultralytics import YOLO
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from uav_demo.camera_geometry import load_gazebo_camera_geometry
from uav_demo.ground_projection import DynamicGroundProjector,VehicleState
from uav_demo.metric_rail_geometry import MetricRailGeometry

folder=Path(sys.argv[1]) if len(sys.argv)>1 else ROOT/'captures/metric_closed_loop/20260916_123421'
models=ROOT/'simulation/gazebo/models'
g=load_gazebo_camera_geometry(models/'mono_cam/model.sdf',models/'x500_mono_cam/model.sdf')
projector=DynamicGroundProjector(g.intrinsics,g.mount)
model=YOLO(str(ROOT/'output/training-runs/rail-segmentation/l4r_spring_yolo26n_sanity/weights/best.pt'))
for record in [json.loads(s) for s in (folder/'decisions.jsonl').read_text().splitlines()]:
    if record['phase']!='vision': continue
    image=cv2.imread(str(folder/f"t0_{record['cycle']:02d}_2_raw.png"))
    state=VehicleState(**record['frames'][2]['state'])
    results=model.predict(image,device='cpu',conf=.15,retina_masks=True,verbose=False)[0]
    print('cycle',record['cycle'],'truth',record['truth'])
    if results.masks is None: print('no masks'); continue
    cv2.imwrite(str(folder/f"diagnostic_{record['cycle']:02d}_overlay.jpg"),results.plot())
    for width in [2.,3.]:
        fitter=MetricRailGeometry(projector,half_width_m=width)
        for mask in results.masks.data:
            result,bird=fitter.estimate(mask.cpu().numpy(),state)
            print('half_width',width,'result',result,flush=True)
            cv2.imwrite(str(folder/f"diagnostic_{record['cycle']:02d}_w{width}_mask.png"),bird)
            coverage=projector.birdseye(np.ones(image.shape[:2],np.uint8)*255,state,half_width_m=width)
            counts=dict(empty=0,clipped=0,width=0,accepted=0); points=[]
            for row in range(75,301):
                cols=np.flatnonzero(bird[row]); visible=np.flatnonzero(coverage[row])
                if len(cols)<5 or len(visible)<5: counts['empty']+=1; continue
                if cols[0]<=visible[0]+1 or cols[-1]>=visible[-1]-1: counts['clipped']+=1; continue
                if not .65*1.59<=(cols[-1]-cols[0])*.02<=1.35*1.59: counts['width']+=1; continue
                counts['accepted']+=1; points.append([8-row*.02,(cols[0]+cols[-1])*.01-width])
            print('rows',counts,'span',np.ptp(np.array(points)[:,0]) if points else 0,flush=True)
