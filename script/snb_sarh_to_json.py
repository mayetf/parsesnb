#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import os
import sys
import datetime as dt
from urllib.request import urlopen, Request
import xml.etree.ElementTree as ET

XML_URL = "https://www.snb.ch/public/en/rss/interestRates"
TARGET_RATE_NAME = "SARH"
OUT_PATH = os.getenv("OUT_PATH", "public/result.json")


def localname(tag: str) -> str:
    """'{uri}name' -> 'name' (ignore namespaces)"""
    return tag.split("}", 1)[-1] if tag and "}" in tag else (tag or "")


def fetch_xml(url: str) -> bytes:
    req = Request(
        url,
        headers={
            "User-Agent": "github-actions-xml-parser/1.0",
            "Accept": "application/xml,text/xml,application/rss+xml,*/*",
        },
    )
    with urlopen(req, timeout=30) as resp:
        return resp.read()


def parse_date_to_yyyy_mm_dd(s: str) -> str:
    s = (s or "").strip()
    if not s:
        raise ValueError("Empty dc:date")

    # Most common: ISO, keep first 10 chars
    if len(s) >= 10 and s[4] == "-" and s[7] == "-":
        return s[:10]

    # Fallback ISO parser
    s2 = s.replace("Z", "+00:00")
    d = dt.datetime.fromisoformat(s2)
    return d.date().isoformat()


def find_first_desc_text(parent: ET.Element, wanted_local: str) -> str | None:
    """Return first descendant text where localname(tag) == wanted_local."""
    for el in parent.iter():
        if localname(el.tag) == wanted_local:
            txt = (el.text or "").strip()
            if txt:
                return txt
    return None


def find_item_by_rate_name(root: ET.Element, rate_name: str) -> ET.Element | None:
    """Find the <item> that contains <...:rateName>rate_name</...:rateName> anywhere inside."""
    for el in root.iter():
        if localname(el.tag) != "item":
            continue

        # look for any descendant with localname == 'rateName'
        for rn in el.iter():
            if localname(rn.tag) == "rateName" and (rn.text or "").strip() == rate_name:
                return el

    return None


def find_observation_value(item: ET.Element) -> str | None:
    """
    Find cb:value specifically inside cb:observation in the selected item.
    """
    # Find first <...:observation> inside item
    for obs in item.iter():
        if localname(obs.tag) == "observation":
            # Find <...:value> inside that observation
            for v in obs.iter():
                if localname(v.tag) == "value":
                    txt = (v.text or "").strip()
                    return txt if txt else None
    return None


def main() -> int:
    try:
        xml_bytes = fetch_xml(XML_URL)
        root = ET.fromstring(xml_bytes)

        item = find_item_by_rate_name(root, TARGET_RATE_NAME)
        if item is None:
            raise RuntimeError(f"Could not find <item> containing rateName={TARGET_RATE_NAME}")

        # date: prefer item-level dc:date, fallback to any date within item
        dc_date = find_first_desc_text(item, "date")
        if not dc_date:
            raise RuntimeError("dc:date not found in matched item")
        date_iso = parse_date_to_yyyy_mm_dd(dc_date)

        value_txt = find_observation_value(item)
        if not value_txt:
            raise RuntimeError("cb:observation/cb:value not found in matched item")

        value_num = float(value_txt.replace(",", "."))

        payload = {
            "generated_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
            "source": XML_URL,
            "rateName": TARGET_RATE_NAME,
            "date": date_iso,
            "value": value_num,
        }

        os.makedirs(os.path.dirname(OUT_PATH) or ".", exist_ok=True)
        with open(OUT_PATH, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)

        print(f"✅ Wrote {OUT_PATH}: date={payload['date']}, value={payload['value']}")
        return 0

    except Exception as e:
        print(f"❌ Error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())