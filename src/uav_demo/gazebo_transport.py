"""Gazebo Transport sources used only by SITL validation.

Images retain both their simulator exposure time and host callback time.
Gazebo pose truth is kept on the simulator clock and never enters control.
"""
from __future__ import annotations

import asyncio
from bisect import bisect_left
from collections import deque
from dataclasses import dataclass
import math
from pathlib import Path
import sys
import threading
import time

import numpy as np

from .onboard_vision import CapturedFrame


def _gz_imports():
    try:
        from gz.transport13 import Node
        from gz.msgs10.image_pb2 import Image
        from gz.msgs10.pose_v_pb2 import Pose_V
    except ModuleNotFoundError:
        # Debian installs Gazebo bindings outside ordinary venv paths.
        system_packages=Path('/usr/lib/python3/dist-packages')
        if system_packages.exists() and str(system_packages) not in sys.path:
            sys.path.append(str(system_packages))
        from gz.transport13 import Node
        from gz.msgs10.image_pb2 import Image
        from gz.msgs10.pose_v_pb2 import Pose_V
    return Node,Image,Pose_V


def _stamp_s(header) -> float:
    return float(header.stamp.sec)+float(header.stamp.nsec)*1e-9


def _image_to_bgr(message) -> np.ndarray:
    if message.pixel_format_type not in (3,8):  # RGB_INT8, BGR_INT8
        raise ValueError(
            f'unsupported Gazebo pixel format {message.pixel_format_type}')
    if message.step < message.width*3:
        raise ValueError('Gazebo image row stride is too short')
    expected=int(message.height)*int(message.step)
    if len(message.data)!=expected:
        raise ValueError('Gazebo image payload size mismatch')
    rows=np.frombuffer(message.data,dtype=np.uint8).reshape(
        int(message.height),int(message.step))
    image=rows[:,:int(message.width)*3].reshape(
        int(message.height),int(message.width),3)
    if message.pixel_format_type==3:
        image=image[:,:,::-1]
    return np.ascontiguousarray(image)


class GazeboTransportFrameSource:
    """Receive camera frames directly, preserving the simulator timestamp."""

    def __init__(self,topic: str,timeout_s: float=3.) -> None:
        Node,Image,_=_gz_imports()
        self._topic=topic
        self._timeout_s=timeout_s
        self._lock=threading.Lock()
        self._latest=None
        self._received_index=0
        self._consumed_index=0
        self._callback_error=None
        self._node=Node()
        self._node.subscribe(Image,topic,self._on_image)

    def _on_image(self,message) -> None:
        try:
            image=_image_to_bgr(message)
            metadata={item.key:list(item.value)
                      for item in message.header.data}
            sequence=(metadata.get('seq') or ['unknown'])[0]
            frame=CapturedFrame(
                image=image,
                source_id=f'gz:{self._topic}:seq={sequence}',
                timestamp_s=time.monotonic(),
                clock='host_monotonic_approximate',
                timestamp_quality='gazebo_transport_callback_receive',
                source_timestamp_s=_stamp_s(message.header),
                source_clock='gazebo_simulation')
            with self._lock:
                self._received_index+=1
                self._latest=(self._received_index,frame)
                self._callback_error=None
        except BaseException as exc:
            with self._lock:
                self._callback_error=exc

    async def capture(self) -> CapturedFrame:
        deadline=time.monotonic()+self._timeout_s
        while time.monotonic()<deadline:
            with self._lock:
                error=self._callback_error
                latest=self._latest
                if latest is not None and latest[0]>self._consumed_index:
                    self._consumed_index=latest[0]
                    return latest[1]
            if error is not None:
                raise RuntimeError('Gazebo image callback failed') from error
            await asyncio.sleep(.01)
        raise TimeoutError(f'no new Gazebo image on {self._topic}')


@dataclass(frozen=True)
class GazeboPoseTruth:
    timestamp_s: float
    body_xyz: tuple[float,float,float]
    heading_rad: float


def _pose_truth(message,model_name: str) -> GazeboPoseTruth | None:
    model=next((pose for pose in message.pose if pose.name==model_name),None)
    if model is None:
        return None
    p=model.position; q=model.orientation
    # Model root to PX4 base_link is +0.24 m on model Z.
    body=(float(p.x)+.24*2*(q.x*q.z+q.w*q.y),
          float(p.y)+.24*2*(q.y*q.z-q.w*q.x),
          float(p.z)+.24*(1-2*(q.x*q.x+q.y*q.y)))
    yaw=math.atan2(2*(q.w*q.z+q.x*q.y),
                   1-2*(q.y*q.y+q.z*q.z))
    return GazeboPoseTruth(_stamp_s(message.header),body,yaw)


class GazeboPoseTruthBuffer:
    """Thread-safe simulator-clock pose history for independent evaluation."""

    def __init__(self,topic: str,model_name='x500_mono_cam_0',
                 capacity=4000,max_gap_s=.1) -> None:
        Node,_,Pose_V=_gz_imports()
        self._model_name=model_name
        self._samples=deque(maxlen=capacity)
        self._lock=threading.Lock()
        self.max_gap_s=max_gap_s
        self._node=Node()
        self._node.subscribe(Pose_V,topic,self._on_pose)

    def _on_pose(self,message) -> None:
        sample=_pose_truth(message,self._model_name)
        if sample is None:
            return
        with self._lock:
            if not self._samples or sample.timestamp_s>self._samples[-1].timestamp_s:
                self._samples.append(sample)

    def latest_timestamp(self) -> float | None:
        with self._lock:
            return self._samples[-1].timestamp_s if self._samples else None

    def latest(self) -> GazeboPoseTruth | None:
        with self._lock:
            return self._samples[-1] if self._samples else None

    def at(self,timestamp_s: float) -> GazeboPoseTruth:
        with self._lock:
            samples=list(self._samples)
        stamps=[sample.timestamp_s for sample in samples]
        index=bisect_left(stamps,timestamp_s)
        if index<len(samples) and samples[index].timestamp_s==timestamp_s:
            return samples[index]
        if index==0 or index==len(samples):
            raise ValueError('Gazebo truth timestamp not bracketed')
        before,after=samples[index-1:index+1]
        gap=after.timestamp_s-before.timestamp_s
        if gap>self.max_gap_s:
            raise ValueError('Gazebo truth gap too large')
        fraction=(timestamp_s-before.timestamp_s)/gap
        xyz=tuple(a+fraction*(b-a)
                  for a,b in zip(before.body_xyz,after.body_xyz))
        delta=math.atan2(math.sin(after.heading_rad-before.heading_rad),
                         math.cos(after.heading_rad-before.heading_rad))
        return GazeboPoseTruth(
            timestamp_s,xyz,before.heading_rad+fraction*delta)
