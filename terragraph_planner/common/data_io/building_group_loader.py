# Copyright (c) Meta Platforms, Inc. and affiliates.

# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

import glob
import logging
import os
import zipfile
from itertools import chain
from typing import List

from osgeo import ogr, osr
from shapely import geometry, wkt

from terragraph_planner.common.constants import LAT_LON_EPSG
from terragraph_planner.common.data_io.building_group_rules import (
    BuildingGroupRules,
    ZippedShpFileRules,
)
from terragraph_planner.common.data_io.kml_library import extract_polygons
from terragraph_planner.common.data_io.patterns import (
    DataValidator,
    DataWorkSpace,
)
from terragraph_planner.common.exceptions import DataException
from terragraph_planner.los.building import Building
from terragraph_planner.los.building_group import BuildingGroup

logger: logging.Logger = logging.getLogger(__name__)


class BuildingGroupLoader(DataValidator[BuildingGroup], DataWorkSpace):
    """
    Used to load BuildingGroup data.
    Support getting data from SHP, KML or KMZ file.
    """

    def __init__(self) -> None:
        super().__init__()
        DataWorkSpace.__init__(self)

    def read(self, file_path: str) -> BuildingGroup:
        try:
            if file_path.endswith("zip"):
                return self._read_from_shapefile(file_path)
            else:
                return self._read_from_kml(file_path)
        except Exception:
            raise DataException("Error encountered when reading file.")

    def _read_from_shapefile(self, source: str) -> BuildingGroup:
        # Read the file from file path and unzip it
        zip_file_path = self.get_a_temp_file_path("zip")
        with open(zip_file_path, "wb") as f:
            with open(source, "rb") as fh:
                f.write(fh.read())
        unzipped_dir = self.get_a_temp_dir()
        with zipfile.ZipFile(zip_file_path, "r") as zip_ref:
            self.validate_shp_file(zip_ref.namelist())
            zip_ref.extractall(unzipped_dir)
            dir_names = [
                ref.filename for ref in zip_ref.infolist() if ref.is_dir()
            ]
            if len(dir_names) > 1:
                raise DataException(
                    "Zip folder that contains shape files must not contain any other folders."
                )
        dir_name = unzipped_dir if len(dir_names) == 0 else dir_names[0]

        # Get input layer and CRS
        shp_file_path = glob.glob(os.path.join(dir_name, "*.shp"))[0]
        driver = ogr.GetDriverByName("ESRI Shapefile")
        ds = driver.Open(shp_file_path)
        layer = ds.GetLayer()
        spatial_reference = layer.GetSpatialRef()

        building_list = []
        feature = layer.GetNextFeature()
        while feature:
            polygon = wkt.loads(feature.GetGeometryRef().ExportToWkt())
            if polygon.has_z:
                polygon = geometry.Polygon(
                    [coord[:2] for coord in polygon.exterior.coords]
                )
            building_list.append(Building(polygon))
            feature = layer.GetNextFeature()

        logger.info(
            f"{len(building_list)} building outlines have been loaded from shapefile {source}."
        )
        building_group = BuildingGroup(building_list, spatial_reference)
        self.validate(building_group, "Building SHP")
        return building_group

    def _read_from_kml(self, source: str) -> BuildingGroup:
        """
        Read building data, given a file path of kml or kmz file.
        """
        polygons = extract_polygons(source)
        building_list = [
            # polygon_coords is a list of (lat, lon), but we want (lon, lat)
            Building(polygon)
            for polygon in polygons
        ]
        logger.info(
            f"{len(building_list)} building outlines have been loaded from {source}."
        )
        spatial_reference = osr.SpatialReference()
        spatial_reference.ImportFromEPSG(LAT_LON_EPSG)
        building_group = BuildingGroup(building_list, spatial_reference)
        self.validate(building_group, "Building KML")
        return building_group

    def write(self, dest_file_path: str, data: BuildingGroup) -> None:
        """
        Save the buildings instance as a shp file and zip it.
        """
        buildings = data
        driver = ogr.GetDriverByName("ESRI Shapefile")

        # Create output layer
        output_dir = self.get_a_temp_dir()
        output_shp = os.path.join(output_dir, "buildings.shp")
        if os.path.exists(output_shp):
            driver.DeleteDataSource(output_shp)
        output_ds = driver.CreateDataSource(output_shp)
        output_layer = output_ds.CreateLayer("Building")
        output_layer_defn = output_layer.GetLayerDefn()

        # Iterate over building_list and save it into created layer
        for building in buildings.building_list:
            output_feature = ogr.Feature(output_layer_defn)
            output_feature.SetGeometry(
                ogr.CreateGeometryFromWkt(building.polygon.wkt)
            )
            output_layer.CreateFeature(output_feature)
            output_feature = None
        output_ds = None

        # Create an ESRI.prj file
        buildings.spatial_reference.MorphFromESRI()
        with open(os.path.join(output_dir, "buildings.prj"), "w") as prj_file:
            prj_file.write(buildings.spatial_reference.ExportToWkt())
            prj_file.close

        # Compressed as a zip file
        output_zf = zipfile.ZipFile(dest_file_path, "w")
        for output_file in glob.glob(os.path.join(output_dir, "*")):
            output_zf.write(
                output_file,
                arcname=os.path.basename(output_file),
                compress_type=zipfile.ZIP_DEFLATED,
            )
        output_zf.close()
        logger.info(
            f"The building outline data has been saved to {dest_file_path}."
        )

    def validate_shp_file(self, namelist: List[str]) -> None:
        rules = ZippedShpFileRules(namelist)
        self.errors += list(
            chain(
                rules.all_files_at_top_level_in_zip_rule(),
                rules.zip_file_contains_exactly_one_shp_file(),
            )
        )

    def validate(self, gis_data: BuildingGroup, role: str) -> None:
        rules = BuildingGroupRules(gis_data, role)
        self.errors += list(
            chain(
                rules.has_crs_rule(),
                rules.vertical_crs_is_valid_if_present_rule(
                    {"metre", "meter", "m"}
                ),
                rules.only_contains_certain_geometries_rule({"Polygon"}),
            )
        )
