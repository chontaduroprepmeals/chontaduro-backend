import os
os.makedirs("uploads", exist_ok=True)

# main.py
from fastapi import FastAPI, HTTPException, Request, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
from pydantic import BaseModel, Field, EmailStr
from upload_image import register_upload_routes
from fastapi.staticfiles import StaticFiles
import random, json, traceback, datetime, math, hashlib
from typing import List, Dict, Any, Optional
from uuid import uuid4
from delivery_allowed_api import register_delivery_routes
from ingredients_database import INGREDIENT_DATABASE, find_ingredient
from fastapi.responses import JSONResponse
import stripe
import bcrypt
from dotenv import load_dotenv
from email.message import EmailMessage
import smtplib

# SQLAlchemy imports (updated for modern syntax)
from sqlalchemy import create_engine, Column, Integer, String, DateTime
from sqlalchemy.orm import DeclarativeBase, sessionmaker

# Cargar variables de entorno
load_dotenv()

# Configurar la clave de Stripe
stripe.api_key = os.getenv("STRIPE_SECRET_KEY")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET")

# --- Payments / Tax config ---
WA_TAX_RATE = 0.1025
ZELLE_PAYEE_NAME = os.getenv("ZELLE_PAYEE_NAME", "Chontaduro Kitchen")
ZELLE_PAYEE_EMAIL = os.getenv("ZELLE_PAYEE_EMAIL", "")
ZELLE_PAYEE_PHONE = os.getenv("ZELLE_PAYEE_PHONE", "")

# --- Email config ---
SMTP_HOST = os.getenv("SMTP_HOST", "")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USERNAME = os.getenv("SMTP_USERNAME", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
SMTP_FROM_EMAIL = os.getenv("SMTP_FROM_EMAIL", SMTP_USERNAME or "")

# In-memory pending order cache (for Stripe webhook correlation)
PENDING_ORDERS: Dict[str, Dict[str, Any]] = {}

# --- SQLite Database Configuration ---
SQLITE_DATABASE_URL = "sqlite:///./app.db"

# Define Base class for ORM models (PUT THIS HERE)
class Base(DeclarativeBase):
    pass

# Create database engine
engine = create_engine(SQLITE_DATABASE_URL, connect_args={"check_same_thread": False})

# Create session maker
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# --- Database Models (User table) ---
class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    creation_date = Column(DateTime, default=lambda: datetime.datetime.now(datetime.timezone.utc))

    @staticmethod
    def hash_password(password: str) -> str:
        if not password:
            raise ValueError("Password must not be empty")
        return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

    @staticmethod
    def verify_password(password: str, hashed_password: str) -> bool:
        if not password or not hashed_password:
            return False
        try:
            return bcrypt.checkpw(password.encode("utf-8"), hashed_password.encode("utf-8"))
        except ValueError:
            return False

# Initialize database tables AFTER models are defined
def init_db():
    Base.metadata.create_all(bind=engine)

init_db()

app = FastAPI()

# --- CORS ---
DEFAULT_ALLOWED_ORIGINS = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "https://chontaduro-backend.onrender.com",
]

CORS_ALLOWED_ORIGINS = [
    origin.strip()
    for origin in os.getenv("CORS_ALLOWED_ORIGINS", ",".join(DEFAULT_ALLOWED_ORIGINS)).split(",")
    if origin.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Registrar rutas de subida (llama a la función que trae upload_image.py)
register_upload_routes(app)
# montar carpeta ./uploads para servir archivos locales (fallback)
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")
register_delivery_routes(app)

@app.get("/healthz")
def healthz():
    return {"status": "ok"}

@app.get("/version")
def version():
    """Return current app version to verify deployment"""
    return {
        "version": "v2.1-checkout-enabled",
        "deploy_date": "2026-02-06T05:25:00Z",
        "features": {
            "checkout_button": True,
            "checkout_modal": True,
            "database_persistence": True
        },
        "status": "deployed"
    }

# Serve frontend
@app.get("/", response_class=HTMLResponse)
async def serve_frontend():
    return FileResponse("index.html")

# --- LOAD MEALS (expects English keys; tolerant with Spanish keys) ---
MEALS_DATA: List[Dict[str, Any]] = []
TEMPLATES_DATA: List[Dict[str, Any]] = []
FEEDBACKS: List[Dict[str, Any]] = []  # in-memory feedback store for now

def normalize_meal_keys(raw: Dict[str, Any]) -> Dict[str, Any]:
    spanish_map = {
        "nombre": "name", "tipo": "type", "ingredientes": "ingredients",
        "calorias": "calories", "precio": "price", "imagen": "image_url", "image": "image_url"
    }
    out = {}
    for k, v in raw.items():
        key = spanish_map.get(k.lower(), k)
        out[key] = v
    # Normalize ingredients
    if "ingredients" in out and isinstance(out["ingredients"], str):
        out["ingredients"] = [i.strip().lower() for i in out["ingredients"].split(",") if i.strip()]
    if "ingredients" in out and isinstance(out["ingredients"], list):
        out["ingredients"] = [str(i).strip().lower() for i in out["ingredients"] if i]
    # Normalize tags
    if "tags" in out and isinstance(out["tags"], str):
        out["tags"] = [t.strip().lower() for t in out["tags"].split(",") if t.strip()]
    if "tags" in out and isinstance(out["tags"], list):
        out["tags"] = [str(t).strip().lower() for t in out["tags"] if t]
    return out

def load_meals(file_path="meals.json"):
    global MEALS_DATA
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, list):
                MEALS_DATA = [normalize_meal_keys(item.copy()) for item in data]
            else:
                print("WARNING: meals.json not a list.")
    except FileNotFoundError:
        print("WARNING: meals.json not found.")
    except json.JSONDecodeError:
        print("WARNING: meals.json invalid JSON.")

def load_templates(file_path="menus_weekly.json"):
    global TEMPLATES_DATA
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, list):
                TEMPLATES_DATA = data
            else:
                print("WARNING: menus_weekly.json not a list.")
    except FileNotFoundError:
        print("NOTICE: menus_weekly.json not found (templates disabled).")
    except json.JSONDecodeError:
        print("WARNING: menus_weekly.json invalid JSON.")

load_meals()
load_templates()


# --- SESSIONS (in-memory) ---
sessions: Dict[str, Dict[str, Any]] = {}

# --- LOGIN SECURITY (in-memory lockout) ---
MAX_FAILED_LOGIN_ATTEMPTS = int(os.getenv("MAX_FAILED_LOGIN_ATTEMPTS", "5"))
LOGIN_LOCKOUT_MINUTES = int(os.getenv("LOGIN_LOCKOUT_MINUTES", "15"))
LOGIN_ATTEMPTS: Dict[str, Dict[str, Any]] = {}

# --- FLOW STEPS ---
STEPS = {
    "start": "diet_preference",
    "diet_preference": "pick_plan",
    "pick_plan": "objective",
    "objective": "allergies_and_restrictions",
    "allergies_and_restrictions": "personal_info",
    "personal_info": "duration",
    "duration": "review",
    "review": "review"
}


# --- MODELS ---
class Meal(BaseModel):
    name: str
    type: str
    ingredients: List[str] = Field(default_factory=list)
    calories: int = 0
    price: float = 0.0
    protein: Optional[int] = None  # Agregar el campo
    fat: Optional[int] = None  # Agrega "grasas" si es usado
    carbs: Optional[int] = None  # Agrega "carbohidratos" si es usado
    image_url: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    model_config = {"extra": "ignore"}


class SessionState(BaseModel):
    plan: Optional[int] = None
    days: Optional[int] = None
    dislikes: List[str] = Field(default_factory=list)
    allergies: List[str] = Field(default_factory=list)
    dietary_restrictions: List[str] = Field(default_factory=list)
    allergies_and_restrictions: Optional[str] = None  # New unified field for allergies/dislikes
    allergy_note: Optional[str] = None
    extra_protein_grams: int = 0  # global extra grams to distribute
    extra_protein_map: Dict[int, int] = Field(default_factory=dict)  # per-meal extras
    menu: List[Any] = Field(default_factory=list)
    current_step: str = "start"
    history: List[Dict[str, Any]] = Field(default_factory=list)
    # personal info
    objective: Optional[str] = None
    diet_preference: Optional[str] = None
    weight_unit: Optional[str] = "kg"
    weight: Optional[float] = None
    height_unit: Optional[str] = "cm"
    height: Optional[float] = None
    age: Optional[int] = None
    sex: Optional[str] = None
    activity_days_bucket: Optional[str] = None
    activity_duration_bucket: Optional[str] = None
    activity_intensity: Optional[str] = None
    body_fat: Optional[float] = None
    user_note: Optional[str] = None

    # new fields for templates / scheduling
    template_id: Optional[str] = None
    selected_week: Optional[str] = None   # e.g. "2025-W45" (ISO week of delivery)
    order_placed_at: Optional[str] = None  # ISO timestamp when user confirmed order
    model_config = {"extra": "ignore"}


class NextStepRequest(BaseModel):
    session_id: str
    step: str
    answer: Dict[str, Any] = Field(default_factory=dict)
    model_config = {"extra": "allow"}

# Modelo para definir un ítem del pedido
class OrderItem(BaseModel):
    item_type: str  # "main_menu" o "breakfast"
    quantity: int
    less_protein: bool = False  # Opcional, indica si el menú tiene menos proteína

class Order(BaseModel):
    items: list[OrderItem]


class CheckoutSessionRequest(BaseModel):
    order: Optional[Order] = None
    email: EmailStr
    name: Optional[str] = None
    password: Optional[str] = Field(default=None, min_length=8, max_length=128)
    session_id: Optional[str] = None
    allergies_selected: List[str] = Field(default_factory=list)
    allergies_other_note: Optional[str] = None


class RegisterRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class RegisterOrAuthRequest(BaseModel):
    full_name: str = Field(min_length=1, max_length=100)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class OrderSummaryRequest(BaseModel):
    session_id: str


class ZelleConfirmRequest(BaseModel):
    session_id: str
    full_name: str = Field(min_length=1, max_length=100)
    email: EmailStr
    payment_proof_url: str = Field(min_length=1, max_length=1000)

# --- HELPERS: normalization for incoming requests (tolerant) ---
def normalize_step_name(step: str) -> str:
    if not step:
        return "start"
    s = str(step).strip().lower()
    if s in ("back", "volver", "regresar"):
        return "back"
    spanish_equiv = {
        "inicio": "start", "pick_plan": "pick_plan", "elegirplan": "pick_plan",
        "objetivo": "objective", "personal_info": "personal_info", "informacionpersonal": "personal_info",
        "duracion": "duration", "dias": "duration", "días": "duration",
        "dislikes": "dislikes", "ingredientesnodedeseados": "dislikes",
        "alergias": "restrictions", "restricciones": "restrictions", "review": "review"
    }
    if s in STEPS:
        return s
    if s in spanish_equiv:
        return spanish_equiv[s]
    return "start"

def normalize_key(k: str) -> str:
    return ''.join(ch for ch in (k or "").lower() if ch.isalnum())

def map_answer_keys(answer: Dict[str, Any]) -> Dict[str, Any]:
    mapping = {
        "plan": "plan",
        "days": "days", "días": "days", "dias": "days",
        "weight": "weight", "peso": "weight",
        "weightunit": "weight_unit", "weight_unit": "weight_unit",
        "height": "height", "altura": "height",
        "heightunit": "height_unit", "height_unit": "height_unit",
        "age": "age", "edad": "age",
        "sex": "sex", "gender": "sex",
        "objective": "objective", "goal": "objective",
        "daysperweek": "activity_days_bucket",
        "avgsessionduration": "activity_duration_bucket", "avg_session_duration": "activity_duration_bucket",
        "intensity": "activity_intensity",
        "diet": "diet_preference", "dietpreference": "diet_preference", "diet_preference": "diet_preference",
        "dietaryrestrictions": "dietary_restrictions", "dietary_restrictions": "dietary_restrictions",
        "allergies": "allergies", "alergias": "allergies",
        "selectedallergies": "selected_allergies", "allergyselection": "selected_allergies",
        "anyotherallergyornote": "allergy_note", "allergy_note": "allergy_note",
        "dislikes": "dislikes", "ingredientesnodedeseados": "dislikes",
        "extra_protein_grams": "extra_protein_grams", "extraprotein": "extra_protein_grams",
        "note": "user_note", "usernote": "user_note",
        "template_id": "template_id"
    }
    out = {}
    for key, val in (answer or {}).items():
        kn = normalize_key(str(key))
        canonical = mapping.get(kn, None)
        if canonical:
            out[canonical] = val
        else:
            out[kn] = val
    return out


# --- NUTRITION helpers (unchanged) ---
def to_kg(weight: float, unit: str) -> Optional[float]:
    if weight is None:
        return None
    if unit and str(unit).lower() in ["lbs", "lb"]:
        return round(float(weight) * 0.45359237, 2)
    return float(weight)

def to_cm(height: float, unit: str) -> Optional[float]:
    if height is None:
        return None
    if unit and str(unit).lower() in ["in", "inch", "inches"]:
        return round(float(height) * 2.54, 1)
    return float(height)

def normalize_days_bucket(days_val) -> str:
    """Convert a raw days value (numeric string or bucket string) to a standard bucket string.
    
    Handles both numeric inputs from the HTML frontend (e.g. "5") and
    already-bucketed strings from the API form (e.g. "5-7").
    
    Mapping: 0 → "0", 1-2 → "1-2", 3-4 → "3-4", 5-7 → "5-7"
    Days per week range is 0–7; values above 4 all map to the highest bucket.
    """
    if days_val is None:
        return "0"
    s = str(days_val).strip()
    # Already a bucket string — pass through
    if s in ("0", "1-2", "3-4", "5-7"):
        return s
    # Numeric string — map to bucket (valid range is 0–7 days/week)
    try:
        n = int(s)
        if n <= 0:
            return "0"
        elif n <= 2:
            return "1-2"
        elif n <= 4:
            return "3-4"
        else:  # 5, 6, or 7 days/week
            return "5-7"
    except (ValueError, TypeError):
        return "0"


def compute_activity_factor(days_bucket: str, duration_bucket: str, intensity: str) -> float:
    # Updated base values to match scientific PAL standards and expert recommendations
    # For 5x/week training, should result in factor ~1.50-1.55
    days_map = {"0":1.2, "1-2":1.375, "3-4":1.50, "5-7":1.55}
    base = days_map.get(normalize_days_bucket(days_bucket), 1.2)
    # Simplified duration/intensity adjustments
    dur_map = {"<30":0.0, "30-60":0.0, "60-120":0.05}
    dur = dur_map.get(str(duration_bucket), 0.0)
    int_map = {"low":0.0, "moderate":0.0, "high":0.05}
    iadj = int_map.get((intensity or "").lower(), 0.0)
    return round(min(base + dur + iadj, 1.9), 3)

def get_activity_factor_with_recomp_minimum(days_bucket: str, duration_bucket: str, intensity: str, objective: str) -> float:
    """
    Calculate activity factor with minimum enforcement for body recomposition.
    
    Expert recommendation: For body recomposition, use minimum AF 1.50-1.55
    because you cannot build muscle and lose fat simultaneously on sedentary calories.
    
    Also enforces universal minimums based on training frequency:
    - Training 3+ days/week cannot result in sedentary factor (1.20)
    - Ensures active people get appropriate calorie estimates
    """
    base_factor = compute_activity_factor(days_bucket, duration_bucket, intensity)
    obj = (objective or "").lower()
    normalized_bucket = normalize_days_bucket(days_bucket)
    
    # UNIVERSAL MINIMUM based on training frequency
    # If training 3+ days/week, CANNOT be sedentary regardless of goal
    if normalized_bucket in ["3-4", "5-7"]:
        min_factor = 1.45  # Moderately active minimum
        if base_factor < min_factor:
            print(f"[ACTIVITY] Training {normalized_bucket} days/week but factor {base_factor:.2f} too low. Enforcing minimum {min_factor}.")
            base_factor = max(base_factor, min_factor)
    
    # EXTRA MINIMUM for body recomposition
    # Recomp needs even more calories to build muscle
    if "recomp" in obj or "body recomp" in obj or ("lose fat" in obj and "gain muscle" in obj):
        min_recomp = 1.50
        if base_factor < min_recomp:
            print(f"[RECOMP] Body recomposition requires minimum {min_recomp} factor. Enforcing.")
            base_factor = max(base_factor, min_recomp)
    
    return base_factor

def calc_tmb_mifflin(weight_kg: float, height_cm: float, age: int, sex: str, objective: str = "") -> Optional[float]:
    """
    Calculate BMR using Mifflin-St Jeor equation.
    Includes validation to prevent unrealistic values for body recomposition.
    """
    if None in (weight_kg, height_cm, age, sex):
        return None
    
    # Validation: For body recomposition with very high age, use realistic age
    # Body recomp is typically done by younger, active individuals
    obj = (objective or "").lower()
    if ("recomp" in obj or "body recomp" in obj) and age > 55:
        print(f"[VALIDATION] Age {age} too high for aggressive body recomposition. Using age 30 for calculations.")
        age = 30
    
    sex = (sex or "").lower()
    if sex in ["male", "m", "man"]:
        bmr = round((10*weight_kg)+(6.25*height_cm)-(5*age)+5, 1)
    else:
        bmr = round((10*weight_kg)+(6.25*height_cm)-(5*age)-161, 1)
    
    # Validation: Warn if BMR is suspiciously low
    if bmr < 1200 and sex not in ["male", "m", "man"]:
        print(f"[WARNING] BMR {bmr} kcal is unusually low for a woman. Check age and weight values.")
    elif bmr < 1400 and sex in ["male", "m", "man"]:
        print(f"[WARNING] BMR {bmr} kcal is unusually low for a man. Check age and weight values.")
    
    return bmr

def calc_calorie_target(tdee: float, objective: str, sex: str = "female") -> Optional[float]:
    """
    Calculate calorie target based on objective.
    Includes minimum calorie enforcement for body recomposition.
    """
    if tdee is None:
        return None
    obj = (objective or "").lower()
    
    if "lose fat" in obj and "gain muscle" not in obj:
        # Reduce por un 20% del TDEE (pérdida de grasa más sostenible)
        target = round(tdee * 0.80)
    elif "gain muscle" in obj and "lose fat" not in obj:
        # Incrementa un 15% para ganancia muscular
        target = round(tdee * 1.15)
    elif "recomp" in obj or "body recomp" in obj or ("lose fat" in obj and "gain muscle" in obj):
        # Body recomposition: 12% deficit (expert recommended 10-12%)
        # Scientific basis: Moderate deficit allows muscle building while losing fat
        # Expert feedback: For active individuals (5x/week), 12% deficit is optimal
        target = round(tdee * 0.88)
        
        # Validation: Enforce minimum calories for body recomposition
        # You cannot build muscle on too few calories
        min_calories = 1500 if sex.lower() in ["female", "f", "mujer", "femenino"] else 1800
        if target < min_calories:
            print(f"[VALIDATION] Recomp target {target} kcal too low. Enforcing minimum {min_calories} kcal.")
            target = min_calories
    elif "maintain" in obj:
        # Maintain weight
        target = round(tdee)
    else:
        # Default: mantener el peso
        target = round(tdee)
    
    return target

def calc_macros(calories: int, objective: str, weight_kg: Optional[float], sex: str = "female") -> Dict[str, Any]:
    """
    Calculate macros based on g/kg for protein (not percentage).
    User feedback: protein should be based on weight, not calories percentage.
    """
    if calories is None or calories == 0:
        return {}
    
    obj = (objective or "").lower()
    
    # Protein g/kg based on objective
    if "lose fat" in obj and "gain muscle" not in obj:
        prot_per_kg = 2.0
    elif "gain muscle" in obj and "lose fat" not in obj:
        prot_per_kg = 1.8
    elif "recomp" in obj or "body recomp" in obj or ("lose fat" in obj and "gain muscle" in obj):
        prot_per_kg = 2.1  # Expert recommended ~2.1 g/kg for recomp
    else:
        prot_per_kg = 1.6

    # Calculate protein based on weight
    if weight_kg and weight_kg > 0:
        protein_grams = round(prot_per_kg * weight_kg)
        # Cap protein: max 2.2 g/kg or 160g (women) / 200g (men)
        max_protein_kg = round(2.2 * weight_kg)
        max_protein_absolute = 160 if sex == "female" else 200
        max_protein = min(max_protein_kg, max_protein_absolute)
        protein_grams = min(protein_grams, max_protein)
    else:
        # Fallback if no weight (shouldn't happen with new fix)
        protein_grams = round((calories * 0.30) / 4)

    # Fat: 25-30% of calories, minimum 0.8 g/kg for women, 0.6 for men
    fat_pct = 0.27  # 27% average
    fat_calories = round(calories * fat_pct)
    fat_grams = round(fat_calories / 9)
    
    # Ensure minimum fat for hormonal health
    if weight_kg and weight_kg > 0:
        # Expert recommended ~0.85 g/kg for women, 0.7 for men
        min_fat = round(0.85 * weight_kg) if sex == "female" else round(0.7 * weight_kg)
        fat_grams = max(fat_grams, min_fat)

    # Carbs: remainder of calories
    protein_cal = protein_grams * 4
    fat_cal = fat_grams * 9
    remaining_cal = calories - (protein_cal + fat_cal)
    carbs_grams = round(max(0, remaining_cal) / 4) if remaining_cal > 0 else 0

    return {
        "calories": int(calories), 
        "protein_grams": int(protein_grams), 
        "fat_grams": int(fat_grams), 
        "carbs_grams": int(carbs_grams)
    }


# --- SNACK DATABASE FOR MACRO COMPLETION ---
SNACK_DATABASE = [
    {
        "name": "Protein Shake + Banana + Almendras",
        "description": "1 scoop whey protein + 1 banana mediana + 15 almendras",
        "protein_g": 28,
        "carbs_g": 30,
        "fat_g": 9,
        "calories": 325,
        "category": "shake"
    },
    {
        "name": "Pechuga de Pollo + Camote",
        "description": "100g pechuga de pollo + 100g camote + 1 cdta aceite oliva",
        "protein_g": 31,
        "carbs_g": 20,
        "fat_g": 5,
        "calories": 253,
        "category": "whole_food"
    },
    {
        "name": "Greek Yogurt + Granola + Mantequilla de Maní",
        "description": "170g Greek yogurt 0% + 30g granola + 1 cda PB",
        "protein_g": 21,
        "carbs_g": 22,
        "fat_g": 11,
        "calories": 267,
        "category": "yogurt"
    },
    {
        "name": "Atún + Arroz + Aguacate",
        "description": "1 lata atún en agua + 60g arroz cocido + 1/4 aguacate",
        "protein_g": 25,
        "carbs_g": 25,
        "fat_g": 8,
        "calories": 272,
        "category": "whole_food"
    },
    {
        "name": "Huevos Revueltos + Pan Integral + Aguacate",
        "description": "2 huevos + 2 rebanadas pan integral + 1/4 aguacate",
        "protein_g": 18,
        "carbs_g": 28,
        "fat_g": 14,
        "calories": 310,
        "category": "eggs"
    },
    {
        "name": "Cottage Cheese + Frutas + Nueces",
        "description": "150g cottage cheese + 80g fresas + 15g nueces",
        "protein_g": 20,
        "carbs_g": 15,
        "fat_g": 12,
        "calories": 252,
        "category": "dairy"
    },
    {
        "name": "Protein Bar de Alta Calidad",
        "description": "1 protein bar (Quest/RX Bar)",
        "protein_g": 20,
        "carbs_g": 24,
        "fat_g": 8,
        "calories": 248,
        "category": "bar"
    },
    {
        "name": "Batido de Proteína Vegana + Avena",
        "description": "1 scoop proteína vegana + 40g avena + 1 cda mantequilla de almendra",
        "protein_g": 26,
        "carbs_g": 35,
        "fat_g": 10,
        "calories": 342,
        "category": "shake"
    },
    {
        "name": "Pavo + Pan Pita + Hummus",
        "description": "100g pavo + 1 pan pita integral + 3 cdas hummus",
        "protein_g": 27,
        "carbs_g": 30,
        "fat_g": 8,
        "calories": 304,
        "category": "whole_food"
    },
    {
        "name": "Salmón Ahumado + Galletas Integrales + Queso Crema Light",
        "description": "60g salmón ahumado + 6 galletas integrales + 2 cdas queso crema light",
        "protein_g": 15,
        "carbs_g": 18,
        "fat_g": 9,
        "calories": 213,
        "category": "fish"
    },
    {
        "name": "Turkey Jerky + Manzana",
        "description": "30g turkey jerky + 1 manzana mediana",
        "protein_g": 13,
        "carbs_g": 25,
        "fat_g": 2,
        "calories": 168,
        "category": "whole_food"
    },
    {
        "name": "Almendras + Queso Mozzarella",
        "description": "20g almendras + 30g mozzarella",
        "protein_g": 10,
        "carbs_g": 4,
        "fat_g": 16,
        "calories": 200,
        "category": "dairy"
    },
    {
        "name": "Banana + Mantequilla de Maní",
        "description": "1 banana mediana + 2 cdas mantequilla de maní",
        "protein_g": 7,
        "carbs_g": 35,
        "fat_g": 16,
        "calories": 308,
        "category": "whole_food"
    },
    {
        "name": "Rice Cakes + Hummus + Pepino",
        "description": "3 rice cakes + 4 cdas hummus + 1/2 pepino",
        "protein_g": 6,
        "carbs_g": 30,
        "fat_g": 6,
        "calories": 198,
        "category": "whole_food"
    },
    {
        "name": "Avocado Toast + Huevo",
        "description": "1 rebanada pan integral + 1/4 aguacate + 1 huevo hervido",
        "protein_g": 10,
        "carbs_g": 18,
        "fat_g": 12,
        "calories": 218,
        "category": "eggs"
    },
    {
        "name": "Yogurt Griego + Miel + Nueces",
        "description": "170g Greek yogurt 0% + 1 cdta miel + 10g nueces",
        "protein_g": 17,
        "carbs_g": 14,
        "fat_g": 6,
        "calories": 178,
        "category": "yogurt"
    },
    {
        "name": "Proteína en Polvo + Leche de Almendra",
        "description": "1 scoop whey protein + 240ml leche de almendra sin azúcar",
        "protein_g": 26,
        "carbs_g": 5,
        "fat_g": 3,
        "calories": 151,
        "category": "shake"
    },
    {
        "name": "Tostadas con Queso Cottage + Tomate",
        "description": "2 tostadas integrales + 100g cottage cheese + 1 tomate",
        "protein_g": 14,
        "carbs_g": 22,
        "fat_g": 4,
        "calories": 180,
        "category": "dairy"
    },
    {
        "name": "Mix de Frutos Secos + Chocolate Oscuro",
        "description": "25g mix de nueces/almendras/marañón + 20g chocolate 70%",
        "protein_g": 6,
        "carbs_g": 18,
        "fat_g": 20,
        "calories": 270,
        "category": "whole_food"
    },
    {
        "name": "Huevos Duros + Frutas del Bosque",
        "description": "2 huevos duros + 80g arándanos/fresas",
        "protein_g": 13,
        "carbs_g": 12,
        "fat_g": 10,
        "calories": 190,
        "category": "eggs"
    },
]


def get_plan_display_config(plan: int) -> Dict[str, bool]:
    """
    Return a dict of boolean flags controlling what nutritional detail
    is visible to the client based on their subscription plan.

    Plan 4 (premium): full macro detail, ingredient list (names only — amounts/gramajes
    are never exposed to the client in any plan), daily summary, snack in summary.
    Plans 1-3 (basic): only dish name and portion slogan — no ingredients, no macros,
    no daily summary, no snack suggestions anywhere.
    Unknown plans default to the most restrictive (basic) view.

    Args:
        plan: The user's plan number (1-4).

    Returns:
        Dict with display flags:
          - show_macros: show per-meal macro table (protein/carbs/fat/calories)
          - show_ingredients: show ingredient name list (amounts are never shown)
          - show_daily_summary: show end-of-day macro totals panel (includes snack suggestion)
          - show_nutrition_totals: show the "Daily Nutrition Plan" header panel
          - show_snack_recommendations: show snack suggestions section (only in daily summary)
    """
    is_plan4 = plan == 4
    return {
        "show_macros": is_plan4,
        "show_ingredients": is_plan4,      # ingredient names only for Plan 4; amounts are never shown
        "show_daily_summary": is_plan4,
        "show_nutrition_totals": is_plan4,
        "show_snack_recommendations": is_plan4,
    }


def calculate_macro_deficit(target_macros: Dict[str, int], achieved_macros: Dict[str, int]) -> Dict[str, int]:
    """
    Calculate the difference between target macros and what was achieved in the meal plan.
    
    Args:
        target_macros: Dict with 'protein_grams', 'carbs_grams', 'fat_grams', 'calories'
        achieved_macros: Dict with same keys
        
    Returns:
        Dict with deficit for each macro (positive means still needed, negative means exceeded)
    """
    deficit = {
        "protein": max(0, target_macros.get("protein_grams", 0) - achieved_macros.get("protein_grams", 0)),
        "carbs": max(0, target_macros.get("carbs_grams", 0) - achieved_macros.get("carbs_grams", 0)),
        "fat": max(0, target_macros.get("fat_grams", 0) - achieved_macros.get("fat_grams", 0)),
        "calories": max(0, target_macros.get("calories", 0) - achieved_macros.get("calories", 0))
    }
    return deficit


def recommend_snacks(deficit: Dict[str, int], num_recommendations: int = 3) -> List[Dict[str, Any]]:
    """
    Recommend snacks that best fill the macro deficit.
    
    Args:
        deficit: Dict with 'protein', 'carbs', 'fat', 'calories' deficits
        num_recommendations: Number of snack recommendations to return
        
    Returns:
        List of snack dicts sorted by how well they fill the deficit,
        each with 'reason' explanation and 'coverage' percentages.
    """
    if all(v <= 0 for v in deficit.values()):
        # No deficit, no need for snacks
        return []
    
    # Score each snack based on how well it fills the deficit
    scored_snacks = []
    for snack in SNACK_DATABASE:
        # Calculate how well this snack matches the deficit
        # Higher score = better match
        score = 0.0
        
        # Protein match (most important for body recomposition)
        if deficit["protein"] > 0:
            protein_ratio = min(snack["protein_g"] / deficit["protein"], 1.0)
            score += protein_ratio * 3.0  # Weight protein heavily
        
        # Carbs match
        if deficit["carbs"] > 0:
            carbs_ratio = min(snack["carbs_g"] / deficit["carbs"], 1.0)
            score += carbs_ratio * 1.5
        
        # Fat match
        if deficit["fat"] > 0:
            fat_ratio = min(snack["fat_g"] / deficit["fat"], 1.0)
            score += fat_ratio * 1.5
        
        # Calorie match
        if deficit["calories"] > 0:
            cal_ratio = min(snack["calories"] / deficit["calories"], 1.0)
            score += cal_ratio * 1.0
        
        # Penalize snacks that are too large (exceed deficit too much)
        if deficit["calories"] > 0 and snack["calories"] > deficit["calories"] * 1.5:
            score *= 0.7
        
        scored_snacks.append({
            "snack": snack,
            "score": score
        })
    
    # Sort by score (highest first) and return top N with frontend-expected key names
    scored_snacks.sort(key=lambda x: x["score"], reverse=True)
    recommendations = []
    for item in scored_snacks[:num_recommendations]:
        snack = item["snack"]
        
        # Compute coverage percentages once, reuse for both reasons and coverage dict
        macro_map = [
            ("protein", snack["protein_g"], deficit["protein"], "High in protein to close {}g gap"),
            ("carbs",   snack["carbs_g"],   deficit["carbs"],   "Good carb source for {}g gap"),
            ("fat",     snack["fat_g"],     deficit["fat"],     "Helps close {}g fat gap"),
            ("calories",snack["calories"],  deficit["calories"],None),
        ]
        pct_values: dict[str, int] = {}
        for key, snack_val, def_val, _ in macro_map:
            pct_values[key] = min(round(snack_val / def_val * 100), 100) if def_val > 0 else 0
        
        # Build reason from highest-coverage macros (>= 50%)
        reasons = []
        for key, _, def_val, reason_tpl in macro_map:
            if reason_tpl and def_val > 0 and pct_values[key] >= 50:
                reasons.append(reason_tpl.format(def_val))
        reason = reasons[0] if reasons else "Balanced macro coverage"
        
        # Coverage percentages per macro as display strings
        coverage = {
            key: (f"{pct_values[key]}%" if def_val > 0 else "—")
            for key, _, def_val, _ in macro_map
        }
        
        recommendations.append({
            "name": snack["name"],
            "protein": snack["protein_g"],
            "carbs": snack["carbs_g"],
            "fat": snack["fat_g"],
            "calories": snack["calories"],
            "reason": reason,
            "coverage": coverage,
        })
    return recommendations


# --- SMART PROTEIN DISTRIBUTION ---

SMALL_PROTEIN_SNACKS = [
    {
        "name": "Greek Yogurt (170g)",
        "protein_g": 17,
        "carbs_g": 6,
        "fat_g": 1,
        "calories": 100,
        "notes": "Perfect for 10-20g protein deficit"
    },
    {
        "name": "Hard Boiled Eggs (2)",
        "protein_g": 12,
        "carbs_g": 1,
        "fat_g": 10,
        "calories": 140,
        "notes": "Good for 10-15g protein deficit"
    },
    {
        "name": "Protein Bar (mini)",
        "protein_g": 10,
        "carbs_g": 15,
        "fat_g": 6,
        "calories": 160,
        "notes": "Convenient for 10g deficit"
    },
    {
        "name": "Cottage Cheese (100g)",
        "protein_g": 11,
        "carbs_g": 3,
        "fat_g": 4,
        "calories": 98,
        "notes": "Low calorie, high protein"
    },
    {
        "name": "Almonds (28g / 1oz)",
        "protein_g": 6,
        "carbs_g": 6,
        "fat_g": 14,
        "calories": 162,
        "notes": "Healthy fats, good for 5-10g deficit"
    },
]


def distribute_protein_across_meals(daily_protein_target: int, num_meals: int = 3) -> List[int]:
    """
    Distribute daily protein target across meals to maximize utilization.

    Rules:
    - Cap: 40g per meal (profitability)
    - Distribute evenly when possible, spreading the remainder across leading meals
    - Maximize protein from meals, minimize from snacks

    Examples:
    - 133g target → [40, 40, 40] = 120g from meals, 13g from snacks
    - 90g target  → [30, 30, 30] = 90g from meals,  0g from snacks
    - 100g target → [34, 33, 33] = 100g from meals,  0g from snacks
    - 150g target → [40, 40, 40] = 120g from meals, 30g from snacks
    """
    max_per_meal = 40
    max_meals_capacity = num_meals * max_per_meal

    if daily_protein_target <= max_meals_capacity:
        base_per_meal = daily_protein_target / num_meals
        if base_per_meal <= max_per_meal:
            # Distribute evenly, spreading remainder across the first N meals
            base = daily_protein_target // num_meals
            remainder = daily_protein_target % num_meals
            return [base + (1 if i < remainder else 0) for i in range(num_meals)]
        else:
            # Would exceed cap — give max to every meal
            return [max_per_meal] * num_meals
    else:
        # Exceeds total meal capacity; give max to each meal, rest via snacks
        return [max_per_meal] * num_meals


def calculate_protein_deficit_for_snacks(daily_protein_target: int, meals_protein_distribution: List[int]) -> int:
    """
    Calculate how much protein needs to come from snacks given the per-meal distribution.
    """
    total_from_meals = sum(meals_protein_distribution)
    return max(0, daily_protein_target - total_from_meals)


def recommend_small_snacks_for_deficit(protein_deficit: int, num_recommendations: int = 3) -> List[Dict]:
    """
    Recommend SMALL snacks (100-200 kcal) that fill the protein gap.
    """
    if protein_deficit <= 0:
        return []

    # Filter snacks whose protein is within the deficit range (allow 5g buffer)
    suitable_snacks = [
        snack for snack in SMALL_PROTEIN_SNACKS
        if snack["protein_g"] <= protein_deficit + 5
    ]

    # Sort by protein content (highest first)
    suitable_snacks.sort(key=lambda x: x["protein_g"], reverse=True)

    return [
        {
            "name": snack["name"],
            "protein": snack["protein_g"],
            "carbs": snack["carbs_g"],
            "fat": snack["fat_g"],
            "calories": snack["calories"],
            "notes": snack.get("notes", ""),
        }
        for snack in suitable_snacks[:num_recommendations]
    ]


# Scoring weights for select_meal_for_protein_target
_MEAL_SCORE_BASE = 100
_PROTEIN_DISTANCE_WEIGHT = 2    # Penalty per gram away from protein target
_CALORIE_DISTANCE_WEIGHT = 0.1  # Penalty per kcal away from calorie target
_HIGH_PROTEIN_BONUS = 20        # Bonus for meals naturally in 30-40g protein range
_LOW_PROTEIN_PENALTY = 30       # Penalty for meals below 20g protein (hard to supplement)


def select_meal_for_protein_target(available_meals: List[Dict], target_protein: int, target_calories: int) -> Dict:
    """
    Select a meal that naturally fits the protein/calorie target.

    Prioritize meals where:
    - Base protein is 25-40g (close to target, minimal adjustment needed)
    - Base calories are within 20% of target

    Returns an empty dict if available_meals is empty.
    """
    if not available_meals:
        return {}

    scored_meals = []
    for meal in available_meals:
        base_macros = calculate_meal_macros_from_ingredients(meal.get("ingredients", []))
        base_protein = base_macros["protein_g"]
        base_calories = base_macros["calories"]

        protein_distance = abs(base_protein - target_protein)
        calorie_distance = abs(base_calories - target_calories)

        score = (
            _MEAL_SCORE_BASE
            - (protein_distance * _PROTEIN_DISTANCE_WEIGHT)
            - (calorie_distance * _CALORIE_DISTANCE_WEIGHT)
        )

        # Bonus for high-protein bases (30-40g) — need minimal adjustment
        if 30 <= base_protein <= 40:
            score += _HIGH_PROTEIN_BONUS

        # Penalty for very low protein (<20g) — hard to supplement
        if base_protein < 20:
            score -= _LOW_PROTEIN_PENALTY

        scored_meals.append({
            "meal": meal,
            "score": score,
            "base_protein": base_protein,
            "base_calories": base_calories,
        })

    scored_meals.sort(key=lambda x: x["score"], reverse=True)
    selected = scored_meals[0]["meal"] if scored_meals else available_meals[0]
    print(f"[SELECTION] {len(available_meals)} meals available for target {target_protein}g protein, {target_calories} kcal")
    if scored_meals:
        print(f"[SELECTION] Selected: {selected.get('name', 'unknown')} (score: {scored_meals[0]['score']:.1f})")
    else:
        print(f"[SELECTION] Selected: {selected.get('name', 'unknown')} (fallback, no scored meals)")
    return selected


# --- DYNAMIC MACRO CALCULATION from ingredient database ---

def calculate_meal_macros_from_ingredients(ingredients: List[str]) -> Dict[str, Any]:
    """
    Calculate real macros based on ingredient database (USDA data).
    Returns macros + ingredient breakdown.
    """
    total_protein = 0.0
    total_carbs = 0.0
    total_fat = 0.0
    total_calories = 0.0
    total_weight_g = 0.0

    ingredient_details = []
    missing_ingredients = []

    for ingredient_str in ingredients:
        canonical_name = find_ingredient(ingredient_str)

        if not canonical_name:
            print(f"[WARNING] Ingredient '{ingredient_str}' not found in database")
            missing_ingredients.append(ingredient_str)
            continue

        ingredient_data = INGREDIENT_DATABASE[canonical_name]
        serving_size = (
            ingredient_data["typical_serving_g"]
            if ingredient_data["unit"] == "g"
            else ingredient_data["typical_serving_ml"]
        )

        # Calculate macros for typical serving
        if ingredient_data["unit"] == "ml":
            protein = (ingredient_data["protein_per_100ml"] / 100) * serving_size
            carbs = (ingredient_data["carbs_per_100ml"] / 100) * serving_size
            fat = (ingredient_data["fat_per_100ml"] / 100) * serving_size
            calories = (ingredient_data["calories_per_100ml"] / 100) * serving_size
        else:
            protein = (ingredient_data["protein_per_100g"] / 100) * serving_size
            carbs = (ingredient_data["carbs_per_100g"] / 100) * serving_size
            fat = (ingredient_data["fat_per_100g"] / 100) * serving_size
            calories = (ingredient_data["calories_per_100g"] / 100) * serving_size

        total_protein += protein
        total_carbs += carbs
        total_fat += fat
        total_calories += calories
        total_weight_g += serving_size

        ingredient_details.append({
            "name": canonical_name,
            "amount": serving_size,
            "unit": ingredient_data["unit"],
            "protein": round(protein, 1),
            "carbs": round(carbs, 1),
            "fat": round(fat, 1),
            "calories": round(calories)
        })

    return {
        "protein_g": round(total_protein, 1),
        "carbs_g": round(total_carbs, 1),
        "fat_g": round(total_fat, 1),
        "calories": round(total_calories),
        "total_weight_g": round(total_weight_g),
        "ingredient_breakdown": ingredient_details,
        "missing_ingredients": missing_ingredients
    }


def adjust_meal_for_protein_target(meal_data: Dict, target_protein_per_meal: float) -> Dict[str, Any]:
    """
    Adjust meal to meet protein target SMARTLY.

    Rules:
    1. Cap target at 40g (profitability)
    2. Only add supplements to compatible meals (oatmeal, yogurt, smoothies)
    3. NEVER add supplements to soups, meats, beans, traditional cooked meals
    4. If meal already has 30-40g protein, don't modify
    5. If meal naturally exceeds 40g protein, scale down portions to enforce the cap
    """
    MAX_PROTEIN_PER_MEAL = 40

    # CAP at 40g for profitability
    if target_protein_per_meal > MAX_PROTEIN_PER_MEAL:
        print(f"[PROTEIN CAP] Reducing target from {target_protein_per_meal}g to {MAX_PROTEIN_PER_MEAL}g")
        target_protein_per_meal = MAX_PROTEIN_PER_MEAL

    base_macros = calculate_meal_macros_from_ingredients(meal_data.get("ingredients", []))
    base_protein = base_macros["protein_g"]

    # If meal naturally exceeds 40g protein, scale down portions to enforce the cap
    if base_protein > MAX_PROTEIN_PER_MEAL:
        print(f"[PROTEIN CAP] Meal has {base_protein}g protein, reducing to {MAX_PROTEIN_PER_MEAL}g")
        scale_factor = MAX_PROTEIN_PER_MEAL / base_protein
        final_macros = {
            "protein_g": round(MAX_PROTEIN_PER_MEAL, 1),
            "carbs_g": round(base_macros["carbs_g"] * scale_factor, 1),
            "fat_g": round(base_macros["fat_g"] * scale_factor, 1),
            "calories": round(base_macros["calories"] * scale_factor),
            "total_weight_g": round(base_macros.get("total_weight_g", 0) * scale_factor),
            "ingredient_breakdown": [
                {
                    **ing,
                    "amount": round(ing["amount"] * scale_factor, 1),
                    "protein": round(ing["protein"] * scale_factor, 1),
                    "carbs": round(ing["carbs"] * scale_factor, 1),
                    "fat": round(ing["fat"] * scale_factor, 1),
                    "calories": round(ing["calories"] * scale_factor)
                }
                for ing in base_macros.get("ingredient_breakdown", [])
            ],
            "missing_ingredients": base_macros.get("missing_ingredients", [])
        }
        return {
            "base_macros": base_macros,
            "modifications": [
                {
                    "type": "reduce_portion",
                    "internal": True,
                    "note": f"Internal adjustment: capped at {MAX_PROTEIN_PER_MEAL}g protein"
                }
            ],
            "final_macros": final_macros
        }

    protein_deficit = target_protein_per_meal - base_protein

    modifications = []
    final_macros = base_macros.copy()

    # Supplement or scale up to reach exactly 40g for any meaningful deficit (>0.5g tolerance)
    if protein_deficit > 0.5:
        ingredients_lower = [i.lower() for i in meal_data.get("ingredients", [])]

        # Meals where protein powder is acceptable
        powder_compatible = any(x in ingredients_lower for x in
            ["oats", "oatmeal", "greek yogurt", "yogurt", "smoothie", "milk shake"])

        # Meals where supplements should NEVER be added
        no_supplement = any(x in ingredients_lower for x in
            ["chicken", "beef", "turkey", "fish", "tuna", "salmon",
             "lentil", "soup", "beans", "chickpeas", "burrito", "bowl",
             "stew", "egg whites", "cottage cheese", "rice", "pasta",
             "salad", "pork", "lamb", "shrimp"])

        # Strategy 1: Add protein powder (oatmeal, smoothies, yogurt-based meals only)
        if powder_compatible and not no_supplement:
            # Max 1 scoop (30g) to avoid over-supplementing, but cap to not exceed 40g
            protein_powder_data = INGREDIENT_DATABASE["protein powder"]
            protein_powder_per_g = protein_powder_data["protein_per_100g"] / 100
            max_protein_to_add = MAX_PROTEIN_PER_MEAL - base_protein
            amount_g = min(30, max_protein_to_add / protein_powder_per_g) if protein_powder_per_g > 0 else 30
            amount_g = round(amount_g, 1)

            added_protein = (protein_powder_data["protein_per_100g"] / 100) * amount_g
            added_carbs = (protein_powder_data["carbs_per_100g"] / 100) * amount_g
            added_fat = (protein_powder_data["fat_per_100g"] / 100) * amount_g
            added_calories = (protein_powder_data["calories_per_100g"] / 100) * amount_g

            modifications.append({
                "type": "add",
                "ingredient": "protein powder",
                "amount": amount_g,
                "unit": "g",
                "internal": True,
                "macros": {
                    "protein": round(added_protein, 1),
                    "carbs": round(added_carbs, 1),
                    "fat": round(added_fat, 1),
                    "calories": round(added_calories)
                }
            })

            final_macros["protein_g"] += added_protein
            final_macros["carbs_g"] += added_carbs
            final_macros["fat_g"] += added_fat
            final_macros["calories"] += added_calories

        # Strategy 2: Add extra eggs (for egg-based breakfasts, only if not in no_supplement list)
        elif not no_supplement and any(x in ingredients_lower for x in ["eggs", "scrambled", "omelette"]):
            egg_data = INGREDIENT_DATABASE["eggs"]
            egg_protein_per_50g = (egg_data["protein_per_100g"] / 100) * 50  # protein per egg

            # For large deficits (>=15g), prefer protein powder to keep calories lower
            if protein_deficit >= 15:
                protein_powder_data = INGREDIENT_DATABASE["protein powder"]
                protein_powder_per_g = protein_powder_data["protein_per_100g"] / 100
                max_protein_to_add = MAX_PROTEIN_PER_MEAL - base_protein
                amount_g = min(30, max_protein_to_add / protein_powder_per_g) if protein_powder_per_g > 0 else 30
                amount_g = round(amount_g, 1)

                added_protein = (protein_powder_data["protein_per_100g"] / 100) * amount_g
                added_carbs = (protein_powder_data["carbs_per_100g"] / 100) * amount_g
                added_fat = (protein_powder_data["fat_per_100g"] / 100) * amount_g
                added_calories = (protein_powder_data["calories_per_100g"] / 100) * amount_g

                modifications.append({
                    "type": "add",
                    "ingredient": "protein powder",
                    "amount": amount_g,
                    "unit": "g",
                    "internal": True,
                    "macros": {
                        "protein": round(added_protein, 1),
                        "carbs": round(added_carbs, 1),
                        "fat": round(added_fat, 1),
                        "calories": round(added_calories)
                    }
                })

                final_macros["protein_g"] += added_protein
                final_macros["carbs_g"] += added_carbs
                final_macros["fat_g"] += added_fat
                final_macros["calories"] += added_calories

            else:
                # Small-to-medium deficit: add eggs using ceil to reach target
                extra_eggs = max(1, math.ceil(protein_deficit / egg_protein_per_50g)) if egg_protein_per_50g > 0 else 1
                amount_g = extra_eggs * 50

                added_protein = (egg_data["protein_per_100g"] / 100) * amount_g
                added_carbs = (egg_data["carbs_per_100g"] / 100) * amount_g
                added_fat = (egg_data["fat_per_100g"] / 100) * amount_g
                added_calories = (egg_data["calories_per_100g"] / 100) * amount_g

                modifications.append({
                    "type": "increase",
                    "ingredient": "eggs",
                    "amount": amount_g,
                    "unit": "g",
                    "internal": True,
                    "macros": {
                        "protein": round(added_protein, 1),
                        "carbs": round(added_carbs, 1),
                        "fat": round(added_fat, 1),
                        "calories": round(added_calories)
                    }
                })

                final_macros["protein_g"] += added_protein
                final_macros["carbs_g"] += added_carbs
                final_macros["fat_g"] += added_fat
                final_macros["calories"] += added_calories

        else:
            # For incompatible meals (meats, soups, beans, etc.) that cannot be supplemented,
            # scale up all ingredient portions proportionally to reach exactly 40g protein.
            if base_protein > 0:
                scale_factor = MAX_PROTEIN_PER_MEAL / base_protein
                final_macros["protein_g"] = MAX_PROTEIN_PER_MEAL
                final_macros["carbs_g"] = round(base_macros["carbs_g"] * scale_factor, 1)
                final_macros["fat_g"] = round(base_macros["fat_g"] * scale_factor, 1)
                final_macros["calories"] = round(base_macros["calories"] * scale_factor)

        # Force protein to exactly 40.0g regardless of supplementation path
        final_macros["protein_g"] = MAX_PROTEIN_PER_MEAL

    # Round final macros
    final_macros["protein_g"] = round(final_macros["protein_g"], 1)
    final_macros["carbs_g"] = round(final_macros["carbs_g"], 1)
    final_macros["fat_g"] = round(final_macros["fat_g"], 1)
    final_macros["calories"] = round(final_macros["calories"])

    return {
        "base_macros": base_macros,
        "modifications": modifications,
        "final_macros": final_macros
    }


def validate_daily_calories(daily_menu: List[Dict], target_daily_calories: int) -> List[Dict]:
    """
    Ensures daily total doesn't exceed target by more than 5%.
    If over, proportionally scales down macros for all meals in the day.
    """
    total_calories = sum(meal.get("final_macros", {}).get("calories", 0) for meal in daily_menu)

    if total_calories <= 0:
        return daily_menu

    max_allowed = target_daily_calories * 1.05

    if total_calories > max_allowed:
        scale_factor = target_daily_calories / total_calories

        for meal in daily_menu:
            if "final_macros" in meal:
                meal["final_macros"]["calories"] = round(meal["final_macros"]["calories"] * scale_factor)
                meal["final_macros"]["protein_g"] = round(meal["final_macros"]["protein_g"] * scale_factor, 1)
                meal["final_macros"]["carbs_g"] = round(meal["final_macros"]["carbs_g"] * scale_factor, 1)
                meal["final_macros"]["fat_g"] = round(meal["final_macros"]["fat_g"] * scale_factor, 1)

            if "portion_multiplier" in meal:
                meal["portion_multiplier"] = round(meal["portion_multiplier"] * scale_factor, 2)

    return daily_menu


def validate_daily_macros(
    daily_menu: List[Dict],
    target_protein: int,
    target_carbs: int,
    target_fat: int,
    target_calories: int,
) -> List[Dict]:
    """
    Validates daily totals for carbs, fat, and calories only.
    Uses SINGLE scaling operation to prevent calorie oscillation:
    1. Collects ALL required scale factors BEFORE applying any
    2. Chooses the MOST CONSERVATIVE factor (closest to 1.0)
    3. Applies that factor ONCE and ONLY ONCE

    Uses FIXED tolerances (not percentages) to prevent over-aggressive scaling:
    - Fat:     ±5g    (e.g. 50–60g for a 55g target)
    - Carbs:   ±10g   (e.g. 188–208g for a 198g target)
    - Calories: ±75 kcal (e.g. 1,575–1,725 for a 1,650 kcal target)

    After any scaling, enforces an absolute minimum of 1,550 kcal.  If the
    scaled result would fall below that floor, meals are scaled UP to reach it.
    Fat may then slightly exceed its target — that is intentional and preferable
    to delivering a nutritionally inadequate plan.

    CRITICAL: Does NOT scale protein. Protein is already enforced at 30-40g per
    meal by adjust_meal_for_protein_target(). Scaling protein here would cause a
    double reduction.
    """
    total_carbs = sum(m.get("final_macros", {}).get("carbs_g", 0) for m in daily_menu)
    total_fat = sum(m.get("final_macros", {}).get("fat_g", 0) for m in daily_menu)
    total_calories = sum(m.get("final_macros", {}).get("calories", 0) for m in daily_menu)

    if total_calories <= 0:
        return daily_menu

    # Fixed tolerances (not percentages) to prevent over-aggressive scaling.
    FAT_TOLERANCE = 5       # ±5g
    CARBS_TOLERANCE = 10    # ±10g
    CALORIE_TOLERANCE = 75  # ±75 kcal

    min_fat = target_fat - FAT_TOLERANCE            # e.g. 50g
    max_fat = target_fat + FAT_TOLERANCE            # e.g. 60g
    min_carbs = target_carbs - CARBS_TOLERANCE      # e.g. 188g
    max_carbs = target_carbs + CARBS_TOLERANCE      # e.g. 208g
    min_calories = target_calories - CALORIE_TOLERANCE  # e.g. 1,575 kcal
    max_calories = target_calories + CALORIE_TOLERANCE  # e.g. 1,725 kcal

    # Safety floor: never allow a day to fall below this regardless of other adjustments.
    # 1,550 kcal is below any reasonable meal target (plans start at ~1,650 kcal) but well
    # above the bare minimum required to avoid nutritionally inadequate delivery.  It ensures
    # that an aggressive fat-correcting scale-down cannot collapse daily calories to harmful
    # levels (e.g. 1,081 kcal), even when fat is significantly over target.
    ABSOLUTE_MIN_CALORIES = 1550

    total_protein = sum(m.get("final_macros", {}).get("protein_g", 0) for m in daily_menu)
    print(f"[VALIDATION] Daily totals: {total_protein}g P (not scaled), {total_carbs:.1f}g C, {total_fat:.1f}g F, {total_calories} kcal")
    print(f"[VALIDATION] Targets: {target_carbs}g C ({min_carbs}-{max_carbs}g), {target_fat}g F ({min_fat}-{max_fat}g), {min_calories}-{max_calories} kcal")
    print(f"[VALIDATION] Absolute minimum: {ABSOLUTE_MIN_CALORIES} kcal")

    # STEP 1: Collect ALL potential scale factors WITHOUT applying any.
    # Calorie and fat factors are added when outside tolerance; carbs are informational only.
    scale_factors = []
    reasons = []

    # Check calories (most important): collect scale-up or scale-down factor as needed.
    if total_calories < min_calories:
        factor = target_calories / total_calories
        scale_factors.append(factor)
        reasons.append(f"calories LOW ({total_calories} < {min_calories})")
        print(f"[VALIDATION] Would need factor {factor:.3f} to fix low calories")
    elif total_calories > max_calories:
        factor = target_calories / total_calories
        scale_factors.append(factor)
        reasons.append(f"calories HIGH ({total_calories} > {max_calories})")
        print(f"[VALIDATION] Would need factor {factor:.3f} to fix high calories")

    # Check fat (±5g fixed tolerance).
    if total_fat < min_fat:
        factor = target_fat / total_fat
        scale_factors.append(factor)
        reasons.append(f"fat LOW ({total_fat:.1f}g < {min_fat}g)")
        print(f"[VALIDATION] Would need factor {factor:.3f} to fix low fat")
    elif total_fat > max_fat:
        factor = target_fat / total_fat
        scale_factors.append(factor)
        reasons.append(f"fat HIGH ({total_fat:.1f}g > {max_fat}g)")
        print(f"[VALIDATION] Would need factor {factor:.3f} to fix high fat")

    # Carbs: informational only — usually self-correct when calories/fat are fixed.
    if total_carbs > max_carbs:
        print(f"[VALIDATION] INFO: Carbs high ({total_carbs:.1f}g > {max_carbs}g), will likely fix with other adjustments")
    elif total_carbs < min_carbs:
        print(f"[VALIDATION] INFO: Carbs low ({total_carbs:.1f}g < {min_carbs}g), will likely self-correct")

    # STEP 2: Choose MOST CONSERVATIVE factor (closest to 1.0) and apply ONCE.
    if scale_factors:
        scale_factor = min(scale_factors, key=lambda x: abs(1.0 - x))
        chosen_reason = reasons[scale_factors.index(scale_factor)]
        other_factors = [f for f in scale_factors if f != scale_factor]

        print(f"[VALIDATION] Applying SINGLE scale factor: {scale_factor:.3f} ({chosen_reason})")
        if other_factors:
            print(f"[VALIDATION] Other factors considered but NOT applied: {[f'{f:.3f}' for f in other_factors]}")

        for meal in daily_menu:
            if "final_macros" in meal:
                # Scale carbs, fat, calories — DO NOT scale protein
                meal["final_macros"]["carbs_g"] = round(meal["final_macros"]["carbs_g"] * scale_factor, 1)
                meal["final_macros"]["fat_g"] = round(meal["final_macros"]["fat_g"] * scale_factor, 1)
                meal["final_macros"]["calories"] = round(meal["final_macros"]["calories"] * scale_factor)
                # protein_g intentionally left unchanged

            if "portion_multiplier" in meal:
                meal["portion_multiplier"] = round(meal["portion_multiplier"] * scale_factor, 2)

        new_total_calories = sum(m["final_macros"]["calories"] for m in daily_menu)
        new_total_fat = sum(m["final_macros"]["fat_g"] for m in daily_menu)
        new_total_carbs = sum(m["final_macros"]["carbs_g"] for m in daily_menu)
        print(f"[VALIDATION] Result after scaling: {new_total_calories} kcal, {new_total_carbs:.1f}g C, {new_total_fat:.1f}g F")
    else:
        print(f"[VALIDATION] All macros within targets, no scaling needed")
        new_total_calories = total_calories
        new_total_fat = total_fat

    # STEP 3: Enforce absolute minimum calories — scale UP if needed.
    # This handles the case where fat-triggered scaling collapsed daily calories.
    # Fat may then exceed its target, which is intentional: adequate calories are
    # non-negotiable; fat deviation is a minor and correctable trade-off.
    if new_total_calories < ABSOLUTE_MIN_CALORIES:
        correction_factor = ABSOLUTE_MIN_CALORIES / new_total_calories
        print(f"[VALIDATION] ⚠️ CRITICAL: Result {new_total_calories} kcal < absolute minimum {ABSOLUTE_MIN_CALORIES} kcal")
        print(f"[VALIDATION] Correcting UP by factor {correction_factor:.3f}")

        for meal in daily_menu:
            if "final_macros" in meal:
                meal["final_macros"]["carbs_g"] = round(meal["final_macros"]["carbs_g"] * correction_factor, 1)
                meal["final_macros"]["fat_g"] = round(meal["final_macros"]["fat_g"] * correction_factor, 1)
                meal["final_macros"]["calories"] = round(meal["final_macros"]["calories"] * correction_factor)
                # protein_g intentionally left unchanged

            if "portion_multiplier" in meal:
                meal["portion_multiplier"] = round(meal["portion_multiplier"] * correction_factor, 2)

        final_calories = sum(m["final_macros"]["calories"] for m in daily_menu)
        final_fat = sum(m["final_macros"]["fat_g"] for m in daily_menu)
        final_carbs = sum(m["final_macros"]["carbs_g"] for m in daily_menu)
        print(f"[VALIDATION] ✓ After correction: {final_calories} kcal, {final_carbs:.1f}g C, {final_fat:.1f}g F")
        if final_fat > max_fat:
            excess = final_fat - max_fat
            print(f"[VALIDATION] Note: Fat now {excess:.1f}g above tolerance ({max_fat}g) — acceptable to meet calorie minimum")
    elif min_calories <= new_total_calories <= max_calories:
        print(f"[VALIDATION] ✓ Result within acceptable calorie range ({min_calories}-{max_calories})")
    else:
        deviation = new_total_calories - target_calories
        print(f"[VALIDATION] Result {deviation:+.0f} kcal from target, within tolerance")

    return daily_menu



MEAT_KEYWORDS = {"chicken","beef","pork","turkey","lamb","bacon","ham","steak"}
FISH_KEYWORDS = {"salmon","shrimp","fish","tuna","trout","cod","shellfish","prawns"}
RED_MEAT_KEYWORDS = {"beef","lamb","steak","veal","bison"}
DAIRY_KEYWORDS = {"milk","yogurt","cheese","butter","cream"}
EGG_KEYWORDS = {"egg","eggs"}
NUT_KEYWORDS = {"nut","nuts","almond","walnut","peanut"}
GLUTEN_KEYWORDS = {"wheat","barley","rye","gluten"}
SOY_KEYWORDS = {"soy","tofu","soy sauce"}
SESAME_KEYWORDS = {"sesame"}
CORN_KEYWORDS = {"corn"}

# Expanded vegetable synonyms/keywords to better detect 'Vegetables' dislike
VEGETABLE_KEYWORDS = {
    "broccoli","spinach","lettuce","carrot","zucchini","eggplant","tomato","bell pepper",
    "cabbage","kale","arugula","asparagus","bok choy","green beans","peas","onion","mushroom",
    "greens","mixed greens","salad","mixed vegetables","vegetables","veg","spring mix","spinach leaves"
}


def is_meal_compatible_with_diet(ingredients: List[str], diet: Optional[str]) -> bool:
    if not diet:
        return True
    d = diet.lower()
    ings = [i.lower() for i in (ingredients or [])]
    if d == "omnivore":
        return True
    if d == "pescatarian":
        return not any(any(mk in ing for mk in MEAT_KEYWORDS) for ing in ings)
    if d == "vegetarian":
        return not any(any(mk in ing for mk in (MEAT_KEYWORDS | FISH_KEYWORDS)) for ing in ings)
    if d in ("no red meat", "no_red_meat"):
        return not any(any(rk in ing for rk in RED_MEAT_KEYWORDS) for ing in ings)
    if d == "few restrictions":
        return True
    return True


# --- BUSINESS LOGIC (MEALS) with robust filtering and per-meal protein allocation ---
def filter_meals(dislikes: List[str], allergies: List[str], dietary_restrictions: List[str], diet: Optional[str]) -> List[Meal]:
    """
    Build a set of undesired keywords from dislikes/allergies/dietary_restrictions,
    including expanding "vegetables" into many vegetable keywords. Then exclude any meal
    where any undesired keyword appears in any ingredient token or in tags.
    """
    undesired = set()
    def add_term(val: str):
        v = str(val or "").strip().lower()
        if not v:
            return
        # expand vegetables
        if "vegetable" in v or v == "vegetables" or v == "veg":
            undesired.update(VEGETABLE_KEYWORDS)
            return
        # map common synonyms
        if v in ("no pork","pork-free"):
            undesired.update({"pork","bacon","ham"})
            return
        undesired.add(v)

    # collect dislikes
    for lst in (dislikes or []):
        if isinstance(lst, list):
            for it in lst:
                if it and isinstance(it, str):
                    val = it.strip()
                    if val.lower().startswith("none") or val.lower().startswith("i like"):
                        continue
                    add_term(val)
        elif isinstance(lst, str):
            add_term(lst)

    # collect allergies
    for lst in (allergies or []):
        if isinstance(lst, list):
            for it in lst:
                if it and isinstance(it, str):
                    val = it.strip()
                    if val.lower().startswith("none"):
                        continue
                    add_term(val)
        elif isinstance(lst, str):
            add_term(lst)

    # dietary restrictions (preferences)
    for r in (dietary_restrictions or []):
        rr = str(r).lower()
        if "gluten" in rr:
            undesired.update(GLUTEN_KEYWORDS)
        elif "lactose" in rr or "dairy" in rr:
            undesired.update(DAIRY_KEYWORDS)
        elif "nut" in rr:
            undesired.update(NUT_KEYWORDS)
        elif "pork" in rr:
            undesired.update({"pork","bacon","ham"})
        elif "chicken" in rr or "poultry" in rr:
            undesired.update({"chicken","poultry"})
        elif "seafood" in rr or "shellfish" in rr:
            undesired.update(FISH_KEYWORDS)
        elif "red meat" in rr or "no red meat" in rr:
            undesired.update(RED_MEAT_KEYWORDS)
        elif "soy" in rr:
            undesired.update(SOY_KEYWORDS)
        elif "corn" in rr:
            undesired.update(CORN_KEYWORDS)
        elif "sesame" in rr:
            undesired.update(SESAME_KEYWORDS)
        elif rr and not rr.startswith("none"):
            undesired.add(rr)

    out = []
    for m in MEALS_DATA:
        ings = [i.lower() for i in m.get("ingredients", [])]
        # diet compatibility first
        if not is_meal_compatible_with_diet(ings, diet):
            continue

        # Check tags too
        tags = [t.lower() for t in (m.get("tags") or [])]

        conflict = False
        for u in undesired:
            # check against ingredients tokens and tags
            for ing in ings:
                # split ingredient into words and tokens, check tokens and substring
                tokens = [tok.strip() for tok in ing.replace('/', ' ').replace('-', ' ').split()]
                if any(u == tok or u in tok or tok in u for tok in tokens):
                    conflict = True
                    break
                # fallback substring
                if u in ing:
                    conflict = True
                    break
            if conflict:
                break
            # tags match
            if any(u == t or u in t for t in tags):
                conflict = True
                break
        if not conflict:
            try:
                out.append(Meal(**m))
            except Exception as e:
                print("meal validation error", e)
    return out


# --- Template helpers: rotate pool by week and expand template to schedule ---
def week_seed_string_from_date(dt: Optional[datetime.datetime] = None) -> str:
    d = (dt or datetime.datetime.now(datetime.timezone.utc)).date()
    iso = d.isocalendar()
    return f"{iso[0]}-W{iso[1]}"

def parse_week_string(week_str: str) -> int:
    try:
        return int(week_str.split("-W")[-1])
    except Exception:
        return 0

def rotate_pool_by_week(pool: List[str], week_seed: str) -> List[str]:
    if not pool:
        return []
    # compute an integer from seed (week number or hash)
    try:
        weeknum = parse_week_string(week_seed)
    except Exception:
        weeknum = 0
    if weeknum == 0:
        h = hashlib.sha256(week_seed.encode()).hexdigest()
        weeknum = int(h[:8], 16)
    offset = weeknum % len(pool)
    return pool[offset:] + pool[:offset]

def find_meal_by_name(name: str) -> Optional[Meal]:
    if not name:
        return None
    nm = name.strip().lower()
    found = next((m for m in MEALS_DATA if str(m.get("name","")).strip().lower() == nm), None)
    if found:
        try:
            return Meal(**found)
        except Exception:
            # fallback minimal
            return Meal(name=found.get("name",""), type=found.get("type","Main Meal"), ingredients=found.get("ingredients",[]), calories=int(found.get("calories",0)), price=float(found.get("price",0.0)), image_url=found.get("image_url"))
    return None

def generate_daily_menu(meals: List[dict], calorie_target: int) -> List[dict]:
    """
    Select meals for the day that stay within the calorie target.
    """
    daily_menu = []
    total_calories = 0

    for meal in meals:
        if total_calories + meal["calories"] <= calorie_target:
            daily_menu.append(meal)
            total_calories += meal["calories"]

        # Stop adding meals if the calorie target is reached
        if total_calories >= calorie_target:
            break

    # Debugging daily totals
    print("[DEBUG] Daily menu generated:")
    print(f"- Total Calories: {total_calories} kcal (Target: {calorie_target} kcal)")
    return daily_menu if total_calories <= calorie_target else []


def expand_template_to_schedule(template: Dict[str, Any], week: Optional[str] = None) -> Dict[str, Any]:
    """
    Expand a template (from menus_weekly.json) into a week schedule.
    Returns dict with fields: template_id, week, days, sequence (list per-day slots), totals.
    Template rules expected:
      rules: { plan, days, mains: { unique_count, repeat_each }, breakfasts: { unique_count, total_needed } }
      pool: { mains: [...names...], breakfasts: [...] }
    """
    week_seed = week or week_seed_string_from_date()
    days = template.get("rules", {}).get("days", 7)
    plan = template.get("rules", {}).get("plan", 4)
    mains_pool_names = list(template.get("pool", {}).get("mains", []))
    breaks_pool_names = list(template.get("pool", {}).get("breakfasts", []))

    # rotate pools by week to vary weekly
    mains_rot = rotate_pool_by_week(mains_pool_names, week_seed)
    breaks_rot = rotate_pool_by_week(breaks_pool_names, week_seed)

    # rules
    mains_rules = template.get("rules", {}).get("mains", {})
    breakfasts_rules = template.get("rules", {}).get("breakfasts", {})
    mains_unique = mains_rules.get("unique_count", len(mains_rot))
    mains_repeat_each = mains_rules.get("repeat_each", 1)
    breakfasts_unique = breakfasts_rules.get("unique_count", len(breaks_rot))
    breakfasts_total_needed = breakfasts_rules.get("total_needed", days)

    # ensure we don't request more unique than available
    mains_unique = min(mains_unique, len(mains_rot)) if mains_rot else 0
    breakfasts_unique = min(breakfasts_unique, len(breaks_rot)) if breaks_rot else 0

    # choose the unique pools (take first mains_unique names from rotated pool)
    chosen_mains = mains_rot[:mains_unique] if mains_unique > 0 else []
    chosen_breaks = breaks_rot[:breakfasts_unique] if breakfasts_unique > 0 else []

    # Build expanded mains list by repeating each chosen main repeat_each times
    mains_expanded = []
    for name in chosen_mains:
        mains_expanded.extend([name] * mains_repeat_each)
    # if still not enough mains to reach needed (plan 4 -> mains_needed = 2 * days), repeat pool rotated
    mains_needed = 0
    if plan == 4:
        mains_needed = 2 * days
    elif plan == 3:
        mains_needed = 1 * days
    elif plan == 2:
        mains_needed = 2 * days
    else:
        mains_needed = 1 * days

    # if expanded shorter, repeat rotated pool until reach mains_needed
    idx = 0
    while len(mains_expanded) < mains_needed and chosen_mains:
        mains_expanded.append(chosen_mains[idx % len(chosen_mains)])
        idx += 1

    mains_expanded = mains_expanded[:mains_needed]

    # Breaks: distribute breakfasts_total_needed across chosen_breaks as evenly as possible
    breaks_needed = breakfasts_total_needed
    breaks_expanded = []
    if chosen_breaks:
        base = breaks_needed // len(chosen_breaks)
        rem = breaks_needed - base * len(chosen_breaks)
        for i, name in enumerate(chosen_breaks):
            count = base + (1 if i < rem else 0)
            breaks_expanded.extend([name] * count)
    # if no breakfasts chosen but breaks_rot available, fallback to rotated
    if not breaks_expanded and breaks_rot:
        # pick first 'breaks_needed' names repeating
        i = 0
        while len(breaks_expanded) < breaks_needed:
            breaks_expanded.append(breaks_rot[i % len(breaks_rot)])
            i += 1

    breaks_expanded = breaks_expanded[:breaks_needed]

    # Now build day-by-day sequence: for plan 4 we want per day: [breakfast] + [main1, main2]
    sequence = []
    mains_idx = 0
    breaks_idx = 0
    for d in range(days):
        slots = []
        # breakfast(s)
        num_breaks = 1 if plan == 3 or plan == 4 else (0 if plan == 1 else 0)
        for _ in range(num_breaks):
            if breaks_idx < len(breaks_expanded):
                slots.append(breaks_expanded[breaks_idx]); breaks_idx += 1
            else:
                # fallback: use any main as breakfast if needed
                slots.append(mains_expanded[mains_idx % len(mains_expanded)] if mains_expanded else (breaks_rot[0] if breaks_rot else None))
        # mains
        num_main = 0
        if plan == 1:
            num_main = 1
        elif plan == 2:
            num_main = 2
        elif plan == 3:
            num_main = 1
        elif plan == 4:
            num_main = 2
        for _ in range(num_main):
            if mains_idx < len(mains_expanded):
                slots.append(mains_expanded[mains_idx]); mains_idx += 1
            else:
                # fallback: rotate chosen_mains
                slots.append(chosen_mains[(mains_idx) % max(1, len(chosen_mains))] if chosen_mains else None)
                mains_idx += 1
        sequence.append({"day": d+1, "slots": slots})

    totals = {"breakfasts": len(breaks_expanded), "mains": len(mains_expanded), "unique_mains": len(set(mains_expanded)), "unique_breakfasts": len(set(breaks_expanded))}
    return {"template_id": template.get("id"), "week": week_seed, "days": days, "sequence": sequence, "totals": totals}


# --- Helper: sanitize template names against user dislikes/allergies/preferences ---
def sanitize_template_names_for_user(state: SessionState, name_list: List[str]) -> List[str]:
    """
    Given a sequence of meal names (from a template expanded schedule),
    return a sanitized list where any meal incompatible with the user's dislikes/allergies/diet
    is replaced by an allowed alternative of the same type where possible.
    """
    if not name_list:
        return []

    # Build allowed meals according to user's filters
    allowed_meals = filter_meals(state.dislikes, state.allergies, state.dietary_restrictions, state.diet_preference)
    # Map by lowercase name for fast lookup
    allowed_by_name = {m.name.strip().lower(): m for m in allowed_meals}

    # Build pools by type for replacements
    allowed_by_type: Dict[str, List[Meal]] = {}
    for m in allowed_meals:
        t = (m.type or "Main Meal").strip().lower()
        allowed_by_type.setdefault(t, []).append(m)

    result: List[str] = []
    used = set()

    for orig in name_list:
        key = (orig or "").strip().lower()
        # if exact allowed and not exceeding naive reuse preference, keep it
        if key and key in allowed_by_name and key not in used:
            result.append(allowed_by_name[key].name)
            used.add(key)
            continue

        # determine desired type from meals.json if possible
        candidate = next((x for x in MEALS_DATA if str(x.get("name","")).strip().lower() == key), None)
        desired_type = candidate.get("type","main meal").strip().lower() if candidate else None

        # Try find a replacement of same type not yet used
        replacement = None
        if desired_type and desired_type in allowed_by_type:
            for m in allowed_by_type[desired_type]:
                nm = m.name.strip().lower()
                if nm not in used:
                    replacement = m
                    break
        # If not found, try any allowed of any type not used
        if not replacement:
            for tpool in allowed_by_type.values():
                for m in tpool:
                    nm = m.name.strip().lower()
                    if nm not in used:
                        replacement = m
                        break
                if replacement:
                    break

        if replacement:
            result.append(replacement.name)
            used.add(replacement.name.strip().lower())
        else:
            # As last resort, if original exists in meals.json return original (even if incompatible)
            # This keeps schedule length consistent; it's better to log and allow fallback.
            if key:
                found_orig = next((x for x in MEALS_DATA if str(x.get("name","")).strip().lower() == key), None)
                if found_orig:
                    result.append(found_orig.get("name"))
                else:
                    # unknown name: keep original string to avoid breaking schedule
                    result.append(orig)
            else:
                result.append(orig)
    return result


# --- BUSINESS / MENU generation integration ---
def generate_menu_using_template(state: SessionState) -> List[Meal]:
    """
    If a session has template_id and selected_week, produce a list of Meal objects
    in order (flattened day slots). Returns list of Meal objects or empty list on error.
    """
    if not state.template_id:
        return []
    tpl = next((t for t in TEMPLATES_DATA if t.get("id") == state.template_id), None)
    if not tpl:
        return []
    week = state.selected_week or week_seed_string_from_date()
    sch = expand_template_to_schedule(tpl, week)
    # flatten sequence into list of meal names in day order
    flat_names: List[str] = []
    for day in sch["sequence"]:
        for slot in day["slots"]:
            if slot:
                flat_names.append(slot)

    # Sanitize names for this specific user (apply dislikes/allergies/diet)
    safe_names = sanitize_template_names_for_user(state, flat_names)

    # map safe_names to Meal objects (fallback to placeholder dict if not found)
    menu_objs: List[Meal] = []
    for name in safe_names:
        m = find_meal_by_name(name)
        if m:
            menu_objs.append(m)
        else:
            # try to find something compatible from MEALS_DATA with same name substring
            candidate = next((x for x in MEALS_DATA if name.strip().lower() in str(x.get("name","")).strip().lower()), None)
            if candidate:
                try:
                    menu_objs.append(Meal(**candidate))
                except Exception:
                    menu_objs.append(Meal(name=name or "Unknown", type="Main Meal", ingredients=[], calories=0, price=0.0))
            else:
                menu_objs.append(Meal(name=name or "Unknown", type="Main Meal", ingredients=[], calories=0, price=0.0))
    return menu_objs

def allocate_protein_to_menu(state: SessionState, menu: List[Meal], macros_daily_protein: Optional[int], calorie_target: int) -> List[Dict[str, Any]]:
    """
    Dynamically distribute macros (protein, carbs, fats) across meals.
    For Plan 4: distributes daily totals EVENLY across 3 meals (1 breakfast + 2 main meals)
    Maximum 40g protein per meal.
    """
    if not menu:
        return []

    # Plan definitions: (num_main_meals, num_breakfasts)
    plan_map = {1: (1, 0), 2: (2, 0), 3: (1, 1), 4: (2, 1)}
    num_main, num_break = plan_map.get(state.plan, (1, 0))
    meals_per_day = num_main + num_break
    days = state.days or max(1, len(menu) // max(1, meals_per_day))

    # Daily nutritional targets
    daily_protein_target = int(macros_daily_protein or 120)  # Default 120g if not provided
    daily_calorie_target = int(calorie_target or 2000)  # Default 2000 kcal

    # Use smart protein distribution: evenly across meals with 40g cap.
    # When target > 40g × num_meals, all slots are capped at 40g and the
    # remainder is covered by snacks (not reflected here).
    protein_distribution = distribute_protein_across_meals(daily_protein_target, meals_per_day)
    protein_per_meal = protein_distribution[0]  # First slot value (may differ by ±1g for remainder slots)

    # Calculate daily macros
    # Fat: 25% of calories
    # Carbs: remaining calories
    fat_calories = daily_calorie_target * 0.25
    daily_fat_target = int(fat_calories / 9)
    protein_calories = daily_protein_target * 4
    carb_calories = daily_calorie_target - protein_calories - fat_calories
    daily_carb_target = int(max(0, carb_calories / 4))

    fat_per_meal = daily_fat_target // meals_per_day
    carbs_per_meal = daily_carb_target // meals_per_day
    calories_per_meal = daily_calorie_target // meals_per_day

    fat_remainder = daily_fat_target % meals_per_day
    carbs_remainder = daily_carb_target % meals_per_day

    print(f"\n[DEBUG] Daily Targets for Plan {state.plan}:")
    print(f"  - Calories: {daily_calorie_target} kcal")
    print(f"  - Protein: {daily_protein_target}g")
    print(f"  - Fat: {daily_fat_target}g")
    print(f"  - Carbs: {daily_carb_target}g")
    print(f"  - Meals per day: {meals_per_day} ({num_break} breakfast + {num_main} main meals)")

    print(f"\n[DEBUG] Per Meal Distribution (smart protein distribution):")
    print(f"  - Protein: {protein_per_meal}g each (max 40g, distribution: {protein_distribution})")
    print(f"  - Fat: ~{fat_per_meal}g")
    print(f"  - Carbs: ~{carbs_per_meal}g")
    print(f"  - Calories: ~{calories_per_meal} kcal")

    out = []
    idx = 0

    for day in range(days):
        for meal_idx_in_day in range(meals_per_day):
            if idx >= len(menu):
                break

            meal_obj = menu[idx]
            meal_dict = meal_obj.model_dump() if hasattr(meal_obj, "model_dump") else dict(meal_obj)

            # Use smart protein distribution value for this slot
            assigned_protein = protein_distribution[meal_idx_in_day % len(protein_distribution)]
            assigned_fat = fat_per_meal + (1 if meal_idx_in_day < fat_remainder else 0)
            assigned_carbs = carbs_per_meal + (1 if meal_idx_in_day < carbs_remainder else 0)

            # Calculate actual calories from macros
            assigned_calories = (assigned_protein * 4) + (assigned_carbs * 4) + (assigned_fat * 9)

            # Update meal with calculated macros
            meal_dict["provided_protein"] = assigned_protein
            meal_dict["protein_assigned"] = assigned_protein
            meal_dict["fat_assigned"] = assigned_fat
            meal_dict["carbs_assigned"] = assigned_carbs
            meal_dict["calories"] = int(assigned_calories)
            meal_dict["day_index"] = day
            meal_dict["meal_index"] = idx

            print(f"\n[DEBUG] Day {day + 1}, Meal {meal_idx_in_day + 1}: {meal_dict.get('name', 'Unnamed')}")
            print(f"  - Protein: {assigned_protein}g")
            print(f"  - Carbs: {assigned_carbs}g")
            print(f"  - Fat: {assigned_fat}g")
            print(f"  - Calories: {int(assigned_calories)} kcal")

            out.append(meal_dict)
            idx += 1

    return out



# Keep original generate_menu as fallback for non-template flows
def generate_menu(state: SessionState, protein_per_meal: Optional[int] = None, calories_per_meal: Optional[int] = None, variety_window: int = 3) -> List[Meal]:
    """
    Generate menu with meal variety tracking.

    Args:
        state: Current session state.
        protein_per_meal: Target protein grams per meal slot.
        calories_per_meal: Target calories per meal slot.
        variety_window: Don't repeat meals within this many days (default 3).
    """
    if state.template_id:
        # if a template is set, prefer template-driven generation
        return generate_menu_using_template(state)
    if not state.plan or not state.days:
        return []
    plan_map = {1:(1,0), 2:(2,0), 3:(1,1), 4:(2,1)}
    num_main, num_break = plan_map.get(state.plan, (1,0))
    available = filter_meals(state.dislikes, state.allergies, state.dietary_restrictions, state.diet_preference)
    if not available:
        return []
    mains = [m for m in available if m.type.lower() == "main meal"]
    breakfasts = [m for m in available if m.type.lower() == "breakfast"]

    # Variety tracking: keep names of recently selected meals across days
    recently_used_meals: List[str] = []
    max_recent = variety_window * (num_main + num_break)

    menu = []
    for day_idx in range(state.days):
        day_items = []
        meals_used_today: List[str] = []

        def pick_meal(pool: List[Meal]) -> Optional[Meal]:
            """Select a meal from pool, honouring variety constraints."""
            if not pool:
                return None

            pool_dicts = [m.model_dump() if hasattr(m, "model_dump") else dict(m) for m in pool]

            # Filter out meals used today and recently across days
            unique_dicts = [
                m for m in pool_dicts
                if m["name"] not in meals_used_today and m["name"] not in recently_used_meals
            ]

            if not unique_dicts:
                # Relax to: at least not used today
                unique_dicts = [m for m in pool_dicts if m["name"] not in meals_used_today]

            if not unique_dicts:
                # No unique options at all — allow any meal and reset recent tracking
                print(
                    f"[VARIETY WARNING] Day {day_idx + 1}: No unique meals available. "
                    f"Allowing repeats to meet nutritional goals."
                )
                recently_used_meals.clear()
                unique_dicts = pool_dicts

            if protein_per_meal is not None and calories_per_meal is not None:
                best_dict = select_meal_for_protein_target(unique_dicts, protein_per_meal, calories_per_meal)
                selected = Meal(**best_dict)
            else:
                selected = Meal(**(random.choice(unique_dicts)))

            meals_used_today.append(selected.name)
            recently_used_meals.append(selected.name)
            if len(recently_used_meals) > max_recent:
                recently_used_meals.pop(0)
            return selected

        for _ in range(num_break):
            if breakfasts:
                meal = pick_meal(breakfasts)
                if meal:
                    day_items.append(meal)
        for _ in range(num_main):
            if mains:
                meal = pick_meal(mains)
                if meal:
                    day_items.append(meal)

        if not day_items and available:
            day_items.append(random.choice(available))
        menu.extend(day_items)
    return menu[: state.days * (num_main + num_break)]


def assess_menu_possibility(state: SessionState) -> Dict[str, Any]:
    if not state.plan or not state.days:
        return {"ok": False, "reason":"missing_data", "message":"Plan or days are not set."}
    plan_map = {1:(1,0),2:(2,0),3:(1,1),4:(2,1)}
    need_main, need_break = plan_map.get(state.plan, (0,0))
    need_mains_total = need_main * state.days
    need_break_total = need_break * state.days
    avail = filter_meals(state.dislikes, state.allergies, state.dietary_restrictions, state.diet_preference)
    if not avail:
        return {"ok": False, "reason":"no_meals", "message":"No meals available after applying filters."}
    mains = [m for m in avail if m.type.lower()=="main meal"]
    breaks = [m for m in avail if m.type.lower()=="breakfast"]
    details = {"available_total": len(avail), "available_mains": len(mains), "available_breakfasts": len(breaks), "need_mains_total": need_mains_total, "need_breakfasts_total": need_break_total}
    if need_mains_total > len(mains):
        return {"ok": False, "reason":"not_enough_mains", "message":"Not enough Main Meal options.", "details": details}
    if need_break_total > len(breaks):
        return {"ok": False, "reason":"not_enough_breakfasts", "message":"Not enough Breakfast options.", "details": details}
    return {"ok": True, "details": details}


def validate_plan_for_protein_goal(num_meals: int, daily_protein_target: int) -> Dict[str, Any]:
    """
    Validates if selected plan can meet protein goal with a reasonable snack burden.

    Returns a validation result with messages for the frontend. Plans that require
    too much protein from snacks are flagged so users can be guided to upgrade.
    """
    MAX_PROTEIN_PER_MEAL = 40

    protein_from_meals = num_meals * MAX_PROTEIN_PER_MEAL
    protein_gap = max(0, daily_protein_target - protein_from_meals)

    # Plan 4 (3 meals): Always optimal for high protein
    if num_meals == 3:
        if protein_gap <= 20:
            message = (
                f"Perfect! Our 3 meals provide {protein_from_meals}g protein. "
                f"You only need ~{protein_gap}g from a simple snack."
            )
        else:
            message = (
                f"Our 3 meals provide {protein_from_meals}g protein (maximum we can offer). "
                f"You'll need ~{protein_gap}g from snacks to reach your {daily_protein_target}g goal."
            )
        return {
            "valid": True,
            "protein_from_meals": protein_from_meals,
            "protein_gap": protein_gap,
            "message": message,
            "snack_burden": "low",
        }

    # Plan 2 (2 meals): Validate gap
    elif num_meals == 2:
        if protein_gap <= 30:
            return {
                "valid": True,
                "protein_from_meals": protein_from_meals,
                "protein_gap": protein_gap,
                "message": f"Our 2 meals provide {protein_from_meals}g protein. You'll need ~{protein_gap}g from snacks.",
                "snack_burden": "medium",
            }
        else:
            plan4_protein_from_meals = 3 * MAX_PROTEIN_PER_MEAL
            plan4_gap = max(0, daily_protein_target - plan4_protein_from_meals)
            return {
                "valid": False,
                "protein_from_meals": protein_from_meals,
                "protein_gap": protein_gap,
                "message": f"⚠️ With 2 meals/day, you'd need {protein_gap}g protein from snacks (difficult to manage).",
                "recommendation": "upgrade_to_plan_4",
                "upgrade_message": (
                    f"💡 Plan 4 (3 meals/day) provides {plan4_protein_from_meals}g protein from meals. "
                    f"You'd only need ~{plan4_gap}g from snacks!"
                ),
                "upgrade_benefits": [
                    f"{plan4_protein_from_meals}g protein from meals (vs {protein_from_meals}g)",
                    f"Only ~{plan4_gap}g from snacks (vs {protein_gap}g)",
                    "Easier to follow",
                    "Better compliance",
                ],
            }

    # Plan 1 (1 meal): Only valid for low protein targets
    elif num_meals == 1:
        if daily_protein_target <= 80:
            return {
                "valid": True,
                "protein_from_meals": protein_from_meals,
                "protein_gap": protein_gap,
                "message": f"Our meal provides {protein_from_meals}g protein. You'll need ~{protein_gap}g from snacks.",
                "snack_burden": "high",
            }
        else:
            return {
                "valid": False,
                "protein_from_meals": protein_from_meals,
                "protein_gap": protein_gap,
                "message": f"❌ Your protein goal ({daily_protein_target}g) requires at least 2-3 meals/day.",
                "recommendation": "upgrade_required",
                "minimum_plan": 4 if daily_protein_target > 110 else 2,
            }

    return {"valid": False, "message": "Invalid plan selection"}


def calculate_meal_calorie_distribution(daily_calories: int, num_meals: int, protein_gap: int) -> Dict[str, Any]:
    """
    Calculates how to distribute calories between meals and snacks.

    For Plan 4 (3 meals) with a small protein gap (<=25g), reserves 100-200 kcal
    for snacks so meals don't consume the entire daily budget. Other plans use
    all calories in meals.
    """
    # ~10 kcal reserved per gram of protein gap (snack needs ~10 kcal/g of protein)
    _SNACK_KCAL_PER_GRAM_PROTEIN = 10
    _MIN_SNACK_RESERVE_KCAL = 100
    _MAX_SNACK_RESERVE_KCAL = 200

    if num_meals == 3 and protein_gap <= 25:
        snack_calorie_reserve = min(
            _MAX_SNACK_RESERVE_KCAL,
            max(_MIN_SNACK_RESERVE_KCAL, protein_gap * _SNACK_KCAL_PER_GRAM_PROTEIN),
        )
        meal_calories_total = daily_calories - snack_calorie_reserve
        calories_per_meal = round(meal_calories_total / num_meals)
        return {
            "calories_per_meal": calories_per_meal,
            "total_meal_calories": meal_calories_total,
            "snack_calories_reserved": snack_calorie_reserve,
            "message": f"Meals designed for {meal_calories_total} kcal, leaving {snack_calorie_reserve} kcal for snacks",
        }
    else:
        calories_per_meal = round(daily_calories / num_meals)
        return {
            "calories_per_meal": calories_per_meal,
            "total_meal_calories": daily_calories,
            "snack_calories_reserved": 0,
            "message": f"All {daily_calories} kcal distributed across {num_meals} meals",
        }


def generate_flexible_snack_message(protein_gap: int, carbs_gap: int, fat_gap: int, calories_gap: int) -> Dict[str, Any]:
    """
    Generates flexible snack guidance with nutrient ranges instead of exact values.
    Only used for Plan 4 when the protein gap is small (<=25g).
    """
    # Range half-widths: allow ±5g protein, ±10g carbs, ±30 kcal flexibility
    _PROTEIN_RANGE_DELTA = 5
    _CARBS_RANGE_DELTA = 10
    _CAL_RANGE_DELTA = 30
    _MIN_PROTEIN_G = 10
    _MIN_CARBS_G = 10
    _MIN_CAL = 100

    protein_min = max(_MIN_PROTEIN_G, protein_gap - _PROTEIN_RANGE_DELTA)
    protein_max = protein_gap + _PROTEIN_RANGE_DELTA

    carbs_min = max(_MIN_CARBS_G, carbs_gap - _CARBS_RANGE_DELTA)
    carbs_max = max(_MIN_CARBS_G + _CARBS_RANGE_DELTA, carbs_gap + _CARBS_RANGE_DELTA)

    cal_min = max(_MIN_CAL, calories_gap - _CAL_RANGE_DELTA)
    cal_max = calories_gap + _CAL_RANGE_DELTA

    message = (
        f"Complete your day with a snack containing:\n"
        f"• {protein_min}-{protein_max}g protein\n"
        f"• {carbs_min}-{carbs_max}g carbs\n"
        f"• {cal_min}-{cal_max} calories\n\n"
        f"💡 Ideas:\n"
        f"• Greek yogurt (170g) - ~17g protein, 100 kcal\n"
        f"• Cottage cheese (100g) + fruit - ~11g protein, 140 kcal\n"
        f"• Hard boiled eggs (2) + berries - ~12g protein, 180 kcal\n"
        f"• Protein shake - ~20g protein, 120 kcal\n"
        f"• Almonds (28g) + apple - ~6g protein, 200 kcal"
    )

    return {
        "show_snacks": True,
        "message": message,
        "protein_range": f"{protein_min}-{protein_max}g",
        "carbs_range": f"{carbs_min}-{carbs_max}g",
        "calories_range": f"{cal_min}-{cal_max} kcal",
    }

def process_meal_data(meal: Meal, protein: int, calories: int, fat_ratio: float = 0.25, carb_ratio: float = 0.50) -> Meal:
    """
    Procesar dinámicamente las macros (calorías, proteínas, grasas y carbohidratos) para cada comida.
    Args:
        meal (Meal): La comida original.
        protein (int): Gramos de proteína asignados dinámicamente.
        calories (int): Calorías totales asignadas dinámicamente.
        fat_ratio (float): Porcentaje de calorías asignadas a grasas. Default 25%.
        carb_ratio (float): Porcentaje de calorías asignadas a carbohidratos. Default 50%.
    Returns:
        Meal: La comida dinámica con macros calculadas.
    """
    protein_calories = max(0, protein * 4)
    fat_calories = max(0, calories * fat_ratio)
    fat_grams = fat_calories / 9  # 1 g grasa = 9 kcal
    carb_calories = max(0, calories - (protein_calories + fat_calories))
    carb_grams = carb_calories / 4  # 1 g carbohidrato = 4 kcal

    # Asegurar que no haya valores negativos
    fat_grams = max(0, round(fat_grams))
    carb_grams = max(0, round(carb_grams))

    # Regresar el objeto Meal con valores dinámicos
        # Normalizar a valores enteros y evitar negativos
    meal.calories = max(0, calories)
    meal.protein = max(0, protein)
    meal.fat = max(0, int(fat_grams))
    meal.carbs = max(0, int(carb_grams))

    return meal

# --- UI form definitions (unchanged) ---
def get_form_fields(step_name: str, state: Optional[SessionState] = None):
    if step_name == "diet_preference":
        return {"question":"What is your diet preference?","fields":[{"name":"Diet Preference","type":"select","options":["Omnivore","Vegetarian","Pescatarian","No Red Meat"], "required": True}],"current_step":"diet_preference"}
    if step_name == "pick_plan":
        return {"question":"Which plan do you want?","fields":[{"name":"Plan","type":"select","options":["Plan 1: 1 main meal per day","Plan 2: 2 main meals per day","Plan 3: 1 main meal + 1 breakfast","Plan 4: 2 main meals + 1 breakfast (full day)"], "required": True}],"current_step":"pick_plan"}
    if step_name == "objective":
        return {"question":"What is your main goal?","fields":[{"name":"Objective","type":"select","options":["Lose Fat","Gain Muscle","Maintain Shape","Body Recomposition (Lose Fat & Gain Muscle)"], "required": True}],"current_step":"objective"}
    if step_name == "allergies_and_restrictions":
        return {
            "question": "Select your allergies:",
            "fields": [
                {
                    "name": "Selected Allergies",
                    "type": "multiselect",
                    "options": [
                        "Peanuts",
                        "Tree Nuts",
                        "Dairy",
                        "Gluten",
                        "Eggs",
                        "Fish",
                        "Shellfish",
                        "Soy",
                        "Spicy",
                    ],
                    "required": False,
                },
                {
                    "name": "Any other allergy or note?",
                    "type": "text",
                    "placeholder": "Optional",
                    "required": False,
                },
            ],
            "current_step": "allergies_and_restrictions",
        }
    if step_name == "personal_info":
        return {
            "question":"Tell us your personal data:",
            "fields":[
                {"name":"Weight Unit","type":"select","options":["kg","lbs"], "required": True},
                {"name":"Weight","type":"number","placeholder":"e.g. 70","unit":"kg or lbs", "required": True},
                {"name":"Height Unit","type":"select","options":["cm","in"], "required": True},
                {"name":"Height","type":"number","placeholder":"e.g. 175","unit":"cm or in", "required": True},
                {"name":"Age","type":"number","placeholder":"e.g. 30", "required": True},
                {"name":"Sex","type":"select","options":["Male","Female"], "required": True},
                {"name":"Days per week","type":"select","options":["0","1-2","3-4","5-7"], "unit":"How many days do you exercise on average?", "required": True},
                {"name":"Avg session duration","type":"select","options":["<30","30-60","60-120"], "unit":"Typical session length (minutes)", "required": True},
                {"name":"Intensity","type":"select","options":["Low","Moderate","High"], "unit":"Select intensity (Low/Moderate/High).", "required": True}
            ],
            "current_step":"personal_info"
        }
    if step_name == "duration":
        return {"question":"For how many days do you want this plan?","fields":[{"name":"Days","type":"number","min":1,"max":30,"placeholder":"e.g. 7", "required": True}],"current_step":"duration"}
    if step_name == "review":
        if not state:
            return {"question":"State error. Start again.","current_step":"review"}
        # Send state data as a single field for frontend to parse
        state_data = {
            "plan_number": state.plan,
            "days": state.days,
            "diet_preference": state.diet_preference or "Omnivore",
            "allergies_and_restrictions": state.allergies_and_restrictions or "None",
            "selected_allergies": state.allergies,
            "allergy_note": state.allergy_note,
            "weight_value": state.weight,
            "weight_unit": state.weight_unit,
            "height_value": state.height,
            "height_unit": state.height_unit,
            "age": state.age,
            "days_per_week": state.activity_days_bucket,
            "avg_session_duration": state.activity_duration_bucket,
            "intensity": state.activity_intensity,
            "sex": state.sex
        }
        return {"question": "Review your information and generate the menu", "fields": [{"name": "state_data", "type": "hidden", "value": state_data}], "current_step":"review"}
    return {"question":"Unknown step. Start again.","current_step":"start"}


# --- ENDPOINTS & FLOW HANDLER (uses new allocation & templates) ---
def normalize_request_payload(payload: Dict[str, Any]) -> NextStepRequest:
    session_id = payload.get("session_id") or payload.get("sessionId") or payload.get("id") or str(uuid4())
    step = payload.get("step") or payload.get("current_step") or payload.get("currentStep") or "start"
    answer = payload.get("answer") or payload.get("answers") or payload.get("data") or {}
    if answer is None:
        answer = {}
    return NextStepRequest(session_id=session_id, step=step, answer=answer)

@app.post("/next-step")
async def next_step(request: Request):
    payload = await request.json()
    req = normalize_request_payload(payload)
    session_id = req.session_id
    step_name = normalize_step_name(req.step)
    raw_answer = req.answer or {}
    if session_id not in sessions:
        sessions[session_id] = SessionState().model_dump()
    state = SessionState(**sessions[session_id])
    answer = map_answer_keys(raw_answer)

    # handle back (special)
    if step_name == "back" and state.history:
        prev = state.history.pop()
        sessions[session_id] = prev
        return get_form_fields(prev.get("current_step","start"), SessionState(**prev))

    if step_name != "start":
        state.history.append(sessions[session_id].copy())

    step_to_render_name = state.current_step

    if step_name == "start":
        step_to_render_name = STEPS["start"]

    elif step_name == "diet_preference":
        if "diet_preference" in answer:
            state.diet_preference = str(answer.get("diet_preference"))
        step_to_render_name = STEPS["diet_preference"]

    elif step_name == "pick_plan":
        plan = answer.get("plan")
        if plan:
            try:
                if isinstance(plan, str) and ":" in plan:
                    plan_num = int(plan.split(":")[0].replace("Plan","").strip())
                else:
                    plan_num = int(plan)
                if plan_num in (1,2,3,4):
                    state.plan = plan_num
            except Exception:
                pass
        step_to_render_name = STEPS["pick_plan"]

    elif step_name == "objective":
        if "objective" in answer:
            state.objective = answer.get("objective")
        step_to_render_name = STEPS["objective"]

    elif step_name == "allergies_and_restrictions":
        selected = (
            answer.get("selected_allergies")
            or answer.get("Selected Allergies")
            or answer.get("allergies")
            or []
        )
        if isinstance(selected, str):
            selected = [s.strip() for s in selected.split(",") if s.strip()]
        if isinstance(selected, list):
            state.allergies = [str(s).strip().lower() for s in selected if str(s).strip()]

        note_val = (
            answer.get("allergy_note")
            or answer.get("Any other allergy or note?")
            or answer.get("allergies_and_restrictions")
            or ""
        )
        state.allergy_note = str(note_val).strip() or None

        combined_parts = []
        if state.allergies:
            combined_parts.append(", ".join(state.allergies))
        if state.allergy_note:
            combined_parts.append(state.allergy_note)
        state.allergies_and_restrictions = " | ".join(combined_parts) if combined_parts else None
        step_to_render_name = STEPS["allergies_and_restrictions"]

    elif step_name == "personal_info":
        # DEBUG: Log all field names to identify issue
        print(f"DEBUG - Personal Info Handler Received:")
        print(f"  Field names: {list(answer.keys())}")
        print(f"  Full data: {answer}")
        
        try:
            # Note: diet_preference is now collected in an earlier step
            # Handle both form field names (with spaces) and custom renderer names
            
            # Weight unit - check "Weight Unit" (from form) or "weight_unit" (custom)
            if "Weight Unit" in answer:
                state.weight_unit = answer.get("Weight Unit")
            elif "weight_unit" in answer:
                state.weight_unit = answer.get("weight_unit")
                
            # Weight - check all possible field names
            if "weightvalue" in answer:         # From form (no underscore!)
                try:
                    state.weight = float(answer.get("weightvalue"))
                except Exception:
                    state.weight = None
            elif "Weight" in answer:            # From form (capital W)
                try:
                    state.weight = float(answer.get("Weight"))
                except Exception:
                    state.weight = None
            elif "weight_value" in answer:      # From custom renderer
                try:
                    state.weight = float(answer.get("weight_value"))
                except Exception:
                    state.weight = None
            elif "weight" in answer:            # Legacy
                try:
                    state.weight = float(answer.get("weight"))
                except Exception:
                    state.weight = None
                    
            # Height unit - check "Height Unit" (from form) or "height_unit" (custom)
            if "Height Unit" in answer:
                state.height_unit = answer.get("Height Unit")
            elif "height_unit" in answer:
                state.height_unit = answer.get("height_unit")
                
            # Height - check all possible field names
            if "heightvalue" in answer:         # From form (no underscore!)
                try:
                    state.height = float(answer.get("heightvalue"))
                except Exception:
                    state.height = None
            elif "Height" in answer:            # From form (capital H)
                try:
                    state.height = float(answer.get("Height"))
                except Exception:
                    state.height = None
            elif "height_value" in answer:      # From custom renderer
                try:
                    state.height = float(answer.get("height_value"))
                except Exception:
                    state.height = None
            elif "height" in answer:            # Legacy
                try:
                    state.height = float(answer.get("height"))
                except Exception:
                    state.height = None
                    
            # Age - check "Age" (from form) or "age" (custom)
            if "Age" in answer:
                try:
                    state.age = int(answer.get("Age"))
                except Exception:
                    state.age = None
            elif "age" in answer:
                try:
                    state.age = int(answer.get("age"))
                except Exception:
                    state.age = None
                    
            # Sex - check "Sex" (from form) or "sex" (custom)
            if "Sex" in answer:
                state.sex = answer.get("Sex")
            elif "sex" in answer:
                state.sex = answer.get("sex")
                
            # Activity days - check "Days per week" (from form) or other variants
            if "Days per week" in answer:
                state.activity_days_bucket = str(answer.get("Days per week"))
            elif "days_per_week" in answer:
                state.activity_days_bucket = str(answer.get("days_per_week"))
            elif "activity_days_bucket" in answer:
                state.activity_days_bucket = str(answer.get("activity_days_bucket"))
                
            # Activity duration - check "Avg session duration" (from form) or other variants
            if "Avg session duration" in answer:
                state.activity_duration_bucket = str(answer.get("Avg session duration"))
            elif "avg_session_duration" in answer:
                state.activity_duration_bucket = str(answer.get("avg_session_duration"))
            elif "activity_duration_bucket" in answer:
                state.activity_duration_bucket = str(answer.get("activity_duration_bucket"))
                
            # Intensity - check "Intensity" (from form) or other variants
            if "Intensity" in answer:
                state.activity_intensity = str(answer.get("Intensity"))
            elif "intensity" in answer:
                state.activity_intensity = str(answer.get("intensity"))
            elif "activity_intensity" in answer:
                state.activity_intensity = str(answer.get("activity_intensity"))
                
            # Go directly to duration (no restrictions step anymore)
            step_to_render_name = STEPS["personal_info"]
        except Exception:
            step_to_render_name = "personal_info"

    elif step_name == "duration":
        days_val = answer.get("days") or answer.get("Days")
        try:
            if days_val is not None and int(days_val) >= 1:
                state.days = int(days_val)
        except Exception:
            pass
        step_to_render_name = STEPS["duration"]  # Goes to review


    elif step_name == "review":
            try:
                # Si el usuario seleccionó un template, configúralo y calcula el target
                if "template_id" in answer:
                    state.template_id = answer.get("template_id")

                    # Calcula la semana seleccionada basada en la lógica de corte jueves 22:00
                    now = datetime.datetime.now(datetime.timezone.utc)
                    weekday = now.weekday()  # Monday=0
                    thursday_cutoff = datetime.datetime.combine(
                        now + datetime.timedelta(days=(3 - weekday)).date(),
                        datetime.time(hour=22, minute=0)
                    )
                    if now <= thursday_cutoff:
                        sunday = now + datetime.timedelta(days=(6 - weekday))
                    else:
                        sunday = now + datetime.timedelta(days=(6 - weekday + 7))
                    iso = sunday.date().isocalendar()
                    state.selected_week = f"{iso[0]}-W{iso[1]}"

                # Valida que sea posible generar un menú
                assessment = assess_menu_possibility(state)
                if not assessment["ok"]:
                    return {
                        "question": assessment.get("message", "Could not generate menu with current settings."),
                        "fields": [],
                        "current_step": state.current_step,
                        "issue": assessment.get("reason"),
                        "details": assessment.get("details", {}),
                    }

                # Calcula calorías objetivo y macros ANTES de generar el menú
                # para poder usar smart meal selection with protein targets
                weight_kg = to_kg(state.weight, state.weight_unit) if state.weight else None
                height_cm = to_cm(state.height, state.height_unit) if state.height else None

                # DEBUG: Log values to help troubleshoot
                print(f"DEBUG - Menu Generation:")
                print(f"  state.weight: {state.weight}")
                print(f"  state.weight_unit: {state.weight_unit}")
                print(f"  weight_kg: {weight_kg}")
                print(f"  state.height: {state.height}")
                print(f"  state.height_unit: {state.height_unit}")
                print(f"  height_cm: {height_cm}")
                print(f"  state.age: {state.age}")
                print(f"  state.sex: {state.sex}")

                tmb = calc_tmb_mifflin(weight_kg, height_cm, state.age, state.sex, state.objective or "")
                print(f"  TMB calculated: {tmb}")
                tdee = (
                    round(
                        tmb
                        * compute_activity_factor(
                            state.activity_days_bucket or "0",
                            state.activity_duration_bucket or "<30",
                            state.activity_intensity or "Low",
                        ),
                        1,
                    )
                    if tmb
                    else None
                )
                calorie_target = calc_calorie_target(tdee, state.objective, state.sex or "female") if tdee else None
                macros = calc_macros(calorie_target, state.objective, weight_kg, state.sex)

                # Determine smart protein distribution across meals BEFORE selecting meals
                daily_protein_target = macros.get("protein_grams", 0)
                plan_map_meals = {1: (1, 0), 2: (2, 0), 3: (1, 1), 4: (2, 1)}
                num_main_pre, num_break_pre = plan_map_meals.get(state.plan, (1, 0))
                meals_per_day_pre = num_main_pre + num_break_pre
                protein_distribution_pre = distribute_protein_across_meals(daily_protein_target, meals_per_day_pre)
                protein_per_meal_pre = protein_distribution_pre[0]

                # Validate plan against protein goal and calculate calorie distribution
                plan_validation = validate_plan_for_protein_goal(meals_per_day_pre, daily_protein_target)
                if not plan_validation["valid"]:
                    return {
                        "question": plan_validation["message"],
                        "fields": [],
                        "current_step": state.current_step,
                        "issue": "plan_protein_mismatch",
                        "plan_validation": plan_validation,
                    }

                calorie_dist = calculate_meal_calorie_distribution(
                    daily_calories=int(calorie_target or 2000),
                    num_meals=meals_per_day_pre,
                    protein_gap=plan_validation["protein_gap"],
                )
                calories_per_meal_pre = calorie_dist["calories_per_meal"]

                print(f"  Smart protein distribution: {protein_distribution_pre} (target: {daily_protein_target}g)")
                print(f"  Calorie distribution: {calorie_dist['message']}")

                # Generate the base menu using smart meal selection
                base_menu_objs = generate_menu(state, protein_per_meal=protein_per_meal_pre, calories_per_meal=calories_per_meal_pre, variety_window=3)

                # Ajusta proteína y calorías dinámicamente por comida
                menu_with_protein = allocate_protein_to_menu(state, base_menu_objs, daily_protein_target, calorie_target)

                if not menu_with_protein:  # Validación adicional de seguridad
                    print("[ERROR] Menu with protein is empty, validation failed!")
                    return {
                        "question": "No meals could be allocated with the current settings.",
                        "fields": [],
                        "current_step": state.current_step,
                        "issue": "validation_failed",
                    }

                # **Get daily macros from calc_macros (not by summing all meals across all days!)**
                # The macros dict contains the DAILY targets, not totals across all days
                total_protein = macros.get("protein_grams", 0)
                total_carbs = macros.get("carbs_grams", 0)
                total_fat = macros.get("fat_grams", 0)
                total_calories = macros.get("calories", 0)

                # Print debug information about daily totals
                print("[DEBUG] Daily macronutrient totals (per day, not across all days):")
                print(f"- Total Protein: {total_protein} g")
                print(f"- Total Carbohydrates: {total_carbs} g")
                print(f"- Total Fats: {total_fat} g")
                print(f"- Total Calories: {total_calories} kcal")

                # Modifica la respuesta según el plan
                # Determine meals per day based on plan
                plan_map = {1: (1, 0), 2: (2, 0), 3: (1, 1), 4: (2, 1)}  # (num_main, num_break)
                num_main, num_break = plan_map.get(state.plan, (1, 0))
                meals_per_day = num_main + num_break
                
                response_menu = []
                meal_index = 0
                for meal in menu_with_protein:
                    meal_entry = dict(meal)
                    
                    # Calculate day number and meal type
                    day_num = (meal_index // meals_per_day) + 1
                    position_in_day = meal_index % meals_per_day
                    
                    # Determine meal type based on plan and position
                    if state.plan == 1:  # 1 lunch per day
                        meal_type = "LUNCH"
                    elif state.plan == 2:  # 2 lunches (lunch + dinner)
                        meal_type = "LUNCH" if position_in_day == 0 else "DINNER"
                    elif state.plan == 3:  # breakfast + lunch
                        meal_type = "BREAKFAST" if position_in_day == 0 else "LUNCH"
                    elif state.plan == 4:  # breakfast + lunch + dinner
                        if position_in_day == 0:
                            meal_type = "BREAKFAST"
                        elif position_in_day == 1:
                            meal_type = "LUNCH"
                        else:
                            meal_type = "DINNER"
                    else:
                        meal_type = "MEAL"
                    
                    # Add day and meal type labels
                    meal_entry["day_number"] = day_num
                    meal_entry["meal_type"] = meal_type
                    meal_entry["day_label"] = f"DAY {day_num} - {meal_type}"
                    
                    # Use the values already calculated by allocate_protein_to_menu
                    # These are already correct and evenly distributed
                    meal_entry["protein_assigned"] = int(meal.get("provided_protein", 0))
                    meal_entry["fat_assigned"] = int(meal.get("fat_assigned", 0))
                    meal_entry["carbs_assigned"] = int(meal.get("carbs_assigned", 0))
                    meal_entry["calories_assigned"] = int(meal.get("calories", 0))

                    # Calculate real ingredient-based macros (dynamic calculation)
                    protein_target_for_meal = meal_entry["protein_assigned"]
                    adjusted = adjust_meal_for_protein_target(meal, protein_target_for_meal)
                    meal_entry["base_macros"] = adjusted["base_macros"]
                    meal_entry["modifications"] = adjusted["modifications"]
                    meal_entry["final_macros"] = adjusted["final_macros"]

                    # Calculate portion multiplier using real ingredient-based protein
                    # (replaces the previous use of hardcoded protein_g from meals.json)
                    base_protein = adjusted["base_macros"]["protein_g"]
                    if base_protein > 0:
                        portion_multiplier = meal_entry["protein_assigned"] / base_protein
                        meal_entry["portion_multiplier"] = round(portion_multiplier, 2)
                        meal_entry["serving_size_adjusted"] = int(meal.get("serving_size_g", 300) * portion_multiplier)
                    else:
                        meal_entry["portion_multiplier"] = 1.0
                        meal_entry["serving_size_adjusted"] = meal.get("serving_size_g", 300)
                    
                    print(f"[DEBUG] {meal_entry['day_label']}: {meal.get('name', 'Unnamed')} - "
                          f"Protein: {meal_entry['protein_assigned']}g, "
                          f"Carbs: {meal_entry['carbs_assigned']}g, "
                          f"Fat: {meal_entry['fat_assigned']}g, "
                          f"Calories: {meal_entry['calories_assigned']} kcal, "
                          f"Portion: {meal_entry['portion_multiplier']}x")

                    response_menu.append(meal_entry)
                    meal_index += 1

                # Apply per-day macro validation: scale down or up carbs/fat/calories so each
                # day's total is within 5% of the meal calorie target.
                # Protein is NOT scaled (already enforced at ~40g per meal).
                days_in_menu = set(m.get("day_number", 1) for m in response_menu)
                for day_num in days_in_menu:
                    day_meals = [m for m in response_menu if m.get("day_number", 1) == day_num]
                    validate_daily_macros(
                        daily_menu=day_meals,
                        target_protein=macros.get("protein_grams", 0),
                        target_carbs=macros.get("carbs_grams", 0),
                        target_fat=macros.get("fat_grams", 0),
                        target_calories=calorie_dist["total_meal_calories"],
                    )

                # Compute Day 1 meal totals from final_macros (post-adjustment values)
                day1_meals = [m for m in response_menu if m.get("day_number", 1) == 1]
                day1_meal_protein = round(sum(m["final_macros"]["protein_g"] for m in day1_meals), 1)
                day1_meal_carbs = round(sum(m["final_macros"]["carbs_g"] for m in day1_meals), 1)
                day1_meal_fat = round(sum(m["final_macros"]["fat_g"] for m in day1_meals), 1)
                day1_meal_calories = round(sum(m["final_macros"]["calories"] for m in day1_meals))

                # Calcula el precio total
                total_price = calculate_price(
                    [Meal(**m) if isinstance(m, dict) else m for m in response_menu], 0
                )

                # Calculate achieved macros from the actual meals (for ONE day only)
                achieved_protein = 0
                achieved_carbs = 0
                achieved_fat = 0
                achieved_calories = 0
                
                # Sum macros for first day's meals only
                for i, meal_entry in enumerate(response_menu):
                    if meal_entry.get("day_number", 1) == 1:  # Only first day
                        achieved_protein += meal_entry.get("protein_assigned", 0)
                        achieved_carbs += meal_entry.get("carbs_assigned", 0)
                        achieved_fat += meal_entry.get("fat_assigned", 0)
                        achieved_calories += meal_entry.get("calories_assigned", 0)
                
                print(f"\n[DEBUG] Achieved macros (Day 1):")
                print(f"  - Protein: {achieved_protein}g")
                print(f"  - Carbs: {achieved_carbs}g")
                print(f"  - Fat: {achieved_fat}g")
                print(f"  - Calories: {achieved_calories} kcal")
                
                # Calculate macro deficit
                deficit = calculate_macro_deficit(
                    target_macros=macros,
                    achieved_macros={
                        "protein_grams": achieved_protein,
                        "carbs_grams": achieved_carbs,
                        "fat_grams": achieved_fat,
                        "calories": achieved_calories
                    }
                )
                
                print(f"\n[DEBUG] Macro Deficit:")
                print(f"  - Protein: {deficit['protein']}g")
                print(f"  - Carbs: {deficit['carbs']}g")
                print(f"  - Fat: {deficit['fat']}g")
                print(f"  - Calories: {deficit['calories']} kcal")

                # Compute protein from meals vs. daily target for context-aware snack message.
                # Use the pre-computed distribution (not the achieved total) so the deficit
                # correctly reflects what the meal plan was designed to provide.
                protein_from_meals = achieved_protein
                protein_deficit_for_snacks = plan_validation["protein_gap"]

                # Build snack info: flexible range message for Plan 4 with small gap,
                # individual recommendations for other cases.
                snack_flexible_info = None
                snack_recommendations = []
                if state.plan == 4 and protein_deficit_for_snacks <= 25:
                    # Plan 4 with small protein gap: show flexible snack guidance (ranges)
                    carbs_deficit = max(0, macros.get("carbs_grams", 0) - achieved_carbs)
                    fat_deficit = max(0, macros.get("fat_grams", 0) - achieved_fat)
                    snack_flexible_info = generate_flexible_snack_message(
                        protein_gap=protein_deficit_for_snacks,
                        carbs_gap=carbs_deficit,
                        fat_gap=fat_deficit,
                        calories_gap=calorie_dist["snack_calories_reserved"],
                    )
                    print(f"\n[DEBUG] Plan 4 flexible snack guidance: {protein_deficit_for_snacks}g protein gap")
                elif protein_deficit_for_snacks > 0 and protein_deficit_for_snacks <= 25:
                    # Small deficit — recommend compact, low-calorie snacks
                    snack_recommendations = recommend_small_snacks_for_deficit(
                        protein_deficit_for_snacks, num_recommendations=3
                    )
                    print(f"\n[DEBUG] Small protein deficit ({protein_deficit_for_snacks}g) — "
                          f"recommended {len(snack_recommendations)} small snacks")
                elif deficit["protein"] >= 10 or deficit["calories"] >= 200:
                    snack_recommendations = recommend_snacks(deficit, num_recommendations=3)
                    print(f"\n[DEBUG] Recommended {len(snack_recommendations)} snacks to fill deficit")

                # Context-aware snack message
                if protein_deficit_for_snacks > 0:
                    snack_message = (
                        f"Your meals provide {int(protein_from_meals)}g protein. "
                        f"To reach your {daily_protein_target}g daily goal, add a small snack:"
                    )
                else:
                    snack_message = "Your meals meet your protein goal! Optional snacks for extra energy:"

                # Respuesta basada en el plan seleccionado
                if state.plan == 4:
                    # Build daily summary for Plan 4
                    # Carbs remaining for the snack after meals contribute their share
                    remaining_carbs_for_snacks = max(0, macros.get("carbs_grams", 0) - day1_meal_carbs)
                    # Snack protein range: ±5g around the deficit, with a minimum of 10g
                    _snack_protein_floor = 10
                    _snack_range_variance = 5
                    daily_summary = {
                        "meals_only": {
                            "protein": round(day1_meal_protein, 1),
                            "carbs": round(day1_meal_carbs, 1),
                            "fat": round(day1_meal_fat, 1),
                            "calories": round(day1_meal_calories),
                        },
                        "snack_contribution": {
                            "protein": f"{max(_snack_protein_floor, protein_deficit_for_snacks - _snack_range_variance)}-{protein_deficit_for_snacks + _snack_range_variance}g",
                            "carbs": snack_flexible_info.get("carbs_range", "15-25g") if snack_flexible_info else "15-25g",
                            "calories": f"~{calorie_dist['snack_calories_reserved']} kcal",
                        },
                        "final_total_estimate": {
                            "protein": f"~{round(day1_meal_protein + protein_deficit_for_snacks - _snack_range_variance)}-{round(day1_meal_protein + protein_deficit_for_snacks + _snack_range_variance)}g",
                            "carbs": f"~{round(day1_meal_carbs + max(0, remaining_carbs_for_snacks - _snack_range_variance))}-{round(day1_meal_carbs + remaining_carbs_for_snacks + 10)}g",
                            "fat": f"~{round(day1_meal_fat)}-{round(day1_meal_fat + 5)}g",
                            "calories": f"~{round(day1_meal_calories + calorie_dist['snack_calories_reserved'] - 30)}-{round(day1_meal_calories + calorie_dist['snack_calories_reserved'] + 30)} kcal",
                        },
                        "message": "✨ Perfect balance for your body recomposition goals!",
                    }
                    state.menu = response_menu
                    state.current_step = "review"
                    sessions[session_id] = state.model_dump()
                    return {
                        "menu": response_menu,
                        "price": total_price,
                        "message": "Your full menu is ready!",
                        "plan": state.plan,
                        "nutrition": {
                            "tmb": tmb,
                            "tdee": tdee,
                            "calorie_target": calorie_target,
                            "protein_needed": daily_protein_target,  # Proteína total necesaria
                            "macros": macros,
                            "totals": {  # Totales de todo el día
                                "protein_total": total_protein,
                                "carbs_total": total_carbs,
                                "fat_total": total_fat,
                                "calories_total": total_calories,
                            },
                            "achieved": {  # What the meal plan actually provides (Day 1)
                                "protein": achieved_protein,
                                "carbs": achieved_carbs,
                                "fat": achieved_fat,
                                "calories": achieved_calories
                            },
                            "deficit": deficit,
                        },
                        "snack_recommendations": snack_recommendations,
                        "snack_flexible": snack_flexible_info,
                        "snack_message": snack_message,
                        "plan_validation": plan_validation,
                        "daily_summary": daily_summary,
                        "current_step": state.current_step,
                    }
                else:
                    state.menu = response_menu
                    state.current_step = "review"
                    sessions[session_id] = state.model_dump()
                    return {
                        "menu": response_menu,
                        "price": total_price,
                        "message": "Your menu is ready!",
                        "plan": state.plan,
                        "nutrition": {
                            "tmb": tmb,
                            "tdee": tdee,
                            "calorie_target": calorie_target,
                            "protein_needed": daily_protein_target,  # Solo mostrar proteína necesaria
                            "achieved": {  # What the meal plan actually provides (Day 1)
                                "protein": achieved_protein,
                                "carbs": achieved_carbs,
                                "fat": achieved_fat,
                                "calories": achieved_calories
                            },
                            "deficit": deficit,
                        },
                        "snack_recommendations": snack_recommendations,
                        "snack_flexible": snack_flexible_info,
                        "snack_message": snack_message,
                        "plan_validation": plan_validation,
                        "current_step": state.current_step,
                    }
            except Exception as e:
                tb = traceback.format_exc()
                print(f"[ERROR] menu generation failed for session {session_id}:\n{tb}")
                return JSONResponse(
                    status_code=500,
                    content={"error": "internal_server_error", "detail": str(e), "trace": tb},
                )

    else:
        step_to_render_name = "start"

    state.current_step = step_to_render_name
    sessions[session_id] = state.model_dump()
    return get_form_fields(state.current_step, state)

# --- Additional endpoints (templates, scheduling, feedback, orders) ---

@app.get("/health")
@app.head("/health")
async def health_check():
    """
    Lightweight health check endpoint for uptime monitoring.

    Returns a simple JSON response indicating the service is alive.
    This endpoint is optimized for fast response times and is used by
    external monitoring services like UptimeRobot to keep the Render.com
    free tier instance awake.

    Returns:
        dict: Status information with service name
    """
    return {
        "status": "ok",
        "service": "chontaduro-backend",
        "version": "2.1"
    }

@app.get("/weekly-templates")
async def weekly_templates():
    """
    Return available weekly templates (menus_weekly.json).
    """
    return {"templates": TEMPLATES_DATA or [], "count": len(TEMPLATES_DATA or [])}


@app.get("/generated-schedule")
async def generated_schedule(template_id: str, week: Optional[str] = None):
    """
    Expand a template into a schedule for the requested week.
    Example: /generated-schedule?template_id=plan4-omnivore-week-a&week=2025-W45
    If week not provided, uses the computed week seed based on current date.
    """
    tpl = next((t for t in TEMPLATES_DATA if t.get("id") == template_id), None)
    if not tpl:
        raise HTTPException(status_code=404, detail="Template not found.")
    sch = expand_template_to_schedule(tpl, week)
    return sch


@app.post("/select-template")
async def select_template(request: Request):
    """
    Request body:
      { "session_id": "...", "template_id": "plan4-omnivore-week-a" }
    This attaches a template to the session and computes selected_week according to cutoff rules.
    """
    payload = await request.json()
    sid = payload.get("session_id")
    tid = payload.get("template_id")
    if not sid:
        raise HTTPException(status_code=422, detail="session_id required.")
    if sid not in sessions:
        sessions[sid] = SessionState().model_dump()
    state = SessionState(**sessions[sid])
    tpl = next((t for t in TEMPLATES_DATA if t.get("id") == tid), None)
    if not tpl:
        raise HTTPException(status_code=404, detail="Template not found.")
    state.template_id = tid
    # compute selected_week based on cutoff (Thursday 22:00 UTC)
    now = datetime.datetime.now(datetime.timezone.utc)
    weekday = now.weekday()  # Monday=0
    thursday = now + datetime.timedelta(days=(3 - weekday))
    thursday_cutoff = datetime.datetime.combine(thursday.date(), datetime.time(hour=22, minute=0))
    if now <= thursday_cutoff:
        sunday = thursday + datetime.timedelta(days=(6 - thursday.weekday()))
    else:
        next_thursday = thursday + datetime.timedelta(days=7)
        sunday = next_thursday + datetime.timedelta(days=(6 - next_thursday.weekday()))
    iso = sunday.date().isocalendar()
    state.selected_week = f"{iso[0]}-W{iso[1]}"
    sessions[sid] = state.model_dump()
    sch = expand_template_to_schedule(tpl, state.selected_week)
    return {"ok": True, "selected_week": state.selected_week, "schedule": sch}


@app.post("/place-order")
async def place_order(request: Request):
    """
    Place/confirm the order for the session (saves order time and keeps template & week).
    Body: { "session_id": "..."}
    Returns current session menu & schedule.
    """
    payload = await request.json()
    sid = payload.get("session_id")
    if not sid or sid not in sessions:
        raise HTTPException(status_code=404, detail="Session not found.")
    state = SessionState(**sessions[sid])
    # record order timestamp
    state.order_placed_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
    sessions[sid] = state.model_dump()
    # return schedule or menu summary
    if state.template_id:
        tpl = next((t for t in TEMPLATES_DATA if t.get("id") == state.template_id), None)
        sch = expand_template_to_schedule(tpl, state.selected_week) if tpl else {}
        return {"ok": True, "message": "Order placed", "selected_week": state.selected_week, "schedule": sch, "session": state.model_dump()}
    else:
        return {"ok": True, "message": "Order placed", "session": state.model_dump()}


@app.get("/production-list")
async def production_list(week: Optional[str] = None):
    """
    Aggregate orders for a week across sessions (in-memory).
    If week not provided uses current week seed.
    """
    week_seed = week or week_seed_string_from_date()
    aggregate: Dict[str, int] = {}
    clients = 0
    for sid, sdata in sessions.items():
        st = SessionState(**sdata)
        if not st.template_id:
            continue
        if st.selected_week != week_seed:
            continue
        clients += 1
        tpl = next((t for t in TEMPLATES_DATA if t.get("id") == st.template_id), None)
        if not tpl:
            continue
        sch = expand_template_to_schedule(tpl, st.selected_week)
        # flatten schedule and count occurences
        for day in sch["sequence"]:
            for slot in day["slots"]:
                if not slot:
                    continue
                aggregate[slot] = aggregate.get(slot, 0) + 1
    return {"week": week_seed, "clients": clients, "aggregate": aggregate}


@app.post("/feedback")
async def post_feedback(request: Request):
    """
    Save feedback (rating 1-5 and optional comment) associated with a session/template/week/day.
    Body: { session_id, template_id(optional), week(optional), rating, comment(optional), day_index(optional), slot_index(optional) }
    """
    payload = await request.json()
    fb = {
        "id": f"fb-{len(FEEDBACKS)+1}",
        "session_id": payload.get("session_id"),
        "template_id": payload.get("template_id"),
        "week": payload.get("week"),
        "rating": int(payload.get("rating")) if payload.get("rating") else None,
        "comment": payload.get("comment"),
        "day_index": payload.get("day_index"),
        "slot_index": payload.get("slot_index"),
        "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat()
    }
    FEEDBACKS.append(fb)
    return {"ok": True, "feedback_id": fb["id"]}


# --- Existing endpoints: add-protein, swap-meal, redo-menu (full implementations) ---
@app.post("/add-protein")
async def add_protein(request: Request):
    """
    Payload:
      {
        "session_id": "...",
        "extra_protein_grams": 30,
        // optional: meal_index (int) to apply to that meal; otherwise global add
      }
    """
    try:
        payload = await request.json()
        sid = payload.get("session_id") or payload.get("sessionId")
        extra = payload.get("extra_protein_grams") or payload.get("extraProtein") or 0
        meal_index = payload.get("meal_index")
        try:
            extra = int(extra)
        except Exception:
            return JSONResponse(status_code=422, content={"detail":"extra_protein_grams must be integer."})
        if not sid or sid not in sessions:
            raise HTTPException(status_code=404, detail="Session not found.")
        state = SessionState(**sessions[sid])
        if meal_index is not None:
            try:
                mi = int(meal_index)
            except Exception:
                return JSONResponse(status_code=422, content={"detail":"meal_index must be integer."})
            state.extra_protein_map[mi] = int(state.extra_protein_map.get(mi, 0)) + extra
        else:
            # add global extra and it WILL be distributed in allocation below
            state.extra_protein_grams = int(state.extra_protein_grams or 0) + extra

        # Recompute using the current session menu as base (if present) to avoid regenerating different menu
        # Build base_menu_objs from current state.menu if available, else generate one
        base_menu_objs: List[Meal] = []
        if state.menu:
            for m in state.menu:
                found = next((x for x in MEALS_DATA if str(x.get("name")).strip() == str(m.get("name")).strip()), None)
                if found:
                    base_menu_objs.append(Meal(**found))
                else:
                    # fallback: reconstruct minimal Meal
                    partial = {
                        "name": m.get("name"),
                        "type": m.get("type", "Main Meal"),
                        "ingredients": m.get("ingredients", []),
                        "calories": int(m.get("calories") or 0),
                        "price": float(m.get("price") or 0.0),
                        "image_url": m.get("image_url")
                    }
                    base_menu_objs.append(Meal(**partial))
        else:
            # No existing menu in session — generate a fresh base menu using current state filters
            base_menu_objs = generate_menu(state)
            if not base_menu_objs:
                return {
                    "message": "No se pudo generar un menú con las calorías objetivo. Intenta ajustes en tus preferencias.",
                    "menu": [],
                    "price": 0.0
                }

        # recompute macros/daily protein
        weight_kg = to_kg(state.weight, state.weight_unit) if state.weight else None
        height_cm = to_cm(state.height, state.height_unit) if state.height else None
        tmb = calc_tmb_mifflin(weight_kg, height_cm, state.age, state.sex, state.objective or "")
        tdee = None
        if tmb is not None:
            tdee = round(tmb * get_activity_factor_with_recomp_minimum(state.activity_days_bucket or "0", state.activity_duration_bucket or "<30", state.activity_intensity or "Low", state.objective or ""), 1)
        calorie_target = calc_calorie_target(tdee, state.objective, state.sex or "female") if tdee else None
        macros = calc_macros(calorie_target, state.objective, weight_kg, state.sex)
        daily_protein_target = macros.get("protein_grams", 0)

        menu_with_protein = allocate_protein_to_menu(state, base_menu_objs, daily_protein_target)
        state.menu = menu_with_protein
        sessions[sid] = state.model_dump()
        extra_total = sum(int(v) for v in state.extra_protein_map.values()) + int(state.extra_protein_grams or 0)
        total_price = calculate_price([Meal(**m) if isinstance(m, dict) else m for m in state.menu], extra_total)
        return {"menu": state.menu, "price": total_price, "message": f"Added {extra}g extra protein.", "extra_total": extra_total, "nutrition": {"tmb": tmb, "tdee": tdee, "calorie_target": calorie_target, "macros": macros}}
    except HTTPException:
        raise
    except Exception as e:
        print(f"[ERROR] /add-protein failed: {str(e)}")
        print(traceback.format_exc())
        return JSONResponse(
            status_code=500,
            content={
                "detail": f"Error adding protein: {str(e)}",
                "menu": getattr(state, 'menu', []) if 'state' in locals() else [],
                "price": 0.0
            }
        )


@app.post("/swap-meal")
async def swap_meal(request: Request):
    """
    Swap a single meal in the current menu by name. Recompute allocations,
    but keep other meals unchanged.
    """
    try:
        payload = await request.json()
        sid = payload.get("session_id") or payload.get("sessionId")
        meal_to_swap = payload.get("meal_to_swap") or payload.get("mealToSwap")
        if not sid or sid not in sessions:
            raise HTTPException(status_code=404, detail="Session not found.")
        state = SessionState(**sessions[sid])

        target_idx = next((i for i, m in enumerate(state.menu) if m.get("name") == meal_to_swap), None)
        if target_idx is None:
            return JSONResponse(
                status_code=404,
                content={
                    "detail": "Meal not in current menu.",
                    "menu": state.menu,
                    "price": calculate_price([Meal(**m) if isinstance(m, dict) else m for m in state.menu], 0)
                }
            )

        replaced_meal = state.menu[target_idx]
        replaced_type = (replaced_meal.get("type") or "").lower()

        avail = filter_meals(state.dislikes, state.allergies, state.dietary_restrictions, state.diet_preference)
        current_names = [m.get("name") for m in state.menu]
        potential = [m for m in avail if m.name not in current_names and m.type.lower() == replaced_type]
        if not potential:
            potential = [m for m in avail if m.name not in current_names]
        if not potential:
            restrictions_applied = list(filter(None, [
                state.diet_preference if state.diet_preference and state.diet_preference.lower() != "omnivore" else None,
                *[str(r) for r in (state.dietary_restrictions or []) if r and not str(r).lower().startswith("none")]
            ]))
            return {
                "menu": state.menu,
                "price": calculate_price([Meal(**m) if isinstance(m, dict) else m for m in state.menu], sum(int(v) for v in state.extra_protein_map.values()) + int(state.extra_protein_grams or 0)),
                "message": f"❌ No compatible alternatives found for '{meal_to_swap}'. All available {replaced_type} options conflict with your restrictions.",
                "reason": "no_compatible_meals",
                "restrictions_applied": restrictions_applied,
                "suggestion": "Try regenerating the full menu or adjusting your restrictions."
            }

        new_meal = random.choice(potential)

        # Standard pricing: Breakfast = $11, Main Meal = $15
        if replaced_type == "breakfast":
            new_meal.price = 11.0
        elif replaced_type in ["lunch", "dinner", "main meal"]:
            new_meal.price = 15.0


        # Build base_menu_objs from current state.menu
        base_menu_objs: List[Meal] = []
        for m in state.menu:
            found = next((x for x in MEALS_DATA if str(x.get("name")).strip() == str(m.get("name")).strip()), None)
            if found:
                base_menu_objs.append(Meal(**found))
            else:
                partial = {
                    "name": m.get("name"),
                    "type": m.get("type", "Main Meal"),
                    "ingredients": m.get("ingredients", []),
                    "calories": int(m.get("calories") or 0),
                    "price": float(m.get("price") or 0.0),
                    "image_url": m.get("image_url")
                }
                base_menu_objs.append(Meal(**partial))

        if target_idx < len(base_menu_objs):
            base_menu_objs[target_idx] = new_meal
        else:
            base_menu_objs.append(new_meal)

        # Recompute macros/daily proteins
        weight_kg = to_kg(state.weight, state.weight_unit) if state.weight else None
        height_cm = to_cm(state.height, state.height_unit) if state.height else None
        tmb = calc_tmb_mifflin(weight_kg, height_cm, state.age, state.sex, state.objective or "")
        tdee = None
        if tmb is not None:
            tdee = round(tmb * get_activity_factor_with_recomp_minimum(state.activity_days_bucket or "0", state.activity_duration_bucket or "<30", state.activity_intensity or "Low", state.objective or ""), 1)
        calorie_target = calc_calorie_target(tdee, state.objective, state.sex or "female") if tdee else None
        macros = calc_macros(calorie_target, state.objective, weight_kg, state.sex)
        daily_protein_target = macros.get("protein_grams", 0)

        menu_with_protein = allocate_protein_to_menu(state, base_menu_objs, daily_protein_target)
        state.menu = menu_with_protein
        sessions[sid] = state.model_dump()

        # Cálculo de precio total con lógica de envío gratis
        precio_menu = sum(m.get("price", 0.0) for m in state.menu)
        envio = 0.0 if precio_menu >= 100.0 else 10.0  # Envío gratis si precio total supera $100
        total_price = precio_menu + envio
        return {"menu": state.menu, "price": total_price, "plan": state.plan, "message": f"Swapped '{meal_to_swap}' -> '{new_meal.name}'.", "nutrition": {"tmb": tmb, "tdee": tdee, "calorie_target": calorie_target, "macros": macros}}
    except HTTPException:
        raise
    except Exception as e:
        print(f"[ERROR] /swap-meal failed: {str(e)}")
        print(traceback.format_exc())
        return JSONResponse(
            status_code=500,
            content={
                "detail": f"Error swapping meal: {str(e)}",
                "menu": getattr(state, 'menu', []) if 'state' in locals() else [],
                "price": 0.0
            }
        )

@app.post("/validate-menu")
async def validate_menu(request: Request):
    payload = await request.json()
    session_id = payload.get("session_id")
    if not session_id or session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found.")
    state = SessionState(**sessions[session_id])
    weight_kg = to_kg(state.weight, state.weight_unit) if state.weight else None
    height_cm = to_cm(state.height, state.height_unit) if state.height else None
    tmb = calc_tmb_mifflin(weight_kg, height_cm, state.age, state.sex, state.objective or "")
    tdee = round(tmb * get_activity_factor_with_recomp_minimum(state.activity_days_bucket, state.activity_duration_bucket, state.activity_intensity, state.objective or ""), 2) if tmb else None
    calorie_target = calc_calorie_target(tdee, state.objective, state.sex or "female") if tdee else None
    menu_objs = generate_menu(state)
    menu_dicts = [m.model_dump() if hasattr(m, "model_dump") else dict(m) for m in menu_objs]
    return {"menu": menu_dicts, "calorie_target": calorie_target, "details": {"tmb": tmb, "tdee": tdee}}


@app.post("/redo-menu")
async def redo_menu(request: Request):
    payload = await request.json()
    sid = payload.get("session_id") or payload.get("sessionId")
    if not sid or sid not in sessions:
        raise HTTPException(status_code=404, detail="Session not found.")
    state = SessionState(**sessions[sid])
    menu_objs = generate_menu(state)
    if not menu_objs:
        return {"message":"Could not generate a menu with current filters."}
    weight_kg = to_kg(state.weight, state.weight_unit) if state.weight else None
    height_cm = to_cm(state.height, state.height_unit) if state.height else None
    tmb = calc_tmb_mifflin(weight_kg, height_cm, state.age, state.sex, state.objective or "")
    tdee = None
    if tmb is not None:
        tdee = round(tmb * get_activity_factor_with_recomp_minimum(state.activity_days_bucket or "0", state.activity_duration_bucket or "<30", state.activity_intensity or "Low", state.objective or ""), 1)
    calorie_target = calc_calorie_target(tdee, state.objective, state.sex or "female") if tdee else None
    macros = calc_macros(calorie_target, state.objective, weight_kg, state.sex)
    daily_protein_target = macros.get("protein_grams", 0)
    state.menu = allocate_protein_to_menu(state, menu_objs, daily_protein_target)
    state.extra_protein_grams = 0
    state.extra_protein_map = {}
    sessions[sid] = state.model_dump()
    total_price = calculate_price([Meal(**m) if isinstance(m, dict) else m for m in state.menu], 0)
    return {"menu": state.menu, "price": total_price, "plan": state.plan, "message":"Full menu regenerated.", "nutrition": {"tmb": tmb, "tdee": tdee, "calorie_target": calorie_target, "macros": macros}}
# --- RUTAS RELACIONADAS CON STRIPE ---

@app.post("/calculate-total")
def calculate_total(order: Order):
    """Calculate totals including Washington state tax (10.25%)."""
    return _compute_order_totals(order)


@app.post("/register-or-authenticate")
def register_or_authenticate(payload: RegisterOrAuthRequest):
    full_name = payload.full_name.strip()
    email = str(payload.email).strip().lower()
    password = payload.password

    db = SessionLocal()
    try:
        existing_user = db.query(User).filter(User.email == email).first()
        if existing_user:
            if not User.verify_password(password, existing_user.hashed_password):
                raise HTTPException(status_code=401, detail="Invalid credentials.")
            return {
                "ok": True,
                "status": "authenticated",
                "user": {
                    "id": existing_user.id,
                    "name": existing_user.name,
                    "email": existing_user.email,
                },
            }

        hashed_password = User.hash_password(password)
        new_user = User(
            name=full_name,
            email=email,
            hashed_password=hashed_password,
            creation_date=datetime.datetime.now(datetime.timezone.utc),
        )
        db.add(new_user)
        db.commit()
        db.refresh(new_user)
        return {
            "ok": True,
            "status": "registered",
            "user": {
                "id": new_user.id,
                "name": new_user.name,
                "email": new_user.email,
            },
        }
    finally:
        db.close()


@app.post("/order-summary")
def order_summary(payload: OrderSummaryRequest):
    order = _build_order_from_session(payload.session_id)
    totals = _compute_order_totals(order)
    return {
        "ok": True,
        "session_id": payload.session_id,
        "items_count": len(order.items),
        **totals,
        "zelle": {
            "name": ZELLE_PAYEE_NAME,
            "email": ZELLE_PAYEE_EMAIL,
            "phone": ZELLE_PAYEE_PHONE,
        },
    }

@app.post("/create-checkout-session")
def create_checkout_session(payload: CheckoutSessionRequest):
    """
    Create Stripe checkout session after user has already registered/authenticated.
    """
    order = payload.order
    email = str(payload.email)
    name = payload.name
    password = payload.password
    session_id = payload.session_id
    allergies_selected = [str(a).strip().lower() for a in (payload.allergies_selected or []) if str(a).strip()]
    allergies_other_note = (payload.allergies_other_note or "").strip()

    if session_id and session_id in sessions:
        state = SessionState(**sessions[session_id])
        if not allergies_selected:
            allergies_selected = [str(a).strip().lower() for a in (state.allergies or []) if str(a).strip()]
        if not allergies_other_note:
            allergies_other_note = (state.allergy_note or "").strip()

    if not order:
        if not session_id:
            raise HTTPException(status_code=422, detail="Either order or session_id is required.")
        order = _build_order_from_session(session_id)

    totals = _compute_order_totals(order)

    # Create a database session
    db = SessionLocal()
    try:
        # Check if the user already exists in the database
        user = db.query(User).filter(User.email == email).first()

        if not user:  # Fallback for clients not using /register-or-authenticate
            if not name or not password:  # Ensure name and password are provided
                raise HTTPException(
                    status_code=400,
                    detail="Please provide your name and a password to register before proceeding."
                )
            # Register the user in the database
            hashed_password = User.hash_password(password)
            user = User(
                name=name,
                email=email,
                hashed_password=hashed_password,
                creation_date=datetime.datetime.now(datetime.timezone.utc),
            )
            db.add(user)
            db.commit()
            db.refresh(user)
        elif password and not User.verify_password(password, user.hashed_password):
            raise HTTPException(status_code=401, detail="Invalid credentials.")

        # Initialize the product list for Stripe
        line_items = []

        # Add each product in the order to the Stripe line items
        for item in order.items:
            price = _item_price(item.item_type)
            
            line_items.append({
                "price_data": {
                    "currency": "usd",
                    "product_data": {
                        "name": item.item_type,  # Name of the product from the order
                    },
                    # Convert price to cents
                    "unit_amount": int(price * 100),
                },
                "quantity": item.quantity,  # Quantity of the product
            })

        tax_amount_cents = int(round(totals["tax"] * 100))
        if tax_amount_cents > 0:
            line_items.append({
                "price_data": {
                    "currency": "usd",
                    "product_data": {
                        "name": "Washington State Tax (10.25%)",
                    },
                    "unit_amount": tax_amount_cents,
                },
                "quantity": 1,
            })

        order_id = str(uuid4())
        PENDING_ORDERS[order_id] = {
            "order_id": order_id,
            "email": email,
            "full_name": name or (user.name if user else "Customer"),
            "session_id": session_id,
            "totals": totals,
            "allergies_selected": allergies_selected,
            "allergies_other_note": allergies_other_note,
            "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }

        # Create the checkout session in Stripe
        session = stripe.checkout.Session.create(
            payment_method_types=["card"],
            line_items=line_items,  # Use the generated list
            mode="payment",
            success_url="https://chontaduro-backend.onrender.com/success",
            cancel_url="https://chontaduro-backend.onrender.com/cancel",
            customer_email=email,
            metadata={
                "order_id": order_id,
                "allergies_selected": ",".join(allergies_selected)[:500],
                "allergies_other_note": allergies_other_note[:500],
                "session_id": (session_id or "")[:120],
            },
        )

        # Return the checkout URL to the client
        return {
            "checkout_url": session.url,
            "order_id": order_id,
            "summary": totals,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()


@app.post("/upload-payment-proof")
async def upload_payment_proof(
    file: UploadFile = File(...),
    session_id: str = Form(...),
    email: str = Form(...),
):
    if not file:
        raise HTTPException(status_code=400, detail="No file uploaded.")
    allowed = {"image/png", "image/jpeg", "image/webp"}
    if file.content_type not in allowed:
        raise HTTPException(status_code=415, detail="Only PNG/JPEG/WEBP screenshots are allowed.")

    ext = ".png"
    if file.filename and "." in file.filename:
        ext = "." + file.filename.rsplit(".", 1)[-1].lower()
    proof_dir = os.path.join("uploads", "payment_proofs")
    os.makedirs(proof_dir, exist_ok=True)
    filename = f"{uuid4().hex}{ext}"
    dest = os.path.join(proof_dir, filename)
    contents = await file.read()
    with open(dest, "wb") as out:
        out.write(contents)

    url = f"/uploads/payment_proofs/{filename}"
    return {
        "ok": True,
        "session_id": session_id,
        "email": email,
        "payment_proof_url": url,
    }


@app.post("/confirm-zelle-payment")
def confirm_zelle_payment(payload: ZelleConfirmRequest):
    order = _build_order_from_session(payload.session_id)
    totals = _compute_order_totals(order)

    sent = _send_confirmation_email(
        to_email=str(payload.email),
        full_name=payload.full_name,
        order_summary=totals,
        payment_method="Zelle",
        payment_reference=payload.payment_proof_url,
    )

    return {
        "ok": True,
        "message": "Payment confirmed. Your order is confirmed and being prepared.",
        "email_sent": sent,
        "summary": totals,
    }


@app.post("/stripe-webhook")
async def stripe_webhook(request: Request):
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")

    try:
        if STRIPE_WEBHOOK_SECRET:
            event = stripe.Webhook.construct_event(payload, sig_header, STRIPE_WEBHOOK_SECRET)
        else:
            event = json.loads(payload.decode("utf-8"))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid webhook payload: {str(e)}")

    if event.get("type") == "checkout.session.completed":
        session_obj = event.get("data", {}).get("object", {})
        metadata = session_obj.get("metadata", {}) or {}
        order_id = metadata.get("order_id")
        pending = PENDING_ORDERS.get(order_id)
        if pending:
            _send_confirmation_email(
                to_email=pending.get("email", ""),
                full_name=pending.get("full_name", "Customer"),
                order_summary=pending.get("totals", {}),
                payment_method="Card (Stripe)",
                payment_reference=session_obj.get("id"),
            )
            PENDING_ORDERS.pop(order_id, None)

    return {"received": True}
    
@app.post("/register")
async def register_user(payload: RegisterRequest):
    """
    Register a new user upon finalizing the order with their name, email, and password.
    """
    name = payload.name
    email = str(payload.email)
    password = payload.password

    # Create a database session
    db = SessionLocal()
    try:
        # Check if the email already exists in the database
        existing_user = db.query(User).filter(User.email == email).first()
        if existing_user:
            raise HTTPException(status_code=400, detail="A user with this email already exists.")

        # Create a new user and hash their password
        hashed_password = User.hash_password(password)
        new_user = User(
            name=name,
            email=email,
            hashed_password=hashed_password,
            creation_date=datetime.datetime.now(datetime.timezone.utc),
        )
        
        # Save the user to the database
        db.add(new_user)
        db.commit()
        db.refresh(new_user)

        # Return JSON-serializable data
        return {
            "message": "User registered successfully",
            "user": {
                "id": new_user.id,
                "name": new_user.name,
                "email": new_user.email,
                "creation_date": new_user.creation_date.isoformat() if new_user.creation_date else None
            }
        }
    finally:
        db.close()   


def _remaining_lockout_seconds(lockout_until: datetime.datetime, now: datetime.datetime) -> int:
    return max(1, int((lockout_until - now).total_seconds()))


@app.post("/login")
async def login_user(payload: LoginRequest):
    """
    Authenticate user credentials and apply temporary lockout after repeated failures.
    """
    email = str(payload.email).strip().lower()
    password = payload.password
    now = datetime.datetime.now(datetime.timezone.utc)

    attempt_info = LOGIN_ATTEMPTS.get(email, {"failed_attempts": 0, "lockout_until": None})
    lockout_until = attempt_info.get("lockout_until")

    if isinstance(lockout_until, datetime.datetime) and now < lockout_until:
        retry_after = _remaining_lockout_seconds(lockout_until, now)
        raise HTTPException(
            status_code=429,
            detail=f"Account temporarily locked. Try again in {retry_after} seconds."
        )

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == email).first()
        is_valid = bool(user and User.verify_password(password, user.hashed_password))

        if not is_valid:
            failed_attempts = int(attempt_info.get("failed_attempts") or 0) + 1
            lockout = None

            if failed_attempts >= MAX_FAILED_LOGIN_ATTEMPTS:
                lockout = now + datetime.timedelta(minutes=LOGIN_LOCKOUT_MINUTES)
                LOGIN_ATTEMPTS[email] = {
                    "failed_attempts": 0,
                    "lockout_until": lockout,
                }
                retry_after = _remaining_lockout_seconds(lockout, now)
                raise HTTPException(
                    status_code=429,
                    detail=f"Too many failed login attempts. Try again in {retry_after} seconds."
                )

            LOGIN_ATTEMPTS[email] = {
                "failed_attempts": failed_attempts,
                "lockout_until": None,
            }
            raise HTTPException(status_code=401, detail="Invalid credentials.")

        LOGIN_ATTEMPTS.pop(email, None)
        return {
            "message": "Login successful",
            "user": {
                "id": user.id,
                "name": user.name,
                "email": user.email,
            },
        }
    finally:
        db.close()

def calculate_price(menu: List[Meal], extra_protein: int) -> float:
    """
    Calculate total price for menu.
    Standard prices: Breakfast = $11, Main Meal = $15
    """
    base = 0.0
    for m in menu:
        meal_type = ""
        if isinstance(m, dict):
            meal_type = str(m.get("type", "")).lower()
        elif hasattr(m, "type"):
            meal_type = str(m.type).lower()
        
        # Standard pricing
        if "breakfast" in meal_type:
            base += 11.0
        else:  # main meal, lunch, dinner
            base += 15.0
    
    # Extra protein cost (if applicable)
    prot_cost = (extra_protein or 0) * 1.0
    return round(base + prot_cost, 2)


def _item_price(item_type: str) -> int:
    t = (item_type or "").strip().lower()
    if t == "main_menu":
        return 15
    if t == "breakfast":
        return 11
    raise HTTPException(status_code=400, detail="Invalid item type")


def _build_order_from_session(session_id: str) -> Order:
    if not session_id or session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found.")
    state = SessionState(**sessions[session_id])
    if not state.menu:
        raise HTTPException(status_code=422, detail="No generated menu found in session.")

    items: List[OrderItem] = []
    for meal in state.menu:
        meal_type = str((meal.get("type") if isinstance(meal, dict) else getattr(meal, "type", "")) or "").lower()
        item_type = "breakfast" if "breakfast" in meal_type else "main_menu"
        items.append(OrderItem(item_type=item_type, quantity=1, less_protein=False))
    return Order(items=items)


def _compute_order_totals(order: Order) -> Dict[str, float]:
    subtotal = 0.0
    for item in order.items:
        subtotal += float(_item_price(item.item_type) * int(item.quantity))
    tax = round(subtotal * WA_TAX_RATE, 2)
    total = round(subtotal + tax, 2)
    return {
        "subtotal": round(subtotal, 2),
        "tax": tax,
        "tax_rate": WA_TAX_RATE,
        "total": total,
    }


def _send_confirmation_email(to_email: str, full_name: str, order_summary: Dict[str, Any], payment_method: str, payment_reference: Optional[str] = None) -> bool:
    if not (SMTP_HOST and SMTP_FROM_EMAIL):
        print("[EMAIL] SMTP not configured. Skipping confirmation email.")
        return False

    subject = "Your Chontaduro order is confirmed ✅"
    body = (
        f"Hi {full_name},\n\n"
        "Thank you for your order. Your order is confirmed and is being prepared.\n\n"
        f"Payment method: {payment_method}\n"
        f"Subtotal: ${order_summary.get('subtotal', 0):.2f}\n"
        f"Washington tax (10.25%): ${order_summary.get('tax', 0):.2f}\n"
        f"Total: ${order_summary.get('total', 0):.2f}\n"
    )
    if payment_reference:
        body += f"Payment reference: {payment_reference}\n"
    body += "\nWe appreciate your trust in Chontaduro!\n"

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = SMTP_FROM_EMAIL
    msg["To"] = to_email
    msg.set_content(body)

    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.starttls()
            if SMTP_USERNAME and SMTP_PASSWORD:
                server.login(SMTP_USERNAME, SMTP_PASSWORD)
            server.send_message(msg)
        return True
    except Exception as exc:
        print(f"[EMAIL] Failed to send confirmation: {exc}")
        return False


# Note: At startup we already loaded meals and templates.
# If you add or edit menus_weekly.json, call load_templates() or restart the server.

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)# Servicio Stripe - validación