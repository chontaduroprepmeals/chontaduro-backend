import os
os.makedirs("uploads", exist_ok=True)

# main.py
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
from pydantic import BaseModel, Field
from upload_image import register_upload_routes
from fastapi.staticfiles import StaticFiles
import random, json, traceback, datetime, math, hashlib
from typing import List, Dict, Any, Optional
from delivery_allowed_api import register_delivery_routes
from fastapi.responses import JSONResponse
import stripe
from dotenv import load_dotenv

# Cargar variables de entorno
load_dotenv()

# Configurar la clave de Stripe
stripe.api_key = os.getenv("STRIPE_SECRET_KEY")

# Prueba temporal para asegurar que Stripe API Key esté configurada
print("Stripe API Key:", os.getenv("STRIPE_SECRET_KEY"))

app = FastAPI()


# --- CORS ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
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

# Serve frontend
@app.get("/", response_class=HTMLResponse)
async def serve_frontend():
    return FileResponse("index.html")

# Manejo de solicitudes HEAD en la raíz
@app.head("/")
async def handle_head_request():
    return HTMLResponse(content="", status_code=200)

# Manejo de solicitudes GET explícito en la raíz
@app.get("/")
async def handle_get_request_override():
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

# --- FLOW STEPS ---
STEPS = {
    "start": "pick_plan",
    "pick_plan": "objective",
    "objective": "personal_info",
    "personal_info": "restrictions",
    "restrictions": "duration",
    "duration": "dislikes",
    "dislikes": "review",
    "review": "review"
}


# --- MODELS ---
class Meal(BaseModel):
    name: str
    type: str
    ingredients: List[str] = Field(default_factory=list)
    calories: int = 0
    price: float = 0.0
    image_url: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    model_config = {"extra": "ignore"}


class SessionState(BaseModel):
    plan: Optional[int] = None
    days: Optional[int] = None
    dislikes: List[str] = Field(default_factory=list)
    allergies: List[str] = Field(default_factory=list)
    dietary_restrictions: List[str] = Field(default_factory=list)
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

def compute_activity_factor(days_bucket: str, duration_bucket: str, intensity: str) -> float:
    days_map = {"0":1.2, "1-2":1.3, "3-4":1.45, "5-7":1.6}
    base = days_map.get(str(days_bucket), 1.2)
    dur_map = {"<30":0.0, "30-60":0.05, "60-120":0.08}
    dur = dur_map.get(str(duration_bucket), 0.0)
    int_map = {"low":0.0, "moderate":0.03, "high":0.06}
    iadj = int_map.get((intensity or "").lower(), 0.0)
    return round(min(base + dur + iadj, 1.9), 3)

def calc_tmb_mifflin(weight_kg: float, height_cm: float, age: int, sex: str) -> Optional[float]:
    if None in (weight_kg, height_cm, age, sex):
        return None
    sex = (sex or "").lower()
    if sex in ["male", "m", "man"]:
        return round((10*weight_kg)+(6.25*height_cm)-(5*age)+5, 1)
    return round((10*weight_kg)+(6.25*height_cm)-(5*age)-161, 1)

def calc_calorie_target(tdee: float, objective: str) -> Optional[float]:
    if tdee is None:
        return None
    obj = (objective or "").lower()
    if obj in ["lose fat", "lose", "fat"]:
        # Reduce por un 20% del TDEE (pérdida de grasa más sostenible)
        return round(tdee * 0.80)
    if obj in ["gain muscle", "gain", "muscle"]:
        # Incrementa un 15% para ganancia muscular
        return round(tdee * 1.15)
    # Default: mantener el peso
    return round(tdee)

def calc_macros(calories: int, objective: str, weight_kg: Optional[float]) -> Dict[str, Any]:
    if calories is None:
        return {}
    obj = (objective or "").lower()
    if obj in ["lose fat", "lose", "fat"]:
        pct_protein, pct_fat, pct_carb = 0.30, 0.25, 0.45
        prot_per_kg = 2.0
    elif obj in ["gain muscle", "gain", "muscle"]:
        pct_protein, pct_fat, pct_carb = 0.28, 0.25, 0.47
        prot_per_kg = 1.8
    else:
        pct_protein, pct_fat, pct_carb = 0.25, 0.30, 0.45
        prot_per_kg = 1.6

    if weight_kg:
        protein_grams = round(prot_per_kg * weight_kg)
        protein_grams = max(protein_grams, round((calories * pct_protein) / 4))
        protein_grams = min(protein_grams, round(2.2 * weight_kg))
    else:
        protein_grams = round((calories * pct_protein) / 4)

    protein_cal = protein_grams * 4
    fat_cal = round(calories * pct_fat)
    fat_grams = round(fat_cal / 9)
    remaining_cal = calories - (protein_cal + fat_cal)
    carbs_grams = round(max(0, remaining_cal) / 4) if remaining_cal > 0 else 0

    return {"calories": int(calories), "protein_grams": int(protein_grams), "fat_grams": int(fat_grams), "carbs_grams": int(carbs_grams), "pct_protein": pct_protein, "pct_fat": pct_fat, "pct_carbs": pct_carb}


# --- DIET / RESTRICTION KEYWORDS (expanded vegetables list) ---
MEAT_KEYWORDS = {"chicken","beef","pork","turkey","lamb","bacon","ham","steak"}
FISH_KEYWORDS = {"salmon","shrimp","fish","tuna","trout","cod","shellfish","prawns"}
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
    if d == "vegan":
        forbidden = MEAT_KEYWORDS | FISH_KEYWORDS | DAIRY_KEYWORDS | EGG_KEYWORDS | {"honey"}
        return not any(any(fk in ing for fk in forbidden) for ing in ings)
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
    d = (dt or datetime.datetime.utcnow()).date()
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
    Dynamically distribute protein across meals, respecting daily protein needs and limits (maximum 35-40g per meal).
    """
    if not menu:
        return []

    plan_map = {1: (1, 0), 2: (2, 0), 3: (1, 1), 4: (2, 1)}
    num_main, num_break = plan_map.get(state.plan, (1, 0))
    meals_per_day = num_main + num_break
    days = state.days or max(1, len(menu) // max(1, meals_per_day))
    total_meals = min(len(menu), days * meals_per_day) if meals_per_day > 0 else len(menu)
    # Calcular las calorías totales de los platos disponibles
    total_calories = sum(getattr(m, "calories", 0) for m in menu)
    if total_calories == 0:  # Evitar división por cero
        total_calories = 1  # Fallback seguro

    # Calcular calorías objetivo por comida
    target_calories_per_meal = calorie_target // max(total_meals, 1) if calorie_target and total_meals > 0 else calorie_target or 0
    if target_calories_per_meal == 0:  # Asignar valor predeterminado si no se calcula objetivo
        target_calories_per_meal = 300  # Valor genérico para estabilidad

    # Debugging
    print(f"[DEBUG] Total calories in menu: {total_calories} kcal")
    print(f"[DEBUG] Target calories per meal: {target_calories_per_meal} kcal")
    # Total daily protein target
    daily_protein_target = int(macros_daily_protein or 0)
    if daily_protein_target == 0:
        daily_protein_target = 40  # Default fallback for safety

    # Log target for debugging
    print("[DEBUG] Daily protein target:", daily_protein_target, "g")
    # Debugging for target calculations
    print(f"[DEBUG] Total calories in menu: {total_calories} kcal")
    print(f"[DEBUG] Target calories per meal: {target_calories_per_meal} kcal")

    out = []
    idx = 0
    for day in range(days):
        for m_idx_in_day in range(meals_per_day):
            if idx >= len(menu):
                break
            meal_obj = menu[idx]
            meal_dict = meal_obj.model_dump() if hasattr(meal_obj, "model_dump") else dict(meal_obj)

            protein_per_meal = total_daily_protein // total_meals
            calories_per_meal = calorie_target // total_meals

            # Generar dinámica
            meal_with_macros = process_meal_data(
                meal=menu[idx],
                protein=protein_per_meal,
                calories=calories_per_meal
            )

            meal_dict["provided_protein"] = meal_with_macros.protein
            meal_dict["calories"] = meal_with_macros.calories

            # Dynamically allocate protein based on daily needs
            # dynamic_protein = daily_protein_target // total_meals
            # leftover_protein = daily_protein_target % total_meals
            # meal_dict["provided_protein"] = dynamic_protein + (
            #     1 if idx < leftover_protein else 0
            # )

            protein_per_meal = daily_protein_target // total_meals
            calories_per_meal = target_calories_per_meal

            # Generar dinámica: proteínas, calorías, grasas, carbohidratos
            meal_with_macros = process_meal_data(
                meal=meal_obj,
                protein=protein_per_meal,
                calories=calories_per_meal,
                fat_ratio=0.25,  # 25% del objetivo calórico para grasas
                carb_ratio=0.50  # 50% del objetivo calórico para carbohidratos
            )

            # Asignar dinámicamente los valores generados
            meal_dict["provided_protein"] = meal_with_macros.protein
            meal_dict["calories"] = meal_with_macros.calories
            meal_dict["fat_assigned"] = meal_with_macros.fat
            meal_dict["carbs_assigned"] = meal_with_macros.carbs

            # Respect the upper limit of 35-40 g, adjust only if higher
            if meal_dict["provided_protein"] > 40:  # Cap maximum
                meal_dict["provided_protein"] = 40
            elif meal_dict["provided_protein"] < 20:  # Allow small adjustments for low needs
                meal_dict["provided_protein"] = 20  


            # Adjust calories dynamically
            original_calories = getattr(meal_obj, "calories", 0)  # Acceso seguro a calorías

            # Calcular calorías objetivo por comida
            target_calories_per_meal = calorie_target // max(total_meals, 1) if calorie_target and total_meals > 0 else calorie_target or 0
            frac_calories = target_calories_per_meal / max(total_calories, 1)  # Evitar división por cero
            adjusted_calories = int(original_calories * frac_calories)

            # Validar extremos de calorías ajustadas (máximo y mínimo)
            adjusted_calories = max(
                100,  # Asignar mínimo de 100 calorías
                min(
                    800,  # Asignar máximo de 800 calorías
                    adjusted_calories  # Mantener el valor calculado si está dentro del rango válido
                )
            )

            # Debugging: valores finales de calorías ajustadas
            meal_dict["calories"] = adjusted_calories
            print(f"[DEBUG] Day {day + 1}, Meal {idx + 1}: {meal_dict.get('name', 'Unnamed Meal')}")
            print(f"  - Dynamic Protein: {meal_dict['provided_protein']} g")
            print(f"  - Adjusted Calories: {meal_dict['calories']} kcal")
            print(f"  - Grasas asignadas: {meal_dict['fat_assigned']} g")
            print(f"  - Carbohidratos asignados: {meal_dict['carbs_assigned']} g")

            # Add meal to output
            meal_dict["day_index"] = day
            meal_dict["meal_index"] = idx
            out.append(meal_dict)
            idx += 1

    return out


# Keep original generate_menu as fallback for non-template flows
def generate_menu(state: SessionState) -> List[Meal]:
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
    menu = []
    for _ in range(state.days):
        day_items = []
        for _ in range(num_break):
            if breakfasts: day_items.append(random.choice(breakfasts))
        for _ in range(num_main):
            if mains: day_items.append(random.choice(mains))
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
    # Calcular calorías de proteína
    protein_calories = protein * 4  # 1 g de proteína = 4 kcal

    # Calcular calorías y gramos de grasa
    fat_calories = calories * fat_ratio
    fat_grams = fat_calories / 9  # 1 g de grasa = 9 kcal

    # Calcular calorías y gramos de carbohidratos
    carb_calories = calories - (protein_calories + fat_calories)
    carb_grams = carb_calories / 4  # 1 g de carb = 4 kcal

    # Asegurar que no haya valores negativos
    fat_grams = max(0, round(fat_grams))
    carb_grams = max(0, round(carb_grams))

    # Regresar el objeto Meal con valores dinámicos
    meal.calories = calories
    meal.protein = protein
    meal.fat = fat_grams
    meal.carbs = carb_grams
    return meal

# --- UI form definitions (unchanged) ---
def get_form_fields(step_name: str, state: Optional[SessionState] = None):
    if step_name == "pick_plan":
        return {"question":"Which plan do you want?","fields":[{"name":"Plan","type":"select","options":["Plan 1: 1 main meal per day","Plan 2: 2 main meals per day","Plan 3: 1 main meal + 1 breakfast","Plan 4: 2 main meals + 1 breakfast (full day)"], "required": True}],"current_step":"pick_plan"}
    if step_name == "objective":
        return {"question":"What is your main goal?","fields":[{"name":"Objective","type":"select","options":["Lose Fat","Gain Muscle","Maintain Shape"], "required": True}],"current_step":"objective"}
    if step_name == "personal_info":
        return {
            "question":"Tell us your personal data:",
            "fields":[
                {"name":"Diet Preference","type":"select","options":["Omnivore","Vegetarian","Vegan","Pescatarian","Few restrictions"], "unit":"Choose the option that best describes your overall diet.", "required": True},
                {"name":"Food Allergies","type":"multiselect","options":["None - no allergies","Egg-free","Nut-free","Seafood-free","Dairy-free","Soy-free","Gluten-free"], "unit":"Medical allergies - select all that apply", "required": True},
                {"name":"Weight Unit","type":"select","options":["kg","lbs"], "required": True},
                {"name":"Weight","type":"number","placeholder":"e.g. 70","unit":"kg or lbs", "required": True},
                {"name":"Height Unit","type":"select","options":["cm","in"], "required": True},
                {"name":"Height","type":"number","placeholder":"e.g. 175","unit":"cm or in", "required": True},
                {"name":"Age","type":"number","placeholder":"e.g. 30", "required": True},
                {"name":"Sex","type":"select","options":["Male","Female"], "required": True},
                {"name":"Days per week","type":"select","options":["0","1-2","3-4","5-7"], "unit":"How many days do you exercise on average?", "required": True},
                {"name":"Avg session duration","type":"select","options":["<30","30-60","60-120"], "unit":"Typical session length (minutes)", "required": True},
                {"name":"Intensity","type":"select","options":["Low","Moderate","High"], "unit":"Select intensity (Low/Moderate/High).", "required": True},
                {"name":"Body Fat % (optional)","type":"number","placeholder":"e.g. 18","required": False}
            ],
            "current_step":"personal_info"
        }
    if step_name == "restrictions":
        return {"question":"Please select any dietary restrictions (preferences):","fields":[{"name":"Dietary Restrictions","type":"multiselect","options":["None - no special restrictions","No pork","No beef","No chicken / poultry","No seafood / shellfish","Gluten-free","Lactose-free / Dairy-free","Soy-free","Corn-free","Sesame-free"],"unit":"Personal or cultural preferences (not medical)"}],"current_step":"restrictions"}
    if step_name == "duration":
        return {"question":"For how many days do you want this plan?","fields":[{"name":"Days","type":"number","min":1,"max":30,"placeholder":"e.g. 7", "required": True}],"current_step":"duration"}
    if step_name == "dislikes":
        return {"question":"Select ingredients you DON'T like:","fields":[{"name":"Dislikes","type":"multiselect","options":["None - I like everything","Vegetables","Oats","Berries","Milk","Chicken","Rice","Broccoli","Salmon","Lettuce","Avocado","Tofu","Carrots","Beef","Pork","Shellfish","Banana"], "unit":"Select foods you simply dislike (taste).", "required": True}],"current_step":"dislikes"}
    if step_name == "review":
        if not state:
            return {"question":"State error. Start again.","current_step":"review"}
        summary = (f"Plan: {state.plan} for {state.days} days\nDiet: {state.diet_preference or 'N/A'}\nDietary restrictions: {', '.join(state.dietary_restrictions) if state.dietary_restrictions else 'None'}\nAllergies: {', '.join(state.allergies) if state.allergies else 'None'}\nDislikes: {', '.join(state.dislikes) if state.dislikes else 'None'}\nWeight: {state.weight or 'N/A'} {state.weight_unit}\nHeight: {state.height or 'N/A'} {state.height_unit}\nAge: {state.age or 'N/A'}\nActivity: {state.activity_days_bucket or 'N/A'} days, {state.activity_duration_bucket or 'N/A'} min, {state.activity_intensity or 'N/A'} intensity\n")
        return {"question": f"Review your info and generate the menu:\n\n{summary}", "fields": [], "current_step":"review"}
    return {"question":"Unknown step. Start again.","current_step":"start"}


# --- ENDPOINTS & FLOW HANDLER (uses new allocation & templates) ---
def normalize_request_payload(payload: Dict[str, Any]) -> NextStepRequest:
    session_id = payload.get("session_id") or payload.get("sessionId") or payload.get("id") or str(random.randint(1000,9999))
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

    elif step_name == "personal_info":
        try:
            if "diet_preference" in answer:
                state.diet_preference = str(answer.get("diet_preference"))
            # Allergies are collected here for everyone
            if "allergies" in answer:
                ag = answer.get("allergies")
                state.allergies = ag if isinstance(ag, list) else [ag]
            if "weight_unit" in answer:
                state.weight_unit = answer.get("weight_unit")
            if "weight" in answer:
                try:
                    state.weight = float(answer.get("weight"))
                except Exception:
                    state.weight = None
            if "height_unit" in answer:
                state.height_unit = answer.get("height_unit")
            if "height" in answer:
                try:
                    state.height = float(answer.get("height"))
                except Exception:
                    state.height = None
            if "age" in answer:
                try:
                    state.age = int(answer.get("age"))
                except Exception:
                    state.age = None
            if "sex" in answer:
                state.sex = answer.get("sex")
            if "activity_days_bucket" in answer:
                state.activity_days_bucket = str(answer.get("activity_days_bucket"))
            if "activity_duration_bucket" in answer:
                state.activity_duration_bucket = str(answer.get("activity_duration_bucket"))
            if "activity_intensity" in answer:
                state.activity_intensity = str(answer.get("activity_intensity"))
            if "body_fat" in answer:
                try:
                    state.body_fat = float(answer.get("body_fat"))
                except Exception:
                    state.body_fat = None

            # Conditional flow: show restrictions only if user chose "Few restrictions"
            dp = (state.diet_preference or "").strip().lower()
            if dp == "few restrictions":
                step_to_render_name = "restrictions"
            else:
                step_to_render_name = "duration"
        except Exception:
            step_to_render_name = "personal_info"

    elif step_name == "restrictions":
        dr = raw_answer.get("Dietary Restrictions") or raw_answer.get("DietaryRestrictions") or answer.get("dietary_restrictions")
        if dr:
            state.dietary_restrictions = dr if isinstance(dr, list) else [dr]
        step_to_render_name = "duration"

    elif step_name == "duration":
        days_val = answer.get("days") or answer.get("Days")
        try:
            if days_val is not None and int(days_val) >= 1:
                state.days = int(days_val)
        except Exception:
            pass
        step_to_render_name = "dislikes"

    elif step_name == "dislikes":
        d = answer.get("dislikes") or answer.get("Dislikes")
        if isinstance(d, list) and any(str(x).lower().startswith("none") or str(x).lower().startswith("i like") for x in d):
            state.dislikes = []
        else:
            state.dislikes = d if isinstance(d, list) else [d] if d else []
        step_to_render_name = "review"


    elif step_name == "review":
            try:
                # Si el usuario seleccionó un template, configúralo y calcula el target
                if "template_id" in answer:
                    state.template_id = answer.get("template_id")

                    # Calcula la semana seleccionada basada en la lógica de corte jueves 22:00
                    now = datetime.datetime.utcnow()
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

                # Genera el menú base (Objetos Meal)
                base_menu_objs = generate_menu(state)

                # Calcula calorías objetivo y macros
                weight_kg = to_kg(state.weight, state.weight_unit) if state.weight else None
                height_cm = to_cm(state.height, state.height_unit) if state.height else None
                tmb = calc_tmb_mifflin(weight_kg, height_cm, state.age, state.sex)
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
                calorie_target = calc_calorie_target(tdee, state.objective) if tdee else None
                macros = calc_macros(calorie_target, state.objective, weight_kg)

                # Ajusta proteína y calorías dinámicamente por comida
                daily_protein_target = macros.get("protein_grams", 0)
                menu_with_protein = allocate_protein_to_menu(state, base_menu_objs, daily_protein_target, calorie_target)

                if not menu_with_protein:  # Validación adicional de seguridad
                    print("[ERROR] Menu with protein is empty, validation failed!")
                    return {
                        "question": "No meals could be allocated with the current settings.",
                        "fields": [],
                        "current_step": state.current_step,
                        "issue": "validation_failed",
                    }

                # **Calcula totales del día**
                total_protein = sum((meal.get("provided_protein", 0) for meal in menu_with_protein))
                total_carbs = sum((meal.get("carbs_assigned", 0) for meal in menu_with_protein))
                total_fat = sum((meal.get("fat_assigned", 0) for meal in menu_with_protein))
                total_calories = sum((getattr(meal, "calories", 0) for meal in menu_with_protein))

                # Print debug information about daily totals
                print("[DEBUG] Daily macronutrient totals:")
                print(f"- Total Protein: {total_protein} g")
                print(f"- Total Carbohydrates: {total_carbs} g")
                print(f"- Total Fats: {total_fat} g")
                print(f"- Total Calories: {total_calories} kcal")

                # Modifica la respuesta según el plan
                response_menu = []
                for meal in menu_with_protein:
                    meal_entry = dict(meal)
                    if state.plan == 4:  # Plan 4: Desglose completo de macronutrientes
                        day_meals = [
                            x
                            for x in menu_with_protein
                            if x.get("day_index") == meal.get("day_index")
                        ]
                        total_cal_day = sum((mm.get("calories", 0) or 0) for mm in day_meals) or 1
                        frac = (getattr(meal, "calories", 0) or 0) / max(total_calories, 1)
                        meal_entry["calories_assigned"] = int(
                            round((calorie_target or 0) * frac)
                        ) if calorie_target else meal.get("calories")
                        meal_entry["protein_assigned"] = int(meal.get("provided_protein", 0))
                        meal_entry["fat_assigned"] = int(
                            round((macros.get("fat_grams", 0) * frac))
                        ) if macros else 0
                        meal_entry["carbs_assigned"] = int(
                            round((macros.get("carbs_grams", 0) * frac))
                        ) if macros else 0

                        # **Ajuste dinámico de calorías** (insertado aquí)
                        original_calories = getattr(meal, "calories", 0)
                        frac_calories = calorie_target / total_calories if total_calories > 0 else 1
                        adjusted_calories = int(original_calories * frac_calories)
                        meal_entry["calories_assigned"] = adjusted_calories

                        # Depuración de calorías ajustadas
                        print(f"[DEBUG] Meal: {meal.get('name', 'Unnamed Meal')} - Adjusted Calories: {adjusted_calories} kcal")

                    else:  # Otros planes: Solo mostrar proteína asignada
                        meal_entry["protein_assigned"] = int(meal.get("provided_protein", 0))

                    response_menu.append(meal_entry)

                # Calcula el precio total
                total_price = calculate_price(
                    [Meal(**m) if isinstance(m, dict) else m for m in response_menu], 0
                )

                # Respuesta basada en el plan seleccionado
                if state.plan == 4:
                    return {
                        "menu": response_menu,
                        "price": total_price,
                        "message": "Your full menu is ready!",
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
                        },
                        "current_step": state.current_step,
                    }
                else:
                    return {
                        "menu": response_menu,
                        "price": total_price,
                        "message": "Your menu is ready!",
                        "nutrition": {
                            "tmb": tmb,
                            "tdee": tdee,
                            "calorie_target": calorie_target,
                            "protein_needed": daily_protein_target,  # Solo mostrar proteína necesaria
                        },
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
async def health():
    """
    Healthcheck simple (200) para pings externos / warmup.
    """
    return JSONResponse({"status": "ok"})

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
    now = datetime.datetime.utcnow()
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
    state.order_placed_at = datetime.datetime.utcnow().isoformat()
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
        "created_at": datetime.datetime.utcnow().isoformat()
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
            # Generamos base menú (Meal objects) usando validación calórica diaria y semanal
            weight_kg = to_kg(state.weight, state.weight_unit) if state.weight else None
            height_cm = to_cm(state.height, state.height_unit) if state.height else None
            tmb = calc_tmb_mifflin(weight_kg, height_cm, state.age, state.sex)
            tdee = round(
                tmb * compute_activity_factor(
                    state.activity_days_bucket or "0",
                    state.activity_duration_bucket or "<30",
                    state.activity_intensity or "Low",
                ),
                1,
            ) if tmb else None
            calorie_target = calc_calorie_target(tdee, state.objective) if tdee else None

            # Generamos el menú semanal verificando que cada día cumpla las calorías objetivo
            weekly_menu = generate_weekly_menu(MEALS_DATA, calorie_target)
            if not weekly_menu:
                return {
                    "message": "No se pudo generar un menú con las calorías objetivo. Intenta ajustes en tus preferencias.",
                }

            # Asigna el menú generado a la sesión actual
            state.menu = weekly_menu
            sessions[session_id] = state.model_dump()

            return {
                "menu": weekly_menu,
                "nutrition": {
                    "tmb": tmb,
                    "tdee": tdee,
                    "calorie_target": calorie_target,
                },
                "current_step": state.current_step,
                "message": "Tu menú se generó correctamente.",
            }

    # recompute macros/daily protein
    weight_kg = to_kg(state.weight, state.weight_unit) if state.weight else None
    height_cm = to_cm(state.height, state.height_unit) if state.height else None
    tmb = calc_tmb_mifflin(weight_kg, height_cm, state.age, state.sex)
    tdee = None
    if tmb is not None:
        tdee = round(tmb * compute_activity_factor(state.activity_days_bucket or "0", state.activity_duration_bucket or "<30", state.activity_intensity or "Low"), 1)
    calorie_target = calc_calorie_target(tdee, state.objective) if tdee else None
    macros = calc_macros(calorie_target, state.objective, weight_kg)
    daily_protein_target = macros.get("protein_grams", 0)

    menu_with_protein = allocate_protein_to_menu(state, base_menu_objs, daily_protein_target)
    state.menu = menu_with_protein
    sessions[sid] = state.model_dump()
    extra_total = sum(int(v) for v in state.extra_protein_map.values()) + int(state.extra_protein_grams or 0)
    total_price = calculate_price([Meal(**m) if isinstance(m, dict) else m for m in state.menu], extra_total)
    return {"menu": state.menu, "price": total_price, "message": f"Added {extra} g extra protein.", "extra_total": extra_total, "nutrition": {"tmb": tmb, "tdee": tdee, "calorie_target": calorie_target, "macros": macros}}


@app.post("/swap-meal")
async def swap_meal(request: Request):
    """
    Swap a single meal in the current menu by name. Recompute allocations,
    but keep other meals unchanged.
    """
    payload = await request.json()
    sid = payload.get("session_id") or payload.get("sessionId")
    meal_to_swap = payload.get("meal_to_swap") or payload.get("mealToSwap")
    if not sid or sid not in sessions:
        raise HTTPException(status_code=404, detail="Session not found.")
    state = SessionState(**sessions[sid])

    target_idx = next((i for i, m in enumerate(state.menu) if m.get("name") == meal_to_swap), None)
    if target_idx is None:
        raise HTTPException(status_code=404, detail="Meal not in current menu.")

    replaced_meal = state.menu[target_idx]
    replaced_type = (replaced_meal.get("type") or "").lower()

    avail = filter_meals(state.dislikes, state.allergies, state.dietary_restrictions, state.diet_preference)
    current_names = [m.get("name") for m in state.menu]
    potential = [m for m in avail if m.name not in current_names and m.type.lower() == replaced_type]
    if not potential:
        potential = [m for m in avail if m.name not in current_names]
    if not potential:
        return {"menu": state.menu, "price": calculate_price([Meal(**m) if isinstance(m, dict) else m for m in state.menu], sum(int(v) for v in state.extra_protein_map.values()) + int(state.extra_protein_grams or 0)), "message": "No replacements available."}

    new_meal = random.choice(potential)

    # Ajustar precio según categoría (replaced_type)
    if replaced_type == "breakfast":
        new_meal.price = 10.0  # Precio fijo para desayunos
    elif replaced_type in ["lunch", "dinner", "main meal"]:
        new_meal.price = 15.0  # Precio fijo para almuerzos/cenas
    

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
    tmb = calc_tmb_mifflin(weight_kg, height_cm, state.age, state.sex)
    tdee = None
    if tmb is not None:
        tdee = round(tmb * compute_activity_factor(state.activity_days_bucket or "0", state.activity_duration_bucket or "<30", state.activity_intensity or "Low"), 1)
    calorie_target = calc_calorie_target(tdee, state.objective) if tdee else None
    macros = calc_macros(calorie_target, state.objective, weight_kg)
    daily_protein_target = macros.get("protein_grams", 0)

    menu_with_protein = allocate_protein_to_menu(state, base_menu_objs, daily_protein_target)
    state.menu = menu_with_protein
    sessions[sid] = state.model_dump()

    # Cálculo de precio total con lógica de envío gratis
    precio_menu = sum(m.get("price", 0.0) for m in state.menu)
    envio = 0.0 if precio_menu >= 100.0 else 10.0  # Envío gratis si precio total supera $100
    total_price = precio_menu + envio
    return {"menu": state.menu, "price": total_price, "message": f"Swapped '{meal_to_swap}' -> '{new_meal.name}'.", "nutrition": {"tmb": tmb, "tdee": tdee, "calorie_target": calorie_target, "macros": macros}}

@app.post("/validate-menu")
async def validate_menu(request: Request):
    payload = await request.json()
    session_id = payload.get("session_id")
    if not session_id or session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found.")
    state = SessionState(**sessions[session_id])
    weight_kg = to_kg(state.weight, state.weight_unit) if state.weight else None
    height_cm = to_cm(state.height, state.height_unit) if state.height else None
    tmb = calc_tmb_mifflin(weight_kg, height_cm, state.age, state.sex)
    tdee = round(tmb * compute_activity_factor(state.activity_days_bucket, state.activity_duration_bucket, state.activity_intensity), 2) if tmb else None
    calorie_target = calc_calorie_target(tdee, state.objective) if tdee else None
    weekly_menu = generate_weekly_menu(MEALS_DATA, calorie_target)
    return {"menu": weekly_menu, "calorie_target": calorie_target, "details": {"tmb": tmb, "tdee": tdee}}


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
    tmb = calc_tmb_mifflin(weight_kg, height_cm, state.age, state.sex)
    tdee = None
    if tmb is not None:
        tdee = round(tmb * compute_activity_factor(state.activity_days_bucket or "0", state.activity_duration_bucket or "<30", state.activity_intensity or "Low"), 1)
    calorie_target = calc_calorie_target(tdee, state.objective) if tdee else None
    macros = calc_macros(calorie_target, state.objective, weight_kg)
    daily_protein_target = macros.get("protein_grams", 0)
    state.menu = allocate_protein_to_menu(state, menu_objs, daily_protein_target)
    state.extra_protein_grams = 0
    state.extra_protein_map = {}
    sessions[sid] = state.model_dump()
    total_price = calculate_price([Meal(**m) if isinstance(m, dict) else m for m in state.menu], 0)
    return {"menu": state.menu, "price": total_price, "message":"Full menu regenerated.", "nutrition": {"tmb": tmb, "tdee": tdee, "calorie_target": calorie_target, "macros": macros}}
# --- RUTAS RELACIONADAS CON STRIPE ---

@app.post("/calculate-total")
def calculate_total(order: Order):
    total = 0
    for item in order.items:
        if item.item_type == "main_menu":
            price = 13 if item.less_protein else 15
        elif item.item_type == "breakfast":
            price = 10
        else:
            raise HTTPException(status_code=400, detail="Invalid item type")
        total += item.quantity * price
    return {"total": total}

@app.post("/create-checkout-session")
def create_checkout_session(order: Order):
    try:
        # Inicializar la lista de productos
        line_items = []

        # Agregar cada producto del pedido a la lista de productos
        for item in order.items:
            line_items.append({
                "price_data": {
                    "currency": "usd",
                    "product_data": {
                        "name": item.item_type,  # Nombre del producto enviado en el pedido
                    },
                    "unit_amount": calculate_price([item], 0) * 100,  # Precio en centavos
                },
                "quantity": item.quantity,  # Cantidad del producto
            })

        # Crear la sesión de pago en Stripe
        session = stripe.checkout.Session.create(
            payment_method_types=["card"],
            line_items=line_items,  # Usar la lista creada
            mode="payment",
            success_url="https://chontaduro-backend.onrender.com/success",
            cancel_url="https://chontaduro-backend.onrender.com/cancel",
        )

        # Devolver la URL de checkout
        return {"checkout_url": session.url}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

def calculate_price(menu: List[Meal], extra_protein: int) -> float:
    base = 0.0
    for m in menu:
        if isinstance(m, dict):
            base += float(getattr(m, "price", 0))
        elif hasattr(m, "price"):
            base += float(m.price)
    prot_cost = (extra_protein or 0) * 1.0
    return round(base + prot_cost, 2)


# Note: At startup we already loaded meals and templates.
# If you add or edit menus_weekly.json, call load_templates() or restart the server.

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)# Servicio Stripe - validación
