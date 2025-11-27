#!/usr/bin/env python3
"""
delivery_allowed_api.py

FastAPI endpoints to check delivery/pickup availability and calculate shipping cost
based on precalculated delivery_allowed_zips table (generated from GeoNames) or
fallback to allowed_zips.csv if the DB/table is not available.
"""
import os
import sqlite3
from fastapi import FastAPI, APIRouter, HTTPException
from pydantic import BaseModel, constr
from typing import Optional, Set
from pathlib import Path
import csv

router = APIRouter()

DB_PATH = os.environ.get("APP_DB_FILE", "app.db")
FREE_SHIPPING_THRESHOLD = float(os.environ.get("FREE_SHIPPING_THRESHOLD", "150.0"))
ALLOWED_ZIPS_CSV = Path("allowed_zips.csv")

class ZipCheckRequest(BaseModel):
    zipcode: constr(strip_whitespace=True)
    subtotal: Optional[float] = 0.0

class ZipCheckResponse(BaseModel):
    can_deliver: bool
    can_pickup: bool = True
    distance_miles: Optional[float] = None
    shipping_cost: Optional[float] = None
    currency: str = "USD"
    free_shipping_threshold: Optional[float] = None
    place_name: Optional[str] = None
    message: Optional[str] = None

def get_conn():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def shipping_fee_for_distance(dist_miles: float):
    # bandas: 0-10: $8, 10-20: $12, 20-30: $18, >30: no delivery
    if dist_miles <= 10:
        return 8.0
    if dist_miles <= 20:
        return 12.0
    if dist_miles <= 30:
        return 18.0
    return None

def load_allowed_zips_from_csv() -> Set[str]:
    seen = set()
    if not ALLOWED_ZIPS_CSV.exists():
        return seen
    try:
        with ALLOWED_ZIPS_CSV.open(newline='', encoding='utf-8') as f:
            rdr = csv.reader(f)
            for row in rdr:
                if not row:
                    continue
                z = str(row[0]).strip()
                if z:
                    seen.add(z)
    except Exception:
        # ignore errors here; return empty set
        pass
    return seen

# cache CSV allowed zips at import time (reload if you update file)
_ALLOWED_ZIPS_SET = load_allowed_zips_from_csv()

@router.post("/api/check-zip", response_model=ZipCheckResponse)
def check_zip(payload: ZipCheckRequest):
    zipcode = payload.zipcode.strip()
    subtotal = float(payload.subtotal or 0.0)

    if not zipcode or len(zipcode) < 3:
        raise HTTPException(status_code=400, detail="Zipcode inválido")

    # First try DB (if available). If any DB error or no row found, fallback to CSV set.
    try:
        if Path(DB_PATH).exists():
            conn = get_conn()
            try:
                cur = conn.cursor()
                cur.execute("SELECT zip, distance_miles, place_name FROM delivery_allowed_zips WHERE zip = ?", (zipcode,))
                row = cur.fetchone()
                if row:
                    dist = float(row["distance_miles"])
                    fee = shipping_fee_for_distance(dist)
                    if fee is None:
                        return ZipCheckResponse(
                            can_deliver=False,
                            can_pickup=True,
                            distance_miles=dist,
                            shipping_cost=0.0,
                            free_shipping_threshold=None,
                            place_name=row["place_name"],
                            message="Fuera del área de delivery (por distancia). Solo pickup disponible."
                        )
                    free_threshold = FREE_SHIPPING_THRESHOLD
                    if subtotal >= free_threshold:
                        fee = 0.0
                    return ZipCheckResponse(
                        can_deliver=True,
                        can_pickup=True,
                        distance_miles=round(dist, 2),
                        shipping_cost=fee,
                        free_shipping_threshold=free_threshold,
                        place_name=row["place_name"],
                        message="Delivery disponible"
                    )
                # if row not found, fall through to CSV fallback
            finally:
                conn.close()
    except sqlite3.Error:
        # DB problem -> fallback to CSV
        pass

    # CSV fallback: if allowed_zips.csv contains the code, allow delivery (no distance info)
    if zipcode in _ALLOWED_ZIPS_SET:
        free_threshold = FREE_SHIPPING_THRESHOLD
        fee = 0.0 if subtotal >= free_threshold else 8.0  # default fee if unknown distance
        return ZipCheckResponse(
            can_deliver=True,
            can_pickup=True,
            distance_miles=None,
            shipping_cost=fee,
            free_shipping_threshold=free_threshold,
            place_name=None,
            message="Delivery disponible (verificado por CSV)"
        )

    # Not found in DB nor CSV -> no delivery
    return ZipCheckResponse(
        can_deliver=False,
        can_pickup=True,
        distance_miles=None,
        shipping_cost=0.0,
        free_shipping_threshold=None,
        message="Fuera del área de delivery. Solo pickup disponible."
    )

def register_delivery_routes(app: FastAPI):
    app.include_router(router)