"""WEBENCH API client for real-time IC recommendations.

Queries TI's WEBENCH Power Designer API to get ranked IC solutions
for arbitrary voltage/current specs. Runs on the user's machine —
no API key needed, just an internet connection.

The API returns real TI reference designs with component values,
efficiency data, and thermal estimates.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass

import requests

logger = logging.getLogger(__name__)

_WEBENCH_URL = "https://webench.ti.com/wb6/restapi/power/solutions"

_DEFAULT_HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Content-Type": "application/json",
    "Referer": "https://webench.ti.com/power-designer/switching-regulator",
}


@dataclass(frozen=True)
class WebenchSolution:
    """A single IC solution from WEBENCH."""

    solution_id: str
    rank: int
    part_number: str
    base_pn: str
    topology: str
    price_usd: float
    vin_min: float
    vin_max: float
    vout_min: float
    vout_max: float
    considerations: str


def query_webench(
    vin: float,
    vout: float,
    iout: float,
    vin_max: float | None = None,
    max_results: int = 10,
) -> list[WebenchSolution]:
    """Query WEBENCH for IC recommendations.

    Args:
        vin: Nominal input voltage (V)
        vout: Output voltage (V)
        iout: Output current (A)
        vin_max: Maximum input voltage (defaults to vin)
        max_results: Maximum number of solutions to return

    Returns:
        List of WebenchSolution objects ranked by WEBENCH's optimization.
    """
    if vin_max is None:
        vin_max = vin

    payload = {
        "vinMin": vin,
        "vinMax": str(vin_max),
        "vout": [str(vout)],
        "iout": [str(iout)],
        "ambientTemp": "25",
        "isIsolated": False,
        "powerSupply": "dc",
        "optimizationSetting": 3,
        "hasAdvancedOptions": False,
        "advancedOptionsOrigin": "HDI",
        "advancedInputs": {
            "vinNom": str(vin),
            "useInputFilter": False,
            "cisprStandard": "",
            "cisprClass": "",
            "voutMaxRipple": [],
            "ioutNom": None,
            "desiredFrequency": None,
            "hasExternalFrequencySync": False,
            "syncPreferredFreq": None,
            "minPackageSize": "",
            "maxComponentHeight": None,
            "softStartTime": None,
            "useOnlyCeramicCaps": False,
            "useOnlyShieldedInductors": False,
        },
        "acFrequency": "60 Hz",
    }

    try:
        response = requests.post(
            _WEBENCH_URL,
            headers=_DEFAULT_HEADERS,
            json=payload,
            timeout=30,
        )
        response.raise_for_status()
    except requests.RequestException as e:
        logger.warning("WEBENCH API request failed: %s", e)
        return []

    try:
        data = response.json()
    except json.JSONDecodeError:
        logger.warning("WEBENCH returned invalid JSON")
        return []

    if not isinstance(data, list):
        return []

    solutions: list[WebenchSolution] = []
    for item in data[:max_results]:
        device = item.get("info", {}).get("device", {})
        solutions.append(WebenchSolution(
            solution_id=item.get("id", ""),
            rank=item.get("rank", 0),
            part_number=device.get("partNumber", ""),
            base_pn=device.get("basePn", ""),
            topology=device.get("topology", ""),
            price_usd=device.get("price", 0),
            vin_min=device.get("vinMin", 0),
            vin_max=device.get("vinMax", 0),
            vout_min=device.get("voutMin", 0),
            vout_max=device.get("voutMax", 0),
            considerations=item.get("considerations", ""),
        ))

    return solutions
