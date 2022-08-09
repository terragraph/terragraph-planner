# Copyright (c) Meta Platforms, Inc. and affiliates.

# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

import math
from unittest import TestCase

from terragraph_planner.common.exceptions import GeoSystemException
from terragraph_planner.common.geos import (
    GeoLocation,
    _law_of_cosines,
    bearing_in_degrees,
    haversine_distance,
    law_of_cosines_spherical,
)


class TestGeos(TestCase):
    def test_ll_location(self) -> None:
        """
        Test a GeoLocation initialized with latitude and longitude
        """
        geo_location = GeoLocation(latitude=0.1, longitude=1.2)
        self.assertIsNone(geo_location._utm_x)
        self.assertIsNone(geo_location._utm_y)
        self.assertIsNotNone(geo_location.utm_x)
        self.assertIsNotNone(geo_location.utm_y)
        self.assertIsNone(geo_location.altitude)
        utm_x1 = geo_location.utm_x
        utm_y1 = geo_location.utm_y
        geo_location = GeoLocation(latitude=1.0, longitude=1.2)
        self.assertNotEqual(geo_location.utm_x, utm_x1)
        self.assertNotEqual(geo_location.utm_y, utm_y1)

    def test_utm_location(self) -> None:
        """
        Test a GeoLocation initialized with utm coordinates
        """
        geo_location = GeoLocation(
            utm_x=123.4,
            utm_y=567.8,
            utm_epsg=32631,
            altitude=9.0,
        )
        self.assertIsNone(geo_location._latitude)
        self.assertIsNotNone(geo_location.latitude)
        self.assertIsNotNone(geo_location.longitude)
        self.assertIsNotNone(geo_location.altitude)
        latitude1 = geo_location.latitude
        longitude1 = geo_location.longitude
        geo_location = GeoLocation(
            utm_x=1234.5,
            utm_y=567.8,
            utm_epsg=32631,
            altitude=9.0,
        )
        self.assertNotEqual(geo_location.latitude, latitude1)
        self.assertNotEqual(geo_location.longitude, longitude1)

    def test_invalid_location(self) -> None:
        """
        Test locations that failed to be initialized
        """
        with self.assertRaises(GeoSystemException):
            GeoLocation(latitude=1, utm_x=2)
        with self.assertRaises(GeoSystemException):
            GeoLocation(latitude=180, longitude=0)
        with self.assertRaises(GeoSystemException):
            GeoLocation(utm_x=1, utm_y=2, utm_epsg=32777)

    def test_haversine_distance(self) -> None:
        location1 = GeoLocation(latitude=0.02, longitude=0.03)
        location2 = GeoLocation(latitude=0.025, longitude=0.035)
        distance1 = haversine_distance(
            location1.longitude,
            location1.latitude,
            location2.longitude,
            location2.latitude,
        )
        distance2 = math.sqrt(
            (location1.utm_x - location2.utm_x)
            * (location1.utm_x - location2.utm_x)
            + (location1.utm_y - location2.utm_y)
            * (location1.utm_y - location2.utm_y)
        )
        self.assertLess(abs(distance1 - distance2) / distance2, 1e-2)

    def test_bearing_in_degrees(self) -> None:
        location1 = GeoLocation(latitude=0.02, longitude=0.03)
        location2 = GeoLocation(latitude=0.025, longitude=0.045)
        bearing1 = bearing_in_degrees(
            location1.longitude,
            location1.latitude,
            location2.longitude,
            location2.latitude,
        )
        bearing2: float = abs(
            math.degrees(
                math.atan(
                    (location1.utm_x - location2.utm_x)
                    / (location1.utm_y - location2.utm_y)
                )
            )
        )
        self.assertLess(abs(bearing1 - bearing2) / bearing2, 1e-2)

    def test_law_of_cosines_spherical(self) -> None:
        """
        Test spherical law of cosines
        """
        # Test sites at a nearly 45 degree angle from each other
        loc0 = GeoLocation(utm_x=0, utm_y=0, utm_epsg=32631)
        loc1 = GeoLocation(utm_x=100, utm_y=0, utm_epsg=32631)
        loc2 = GeoLocation(utm_x=150, utm_y=150, utm_epsg=32631)

        angle, ratio = law_of_cosines_spherical(
            loc0.latitude,
            loc0.longitude,
            loc1.latitude,
            loc1.longitude,
            loc2.latitude,
            loc2.longitude,
        )
        self.assertAlmostEqual(angle, 45, delta=0.2)
        self.assertAlmostEqual(ratio, math.sqrt(2 * 1.5 * 1.5), delta=0.01)

        # Test situations where the angle is very close to 180 and precision
        # errors can cause the cosine ratio to fall just barely outside of
        # acceptable ranges (so it needs to be clamped to a valid range)
        len1 = 1.0
        len2 = 1.0
        len3 = 2.0000001
        angle = _law_of_cosines(len1, len2, len3)
        self.assertEqual(angle, 180)

        # Test situations where the angle is very close to 0 and precision
        # errors can cause the cosine ratio to fall just barely outside of
        # acceptable ranges (so it needs to be clamped to a valid range)
        len1 = 1.0
        len2 = 2.0000001
        len3 = 1.0
        angle = _law_of_cosines(len1, len2, len3)
        self.assertEqual(angle, 0)

        # Test to catch invalid inputs
        lat0 = 37.3292165639
        lon0 = -121.901700882

        lat1 = 37.3292090176
        lon1 = -121.900888308

        with self.assertRaises(AssertionError):
            law_of_cosines_spherical(lat0, lon0, lat1, lon1, lat0, lon0)
