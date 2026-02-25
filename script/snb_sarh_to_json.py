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
    req = Request(url, headers={"User-Agent": "github-actions-xml-parser/1.0"})
    with urlopen(req, timeout=30) as resp:
        return resp.read()


def parse_date_to_yyyy_mm_dd(s: str) -> str:
    s = (s or "").strip()
    if not s:
        raise ValueError("Empty dc:date")
    # ISO fast path (most common)
    if len(s) >= 10 and s[4] == "-" and s[7] == "-":
        return s[:10]
    # Fallback: try fromisoformat
    s2 = s.replace("Z", "+00:00")
    d = dt.datetime.fromisoformat(s2)
    return d.date().isoformat()


def find_first_desc_text(parent: ET.Element, wanted_local: str):
    """First descendant text matching localname == wanted_local."""
    for el in parent.iter():
        if localname(el.tag) == wanted_local:
            txt = (el.text or "").strip()
            if txt:
                return txt
    return None


def find_items(root: ET.Element):
    for el in root.iter():
        if localname(el.tag) == "item":
            yield el


def find_observations(item: ET.Element):
    for el in item.iter():
        if localname(el.tag) == "observation":
            yield el


def main() -> int:
    try:
        xml_bytes = fetch_xml(XML_URL)
        root = ET.fromstring(xml_bytes)

        matched_item = None
        matched_obs = None

        # 1) Find the <item> that contains an <cb:observation> with <cb:rateName>SARH</cb:rateName>
        for item in find_items(root):
            for obs in find_observations(item):
                rn = find_first_desc_text(obs, "rateName")
                if rn == TARGET_RATE_NAME:
                    matched_item = item
                    matched_obs = obs
                    break
            if matched_item is not None:
                break

        if matched_item is None or matched_obs is None:
            raise RuntimeError(f"Could not find item/observation for rateName={TARGET_RATE_NAME}")

        # 2) Extract dc:date (as requested) — generally at item-level
        dc_date = find_first_desc_text(matched_item, "date")
        if not dc_date:
            raise RuntimeError("dc:date not found in matched item")
        date_iso = parse_date_to_yyyy_mm_dd(dc_date)

        # 3) Extract cb:value INSIDE the matched observation
        value_txt = find_first_desc_text(matched_obs, "value")
        if not value_txt:
            raise RuntimeError("cb:value not found in matched observation")

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