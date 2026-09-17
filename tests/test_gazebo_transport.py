from collections import deque
from types import SimpleNamespace
import math
import threading
import unittest

import numpy as np

from uav_demo.gazebo_transport import (
    GazeboPoseTruth, GazeboPoseTruthBuffer, _image_to_bgr, _pose_truth,
)


class GazeboTransportTests(unittest.TestCase):
    def test_rgb_payload_is_converted_to_contiguous_bgr(self):
        message=SimpleNamespace(
            pixel_format_type=3,width=2,height=1,step=8,
            data=bytes([1,2,3,4,5,6,99,99]))
        image=_image_to_bgr(message)
        np.testing.assert_array_equal(
            image,np.array([[[3,2,1],[6,5,4]]],dtype=np.uint8))
        self.assertTrue(image.flags['C_CONTIGUOUS'])

    def test_pose_truth_uses_model_pose_and_base_link_offset(self):
        stamp=SimpleNamespace(sec=2,nsec=500_000_000)
        pose=SimpleNamespace(
            name='vehicle',
            position=SimpleNamespace(x=1.,y=2.,z=3.),
            orientation=SimpleNamespace(x=0.,y=0.,z=0.,w=1.))
        result=_pose_truth(
            SimpleNamespace(header=SimpleNamespace(stamp=stamp),pose=[pose]),
            'vehicle')
        self.assertEqual(result.timestamp_s,2.5)
        self.assertEqual(result.body_xyz,(1.,2.,3.24))
        self.assertEqual(result.heading_rad,0.)

    def test_truth_interpolation_wraps_heading(self):
        buffer=object.__new__(GazeboPoseTruthBuffer)
        buffer.max_gap_s=.2
        buffer._lock=threading.Lock()
        buffer._samples=deque([
            GazeboPoseTruth(1.,(0.,0.,1.),math.radians(179)),
            GazeboPoseTruth(1.1,(2.,4.,3.),math.radians(-179))])
        result=buffer.at(1.05)
        np.testing.assert_allclose(result.body_xyz,(1.,2.,2.))
        self.assertAlmostEqual(abs(result.heading_rad),math.pi)


if __name__=='__main__':
    unittest.main()
