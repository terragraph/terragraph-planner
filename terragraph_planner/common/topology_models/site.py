# Copyright (c) Meta Platforms, Inc. and affiliates.

# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

from typing import NamedTuple, Optional

from terragraph_planner.common.configuration.configs import (
    DeviceData,
    SectorParams,
)
from terragraph_planner.common.configuration.enums import (
    DeviceType,
    LocationType,
    PolarityType,
    SiteType,
    StatusType,
)
from terragraph_planner.common.exceptions import (
    TopologyException,
    planner_assert,
)
from terragraph_planner.common.geos import GeoLocation, lat_lon_to_geo_hash
from terragraph_planner.common.utils import deterministic_hash


class Site:
    def __init__(
        self,
        site_type: SiteType,
        location: GeoLocation,
        device: DeviceData,
        status_type: StatusType,
        location_type: LocationType,
        building_id: Optional[int],
        name: str,
        number_of_subscribers: Optional[int],
    ) -> None:
        """
        The site_type, location and device are the key attributes, which impact the site_id and
        are read-only. Whenever you want to update the key attributes, please initialize a new Site
        instance.

        @param site_type
        The type of the site, including CN, DN, and POP.

        @param location
        The geographical location of the site, using latitude and longitude or
        utm coordinates.

        @param device
        The Device mounted on this site.

        @param status_type
        The status of the Site, which can be UNAVAILABLE, CANDIDATE, PROPOSED, EXISTING or UNREACHABLE.

        @param location_type
        Indicating whether the site is on the rooftop or street. UNKNOWN if the planner is not able
        to infer it or don't know the building id if it's on the rooftop.

        @param building_id
        The id of the building where the site is located on. A valid id is an int ranging from 0, but specially,
         - None if the location type is not ROOFTOP
         - -1 if the location is ROOFTOP but the site is inputed rather than detected

        @param name
        The name of the site

        @param number_of_subscribers
        The number of connected demand sites
        """
        planner_assert(
            not (location_type == LocationType.ROOFTOP and building_id is None),
            "Building id must be provided when the location type of a site is ROOFTOP",
            TopologyException,
        )
        planner_assert(
            not (
                location_type != LocationType.ROOFTOP
                and building_id is not None
            ),
            "Building id must not be provided when the location type of a site is not ROOFTOP",
            TopologyException,
        )
        planner_assert(
            site_type == SiteType.CN
            and device.device_type == DeviceType.CN
            or site_type != SiteType.CN
            and device.device_type == DeviceType.DN,
            f"Site{'' + name if len(name) > 0 else name} has a device of inconsistent device type",
            TopologyException,
        )
        self._site_type = site_type
        self._location = location
        self._device = device
        self._site_id: str = deterministic_hash(
            site_type.value,
            location.latitude,
            location.longitude,
            location.altitude,
            device.device_sku,
        )
        self._site_hash: str = lat_lon_to_geo_hash(
            location.latitude, location.longitude
        )

        self._status_type = status_type
        self._location_type = location_type
        self._building_id = building_id
        self._name = name
        self._number_of_subscribers = number_of_subscribers
        self.polarity: PolarityType = PolarityType.UNASSIGNED
        self.breakdowns: int = 0

    @property
    def site_type(self) -> SiteType:
        return self._site_type

    @property
    def device(self) -> DeviceData:
        return self._device

    @property
    def location(self) -> GeoLocation:
        return self._location

    @property
    def latitude(self) -> float:
        return self._location.latitude

    @property
    def longitude(self) -> float:
        return self._location.longitude

    @property
    def utm_x(self) -> float:
        return self._location.utm_x

    @property
    def utm_y(self) -> float:
        return self._location.utm_y

    @property
    def utm_epsg(self) -> int:
        return self._location.utm_epsg

    @property
    def altitude(self) -> Optional[float]:
        return self._location.altitude

    @property
    def site_id(self) -> str:
        return self._site_id

    @property
    def site_hash(self) -> str:
        return self._site_hash

    @property
    def status_type(self) -> StatusType:
        return self._status_type

    @status_type.setter
    def status_type(self, status_type: StatusType) -> None:
        planner_assert(
            len(
                {self._status_type, status_type} & StatusType.immutable_status()
            )
            == 0,
            f"Cannot change the site status to/from {StatusType.immutable_status()}",
            TopologyException,
        )
        self._status_type = status_type

    @property
    def location_type(self) -> LocationType:
        return self._location_type

    @property
    def building_id(self) -> Optional[int]:
        return self._building_id

    @property
    def name(self) -> str:
        if len(self._name) == 0:
            return self.site_id
        return self._name

    @name.setter
    def name(self, name: str) -> None:
        self._name = name

    @property
    def number_of_subscribers(self) -> int:
        return (
            self._number_of_subscribers or 1
            if self.site_type == SiteType.CN
            else 0
        )


class DetectedSite(Site):
    """
    DetectedSite is a Site detected on the building rooftop by the planner. Unlike Site,
    it does not have an assigned device.
    """

    def __init__(
        self,
        site_type: SiteType,
        location: GeoLocation,
        building_id: int,
    ) -> None:
        expected_device_type = (
            DeviceType.CN if site_type == SiteType.CN else DeviceType.DN
        )
        super().__init__(
            site_type,
            location,
            DeviceData(
                device_sku="FAKE",
                device_type=expected_device_type,
                sector_params=SectorParams(),
            ),
            StatusType.CANDIDATE,
            LocationType.ROOFTOP,
            building_id,
            "",
            None,
        )

    @property
    def device(self) -> None:
        return None

    def to_site(self, device: DeviceData) -> Site:
        return Site(
            self._site_type,
            self._location,
            device,
            self._status_type,
            self._location_type,
            self._building_id,
            self._name,
            self.number_of_subscribers,
        )


class LOSSite(NamedTuple):
    """
    Used for multiprocessing LOS computation
    """

    utm_x: float
    utm_y: float
    altitude: Optional[float]
    location_type: int
    building_id: Optional[int]
