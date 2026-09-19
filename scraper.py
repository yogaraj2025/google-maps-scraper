"""
Google Maps scraper — refactored from the original script into a callable function
suitable for use inside a Streamlit app.

The API key is read from the GOOGLE_MAPS_API_KEY environment variable (or
.streamlit/secrets.toml when running on Streamlit Cloud) — never hard-coded.
"""
from __future__ import annotations

import os
import time
from typing import Callable, Optional

import googlemaps
import pandas as pd

# A small but useful list of common Indian-city neighbourhoods. Used only when the
# user enters a city we recognise; otherwise we just search the city itself.
COMMON_AREAS = {
    "chennai": [
        "Anna Nagar", "Adyar", "Velachery", "Tambaram", "Porur", "Mylapore",
        "Nungambakkam", "Madipakkam", "Pallikaranai", "Perambur", "Ambattur",
        "Chromepet", "OMR", "Thiruvanmiyur", "Mogappair", "T Nagar",
        "KK Nagar", "Vadapalani", "Ashok Nagar", "Avadi",
    ],
    "bangalore": [
        "Indiranagar", "Koramangala", "Whitefield", "HSR Layout", "BTM Layout",
        "Jayanagar", "JP Nagar", "Marathahalli", "Electronic City",
        "Hebbal", "Yelahanka", "Malleshwaram", "Rajajinagar", "Banashankari",
    ],
    "mumbai": [
        "Andheri", "Bandra", "Borivali", "Dadar", "Goregaon", "Juhu",
        "Kandivali", "Malad", "Powai", "Thane", "Vile Parle", "Worli",
    ],
    "delhi": [
        "Connaught Place", "Saket", "Dwarka", "Rohini", "Lajpat Nagar",
        "Karol Bagh", "Pitampura", "Janakpuri", "Vasant Kunj", "Hauz Khas",
    ],
    "hyderabad": [
        "Banjara Hills", "Jubilee Hills", "Gachibowli", "Madhapur", "Kondapur",
        "Hitech City", "Kukatpally", "Begumpet", "Secunderabad", "Ameerpet",
    ],
    "pune": [
        "Kothrud", "Hinjewadi", "Baner", "Aundh", "Viman Nagar", "Wakad",
        "Hadapsar", "Camp", "Kalyani Nagar", "Magarpatta",
    ],
    "kolkata": [
        "Park Street", "Salt Lake", "New Town", "Howrah", "Ballygunge",
        "Gariahat", "Behala", "Tollygunge", "Dum Dum",
    ],
}

ProgressFn = Callable[[float, str], None]  # (fraction 0..1, message)


def get_api_key() -> str:
    """Read the API key from env or Streamlit secrets. Raise if missing."""
    key = os.getenv("GOOGLE_MAPS_API_KEY", "").strip()
    if not key:
        try:
            import streamlit as st  # type: ignore
            key = (st.secrets.get("GOOGLE_MAPS_API_KEY", "") or "").strip()
        except Exception:
            key = ""
    if not key:
        raise RuntimeError(
            "GOOGLE_MAPS_API_KEY is not configured. Add it in Streamlit Cloud "
            "Settings → Secrets, or in your local .env file."
        )
    return key


def build_queries(keyword: str, city: str, include_areas: bool = True):
    """Build a deduplicated list of search queries from a base keyword + city."""
    keyword = (keyword or "").strip()
    city = (city or "").strip()
    if not keyword or not city:
        return []

    queries = [f"{keyword} {city}"]
    if include_areas:
        for area in COMMON_AREAS.get(city.lower(), []):
            queries.append(f"{keyword} {area} {city}")
    seen, ordered = set(), []
    for q in queries:
        ql = q.lower()
        if ql not in seen:
            seen.add(ql)
            ordered.append(q)
    return ordered


def _all_places(gmaps, query):
    results = []
    try:
        response = gmaps.places(query)
        while response:
            results.extend(response.get("results", []))
            token = response.get("next_page_token")
            if not token:
                break
            time.sleep(2)  # token needs a moment to become valid
            response = gmaps.places(query, page_token=token)
    except Exception as e:
        print(f"  ⚠️  Error fetching query '{query}': {e}")
    return results


def _details(gmaps, place_id):
    try:
        return gmaps.place(place_id, fields=[
            "name", "formatted_phone_number", "international_phone_number",
            "formatted_address", "rating", "user_ratings_total",
            "website", "url", "opening_hours", "business_status",
        ])["result"]
    except Exception as e:
        print(f"  ⚠️  Error fetching details: {e}")
        return {}


def scrape(keyword, city, include_areas=True, progress=None, api_key=None):
    """
    Run the full two-phase scrape and return a sorted DataFrame.
    `progress(fraction, message)` is called as work proceeds.
    """
    queries = build_queries(keyword, city, include_areas=include_areas)
    if not queries:
        return pd.DataFrame()

    gmaps = googlemaps.Client(key=api_key or get_api_key())

    all_place_ids = {}
    for i, q in enumerate(queries):
        if progress:
            progress(0.5 * (i / len(queries)),
                     f"Searching ({i+1}/{len(queries)}): {q}")
        for place in _all_places(gmaps, q):
            pid = place.get("place_id")
            if pid and pid not in all_place_ids:
                all_place_ids[pid] = place.get("name", "")
        time.sleep(1)
    if progress:
        progress(0.5, f"Found {len(all_place_ids)} unique places. Fetching details…")

    rows = []
    pid_list = list(all_place_ids.keys())
    for i, pid in enumerate(pid_list):
        d = _details(gmaps, pid)
        if d.get("business_status") == "CLOSED_PERMANENTLY":
            if progress:
                progress(0.5 + 0.5 * (i / max(1, len(pid_list))),
                         f"Skipped closed: {d.get('name','')}")
            continue
        rows.append({
            "S.No": len(rows) + 1,
            "Name": d.get("name", ""),
            "Phone": d.get("formatted_phone_number", ""),
            "International Phone": d.get("international_phone_number", ""),
            "Address": d.get("formatted_address", ""),
            "Rating": d.get("rating", ""),
            "Total Reviews": d.get("user_ratings_total", ""),
            "Website": d.get("website", ""),
            "Business Status": d.get("business_status", ""),
            "Google Maps URL": d.get("url", ""),
        })
        if progress and (i % 5 == 0 or i == len(pid_list) - 1):
            progress(0.5 + 0.5 * ((i + 1) / max(1, len(pid_list))),
                     f"Fetched {i+1}/{len(pid_list)}: {d.get('name','')}")
        time.sleep(0.3)

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)
    df["Rating"] = pd.to_numeric(df["Rating"], errors="coerce")
    df = df.sort_values(by="Rating", ascending=False, na_position="last").reset_index(drop=True)
    df["S.No"] = df.index + 1
    if progress:
        progress(1.0, f"Done — {len(df)} places.")
    return df


def to_excel_bytes(df):
    """Return a 3-sheet Excel workbook (with-phone, no-phone, all) as bytes."""
    import io
    with_phone = df[df["Phone"].astype(str).str.strip() != ""]
    no_phone = df[df["Phone"].astype(str).str.strip() == ""]
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        with_phone.to_excel(writer, sheet_name="With Phone Numbers", index=False)
        no_phone.to_excel(writer, sheet_name="No Phone Number", index=False)
        df.to_excel(writer, sheet_name="All Results", index=False)
    return buf.getvalue()


def mask_for_free(df, sample_size=10):
    """
    Return a copy of `df` where the first `sample_size` rows are visible and the
    rest have their sensitive columns masked. Free-tier export.
    """
    if df.empty:
        return df.copy()
    masked = df.copy()
    sensitive_cols = [
        "Name", "Phone", "International Phone", "Address",
        "Website", "Google Maps URL",
    ]
    cols_to_mask = [c for c in sensitive_cols if c in masked.columns]
    if len(masked) <= sample_size:
        return masked
    masked.loc[sample_size:, cols_to_mask] = "🔒 Upgrade to Premium to unlock"
    return masked
