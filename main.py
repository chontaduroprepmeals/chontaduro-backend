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

# Updated flow: we add 'objective' and 'personal_info' steps
steps_mapping = {
    "start": "pick_plan",
    "pick_plan": "objective",
    "objective": "personal_info",
    "personal_info": "duration",
    "duration": "dislikes",
    "dislikes": "allergies",
    "allergies": "extra_protein",
    "extra_protein": "review",
}

# --- MODELS ---
class Meal(BaseModel):
    name: str
    type: str
    ingredients: List[str] = Field(default_factory=list)
    calories: int
    price: float
    image_url: Optional[str] = None

    model_config = {"extra": "ignore"}

class SessionState(BaseModel):
    plan: Optional[int] = None
    days: Optional[int] = None
    dislikes: List[str] = Field(default_factory=list)
    allergies: List[str] = Field(default_factory=list)
    extra_protein_grams: int = 0
    menu: List[Any] = Field(default_factory=list)
    current_step: str = "start"
    history: List[Dict[str, Any]] = Field(default_factory=list)

    # New personal/nutrition fields
    objective: Optional[str] = None  # "Lose Fat", "Gain Muscle", "Maintain Shape"
    weight: Optional[float] = None
    weight_unit: Optional[str] = "kg"  # "kg" or "lbs"
    height: Optional[float] = None
    height_unit: Optional[str] = "cm"  # "cm" or "in"
    age: Optional[int] = None
    sex: Optional[str] = None  # "male" | "female"
    activity_level: Optional[str] = None  # one of the factor keys (sedentary, light, moderate, intense, very_intense)
    body_fat: Optional[float] = None  # percentage optional

    model_config = {"extra": "ignore"}


class NextStepRequest(BaseModel):
    session_id: str
    step: str
    answer: Dict[str, Any] = Field(default_factory=dict)

    model_config = {"extra": "allow"}


# --- NUTRITION CALCULATION HELPERS ---
ACTIVITY_FACTORS = {
    "sedentary": 1.2,
    "light": 1.375,
    "moderate": 1.55,
    "intense": 1.725,
    "very_intense": 1.9,
    # Accept numeric string too (1.2 etc.)
}

def to_kg(weight: float, unit: str) -> float:
    if weight is None:
        return None
    if unit == "lbs" or unit.lower() in ["lb", "lbs"]:
        return round(weight * 0.45359237, 2)
    return float(weight)

def to_cm(height: float, unit: str) -> float:
    if height is None:
        return None
    if unit == "in" or unit.lower() in ["inch", "inches", "in"]:
        return round(height * 2.54, 1)
    return float(height)

def calc_tmb_mifflin(weight_kg: float, height_cm: float, age: int, sex: str) -> float:
    if None in (weight_kg, height_cm, age, sex):
        return None
    sex = (sex or "").lower()
    if sex in ["male", "m", "man"]:
        return round((10 * weight_kg) + (6.25 * height_cm) - (5 * age) + 5, 1)
    else:
        return round((10 * weight_kg) + (6.25 * height_cm) - (5 * age) - 161, 1)

def get_activity_factor(level: str) -> Optional[float]:
    if not level:
        return None
    level_low = str(level).lower()
    return ACTIVITY_FACTORS.get(level_low) or (float(level_low) if level_low.replace('.', '', 1).isdigit() else None)

def calc_tdee(tmb: float, activity_level: str) -> Optional[float]:
    factor = get_activity_factor(activity_level)
    if tmb is None or factor is None:
        return None
    return round(tmb * factor, 1)

def calc_calorie_target(tdee: float, objective: str) -> Optional[float]:
    if tdee is None:
        return None
    objective_low = (objective or "").lower()
    if objective_low in ["lose fat", "lose", "fat", "lose_fat"]:
        return round(tdee - 400)  # middle of 300-500
    elif objective_low in ["gain muscle", "gain", "muscle", "gain_muscle"]:
        return round(tdee + 350)  # middle of 250-450
    else:
        return round(tdee)  # maintain

def calc_macros(calories: int, objective: str, weight_kg: Optional[float]) -> Dict[str, Any]:
    """
    Returns protein_grams, fat_grams, carbs_grams and percentages.
    Uses protein per kg heuristic depending on objective, constrained to reasonable bounds.
    """
    if calories is None:
        return {}
    obj = (objective or "").lower()
    # default percentages
    if obj in ["lose fat", "lose", "fat"]:
        pct_protein, pct_fat, pct_carb = 0.30, 0.25, 0.45
        prot_per_kg = 2.0
    elif obj in ["gain muscle", "gain", "muscle"]:
        pct_protein, pct_fat, pct_carb = 0.28, 0.25, 0.47
        prot_per_kg = 1.8
    else:
        pct_protein, pct_fat, pct_carb = 0.25, 0.30, 0.45
        prot_per_kg = 1.6

    # calculate protein grams: prefer grams-per-kg if weight known, else percent-based
    if weight_kg:
        protein_grams = round(prot_per_kg * weight_kg)
        # enforce reasonable bounds
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


# --- BUSINESS LOGIC (MEALS) ---
def calculate_price(menu: List[Meal], extra_protein: int) -> float:
    base_price = sum(meal.price for meal in menu)
    protein_cost = extra_protein * 1.00
    return round(base_price + protein_cost, 2)

def filter_meals(dislikes: List[str], allergies: List[str]) -> List[Meal]:
    undesired = set([d.lower() for d in (dislikes or [])] + [a.lower() for a in (allergies or [])])
    filtered_meals = []
    for meal in MEALS_DATA:
        ingredients = [str(i).lower() for i in meal.get("ingredients", [])]
        if not any(ing in undesired for ing in ingredients):
            try:
                filtered_meals.append(Meal(**meal))
            except Exception as e:
                print(f"Error validating meal data: {e} for meal {meal.get('name')}")
    return filtered_meals

def generate_menu(state: SessionState) -> List[Meal]:
    if not state.plan or not state.days:
        return []

    meals_per_day = {1: 1, 2: 2, 3: 3, 4: 3}.get(state.plan)
    if not meals_per_day:
        return []

    total_meals_required = state.days * meals_per_day
    available_meals = filter_meals(state.dislikes, state.allergies)
    if not available_meals:
        return []

    categories = {
        "Breakfast": [m for m in available_meals if m.type == "Breakfast"],
        "Main Meal": [m for m in available_meals if m.type == "Main Meal"]
    }

    menu: List[Meal] = []
    for _ in range(state.days):
        day_meals = []
        if meals_per_day >= 1 and categories["Breakfast"]:
            day_meals.append(random.choice(categories["Breakfast"]))
        main_meals_required = meals_per_day - (1 if meals_per_day >= 1 else 0)
        for _ in range(main_meals_required):
            if categories["Main Meal"]:
                day_meals.append(random.choice(categories["Main Meal"]))
        menu.extend(day_meals)

    return menu[:total_meals_required]


# --- UI FORM STRUCTURE ---
def get_form_fields(step_name: str, state: Optional[SessionState] = None):
    if step_name == "pick_plan":
        return {
            "question": "Which plan do you want?",
            "fields": [
                {"name": "Plan", "type": "select", "options": [
                    "Plan 1: 1 meal per day",
                    "Plan 2: 2 meals per day",
                    "Plan 3: 3 meals per day (with dessert)",
                    "Plan 4: 3 meals per day (with extra protein)"
                ]}
            ]
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
            ]
        }

    if step_name == "personal_info":
        return {
            "question": "Tell us your personal data (used to calculate calories & macros):",
            "fields": [
                {"name": "Weight", "type": "number", "placeholder": "e.g. 70", "unit": "kg or lbs"},
                {"name": "Weight Unit", "type": "select", "options": ["kg", "lbs"]},
                {"name": "Height", "type": "number", "placeholder": "e.g. 175", "unit": "cm or in"},
                {"name": "Height Unit", "type": "select", "options": ["cm", "in"]},
                {"name": "Age", "type": "number", "placeholder": "e.g. 30"},
                {"name": "Sex", "type": "select", "options": ["Male", "Female"]},
                {"name": "Activity Level", "type": "select", "options": [
                    "sedentary", "light", "moderate", "intense", "very_intense"
                ], "unit": "Choose one (see app for definitions)"},
                {"name": "Body Fat % (optional)", "type": "number", "placeholder": "e.g. 18", "required": False}
            ]
        }

    if step_name == "duration":
        return {
            "question": "For how many days do you want this plan?",
            "fields": [
                {"name": "Días", "type": "number", "min": 1, "max": 30, "placeholder": "e.g. 7"}
            ]
        }

    if step_name == "dislikes":
        return {
            "question": "Select ingredients you DON'T like (optional):",
            "fields": [
                {"name": "Ingredientes_No_Deseados", "type": "multiselect", "options": [
                    "Oats", "Berries", "Milk", "Chicken", "Rice", "Broccoli",
                    "Salmon", "Lettuce", "Avocado", "Tofu", "Carrots"
                ]}
            ]
        }

    if step_name == "allergies":
        return {
            "question": "Any food allergies? (optional)",
            "fields": [
                {"name": "Alergias", "type": "multiselect", "options": [
                    "Gluten", "Lactose", "Nuts", "Shellfish", "Soy"
                ]}
            ]
        }

    if step_name == "extra_protein":
        return {
            "question": "Extra protein grams per menu? (optional)",
            "fields": [
                {"name": "Gramos_Extra_Proteína", "type": "number", "min": 0, "max": 100, "placeholder": "0"}
            ]
        }

    if step_name == "review":
        if not state:
            return {"question": "State error. Start again."}
        summary = (
            f"Plan: {state.plan} meals/day for {state.days} days.\n"
            f"Goal: {state.objective or 'N/A'}\n"
            f"Weight: {state.weight} {state.weight_unit}\n"
            f"Height: {state.height} {state.height_unit}\n"
            f"Age: {state.age}\n"
            f"Activity: {state.activity_level}\n"
            f"Extra protein: {state.extra_protein_grams} g\n"
        )
        return {
            "question": f"Review your info and generate the menu:\n\n{summary}",
            "fields": []
        }

    return {"question": "Unknown step. Start again."}


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
            # map many possible keys to internal canonical keys
            if key_norm in ["plan", "tipoplan"]:
                translated_answer["plan"] = value
            elif key_norm in ["days", "dias", "días"]:
                translated_answer["days"] = value
            elif key_norm in ["dislikes", "ingredientesnodedeseados", "ingredientesnodeseados"]:
                translated_answer["dislikes"] = value
            elif key_norm in ["allergies", "alergias", "alergieslist"]:
                translated_answer["allergies"] = value
            elif key_norm in ["extraprotein", "protein", "gramosextraproteina", "gramosextraprotena", "gramos_extra_proteina"]:
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
            elif key_norm in ["activitylevel", "activity_level", "activity"]:
                translated_answer["activity_level"] = value
            elif key_norm in ["bodyfat", "body_fat", "bfpercent", "bf"]:
                translated_answer["body_fat"] = value
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
        # Accept variants and convert types
        try:
            w = answer.get("weight")
            if w is not None and str(w) != "":
                state.weight = float(w)
            wu = answer.get("weight_unit")
            if wu:
                state.weight_unit = str(wu)

            h = answer.get("height")
            if h is not None and str(h) != "":
                state.height = float(h)
            hu = answer.get("height_unit")
            if hu:
                state.height_unit = str(hu)

            a = answer.get("age")
            if a is not None and str(a) != "":
                state.age = int(a)

            s = answer.get("sex")
            if s:
                state.sex = str(s)

            al = answer.get("activity_level")
            if al:
                state.activity_level = str(al)

            bf = answer.get("body_fat")
            if bf is not None and str(bf) != "":
                state.body_fat = float(bf)

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

    elif step_name == "dislikes" and "dislikes" in answer or "Ingredientes_No_Deseados" in answer:
        data = answer.get("dislikes") or answer.get("Ingredientes_No_Deseados")
        state.dislikes = data if isinstance(data, list) else [data] if data else []
        step_to_render_name = steps_mapping["dislikes"]

    elif step_name == "allergies" and "allergies" in answer or "Alergias" in answer:
        data = answer.get("allergies") or answer.get("Alergias")
        state.allergies = data if isinstance(data, list) else [data] if data else []
        step_to_render_name = steps_mapping["allergies"]

    elif step_name == "extra_protein" and ("extra_protein_grams" in answer or "Gramos_Extra_Proteína" in answer):
        try:
            protein_input = answer.get("extra_protein_grams") or answer.get("Gramos_Extra_Proteína")
            if protein_input is not None and str(protein_input).isdigit() and 0 <= int(protein_input) <= 100:
                state.extra_protein_grams = int(protein_input)
            elif protein_input == "" or protein_input is None:
                state.extra_protein_grams = 0
            step_to_render_name = steps_mapping["extra_protein"]
        except Exception:
            state.extra_protein_grams = 0
            step_to_render_name = steps_mapping["extra_protein"]

    elif step_name == "review":
        # Generate final menu and compute nutrition summary
        state.menu = generate_menu(state)
        sessions[session_id] = state.model_dump()
        if not state.menu:
            return {"question": "Error: filters too strict. Go back and relax preferences.", "fields": []}

        # Nutrition calculation
        weight_kg = to_kg(state.weight, state.weight_unit) if state.weight else None
        height_cm = to_cm(state.height, state.height_unit) if state.height else None
        tmb = calc_tmb_mifflin(weight_kg, height_cm, state.age, state.sex)
        tdee = calc_tdee(tmb, state.activity_level) if tmb else None
        calorie_target = calc_calorie_target(tdee, state.objective) if tdee else None
        macros = calc_macros(calorie_target, state.objective, weight_kg)

        total_price = calculate_price(state.menu, state.extra_protein_grams)

        return {
            "menu": [m.model_dump() for m in state.menu],
            "price": total_price,
            "message": "Your menu is ready!",
            "nutrition": {
                "tmb": tmb,
                "tdee": tdee,
                "calorie_target": calorie_target,
                "macros": macros
            }
        }

    # persist and return next form
    state.current_step = step_to_render_name
    sessions[session_id] = state.model_dump()

    return get_form_fields(state.current_step, state)


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
    available_meals = filter_meals(state.dislikes, state.allergies)
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
    sessions[session_id] = state.model_dump()
    total_price = calculate_price(new_menu_objects, state.extra_protein_grams)
    return {"menu": state.menu, "price": total_price, "message": "Full menu regenerated!"}