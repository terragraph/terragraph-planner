# Copyright (c) Meta Platforms, Inc. and affiliates.

# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

from typing import List, Optional, Tuple

from pyre_extensions import none_throws
from shapely.geometry import Point, Polygon

from terragraph_planner.common.geos import law_of_cosines_utm
from terragraph_planner.common.structs import Point3D
from terragraph_planner.los.constants import (
    BUILDING_HEIGHT_THRESHOLD,
    HALF_SIDE_LENGTH_FOR_ALTITUDE_SEARCH,
    MIN_CORNER_ANGLE,
    POLYGON_MINIMUM_VERTICES,
)
from terragraph_planner.los.elevation import Elevation


def detect_corners_from_polygon_vertices(
    polygon_exterior_coords: List[Tuple[float, float]], max_corner_angle: float
) -> List[Tuple[float, float]]:
    """
    Assume that the list of vertices passed in is extracted from
    Shapely's polygon.exterior.coords, where the first and last elements in the
    list are equal.

    Before we iterate through the list, we add the **second** element to the end
    of the list. The reason is that to consider the angle at B, we must know the
    line segments AB and BC, given the order of the points is A->B->C, where B
    can be assumed to be the first point in the list.
    """
    vertices = polygon_exterior_coords[:]
    vertices.append(vertices[1])

    corners = []
    current_vertex = 2
    while current_vertex < len(vertices):
        # Calculate angle using three vertices of the polygon
        first_vertex = current_vertex - 2
        second_vertex = current_vertex - 1
        angle = round(
            law_of_cosines_utm(
                vertices[second_vertex][0],
                vertices[second_vertex][1],
                vertices[first_vertex][0],
                vertices[first_vertex][1],
                vertices[current_vertex][0],
                vertices[current_vertex][1],
            ),
            2,
        )  # Round to two decimal places

        # If calculated angle is less than or equal to the corner threshold,
        # and above the minimum threshold,
        # add to valid building corners
        if MIN_CORNER_ANGLE <= angle <= max_corner_angle:
            corners.append(vertices[second_vertex])

        current_vertex += 1

    return corners


class Building:
    """
    Used to detect locations of candidate sites on a building with 4 types:
    - Rooftop center
    - Rooftop corners
    - Highest point within the building polygon
    """

    def __init__(
        self,
        polygon: Polygon,
    ) -> None:
        self.polygon = polygon

    @property
    def bound(self) -> Tuple[float, float, float, float]:
        """
        (min_x, min_y, max_x, max_y) of the polygon
        """
        return self.polygon.bounds

    def detect_all_site_candidate_locations(
        self,
        surface_elevation: Optional[Elevation],
        max_corner_angle: Optional[int],
        detect_corners: bool,
        detect_center: bool,
        detect_highest: bool,
    ) -> List[Point3D]:
        """
        Detect all site candidates from corners, center and highest point if
        corresponding bool is True.

        @param surface_elevation
        Surface elevation data used to get the altitude of the detected sites. If None is passed in,
        the altitude of all the sites will equal to 0.

        @param max_corner_angle
        If given, only vertices whose angle is smaller than that will be detected as corners,
        else all vertices will be detected.

        @param detect_corners, detect_center, detect_highest
        Flags indicting which type of locations will be detected.
        """

        candidate_locations = []
        if detect_corners:
            corners = self.detect_corners(surface_elevation, max_corner_angle)
            candidate_locations.extend(corners)
        if detect_center:
            center = self.detect_center(surface_elevation)
            candidate_locations.append(center)
        if detect_highest:
            highest = self.detect_highest(none_throws(surface_elevation))
            candidate_locations.append(highest)
        return candidate_locations

    def detect_corners(
        self,
        surface_elevation: Optional[Elevation],
        max_corner_angle: Optional[float],
    ) -> List[Point3D]:
        """
        This method does the following:
            - If `max_corner_angle` is specified
                - Identify the building "corners", as defined by the
                max_corner_angle parameter
            - Else
                - Identify all building vertices
        """
        # The index offset of eight adjacent grids
        ADJACENT_OFFSETS = [
            (-1, -1),
            (-1, 0),
            (-1, 1),
            (0, -1),
            (0, 1),
            (1, -1),
            (1, 0),
            (1, 1),
        ]

        corners = []
        polygon_vertices = list(self.polygon.exterior.coords)
        if len(polygon_vertices) < POLYGON_MINIMUM_VERTICES:
            return corners

        if max_corner_angle is not None:
            corners_2d = detect_corners_from_polygon_vertices(
                polygon_vertices, none_throws(max_corner_angle)
            )
        else:
            # The last vertex is the same as the first one
            corners_2d = polygon_vertices[:-1]

        # Last resort: if polygon is too complex, return the first vertex
        # as the single corner detected
        if len(corners_2d) == 0:
            corners_2d = polygon_vertices[0:1]

        # Get the altitude of corners
        for utm_x, utm_y in corners_2d:
            if surface_elevation is None:
                corners.append(Point3D(utm_x, utm_y, 0))
                continue
            # First find neighbor grid within near the corner within the bound
            neighbors = surface_elevation.get_value_matrix_within_bound(
                utm_x - HALF_SIDE_LENGTH_FOR_ALTITUDE_SEARCH,
                utm_y - HALF_SIDE_LENGTH_FOR_ALTITUDE_SEARCH,
                utm_x + HALF_SIDE_LENGTH_FOR_ALTITUDE_SEARCH,
                utm_y + HALF_SIDE_LENGTH_FOR_ALTITUDE_SEARCH,
            )
            altitude = None
            nb_neighbor_each_col = len(neighbors)
            nb_neighbor_each_row = len(neighbors[0])
            # Iterate over at most 8 adjacent grids of the neighbor
            for idx_y in range(nb_neighbor_each_col):
                if altitude is not None:
                    break
                for idx_x in range(nb_neighbor_each_row):
                    for neighbor_offset in ADJACENT_OFFSETS:
                        neighbor_y = idx_y + neighbor_offset[0]
                        neighbor_x = idx_x + neighbor_offset[1]
                        # If the neighbor is over BUILDING_HEIGHT_THRESHOLD metres
                        # higher than its adjacent grid, its altitude will be picked
                        # as the altitude of the corner
                        if (
                            0 <= neighbor_y < nb_neighbor_each_col
                            and 0 <= neighbor_x < nb_neighbor_each_row
                            and neighbors[idx_y, idx_x]
                            - neighbors[neighbor_y, neighbor_x]
                            > BUILDING_HEIGHT_THRESHOLD
                        ):
                            altitude = neighbors[idx_y, idx_x]
                            break
            # If not find a neighbor much higher than the neighbor's neighbor,
            # use the the altitude of the corner location as fallback.
            if altitude is None:
                altitude = surface_elevation.get_value(utm_x, utm_y)
            corners.append(Point3D(utm_x, utm_y, altitude))
        return corners

    def detect_center(self, surface_elevation: Optional[Elevation]) -> Point3D:
        centroid = self.polygon.centroid
        # If centroid intersects with the polygon, use centroid as the rooftop center,
        # else use representative point
        center = (
            centroid
            if self.polygon.intersects(centroid)
            else self.polygon.representative_point()
        )
        utm_x, utm_y = list(center.coords)[0]
        return Point3D(
            utm_x,
            utm_y,
            surface_elevation.get_value(utm_x, utm_y)
            if surface_elevation is not None
            else 0,
        )

    def detect_highest(self, surface_elevation: Elevation) -> Point3D:
        """
        Detect the highest point on a rooftop using surface elevation data.
        """
        min_x, min_y, max_x, max_y = self.bound
        # Get (utm_x, utm_y, altitude) within the bound
        candidates = surface_elevation.get_value_list_within_bound(
            min_x, min_y, max_x, max_y
        )
        highest = None
        for candidate in candidates:
            # If higher
            if highest is None or candidate.z > highest.z:
                pt = Point((candidate.x, candidate.y))
                # If within the building
                if self.polygon.intersects(pt):
                    highest = candidate
        # Failover: If no highest point is found, use the center as the highest point.
        # That might happen when the geotiff resolution is low but the building polygon
        # is small, and no geotiff grid center intersects with the polygon.
        if highest is None:
            center = self.detect_center(surface_elevation)
            highest = center
        return highest
