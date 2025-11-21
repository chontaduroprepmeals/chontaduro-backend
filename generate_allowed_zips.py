#!/usr/bin/env python3
"""
generate_allowed_zips.py

Descarga el archivo postal de GeoNames (US.zip), lo procesa y genera
allowed_zips.csv con los ZIP codes dentro de un radio (millas) desde
un punto origen.

Uso:
  python generate_allowed_zips.py --lat 47.5537222222 --lon -122.0972222222 --miles 30 --out allowed_zips.csv
"""
import argparse
import csv
import math
import os
import urllib.request
import zipfile
from pathlib import Path

GEO_URL_DEFAULT = "http://download.geonames.org/export/zip/US.zip"

def haversine_miles(lat1, lon1, lat2, lon2):
    R = 3958.8  # Earth radius in miles
    phi1 = math.radians(lat1); phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlambda/2)**2
    return 2 * R * math.asin(math.sqrt(a))

def download_and_extract(us_zip_url: str, tmp_dir: Path, quiet=False) -> Path:
    tmp_dir.mkdir(parents=True, exist_ok=True)
    zip_path = tmp_dir / "US.zip"
    if not zip_path.exists():
        if not quiet: print(f"Downloading {us_zip_url} -> {zip_path}")
        urllib.request.urlretrieve(us_zip_url, zip_path)
    else:
        if not quiet: print(f"Using cached {zip_path}")

    # inspect ZIP content and choose the US.txt specifically (if present)
    with zipfile.ZipFile(zip_path, 'r') as z:
        members = z.namelist()
        txt_names = [m for m in members if m.lower().endswith('.txt')]
        if not txt_names:
            raise SystemExit("No .txt found inside ZIP")
        # prefer an entry ending with US.txt (case-insensitive), otherwise pick the first txt
        txt_name = None
        for m in txt_names:
            if Path(m).name.lower() == "us.txt":
                txt_name = m
                break
        if not txt_name:
            # fallback: try to find something that contains '/US' or 'US.txt'
            for m in txt_names:
                if "us.txt" in m.lower():
                    txt_name = m
                    break
        if not txt_name:
            txt_name = txt_names[0]

        extracted = tmp_dir / Path(txt_name).name
        if not extracted.exists():
            if not quiet: print(f"Extracting {txt_name} -> {extracted}")
            z.extract(txt_name, path=tmp_dir)
            # move to root of tmp_dir if extraction kept folders
            possible = tmp_dir / txt_name
            if possible.exists() and possible != extracted:
                possible.rename(extracted)
        else:
            if not quiet: print(f"Using cached extracted {extracted}")
    if not quiet:
        print(f"Will process file: {extracted}")
    return extracted

def process_geonames_txt(txt_path: Path, out_csv: Path, origin_lat: float, origin_lon: float, miles: float, min_zip_len: int = 5, quiet=False):
    count_total = 0
    count_allowed = 0
    with txt_path.open(encoding="utf-8", errors="ignore") as f, out_csv.open("w", newline='', encoding="utf-8") as fo:
        writer = csv.writer(fo)
        writer.writerow(["zip","distance_miles","place_name","lat","lon"])
        for line in f:
            line = line.strip()
            if not line:
                continue
            parts = line.split('\t')
            if len(parts) < 11:
                # skip lines that do not have the expected columns
                continue
            country = parts[0]
            postal_code = parts[1]
            place_name = parts[2]
            try:
                lat = float(parts[9])
                lon = float(parts[10])
            except Exception:
                continue
            count_total += 1
            if country != "US":
                continue
            if not postal_code or len(postal_code) < min_zip_len:
                continue
            dist = haversine_miles(origin_lat, origin_lon, lat, lon)
            if dist <= miles:
                writer.writerow([postal_code, f"{dist:.2f}", place_name, f"{lat:.6f}", f"{lon:.6f}"])
                count_allowed += 1
    if not quiet:
        print(f"Processed {count_total} entries, found {count_allowed} ZIPs within {miles} miles")

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--lat", type=float, required=True, help="Latitude origin (decimal)")
    p.add_argument("--lon", type=float, required=True, help="Longitude origin (decimal)")
    p.add_argument("--miles", type=float, required=True, help="Radius in miles")
    p.add_argument("--out", default="allowed_zips.csv", help="Output CSV")
    p.add_argument("--zips-url", default=GEO_URL_DEFAULT, help="GeoNames US.zip URL")
    p.add_argument("--tmp", default="tmp_geonames", help="Temporary folder for download/extract")
    p.add_argument("--min-zip-len", type=int, default=5, help="Minimum length of postal code to consider")
    p.add_argument("--quiet", action="store_true", help="Quiet mode")
    args = p.parse_args()

    tmp_dir = Path(args.tmp)
    out_csv = Path(args.out)

    txt_path = download_and_extract(args.zips_url, tmp_dir, quiet=args.quiet)
    process_geonames_txt(txt_path, out_csv, args.lat, args.lon, args.miles, args.min_zip_len, quiet=args.quiet)
    if not args.quiet:
        print(f"Wrote {out_csv.resolve()}")
        print("\nLicense: GeoNames data is under Creative Commons Attribution 4.0. See http://www.geonames.org/\n")

if __name__ == "__main__":
    main()