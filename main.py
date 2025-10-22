# main.py
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
from pydantic import BaseModel, Field
import random
import json
from typing import List, Dict, Any, Optional

app = FastAPI()

# --- CORS ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Middleware for debugging request bodies
@app.middleware("http")
async def log_request_body(request: Request, call_next):
    try:
        body = await request.json()
    except Exception:
        body = await request.body()
    print(f"[REQUEST BODY] {request.method} {request.url} -> {body}")
    response = await call_next(request)
    return response

@app.get("/", response_class=HTMLResponse)
async def serve_frontend():
    return FileResponse("index.html")


# --- LOAD MEALS ---
MEALS_DATA: List[Dict[str, Any]] = []

def normalize_meal_keys(raw: Dict[str, Any]) -> Dict[str, Any]:
    mapping = {
        "nombre": "name",
        "tipo": "type",
        "ingredientes": "ingredients",
        "calorias": "calories",
        "precio": "price",
        "imagen": "image_url",
        "image": "image_url",
    }
    out = {}
    for k, v in raw.items():
        key = mapping.get(k, k)
        out[key] = v
    if "ingredients" in out and isinstance(out["ingredients"], str):
        out["ingredients"] = [i.strip() for i in out["ingredients"].split(",") if i.strip()]
    # ensure tags list exists
    if "tags" in out and isinstance(out["tags"], str):
        out["tags"] = [t.strip().lower() for t in out["tags"].split(",") if t.strip()]
    return out

def sanitize_meal_data(data: List[Dict[str, Any]]):
    sanitized = []
    for meal in data:
        m = normalize_meal_keys(meal.copy())
        url = m.get("image_url", "") or m.get("image", "")
        if isinstance(url, str) and "google.com/search?q=" in url:
            try:
                start_index = url.index("?q=") + 3
                m["image_url"] = url[start_index:]
            except ValueError:
                m["image_url"] = None
        sanitized.append(m)
    return sanitized

try:
    with open("meals.json", "r", encoding="utf-8") as f:
        raw_data = json.load(f)
        if isinstance(raw_data, list):
            MEALS_DATA = sanitize_meal_data(raw_data)
        else:
            print("WARNING: meals.json not a list.")
except FileNotFoundError:
    print("WARNING: meals.json not found. Meal generation will fail.")
except json.JSONDecodeError:
    print("WARNING: meals.json could not be decoded. Check JSON format.")


# --- SESSIONS ---
sessions: Dict[str, Dict[str, Any]] = {}

# Flow mapping with new objective / personal_info steps
steps_mapping = {
    "start": "pick_plan",
    "pick_plan": "objective",
    "objective": "personal_info",
    "personal_info": "duration",
    "duration": "dislikes",
    "dislikes": "allergies",
    "allergies": "review",  # moved extra protein AFTER review via endpoint
    "extra_protein": "review",  # kept for compatibility but not used for menu generation
    "review": "review",
}

# --- MODELS ---
class Meal(BaseModel):
    name: str
    type: str
    ingredients: List[str] = Field(default_factory=list)
    calories: int
    price: float
    image_url: Optional[str] = None
    tags: List[str] = Field(default_factory=list)

    model_config = {"extra": "ignore"}

class SessionState(BaseModel):
    plan: Optional[int] = None
    days: Optional[int] = None
    dislikes: List[str] = Field(default_factory=list)
    allergies: List[str] = Field(default_factory=list)
    extra_protein_grams: int = 0  # stored but NOT used when generating the menu
    menu: List[Any] = Field(default_factory=list)
    current_step: str = "start"
    history: List[Dict[str, Any]] = Field(default_factory=list)

    # personal/nutrition fields
    objective: Optional[str] = None  # "Lose Fat", "Gain Muscle", "Maintain Shape"
    # Reordered: store unit before weight is used in UI; values saved the same
    weight_unit: Optional[str] = "kg"  # "kg" or "lbs"
    weight: Optional[float] = None
    height_unit: Optional[str] = "cm"  # "cm" or "in"
    height: Optional[float] = None
    age: Optional[int] = None
    sex: Optional[str] = None  # "male" | "female"
    # New activity detail fields
    activity_days_bucket: Optional[str] = None      # "0","1-2","3-4","5-7"
    activity_duration_bucket: Optional[str] = None  # "<30","30-60","60-120"
    activity_intensity: Optional[str] = None        # "Low","Moderate","High"
    body_fat: Optional[float] = None  # percentage optional

    # Diet preference
    diet_preference: Optional[str] = None  # "omnivore","vegetarian","vegan","pescatarian","i eat almost everything"

    # free text note
    user_note: Optional[str] = None

    model_config = {"extra": "ignore"}

class NextStepRequest(BaseModel):
    session_id: str
    step: str
    answer: Dict[str, Any] = Field(default_factory=dict)

    model_config = {"extra": "allow"}


# --- NUTRITION HELPERS ---
ACTIVITY_FACTORS = {
    "sedentary": 1.2,
    "light": 1.375,
    "moderate": 1.55,
    "intense": 1.725,
    "very_intense": 1.9,
}

def to_kg(weight: float, unit: str) -> Optional[float]:
    if weight is None:
        return None
    if unit and unit.lower() in ["lbs", "lb"]:
        return round(float(weight) * 0.45359237, 2)
    return float(weight)

def to_cm(height: float, unit: str) -> Optional[float]:
    if height is None:
        return None
    if unit and unit.lower() in ["in", "inch", "inches"]:
        return round(float(height) * 2.54, 1)
    return float(height)

def calc_tmb_mifflin(weight_kg: float, height_cm: float, age: int, sex: str) -> Optional[float]:
    if None in (weight_kg, height_cm, age, sex):
        return None
    sex = (sex or "").lower()
    if sex in ["male", "m", "man"]:
        return round((10 * weight_kg) + (6.25 * height_cm) - (5 * age) + 5, 1)
    else:
        return round((10 * weight_kg) + (6.25 * height_cm) - (5 * age) - 161, 1)

def compute_activity_factor(days_bucket: str, duration_bucket: str, intensity: str) -> Optional[float]:
    """
    Convert the user-friendly buckets to an activity multiplier.
    days_bucket: "0","1-2","3-4","5-7"
    duration_bucket: "<30","30-60","60-120"
    intensity: "Low","Moderate","High"
    """
    days_map = {"0": 1.2, "1-2": 1.3, "3-4": 1.45, "5-7": 1.6}
    base = days_map.get(str(days_bucket), 1.2)

    dur_map = {"<30": 0.0, "30-60": 0.05, "60-120": 0.08}
    dur_adj = dur_map.get(str(duration_bucket), 0.0)

    int_map = {"low": 0.0, "moderate": 0.03, "high": 0.06}
    int_adj = int_map.get((intensity or "").lower(), 0.0)

    factor = base + dur_adj + int_adj
    return round(min(factor, 1.9), 3)

def calc_tdee_with_details(tmb: float, days_bucket: str, duration_bucket: str, intensity: str) -> Optional[float]:
    factor = compute_activity_factor(days_bucket, duration_bucket, intensity)
    if tmb is None or factor is None:
        return None
    return round(tmb * factor, 1)

def calc_calorie_target(tdee: float, objective: str) -> Optional[float]:
    if tdee is None:
        return None
    objective_low = (objective or "").lower()
    if objective_low in ["lose fat", "lose", "fat", "lose_fat"]:
        return round(tdee - 400)
    elif objective_low in ["gain muscle", "gain", "muscle", "gain_muscle"]:
        return round(tdee + 350)
    else:
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
    carbs_grams = round(max(0, remaining_cal) / 4)

    return {
        "calories": int(calories),
        "protein_grams": int(protein_grams),
        "fat_grams": int(fat_grams),
        "carbs_grams": int(carbs_grams),
        "pct_protein": pct_protein,
        "pct_fat": pct_fat,
        "pct_carbs": pct_carb
    }


# --- DIET / COMPATIBILITY HELPERS ---
MEAT_KEYWORDS = {"chicken", "beef", "pork", "turkey", "steak", "bacon", "ham", "lamb"}
FISH_KEYWORDS = {"salmon", "shrimp", "fish", "tuna", "trout", "cod", "shellfish", "prawns", "crab", "lobster"}
DAIRY_KEYWORDS = {"milk", "yogurt", "cheese", "butter", "cream"}
EGG_KEYWORDS = {"egg", "eggs"}
HONEY_KEYWORDS = {"honey"}

def is_meal_compatible_with_diet(meal: Dict[str, Any], diet: Optional[str]) -> bool:
    """
    Returns True if meal matches the user's diet preference.
    Logic:
      - If diet is None or 'omnivore' or 'i eat almost everything' -> True
      - If meal has tags and tag matches (e.g., 'vegan' for vegan) -> True
      - Otherwise check ingredients for forbidden keywords per diet.
    """
    if not diet:
        return True
    diet_low = diet.lower()
    if diet_low in ["omnivore", "i eat almost everything", "everything"]:
        return True

    tags = [t.lower() for t in meal.get("tags", [])] if meal.get("tags") else []
    ingredients = [str(i).lower() for i in meal.get("ingredients", [])]

    # Vegan: require no meat, no fish, no dairy, no egg, no honey
    if diet_low == "vegan":
        if "vegan" in tags:
            return True
        forbidden = MEAT_KEYWORDS | FISH_KEYWORDS | DAIRY_KEYWORDS | EGG_KEYWORDS | HONEY_KEYWORDS
        return not any(any(k in ing for ing in ingredients) for k in forbidden)

    # Vegetarian: allow dairy/eggs, but no meat/fish
    if diet_low == "vegetarian":
        if "vegetarian" in tags or "vegan" in tags:
            return True
        forbidden = MEAT_KEYWORDS | FISH_KEYWORDS
        return not any(any(k in ing for ing in ingredients) for k in forbidden)

    # Pescatarian: allow fish/seafood, but no meat (beef/pork/chicken)
    if diet_low == "pescatarian":
        if "pescatarian" in tags or "vegan" in tags or "vegetarian" in tags:
            return True
        forbidden = MEAT_KEYWORDS
        return not any(any(k in ing for ing in ingredients) for k in forbidden)

    # Fallback conservative: allow only if no obvious conflict
    return True


# --- BUSINESS LOGIC (MEALS) ---
def calculate_price(menu: List[Meal], extra_protein: int) -> float:
    base_price = sum(meal.price for meal in menu)
    protein_cost = (extra_protein or 0) * 1.00
    return round(base_price + protein_cost, 2)

def filter_meals(dislikes: List[str], allergies: List[str], diet: Optional[str] = None) -> List[Meal]:
    # Interpret "I like everything" sentinel: empty lists means no filtering
    undesired = set()
    if dislikes:
        # if the either sentinel appears, treat as no dislikes
        if isinstance(dislikes, list) and any(str(x).lower().startswith("none") or str(x).lower().startswith("i like") for x in dislikes):
            undesired = set()
        else:
            undesired.update([d.lower() for d in dislikes])
    if allergies:
        if isinstance(allergies, list) and any(str(x).lower().startswith("none") or str(x).lower().startswith("i like") for x in allergies):
            # ignore allergies sentinel
            pass
        else:
            undesired.update([a.lower() for a in allergies])

    filtered_meals = []
    for meal in MEALS_DATA:
        # First check diet compatibility
        if not is_meal_compatible_with_diet(meal, diet):
            continue

        ingredients = [str(i).lower() for i in meal.get("ingredients", [])]
        if not any(ing in undesired for ing in ingredients):
            try:
                # Ensure tags exist
                meal_copy = meal.copy()
                meal_copy["tags"] = [t.lower() for t in meal_copy.get("tags", [])] if meal_copy.get("tags") else []
                filtered_meals.append(Meal(**meal_copy))
            except Exception as e:
                print(f"Error validating meal data: {e} for meal {meal.get('name')}")
    return filtered_meals

def generate_menu(state: SessionState) -> List[Meal]:
    """
    Generate menu according to the plan mapping:
      plan 1: 1 main meal
      plan 2: 2 main meals
      plan 3: 1 main meal + 1 breakfast
      plan 4: 2 main meals + 1 breakfast (full day)
    """
    if not state.plan or not state.days:
        return []

    plan_map = {1: (1, 0), 2: (2, 0), 3: (1, 1), 4: (2, 1)}
    meals_config = plan_map.get(state.plan)
    if not meals_config:
        return []

    num_main, num_breakfast = meals_config
    total_meals_required = state.days * (num_main + num_breakfast)
    available_meals = filter_meals(state.dislikes, state.allergies, state.diet_preference)
    if not available_meals:
        return []

    breakfasts = [m for m in available_meals if m.type == "Breakfast"]
    mains = [m for m in available_meals if m.type == "Main Meal"]

    menu: List[Meal] = []
    for _ in range(state.days):
        day_meals = []
        for _ in range(num_breakfast):
            if breakfasts:
                day_meals.append(random.choice(breakfasts))
        for _ in range(num_main):
            if mains:
                day_meals.append(random.choice(mains))
        if not day_meals and available_meals:
            day_meals.append(random.choice(available_meals))
        menu.extend(day_meals)

    return menu[:total_meals_required]

def assess_menu_possibility(state: SessionState) -> Dict[str, Any]:
    """
    Check if there are enough meals available after filters for user's plan and days.
    """
    if not state.plan or not state.days:
        return {"ok": False, "reason": "missing_data", "message": "Plan or days are not set."}

    plan_map = {1: (1, 0), 2: (2, 0), 3: (1, 1), 4: (2, 1)}
    config = plan_map.get(state.plan)
    if not config:
        return {"ok": False, "reason": "invalid_plan", "message": "Plan value not recognized."}

    need_main_per_day, need_breakfast_per_day = config
    need_mains_total = need_main_per_day * state.days
    need_breakfasts_total = need_breakfast_per_day * state.days

    available_meals = filter_meals(state.dislikes, state.allergies, state.diet_preference)
    if not available_meals:
        return {"ok": False, "reason": "no_meals", "message": "No meals available after applying your diet/dislikes/allergies."}

    mains = [m for m in available_meals if m.type == "Main Meal"]
    breakfasts = [m for m in available_meals if m.type == "Breakfast"]

    details = {
        "available_total": len(available_meals),
        "available_mains": len(mains),
        "available_breakfasts": len(breakfasts),
        "need_mains_total": need_mains_total,
        "need_breakfasts_total": need_breakfasts_total
    }

    if need_mains_total > len(mains):
        return {"ok": False, "reason": "not_enough_mains", "message": "Not enough Main Meal options for your current filters.", "details": details}
    if need_breakfasts_total > len(breakfasts):
        return {"ok": False, "reason": "not_enough_breakfasts", "message": "Not enough Breakfast options for your current filters.", "details": details}

    return {"ok": True, "reason": None, "details": details}

# --- FORM UI ---
def get_dislikes_options_for_diet(diet: Optional[str]) -> List[str]:
    base = ["None - I like everything", "Oats", "Berries", "Milk", "Chicken", "Rice", "Broccoli",
            "Salmon", "Lettuce", "Avocado", "Tofu", "Carrots", "Beef", "Pork", "Shellfish", "Banana"]
    if not diet:
        return base
    diet_low = diet.lower()
    if diet_low == "vegetarian":
        # remove meat/fish options
        return [o for o in base if o.lower() not in {"chicken", "beef", "pork", "salmon", "shellfish"}]
    if diet_low == "vegan":
        # remove meat/fish/dairy/egg/honey related options
        return [o for o in base if o.lower() not in {"chicken", "beef", "pork", "salmon", "shellfish", "milk", "banana"}]
    if diet_low == "pescatarian":
        # allow fish but remove red meat/pork/chicken
        return [o for o in base if o.lower() not in {"chicken", "beef", "pork"}]
    # omnivore / everything
    return base

def get_form_fields(step_name: str, state: Optional[SessionState] = None):
    """
    Returns the UI structure for each step. NOTE: order matters for UI rendering.
    For personal_info we put Weight Unit before Weight as requested.
    Activity inputs are split into three fields so users can choose days/duration/intensity.
    Dislikes/Allergies are rendered as checkboxes on the frontend (type=multiselect).
    """
    if step_name == "pick_plan":
        return {
            "question": "Which plan do you want?",
            "fields": [
                {"name": "Plan", "type": "select", "options": [
                    "Plan 1: 1 main meal per day",
                    "Plan 2: 2 main meals per day",
                    "Plan 3: 1 main meal + 1 breakfast",
                    "Plan 4: 2 main meals + 1 breakfast (full day)"
                ]}
            ],
            "current_step": "pick_plan"
        }

    if step_name == "objective":
        return {
            "question": "What is your main goal?",
            "fields": [
                {"name": "Objective", "type": "select", "options": [
                    "Lose Fat",
                    "Gain Muscle",
                    "Maintain Shape"
                ]}
            ],
            "current_step": "objective"
        }

    if step_name == "personal_info":
        return {
            "question": "Tell us your personal data (used to calculate calories & macros):",
            "fields": [
                {"name": "Diet Preference", "type": "select", "options": ["omnivore", "vegetarian", "vegan", "pescatarian", "i eat almost everything"]},
                {"name": "Weight Unit", "type": "select", "options": ["kg", "lbs"]},
                {"name": "Weight", "type": "number", "placeholder": "e.g. 70", "unit": "kg or lbs"},
                {"name": "Height Unit", "type": "select", "options": ["cm", "in"]},
                {"name": "Height", "type": "number", "placeholder": "e.g. 175", "unit": "cm or in"},
                {"name": "Age", "type": "number", "placeholder": "e.g. 30"},
                {"name": "Sex", "type": "select", "options": ["Male", "Female"]},
                # Activity split into three fields (days, duration, intensity)
                {"name": "Days per week", "type": "select", "options": ["0", "1-2", "3-4", "5-7"], "unit": "How many days do you exercise on average?"},
                {"name": "Avg session duration", "type": "select", "options": ["<30", "30-60", "60-120"], "unit": "Typical length of each session (minutes)"},
                {"name": "Intensity", "type": "select", "options": ["Low", "Moderate", "High"], "unit": "Low = easy; Moderate = pushed but can talk; High = breathless, HIIT/heavy lifting."},
                {"name": "Body Fat % (optional)", "type": "number", "placeholder": "e.g. 18", "required": False}
            ],
            "current_step": "personal_info"
        }

    if step_name == "duration":
        return {
            "question": "For how many days do you want this plan?",
            "fields": [
                {"name": "Días", "type": "number", "min": 1, "max": 30, "placeholder": "e.g. 7"}
            ],
            "current_step": "duration"
        }

    if step_name == "dislikes":
        diet = state.diet_preference if state else None
        options = get_dislikes_options_for_diet(diet)
        return {
            "question": "Select ingredients you DON'T like (optional):",
            "fields": [
                {"name": "Ingredientes_No_Deseados", "type": "multiselect", "options": options}
            ],
            "current_step": "dislikes"
        }

    if step_name == "allergies":
        return {
            "question": "Any food allergies? (optional)",
            "fields": [
                {"name": "Alergias", "type": "multiselect", "options": [
                    "None - I like everything",
                    "Gluten", "Lactose", "Nuts", "Shellfish", "Soy", "Eggs", "Fish"
                ]}
            ],
            "current_step": "allergies"
        }

    if step_name == "review":
        if not state:
            return {"question": "State error. Start again.", "current_step": "review"}
        summary = (
            f"Plan: {state.plan} meals/day for {state.days} days.\n"
            f"Goal: {state.objective or 'N/A'}\n"
            f"Diet: {state.diet_preference or 'N/A'}\n"
            f"Weight: {state.weight or 'N/A'} {state.weight_unit}\n"
            f"Height: {state.height or 'N/A'} {state.height_unit}\n"
            f"Age: {state.age or 'N/A'}\n"
            f"Activity days: {state.activity_days_bucket or 'N/A'}, duration: {state.activity_duration_bucket or 'N/A'}, intensity: {state.activity_intensity or 'N/A'}\n"
        )
        return {
            "question": f"Review your info and generate the menu:\n\n{summary}",
            "fields": [],
            "current_step": "review"
        }

    return {"question": "Unknown step. Start again.", "current_step": "start"}


# --- ENDPOINTS ---
def normalize_request_payload(payload: Dict[str, Any]) -> NextStepRequest:
    session_id = payload.get("session_id") or payload.get("sessionId") or payload.get("id") or str(random.randint(1000, 9999))
    step = payload.get("step") or payload.get("current_step") or payload.get("currentStep") or "start"
    answer = payload.get("answer") or payload.get("answers") or payload.get("data") or {}
    if answer is None:
        answer = {}
    return NextStepRequest(session_id=session_id, step=step, answer=answer)

@app.post("/next-step")
async def next_step(request: Request):
    payload = await request.json()
    try:
        req = normalize_request_payload(payload)
    except Exception as e:
        return JSONResponse(status_code=422, content={"detail": "Invalid payload", "error": str(e), "raw": payload})

    session_id = req.session_id
    step_name = (req.step or "start")
    answer = req.answer or {}

    # ensure step_name valid fallback
    if step_name not in steps_mapping and step_name not in ["review", "start", "back"]:
        step_name = "start"

    if session_id not in sessions:
        sessions[session_id] = SessionState().model_dump()

    state = SessionState(**sessions[session_id])

    # Normalize answer keys robustly
    def normalize_key(k: str) -> str:
        return ''.join(ch for ch in (k or "").lower() if ch.isalnum())

    translated_answer = {}
    if isinstance(answer, dict):
        for key, value in answer.items():
            key_norm = normalize_key(str(key))
            if key_norm in ["plan", "tipoplan"]:
                translated_answer["plan"] = value
            elif key_norm in ["days", "dias", "días"]:
                translated_answer["days"] = value
            elif key_norm in ["dislikes", "ingredientesnodedeseados", "ingredientesnodeseados"]:
                translated_answer["dislikes"] = value
            elif key_norm in ["allergies", "alergias", "alergieslist"]:
                translated_answer["allergies"] = value
            elif key_norm in ["extraprotein", "protein", "gramosextraproteina", "gramosextraprotena", "gramosextraproteina", "gramos_extra_proteina"]:
                translated_answer["extra_protein_grams"] = value
            elif key_norm in ["objective", "goal", "objetivo"]:
                translated_answer["objective"] = value
            elif key_norm in ["weight", "peso"]:
                translated_answer["weight"] = value
            elif key_norm in ["weightunit", "weight_unit", "unitweight"]:
                translated_answer["weight_unit"] = value
            elif key_norm in ["height", "altura"]:
                translated_answer["height"] = value
            elif key_norm in ["heightunit", "height_unit", "unitheight"]:
                translated_answer["height_unit"] = value
            elif key_norm in ["age", "edad"]:
                translated_answer["age"] = value
            elif key_norm in ["sex", "gender"]:
                translated_answer["sex"] = value
            elif key_norm in ["daysperweek", "daysperweek", "days", "daysperwk", "daysperweekbucket"]:
                translated_answer["activity_days_bucket"] = value
            elif key_norm in ["avgsessionduration", "avg_session_duration", "avgduration", "sessionduration", "durationbucket"]:
                translated_answer["activity_duration_bucket"] = value
            elif key_norm in ["intensity", "activityintensity"]:
                translated_answer["activity_intensity"] = value
            elif key_norm in ["bodyfat", "body_fat", "bfpercent", "bf"]:
                translated_answer["body_fat"] = value
            elif key_norm in ["diet", "dietpreference", "diet_preference", "dietpreferencechoice"]:
                translated_answer["diet_preference"] = value
            elif key_norm in ["note", "usernote", "tellus", "tellussomething"]:
                translated_answer["user_note"] = value
            else:
                translated_answer[key] = value

    answer = translated_answer

    step_to_render_name = state.current_step

    if step_name == "back" and state.history:
        prev_state_data = state.history.pop()
        prev_state = SessionState(**prev_state_data)
        sessions[session_id] = prev_state.model_dump()
        return get_form_fields(prev_state.current_step, prev_state)

    if step_name != "start":
        state.history.append(sessions[session_id].copy())

    # Step handling
    if step_name == "start":
        step_to_render_name = steps_mapping["start"]

    elif step_name == "pick_plan":
        plan_answer = answer.get("plan")
        if plan_answer and isinstance(plan_answer, str):
            try:
                plan_str = plan_answer.split(":")[0].replace("Plan", "").strip()
                plan_num = int(plan_str)
                if plan_num in [1, 2, 3, 4]:
                    state.plan = plan_num
                    step_to_render_name = steps_mapping["pick_plan"]
                else:
                    step_to_render_name = "pick_plan"
            except Exception:
                step_to_render_name = "pick_plan"
        else:
            step_to_render_name = "pick_plan"

    elif step_name == "objective":
        obj = answer.get("objective")
        if obj and isinstance(obj, str):
            state.objective = obj
            step_to_render_name = steps_mapping["objective"]
        else:
            step_to_render_name = "objective"

    elif step_name == "personal_info":
        try:
            # diet first (if provided)
            dp = answer.get("diet_preference")
            if dp:
                state.diet_preference = str(dp)

            # unit first (frontend sends weight_unit before weight)
            wu = answer.get("weight_unit")
            if wu:
                state.weight_unit = str(wu)

            w = answer.get("weight")
            if w is not None and str(w) != "":
                try:
                    state.weight = float(w)
                except Exception:
                    state.weight = None

            hu = answer.get("height_unit")
            if hu:
                state.height_unit = str(hu)

            h = answer.get("height")
            if h is not None and str(h) != "":
                try:
                    state.height = float(h)
                except Exception:
                    state.height = None

            a = answer.get("age")
            if a is not None and str(a) != "":
                try:
                    state.age = int(a)
                except Exception:
                    state.age = None

            s = answer.get("sex")
            if s:
                state.sex = str(s)

            adb = answer.get("activity_days_bucket")
            if adb:
                state.activity_days_bucket = str(adb)

            adb2 = answer.get("activity_duration_bucket")
            if adb2:
                state.activity_duration_bucket = str(adb2)

            ai = answer.get("activity_intensity")
            if ai:
                state.activity_intensity = str(ai)

            bf = answer.get("body_fat")
            if bf is not None and str(bf) != "":
                try:
                    state.body_fat = float(bf)
                except Exception:
                    state.body_fat = None

            step_to_render_name = steps_mapping["personal_info"]
        except Exception:
            step_to_render_name = "personal_info"

    elif step_name == "duration":
        try:
            days_input = answer.get("days") or answer.get("Días") or answer.get("dias")
            if days_input is not None and str(days_input).isdigit() and 1 <= int(days_input) <= 30:
                state.days = int(days_input)
                step_to_render_name = steps_mapping["duration"]
            else:
                step_to_render_name = "duration"
        except Exception:
            step_to_render_name = "duration"

    elif step_name == "dislikes" and ("dislikes" in answer or "Ingredientes_No_Deseados" in answer):
        data = answer.get("dislikes") or answer.get("Ingredientes_No_Deseados")
        # Interpret "None - I like everything" as empty list
        if isinstance(data, list) and any(str(x).lower().startswith("none") or str(x).lower().startswith("i like") for x in data):
            state.dislikes = []
        else:
            state.dislikes = data if isinstance(data, list) else [data] if data else []
        step_to_render_name = steps_mapping["dislikes"]

    elif step_name == "allergies" and ("allergies" in answer or "Alergias" in answer):
        data = answer.get("allergies") or answer.get("Alergias")
        if isinstance(data, list) and any(str(x).lower().startswith("none") or str(x).lower().startswith("i like") for x in data):
            state.allergies = []
        else:
            state.allergies = data if isinstance(data, list) else [data] if data else []
        step_to_render_name = steps_mapping["allergies"]

    elif step_name == "review":
        # First, validate we have plan/days and enough meals available
        assessment = assess_menu_possibility(state)
        if not assessment["ok"]:
            # Return a clear guidance payload instead of a generic error
            # include current_step so frontend stays synchronized
            return {
                "question": assessment.get("message", "Could not generate menu with current settings."),
                "fields": [],
                "current_step": state.current_step,
                "issue": assessment.get("reason"),
                "details": assessment.get("details", {})
            }

        # If assessment OK, generate menu (without extra protein at generation time)
        state.menu = generate_menu(state)
        sessions[session_id] = state.model_dump()

        # Defensive double-check
        if not state.menu:
            return {
                "question": "Unexpected error: no menu items could be selected. Try changing plan or relaxing filters.",
                "fields": [],
                "current_step": state.current_step,
                "issue": "generation_failed"
            }

        # Nutrition calculation (no extra protein included here)
        weight_kg = to_kg(state.weight, state.weight_unit) if state.weight else None
        height_cm = to_cm(state.height, state.height_unit) if state.height else None
        tmb = calc_tmb_mifflin(weight_kg, height_cm, state.age, state.sex)

        # Compute TDEE using detailed inputs if present (days/duration/intensity)
        tdee = None
        if state.activity_days_bucket or state.activity_duration_bucket or state.activity_intensity:
            tdee = calc_tdee_with_details(tmb, state.activity_days_bucket or "0", state.activity_duration_bucket or "<30", state.activity_intensity or "Low")
        else:
            # fallback to a default multiplier if user didn't provide detailed activity (conservative)
            tdee = calc_tdee_with_details(tmb, "0", "<30", "Low") if tmb else None

        calorie_target = calc_calorie_target(tdee, state.objective) if tdee else None
        macros = calc_macros(calorie_target, state.objective, to_kg(state.weight, state.weight_unit) if state.weight else None)

        total_price = calculate_price(state.menu, 0)  # price WITHOUT extra protein at generation time

        return {
            "menu": [m.model_dump() for m in state.menu],
            "price": total_price,
            "message": "Your menu is ready!",
            "nutrition": {
                "tmb": tmb,
                "tdee": tdee,
                "calorie_target": calorie_target,
                "macros": macros
            },
            "current_step": state.current_step
        }

    # persist and return next form
    state.current_step = step_to_render_name
    sessions[session_id] = state.model_dump()

    return get_form_fields(state.current_step, state)


# --- NEW endpoint: add protein AFTER menu generated ---
@app.post("/add-protein")
async def add_protein(request: Request):
    payload = await request.json()
    session_id = payload.get("session_id") or payload.get("sessionId")
    extra = payload.get("extra_protein_grams") or payload.get("extraProtein") or payload.get("grams") or 0
    try:
        extra = int(extra or 0)
    except Exception:
        return JSONResponse(status_code=422, content={"detail": "extra_protein_grams must be integer."})

    if not session_id or session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found.")

    state = SessionState(**sessions[session_id])

    # Save extra protein grams in session
    state.extra_protein_grams = extra
    sessions[session_id] = state.model_dump()

    # Recompute price including protein cost ($1 per gram)
    current_menu_objects = [Meal(**m) if isinstance(m, dict) else m for m in state.menu]
    total_price = calculate_price(current_menu_objects, state.extra_protein_grams)

    # Recompute nutrition: base macros + added protein calories
    weight_kg = to_kg(state.weight, state.weight_unit) if state.weight else None
    height_cm = to_cm(state.height, state.height_unit) if state.height else None
    tmb = calc_tmb_mifflin(weight_kg, height_cm, state.age, state.sex)
    if state.activity_days_bucket or state.activity_duration_bucket or state.activity_intensity:
        tdee = calc_tdee_with_details(tmb, state.activity_days_bucket or "0", state.activity_duration_bucket or "<30", state.activity_intensity or "Low")
    else:
        tdee = calc_tdee_with_details(tmb, "0", "<30", "Low") if tmb else None
    calorie_target = calc_calorie_target(tdee, state.objective) if tdee else None
    base_macros = calc_macros(calorie_target, state.objective, weight_kg)

    # Add extra protein (calories and grams). We simply add protein calories on top.
    added_protein_cal = state.extra_protein_grams * 4
    new_calories = (base_macros.get("calories") or 0) + added_protein_cal
    new_protein = (base_macros.get("protein_grams") or 0) + state.extra_protein_grams
    # Keep fat/carbs unchanged for simplicity
    new_macros = {
        "calories": int(new_calories),
        "protein_grams": int(new_protein),
        "fat_grams": int(base_macros.get("fat_grams", 0)),
        "carbs_grams": int(base_macros.get("carbs_grams", 0)),
        "pct_protein": base_macros.get("pct_protein"),
        "pct_fat": base_macros.get("pct_fat"),
        "pct_carbs": base_macros.get("pct_carbs"),
    }

    return {
        "menu": [m.model_dump() for m in current_menu_objects],
        "price": total_price,
        "message": f"Added {state.extra_protein_grams} g extra protein.",
        "nutrition": {
            "tmb": tmb,
            "tdee": tdee,
            "calorie_target": calorie_target,
            "macros": new_macros
        }
    }


@app.post("/add-note")
async def add_note(request: Request):
    payload = await request.json()
    session_id = payload.get("session_id") or payload.get("sessionId")
    note = payload.get("note") or payload.get("user_note") or payload.get("tellus") or ""
    if not session_id or session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found.")
    state = SessionState(**sessions[session_id])
    state.user_note = str(note)[:1000]  # limit
    sessions[session_id] = state.model_dump()
    current_menu_objects = [Meal(**m) if isinstance(m, dict) else m for m in state.menu]
    total_price = calculate_price(current_menu_objects, state.extra_protein_grams)
    return {"menu": state.menu, "price": total_price, "message": "Note saved.", "note": state.user_note}


@app.post("/swap-meal")
async def swap_meal(request: Request):
    payload = await request.json()
    session_id = payload.get("session_id") or payload.get("sessionId")
    meal_to_swap_name = payload.get("meal_to_swap") or payload.get("mealToSwap") or payload.get("mealName")
    if not session_id or session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found.")
    state = SessionState(**sessions[session_id])
    current_menu_objects = [Meal(**m) if isinstance(m, dict) else m for m in state.menu]
    meal_to_swap_info = next((m for m in current_menu_objects if m.name == meal_to_swap_name), None)
    if not meal_to_swap_info:
        raise HTTPException(status_code=404, detail="Meal not found in current menu.")
    meal_type = meal_to_swap_info.type
    available_meals = filter_meals(state.dislikes, state.allergies, state.diet_preference)

    # Filter only meals of the same type and that are NOT already in the menu and compatible with diet
    potential_replacements = [
        m for m in available_meals
        if m.type == meal_type and m.name != meal_to_swap_name and m.name not in [x.name for x in current_menu_objects]
    ]

    if not potential_replacements:
        return {"menu": [m.model_dump() for m in current_menu_objects], "price": calculate_price(current_menu_objects, state.extra_protein_grams), "message": "No replacements available with your filters."}

    new_meal = random.choice(potential_replacements)

    new_menu = []
    replaced = False
    for meal in current_menu_objects:
        if not replaced and meal.name == meal_to_swap_name:
            new_menu.append(new_meal)
            replaced = True
        else:
            new_menu.append(meal)

    state.menu = [m.model_dump() for m in new_menu]
    sessions[session_id] = state.model_dump()
    total_price = calculate_price(new_menu, state.extra_protein_grams)
    return {"menu": state.menu, "price": total_price, "message": f"Meal '{meal_to_swap_name}' swapped with '{new_meal.name}'."}


@app.post("/redo-menu")
async def redo_menu(request: Request):
    payload = await request.json()
    session_id = payload.get("session_id") or payload.get("sessionId")
    if not session_id or session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found.")
    state = SessionState(**sessions[session_id])
    new_menu_objects = generate_menu(state)
    if not new_menu_objects:
        return {"message": "Could not generate a new menu with your current filters."}
    state.menu = [m.model_dump() for m in new_menu_objects]
    # reset extra protein when regenerating menu (user must add afterward)
    state.extra_protein_grams = 0
    sessions[session_id] = state.model_dump()
    total_price = calculate_price(new_menu_objects, state.extra_protein_grams)
    return {"menu": state.menu, "price": total_price, "message": "Full menu regenerated!"}