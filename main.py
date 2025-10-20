from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import random
import json

app = FastAPI()

# ---------------------------
# Configurar CORS
# ---------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Cambia "*" por tu dominio Carrd o localhost
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------
# Modelos de entrada
# ---------------------------
class UserInput(BaseModel):
    session_id: str
    step: str
    answer: dict = {}

class SwapMealInput(BaseModel):
    session_id: str
    meal_name: str

class AddProteinInput(BaseModel):
    session_id: str
    extra_protein_g: int

# ---------------------------
# Sesiones en memoria
# ---------------------------
sessions = {}

# ---------------------------
# Cargar comidas desde JSON
# ---------------------------
with open("meals.json", "r") as f:
    all_meals = json.load(f)

# ---------------------------
# Función para filtrar comidas según categoría, dislikes y alergias
# ---------------------------
def filter_meals(category=None, dislikes=None, allergies=None):
    meals = all_meals.copy()
    if category:
        meals = [m for m in meals if m["category"].lower() == category.lower()]
    if dislikes:
        meals = [m for m in meals if not any(d.lower() in [ing.lower() for ing in m.get("ingredients", [])] for d in dislikes)]
    if allergies:
        meals = [m for m in meals if not any(a.lower() in [ing.lower() for ing in m.get("ingredients", [])] for a in allergies)]
    return meals

# ---------------------------
# Generar menú personalizado
# ---------------------------
def generate_menu(session_id):
    session = sessions[session_id]

    plan = session.get("pick_plan", {}).get("Plan")
    duration = int(session.get("duration", {}).get("Duration", 1))
    preferences = session.get("preferences", {}).get("Dietary Preferences", [])
    dislikes = session.get("preferences", {}).get("Dislikes", [])
    allergies = session.get("allergies", {}).get("Allergies", [])

    category_map = {
        "Plan 1": "Vegetarian",
        "Plan 2": "Vegan",
        "Plan 3": "Pescatarian",
        "Plan 4": "Omnivore"
    }
    category = category_map.get(plan)
    available_meals = filter_meals(category, dislikes, allergies)

    if len(available_meals) < 3:
        raise HTTPException(status_code=400, detail="Not enough meals available for your preferences/allergies.")

    menu = random.sample(available_meals, 3)

    plan_price_map = {"Plan 1": 12, "Plan 2": 12, "Plan 3": 15, "Plan 4": 14}
    price = sum([plan_price_map.get(plan, 12) for _ in menu]) * duration

    sessions[session_id]['menu'] = menu
    sessions[session_id]['price'] = price
    return {"menu": menu, "price": price}

# ---------------------------
# Flujo principal /next-step
# ---------------------------
@app.post("/next-step")
def next_step(input: UserInput):
    session_id = input.session_id
    step = input.step
    answer = input.answer

    if session_id not in sessions:
        sessions[session_id] = {}

    if answer:
        sessions[session_id][step] = answer

    steps_mapping = {
        "pick_plan": {"question": "Select your plan", "fields": ["Plan"]},
        "duration": {"question": "Select duration (days)", "fields": ["Duration"]},
        "personal_data": {"question": "Enter your personal data", "fields": ["Age", "Weight", "Sex"]},
        "preferences": {"question": "Select your dietary preferences", "fields": ["Dietary Preferences", "Dislikes"]},
        "allergies": {"question": "Indicate your allergies", "fields": ["Allergies"]}
    }

    steps_order = ["pick_plan", "duration", "personal_data", "preferences", "allergies", "generate_menu"]

    # Calcular siguiente paso
    try:
        next_index = steps_order.index(step) + 1
        next_step_name = steps_order[next_index]
    except IndexError:
        next_step_name = "generate_menu"

    if next_step_name == "generate_menu":
        return generate_menu(session_id)

    step_info = steps_mapping.get(next_step_name, {"question": f"Next step: {next_step_name}", "fields": []})
    return {"question": step_info["question"], "fields": step_info["fields"]}

# ---------------------------
# Swap meal
# ---------------------------
@app.post("/swap-meal")
def swap_meal(input: SwapMealInput):
    session_id = input.session_id
    meal_name = input.meal_name

    if session_id not in sessions or 'menu' not in sessions[session_id]:
        raise HTTPException(status_code=400, detail="No menu generated for this session")

    menu = sessions[session_id]['menu']
    plan = sessions[session_id].get("pick_plan", {}).get("Plan")
    dislikes = sessions[session_id].get("preferences", {}).get("Dislikes", [])
    allergies = sessions[session_id].get("allergies", {}).get("Allergies", [])

    category_map = {
        "Plan 1": "Vegetarian",
        "Plan 2": "Vegan",
        "Plan 3": "Pescatarian",
        "Plan 4": "Omnivore"
    }
    category = category_map.get(plan)
    available_meals = filter_meals(category, dislikes, allergies)

    new_meal = random.choice([m for m in available_meals if m['name'] != meal_name])
    for i, m in enumerate(menu):
        if m['name'] == meal_name:
            menu[i] = new_meal
            break

    sessions[session_id]['menu'] = menu
    price = sessions[session_id]['price']
    return {"menu": menu, "price": price}

# ---------------------------
# Redo menu
# ---------------------------
@app.post("/redo-menu")
def redo_menu(input: UserInput):
    session_id = input.session_id
    return generate_menu(session_id)

# ---------------------------
# Add protein
# ---------------------------
@app.post("/add-protein")
def add_protein(input: AddProteinInput):
    session_id = input.session_id

    if session_id not in sessions or 'menu' not in sessions[session_id]:
        raise HTTPException(status_code=400, detail="No menu generated for this session")

    menu = sessions[session_id]['menu']
    for m in menu:
        m['calories'] += input.extra_protein_g * 4  # 4 cal per gram protein

    sessions[session_id]['menu'] = menu
    price = sessions[session_id]['price']
    return {"menu": menu, "price": price, "message": f"{input.extra_protein_g}g extra protein added."}
