# Copyright (c) Meta Platforms, Inc. and affiliates.

# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

import itertools
import logging
import os
from io import StringIO
from time import time
from typing import Dict, List, Optional, Set, Tuple, Union
from xml.sax.saxutils import escape

from pyre_extensions import none_throws

from terragraph_planner.common.configuration.enums import (
    DebugFile,
    LinkType,
    OutputFile,
    SiteType,
    StatusType,
)
from terragraph_planner.common.data_io.data_key import LinkKey, SiteKey
from terragraph_planner.common.exceptions import (
    TopologyException,
    planner_assert,
)
from terragraph_planner.common.geos import lat_lon_to_geo_hash
from terragraph_planner.common.topology_models.demand_site import DemandSite
from terragraph_planner.common.topology_models.link import Link
from terragraph_planner.common.topology_models.site import Site
from terragraph_planner.common.topology_models.topology import Topology
from terragraph_planner.common.utils import current_system_params
from terragraph_planner.optimization.constants import UNASSIGNED_CHANNEL

# KML site styles: Dict[type, Dict[status, Tuple[icon, color_code, scale]]]
SITE_STYLES: Dict[str, Dict[str, Tuple[str, str, float]]] = {
    "POP": {
        "UNAVAILABLE": ("placemark_square", "ffe1b9f7", 1.0),
        "CANDIDATE": ("placemark_square", "ffe1b9f7", 1.0),
        "PROPOSED": ("placemark_square", "ffe1b9f7", 1.0),
        "EXISTING": ("placemark_square", "ffe1b9f7", 1.0),
    },
    "DN": {
        "UNAVAILABLE": ("placemark_circle", "ff76e600", 1.0),
        "UNREACHABLE": ("placemark_circle", "ff76e600", 1.0),
        "CANDIDATE": ("placemark_circle", "ff76e600", 1.0),
        "PROPOSED": ("placemark_circle", "ff76e600", 1.0),
        "EXISTING": ("placemark_circle", "ff76e600", 1.0),
    },
    "CN": {
        "UNAVAILABLE": ("shaded_dot", "ff00ffff", 0.7),
        "UNREACHABLE": ("shaded_dot", "ff00ffff", 0.7),
        "CANDIDATE": ("shaded_dot", "fff900d5", 0.7),
        "PROPOSED": ("shaded_dot", "ffecf51f", 0.7),
        "EXISTING": ("shaded_dot", "ffecf51f", 0.7),
    },
}
UNKNOWN_SITE_STYLE = ("wht-blank", "ffffffff")
# KML link styles: Dict[status, Dict[type, color_code]]
LINK_COLORS: Dict[str, Dict[str, str]] = {
    "UNAVAILABLE": {
        "Backhaul": "ff00ffff",
        "Access": "ff00ffff",
    },
    "UNREACHABLE": {
        "Backhaul": "ff00ffff",
        "Access": "ff00ffff",
    },
    "CANDIDATE": {"Backhaul": "fff900d5", "Access": "fff900d5"},
    "PROPOSED": {"Backhaul": "fffb3b33", "Access": "ffecf51f"},
    "EXISTING": {"Backhaul": "fffb3b33", "Access": "ffecf51f"},
}
HIGH_UTIL_LINK_COLORS: Dict[str, str] = {
    "PROPOSED": "ff26a7ff",
    "EXISTING": "ff26a7ff",
}
LINK_WIDTH: Dict[str, float] = {
    "Backhaul": 3,
    "Access": 1,
    "Wired": 3,
}
DEMAND_COLORS = {0: "ffb4fab2", 1: "ff84c781", 2: "ff579651"}
DEMAND_SCALE = 0.6
WIRED_LINK_COLOR = "ff000000"
DEFAULT_VISIBILITY = 0

# If a link has higher than 80% utilization, give it a different color
HIGH_UTIL_THRES = 80
HIGH_UTIL_STR = "_high_util"

COMPONENT_VISIBILITY: Dict[StatusType, int] = {
    StatusType.PROPOSED: 1,
    StatusType.EXISTING: 0,
    StatusType.CANDIDATE: 0,
    StatusType.UNAVAILABLE: 0,
    StatusType.UNREACHABLE: 1,
}

logger: logging.Logger = logging.getLogger(__name__)


def dump_topology_to_kml(
    topology: "Topology",
    file_type: Union[OutputFile, DebugFile],
) -> None:
    """
    Dump the Topology file to the KML file. This functions determines the
    dumped file path according to the file_type and writes to to logger.
    While the following function write_to_kml_file should be called with a
    file_path.

    It is recommended to use this function, instead of write_to_kml_file,
    when you set global debug_mode correctly. Only use write_to_kml_file
    when you want to have your own file path.
    """
    # Dump the topology if it's an output file or the debug mode is on
    is_output_file = isinstance(file_type, OutputFile)
    if is_output_file or current_system_params.debug_mode:
        time_suffix = "".join(str(time()).split("."))
        if is_output_file:
            dump_dir = os.path.join(current_system_params.output_dir, "output")
            file_name = f"{file_type.name.lower()}.kml"
        else:
            dump_dir = os.path.join(current_system_params.output_dir, "debug")
            file_name = f"{file_type.name.lower()}_{time_suffix}.kml"

        if not os.path.exists(dump_dir):
            os.mkdir(dump_dir)
        full_file_path = os.path.join(dump_dir, file_name)
        write_to_kml_file(topology, os.path.join(dump_dir, file_name))
        logger.info(
            f"{file_type.name.lower()} has been dumped to {full_file_path}"
        )


def write_to_kml_file(
    topology: "Topology",
    kml_file_path: str,
) -> None:
    """
    Convert a Topology to KML str.

    @param topology
    The topology to be converted.

    @param kml_file_path
    The path that the KML file to be written to.
    """
    markup_string = StringIO()
    _set_styles(markup_string, topology.name)
    _add_sites_links(markup_string, topology)
    _add_demands(markup_string, topology)

    markup_string.write("</Document>\n</kml>")
    kml = markup_string.getvalue()
    markup_string.close()

    with open(kml_file_path, "w") as kfile:
        kfile.write(kml)


def _add_sites_links(
    markup_string: StringIO,
    topology: "Topology",
) -> None:
    def _site_type_key(site: "Site") -> SiteType:
        return site.site_type

    def _ordered_site_type_key(site: "Site") -> Tuple[int, str]:
        return site.site_type.value, site.name

    def _link_type_key(link: "Link") -> LinkType:
        return link.link_type

    def _ordered_link_type_key(link: "Link") -> Tuple[int, str]:
        return link.link_type.value, _link_hash_key(link)

    def _link_hash_key(link: "Link") -> str:
        return link.link_hash

    def _link_utilization(link: "Link") -> float:
        return link.utilization

    for status_type in StatusType:
        sorted_sites = sorted(
            [
                site
                for site in topology.sites.values()
                if site.status_type == status_type
            ],
            key=_ordered_site_type_key,
        )
        sorted_links = sorted(
            [
                link
                for link in topology.links.values()
                if link.status_type == status_type
            ],
            key=_ordered_link_type_key,
        )
        if len(sorted_sites) == 0 and len(sorted_links) == 0:
            continue
        status_string = status_type.to_string()
        visibility = COMPONENT_VISIBILITY[status_type]
        markup_string.write(
            f'<Folder id="{status_string}"><name>{status_string}</name>'
        )
        markup_string.write(f"<visibility>{visibility}</visibility>")
        # add sites
        for site_type, sites in itertools.groupby(
            sorted_sites, key=_site_type_key
        ):
            type_string = site_type.to_string()
            markup_string.write(
                f'<Folder id="{status_string}_{type_string}_sites">'
            )
            markup_string.write(f"<name>{type_string} Sites</name>")
            markup_string.write(f"<visibility>{visibility}</visibility>")
            for site in sites:
                markup_string.write(
                    _site_markup(
                        site,
                        status_string,
                        SiteKey.kml_output_keys(),
                        visibility,
                    )
                )
            markup_string.write("</Folder>")
        # add links
        for link_type, links_subset in itertools.groupby(
            sorted_links, key=_link_type_key
        ):
            link_type = link_type.name
            markup_string.write(f'<Folder id="{link_type}_links">')
            markup_string.write(f"<name>{link_type} Links</name>")
            markup_string.write(f"<visibility>{visibility}</visibility>")
            # Output overlapped links continuously, so that users can easily find
            # the overlapped links in the navigation
            links_subset = sorted(links_subset, key=_link_hash_key)
            for _, links_group_by_hash in itertools.groupby(
                links_subset, key=_link_hash_key
            ):
                # Always let the link with highest utlization show at the top of overlapped links
                links_group_by_hash = sorted(
                    links_group_by_hash, key=_link_utilization, reverse=True
                )
                for link in links_group_by_hash:
                    markup_string.write(
                        _link_markup(
                            topology,
                            link,
                            LinkKey.kml_output_keys(),
                            visibility,
                        )
                    )
            markup_string.write("</Folder>")
        markup_string.write("</Folder>")


def _site_markup(
    site: "Site", status: str, output_site_keys: List[SiteKey], visibility: int
) -> str:
    site_type = site.site_type.to_string()
    if site_type in ["POP", "DN", "CN"]:
        style_id = site_type + "_" + status
    else:
        style_id = "UNKNOWN"
    altitude_mode = get_site_altitude_mode(site.altitude)

    extended_data = ""
    for site_key in output_site_keys:
        output_name, value_str = site_key.get_output_name_and_value(
            site, 1, True
        )
        # If the name is empty, then skip it
        if site_key != SiteKey.NAME or value_str != "N/A":
            extended_data += _data_field_markup(output_name, str(value_str))

    return f"""
    <Placemark>
        <name>{escape(site.name)}</name>
        <visibility>{visibility}</visibility>
        <styleUrl>#{style_id}</styleUrl>
        <ExtendedData>
            {extended_data}
        </ExtendedData>
        <Point>
            <altitudeMode>{altitude_mode}</altitudeMode>
            <coordinates>{site.longitude},{site.latitude},{site.altitude}</coordinates>
        </Point>
    </Placemark>
    """


def _link_markup(
    topology: "Topology",
    link: "Link",
    output_link_keys: List[LinkKey],
    visibility: int,
) -> str:
    tx_site = link.tx_site
    rx_site = link.rx_site

    link_style_prefix = "backhaul_link_"

    tx_altitude_mode = get_site_altitude_mode(tx_site.altitude)
    rx_altitude_mode = get_site_altitude_mode(rx_site.altitude)
    planner_assert(
        tx_altitude_mode == rx_altitude_mode,
        "Altitude modes of the two sites of a link should be the same.",
        TopologyException,
    )

    extended_data = ""
    rf_field_set = set(LinkKey.rf_field())
    for link_key in output_link_keys:
        # Only wireless links have rf fields
        if link_key in rf_field_set and link.link_type == LinkType.ETHERNET:
            continue
        # Two special key with different precision of float
        if link_key == LinkKey.PROPOSED_FLOW or link_key == LinkKey.CAPACITY:
            output_name, value_str = link_key.get_output_name_and_value(
                link, 2, True
            )
        else:
            output_name, value_str = link_key.get_output_name_and_value(
                link, 1, True
            )

        # Tx_beam_azimuth and rx_beam_azimuth should be 0 rather than N/A when empty
        if (
            link_key == LinkKey.TX_BEAM_AZIMUTH
            or link_key == LinkKey.RX_BEAM_AZIMUTH
        ):
            if value_str == "N/A":
                value_str = "0"
            extended_data += _data_field_markup(output_name, str(value_str))
        # The following fields cannot be fetched directly from Link class
        elif link_key == LinkKey.CHANNEL:
            link_channel = link.link_channel
            extended_data += _data_field_markup(
                output_name,
                str(link_channel)
                if link_channel > UNASSIGNED_CHANNEL
                else "UNASSIGNED",
            )
        else:
            extended_data += _data_field_markup(output_name, str(value_str))

    high_util_string = ""
    util = link.utilization
    reverse_link = topology.get_link_by_site_ids(
        rx_site.site_id, tx_site.site_id
    )
    reverse_util = reverse_link.utilization if reverse_link else 0.0
    if (
        max(util, reverse_util) > HIGH_UTIL_THRES
        and link.link_type.is_wireless()
    ):
        high_util_string = HIGH_UTIL_STR

    return f"""
    <Placemark>
        <name>{link.link_hash}</name>
        <visibility>{visibility}</visibility>
        <styleUrl>#{link_style_prefix + link.status_type.to_string() + high_util_string}</styleUrl>
        <ExtendedData>
            {extended_data}
        </ExtendedData>
        <LineString>
            <altitudeMode>{tx_altitude_mode}</altitudeMode>
            <coordinates> {tx_site.longitude},{tx_site.latitude},{tx_site.altitude}
            {rx_site.longitude},{rx_site.latitude},{rx_site.altitude}
            </coordinates>
        </LineString>
    </Placemark>
    """


def _data_field_markup(field_name: str, field_value: str) -> str:
    return f"""
        <Data name="{field_name}">
            <value>{field_value}</value>
        </Data>
    """


def _add_demands(
    markup_string: StringIO,
    topology: "Topology",
) -> None:
    # Wrtie demand folder
    markup_string.write('<Folder id="demand">')
    markup_string.write("<name>Demand</name>")
    markup_string.write(f"<visibility>{DEFAULT_VISIBILITY}</visibility>")
    markup_string.write('<Folder id="sites_demand">')
    markup_string.write("<name>Demand Sites</name>")
    markup_string.write(f"<visibility>{DEFAULT_VISIBILITY}</visibility>")
    demand_values: Set[float] = {
        _.demand or 0 for _ in topology.demand_sites.values()
    }
    if len(demand_values):
        max_demand = max(demand_values)
        for site_id, site_data in topology.demand_sites.items():
            # Linear color mapping
            scale = (
                int(
                    none_throws(site_data.demand)
                    / max_demand
                    * len(DEMAND_COLORS)
                )
                if len(demand_values) > 1
                else 0
            )  # Uniform demand, use normal color
            if scale >= len(DEMAND_COLORS):
                scale = len(DEMAND_COLORS) - 1
            markup_string.write(_demand_markup(site_id, site_data, scale))
    markup_string.write("</Folder>")

    # Write demand connections folder
    markup_string.write('<Folder id="conns_demand">')
    markup_string.write("<name>Demand Connections</name>")
    markup_string.write(f"<visibility>{DEFAULT_VISIBILITY}</visibility>")
    for demand_data in topology.demand_sites.values():
        connected_site = demand_data.connected_sites
        for site in connected_site:
            if site.status_type in StatusType.active_status():
                site_data = site
                markup_string.write(
                    f"""
                    <Placemark>
                        <name>link_{site_data.site_id}_{demand_data.demand_id}</name>
                        <visibility>{DEFAULT_VISIBILITY}</visibility>
                        <styleUrl>#demand_links</styleUrl>
                        <LineString>
                            <altitudeMode>clampToGround</altitudeMode>
                            <coordinates> {demand_data.longitude},{demand_data.latitude},0
                            {site_data.longitude},{site_data.latitude},0
                            </coordinates>
                        </LineString>
                    </Placemark>"""
                )
    markup_string.write("</Folder>")
    markup_string.write("</Folder>")


def _demand_markup(site_id: str, site_data: "DemandSite", scale: float) -> str:
    style_id = f"demand_site_{scale}"

    site_hash = lat_lon_to_geo_hash(site_data.latitude, site_data.longitude)
    return f"""
    <Placemark>
        <name>{site_hash}</name>
        <visibility>0</visibility>
        <ExtendedData><SchemaData schemaUrl="#site_metadata">
            <SimpleData name="site_demand">{site_data.demand}</SimpleData>
            <SimpleData name="site_type">DEMAND</SimpleData>
            <SimpleData name="status">PROPOSED</SimpleData>
        </SchemaData></ExtendedData>
        <styleUrl>#{style_id}</styleUrl>
        <Point>
            <coordinates>{site_data.longitude},{site_data.latitude},0</coordinates>
        </Point>
    </Placemark>
    """


def _set_styles(markup_string: StringIO, topology_name: Optional[str]) -> None:
    """
    Set styles of Site, Link, Demand at the beginning of KML str.
    """
    markup_string.write(
        f"""<?xml version="1.0" encoding="UTF-8"?>
        <kml xmlns="http://www.opengis.net/kml/2.2"
             xmlns:gx="http://www.google.com/kml/ext/2.2">
        <Document>
        <name>{topology_name or "topology"}</name>
        <Schema name="site_metadata" id="site_metadata">
            <SimpleField name="description" type="string"></SimpleField>
            <SimpleField name="site_hash" type="string"></SimpleField>
            <SimpleField name="site_type" type="string"></SimpleField>
            <SimpleField name="status" type="string"></SimpleField>
        </Schema>
    """
    )
    for site_type, node_styles in SITE_STYLES.items():
        for status, (icon, color, scale) in node_styles.items():
            markup_string.write(
                _site_style(site_type + "_" + status, icon, color, scale)
            )
    markup_string.write(
        _site_style("UNKNOWN", UNKNOWN_SITE_STYLE[0], UNKNOWN_SITE_STYLE[1])
    )
    # Demand styles with different colors
    for i, color in DEMAND_COLORS.items():
        markup_string.write(_demand_style(i, color, DEMAND_SCALE))
    markup_string.write(_demand_link_style())
    for status, color in LINK_COLORS.items():
        markup_string.write(
            _link_style(
                "backhaul_link_" + status,
                color["Backhaul"],
                width=LINK_WIDTH["Backhaul"],
            )
        )
        markup_string.write(
            _link_style(
                "access_link_" + status,
                color["Access"],
                width=LINK_WIDTH["Access"],
            )
        )
        markup_string.write(
            _link_style(
                "wired_link_" + status,
                WIRED_LINK_COLOR,
                width=LINK_WIDTH["Wired"],
            )
        )
    for status, color in HIGH_UTIL_LINK_COLORS.items():
        markup_string.write(
            _link_style(
                "backhaul_link_" + status + HIGH_UTIL_STR,
                color,
                width=LINK_WIDTH["Backhaul"],
            )
        )
        markup_string.write(
            _link_style(
                "access_link_" + status + HIGH_UTIL_STR,
                color,
                width=LINK_WIDTH["Access"],
            )
        )
    # Add legend
    markup_string.write(
        """
            <ScreenOverlay>
                <name>Legend</name>
                <Icon>
                    <href>
                    https://i.ibb.co/d0THmwL/kml-legend.png
                    </href>
                </Icon>
                <overlayXY x="0" y="0" xunits="fraction" yunits="fraction"/>
                <screenXY x="20" y="50" xunits="pixels" yunits="pixels"/>
                <rotationXY x="0.5" y="0.5" xunits="fraction" yunits="fraction"/>
                <size x="195" y="330" xunits="pixels" yunits="pixels"/>
            </ScreenOverlay>
        """
    )


def _site_style(style_id: str, icon: str, color: str, scale: float = 1) -> str:
    icon_url = f"http://maps.google.com/mapfiles/kml/shapes/{icon}.png"
    return f"""
        <Style id="{style_id}">
            <IconStyle>
                <color>{color}</color>
                <scale>{scale}</scale>
                <Icon>
                    <href>{icon_url}</href>
                    <scale>1.0</scale>
                </Icon>
            </IconStyle>
            <LabelStyle>
                <scale>0</scale>
            </LabelStyle>
        </Style>
    """


def _link_style(style_id: str, color: str, width: float = 1) -> str:
    return f"""
        <Style id="{style_id}">
            <LineStyle>
                <color>{color}</color>
                <width>{width}</width>
            </LineStyle>
        </Style>
    """


def _demand_style(n: int, color: str, scale: float) -> str:
    return f"""
        <Style id="demand_site_{n}">
            <IconStyle>
                <color>{color}</color>
                <scale>{scale}</scale>
                <Icon>
                    <href>
                        http://maps.google.com/mapfiles/kml/shapes/shaded_dot.png
                    </href>
                </Icon>
            </IconStyle>
            <LabelStyle>
                <scale>0</scale>
            </LabelStyle>
        </Style>
    """


def _demand_link_style() -> str:
    return """
        <Style id="demand_links">
            <LineStyle>
                <color>ffffcc66</color>
                <width>1</width>
            </LineStyle>
        </Style>
    """


def get_site_altitude_mode(altitude: Optional[float]) -> str:
    return "clampToGround" if altitude is None else "absolute"
