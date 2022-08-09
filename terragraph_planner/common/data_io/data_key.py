# Copyright (c) Meta Platforms, Inc. and affiliates.

# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

from enum import Enum
from typing import TYPE_CHECKING, List, NamedTuple, Set, Tuple, TypeVar, Union
from xml.sax.saxutils import escape

from terragraph_planner.common.configuration.enums import EnumParser

if TYPE_CHECKING:
    from terragraph_planner.common.topology_models.link import Link
    from terragraph_planner.common.topology_models.sector import Sector
    from terragraph_planner.common.topology_models.site import Site


class OutputDataAttr(NamedTuple):
    """
    Attribute of a data (site, link, sector, etc). e.g. site type, link distance.
    internal_name is the name of attribute internally, used to get the attribute value.
    e.g. getattr(site, internal_name, None).
    If the value cannot be directly get by this way, leave internal_name an empty str.
    output_name is the name of attribute that we output to external.
    """

    internal_name: str
    output_name: str


class DataAttr(NamedTuple):
    """
    Like OutputDataAttr, but DataAttr can also be inputted by users, so we need an extra
    field possible_input_names to parse the input.
    """

    internal_name: str
    output_name: str
    possible_input_names: Set[str]


class BaseDataKey(Enum):
    def get_output_name_and_value(
        self,
        data: Union["Site", "Link", "Sector"],
        digits_for_float: int,
        xml_output: bool,
    ) -> Tuple[str, Union[str, float, int, bool]]:
        """
        Get the output name and value of the key.

        @param data
        The data, which can be Site, Link or Sector, to get the value from.

        @param digites_for_float
        The number of digits for a float value.

        @param xml_output
        If the value is used for xml output. If True, the escape characters
        will be used.
        """
        v = data
        for attr_name in self.value.internal_name.split("."):
            v = getattr(v, attr_name, None)
            if v is None:
                break
        if isinstance(v, float):
            v = round(v, digits_for_float)
        if v is None:
            v = "N/A"
        elif isinstance(v, EnumParser):
            v = v.to_string()

        if xml_output:
            v = escape(str(v))
        return self.value.output_name, v


class SiteKey(BaseDataKey):
    # Keys can be got from input
    LATITUDE = DataAttr("latitude", "Lat", {"base_lat", "latitude", "lat"})
    LONGITUDE = DataAttr("longitude", "Lon", {"base_lon", "longitude", "lon"})
    ALTITUDE = DataAttr("altitude", "Altitude", {"altitude", "alt"})
    HEIGHT = DataAttr(
        "height",
        "Height",
        {
            "height",
            "install_height",
            "site_height",
            "height_m",
            "height(m)",
            "height (m)",
        },
    )
    NAME = DataAttr(
        "name", "Site Name", {"name", "site_name", "site name", "pole_name"}
    )
    SITE_TYPE = DataAttr(
        "site_type", "Site Type", {"type", "site_type", "site type"}
    )
    DEVICE_SKU = DataAttr(
        "device.device_sku", "Device SKU", {"sku", "device_sku", "device sku"}
    )
    NUMBER_OF_SUBSCRIBERS = DataAttr(
        "number_of_subscribers",
        "Number of Subscribers",
        {
            "number_of_demand_points",
            "number of demand points",
            "num_demand_points",
            "number_of_subscribers",
            "number of subscribers",
            "number of demand sites",
            "num_demand_sites",
            "demand_points",
            "demand points",
            "demand_sites",
            "demand sites",
        },
    )
    ALTITUDE_MODE = DataAttr(
        "altitude_mode",
        "Altitude Mode",
        {"altitude mode", "altitude_mode", "altitudemode"},
    )
    BUILDING_ID = DataAttr(
        "building_id", "Building Id", {"building id", "building_id"}
    )
    LOCATION_TYPE = DataAttr(
        "location_type", "Location Type", {"location type", "location_type"}
    )
    STATUS_TYPE = DataAttr(
        "status_type", "Status", {"status", "status type", "status_type"}
    )

    # Keys only in output
    SITE_GEOHASH = OutputDataAttr("site_hash", "Site Geohash")
    POLARITY = OutputDataAttr("polarity", "Polarity")
    ACTIVE_NODES = OutputDataAttr("", "Active Nodes")
    ACTIVE_SECTORS = OutputDataAttr("", "Active Sectors")
    ACTIVE_LINKS = OutputDataAttr("", "Active Links")
    BREAKDOWNS = OutputDataAttr("breakdowns", "Outages Caused")
    SITE_CAPEX = OutputDataAttr("", "Site Capex")
    HOPS_TO_NEAREST_POP = OutputDataAttr("hops", "Hops to Nearest Pop")
    OUTGOING_FLOW = OutputDataAttr("", "Outgoing Flow")
    INCOMING_FLOW = OutputDataAttr("", "Incoming Flow")

    @classmethod
    def input_keys(cls) -> List["SiteKey"]:
        return list(filter(lambda k: isinstance(k.value, DataAttr), cls))

    @classmethod
    def required_keys_for_user_input(cls) -> List[List["SiteKey"]]:
        return [[cls.LATITUDE, cls.LONGITUDE]]

    @classmethod
    def required_keys_for_topology(cls) -> List[List["SiteKey"]]:
        return [
            [
                cls.NAME,
                cls.SITE_TYPE,
                cls.LATITUDE,
                cls.LONGITUDE,
            ]
        ]

    @classmethod
    def kml_output_keys(cls) -> List["SiteKey"]:
        return [
            cls.SITE_TYPE,
            cls.SITE_GEOHASH,
            cls.ALTITUDE,
            cls.STATUS_TYPE,
            cls.POLARITY,
            cls.LOCATION_TYPE,
            cls.DEVICE_SKU,
            cls.NUMBER_OF_SUBSCRIBERS,
        ]

    @classmethod
    def csv_output_keys(cls) -> List["SiteKey"]:
        return [
            cls.SITE_GEOHASH,
            cls.STATUS_TYPE,
            cls.LATITUDE,
            cls.LONGITUDE,
            cls.ALTITUDE,
            cls.SITE_TYPE,
            cls.POLARITY,
            cls.BREAKDOWNS,
            cls.SITE_CAPEX,
            cls.ACTIVE_NODES,
            cls.ACTIVE_SECTORS,
            cls.ACTIVE_LINKS,
            cls.HOPS_TO_NEAREST_POP,
            cls.BUILDING_ID,
            cls.DEVICE_SKU,
            cls.NUMBER_OF_SUBSCRIBERS,
            cls.NAME,
            cls.OUTGOING_FLOW,
            cls.INCOMING_FLOW,
        ]


class LinkKey(BaseDataKey):
    # Keys can be got from input
    TX_SITE_NAME = DataAttr(
        "tx_site.name",
        "Tx Site Name",
        {
            "tx_site",
            "tx_site_name",
            "tx_site_id",
            "from_site",
            "from_site_name",
            "from_site_id",
        },
    )
    RX_SITE_NAME = DataAttr(
        "rx_site.name",
        "Rx Site Name",
        {
            "rx_site",
            "rx_site_name",
            "rx_site_id",
            "to_site",
            "to_site_name",
            "to_site_id",
        },
    )
    SITE1_NAME = DataAttr(
        "",
        "Site 1 Name",
        {
            "site1",
            "site1_id",
            "site1_name",
        },
    )
    SITE2_NAME = DataAttr(
        "",
        "Site 2 Name",
        {
            "site2",
            "site2_id",
            "site2_name",
        },
    )
    SITE_PAIR = DataAttr(
        "",
        "Site Pair",
        {
            "site_pair",
            "sites",
        },
    )
    CONFIDENCE_LEVEL = DataAttr(
        "confidence_level",
        "Confidence Level",
        {"confidence level", "confidence_level"},
    )
    LINK_TYPE = DataAttr("link_type", "Link Type", {"link type", "link_type"})
    STATUS_TYPE = DataAttr(
        "status_type", "Status", {"status", "status type", "status_type"}
    )

    # Keys only in output
    DISTANCE = OutputDataAttr("distance", "Distance")
    PROPOSED_FLOW = OutputDataAttr("proposed_flow", "Data Flow (Gbps)")
    CAPACITY = OutputDataAttr("capacity", "Throughput (Gbps)")
    CAPACITY_UTILIZED = OutputDataAttr("utilization", "Utilization")
    TX_BEAM_AZIMUTH = OutputDataAttr("tx_beam_azimuth", "Tx Beam Azimuth")
    RX_BEAM_AZIMUTH = OutputDataAttr("rx_beam_azimuth", "Rx Beam Azimuth")
    TX_DEV = OutputDataAttr("tx_dev", "Deviation from Tx Boresight")
    RX_DEV = OutputDataAttr("rx_dev", "Deviation from Rx Boresight")
    EL_DEV = OutputDataAttr("el_dev", "Deviation from El Boresight")
    TX_POWER = OutputDataAttr("tx_power", "Tx Power (dBm)")
    MCS = OutputDataAttr("mcs_level", "Estimated MCS")
    SNR = OutputDataAttr("snr_dbm", "Estimated SNR (dB)")
    SINR = OutputDataAttr("sinr_dbm", "Estimated SINR (dB)")
    RSL = OutputDataAttr("rsl_dbm", "Estimated RSL")
    CHANNEL = OutputDataAttr("channel", "Channel")
    TX_NODE_USED = OutputDataAttr("", "Tx Node Used")
    RX_NODE_USED = OutputDataAttr("", "Rx Node Used")
    TX_ALTITUDE = OutputDataAttr("tx_site.altitude", "Tx Altitude")
    RX_ALTITUDE = OutputDataAttr("rx_site.altitude", "Rx Altitude")
    P2MP = OutputDataAttr("p2mp", "P2MP")
    BREAKDOWNS = OutputDataAttr("breakdowns", "Outages Caused")
    TIMES_ON_MCS_ROUTE = OutputDataAttr(
        "times_on_mcs_route", "Nb times on MCS route"
    )
    SECTORS = OutputDataAttr("", "Sectors")
    SECTOR_POSITIONS = OutputDataAttr("", "Sector Positions")
    NODES = OutputDataAttr("", "Nodes")
    LINK_GEOHASH = OutputDataAttr("link_hash", "Link Geohash")
    VIOLATES_NEAR_FAR = OutputDataAttr("", "Violates Near-Far Rule")
    VIOLATES_DIFF_SECTOR_ANGLE = OutputDataAttr(
        "", "Violates Diff Sector Angle Rule"
    )
    VIOLATES_SECTOR_LIMIT = OutputDataAttr("", "Violates Sector Link Limit")

    @classmethod
    def input_keys(cls) -> List["LinkKey"]:
        return list(filter(lambda k: isinstance(k.value, DataAttr), cls))

    @classmethod
    def required_keys(cls) -> List[List["LinkKey"]]:
        return [
            [cls.SITE_PAIR],
            [cls.SITE1_NAME, cls.SITE2_NAME],
            [cls.TX_SITE_NAME, cls.RX_SITE_NAME],
        ]

    @classmethod
    def kml_output_keys(cls) -> List["LinkKey"]:
        return [
            cls.LINK_TYPE,
            cls.TX_SITE_NAME,
            cls.RX_SITE_NAME,
            cls.STATUS_TYPE,
            cls.DISTANCE,
            cls.PROPOSED_FLOW,
            cls.CAPACITY,
            cls.CAPACITY_UTILIZED,
            cls.TX_BEAM_AZIMUTH,
            cls.RX_BEAM_AZIMUTH,
            cls.TX_DEV,
            cls.RX_DEV,
            cls.EL_DEV,
            cls.TX_POWER,
            cls.MCS,
            cls.SNR,
            cls.SINR,
            cls.RSL,
            cls.CONFIDENCE_LEVEL,
            cls.CHANNEL,
        ]

    @classmethod
    def csv_output_keys(cls) -> List["LinkKey"]:
        return [
            cls.LINK_GEOHASH,
            cls.LINK_TYPE,
            cls.STATUS_TYPE,
            cls.TX_SITE_NAME,
            cls.RX_SITE_NAME,
            cls.DISTANCE,
            cls.PROPOSED_FLOW,
            cls.CAPACITY,
            cls.CAPACITY_UTILIZED,
            cls.TX_BEAM_AZIMUTH,
            cls.RX_BEAM_AZIMUTH,
            cls.TX_DEV,
            cls.RX_DEV,
            cls.EL_DEV,
            cls.TX_POWER,
            cls.MCS,
            cls.SNR,
            cls.SINR,
            cls.RSL,
            cls.SECTORS,
            cls.BREAKDOWNS,
            cls.CONFIDENCE_LEVEL,
            cls.CHANNEL,
            cls.VIOLATES_DIFF_SECTOR_ANGLE,
            cls.VIOLATES_NEAR_FAR,
            cls.VIOLATES_SECTOR_LIMIT,
        ]

    @classmethod
    def rf_field(cls) -> List["LinkKey"]:
        return [
            cls.TX_NODE_USED,
            cls.RX_NODE_USED,
            cls.TX_BEAM_AZIMUTH,
            cls.RX_BEAM_AZIMUTH,
            cls.TX_DEV,
            cls.RX_DEV,
            cls.EL_DEV,
            cls.TX_ALTITUDE,
            cls.RX_ALTITUDE,
            cls.TX_POWER,
            cls.MCS,
            cls.SNR,
            cls.SINR,
            cls.RSL,
            cls.P2MP,
            cls.BREAKDOWNS,
            cls.TIMES_ON_MCS_ROUTE,
        ]


class SectorKey(BaseDataKey):
    SECTOR_ID = OutputDataAttr("sector_id", "Sector ID")
    NODE_ID = OutputDataAttr("node_id", "Node ID")
    SECTOR_POSITION = OutputDataAttr("position_in_node", "Sector Position")
    SITE_GEOHASH = OutputDataAttr("site.site_hash", "Site Geohash")
    STATUS_TYPE = OutputDataAttr("status_type", "Status")
    AZIMUTH_ORIENTATION = OutputDataAttr("ant_azimuth", "Azimuth Orientation")
    POLARITY = OutputDataAttr("site.polarity", "Polarity")
    CHANNEL = OutputDataAttr("channel", "Channel")
    NODE_COST = OutputDataAttr("node_capex", "Node Cost")
    ACTIVE_BACKHAUL_LINKS = OutputDataAttr("", "Active Backhaul Links")
    ACTIVE_ACCESS_LINKS = OutputDataAttr("", "Active Access Links")
    SITE_TYPE = OutputDataAttr("site.site_type", "Site Type")
    VIOLATES_LINK_LOAD = OutputDataAttr("", "Violates Link Load")

    @classmethod
    def csv_output_keys(cls) -> List["SectorKey"]:
        return [sector_key for sector_key in cls]


DataKey = TypeVar("DataKey", bound=BaseDataKey)

NUMERIC_KEYS: Set[SiteKey] = {
    SiteKey.LATITUDE,
    SiteKey.LONGITUDE,
    SiteKey.ALTITUDE,
    SiteKey.HEIGHT,
    SiteKey.NUMBER_OF_SUBSCRIBERS,
}
