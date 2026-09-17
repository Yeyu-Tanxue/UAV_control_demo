"""Independent Rodrigues-axis check of FLU/FRD roll and pitch signs."""
import math
import unittest
import numpy as np
from uav_demo.camera_geometry import _rpy_rotation


class PoseConventionTests(unittest.TestCase):
    def test_basis_conversion_keeps_roll_and_flips_pitch(self):
        roll,pitch=.17,-.23
        cr,sr=math.cos(roll),math.sin(roll)
        cp,sp=math.cos(-pitch),math.sin(-pitch)
        flu_roll=np.array([[1,0,0],[0,cr,-sr],[0,sr,cr]])
        flu_pitch=np.array([[cp,0,sp],[0,1,0],[-sp,0,cp]])
        change=np.diag([1,-1,-1])
        expected=change @ flu_pitch @ flu_roll @ change
        np.testing.assert_allclose(_rpy_rotation(roll,pitch,0),expected,atol=1e-12)
