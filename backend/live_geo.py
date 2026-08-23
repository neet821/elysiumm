from dataclasses import dataclass
import ipaddress
from pathlib import Path
from typing import Callable

import maxminddb
from user_agents import parse as parse_user_agent

from config import config


@dataclass(frozen=True)
class VisitorFingerprint:
    country: str | None
    region: str | None
    city: str | None
    device_type: str
    operating_system: str
    browser: str


def _is_public_address(ip_address: str) -> bool:
    try:
        address = ipaddress.ip_address(ip_address)
    except ValueError:
        return False
    return not (
        address.is_private
        or address.is_loopback
        or address.is_link_local
        or address.is_multicast
        or address.is_reserved
        or address.is_unspecified
    )


def _localized_name(value: object) -> str | None:
    if not isinstance(value, dict):
        return None
    names = value.get("names")
    if not isinstance(names, dict):
        return None
    return names.get("zh-CN") or names.get("en")


def _database_lookup(ip_address: str) -> dict:
    database_path = Path(config.LIVE_GEOIP_DATABASE)
    if not database_path.is_file():
        return {}
    try:
        with maxminddb.open_database(database_path) as reader:
            record = reader.get(ip_address)
    except (OSError, ValueError):
        return {}
    return record if isinstance(record, dict) else {}


def identify_visitor(
    ip_address: str,
    user_agent: str,
    *,
    geo_lookup: Callable[[str], dict] | None = None,
) -> VisitorFingerprint:
    parsed_agent = parse_user_agent(user_agent or "")
    if parsed_agent.is_mobile:
        device_type = "mobile"
    elif parsed_agent.is_tablet:
        device_type = "tablet"
    elif parsed_agent.is_pc:
        device_type = "computer"
    elif parsed_agent.is_bot:
        device_type = "bot"
    else:
        device_type = "other"

    country = region = city = None
    if _is_public_address(ip_address):
        try:
            record = (geo_lookup or _database_lookup)(ip_address) or {}
        except (OSError, ValueError):
            record = {}
        country = _localized_name(record.get("country"))
        subdivisions = record.get("subdivisions")
        if isinstance(subdivisions, list) and subdivisions:
            region = _localized_name(subdivisions[0])
        region = record.get("region") or region
        city = record.get("city") if isinstance(record.get("city"), str) else (
            _localized_name(record.get("city"))
        )
        country = record.get("country") if isinstance(record.get("country"), str) else country

    return VisitorFingerprint(
        country=country,
        region=region,
        city=city,
        device_type=device_type,
        operating_system=parsed_agent.os.family or "Unknown",
        browser=parsed_agent.browser.family or "Unknown",
    )
