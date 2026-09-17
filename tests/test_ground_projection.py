import math
from pathlib import Path
import unittest
import numpy as np
from uav_demo.camera_geometry import load_gazebo_camera_geometry
from uav_demo.ground_projection import VehicleState, VehicleStateBuffer, DynamicGroundProjector


class ProjectionTests(unittest.TestCase):
    def setUp(self):
        models = Path(__file__).resolve().parents[1]/"simulation/gazebo/models"
        g = load_gazebo_camera_geometry(models/"mono_cam/model.sdf",models/"x500_mono_cam/model.sdf")
        self.projector = DynamicGroundProjector(g.intrinsics,g.mount)

    def test_level_centre_ray_has_analytic_ground_intersection(self):
        state = VehicleState(1,0,0,0,2.45)
        points,valid = self.projector.pixels_to_ground([[320,240],[400,240]],state)
        self.assertTrue(valid.all())
        self.assertAlmostEqual(points[0,0],0.12+(2.45-0.06)/math.tan(math.radians(35)),places=8)
        self.assertAlmostEqual(points[0,1],0)
        self.assertGreater(points[1,1],0)

    def test_round_trip_under_roll_pitch_and_height_changes(self):
        ground = np.array([[3.,-.3],[4.,.2],[6.,0.]])
        for height in [1.,2.45,3.]:
            for roll,pitch in [(0,0),(.1,-.2),(-.2,.1)]:
                state = VehicleState(1,roll,pitch,1.2,height)
                h = self.projector.ground_to_image_homography(state)
                uvw = np.column_stack((ground,np.ones(3))) @ h.T
                recovered,valid = self.projector.pixels_to_ground(uvw[:,:2]/uvw[:,2,None],state)
                self.assertTrue(valid.all())
                np.testing.assert_allclose(recovered,ground,atol=1e-9)

    def test_sky_ray_rejected(self):
        _,valid = self.projector.pixels_to_ground([[320,0]],VehicleState(1,0,0,0,2))
        self.assertFalse(valid[0])

    def test_heading_frame_is_yaw_invariant(self):
        a = self.projector.ground_to_image_homography(VehicleState(1,.1,.1,0,2))
        b = self.projector.ground_to_image_homography(VehicleState(1,.1,.1,2,2))
        np.testing.assert_allclose(a,b)

    def test_buffer_wrap_gap_and_clock(self):
        b = VehicleStateBuffer(max_gap_s=.3)
        b.add(VehicleState(1,0,0,math.radians(179),2))
        b.add(VehicleState(1.2,0,0,math.radians(-179),3))
        s = b.at(1.1)
        self.assertAlmostEqual(abs(s.yaw_rad),math.pi)
        self.assertAlmostEqual(s.body_agl_m,2.5)
        for stamp in [.9,1.3]:
            with self.assertRaises(ValueError): b.at(stamp)
        with self.assertRaises(ValueError): b.at(1.1,clock="simulation")
        b.add(VehicleState(2,0,0,0,3))
        with self.assertRaises(ValueError): b.at(1.5)

    def test_birdseye_shape_and_calibration_guard(self):
        state = VehicleState(1,0,0,0,2)
        image = np.zeros((480,640,3),np.uint8)
        self.assertEqual(self.projector.birdseye(image,state).shape,(400,200,3))
        with self.assertRaises(ValueError): self.projector.birdseye(image[:200],state)


if __name__ == "__main__":
    unittest.main()
