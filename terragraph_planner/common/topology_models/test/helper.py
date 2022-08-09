# Copyright (c) Meta Platforms, Inc. and affiliates.

# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

from copy import deepcopy
from itertools import permutations
from typing import Optional
from unittest.mock import MagicMock, patch

from terragraph_planner.common.configuration.configs import (
    DeviceData,
    OptimizerParams,
    SectorParams,
)
from terragraph_planner.common.configuration.enums import (
    DeviceType,
    LocationType,
    PolarityType,
    SiteType,
    StatusType,
)
from terragraph_planner.common.geos import GeoLocation
from terragraph_planner.common.topology_models.demand_site import DemandSite
from terragraph_planner.common.topology_models.link import Link
from terragraph_planner.common.topology_models.sector import Sector
from terragraph_planner.common.topology_models.site import Site
from terragraph_planner.common.topology_models.topology import Topology
from terragraph_planner.optimization.topology_preparation import (
    prepare_topology_for_optimization,
)

DEFAULT_DN_DEVICE = DeviceData(
    device_sku="SAMPLE_DN_DEVICE",
    sector_params=SectorParams(),
    node_capex=250,
    number_of_nodes_per_site=4,
    device_type=DeviceType.DN,
)

DEFAULT_CN_DEVICE = DeviceData(
    device_sku="SAMPLE_CN_DEVICE",
    sector_params=SectorParams(),
    node_capex=150,
    number_of_nodes_per_site=1,
    device_type=DeviceType.CN,
)

# For multi-sku testing
ANOTHER_DN_DEVICE = DeviceData(
    device_sku="SAMPLE_DN_DEVICE2",
    sector_params=SectorParams(),
    node_capex=250,
    number_of_nodes_per_site=4,
    device_type=DeviceType.DN,
)


class SampleSite(Site):
    def __init__(
        self,
        site_type: SiteType,
        location: GeoLocation,
        device: Optional[DeviceData] = None,
        status_type: StatusType = StatusType.CANDIDATE,
        location_type: LocationType = LocationType.UNKNOWN,
        building_id: Optional[int] = None,
        site_id: Optional[str] = None,
        name: str = "",
        number_of_subscribers: Optional[int] = None,
    ) -> None:
        if device is None:
            device = (
                DEFAULT_CN_DEVICE
                if site_type == SiteType.CN
                else DEFAULT_DN_DEVICE
            )
        super().__init__(
            site_type,
            location,
            device,
            status_type,
            location_type,
            building_id,
            name,
            number_of_subscribers,
        )
        self._input_site_id = site_id

    @property
    def site_id(self) -> str:
        if self._input_site_id is not None:
            return self._input_site_id
        return super().site_id

    @site_id.setter
    def site_id(self, site_id: Optional[str]) -> None:
        self._input_site_id = site_id


def set_topology_proposed(topology: Topology) -> None:
    for site in topology.sites.values():
        if site.status_type not in StatusType.active_status():
            site.status_type = StatusType.PROPOSED
        site.polarity = PolarityType.UNASSIGNED
    for sector in topology.sectors.values():
        if sector.status_type not in StatusType.active_status():
            sector.status_type = StatusType.PROPOSED
    for link in topology.links.values():
        if link.status_type not in StatusType.active_status():
            link.status_type = StatusType.PROPOSED


# Demand sites with connected sectors already provided in square topology, so
# skip add_demand_to_topology
@patch(
    "terragraph_planner.optimization.topology_preparation.add_demand_to_topology",
    MagicMock(side_effect=lambda t, p: None),  # return input topology
)
def square_topology(params: Optional[OptimizerParams] = None) -> Topology:
    params = (
        OptimizerParams(device_list=[DEFAULT_DN_DEVICE, DEFAULT_CN_DEVICE])
        if params is None
        else params
    )
    topology = raw_square_topology(params.demand)
    prepare_topology_for_optimization(topology, params)
    return topology


def raw_square_topology(demand: float = 0.025) -> Topology:
    sites = [
        SampleSite(
            site_id="DN1",
            site_type=SiteType.DN,
            location=GeoLocation(
                utm_x=160, utm_y=510, utm_epsg=32631, altitude=0
            ),
        ),
        SampleSite(
            site_id="DN2",
            site_type=SiteType.DN,
            location=GeoLocation(
                utm_x=155, utm_y=220, utm_epsg=32631, altitude=0
            ),
        ),
        SampleSite(
            site_id="DN3",
            site_type=SiteType.DN,
            location=GeoLocation(
                utm_x=-190, utm_y=190, utm_epsg=32631, altitude=0
            ),
        ),
        SampleSite(
            site_id="DN4",
            site_type=SiteType.DN,
            location=GeoLocation(
                utm_x=-195, utm_y=490, utm_epsg=32631, altitude=0
            ),
        ),
        SampleSite(
            site_id="POP5",
            site_type=SiteType.POP,
            location=GeoLocation(
                utm_x=-10, utm_y=755, utm_epsg=32631, altitude=0
            ),
        ),
        SampleSite(
            site_id="POP6",
            site_type=SiteType.POP,
            location=GeoLocation(utm_x=0, utm_y=0, utm_epsg=32631, altitude=0),
        ),
    ]

    sectors = [
        Sector(site=sites[0], node_id=0, position_in_node=0, ant_azimuth=181),
        Sector(site=sites[0], node_id=1, position_in_node=0, ant_azimuth=296),
        Sector(site=sites[1], node_id=0, position_in_node=0, ant_azimuth=247),
        Sector(site=sites[1], node_id=1, position_in_node=0, ant_azimuth=1),
        Sector(site=sites[2], node_id=0, position_in_node=0, ant_azimuth=102),
        Sector(site=sites[2], node_id=1, position_in_node=0, ant_azimuth=359),
        Sector(site=sites[3], node_id=0, position_in_node=0, ant_azimuth=68),
        Sector(site=sites[3], node_id=1, position_in_node=0, ant_azimuth=179),
        Sector(site=sites[4], node_id=0, position_in_node=0, ant_azimuth=180),
        Sector(site=sites[5], node_id=0, position_in_node=0, ant_azimuth=315),
        Sector(site=sites[5], node_id=1, position_in_node=0, ant_azimuth=45),
    ]

    links = [
        Link(tx_sector=sectors[1], rx_sector=sectors[6]),  # DN1->DN4
        Link(tx_sector=sectors[6], rx_sector=sectors[1]),  # DN4->DN1
        Link(tx_sector=sectors[0], rx_sector=sectors[3]),  # DN1->DN2
        Link(tx_sector=sectors[3], rx_sector=sectors[0]),  # DN2->DN1
        Link(tx_sector=sectors[2], rx_sector=sectors[4]),  # DN2->DN3
        Link(tx_sector=sectors[4], rx_sector=sectors[2]),  # DN3->DN2
        Link(tx_sector=sectors[5], rx_sector=sectors[7]),  # DN3->DN4
        Link(tx_sector=sectors[7], rx_sector=sectors[5]),  # DN4->DN3
        Link(tx_sector=sectors[8], rx_sector=sectors[1]),  # DN1->POP5
        Link(tx_sector=sectors[1], rx_sector=sectors[8]),  # POP5->DN1
        Link(tx_sector=sectors[8], rx_sector=sectors[6]),  # POP5->DN4
        Link(tx_sector=sectors[6], rx_sector=sectors[8]),  # DN4->POP5
        Link(tx_sector=sectors[9], rx_sector=sectors[4]),  # POP6->DN3
        Link(tx_sector=sectors[4], rx_sector=sectors[9]),  # DN3->POP6
        Link(tx_sector=sectors[10], rx_sector=sectors[2]),  # POP6->DN2
        Link(tx_sector=sectors[2], rx_sector=sectors[10]),  # DN2->POP6
    ]

    demand_sites = [
        DemandSite(
            location=GeoLocation(
                utm_x=160, utm_y=510, utm_epsg=32631, altitude=0
            ),
            connected_sites=sites[0:1],
            demand=demand,
        ),
        DemandSite(
            location=GeoLocation(
                utm_x=-185, utm_y=490, utm_epsg=32631, altitude=0
            ),
            connected_sites=sites[3:4],
            demand=demand,
        ),
        DemandSite(
            location=GeoLocation(
                utm_x=-187.5, utm_y=340, utm_epsg=32631, altitude=0
            ),
            connected_sites=sites[2:4],
            demand=demand,
        ),
        DemandSite(
            location=GeoLocation(
                utm_x=-190, utm_y=190, utm_epsg=32631, altitude=0
            ),
            connected_sites=sites[2:3],
            demand=demand,
        ),
        DemandSite(
            location=GeoLocation(
                utm_x=155, utm_y=220, utm_epsg=32631, altitude=0
            ),
            connected_sites=sites[1:2],
            demand=demand,
        ),
        DemandSite(
            location=GeoLocation(
                utm_x=-15, utm_y=352.5, utm_epsg=32631, altitude=0
            ),
            connected_sites=sites[0:4],
            demand=demand,
        ),
    ]

    return Topology(
        sites=sites, sectors=sectors, links=links, demand_sites=demand_sites
    )


def square_topology_with_cns(
    params: Optional[OptimizerParams] = None,
) -> Topology:
    params = (
        OptimizerParams(device_list=[DEFAULT_DN_DEVICE, DEFAULT_CN_DEVICE])
        if params is None
        else params
    )
    topology = raw_square_topology_with_cns()
    prepare_topology_for_optimization(topology, params)
    return topology


def raw_square_topology_with_cns() -> Topology:
    topology = raw_square_topology()
    topology.demand_sites = {}  # Remove demand sites

    cn_sites = [
        SampleSite(
            site_id="CN7",
            site_type=SiteType.CN,
            location=GeoLocation(
                utm_x=-230, utm_y=430, utm_epsg=32631, altitude=0
            ),
        ),
        SampleSite(
            site_id="CN8",
            site_type=SiteType.CN,
            location=GeoLocation(
                utm_x=-205, utm_y=400, utm_epsg=32631, altitude=0
            ),
        ),
    ]

    for site in cn_sites:
        topology.add_site(site)

    cn_sectors = [
        Sector(site=cn_sites[0], node_id=0, position_in_node=0, ant_azimuth=0),
        Sector(site=cn_sites[1], node_id=0, position_in_node=0, ant_azimuth=0),
    ]
    for sector in cn_sectors:
        topology.add_sector(sector)

    cn_links = [
        Link(tx_sector=topology.sectors["DN4-1-0-DN"], rx_sector=cn_sectors[0]),
        Link(tx_sector=topology.sectors["DN4-1-0-DN"], rx_sector=cn_sectors[1]),
    ]
    for link in cn_links:
        topology.add_link(link)

    return topology


def square_topology_with_cns_with_multi_dns(
    params: Optional[OptimizerParams] = None,
) -> Topology:
    params = (
        OptimizerParams(device_list=[DEFAULT_DN_DEVICE, DEFAULT_CN_DEVICE])
        if params is None
        else params
    )
    topology = raw_square_topology_with_cns_with_multi_dns()
    prepare_topology_for_optimization(topology, params)
    return topology


def raw_square_topology_with_cns_with_multi_dns() -> Topology:
    topology = raw_square_topology_with_cns()
    topology.add_link(
        Link(
            tx_sector=topology.sectors["DN3-1-0-DN"],
            rx_sector=topology.sectors["CN8-0-0-CN"],
        )
    )
    return topology


def square_topology_with_colocated_sites(
    params: Optional[OptimizerParams] = None,
) -> Topology:
    params = (
        OptimizerParams(device_list=[DEFAULT_DN_DEVICE, DEFAULT_CN_DEVICE])
        if params is None
        else params
    )
    topology = raw_square_topology_with_colocated_sites()
    prepare_topology_for_optimization(topology, params)
    return topology


def raw_square_topology_with_colocated_sites() -> Topology:
    topology = raw_square_topology_with_cns()

    sites = [
        SampleSite(
            site_id="DN9",
            site_type=SiteType.DN,
            location=deepcopy(topology.sites["POP5"].location),
        ),
        SampleSite(
            site_id="CN10",
            site_type=SiteType.CN,
            location=deepcopy(topology.sites["POP5"].location),
        ),
        SampleSite(
            site_id="CN11",
            site_type=SiteType.CN,
            location=deepcopy(topology.sites["DN3"].location),
        ),
    ]
    for site in sites:
        topology.add_site(site)

    sectors = [
        Sector(site=sites[0], node_id=0, position_in_node=0, ant_azimuth=180),
        Sector(site=sites[1], node_id=0, position_in_node=0, ant_azimuth=180),
        Sector(site=sites[2], node_id=0, position_in_node=0, ant_azimuth=102),
    ]
    for sector in sectors:
        topology.add_sector(sector)

    links = [
        Link(
            tx_sector=sectors[0], rx_sector=topology.links["POP5-DN4"].rx_sector
        ),  # DN9->DN4
        Link(
            tx_sector=topology.links["DN4-POP5"].tx_sector, rx_sector=sectors[0]
        ),  # DN4->DN9
        Link(
            tx_sector=sectors[0], rx_sector=topology.links["POP5-DN1"].rx_sector
        ),  # DN9->DN1
        Link(
            tx_sector=topology.links["DN1-POP5"].tx_sector, rx_sector=sectors[0]
        ),  # DN1->DN9
        Link(
            tx_sector=topology.links["DN4-POP5"].tx_sector, rx_sector=sectors[1]
        ),  # DN4->CN10
        Link(
            tx_sector=topology.links["DN1-POP5"].tx_sector, rx_sector=sectors[1]
        ),  # DN1->DN10
        Link(
            tx_sector=topology.links["POP6-DN3"].tx_sector, rx_sector=sectors[2]
        ),  # POP6->CN11
        Link(
            tx_sector=topology.links["DN4-DN3"].tx_sector, rx_sector=sectors[2]
        ),  # DN4->CN11
        Link(
            tx_sector=topology.links["DN2-DN3"].tx_sector, rx_sector=sectors[2]
        ),  # DN3->CN11
    ]
    for link in links:
        topology.add_link(link)

    return topology


# Demand sites with connected sectors already provided in multi sector topology, so
# skip add_demand_to_topology
@patch(
    "terragraph_planner.optimization.topology_preparation.add_demand_to_topology",
    MagicMock(side_effect=lambda t, p: None),  # return input topology
)
def multi_sector_topology(params: Optional[OptimizerParams] = None) -> Topology:
    """
    Simple topology with three nodes forming a right angle. Good for exposing
    multi-sector node behavior.

    If non-None params is provided, the first DN device in the device list
    will be mounted on each DN site.
    """
    params = (
        OptimizerParams(device_list=[DEFAULT_DN_DEVICE, DEFAULT_CN_DEVICE])
        if params is None
        else params
    )
    dn_device = [
        device
        for device in params.device_list
        if device.device_type == DeviceType.DN
    ][0]

    sites = [
        SampleSite(
            site_id="POP1",
            site_type=SiteType.POP,
            location=GeoLocation(utm_x=0, utm_y=0, utm_epsg=32631, altitude=0),
            device=dn_device,
        ),
        SampleSite(
            site_id="DN2",
            site_type=SiteType.DN,
            location=GeoLocation(
                utm_x=100, utm_y=0, utm_epsg=32631, altitude=0
            ),
            device=dn_device,
        ),
        SampleSite(
            site_id="DN3",
            site_type=SiteType.DN,
            location=GeoLocation(
                utm_x=0, utm_y=-100, utm_epsg=32631, altitude=0
            ),
            device=dn_device,
        ),
    ]

    links = [
        Link(tx_site=sites[0], rx_site=sites[1]),
        Link(tx_site=sites[0], rx_site=sites[2]),
        Link(tx_site=sites[1], rx_site=sites[0]),
        Link(tx_site=sites[2], rx_site=sites[0]),
    ]

    demand_sites = [
        DemandSite(
            location=deepcopy(site.location),
            connected_sites=[site],
            demand=params.demand,
        )
        for site in sites
    ]

    topology = Topology(sites=sites, links=links, demand_sites=demand_sites)

    prepare_topology_for_optimization(topology, params)
    return topology


def straight_line_topology(
    params: Optional[OptimizerParams] = None,
) -> Topology:
    """
    Simple topology with 9 sites on a straight line.
    """
    sites = [
        SampleSite(
            site_id=str(i),
            site_type=SiteType.POP
            if i == 0
            else SiteType.CN
            if i == 9
            else SiteType.DN,
            location=GeoLocation(
                utm_x=i * 50, utm_y=0, utm_epsg=32631, altitude=0
            ),
        )
        for i in range(1, 10)
    ]
    links = [
        Link(tx_site=site1, rx_site=site2)
        for site1, site2 in permutations(sites, 2)
        if site1.site_type != SiteType.CN
    ]

    topology = Topology(sites=sites, links=links)

    params = (
        OptimizerParams(device_list=[DEFAULT_DN_DEVICE, DEFAULT_CN_DEVICE])
        if params is None
        else params
    )
    prepare_topology_for_optimization(topology, params)
    return topology


# Demand sites with connected sectors already provided in rectangle topology, so
# skip add_demand_to_topology
@patch(
    "terragraph_planner.optimization.topology_preparation.add_demand_to_topology",
    MagicMock(side_effect=lambda t, p: None),  # return input topology
)
def rectangle_topology(params: Optional[OptimizerParams] = None) -> Topology:
    """
    Simple topology with only 4 sites that form a rectangle. Good for testing
    deployment rules.
    """
    sites = [
        SampleSite(
            site_id="1",
            site_type=SiteType.POP,
            location=GeoLocation(utm_x=0, utm_y=0, utm_epsg=32610),
        ),
        SampleSite(
            site_id="2",
            site_type=SiteType.DN,
            location=GeoLocation(utm_x=100, utm_y=0, utm_epsg=32610),
        ),
        SampleSite(
            site_id="3",
            site_type=SiteType.DN,
            location=GeoLocation(utm_x=100, utm_y=20, utm_epsg=32610),
        ),
        SampleSite(
            site_id="4",
            site_type=SiteType.DN,
            location=GeoLocation(utm_x=0, utm_y=20, utm_epsg=32610),
        ),
    ]
    links = [
        Link(tx_site=sites[i], rx_site=sites[j])
        for i, j in permutations(range(4), 2)
        if abs(i - j) == 1 or abs(i - j) == 3
    ]

    params = (
        OptimizerParams(device_list=[DEFAULT_DN_DEVICE, DEFAULT_CN_DEVICE])
        if params is None
        else params
    )

    demand_sites = [
        DemandSite(
            location=deepcopy(site.location),
            connected_sites=[site],
            demand=params.demand,
        )
        for site in sites
    ]

    topology = Topology(sites=sites, links=links, demand_sites=demand_sites)

    prepare_topology_for_optimization(topology, params)
    return topology


def hybrid_sites_topology(params: Optional[OptimizerParams] = None) -> Topology:
    """
    A square topology with one pop (P1), three dns (D1-D3) and four cns (C0-C4).
    P1 and C0 are co-located as are D1/C1, D2/C2 and D3/C3.
    """
    sites = [
        SampleSite(
            site_id="POP1",
            site_type=SiteType.POP,
            location=GeoLocation(utm_x=0, utm_y=0, utm_epsg=32610),
        ),
        SampleSite(
            site_id="DN1",
            site_type=SiteType.DN,
            location=GeoLocation(utm_x=100, utm_y=100, utm_epsg=32610),
        ),
        SampleSite(
            site_id="DN2",
            site_type=SiteType.DN,
            location=GeoLocation(utm_x=100, utm_y=-100, utm_epsg=32610),
        ),
        SampleSite(
            site_id="DN3",
            site_type=SiteType.DN,
            location=GeoLocation(utm_x=200, utm_y=0, utm_epsg=32610),
        ),
        SampleSite(
            site_id="CN0",
            site_type=SiteType.CN,
            location=GeoLocation(utm_x=0, utm_y=0, utm_epsg=32610),
        ),
        SampleSite(
            site_id="CN1",
            site_type=SiteType.CN,
            location=GeoLocation(utm_x=100, utm_y=100, utm_epsg=32610),
        ),
        SampleSite(
            site_id="CN2",
            site_type=SiteType.CN,
            location=GeoLocation(utm_x=100, utm_y=-100, utm_epsg=32610),
        ),
        SampleSite(
            site_id="CN3",
            site_type=SiteType.CN,
            location=GeoLocation(utm_x=200, utm_y=0, utm_epsg=32610),
        ),
    ]

    links = [
        Link(tx_site=sites[0], rx_site=sites[1]),  # POP1->DN1
        Link(tx_site=sites[1], rx_site=sites[0]),  # DN1->POP1
        Link(tx_site=sites[0], rx_site=sites[2]),  # POP1->DN2
        Link(tx_site=sites[2], rx_site=sites[0]),  # DN2->POP1
        Link(tx_site=sites[1], rx_site=sites[3]),  # DN1->DN3
        Link(tx_site=sites[3], rx_site=sites[1]),  # DN3->DN1
        Link(tx_site=sites[2], rx_site=sites[3]),  # DN2->DN3
        Link(tx_site=sites[3], rx_site=sites[2]),  # DN3->DN2
        Link(tx_site=sites[0], rx_site=sites[4]),  # POP1->CN0
        Link(tx_site=sites[0], rx_site=sites[5]),  # POP1->CN1
        Link(tx_site=sites[0], rx_site=sites[6]),  # POP1->CN2
        Link(tx_site=sites[1], rx_site=sites[7]),  # DN1->CN3
        Link(tx_site=sites[2], rx_site=sites[7]),  # DN2->CN3
    ]

    topology = Topology(sites=sites, links=links)

    params = (
        OptimizerParams(device_list=[DEFAULT_DN_DEVICE, DEFAULT_CN_DEVICE])
        if params is None
        else params
    )
    prepare_topology_for_optimization(topology, params)
    return topology


def simple_pop_multi_sku_topology(
    params: Optional[OptimizerParams] = None,
) -> Topology:
    """
    Simple POP->CN topology with two DN sku options
    """
    sites = [
        SampleSite(
            site_id="POP0",
            site_type=SiteType.POP,
            location=GeoLocation(utm_x=0, utm_y=0, utm_epsg=32610),
            device=DEFAULT_DN_DEVICE,
        ),
        SampleSite(
            site_id="POP1",
            site_type=SiteType.POP,
            location=GeoLocation(utm_x=0, utm_y=0, utm_epsg=32610),
            device=ANOTHER_DN_DEVICE,
        ),
        SampleSite(
            site_id="CN2",
            site_type=SiteType.CN,
            location=GeoLocation(utm_x=0, utm_y=100, utm_epsg=32610),
            device=DEFAULT_CN_DEVICE,
        ),
    ]

    links = [
        Link(tx_site=sites[0], rx_site=sites[2]),
        Link(tx_site=sites[1], rx_site=sites[2]),
    ]

    topology = Topology(sites=sites, links=links)

    params = (
        OptimizerParams(
            device_list=[
                DEFAULT_DN_DEVICE,
                DEFAULT_CN_DEVICE,
                ANOTHER_DN_DEVICE,
            ]
        )
        if params is None
        else params
    )
    prepare_topology_for_optimization(topology, params)
    return topology


def simple_minimize_cost_topology(
    params: Optional[OptimizerParams] = None,
) -> Topology:
    """
    Simple topology for testing cost minimization
    POP->DN->CN
     ---------^
    """
    sites = [
        SampleSite(
            site_id="POP1",
            site_type=SiteType.POP,
            location=GeoLocation(utm_x=0, utm_y=0, utm_epsg=32610),
        ),
        SampleSite(
            site_id="DN1",
            site_type=SiteType.DN,
            location=GeoLocation(utm_x=50, utm_y=100, utm_epsg=32610),
        ),
        SampleSite(
            site_id="CN1",
            site_type=SiteType.CN,
            location=GeoLocation(utm_x=100, utm_y=0, utm_epsg=32610),
        ),
    ]

    links = [
        Link(tx_site=sites[0], rx_site=sites[1]),  # POP1->DN1
        Link(tx_site=sites[1], rx_site=sites[0]),  # DN1->POP1
        Link(tx_site=sites[0], rx_site=sites[2]),  # POP1->CN1
        Link(tx_site=sites[1], rx_site=sites[2]),  # DN1->CN1
    ]

    topology = Topology(sites=sites, links=links)

    params = (
        OptimizerParams(device_list=[DEFAULT_DN_DEVICE, DEFAULT_CN_DEVICE])
        if params is None
        else params
    )
    prepare_topology_for_optimization(topology, params)
    return topology


def multi_path_topology(params: Optional[OptimizerParams] = None) -> Topology:
    """
    Topology for testing optimization with multiple paths to CNs
    """
    sites = [
        SampleSite(
            site_id="POP1",
            site_type=SiteType.POP,
            location=GeoLocation(utm_x=0, utm_y=0, utm_epsg=32610),
        ),
        SampleSite(
            site_id="DN1",
            site_type=SiteType.DN,
            location=GeoLocation(utm_x=100, utm_y=100, utm_epsg=32610),
        ),
        SampleSite(
            site_id="DN2",
            site_type=SiteType.DN,
            location=GeoLocation(utm_x=100, utm_y=-100, utm_epsg=32610),
        ),
        SampleSite(
            site_id="CN1",
            site_type=SiteType.CN,
            location=GeoLocation(utm_x=200, utm_y=100, utm_epsg=32610),
        ),
        SampleSite(
            site_id="CN2",
            site_type=SiteType.CN,
            location=GeoLocation(utm_x=200, utm_y=-100, utm_epsg=32610),
        ),
    ]

    sectors = [
        Sector(site=sites[0], node_id=0, position_in_node=0, ant_azimuth=45),
        Sector(site=sites[0], node_id=1, position_in_node=0, ant_azimuth=135),
        Sector(site=sites[1], node_id=0, position_in_node=0, ant_azimuth=225),
        Sector(site=sites[1], node_id=1, position_in_node=0, ant_azimuth=122),
        Sector(site=sites[2], node_id=0, position_in_node=0, ant_azimuth=315),
        Sector(site=sites[2], node_id=1, position_in_node=0, ant_azimuth=58),
        Sector(site=sites[3], node_id=0, position_in_node=0, ant_azimuth=270),
        Sector(site=sites[4], node_id=0, position_in_node=0, ant_azimuth=270),
    ]

    links = [
        Link(tx_sector=sectors[0], rx_sector=sectors[2]),  # POP1->DN1
        Link(tx_sector=sectors[2], rx_sector=sectors[0]),  # DN1->POP1
        Link(tx_sector=sectors[1], rx_sector=sectors[4]),  # POP1->DN2
        Link(tx_sector=sectors[4], rx_sector=sectors[1]),  # DN2->POP1
        Link(tx_sector=sectors[3], rx_sector=sectors[6]),  # DN1->CN1
        Link(tx_sector=sectors[3], rx_sector=sectors[7]),  # DN1->CN2
        Link(tx_sector=sectors[5], rx_sector=sectors[6]),  # DN2->CN1
        Link(tx_sector=sectors[5], rx_sector=sectors[7]),  # DN2->CN2
    ]

    topology = Topology(sites=sites, sectors=sectors, links=links)

    params = (
        OptimizerParams(device_list=[DEFAULT_DN_DEVICE, DEFAULT_CN_DEVICE])
        if params is None
        else params
    )
    prepare_topology_for_optimization(topology, params)
    return topology


def another_multi_path_topology(
    params: Optional[OptimizerParams] = None,
) -> Topology:
    """
    Topology for testing optimization with multiple paths to CNs
    """
    sites = [
        SampleSite(
            site_id="POP1",
            site_type=SiteType.POP,
            location=GeoLocation(utm_x=0, utm_y=0, utm_epsg=32610),
        ),
        SampleSite(
            site_id="DN1",
            site_type=SiteType.DN,
            location=GeoLocation(utm_x=100, utm_y=100, utm_epsg=32610),
        ),
        SampleSite(
            site_id="DN2",
            site_type=SiteType.DN,
            location=GeoLocation(utm_x=100, utm_y=-100, utm_epsg=32610),
        ),
        SampleSite(
            site_id="CN1",
            site_type=SiteType.CN,
            location=GeoLocation(utm_x=200, utm_y=100, utm_epsg=32610),
        ),
        SampleSite(
            site_id="CN2",
            site_type=SiteType.CN,
            location=GeoLocation(utm_x=200, utm_y=-100, utm_epsg=32610),
        ),
        SampleSite(
            site_id="CN3",
            site_type=SiteType.CN,
            location=GeoLocation(utm_x=200, utm_y=-80, utm_epsg=32610),
        ),
    ]

    sectors = [
        Sector(site=sites[0], node_id=0, position_in_node=0, ant_azimuth=45),
        Sector(site=sites[0], node_id=1, position_in_node=0, ant_azimuth=135),
        Sector(site=sites[1], node_id=0, position_in_node=0, ant_azimuth=225),
        Sector(site=sites[1], node_id=1, position_in_node=0, ant_azimuth=122),
        Sector(site=sites[2], node_id=0, position_in_node=0, ant_azimuth=315),
        Sector(site=sites[2], node_id=1, position_in_node=0, ant_azimuth=58),
        Sector(site=sites[3], node_id=0, position_in_node=0, ant_azimuth=270),
        Sector(site=sites[4], node_id=0, position_in_node=0, ant_azimuth=270),
        Sector(site=sites[5], node_id=0, position_in_node=0, ant_azimuth=270),
    ]

    links = [
        Link(tx_sector=sectors[0], rx_sector=sectors[2]),  # POP1->DN1
        Link(tx_sector=sectors[2], rx_sector=sectors[0]),  # DN1->POP1
        Link(tx_sector=sectors[1], rx_sector=sectors[4]),  # POP1->DN2
        Link(tx_sector=sectors[4], rx_sector=sectors[1]),  # DN2->POP1
        Link(tx_sector=sectors[3], rx_sector=sectors[6]),  # DN1->CN1
        Link(tx_sector=sectors[5], rx_sector=sectors[7]),  # DN2->CN2
        Link(tx_sector=sectors[5], rx_sector=sectors[8]),  # DN2->CN3
    ]

    topology = Topology(sites=sites, sectors=sectors, links=links)

    params = (
        OptimizerParams(device_list=[DEFAULT_DN_DEVICE, DEFAULT_CN_DEVICE])
        if params is None
        else params
    )
    prepare_topology_for_optimization(topology, params)
    return topology


# Demand sites with connected sectors already provided in triangle topology, so
# skip add_demand_to_topology
@patch(
    "terragraph_planner.optimization.topology_preparation.add_demand_to_topology",
    MagicMock(side_effect=lambda t, p: None),  # return input topology
)
def triangle_topology(params: Optional[OptimizerParams] = None) -> Topology:
    """
    Simple triangle topology with a POP connected to two DNs
    """
    sites = [
        SampleSite(
            site_id="POP0",
            site_type=SiteType.POP,
            location=GeoLocation(utm_x=0, utm_y=0, utm_epsg=32610),
        ),
        SampleSite(
            site_id="DN1",
            site_type=SiteType.DN,
            location=GeoLocation(utm_x=200, utm_y=200, utm_epsg=32610),
        ),
        SampleSite(
            site_id="DN2",
            site_type=SiteType.DN,
            location=GeoLocation(utm_x=-200, utm_y=200, utm_epsg=32610),
        ),
    ]

    links = [
        Link(tx_site=sites[0], rx_site=sites[1]),  # POP0->DN1
        Link(tx_site=sites[1], rx_site=sites[0]),  # DN1->POP0
        Link(tx_site=sites[0], rx_site=sites[2]),  # POP0->DN2
        Link(tx_site=sites[2], rx_site=sites[0]),  # DN2->POP0
        Link(tx_site=sites[1], rx_site=sites[2]),  # DN1->DN2
        Link(tx_site=sites[2], rx_site=sites[1]),  # DN2->DN1
    ]

    params = (
        OptimizerParams(device_list=[DEFAULT_DN_DEVICE, DEFAULT_CN_DEVICE])
        if params is None
        else params
    )

    demand_sites = [
        DemandSite(
            location=deepcopy(sites[1].location),
            connected_sites=[sites[1]],
            demand=params.demand,
        ),
        DemandSite(
            location=deepcopy(sites[2].location),
            connected_sites=[sites[2]],
            demand=params.demand,
        ),
    ]

    topology = Topology(sites=sites, links=links, demand_sites=demand_sites)
    prepare_topology_for_optimization(topology, params)
    return topology


def triangle_topology_with_cns(
    params: Optional[OptimizerParams] = None,
) -> Topology:
    """
    Simple triangle topology with a POP connected to two CNs
    """
    sites = [
        SampleSite(
            site_id="POP0",
            site_type=SiteType.POP,
            location=GeoLocation(utm_x=0, utm_y=0, utm_epsg=32610),
        ),
        SampleSite(
            site_id="CN1",
            site_type=SiteType.CN,
            location=GeoLocation(utm_x=200, utm_y=200, utm_epsg=32610),
        ),
        SampleSite(
            site_id="CN2",
            site_type=SiteType.CN,
            location=GeoLocation(utm_x=-200, utm_y=200, utm_epsg=32610),
        ),
    ]

    links = [
        Link(tx_site=sites[0], rx_site=sites[1]),  # POP0->CN1
        Link(tx_site=sites[0], rx_site=sites[2]),  # POP0->CN2
    ]

    topology = Topology(sites=sites, links=links)

    params = (
        OptimizerParams(device_list=[DEFAULT_DN_DEVICE, DEFAULT_CN_DEVICE])
        if params is None
        else params
    )
    prepare_topology_for_optimization(topology, params)
    return topology


def figure_eight_topology(params: Optional[OptimizerParams] = None) -> Topology:
    """
      -- DN1 --     -- DN4 --
     |         |   |         |
    POP0         DN3         DN6 - CN7
     |         |   |         |
      -- DN2 --     -- DN5 --
    """
    sites = [
        SampleSite(
            site_id="POP0",
            site_type=SiteType.POP,
            location=GeoLocation(utm_x=0, utm_y=0, utm_epsg=32610),
        ),
        SampleSite(
            site_id="DN1",
            site_type=SiteType.DN,
            location=GeoLocation(utm_x=100, utm_y=100, utm_epsg=32610),
        ),
        SampleSite(
            site_id="DN2",
            site_type=SiteType.DN,
            location=GeoLocation(utm_x=100, utm_y=-100, utm_epsg=32610),
        ),
        SampleSite(
            site_id="DN3",
            site_type=SiteType.DN,
            location=GeoLocation(utm_x=200, utm_y=0, utm_epsg=32610),
        ),
        SampleSite(
            site_id="DN4",
            site_type=SiteType.DN,
            location=GeoLocation(utm_x=300, utm_y=100, utm_epsg=32610),
        ),
        SampleSite(
            site_id="DN5",
            site_type=SiteType.DN,
            location=GeoLocation(utm_x=300, utm_y=-100, utm_epsg=32610),
        ),
        SampleSite(
            site_id="DN6",
            site_type=SiteType.DN,
            location=GeoLocation(utm_x=400, utm_y=0, utm_epsg=32610),
        ),
        SampleSite(
            site_id="CN7",
            site_type=SiteType.CN,
            location=GeoLocation(utm_x=500, utm_y=0, utm_epsg=32610),
        ),
    ]

    links = [
        Link(tx_site=sites[0], rx_site=sites[1]),  # POP0->DN1
        Link(tx_site=sites[1], rx_site=sites[0]),  # DN1->POP0
        Link(tx_site=sites[0], rx_site=sites[2]),  # POP0->DN2
        Link(tx_site=sites[2], rx_site=sites[0]),  # DN2->POP0
        Link(tx_site=sites[1], rx_site=sites[3]),  # DN1->DN3
        Link(tx_site=sites[3], rx_site=sites[1]),  # DN3->DN1
        Link(tx_site=sites[2], rx_site=sites[3]),  # DN1->DN3
        Link(tx_site=sites[3], rx_site=sites[2]),  # DN3->DN1
        Link(tx_site=sites[3], rx_site=sites[4]),  # DN3->DN4
        Link(tx_site=sites[4], rx_site=sites[3]),  # DN4->DN3
        Link(tx_site=sites[3], rx_site=sites[5]),  # DN3->DN5
        Link(tx_site=sites[5], rx_site=sites[3]),  # DN5->DN3
        Link(tx_site=sites[4], rx_site=sites[6]),  # DN4->DN6
        Link(tx_site=sites[6], rx_site=sites[4]),  # DN6->DN4
        Link(tx_site=sites[5], rx_site=sites[6]),  # DN5->DN6
        Link(tx_site=sites[6], rx_site=sites[5]),  # DN6->DN5
        Link(tx_site=sites[6], rx_site=sites[7]),  # DN6->CN7
    ]

    topology = Topology(sites=sites, links=links)

    params = (
        OptimizerParams(device_list=[DEFAULT_DN_DEVICE, DEFAULT_CN_DEVICE])
        if params is None
        else params
    )
    prepare_topology_for_optimization(topology, params)
    return topology


def diamond_topology(params: Optional[OptimizerParams] = None) -> Topology:
    """
             -- POP5 --
            |          |
           DN3 ------- DN4 -- CN7
            |   x   x  |
            |   x   x  |
    CN6 -- DN1 ------- DN2
            |          |
             -- POP0 --
    Note: DN1 <-> DN4 and DN2 <-> DN3 have candidate links
    """
    sites = [
        SampleSite(
            site_id="POP0",
            site_type=SiteType.POP,
            location=GeoLocation(utm_x=0, utm_y=0, utm_epsg=32610),
        ),
        SampleSite(
            site_id="DN1",
            site_type=SiteType.DN,
            location=GeoLocation(utm_x=-100, utm_y=100, utm_epsg=32610),
        ),
        SampleSite(
            site_id="DN2",
            site_type=SiteType.DN,
            location=GeoLocation(utm_x=100, utm_y=100, utm_epsg=32610),
        ),
        SampleSite(
            site_id="DN3",
            site_type=SiteType.DN,
            location=GeoLocation(utm_x=-100, utm_y=200, utm_epsg=32610),
        ),
        SampleSite(
            site_id="DN4",
            site_type=SiteType.DN,
            location=GeoLocation(utm_x=100, utm_y=200, utm_epsg=32610),
        ),
        SampleSite(
            site_id="POP5",
            site_type=SiteType.POP,
            location=GeoLocation(utm_x=0, utm_y=300, utm_epsg=32610),
        ),
        SampleSite(
            site_id="CN6",
            site_type=SiteType.CN,
            location=GeoLocation(utm_x=-200, utm_y=100, utm_epsg=32610),
        ),
        SampleSite(
            site_id="CN7",
            site_type=SiteType.CN,
            location=GeoLocation(utm_x=200, utm_y=200, utm_epsg=32610),
        ),
    ]

    links = [
        Link(tx_site=sites[0], rx_site=sites[1]),  # POP0->DN1
        Link(tx_site=sites[1], rx_site=sites[0]),  # DN1->POP0
        Link(tx_site=sites[0], rx_site=sites[2]),  # POP0->DN2
        Link(tx_site=sites[2], rx_site=sites[0]),  # DN2->POP0
        Link(tx_site=sites[1], rx_site=sites[2]),  # DN1->DN2
        Link(tx_site=sites[2], rx_site=sites[1]),  # DN2->DN1
        Link(tx_site=sites[1], rx_site=sites[3]),  # DN1->DN3
        Link(tx_site=sites[3], rx_site=sites[1]),  # DN3->DN1
        Link(tx_site=sites[1], rx_site=sites[4]),  # DN1->DN4
        Link(tx_site=sites[4], rx_site=sites[1]),  # DN4->DN1
        Link(tx_site=sites[2], rx_site=sites[3]),  # DN2->DN3
        Link(tx_site=sites[3], rx_site=sites[2]),  # DN3->DN2
        Link(tx_site=sites[2], rx_site=sites[4]),  # DN2->DN4
        Link(tx_site=sites[4], rx_site=sites[2]),  # DN4->DN2
        Link(tx_site=sites[3], rx_site=sites[4]),  # DN3->DN4
        Link(tx_site=sites[4], rx_site=sites[3]),  # DN4->DN3
        Link(tx_site=sites[3], rx_site=sites[5]),  # DN3->DN5
        Link(tx_site=sites[5], rx_site=sites[3]),  # DN5->DN3
        Link(tx_site=sites[4], rx_site=sites[5]),  # DN4->POP5
        Link(tx_site=sites[5], rx_site=sites[4]),  # POP5->DN4
        Link(tx_site=sites[1], rx_site=sites[6]),  # DN1->CN6
        Link(tx_site=sites[4], rx_site=sites[7]),  # DN4->CN7
    ]

    topology = Topology(sites=sites, links=links)

    params = (
        OptimizerParams(device_list=[DEFAULT_DN_DEVICE, DEFAULT_CN_DEVICE])
        if params is None
        else params
    )
    prepare_topology_for_optimization(topology, params)
    return topology


def flow_tree_topology(params: Optional[OptimizerParams] = None) -> Topology:
    sites = [
        SampleSite(
            site_id="POP0",
            site_type=SiteType.POP,
            location=GeoLocation(utm_x=0, utm_y=0, utm_epsg=32610),
        ),
        SampleSite(
            site_id="DN1",
            site_type=SiteType.DN,
            location=GeoLocation(utm_x=50, utm_y=100, utm_epsg=32610),
        ),
        SampleSite(
            site_id="DN2",
            site_type=SiteType.DN,
            location=GeoLocation(utm_x=-50, utm_y=100, utm_epsg=32610),
        ),
        SampleSite(
            site_id="DN3",
            site_type=SiteType.DN,
            location=GeoLocation(utm_x=50, utm_y=200, utm_epsg=32610),
        ),
        SampleSite(
            site_id="DN4",
            site_type=SiteType.DN,
            location=GeoLocation(utm_x=-50, utm_y=200, utm_epsg=32610),
        ),
        SampleSite(
            site_id="CN5",
            site_type=SiteType.CN,
            location=GeoLocation(utm_x=50, utm_y=300, utm_epsg=32610),
        ),
        SampleSite(
            site_id="CN6",
            site_type=SiteType.CN,
            location=GeoLocation(utm_x=-50, utm_y=300, utm_epsg=32610),
        ),
        SampleSite(
            site_id="CN7",
            site_type=SiteType.CN,
            location=GeoLocation(utm_x=100, utm_y=100, utm_epsg=32610),
        ),
    ]

    links = [
        Link(tx_site=sites[0], rx_site=sites[1]),  # POP0->DN1
        Link(tx_site=sites[1], rx_site=sites[0]),  # DN1->POP0
        Link(tx_site=sites[0], rx_site=sites[2]),  # POP0->DN2
        Link(tx_site=sites[2], rx_site=sites[0]),  # DN2->POP0
        Link(tx_site=sites[1], rx_site=sites[3]),  # DN1->DN3
        Link(tx_site=sites[3], rx_site=sites[1]),  # DN3->DN1
        Link(tx_site=sites[2], rx_site=sites[4]),  # DN2->DN4
        Link(tx_site=sites[4], rx_site=sites[2]),  # DN4->DN2
        Link(tx_site=sites[3], rx_site=sites[5]),  # DN3->CN5
        Link(tx_site=sites[4], rx_site=sites[6]),  # DN4->CN6
        Link(tx_site=sites[1], rx_site=sites[7]),  # DN1->CN7
    ]

    topology = Topology(sites=sites, links=links)

    params = (
        OptimizerParams(device_list=[DEFAULT_DN_DEVICE, DEFAULT_CN_DEVICE])
        if params is None
        else params
    )
    prepare_topology_for_optimization(topology, params)
    return topology


def intersecting_links_topology(
    params: Optional[OptimizerParams] = None,
) -> Topology:
    """
      ----- DN1 ----- DN2 ----- CN5
     |          x   x
    POP0          x
     |          x   x
      ----- DN3 ----- DN4 ----- CN6
    """
    sites = [
        SampleSite(
            site_id="POP0",
            site_type=SiteType.POP,
            location=GeoLocation(utm_x=0, utm_y=0, utm_epsg=32610),
        ),
        SampleSite(
            site_id="DN1",
            site_type=SiteType.DN,
            location=GeoLocation(utm_x=100, utm_y=50, utm_epsg=32610),
        ),
        SampleSite(
            site_id="DN2",
            site_type=SiteType.DN,
            location=GeoLocation(utm_x=200, utm_y=50, utm_epsg=32610),
        ),
        SampleSite(
            site_id="DN3",
            site_type=SiteType.DN,
            location=GeoLocation(utm_x=100, utm_y=-50, utm_epsg=32610),
        ),
        SampleSite(
            site_id="DN4",
            site_type=SiteType.DN,
            location=GeoLocation(utm_x=200, utm_y=-50, utm_epsg=32610),
        ),
        SampleSite(
            site_id="CN5",
            site_type=SiteType.CN,
            location=GeoLocation(utm_x=300, utm_y=50, utm_epsg=32610),
        ),
        SampleSite(
            site_id="CN6",
            site_type=SiteType.CN,
            location=GeoLocation(utm_x=300, utm_y=-50, utm_epsg=32610),
        ),
    ]

    sectors = [
        Sector(site=sites[0], node_id=0, position_in_node=0, ant_azimuth=45),
        Sector(site=sites[0], node_id=1, position_in_node=0, ant_azimuth=135),
        Sector(site=sites[1], node_id=0, position_in_node=0, ant_azimuth=112.5),
        Sector(site=sites[1], node_id=1, position_in_node=0, ant_azimuth=225),
        Sector(site=sites[2], node_id=0, position_in_node=0, ant_azimuth=90),
        Sector(site=sites[2], node_id=1, position_in_node=0, ant_azimuth=247.5),
        Sector(site=sites[3], node_id=0, position_in_node=0, ant_azimuth=67.5),
        Sector(site=sites[3], node_id=1, position_in_node=0, ant_azimuth=315),
        Sector(site=sites[4], node_id=0, position_in_node=0, ant_azimuth=90),
        Sector(site=sites[4], node_id=1, position_in_node=0, ant_azimuth=292.5),
        Sector(site=sites[5], node_id=0, position_in_node=0, ant_azimuth=270),
        Sector(site=sites[6], node_id=0, position_in_node=0, ant_azimuth=270),
    ]

    links = [
        Link(tx_sector=sectors[0], rx_sector=sectors[3]),  # POP0->DN1
        Link(tx_sector=sectors[3], rx_sector=sectors[0]),  # DN1->POP0
        Link(tx_sector=sectors[1], rx_sector=sectors[7]),  # POP0->DN3
        Link(tx_sector=sectors[7], rx_sector=sectors[1]),  # DN3->POP0
        Link(tx_sector=sectors[2], rx_sector=sectors[5]),  # DN1->DN2
        Link(tx_sector=sectors[5], rx_sector=sectors[2]),  # DN2->DN1
        Link(tx_sector=sectors[6], rx_sector=sectors[9]),  # DN3->DN4
        Link(tx_sector=sectors[9], rx_sector=sectors[6]),  # DN4->DN3
        Link(tx_sector=sectors[2], rx_sector=sectors[9]),  # DN1->DN4
        Link(tx_sector=sectors[9], rx_sector=sectors[2]),  # DN4->DN1
        Link(tx_sector=sectors[5], rx_sector=sectors[6]),  # DN2->DN3
        Link(tx_sector=sectors[6], rx_sector=sectors[5]),  # DN3->DN2
        Link(tx_sector=sectors[4], rx_sector=sectors[10]),  # DN2->CN5
        Link(tx_sector=sectors[8], rx_sector=sectors[11]),  # DN4->CN6
    ]

    topology = Topology(sites=sites, sectors=sectors, links=links)

    params = (
        OptimizerParams(device_list=[DEFAULT_DN_DEVICE, DEFAULT_CN_DEVICE])
        if params is None
        else params
    )
    prepare_topology_for_optimization(topology, params)
    return topology


def interfering_links_topology(
    params: Optional[OptimizerParams] = None,
) -> Topology:
    """
     DN3 ----- DN4 ----- DN5
     |                    |
     |                    |
    POP0 ----- DN1 ----- DN2 ----- CN
    where POP0<->DN5 and DN2<->DN3 are linked as well
    """
    sites = [
        SampleSite(
            site_id="POP0",
            site_type=SiteType.POP,
            location=GeoLocation(utm_x=0, utm_y=0, utm_epsg=32610),
        ),
        SampleSite(
            site_id="DN1",
            site_type=SiteType.DN,
            location=GeoLocation(utm_x=100, utm_y=0, utm_epsg=32610),
        ),
        SampleSite(
            site_id="DN2",
            site_type=SiteType.DN,
            location=GeoLocation(utm_x=200, utm_y=0, utm_epsg=32610),
        ),
        SampleSite(
            site_id="DN3",
            site_type=SiteType.DN,
            location=GeoLocation(utm_x=0, utm_y=100, utm_epsg=32610),
        ),
        SampleSite(
            site_id="DN4",
            site_type=SiteType.DN,
            location=GeoLocation(utm_x=100, utm_y=100, utm_epsg=32610),
        ),
        SampleSite(
            site_id="DN5",
            site_type=SiteType.DN,
            location=GeoLocation(utm_x=200, utm_y=100, utm_epsg=32610),
        ),
        SampleSite(
            site_id="CN6",
            site_type=SiteType.CN,
            location=GeoLocation(utm_x=300, utm_y=0, utm_epsg=32610),
        ),
    ]

    links = [
        Link(tx_site=sites[0], rx_site=sites[1]),  # POP0->DN1
        Link(tx_site=sites[1], rx_site=sites[0]),  # DN1->POP0
        Link(tx_site=sites[0], rx_site=sites[3]),  # POP0->DN3
        Link(tx_site=sites[3], rx_site=sites[0]),  # DN3->POP0
        Link(tx_site=sites[0], rx_site=sites[5]),  # POP0->DN5
        Link(tx_site=sites[5], rx_site=sites[0]),  # DN5->POP0
        Link(tx_site=sites[1], rx_site=sites[2]),  # DN1->DN2
        Link(tx_site=sites[2], rx_site=sites[1]),  # DN2->DN1
        Link(tx_site=sites[2], rx_site=sites[3]),  # DN2->DN3
        Link(tx_site=sites[3], rx_site=sites[2]),  # DN3->DN2
        Link(tx_site=sites[3], rx_site=sites[4]),  # DN3->DN4
        Link(tx_site=sites[4], rx_site=sites[3]),  # DN4->DN3
        Link(tx_site=sites[4], rx_site=sites[5]),  # DN4->DN5
        Link(tx_site=sites[5], rx_site=sites[4]),  # DN5->DN4
        Link(tx_site=sites[2], rx_site=sites[5]),  # DN2->DN5
        Link(tx_site=sites[5], rx_site=sites[2]),  # DN5->DN2
        Link(tx_site=sites[2], rx_site=sites[6]),  # DN2->CN6
    ]

    topology = Topology(sites=sites, links=links)

    params = (
        OptimizerParams(device_list=[DEFAULT_DN_DEVICE, DEFAULT_CN_DEVICE])
        if params is None
        else params
    )
    prepare_topology_for_optimization(topology, params)
    return topology


def dn_dn_limit_topology(params: Optional[OptimizerParams] = None) -> Topology:
    sites = [
        SampleSite(
            site_id="POP0",
            site_type=SiteType.POP,
            location=GeoLocation(utm_x=0, utm_y=0, utm_epsg=32610),
        ),
        SampleSite(
            site_id="DN1",
            site_type=SiteType.DN,
            location=GeoLocation(utm_x=100, utm_y=0, utm_epsg=32610),
        ),
        SampleSite(
            site_id="DN2",
            site_type=SiteType.DN,
            location=GeoLocation(utm_x=100, utm_y=25, utm_epsg=32610),
        ),
        SampleSite(
            site_id="DN3",
            site_type=SiteType.DN,
            location=GeoLocation(utm_x=100, utm_y=50, utm_epsg=32610),
        ),
        SampleSite(
            site_id="CN4",
            site_type=SiteType.CN,
            location=GeoLocation(utm_x=200, utm_y=0, utm_epsg=32610),
        ),
        SampleSite(
            site_id="CN5",
            site_type=SiteType.CN,
            location=GeoLocation(utm_x=200, utm_y=25, utm_epsg=32610),
        ),
        SampleSite(
            site_id="CN6",
            site_type=SiteType.CN,
            location=GeoLocation(utm_x=200, utm_y=50, utm_epsg=32610),
        ),
    ]

    sectors = [
        Sector(site=sites[0], node_id=0, position_in_node=0, ant_azimuth=90),
        Sector(site=sites[1], node_id=0, position_in_node=0, ant_azimuth=90),
        Sector(site=sites[1], node_id=1, position_in_node=0, ant_azimuth=270),
        Sector(site=sites[2], node_id=0, position_in_node=0, ant_azimuth=90),
        Sector(site=sites[2], node_id=1, position_in_node=0, ant_azimuth=270),
        Sector(site=sites[3], node_id=0, position_in_node=0, ant_azimuth=90),
        Sector(site=sites[3], node_id=1, position_in_node=0, ant_azimuth=270),
        Sector(site=sites[4], node_id=0, position_in_node=0, ant_azimuth=270),
        Sector(site=sites[5], node_id=0, position_in_node=0, ant_azimuth=270),
        Sector(site=sites[6], node_id=0, position_in_node=0, ant_azimuth=270),
    ]

    links = [
        Link(tx_sector=sectors[0], rx_sector=sectors[2]),  # POP0->DN1
        Link(tx_sector=sectors[2], rx_sector=sectors[0]),  # DN1->POP0
        Link(tx_sector=sectors[0], rx_sector=sectors[4]),  # POP0->DN2
        Link(tx_sector=sectors[4], rx_sector=sectors[0]),  # DN2->POP0
        Link(tx_sector=sectors[0], rx_sector=sectors[6]),  # POP0->DN3
        Link(tx_sector=sectors[6], rx_sector=sectors[0]),  # DN3->POP0
        Link(tx_sector=sectors[1], rx_sector=sectors[7]),  # DN1->CN4
        Link(tx_sector=sectors[3], rx_sector=sectors[8]),  # DN2->CN5
        Link(tx_sector=sectors[5], rx_sector=sectors[9]),  # DN3->CN6
    ]

    topology = Topology(sites=sites, sectors=sectors, links=links)

    params = (
        OptimizerParams(device_list=[DEFAULT_DN_DEVICE, DEFAULT_CN_DEVICE])
        if params is None
        else params
    )
    prepare_topology_for_optimization(topology, params)
    return topology


def dn_cn_limit_topology(params: Optional[OptimizerParams] = None) -> Topology:
    sites = [
        SampleSite(
            site_id="POP0",
            site_type=SiteType.POP,
            location=GeoLocation(utm_x=0, utm_y=0, utm_epsg=32610),
        ),
        SampleSite(
            site_id="CN1",
            site_type=SiteType.CN,
            location=GeoLocation(utm_x=200, utm_y=15, utm_epsg=32610),
        ),
        SampleSite(
            site_id="CN2",
            site_type=SiteType.CN,
            location=GeoLocation(utm_x=200, utm_y=40, utm_epsg=32610),
        ),
        SampleSite(
            site_id="CN3",
            site_type=SiteType.CN,
            location=GeoLocation(utm_x=200, utm_y=65, utm_epsg=32610),
        ),
        SampleSite(
            site_id="CN4",
            site_type=SiteType.CN,
            location=GeoLocation(utm_x=200, utm_y=90, utm_epsg=32610),
        ),
        SampleSite(
            site_id="CN5",
            site_type=SiteType.CN,
            location=GeoLocation(utm_x=200, utm_y=-15, utm_epsg=32610),
        ),
        SampleSite(
            site_id="CN6",
            site_type=SiteType.CN,
            location=GeoLocation(utm_x=200, utm_y=-40, utm_epsg=32610),
        ),
        SampleSite(
            site_id="CN7",
            site_type=SiteType.CN,
            location=GeoLocation(utm_x=200, utm_y=-65, utm_epsg=32610),
        ),
        SampleSite(
            site_id="CN8",
            site_type=SiteType.CN,
            location=GeoLocation(utm_x=200, utm_y=-90, utm_epsg=32610),
        ),
    ]

    sectors = [
        Sector(site=sites[0], node_id=0, position_in_node=0, ant_azimuth=90),
        Sector(site=sites[1], node_id=0, position_in_node=0, ant_azimuth=270),
        Sector(site=sites[2], node_id=0, position_in_node=0, ant_azimuth=270),
        Sector(site=sites[3], node_id=0, position_in_node=0, ant_azimuth=270),
        Sector(site=sites[4], node_id=0, position_in_node=0, ant_azimuth=270),
        Sector(site=sites[5], node_id=0, position_in_node=0, ant_azimuth=270),
        Sector(site=sites[6], node_id=0, position_in_node=0, ant_azimuth=270),
        Sector(site=sites[7], node_id=0, position_in_node=0, ant_azimuth=270),
        Sector(site=sites[8], node_id=0, position_in_node=0, ant_azimuth=270),
    ]

    links = [
        Link(tx_sector=sectors[0], rx_sector=sectors[1]),  # POP0->CN1
        Link(tx_sector=sectors[0], rx_sector=sectors[2]),  # POP0->CN2
        Link(tx_sector=sectors[0], rx_sector=sectors[3]),  # POP0->CN3
        Link(tx_sector=sectors[0], rx_sector=sectors[4]),  # POP0->CN4
        Link(tx_sector=sectors[0], rx_sector=sectors[5]),  # POP0->CN5
        Link(tx_sector=sectors[0], rx_sector=sectors[6]),  # POP0->CN6
        Link(tx_sector=sectors[0], rx_sector=sectors[7]),  # POP0->CN7
        Link(tx_sector=sectors[0], rx_sector=sectors[8]),  # POP0->CN8
    ]

    topology = Topology(sites=sites, sectors=sectors, links=links)

    params = (
        OptimizerParams(device_list=[DEFAULT_DN_DEVICE, DEFAULT_CN_DEVICE])
        if params is None
        else params
    )
    prepare_topology_for_optimization(topology, params)
    return topology


def different_sector_angle_topology(
    params: Optional[OptimizerParams] = None,
) -> Topology:
    sites = [
        SampleSite(
            site_id="POP0",
            site_type=SiteType.POP,
            location=GeoLocation(utm_x=0, utm_y=0, utm_epsg=32610),
        ),
        SampleSite(
            site_id="DN1",
            site_type=SiteType.DN,
            location=GeoLocation(utm_x=100, utm_y=0, utm_epsg=32610),
        ),
        SampleSite(
            site_id="DN2",
            site_type=SiteType.DN,
            location=GeoLocation(utm_x=100, utm_y=25, utm_epsg=32610),
        ),
        SampleSite(
            site_id="CN3",
            site_type=SiteType.CN,
            location=GeoLocation(utm_x=200, utm_y=0, utm_epsg=32610),
        ),
        SampleSite(
            site_id="CN4",
            site_type=SiteType.CN,
            location=GeoLocation(utm_x=200, utm_y=25, utm_epsg=32610),
        ),
    ]

    sectors = [
        Sector(site=sites[0], node_id=0, position_in_node=0, ant_azimuth=115),
        Sector(site=sites[0], node_id=1, position_in_node=0, ant_azimuth=45),
        Sector(site=sites[1], node_id=0, position_in_node=0, ant_azimuth=90),
        Sector(site=sites[1], node_id=1, position_in_node=0, ant_azimuth=270),
        Sector(site=sites[2], node_id=0, position_in_node=0, ant_azimuth=90),
        Sector(site=sites[2], node_id=1, position_in_node=0, ant_azimuth=270),
        Sector(site=sites[3], node_id=0, position_in_node=0, ant_azimuth=270),
        Sector(site=sites[4], node_id=0, position_in_node=0, ant_azimuth=270),
    ]

    links = [
        Link(tx_sector=sectors[0], rx_sector=sectors[3]),  # POP0->DN1
        Link(tx_sector=sectors[3], rx_sector=sectors[0]),  # DN1->POP0
        Link(tx_sector=sectors[1], rx_sector=sectors[5]),  # POP0->DN2
        Link(tx_sector=sectors[5], rx_sector=sectors[1]),  # DN2->POP0
        Link(tx_sector=sectors[2], rx_sector=sectors[6]),  # DN1->CN3
        Link(tx_sector=sectors[4], rx_sector=sectors[7]),  # DN2->CN4
    ]

    topology = Topology(sites=sites, sectors=sectors, links=links)

    params = (
        OptimizerParams(device_list=[DEFAULT_DN_DEVICE, DEFAULT_CN_DEVICE])
        if params is None
        else params
    )
    prepare_topology_for_optimization(topology, params)
    return topology


def near_far_effect_topology(
    params: Optional[OptimizerParams] = None,
) -> Topology:
    sites = [
        SampleSite(
            site_id="POP0",
            site_type=SiteType.POP,
            location=GeoLocation(utm_x=0, utm_y=0, utm_epsg=32610),
        ),
        SampleSite(
            site_id="DN1",
            site_type=SiteType.DN,
            location=GeoLocation(utm_x=400, utm_y=0, utm_epsg=32610),
        ),
        SampleSite(
            site_id="DN2",
            site_type=SiteType.DN,
            location=GeoLocation(utm_x=100, utm_y=25, utm_epsg=32610),
        ),
        SampleSite(
            site_id="CN3",
            site_type=SiteType.CN,
            location=GeoLocation(utm_x=500, utm_y=0, utm_epsg=32610),
        ),
        SampleSite(
            site_id="CN4",
            site_type=SiteType.CN,
            location=GeoLocation(utm_x=200, utm_y=25, utm_epsg=32610),
        ),
    ]

    sectors = [
        Sector(site=sites[0], node_id=0, position_in_node=0, ant_azimuth=115),
        Sector(site=sites[0], node_id=1, position_in_node=0, ant_azimuth=45),
        Sector(site=sites[1], node_id=0, position_in_node=0, ant_azimuth=90),
        Sector(site=sites[1], node_id=1, position_in_node=0, ant_azimuth=270),
        Sector(site=sites[2], node_id=0, position_in_node=0, ant_azimuth=90),
        Sector(site=sites[2], node_id=1, position_in_node=0, ant_azimuth=270),
        Sector(site=sites[3], node_id=0, position_in_node=0, ant_azimuth=270),
        Sector(site=sites[4], node_id=0, position_in_node=0, ant_azimuth=270),
    ]

    links = [
        Link(tx_sector=sectors[0], rx_sector=sectors[3]),  # POP0->DN1
        Link(tx_sector=sectors[3], rx_sector=sectors[0]),  # DN1->POP0
        Link(tx_sector=sectors[1], rx_sector=sectors[5]),  # POP0->DN2
        Link(tx_sector=sectors[5], rx_sector=sectors[1]),  # DN2->POP0
        Link(tx_sector=sectors[2], rx_sector=sectors[6]),  # DN1->CN3
        Link(tx_sector=sectors[4], rx_sector=sectors[7]),  # DN2->CN4
    ]

    topology = Topology(sites=sites, sectors=sectors, links=links)

    params = (
        OptimizerParams(device_list=[DEFAULT_DN_DEVICE, DEFAULT_CN_DEVICE])
        if params is None
        else params
    )
    prepare_topology_for_optimization(topology, params)
    return topology


def hop_count_topology(
    params: Optional[OptimizerParams] = None,
) -> Topology:
    """
     DN2 ----- DN3 ----- DN4 ----- DN5
     |                              |
     |                              |
    POP0 ------------------------- DN1 ----- CN
    """
    sites = [
        SampleSite(
            site_id="POP0",
            site_type=SiteType.POP,
            location=GeoLocation(utm_x=0, utm_y=0, utm_epsg=32610),
        ),
        SampleSite(
            site_id="DN1",
            site_type=SiteType.DN,
            location=GeoLocation(utm_x=100, utm_y=0, utm_epsg=32610),
        ),
        SampleSite(
            site_id="DN2",
            site_type=SiteType.DN,
            location=GeoLocation(utm_x=0, utm_y=100, utm_epsg=32610),
        ),
        SampleSite(
            site_id="DN3",
            site_type=SiteType.DN,
            location=GeoLocation(utm_x=25, utm_y=100, utm_epsg=32610),
        ),
        SampleSite(
            site_id="DN4",
            site_type=SiteType.DN,
            location=GeoLocation(utm_x=75, utm_y=100, utm_epsg=32610),
        ),
        SampleSite(
            site_id="DN5",
            site_type=SiteType.DN,
            location=GeoLocation(utm_x=100, utm_y=100, utm_epsg=32610),
        ),
        SampleSite(
            site_id="CN6",
            site_type=SiteType.CN,
            location=GeoLocation(utm_x=150, utm_y=0, utm_epsg=32610),
        ),
    ]

    links = [
        Link(tx_site=sites[0], rx_site=sites[1]),  # POP0->DN1
        Link(tx_site=sites[1], rx_site=sites[0]),  # DN1->POP0
        Link(tx_site=sites[0], rx_site=sites[2]),  # POP0->DN2
        Link(tx_site=sites[2], rx_site=sites[0]),  # DN2->POP0
        Link(tx_site=sites[2], rx_site=sites[3]),  # DN2->DN3
        Link(tx_site=sites[3], rx_site=sites[2]),  # DN3->DN2
        Link(tx_site=sites[3], rx_site=sites[4]),  # DN3->DN4
        Link(tx_site=sites[4], rx_site=sites[3]),  # DN4->DN3
        Link(tx_site=sites[4], rx_site=sites[5]),  # DN4->DN5
        Link(tx_site=sites[5], rx_site=sites[4]),  # DN5->DN4
        Link(tx_site=sites[1], rx_site=sites[5]),  # DN1->DN5
        Link(tx_site=sites[5], rx_site=sites[1]),  # DN5->DN1
        Link(tx_site=sites[1], rx_site=sites[6]),  # DN1->CN6
    ]

    topology = Topology(sites=sites, links=links)

    params = (
        OptimizerParams(device_list=[DEFAULT_DN_DEVICE, DEFAULT_CN_DEVICE])
        if params is None
        else params
    )
    prepare_topology_for_optimization(topology, params)
    return topology


def tdm_constraint_topology(
    params: Optional[OptimizerParams] = None,
) -> Topology:
    """
    POP0 --- CN1
      |
      ------ CN2
      |
      ------ CN3
    """
    sites = [
        SampleSite(
            site_id="POP0",
            site_type=SiteType.POP,
            location=GeoLocation(utm_x=0, utm_y=0, utm_epsg=32610),
        ),
        SampleSite(
            site_id="CN1",
            site_type=SiteType.CN,
            location=GeoLocation(utm_x=100, utm_y=0, utm_epsg=32610),
        ),
        SampleSite(
            site_id="CN2",
            site_type=SiteType.CN,
            location=GeoLocation(utm_x=100, utm_y=25, utm_epsg=32610),
        ),
        SampleSite(
            site_id="CN3",
            site_type=SiteType.CN,
            location=GeoLocation(utm_x=100, utm_y=50, utm_epsg=32610),
        ),
    ]

    sectors = [
        Sector(site=sites[0], node_id=0, position_in_node=0, ant_azimuth=75),
        Sector(site=sites[1], node_id=0, position_in_node=0, ant_azimuth=270),
        Sector(site=sites[2], node_id=0, position_in_node=0, ant_azimuth=270),
        Sector(site=sites[3], node_id=0, position_in_node=0, ant_azimuth=270),
    ]

    links = [
        Link(tx_site=sites[0], rx_site=sites[1]),  # POP0->CN1
        Link(tx_site=sites[0], rx_site=sites[2]),  # POP0->CN2
        Link(tx_site=sites[0], rx_site=sites[3]),  # POP0->CN3
    ]

    topology = Topology(sites=sites, sectors=sectors, links=links)

    params = (
        OptimizerParams(device_list=[DEFAULT_DN_DEVICE, DEFAULT_CN_DEVICE])
        if params is None
        else params
    )
    prepare_topology_for_optimization(topology, params)
    return topology


def tdm_cn_constraint_topology(
    params: Optional[OptimizerParams] = None,
) -> Topology:
    """
    POP0 -> CN2 <- POP1
    """
    sites = [
        SampleSite(
            site_id="POP0",
            site_type=SiteType.POP,
            location=GeoLocation(utm_x=0, utm_y=0, utm_epsg=32610),
        ),
        SampleSite(
            site_id="POP1",
            site_type=SiteType.POP,
            location=GeoLocation(utm_x=200, utm_y=0, utm_epsg=32610),
        ),
        SampleSite(
            site_id="CN2",
            site_type=SiteType.CN,
            location=GeoLocation(utm_x=100, utm_y=0, utm_epsg=32610),
        ),
    ]

    sectors = [
        Sector(site=sites[0], node_id=0, position_in_node=0, ant_azimuth=90),
        Sector(site=sites[1], node_id=0, position_in_node=0, ant_azimuth=270),
        Sector(site=sites[2], node_id=0, position_in_node=0, ant_azimuth=0),
    ]

    links = [
        Link(tx_site=sites[0], rx_site=sites[2]),  # POP0->CN2
        Link(tx_site=sites[1], rx_site=sites[2]),  # POP1->CN2
    ]

    topology = Topology(sites=sites, sectors=sectors, links=links)

    params = (
        OptimizerParams(device_list=[DEFAULT_DN_DEVICE, DEFAULT_CN_DEVICE])
        if params is None
        else params
    )
    prepare_topology_for_optimization(topology, params)

    # Create multiple demand sites on the CN
    for demand in topology.demand_sites.values():
        demand.num_sites = 2

    return topology


def dpa_topology(params: Optional[OptimizerParams] = None) -> Topology:
    sites = [
        SampleSite(
            site_id="POP1",
            site_type=SiteType.POP,
            location=GeoLocation(utm_x=-150, utm_y=450, utm_epsg=32631),
        ),
        SampleSite(
            site_id="POP2",
            site_type=SiteType.POP,
            location=GeoLocation(utm_x=-150, utm_y=0, utm_epsg=32631),
        ),
        SampleSite(
            site_id="DN3",
            site_type=SiteType.DN,
            location=GeoLocation(utm_x=0, utm_y=450, utm_epsg=32631),
        ),
        SampleSite(
            site_id="DN4",
            site_type=SiteType.DN,
            location=GeoLocation(utm_x=0, utm_y=300, utm_epsg=32631),
        ),
        SampleSite(
            site_id="DN5",
            site_type=SiteType.DN,
            location=GeoLocation(utm_x=150, utm_y=300, utm_epsg=32631),
        ),
        SampleSite(
            site_id="DN6",
            site_type=SiteType.DN,
            location=GeoLocation(utm_x=0, utm_y=150, utm_epsg=32631),
        ),
        SampleSite(
            site_id="DN7",
            site_type=SiteType.DN,
            location=GeoLocation(utm_x=150, utm_y=150, utm_epsg=32631),
        ),
        SampleSite(
            site_id="DN8",
            site_type=SiteType.DN,
            location=GeoLocation(utm_x=0, utm_y=0, utm_epsg=32631),
        ),
        SampleSite(
            site_id="CN9",
            site_type=SiteType.CN,
            location=GeoLocation(utm_x=150, utm_y=450, utm_epsg=32631),
        ),
        SampleSite(
            site_id="CN10",
            site_type=SiteType.CN,
            location=GeoLocation(utm_x=150, utm_y=0, utm_epsg=32631),
        ),
    ]

    sectors = [
        Sector(site=sites[0], node_id=0, position_in_node=0, ant_azimuth=112.5),
        Sector(site=sites[1], node_id=0, position_in_node=0, ant_azimuth=67.5),
        Sector(site=sites[2], node_id=0, position_in_node=0, ant_azimuth=270),
        Sector(site=sites[2], node_id=1, position_in_node=0, ant_azimuth=90),
        Sector(site=sites[3], node_id=0, position_in_node=0, ant_azimuth=315),
        Sector(site=sites[3], node_id=1, position_in_node=0, ant_azimuth=90),
        Sector(site=sites[3], node_id=2, position_in_node=0, ant_azimuth=180),
        Sector(site=sites[4], node_id=0, position_in_node=0, ant_azimuth=270),
        Sector(site=sites[4], node_id=1, position_in_node=0, ant_azimuth=0),
        Sector(site=sites[5], node_id=0, position_in_node=0, ant_azimuth=225),
        Sector(site=sites[5], node_id=1, position_in_node=0, ant_azimuth=0),
        Sector(site=sites[5], node_id=2, position_in_node=0, ant_azimuth=90),
        Sector(site=sites[6], node_id=0, position_in_node=0, ant_azimuth=270),
        Sector(site=sites[6], node_id=1, position_in_node=0, ant_azimuth=180),
        Sector(site=sites[7], node_id=0, position_in_node=0, ant_azimuth=270),
        Sector(site=sites[7], node_id=1, position_in_node=0, ant_azimuth=90),
        Sector(site=sites[8], node_id=0, position_in_node=0, ant_azimuth=270),
        Sector(site=sites[9], node_id=0, position_in_node=0, ant_azimuth=0),
    ]

    links = [
        Link(tx_sector=sectors[0], rx_sector=sectors[2]),  # POP1->DN3
        Link(tx_sector=sectors[0], rx_sector=sectors[4]),  # POP1->DN4
        Link(tx_sector=sectors[1], rx_sector=sectors[9]),  # POP2->DN6
        Link(tx_sector=sectors[1], rx_sector=sectors[14]),  # POP2->DN8
        Link(tx_sector=sectors[3], rx_sector=sectors[16]),  # DN3->CN9
        Link(tx_sector=sectors[5], rx_sector=sectors[7]),  # DN4->DN5
        Link(tx_sector=sectors[6], rx_sector=sectors[10]),  # DN4->DN6
        Link(tx_sector=sectors[8], rx_sector=sectors[16]),  # DN5->CN9
        Link(tx_sector=sectors[10], rx_sector=sectors[6]),  # DN6->DN4
        Link(tx_sector=sectors[11], rx_sector=sectors[12]),  # DN6->DN7
        Link(tx_sector=sectors[13], rx_sector=sectors[17]),  # DN7->CN10
        Link(tx_sector=sectors[15], rx_sector=sectors[17]),  # DN8->CN10
    ]

    topology = Topology(sites=sites, sectors=sectors, links=links)

    params = (
        OptimizerParams(device_list=[DEFAULT_DN_DEVICE, DEFAULT_CN_DEVICE])
        if params is None
        else params
    )
    prepare_topology_for_optimization(topology, params)
    return topology
