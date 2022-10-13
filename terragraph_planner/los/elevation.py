# Copyright (c) Meta Platforms, Inc. and affiliates.

# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

import math
from itertools import product
from typing import Callable, List, Optional, Tuple

import numpy as np
import numpy.typing as npt
from osgeo import osr

from terragraph_planner.common.data_io.constants import (
    DEFAULT_ELEVATION_SEARCH_RADIUS,
    MIN_RES_TO_OUTPUT_AS_LIST,
    NO_DATA_VALUE,
)
from terragraph_planner.common.data_io.patterns import GISData
from terragraph_planner.common.exceptions import DataException
from terragraph_planner.common.structs import Point3D, UTMBoundingBox


class Elevation(GISData):
    """
    Used to store and handle 2.5-D geographic data.
    Only support "north-up" geodata now.
    """

    def __init__(
        self,
        data_matrix: npt.NDArray[np.float32],
        utm_bounding_box: UTMBoundingBox,
        x_resolution: float,
        y_resolution: float,
        left_top_x: float,
        left_top_y: float,
        spatial_reference: osr.SpatialReference,
        collection_time: Optional[str],
    ) -> None:
        super().__init__(spatial_reference)
        self.data_matrix = data_matrix
        self.utm_bounding_box = utm_bounding_box
        self.x_resolution = x_resolution
        self.y_resolution = y_resolution
        self.left_top_x = left_top_x
        self.left_top_y = left_top_y
        self.spatial_reference = spatial_reference
        self.elevation_search_radius: int = DEFAULT_ELEVATION_SEARCH_RADIUS
        self.collection_time = collection_time

    @property
    def x_size(self) -> int:
        return self.data_matrix.shape[1]

    @property
    def y_size(self) -> int:
        return self.data_matrix.shape[0]

    def idx_to_utm(self, idx_x: int, idx_y: int) -> Tuple[float, float]:
        """
        Convert data matrix index to utm, return (utm_x, utm_y)
        """
        utm_x = self.left_top_x + self.x_resolution * idx_x
        utm_y = self.left_top_y - self.y_resolution * idx_y
        return utm_x, utm_y

    def utm_to_idx(self, utm_x: float, utm_y: float) -> Tuple[int, int]:
        """
        Convert utm to data matrix index, return (idx_x, idx_y)
        """
        idx_x = round((utm_x - self.left_top_x) / self.x_resolution)
        idx_y = round((self.left_top_y - utm_y) / self.y_resolution)
        # Set index within the range [0, x_size - 1], [0, y_size - 1]
        idx_x = min(max(idx_x, 0), self.x_size - 1)
        idx_y = min(max(idx_y, 0), self.y_size - 1)
        return idx_x, idx_y

    def get_all_obstructions(
        self,
        utm_x1: float,
        utm_y1: float,
        utm_x2: float,
        utm_y2: float,
        point_within_bounds: Callable[[float, float], bool],
    ) -> List[Point3D]:
        """
        Get all obstructions within an axis-aligned bounding box that encapsulates both sites
        utm_x1, utm_y1 is the top left corner
        utm_x2, utm_y2 is the bottom right corner
        """
        # Ensure the boundary are within the bounding box
        utm_x1 = min(
            max(utm_x1, self.utm_bounding_box.min_utm_x),
            self.utm_bounding_box.max_utm_x,
        )
        utm_x2 = min(
            max(utm_x2, self.utm_bounding_box.min_utm_x),
            self.utm_bounding_box.max_utm_x,
        )
        utm_y1 = min(
            max(utm_y1, self.utm_bounding_box.min_utm_y),
            self.utm_bounding_box.max_utm_y,
        )
        utm_y2 = min(
            max(utm_y2, self.utm_bounding_box.min_utm_y),
            self.utm_bounding_box.max_utm_y,
        )

        result_list = []
        utm_x1, utm_x2 = sorted([utm_x1, utm_x2])
        utm_y1, utm_y2 = sorted([utm_y1, utm_y2])
        min_idx_x, min_idx_y = self.utm_to_idx(utm_x1, utm_y2)
        max_idx_x, max_idx_y = self.utm_to_idx(utm_x2, utm_y1)
        for idx_y in range(min_idx_y, max_idx_y + 1):
            for idx_x in range(min_idx_x, max_idx_x + 1):
                utm_x, utm_y = self.idx_to_utm(idx_x, idx_y)
                if point_within_bounds(utm_x, utm_y):
                    result_list.append(
                        Point3D(utm_x, utm_y, self.data_matrix[idx_y, idx_x])
                    )
        return result_list

    def get_value(self, x: float, y: float) -> float:
        idx_x, idx_y = self.utm_to_idx(x, y)
        if 0 <= idx_x < self.x_size and 0 <= idx_y < self.y_size:
            return self.data_matrix[idx_y, idx_x]
        raise DataException("get_value() error: out of index")

    def set_resolution(self, x_resolution: float, y_resolution: float) -> None:
        """
        Re-sample data_matrix by nearest neighbor
        """
        if (
            x_resolution == self.x_resolution
            and y_resolution == self.y_resolution
        ):
            return
        x_size = math.ceil(
            (
                self.utm_bounding_box.max_utm_x
                + x_resolution / 2
                - self.left_top_x
            )
            / x_resolution
        )
        y_size = math.ceil(
            (
                self.left_top_y
                - self.utm_bounding_box.min_utm_y
                + y_resolution / 2
            )
            / y_resolution
        )
        data_matrix = np.zeros((y_size, x_size), dtype=self.data_matrix.dtype)
        for idx_y in range(y_size):
            for idx_x in range(x_size):
                data_matrix[idx_y][idx_x] = self.get_value(
                    self.left_top_x + x_resolution * idx_x,
                    self.left_top_y - y_resolution * idx_y,
                )
        self.data_matrix = data_matrix
        self.x_resolution = x_resolution
        self.y_resolution = y_resolution

    def get_data_as_list(self) -> List[Tuple[float, float, float]]:
        """
        Get data in the format of List[Tuple[utm_x, utm_y, elevation]]
        """
        y_step = math.ceil(MIN_RES_TO_OUTPUT_AS_LIST / self.y_resolution)
        x_step = math.ceil(MIN_RES_TO_OUTPUT_AS_LIST / self.x_resolution)
        result_list = []
        for idx_y in range(0, self.y_size, y_step):
            for idx_x in range(0, self.x_size, x_step):
                if self.data_matrix[idx_y][idx_x] != NO_DATA_VALUE:
                    utm_x, utm_y = self.idx_to_utm(idx_x, idx_y)
                    result_list.append(
                        (utm_x, utm_y, self.data_matrix[idx_y, idx_x])
                    )
        return result_list

    def get_value_list_within_bound(
        self,
        min_utm_x: float,
        min_utm_y: float,
        max_utm_x: float,
        max_utm_y: float,
    ) -> List[Point3D]:
        """
        Get the values within the bound (min_utm_x, min_utm_y, max_utm_x, max_utm_y).
        The center locations (utm_x, utm_y, elevation) of all grid in this bound are returned.
        """
        min_idx_x = math.ceil((min_utm_x - self.left_top_x) / self.x_resolution)
        max_idx_y = math.floor(
            (self.left_top_y - min_utm_y) / self.y_resolution
        )
        max_idx_x = math.floor(
            (max_utm_x - self.left_top_x) / self.x_resolution
        )
        min_idx_y = math.ceil((self.left_top_y - max_utm_y) / self.y_resolution)
        # All candidate utm_x and utm_y in the bound
        utm_xs = [
            self.left_top_x + i * self.x_resolution
            for i in range(min_idx_x, max_idx_x + 1)
        ]
        utm_ys = [
            self.left_top_y - i * self.y_resolution
            for i in range(min_idx_y, max_idx_y + 1)
        ]
        return [
            Point3D(utm_x, utm_y, self.get_value(utm_x, utm_y))
            for utm_x, utm_y in product(utm_xs, utm_ys)
        ]

    def get_value_matrix_within_bound(
        self,
        min_utm_x: float,
        min_utm_y: float,
        max_utm_x: float,
        max_utm_y: float,
    ) -> npt.NDArray[np.float32]:
        """
        Get the values within the bound (min_utm_x, min_utm_y, max_utm_x, max_utm_y).
        The elevation of center locations in this bound are returned in the matrix format.
        """
        min_idx_x = math.ceil((min_utm_x - self.left_top_x) / self.x_resolution)
        max_idx_y = math.floor(
            (self.left_top_y - min_utm_y) / self.y_resolution
        )
        max_idx_x = math.floor(
            (max_utm_x - self.left_top_x) / self.x_resolution
        )
        min_idx_y = math.ceil((self.left_top_y - max_utm_y) / self.y_resolution)
        result_matrix = self.data_matrix[
            min_idx_y : max_idx_y + 1, min_idx_x : max_idx_x + 1
        ]
        # If the bound is outside of the region with valid data, return a 1 * 1 matrix with
        # the closest elevation as the only element in the matrix
        if result_matrix.size == 0:
            return np.array([[self.get_value(min_utm_x, min_utm_y)]])
        return result_matrix

    def _has_same_metadata(self, other_geogrids: "Elevation") -> bool:
        return (
            self.crs_epsg_code == other_geogrids.crs_epsg_code
            and self.x_size == other_geogrids.x_size
            and self.y_size == other_geogrids.y_size
            and self.x_resolution == other_geogrids.x_resolution
            and self.y_resolution == other_geogrids.y_resolution
            and self.left_top_x == other_geogrids.left_top_x
            and self.left_top_y == other_geogrids.left_top_y
        )

    def __add__(self, other_geogrids: "Elevation") -> "Elevation":
        if self._has_same_metadata(other_geogrids):
            result = Elevation(
                self.data_matrix + other_geogrids.data_matrix,
                self.utm_bounding_box,
                self.x_resolution,
                self.y_resolution,
                self.left_top_x,
                self.left_top_y,
                self.spatial_reference,
                None,
            )
            return result
        else:
            raise DataException(
                "Addition operation is only supported on GeoGrids with same metadata"
            )

    def __sub__(self, other_geogrids: "Elevation") -> "Elevation":
        if self._has_same_metadata(other_geogrids):
            result = Elevation(
                self.data_matrix - other_geogrids.data_matrix,
                self.utm_bounding_box,
                self.x_resolution,
                self.y_resolution,
                self.left_top_x,
                self.left_top_y,
                self.spatial_reference,
                None,
            )
            return result
        else:
            raise DataException(
                "Subtraction operation is only supported on GeoGrids with same metadata"
            )
