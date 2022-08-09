# Copyright (c) Meta Platforms, Inc. and affiliates.

# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

import logging
from typing import Callable, Dict, List, Optional, Tuple

from shapely.geometry import Point, Polygon
from shapely.prepared import prep

from terragraph_planner.common.configuration.configs import DeviceData
from terragraph_planner.common.configuration.constants import (
    UNKNOWN_BUILDING_ID,
)
from terragraph_planner.common.configuration.enums import (
    DeviceType,
    LocationType,
    SiteType,
    StatusType,
)
from terragraph_planner.common.data_io.csv_library import (
    load_input_sites_from_csv_file,
)
from terragraph_planner.common.data_io.input_sites import InputSites
from terragraph_planner.common.data_io.kml_library import (
    extract_raw_data_from_kml_file,
)
from terragraph_planner.common.exceptions import DataException, planner_assert
from terragraph_planner.common.geos import GeoLocation
from terragraph_planner.common.structs import RawSite
from terragraph_planner.common.topology_models.site import Site

logger: logging.Logger = logging.getLogger(__name__)


class InputSitesLoader:
    """
    Used to load site list data, including user input site list and site list for candidate
    topology.

    Please use this loader to load any site data from any files, to keep all the site data
    keep the same validity.
    """

    def __init__(self, device_list: List[DeviceData]) -> None:
        self.device_list = device_list
        self.sku_to_device: Dict[str, DeviceData] = {}
        dn_devices = []
        cn_devices = []
        for device in device_list:
            self.sku_to_device[device.device_sku.casefold()] = device
            if device.device_type == DeviceType.DN:
                dn_devices.append(device)
            else:
                cn_devices.append(device)
        self.site_type_to_devices: Dict[SiteType, List[DeviceData]] = {
            SiteType.POP: dn_devices,
            SiteType.DN: dn_devices,
            SiteType.CN: cn_devices,
        }

    def read_user_input(
        self,
        data_source: Optional[str],
        boundary_polygon: Optional[Polygon],
        infer_input_site_location: Optional[
            Callable[
                ...,
                Tuple[GeoLocation, LocationType],
            ]
        ],
    ) -> InputSites:
        if data_source is None:
            return InputSites()
        ext = data_source.split(".")[-1].casefold()
        if ext == "csv":
            raw_sites = load_input_sites_from_csv_file(data_source, True)
        else:
            raw_sites, _, _ = extract_raw_data_from_kml_file(data_source)
        return self.get_input_sites(
            raw_sites, boundary_polygon, infer_input_site_location
        )

    def get_input_sites(
        self,
        raw_sites: List[RawSite],
        boundary_polygon: Optional[Polygon],
        infer_input_site_location: Optional[
            Callable[
                ...,
                Tuple[GeoLocation, LocationType],
            ]
        ],
    ) -> InputSites:
        """
        Get input sites based on the raw site data read from inputs.

        @param raw_sites
        A list of site data read from input files.

        @param boundary_polygon
        Optional of Polygon. If provided, it will be used to filter out all the sites out of the boundary.
        """
        input_sites = InputSites()
        if boundary_polygon is not None:
            prepared_boundary = prep(boundary_polygon)
        for site in raw_sites:
            if boundary_polygon is None or prepared_boundary.contains(
                Point(site.longitude, site.latitude)
            ):
                sites = self._construct_sites(
                    site_type=site.site_type,
                    latitude=site.latitude,
                    longitude=site.longitude,
                    altitude=site.altitude,
                    height=site.height,
                    device_sku=site.device_sku,
                    status_type=site.status_type,
                    location_type=site.location_type,
                    building_id=site.building_id,
                    name=site.name,
                    number_of_subscribers=site.number_of_subscribers,
                    infer_input_site_location=infer_input_site_location,
                )
                for site in sites:
                    input_sites.add_site(site)
        logger.info(f"{len(input_sites)} sites have been loaded.")
        return input_sites

    def _construct_sites(
        self,
        site_type: SiteType,
        latitude: float,
        longitude: float,
        altitude: Optional[float],
        height: Optional[float],
        device_sku: Optional[str],
        status_type: StatusType,
        location_type: LocationType,
        building_id: Optional[int],
        name: Optional[str],
        number_of_subscribers: Optional[int],
        infer_input_site_location: Optional[
            Callable[
                ...,
                Tuple[GeoLocation, LocationType],
            ]
        ],
    ) -> List[Site]:
        # infer_input_site_location is None when load sites for candidate topology
        if infer_input_site_location is not None:
            location, location_type = infer_input_site_location(
                latitude=latitude,
                longitude=longitude,
                altitude=altitude,
                height=height,
                location_type=location_type,
                site_type=site_type,
            )
            # Set building is as unknown building id if location type if rooftop when loading user input
            building_id = (
                UNKNOWN_BUILDING_ID
                if location_type == LocationType.ROOFTOP
                else None
            )
        else:
            location = GeoLocation(
                latitude=latitude, longitude=longitude, altitude=altitude
            )

        if device_sku is not None:
            planner_assert(
                device_sku.casefold() in self.sku_to_device,
                f"Device {device_sku} does not exist in device list",
                DataException,
            )
            return [
                Site(
                    site_type=site_type,
                    location=location,
                    device=self.sku_to_device[device_sku.casefold()],
                    status_type=status_type,
                    location_type=location_type,
                    building_id=building_id,
                    name=name or "",
                    number_of_subscribers=number_of_subscribers,
                )
            ]
        res = []
        for device in self.site_type_to_devices[site_type]:
            res.append(
                Site(
                    site_type=site_type,
                    location=location,
                    device=device,
                    status_type=status_type,
                    location_type=location_type,
                    building_id=building_id,
                    name=name or "",
                    number_of_subscribers=number_of_subscribers,
                )
            )
        return res
