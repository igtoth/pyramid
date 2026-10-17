"""Genesys Cloud regions and their API and login hosts.

The list mirrors PureCloudRegionHosts of the official SDK. The login host of
every region is the API host with "api." replaced by "login.".
"""

from __future__ import annotations

import os

API_HOSTS: dict[str, str] = {
    "us_east_1": "https://api.mypurecloud.com",
    "us_east_2": "https://api.use2.us-gov-pure.cloud",
    "us_west_2": "https://api.usw2.pure.cloud",
    "ca_central_1": "https://api.cac1.pure.cloud",
    "sa_east_1": "https://api.sae1.pure.cloud",
    "mx_central_1": "https://api.mxc1.pure.cloud",
    "eu_west_1": "https://api.mypurecloud.ie",
    "eu_west_2": "https://api.euw2.pure.cloud",
    "eu_central_1": "https://api.mypurecloud.de",
    "eu_central_2": "https://api.euc2.pure.cloud",
    "eusc_de_east_1": "https://api.edee1.eusc-pure.cloud",
    "me_central_1": "https://api.mec1.pure.cloud",
    "ap_south_1": "https://api.aps1.pure.cloud",
    "ap_southeast_1": "https://api.apse1.pure.cloud",
    "ap_southeast_2": "https://api.mypurecloud.com.au",
    "ap_northeast_1": "https://api.mypurecloud.jp",
    "ap_northeast_2": "https://api.apne2.pure.cloud",
    "ap_northeast_3": "https://api.apne3.pure.cloud",
}

REGIONS: list[str] = list(API_HOSTS)


def api_base(region: str) -> str:
    """API base URL for a region. PYRAMID_API_BASE overrides it (tests, mocks)."""
    override = os.environ.get("PYRAMID_API_BASE")
    if override:
        return override.rstrip("/")
    try:
        return API_HOSTS[region]
    except KeyError:
        raise ValueError(f"Unknown region: {region!r}") from None


def login_base(region: str) -> str:
    """Login (OAuth) base URL for a region. PYRAMID_LOGIN_BASE overrides it."""
    override = os.environ.get("PYRAMID_LOGIN_BASE")
    if override:
        return override.rstrip("/")
    return api_base(region).replace("://api.", "://login.", 1)
