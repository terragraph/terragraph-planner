# Copyright (c) Meta Platforms, Inc. and affiliates.

# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

import logging
import math
from itertools import chain
from typing import List

from osgeo import gdal

from terragraph_planner.common.data_io.constants import NO_DATA_VALUE
from terragraph_planner.common.data_io.elevation_rules import ElevationRules
from terragraph_planner.common.data_io.patterns import DataValidator
from terragraph_planner.common.exceptions import DataException
from terragraph_planner.common.structs import UTMBoundingBox
from terragraph_planner.los.elevation import Elevation

logger: logging.Logger = logging.getLogger(__name__)


class ElevationLoader(DataValidator[Elevation]):
    """
    Used to load Elevation Data.
    Only support getting data from GeoTIFF file.
    """

    def __init__(self) -> None:
        super().__init__()

    def read(
        self,
        file_paths: List[str],
        utm_epsg_code: int,
        utm_bounding_box: UTMBoundingBox,
    ) -> Elevation:
        return self._read_from_geotiff(
            file_paths, utm_epsg_code, utm_bounding_box
        )

    def write(self, dest_file_path: str, data: Elevation) -> None:
        """
        Write elevation data to file.

        @param dest_file_path: file path to write the data. Have to include extension.
        @param data: Elevation data that is to be written.
        """
        try:
            driver = gdal.GetDriverByName("GTiff")
            driver.Register()
            outds = driver.Create(
                dest_file_path,
                xsize=data.x_size,
                ysize=data.y_size,
                bands=1,
                eType=gdal.GDT_Float32,
            )
            outds.SetGeoTransform(
                [
                    data.left_top_x,
                    data.x_resolution,
                    0,
                    data.left_top_y,
                    0,
                    -data.y_resolution,
                ]
            )
            outds.SetSpatialRef(data.spatial_reference)

            outband = outds.GetRasterBand(1)
            outband.WriteArray(data.data_matrix)
            outband.SetNoDataValue(NO_DATA_VALUE)
            outband.FlushCache()

            outband = None
            outds = None
        except Exception:
            raise DataException("Error encountered when writting GeoTIFF")
        logger.info(
            f"The elevation model data has been saved to {dest_file_path}."
        )

    def _read_from_geotiff(
        self,
        sources: List[str],
        utm_epsg_code: int,
        utm_bounding_box: UTMBoundingBox,
    ) -> Elevation:
        """
        Load data from one or more GeoTiff files, and preprocess it:
        - Merge into one single ds if there're more than one source,
        - Convert crs to UTM
            - If original CRS is UTM, do nothing
            - elif original CRS is lat/lon, directly convert it to UTM
            - else convert left-top point to lat/lon to get the utm_zone
                and then convert it to UTM
        - Crop the geotiff into utm_bounding_box
        """
        try:
            ds_list = []
            for source in sources:
                ds_list.append(gdal.Open(source))

            ds = gdal.Warp(
                "",
                ds_list,
                format="MEM",
                dstSRS=f"EPSG:{utm_epsg_code}",
                dstNodata=NO_DATA_VALUE,
                srcNodata=None,
            )

            # Crop the geotiff into boundary bounding box
            geotransform = ds.GetGeoTransform()
            x_resolution = round(
                math.sqrt(geotransform[1] ** 2 + geotransform[4] ** 2), 6
            )
            y_resolution = round(
                math.sqrt(geotransform[2] ** 2 + geotransform[5] ** 2), 6
            )

            ds = gdal.Translate(
                "",
                ds,
                projWin=(
                    utm_bounding_box.min_utm_x,
                    utm_bounding_box.max_utm_y,
                    utm_bounding_box.max_utm_x,
                    utm_bounding_box.min_utm_y,
                ),
                xRes=x_resolution,
                yRes=y_resolution,
                format="MEM",
                noData=NO_DATA_VALUE,
            )

            geotransform = ds.GetGeoTransform()
        except Exception:
            raise DataException("Error encountered when loading GeoTIFF")

        elevation = Elevation(
            ds.ReadAsArray(),
            utm_bounding_box,
            geotransform[1],
            -geotransform[5],
            geotransform[0],
            geotransform[3],
            ds.GetSpatialRef(),
            ds.GetMetadata_Dict["TIFFTAG_DATETIME"]
            if "TIFFTAG_DATETIME" in ds.GetMetadata_Dict()
            else None,
        )

        logger.info(f"The geotiff file(s) {sources} has been loaded.")
        self.validate(elevation)

        return elevation

    def validate(self, gis_data: Elevation) -> None:
        rules = ElevationRules(gis_data)
        self.errors += list(
            chain(
                rules.has_crs_rule(),
                rules.geogcs_has_enough_info_rule(),
                rules.has_recent_collection_time_rule(),
                rules.has_valid_linear_unit_rule(1.0, {"metre", "meter", "m"}),
                rules.has_valid_pixel_size_rule(0.15, 35.0),
                rules.vertical_crs_is_valid_if_present_rule(
                    {"metre", "meter", "m"}
                ),
            )
        )
