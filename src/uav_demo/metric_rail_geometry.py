"""Straight-track metric geometry from an original-size YOLO mask.

Offsets describe the track relative to the vehicle: positive is right.
State height must be relative to the chosen rail plane, not arbitrary ground.
"""
from dataclasses import dataclass
import math
import cv2
import numpy as np


@dataclass(frozen=True)
class MetricRailEstimate:
    lateral_error_m: float
    heading_error_deg: float
    centre_at_3m_m: float
    width_m: float
    residual_m: float
    valid_rows: int
    observed_forward_min_m: float
    observed_forward_max_m: float


class MetricRailGeometry:
    def __init__(self, projector, nominal_width_m=1.59, half_width_m=2.):
        self.projector=projector
        self.nominal_width_m=nominal_width_m
        if not math.isfinite(half_width_m) or half_width_m <= 0:
            raise ValueError('positive finite birdseye half width required')
        self.half_width_m=half_width_m

    def estimate(self, original_mask, state):
        mask=(np.asarray(original_mask)>.5).astype(np.uint8)*255
        # A segmentation instance may contain disconnected background islands.
        # They must not become the left/right boundaries of the ego corridor.
        count,labels,stats,_=cv2.connectedComponentsWithStats(mask,connectivity=8)
        if count>1:
            largest=1+int(np.argmax(stats[1:,cv2.CC_STAT_AREA]))
            mask=(labels==largest).astype(np.uint8)*255
        bird=self.projector.birdseye(mask,state,half_width_m=self.half_width_m)
        coverage=self.projector.birdseye(np.ones_like(mask)*255,state,half_width_m=self.half_width_m)
        points=[]
        for row in range(75,301):  # observed forward range 2.0 to 6.5 m
            cols=np.flatnonzero(bird[row])
            if len(cols)<5: continue
            # Reject clipped masks: their centre is not observable.
            visible=np.flatnonzero(coverage[row])
            if len(visible)<5: continue
            if cols[0]<=visible[0]+1 or cols[-1]>=visible[-1]-1: continue
            width=(cols[-1]-cols[0])*.02
            if not .65*self.nominal_width_m <= width <= 1.35*self.nominal_width_m: continue
            points.append([8-row*.02,(cols[0]+cols[-1])*.01-self.half_width_m,width])
        if len(points)<40: return None,bird
        p=np.array(points)
        keep=np.ones(len(p),bool)
        for _ in range(3):
            slope,offset=np.polyfit(p[keep,0],p[keep,1],1)
            residual=np.abs(p[:,1]-(slope*p[:,0]+offset))
            threshold=max(.04,3*float(np.median(residual[keep])))
            updated=residual<=threshold
            if updated.sum()<40: break
            keep=updated
        p=p[keep]
        if np.ptp(p[:,0])<2: return None,bird
        slope,offset=np.polyfit(p[:,0],p[:,1],1)
        residual=float(np.sqrt(np.mean((p[:,1]-(slope*p[:,0]+offset))**2)))
        if residual>.12: return None,bird
        return MetricRailEstimate(float(offset),math.degrees(math.atan(slope)),
            float(offset+3*slope),float(np.median(p[:,2])),residual,len(p),
            float(p[:,0].min()),float(p[:,0].max())),bird
