from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import random
import json

app = FastAPI()

# ---------------------------
# CORS
# ---------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------
# Modelos
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
    target: str  # "all" o nombre de la comida

# ---------------------------
# Sesiones
# ---------------------------
sessions = {}

# ---------------------------
# Cargar comidas
# ---------------------------
with open("meals.json", "r") as f:
    all_meals = json.load(f)

# ---------------------------
# Función para filtrar comidas según categoría, dislikes y alergias
# ---------------------------
def filter_meals(category=None, dislikes=None, allergies=None, type_filter=None):
    meals = all_meals.copy()
    if category:
        meals = [m for m in meals if m["category"] == category]
    if type_filter:
        meals = [m for m in meals if m["type"] == type_filter]
    if dislikes:
        meals = [m for m in meals if not any(d.lower() in [i.lower() for i in m["ingredients"]] for d in dislikes)]
    if allergies:
        meals = [m for m in meals if not any(a.lower() in [i.lower() for i in m["ingredients"]] for a in allergies)]
    return meals

# ---------------------------
# Generar menú
# ---------------------------
def generate_menu(session_id):
    session = sessions[session_id]
    plan = session.get("pick_plan", {}).get("Plan")
    days = int(session.get("duration", {}).get("Duration", 1))
    preferences = session.get("preferences", {}).get("Dietary Preferences", [])
    dislikes = session.get("preferences", {}).get("Dislikes", [])
    allergies = session.get("allergies", {}).get("Allergies", [])
    
    # Determinar tipos de comidas por plan
    plan_types = {
        "Plan 1": ["main"],
        "Plan 2": ["main", "dinner"],
        "Plan 3": ["breakfast", "main"],
        "Plan 4": ["breakfast", "main", "dinner"]
    }
    types = plan_types.get(plan, ["main"])
    
    menu = []
    for t in types:
        available = filter_meals(plan, dislikes, allergies, t)
        if not available:
            raise HTTPException(status_code=400, detail=f"No meals available for {t}")
        for _ in range(days):
            menu.append(random.choice(available))
    
    # Precio total
    price = sum(m["price"] for m in menu)
    
    sessions[session_id]['menu'] = menu
    sessions[session_id]['price'] = price
    return {"menu": menu, "price": price}

# ---------------------------
# Flujo de pasos
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
        "pick_plan": {
            "question": "Pick your plan",
            "fields": [{"name": "Plan", "type": "select", "options": ["Plan 1","Plan 2","Plan 3","Plan 4"]}]
        },
        "duration": {
            "question": "How many days?",
            "fields": [{"name": "Duration", "type": "select", "options": ["1","2","3","4","5","6","7"]}]
        },
        "personal_data": {
            "question": "Enter your personal data",
            "fields": [
                {"name": "Age", "type": "number"},
                {"name": "Weight", "type": "number"},
                {"name": "Height", "type": "number"},
                {"name": "Gender", "type": "select", "options": ["M","F"]},
                {"name": "Goal", "type": "select", "options": ["Lose Fat","Maintain","Gain Muscle"]}
            ]
        },
        "preferences": {
            "question": "Dietary preferences",
            "fields": [
                {"name": "Dietary Preferences", "type": "multiselect", "options": ["Vegan","Vegetarian","Pescatarian","Omnivore","No preference"]},
                {"name": "Dislikes", "type": "multiselect", "options": ["Nuts","Gluten","Dairy","Eggs","Soy","Fish","Shellfish","Meat","Peanuts","No dislikes"]}
            ]
        },
        "allergies": {
            "question": "Allergies",
            "fields": [
                {"name": "Allergies", "type": "multiselect", "options": ["Nuts","Gluten","Dairy","Eggs","Soy","Fish","Shellfish","Meat","Peanuts","No allergies"]}
            ]
        }
    }

    steps_order = ["pick_plan","duration","personal_data","preferences","allergies","generate_menu"]
    try:
        next_index = steps_order.index(step) + 1
        next_step_name = steps_order[next_index]
    except IndexError:
        next_step_name = "generate_menu"

    if next_step_name == "generate_menu":
        return generate_menu(session_id)

    return {"question": steps_mapping[next_step_name]["question"], "fields": steps_mapping[next_step_name]["fields"]}

# ---------------------------
# Swap meal
# ---------------------------
@app.post("/swap-meal")
def swap_meal(input: SwapMealInput):
    session_id = input.session_id
    meal_name = input.meal_name
    if session_id not in sessions or 'menu' not in sessions[session_id]:
        raise HTTPException(status_code=400, detail="No menu generated")
    
    menu = sessions[session_id]['menu']
    plan = sessions[session_id].get("pick_plan", {}).get("Plan")
    dislikes = sessions[session_id].get("preferences", {}).get("Dislikes", [])
    allergies = sessions[session_id].get("allergies", {}).get("Allergies", [])

    plan_types = {
        "Plan 1": ["main"],
        "Plan 2": ["main","dinner"],
        "Plan 3": ["breakfast","main"],
        "Plan 4": ["breakfast","main","dinner"]
    }
    types = plan_types.get(plan, ["main"])
    
    # Filtrar comidas disponibles
    available = []
    for t in types:
        available.extend(filter_meals(plan, dislikes, allergies, t))
    
    new_meal = random.choice([m for m in available if m['name'] != meal_name])
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
        raise HTTPException(status_code=400, detail="No menu generated")
    
    menu = sessions[session_id]['menu']
    if input.target == "all":
        per_meal = input.extra_protein_g / len(menu)
        for m in menu:
            m["calories"] += per_meal * 4
    else:
        for m in menu:
            if m["name"] == input.target:
                m["calories"] += input.extra_protein_g * 4
                break

    sessions[session_id]['menu'] = menu
    sessions[session_id]['price'] += input.extra_protein_g  # 1$ por gramo extra
    return {"menu": menu, "price": sessions[session_id]['price']}
