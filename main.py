# main.py
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
from pydantic import BaseModel, Field
import random, json, traceback
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

# Serve frontend
@app.get("/", response_class=HTMLResponse)
async def serve_frontend():
    return FileResponse("index.html")


# --- LOAD MEALS (expects English keys; tolerant with Spanish keys) ---
MEALS_DATA: List[Dict[str, Any]] = []

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

load_meals()


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
    extra_protein_grams: int = 0
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
    model_config = {"extra": "ignore"}


class NextStepRequest(BaseModel):
    session_id: str
    step: str
    answer: Dict[str, Any] = Field(default_factory=dict)
    model_config = {"extra": "allow"}


# --- HELPERS: normalization for incoming requests (tolerant) ---
def normalize_step_name(step: str) -> str:
    if not step:
        return "start"
    s = str(step).strip().lower()
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
    # fallback to start
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
        "note": "user_note", "usernote": "user_note"
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


# --- NUTRITION helpers ---
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
        return round(tdee - 400)
    if obj in ["gain muscle", "gain", "muscle"]:
        return round(tdee + 350)
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

    return {"calories": int(calories), "protein_grams": int(protein_grams), "fat_grams": int(fat_grams), "carbs_grams": int(carbs_grams), "pct_protein": pct_protein, "pct_fat": pct_fat, "pct_carbs": pct_carb}


# --- DIET / RESTRICTION KEYWORDS ---
MEAT_KEYWORDS = {"chicken","beef","pork","turkey","lamb","bacon","ham","steak"}
FISH_KEYWORDS = {"salmon","shrimp","fish","tuna","trout","cod","shellfish","prawns"}
DAIRY_KEYWORDS = {"milk","yogurt","cheese","butter","cream"}
EGG_KEYWORDS = {"egg","eggs"}
NUT_KEYWORDS = {"nut","nuts","almond","walnut","peanut"}
GLUTEN_KEYWORDS = {"wheat","barley","rye","gluten"}
SOY_KEYWORDS = {"soy","tofu","soy sauce"}
SESAME_KEYWORDS = {"sesame"}
CORN_KEYWORDS = {"corn"}

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


# --- BUSINESS LOGIC (MEALS) ---
def filter_meals(dislikes: List[str], allergies: List[str], dietary_restrictions: List[str], diet: Optional[str]) -> List[Meal]:
    undesired = set()
    for lst in (dislikes or []):
        if isinstance(lst, list):
            for it in lst:
                if it and isinstance(it, str):
                    if it.lower().startswith("none") or it.lower().startswith("i like"):
                        continue
                    undesired.add(it.strip().lower())
    for lst in (allergies or []):
        if isinstance(lst, list):
            for it in lst:
                if it and isinstance(it, str):
                    if it.lower().startswith("none"):
                        continue
                    undesired.add(it.strip().lower())
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
        if not is_meal_compatible_with_diet(ings, diet):
            continue
        conflict = False
        for u in undesired:
            if any(u in ing for ing in ings):
                conflict = True
                break
        if not conflict:
            try:
                out.append(Meal(**m))
            except Exception as e:
                print("meal validation error", e)
    return out

def generate_menu(state: SessionState) -> List[Meal]:
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
        if not day_items:
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


# --- UI form definitions (English labels) ---
def get_form_fields(step_name: str, state: Optional[SessionState] = None):
    if step_name == "pick_plan":
        return {"question":"Which plan do you want?","fields":[{"name":"Plan","type":"select","options":["Plan 1: 1 main meal per day","Plan 2: 2 main meals per day","Plan 3: 1 main meal + 1 breakfast","Plan 4: 2 main meals + 1 breakfast (full day)"]}],"current_step":"pick_plan"}
    if step_name == "objective":
        return {"question":"What is your main goal?","fields":[{"name":"Objective","type":"select","options":["Lose Fat","Gain Muscle","Maintain Shape"]}],"current_step":"objective"}
    if step_name == "personal_info":
        return {"question":"Tell us your personal data:","fields":[{"name":"Diet Preference","type":"select","options":["Omnivore","Vegetarian","Vegan","Pescatarian","Few restrictions"], "unit":"Choose the option that best describes your overall diet."},{"name":"Weight Unit","type":"select","options":["kg","lbs"]},{"name":"Weight","type":"number","placeholder":"e.g. 70","unit":"kg or lbs"},{"name":"Height Unit","type":"select","options":["cm","in"]},{"name":"Height","type":"number","placeholder":"e.g. 175","unit":"cm or in"},{"name":"Age","type":"number","placeholder":"e.g. 30"},{"name":"Sex","type":"select","options":["Male","Female"]},{"name":"Days per week","type":"select","options":["0","1-2","3-4","5-7"], "unit":"How many days do you exercise on average?"},{"name":"Avg session duration","type":"select","options":["<30","30-60","60-120"], "unit":"Typical session length (minutes)"},{"name":"Intensity","type":"select","options":["Low","Moderate","High"], "unit":"Select intensity (Low/Moderate/High)."},{"name":"Body Fat % (optional)","type":"number","placeholder":"e.g. 18","required":False}],"current_step":"personal_info"}
    if step_name == "restrictions":
        return {"question":"Please select any foods you avoid or are allergic to.","fields":[{"name":"Dietary Restrictions","type":"multiselect","options":["None - no special restrictions","No pork","No beef","No chicken / poultry","No seafood / shellfish","Gluten-free","Lactose-free / Dairy-free","Soy-free","Corn-free","Sesame-free"],"unit":"Personal or cultural preferences (not medical)"},{"name":"Food Allergies","type":"multiselect","options":["None - no allergies","Egg-free","Nut-free","Seafood-free","Dairy-free","Soy-free","Gluten-free"],"unit":"Medical allergies - select all that apply"}],"current_step":"restrictions"}
    if step_name == "duration":
        return {"question":"For how many days do you want this plan?","fields":[{"name":"Days","type":"number","min":1,"max":30,"placeholder":"e.g. 7"}],"current_step":"duration"}
    if step_name == "dislikes":
        return {"question":"Select ingredients you DON'T like (optional):","fields":[{"name":"Dislikes","type":"multiselect","options":["None - I like everything","Vegetables","Oats","Berries","Milk","Chicken","Rice","Broccoli","Salmon","Lettuce","Avocado","Tofu","Carrots","Beef","Pork","Shellfish","Banana"], "unit":"Select foods you simply dislike (taste)."}],"current_step":"dislikes"}
    if step_name == "review":
        if not state:
            return {"question":"State error. Start again.","current_step":"review"}
        summary = (f"Plan: {state.plan} for {state.days} days\nDiet: {state.diet_preference or 'N/A'}\nDietary restrictions: {', '.join(state.dietary_restrictions) if state.dietary_restrictions else 'None'}\nAllergies: {', '.join(state.allergies) if state.allergies else 'None'}\nDislikes: {', '.join(state.dislikes) if state.dislikes else 'None'}\nWeight: {state.weight or 'N/A'} {state.weight_unit}\nHeight: {state.height or 'N/A'} {state.height_unit}\nAge: {state.age or 'N/A'}\nActivity: {state.activity_days_bucket or 'N/A'} days, {state.activity_duration_bucket or 'N/A'} min, {state.activity_intensity or 'N/A'} intensity\n")
        return {"question": f"Review your info and generate the menu:\n\n{summary}", "fields": [], "current_step":"review"}
    return {"question":"Unknown step. Start again.","current_step":"start"}


# --- ENDPOINTS & FLOW HANDLER ---
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

    # handle back
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
            # IMPORTANT: dietary_restrictions is NOT read here (we ask it in the 'restrictions' step)
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
        ag = raw_answer.get("Food Allergies") or raw_answer.get("FoodAllergies") or answer.get("allergies")
        if ag:
            state.allergies = ag if isinstance(ag, list) else [ag]
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
            assessment = assess_menu_possibility(state)
            if not assessment["ok"]:
                return {"question": assessment.get("message", "Could not generate menu with current settings."), "fields": [], "current_step": state.current_step, "issue": assessment.get("reason"), "details": assessment.get("details", {})}
            state.menu = generate_menu(state)
            sessions[session_id] = state.model_dump()
            if not state.menu:
                return {"question": "Unexpected error: no menu items could be selected. Try changing plan or relaxing filters.", "fields": [], "current_step": state.current_step, "issue": "generation_failed"}
            weight_kg = to_kg(state.weight, state.weight_unit) if state.weight else None
            height_cm = to_cm(state.height, state.height_unit) if state.height else None
            tmb = calc_tmb_mifflin(weight_kg, height_cm, state.age, state.sex)
            tdee = None
            if tmb is not None:
                tdee = round(tmb * compute_activity_factor(state.activity_days_bucket or "0", state.activity_duration_bucket or "<30", state.activity_intensity or "Low"), 1)
            calorie_target = calc_calorie_target(tdee, state.objective) if tdee else None
            macros = calc_macros(calorie_target, state.objective, to_kg(state.weight, state.weight_unit) if state.weight else None)
            total_price = calculate_price(state.menu, 0)
            sessions[session_id] = state.model_dump()
            return {"menu":[m.model_dump() for m in state.menu],"price":total_price,"message":"Your menu is ready!","nutrition":{"tmb":tmb,"tdee":tdee,"calorie_target":calorie_target,"macros":macros},"current_step":state.current_step}
        except Exception as e:
            tb = traceback.format_exc()
            print(f"[ERROR] menu generation failed for session {session_id}:\n{tb}")
            return JSONResponse(status_code=500, content={"error":"internal_server_error","detail":str(e),"trace":tb})

    else:
        step_to_render_name = "start"

    state.current_step = step_to_render_name
    sessions[session_id] = state.model_dump()
    return get_form_fields(state.current_step, state)


# --- Additional endpoints ---
@app.post("/add-protein")
async def add_protein(request: Request):
    payload = await request.json()
    sid = payload.get("session_id") or payload.get("sessionId")
    extra = payload.get("extra_protein_grams") or payload.get("extraProtein") or 0
    try:
        extra = int(extra)
    except Exception:
        extra = 0
    if not sid or sid not in sessions:
        raise HTTPException(status_code=404, detail="Session not found.")
    state = SessionState(**sessions[sid])
    state.extra_protein_grams = extra
    sessions[sid] = state.model_dump()
    menu_objs = [Meal(**m) if isinstance(m, dict) else m for m in state.menu]
    return {"menu":[m.model_dump() for m in menu_objs], "price": calculate_price(menu_objs, extra), "message": f"Added {extra} g extra protein."}

@app.post("/add-note")
async def add_note(request: Request):
    payload = await request.json()
    sid = payload.get("session_id") or payload.get("sessionId")
    note = payload.get("note") or payload.get("user_note") or ""
    if not sid or sid not in sessions:
        raise HTTPException(status_code=404, detail="Session not found.")
    state = SessionState(**sessions[sid])
    state.user_note = str(note)[:1000]
    sessions[sid] = state.model_dump()
    return {"menu": state.menu, "price": calculate_price([Meal(**m) if isinstance(m, dict) else m for m in state.menu], state.extra_protein_grams), "message":"Note saved.", "note": state.user_note}

@app.post("/swap-meal")
async def swap_meal(request: Request):
    payload = await request.json()
    sid = payload.get("session_id") or payload.get("sessionId")
    meal_to_swap = payload.get("meal_to_swap") or payload.get("mealToSwap")
    if not sid or sid not in sessions:
        raise HTTPException(status_code=404, detail="Session not found.")
    state = SessionState(**sessions[sid])
    current_menu = [Meal(**m) if isinstance(m, dict) else m for m in state.menu]
    target = next((m for m in current_menu if m.name == meal_to_swap), None)
    if not target:
        raise HTTPException(status_code=404, detail="Meal not in current menu.")
    avail = filter_meals(state.dislikes, state.allergies, state.dietary_restrictions, state.diet_preference)
    potential = [m for m in avail if m.type == target.type and m.name != target.name and m.name not in [x.name for x in current_menu]]
    if not potential:
        return {"menu":[m.model_dump() for m in current_menu], "price": calculate_price(current_menu, state.extra_protein_grams), "message":"No replacements available."}
    new = random.choice(potential)
    new_menu = []
    replaced = False
    for m in current_menu:
        if not replaced and m.name == meal_to_swap:
            new_menu.append(new)
            replaced = True
        else:
            new_menu.append(m)
    state.menu = [m.model_dump() for m in new_menu]
    sessions[sid] = state.model_dump()
    return {"menu": state.menu, "price": calculate_price([Meal(**m) if isinstance(m, dict) else m for m in state.menu], state.extra_protein_grams), "message":f"Swapped {meal_to_swap} -> {new.name}"}

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
    state.menu = [m.model_dump() for m in menu_objs]
    state.extra_protein_grams = 0
    sessions[sid] = state.model_dump()
    return {"menu": state.menu, "price": calculate_price(menu_objs, 0), "message":"Menu regenerated."}

def calculate_price(menu: List[Meal], extra_protein: int) -> float:
    base = 0.0
    for m in menu:
        if isinstance(m, dict):
            base += float(m.get("price", 0))
        elif hasattr(m, "price"):
            base += float(m.price)
    prot_cost = (extra_protein or 0) * 1.0
    return round(base + prot_cost, 2)