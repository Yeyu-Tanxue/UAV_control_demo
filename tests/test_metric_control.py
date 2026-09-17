from dataclasses import asdict
import unittest
from uav_demo.metric_rail_geometry import MetricRailEstimate
from uav_demo.metric_control import metric_command

class MetricControlTests(unittest.TestCase):
    def estimate(self,lateral,heading):
        return MetricRailEstimate(lateral,heading,lateral,1.59,.01,100,2,6)
    def test_right_track_commands_right_and_clockwise(self):
        c=metric_command(self.estimate(.4,10))
        self.assertEqual(c.right_m_s,.12)
        self.assertEqual(c.yaw_rate_deg_s,6)
        self.assertEqual(c.forward_m_s,0)
    def test_left_track_is_symmetric(self):
        c=metric_command(self.estimate(-.4,-10))
        self.assertEqual(c.right_m_s,-.12)
        self.assertEqual(c.yaw_rate_deg_s,-6)
    def test_invalid_and_outside_envelope_hold(self):
        for e in [None,self.estimate(float('nan'),0),self.estimate(.8,0),self.estimate(0,20)]:
            self.assertEqual(tuple(asdict(metric_command(e)).values()),(0.,0.,0.))
    def test_forward_requires_alignment_and_permission(self):
        e=self.estimate(.01,.5)
        self.assertEqual(metric_command(e).forward_m_s,0)
        self.assertEqual(metric_command(e,allow_forward=True).forward_m_s,.1)
        self.assertEqual(metric_command(self.estimate(.2,.5),allow_forward=True).forward_m_s,0)
