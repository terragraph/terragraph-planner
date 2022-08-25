# Copyright (c) Meta Platforms, Inc. and affiliates.

# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

import math
from typing import Dict, Optional, Tuple, Union, cast

import numpy as np
from pyproj import Transformer
from pyre_extensions import none_throws

from terragraph_planner.common.constants import (
    EARTH_RADIUS,
    FULL_ROTATION_ANGLE,
    LAT_LON_EPSG,
    LAT_LON_TO_GEO_HASH_PRECISION,
    STRAIGHT_ANGLE,
)
from terragraph_planner.common.exceptions import (
    GeoSystemException,
    planner_assert,
)

GEOHASH_SEED = "0123456789abcdefghijklmnopqrstuv"


class GeoLocation:
    """
    This class represents a 2-D or 3-D geographical location and supports
    latitude & longitude or utm coordinates.
    """

    def __init__(
        self,
        latitude: Optional[float] = None,
        longitude: Optional[float] = None,
        utm_x: Optional[float] = None,
        utm_y: Optional[float] = None,
        utm_epsg: Optional[int] = None,
        altitude: Optional[float] = None,
    ) -> None:
        """
        Initialize a location instance with latitude and longitude or
        utm coordinates. Altitude is optional in either case.
        """
        if latitude is not None and longitude is not None:
            planner_assert(
                -90 <= latitude <= 90,
                "Latitude must be between [-90, 90].",
                GeoSystemException,
            )
            planner_assert(
                -180 <= longitude <= 180,
                "Longitude must be between [-180, 180]",
                GeoSystemException,
            )
            self._latitude: Optional[float] = latitude
            self._longitude: Optional[float] = longitude
            self._utm_x: Optional[float] = None
            self._utm_y: Optional[float] = None
            self._utm_epsg: Optional[int] = None
        elif utm_x is not None and utm_y is not None and utm_epsg is not None:
            planner_assert(
                32600 < utm_epsg <= 32660 or 32700 < utm_epsg <= 32760,
                "UTM EPSG must be between (32600, 32660] or (32700, 32760].",
                GeoSystemException,
            )
            self._latitude: Optional[float] = None
            self._longitude: Optional[float] = None
            self._utm_x: Optional[float] = utm_x
            self._utm_y: Optional[float] = utm_y
            self._utm_epsg: Optional[int] = utm_epsg
        else:
            raise GeoSystemException(
                "Please initialize a geograghical location with either "
                "[latitude, longitutde] or [utm_x, utm_y, utm_epsg]."
            )
        self._altitude: Optional[float] = altitude

    @property
    def latitude(self) -> float:
        if self._latitude is None:
            self._update_lat_lon()
        return none_throws(self._latitude)

    @property
    def longitude(self) -> float:
        if self._longitude is None:
            self._update_lat_lon()
        return none_throws(self._longitude)

    @property
    def utm_x(self) -> float:
        if self._utm_x is None:
            self._update_utm()
        return none_throws(self._utm_x)

    @property
    def utm_y(self) -> float:
        if self._utm_y is None:
            self._update_utm()
        return none_throws(self._utm_y)

    @property
    def utm_epsg(self) -> int:
        if self._utm_epsg is None:
            self._update_utm()
        return none_throws(self._utm_epsg)

    @property
    def altitude(self) -> Optional[float]:
        return self._altitude

    def copy(
        self, **kwargs: Union[Optional[float], Optional[int]]
    ) -> "GeoLocation":
        """
        Creates a new GeoLocation instance with attribute values taken from kwargs when they exist
        and defaulting to self's attribute values otherwise.
        NOTE: this is not __copy__ or __deepcopy__ and is not intended for the same purpose.
        """
        return GeoLocation(
            latitude=kwargs.get("latitude", self._latitude),
            longitude=kwargs.get("longitude", self._longitude),
            utm_x=kwargs.get("utm_x", self._utm_x),
            utm_y=kwargs.get("utm_y", self._utm_y),
            utm_epsg=cast(
                Optional[int], kwargs.get("utm_epsg", self._utm_epsg)
            ),
            altitude=kwargs.get("altitude", self._altitude),
        )

    def _update_lat_lon(self) -> None:
        utm_to_ll = TransformerLib.get_tranformer(
            crs_from=none_throws(self._utm_epsg), crs_to=LAT_LON_EPSG
        )
        self._longitude, self._latitude = utm_to_ll.transform(
            self._utm_x, self._utm_y
        )

    def _reset_lat_lon(self) -> None:
        self._latitude = None
        self._longitude = None

    def _update_utm(self) -> None:
        self._utm_epsg = lat_lon_to_utm_epsg(self.latitude, self.longitude)
        ll_to_utm = TransformerLib.get_tranformer(
            crs_from=LAT_LON_EPSG, crs_to=self._utm_epsg
        )
        self._utm_x, self._utm_y = ll_to_utm.transform(
            self.longitude, self.latitude
        )

    def _reset_utm(self) -> None:
        self._utm_x = None
        self._utm_y = None
        self._utm_epsg = None


class TransformerLib:
    _transformer_dict: Dict[Tuple[int, int], Transformer] = {}

    @staticmethod
    def get_tranformer(crs_from: int, crs_to: int) -> Transformer:
        if (crs_from, crs_to) not in TransformerLib._transformer_dict:
            TransformerLib._transformer_dict[
                (crs_from, crs_to)
            ] = Transformer.from_crs(
                crs_from=crs_from, crs_to=crs_to, always_xy=True
            )
        return TransformerLib._transformer_dict[(crs_from, crs_to)]


def _longitude_to_utm_zone(longitude: float) -> int:
    """
    Stolen from Wikipedia:
    The UTM system divides the surface of Earth between 80°S and 84°N latitude
    into 60 zones, each 6° of longitude in width. Zone 1 covers longitude
    180° to 174° W; zone numbering increases eastward to zone 60 that covers
    longitude 174 to 180 East.
    """
    return int(math.floor((longitude + 180) / 6) % 60) + 1


def angle_delta(angle1: float, angle2: float) -> float:
    """
    Computes angle1 - angle2 with result in (-180, 180].
    """
    dev = angle1 - angle2
    return (
        dev - FULL_ROTATION_ANGLE
        if dev > STRAIGHT_ANGLE
        else dev + FULL_ROTATION_ANGLE
        if dev <= -STRAIGHT_ANGLE
        else dev
    )


def lat_lon_to_utm_epsg(latitutde: float, longitude: float) -> int:
    """
    Transform from WGS84 to a UTM Zone (Mercator) coordinate system.
    """
    band = _longitude_to_utm_zone(longitude)
    return 32600 + band if latitutde >= 0 else 32700 + band


def lat_lon_to_geo_hash(latitutde: float, longitude: float) -> str:
    lat_range, lon_range = [-90.0, 90.0], [-180.0, 180.0]

    planner_assert(
        lat_range[0] <= latitutde and latitutde <= lat_range[1],
        f"Geohash for latitude {latitutde} not in valid range",
        GeoSystemException,
    )
    planner_assert(
        lon_range[0] <= longitude and longitude <= lon_range[1],
        f"Geohash for longitude {longitude} not in valid range",
        GeoSystemException,
    )

    geohash_string = ""
    odd_bit = False
    bitvals = [16, 8, 4, 2, 1]
    for _ in range(LAT_LON_TO_GEO_HASH_PRECISION):
        # execute once per character in our output geohash
        character_bits = 0
        for bit in bitvals:
            if odd_bit:
                # splitting latitude in half
                center = sum(lat_range) / 2
                if latitutde < center:
                    lat_range = [lat_range[0], center]
                    # bit already 0, so no change needed
                else:
                    # when input latitutde is bigger, encode in our character_bits
                    lat_range = [center, lat_range[1]]
                    character_bits |= bit
            else:
                # even_bit, so split longitude
                center = sum(lon_range) / 2
                if longitude < center:
                    lon_range = [lon_range[0], center]
                    # bit already 0, so no change needed
                else:
                    # encode character_bits if longitude is bigger than center
                    lon_range = [center, lon_range[1]]
                    character_bits |= bit
            odd_bit = not odd_bit
        geohash_string += GEOHASH_SEED[character_bits]
    return geohash_string


def haversine_distance(
    longitude_a: float, latitude_a: float, longitude_b: float, latitude_b: float
) -> float:
    """
    Compute the Haversine distance, i.e., the shortest distance between two points on the surface of a sphere.
    See, e.g., http://www.movable-type.co.uk/scripts/latlong.html for details.
    """
    latitude_delta = latitude_b - latitude_a
    longitude_delta = longitude_b - longitude_a

    half_chord_length_squared = np.sin(
        np.radians(latitude_delta) / 2.0
    ) ** 2 + np.cos(np.radians(latitude_a)) * np.cos(np.radians(latitude_b)) * (
        np.sin(np.radians(longitude_delta) / 2.0) ** 2
    )

    angular_distance = 2 * np.arctan2(
        np.sqrt(half_chord_length_squared),
        np.sqrt(1 - half_chord_length_squared),
    )

    return EARTH_RADIUS * angular_distance


def translate_point(
    longitude: float, latitude: float, bearing: float, distance: float
) -> Tuple[float, float]:
    d = distance / EARTH_RADIUS

    new_latitude = np.arcsin(
        np.sin(np.radians(latitude)) * np.cos(d)
        + np.cos(np.radians(latitude)) * np.sin(d) * np.cos(np.radians(bearing))
    )

    longitude_delta = np.arctan2(
        np.sin(np.radians(bearing)) * np.sin(d) * np.cos(np.radians(latitude)),
        np.cos(d) - np.sin(np.radians(latitude)) * np.sin(new_latitude),
    )

    return (longitude + np.degrees(longitude_delta), np.degrees(new_latitude))


def grid_deltas(
    starting_longitude: float, starting_latitude: float, grid_spacing: float
) -> Tuple[float, float]:
    first_east = translate_point(
        starting_longitude, starting_latitude, 90, grid_spacing
    )
    longitude_delta = first_east[0] - starting_longitude

    first_north = translate_point(
        starting_longitude, starting_latitude, 0, grid_spacing
    )
    latitude_delta = first_north[1] - starting_latitude

    return (longitude_delta, latitude_delta)


def _law_of_cosines(len1: float, len2: float, len3: float) -> float:
    assert len1 > 0 and len2 > 0
    if len3 == 0:
        return 0
    # Use law of cosines to estimate the angle
    cosine_ratio = ((len1**2) + (len2**2) - (len3**2)) / (2 * len1 * len2)
    # Clamp the cosine_ratio to range [-1,1]; numerical precision issues can
    # cause the cosine ratio to fall just barely outside of acceptable ranges.
    cosine_ratio = min(1, max(-1, cosine_ratio))
    angle = np.degrees(np.arccos(cosine_ratio))
    return angle


def _get_length_ratio(len1: float, len2: float) -> float:
    assert len1 > 0 and len2 > 0
    return max(len1, len2) / min(len1, len2)


def law_of_cosines_spherical(
    lat0: float, lon0: float, lat1: float, lon1: float, lat2: float, lon2: float
) -> Tuple[float, float]:
    """
    This function computes the angle between straight lines
    point0->point1 and point0->point2 using law of cosines
    """
    len1 = haversine_distance(lon0, lat0, lon1, lat1)
    len2 = haversine_distance(lon0, lat0, lon2, lat2)
    len3 = haversine_distance(lon1, lat1, lon2, lat2)

    return (_law_of_cosines(len1, len2, len3), _get_length_ratio(len1, len2))


def law_of_cosines_utm(
    x0: float, y0: float, x1: float, y1: float, x2: float, y2: float
) -> float:
    """
    This function computes the angle between straight lines
    point0->point1 and point0->point2 using law of cosines, where
    x,y have been projected into a UTM coordinate system
    """
    len1 = np.sqrt((x1 - x0) ** 2 + (y1 - y0) ** 2)
    len2 = np.sqrt((x2 - x0) ** 2 + (y2 - y0) ** 2)
    len3 = np.sqrt((x2 - x1) ** 2 + (y2 - y1) ** 2)

    return _law_of_cosines(len1, len2, len3)


def bearing_in_degrees(
    longitude_a: float, latitude_a: float, longitude_b: float, latitude_b: float
) -> float:
    """
    Compute the bearing, or the heading angle between two points with lat/lon coordinates
    """
    longitude_delta = longitude_b - longitude_a
    x = np.cos(np.radians(latitude_b)) * np.sin(np.radians(longitude_delta))
    y = np.cos(np.radians(latitude_a)) * np.sin(np.radians(latitude_b)) - (
        np.sin(np.radians(latitude_a))
        * np.cos(np.radians(latitude_b))
        * np.cos(np.radians(longitude_delta))
    )

    return np.degrees(np.arctan2(x, y)) % 360
