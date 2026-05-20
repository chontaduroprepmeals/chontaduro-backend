#!/usr/bin/env python3
"""
delivery_allowed_api.py

FastAPI endpoints to check delivery/pickup availability and calculate shipping cost
using the current business rule:
- ZIP prefixes 980xx, 981xx, 982xx, 983xx, 984xx => delivery available
- all other ZIPs => pickup only
"""
import os
from fastapi import FastAPI, APIRouter, HTTPException
from pydantic import BaseModel, constr
from typing import Optional

router = APIRouter()

FREE_SHIPPING_THRESHOLD = float(os.environ.get("FREE_SHIPPING_THRESHOLD", "150.0"))
DELIVERY_FEE = float(os.environ.get("DELIVERY_FEE", "10.0"))
ALLOWED_PREFIXES = {"980", "981", "982", "983", "984"}

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

@router.post("/api/check-zip", response_model=ZipCheckResponse)
def check_zip(payload: ZipCheckRequest):
    zipcode = payload.zipcode.strip()
    subtotal = float(payload.subtotal or 0.0)

    if not zipcode or len(zipcode) < 3:
        raise HTTPException(status_code=400, detail="Zipcode inválido")

    prefix = zipcode[:3]
    if prefix in ALLOWED_PREFIXES:
        free_threshold = FREE_SHIPPING_THRESHOLD
        fee = 0.0 if subtotal >= free_threshold else DELIVERY_FEE
        return ZipCheckResponse(
            can_deliver=True,
            can_pickup=True,
            distance_miles=None,
            shipping_cost=fee,
            free_shipping_threshold=free_threshold,
            place_name=None,
            message=f"Delivery available for ZIPs starting with {prefix}. ${int(DELIVERY_FEE)} flat fee, free on orders ${int(free_threshold)}+."
        )

    return ZipCheckResponse(
        can_deliver=False,
        can_pickup=True,
        distance_miles=None,
        shipping_cost=0.0,
        free_shipping_threshold=None,
        message="Delivery is not available for this ZIP code. Pickup is still available on Sunday from 4PM to 7PM."
    )

def register_delivery_routes(app: FastAPI):
    app.include_router(router)