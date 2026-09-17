import math
import unittest
import numpy as np
from uav_demo.metric_rail_geometry import MetricRailGeometry


class BirdSource:
    def birdseye(self,mask,state,**kwargs): return mask


class MetricRailTests(unittest.TestCase):
    def mask(self,offset=.2,heading=4):
        image=np.zeros((400,200),np.uint8)
        for row in range(400):
            centre=offset+math.tan(math.radians(heading))*(8-row*.02)
            left=round((centre-.795+2)/.02)
            right=round((centre+.795+2)/.02)
            image[row,max(0,left):min(200,right+1)]=1
        return image

    def test_known_offset_and_heading_in_metres(self):
        result,_=MetricRailGeometry(BirdSource()).estimate(self.mask(),None)
        self.assertIsNotNone(result)
        self.assertAlmostEqual(result.lateral_error_m,.2,delta=.02)
        self.assertAlmostEqual(result.heading_error_deg,4,delta=.3)

    def test_clipped_or_missing_rail_is_rejected(self):
        for mask in [np.zeros((400,200)),np.ones((400,200))]:
            result,_=MetricRailGeometry(BirdSource()).estimate(mask,None)
            self.assertIsNone(result)

    def test_negative_offset_is_left(self):
        result,_=MetricRailGeometry(BirdSource()).estimate(self.mask(-.3,-3),None)
        self.assertAlmostEqual(result.lateral_error_m,-.3,delta=.02)
        self.assertAlmostEqual(result.heading_error_deg,-3,delta=.3)

    def test_disconnected_background_islands_do_not_set_boundaries(self):
        mask=self.mask()
        mask[75:301,10:15]=1
        result,_=MetricRailGeometry(BirdSource()).estimate(mask,None)
        self.assertIsNotNone(result)
        self.assertAlmostEqual(result.lateral_error_m,.2,delta=.02)
        self.assertAlmostEqual(result.heading_error_deg,4,delta=.3)

    def test_wide_window_keeps_combined_offset_and_yaw(self):
        mask=np.zeros((400,300),np.uint8)
        for row in range(400):
            centre=.44+math.tan(math.radians(10))*(8-row*.02)
            left=round((centre-.795+3)/.02)
            right=round((centre+.795+3)/.02)
            mask[row,max(0,left):min(300,right+1)]=1
        result,_=MetricRailGeometry(BirdSource(),half_width_m=3).estimate(mask,None)
        self.assertIsNotNone(result)
        self.assertAlmostEqual(result.lateral_error_m,.44,delta=.02)
        self.assertAlmostEqual(result.heading_error_deg,10,delta=.3)
