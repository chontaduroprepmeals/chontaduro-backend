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

# Middleware para loggear bodies (útil para reproducir 422)
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
    """
    Normaliza claves comunes en meals.json (español/inglés) a las que espera el modelo interno.
    Mapea:
      nombre -> name
      tipo -> type
      ingredientes -> ingredients
      calorias -> calories
      precio -> price
      imagen -> image_url
      image_url stays image_url
    """
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
    # Asegurar campos mínimos
    if "ingredients" in out and isinstance(out["ingredients"], str):
        # si vienen como CSV -> split
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
            print("WARNING: meals.json no es una lista.")
except FileNotFoundError:
    print("WARNING: meals.json not found. Meal generation will fail.")
except json.JSONDecodeError:
    print("WARNING: meals.json could not be decoded. Check JSON format.")

# --- SESSIONS ---
sessions: Dict[str, Dict[str, Any]] = {}

steps_mapping = {
    "start": "pick_plan",
    "pick_plan": "duration",
    "duration": "dislikes",
    "dislikes": "allergies",
    "allergies": "extra_protein",
    "extra_protein": "review",
}

# --- MODELOS Pydantic ---
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

    model_config = {"extra": "ignore"}

class NextStepRequest(BaseModel):
    session_id: str
    step: str
    answer: Dict[str, Any] = Field(default_factory=dict)

    model_config = {"extra": "allow"}

# Para swap/redo mantengo modelos simples (pero en endpoints los parseo de forma tolerante)
class SwapMealRequest(BaseModel):
    session_id: str
    meal_to_swap: str

class RedoMenuRequest(BaseModel):
    session_id: str

# --- LÓGICA ---
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

# --- HELPERS UI FORM ---
def get_form_fields(step_name: str, state: Optional[SessionState] = None):
    if step_name == "pick_plan":
        return {
            "question": "¿Qué plan de dieta deseas seguir?",
            "fields": [
                {"name": "Plan", "type": "select", "options": [
                    "Plan 1: 1 comida al día",
                    "Plan 2: 2 comidas al día",
                    "Plan 3: 3 comidas al día (con postre)",
                    "Plan 4: 3 comidas al día (con extra de proteína)"
                ]}
            ]
        }
    elif step_name == "duration":
        return {
            "question": "¿Por cuántos días deseas este plan?",
            "fields": [
                {"name": "Días", "type": "number", "min": 1, "max": 30, "placeholder": "Ej: 7 días"}
            ]
        }
    elif step_name == "dislikes":
        return {
            "question": "Selecciona los ingredientes que NO te gustan (opcional):",
            "fields": [
                {"name": "Ingredientes_No_Deseados", "type": "multiselect", "options": [
                    "Oats", "Berries", "Milk", "Chicken", "Rice", "Broccoli",
                    "Salmon", "Lettuce", "Avocado", "Tofu", "Carrots"
                ]}
            ]
        }
    elif step_name == "allergies":
        return {
            "question": "¿Tienes alguna alergia alimentaria? (opcional)",
            "fields": [
                {"name": "Alergias", "type": "multiselect", "options": [
                    "Gluten", "Lactosa", "Nueces", "Mariscos", "Soya"
                ]}
            ]
        }
    elif step_name == "extra_protein":
        return {
            "question": "¿Cuántos gramos de proteína extra deseas por menú? (opcional)",
            "fields": [
                {"name": "Gramos_Extra_Proteína", "type": "number", "min": 0, "max": 100, "placeholder": "0"}
            ]
        }
    elif step_name == "review":
        if not state:
            return {"question": "Error de estado. Comienza de nuevo."}
        summary = (
            f"**Plan Seleccionado:** {state.plan} comidas/día por {state.days} días.<br>"
            f"**No me gusta:** {', '.join(state.dislikes) if state.dislikes else 'Ninguno'}<br>"
            f"**Alergias:** {', '.join(state.allergies) if state.allergies else 'Ninguna'}<br>"
            f"**Proteína Extra:** {state.extra_protein_grams} gramos."
        )
        return {
            "question": f"Resumen de tu pedido: ¿Deseas generar el menú?<br><br>{summary}",
            "fields": []
        }
    return {"question": "Paso no reconocido. Inicia de nuevo."}

# --- ENDPOINTS ---

def normalize_request_payload(payload: Dict[str, Any]) -> NextStepRequest:
    # Acepta sessionId / session_id / id
    session_id = payload.get("session_id") or payload.get("sessionId") or payload.get("id") or str(random.randint(1000, 9999))
    step = payload.get("step") or payload.get("current_step") or payload.get("currentStep") or "start"
    answer = payload.get("answer") or payload.get("answers") or payload.get("data") or {}
    # Aceptar strings "null" o None
    if answer is None:
        answer = {}
    return NextStepRequest(session_id=session_id, step=step, answer=answer)

@app.post("/next-step")
async def next_step(request: Request):
    payload = await request.json()
    print("Normalized incoming payload:", payload)
    try:
        req = normalize_request_payload(payload)
    except Exception as e:
        return JSONResponse(status_code=422, content={"detail": "Invalid payload", "error": str(e), "raw": payload})

    session_id = req.session_id
    step_name = req.step or "start"
    answer = req.answer or {}

    if step_name not in steps_mapping and step_name not in ["review", "start", "back"]:
        step_name = "start"

    if session_id not in sessions:
        sessions[session_id] = SessionState().model_dump()

    state = SessionState(**sessions[session_id])

    # Normalize answer keys to expected Spanish UI keys
    translated_answer = {}
    for key, value in (answer.items() if isinstance(answer, dict) else []):
        key_lower = str(key).lower().replace("_", "").replace("-", "")
        if key_lower in ["plan", "tipoplan"]:
            translated_answer["Plan"] = value
        elif key_lower in ["days", "dias"]:
            translated_answer["Días"] = value
        elif key_lower in ["dislikes", "ingredientesnodedeseados", "ingredientesnodeseados"]:
            translated_answer["Ingredientes_No_Deseados"] = value
        elif key_lower in ["allergies", "alergias"]:
            translated_answer["Alergias"] = value
        elif key_lower in ["extraprotein", "protein", "gramosextraproteina", "gramos_extra_proteina"]:
            translated_answer["Gramos_Extra_Proteína"] = value
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

    if step_name == "start":
        step_to_render_name = steps_mapping["start"]
    elif step_name == "pick_plan":
        plan_answer = answer.get("Plan")
        if plan_answer and isinstance(plan_answer, str):
            try:
                plan_str = plan_answer.split(":")[0].replace("Plan ", "").strip()
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
    elif step_name == "duration":
        try:
            days_input = answer.get("Días")
            if days_input is not None and str(days_input).isdigit() and 1 <= int(days_input) <= 30:
                state.days = int(days_input)
                step_to_render_name = steps_mapping["duration"]
            else:
                step_to_render_name = "duration"
        except Exception:
            step_to_render_name = "duration"
    elif step_name == "dislikes" and "Ingredientes_No_Deseados" in answer:
        data = answer["Ingredientes_No_Deseados"]
        state.dislikes = data if isinstance(data, list) else [data] if data else []
        step_to_render_name = steps_mapping["dislikes"]
    elif step_name == "allergies" and "Alergias" in answer:
        data = answer["Alergias"]
        state.allergies = data if isinstance(data, list) else [data] if data else []
        step_to_render_name = steps_mapping["allergies"]
    elif step_name == "extra_protein" and "Gramos_Extra_Proteína" in answer:
        try:
            protein_input = answer.get("Gramos_Extra_Proteína")
            if protein_input is not None and str(protein_input).isdigit() and 0 <= int(protein_input) <= 100:
                state.extra_protein_grams = int(protein_input)
            elif protein_input == "" or protein_input is None:
                state.extra_protein_grams = 0
            step_to_render_name = steps_mapping["extra_protein"]
        except Exception:
            state.extra_protein_grams = 0
            step_to_render_name = steps_mapping["extra_protein"]
    elif step_name == "review":
        state.menu = generate_menu(state)
        sessions[session_id] = state.model_dump()
        if not state.menu:
            return {"question": "Error: Los filtros son muy restrictivos. Vuelve atrás y ajusta tus preferencias.", "fields": []}
        total_price = calculate_price(state.menu, state.extra_protein_grams)
        return {"menu": [m.model_dump() for m in state.menu], "price": total_price, "message": "¡Tu menú está listo!"}

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
        return {"menu": [m.model_dump() for m in current_menu_objects], "price": calculate_price(current_menu_objects, state.extra_protein_grams), "message": "No hay reemplazos disponibles con tus filtros."}

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

    return {"menu": state.menu, "price": total_price, "message": f"Comida '{meal_to_swap_name}' reemplazada por '{new_meal.name}'."}

@app.post("/redo-menu")
async def redo_menu(request: Request):
    payload = await request.json()
    session_id = payload.get("session_id") or payload.get("sessionId")
    if not session_id or session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found.")
    state = SessionState(**sessions[session_id])
    new_menu_objects = generate_menu(state)
    if not new_menu_objects:
        return {"message": "No se pudo generar un nuevo menú con tus filtros actuales."}
    state.menu = [m.model_dump() for m in new_menu_objects]
    sessions[session_id] = state.model_dump()
    total_price = calculate_price(new_menu_objects, state.extra_protein_grams)
    return {"menu": state.menu, "price": total_price, "message": "¡Menú completo regenerado!"}