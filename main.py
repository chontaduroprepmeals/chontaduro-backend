from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import random
import json

app = FastAPI()

# --- CORS ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Modelos ---
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
    distribute_all: bool = True
    meal_name: str = None  # si quiere ponerlo solo en una comida

# --- Sesiones ---
sessions = {}

# --- Cargar comidas ---
with open("meals.json", "r") as f:
    all_meals = json.load(f)

# --- Filtrar comidas ---
def filter_meals(meal_type=None, dislikes=None, allergies=None):
    meals = all_meals.copy()
    if meal_type:
        meals = [m for m in meals if m["type"] == meal_type]
    if dislikes:
        meals = [m for m in meals if not any(d.lower() in [i.lower() for i in m.get("ingredients", [])] for d in dislikes)]
    if allergies:
        meals = [m for m in meals if not any(a.lower() in [i.lower() for i in m.get("ingredients", [])] for a in allergies)]
    return meals

# --- Cálculo genérico de calorías según sexo y objetivo ---
def calculate_calories(weight_lbs, height_in, age, sex, goal):
    # Conversión a kg y cm
    weight = weight_lbs * 0.453592
    height = height_in * 2.54
    if sex.lower() == "m":
        bmr = 10*weight + 6.25*height - 5*age + 5
    else:
        bmr = 10*weight + 6.25*height - 5*age - 161
    if goal == "lose fat":
        return int(bmr * 1.2)
    elif goal == "gain muscle":
        return int(bmr * 1.5)
    else:
        return int(bmr * 1.35)  # maintain

# --- Generar menú ---
def generate_menu(session_id):
    session = sessions[session_id]
    plan = session.get("pick_plan", {}).get("Plan")
    days = int(session.get("duration", {}).get("Days", 1))
    preferences = session.get("preferences", {}).get("Dietary Preferences", [])
    dislikes = session.get("preferences", {}).get("Dislikes", [])
    allergies = session.get("allergies", {}).get("Allergies", [])
    # Datos personales
    personal = session.get("personal_data", {})
    calories_needed = calculate_calories(
        weight_lbs=float(personal.get("Weight", 0)),
        height_in=float(personal.get("Height", 0)),
        age=int(personal.get("Age", 0)),
        sex=personal.get("Gender", "F"),
        goal=personal.get("Goal", "maintain")
    )

    menu = []
    type_map = {
        "Plan 1": {"Main Meal": 1, "Breakfast": 0},
        "Plan 2": {"Main Meal": 2, "Breakfast": 0},
        "Plan 3": {"Main Meal": 1, "Breakfast": 1},
        "Plan 4": {"Main Meal": 2, "Breakfast": 1}
    }
    for day in range(days):
        for t, count in type_map.get(plan, {}).items():
            available = filter_meals(t, dislikes, allergies)
            if not available:
                continue
            for _ in range(count):
                menu.append(random.choice(available))

    # Precio
    total_price = sum([m["price"] for m in menu])
    sessions[session_id]['menu'] = menu
    sessions[session_id]['price'] = total_price
    return {"menu": menu, "price": total_price}

# --- Endpoints ---
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
        "pick_plan": {"question": "Pick your plan", "fields":[{"name":"Plan","type":"select","options":["Plan 1","Plan 2","Plan 3","Plan 4"]}]},
        "duration": {"question":"How many days?","fields":[{"name":"Days","type":"select","options":["1","2","3","4","5","6","7"]}]},
        "personal_data":{"question":"Enter your personal data","fields":[
            {"name":"Age","type":"number"},
            {"name":"Weight","type":"number"},
            {"name":"Height","type":"number"},
            {"name":"Gender","type":"select","options":["M","F"]},
            {"name":"Goal","type":"select","options":["lose fat","maintain","gain muscle"]}
        ]},
        "preferences":{"question":"Dietary Preferences","fields":[{"name":"Dietary Preferences","type":"select","options":["Vegetarian","Vegan","Pescatarian","Omnivore"]},
        {"name":"Dislikes","type":"multiselect","options":["Nuts","Gluten","Dairy","Eggs","Soy","Fish","Shellfish","Meat","Peanuts","None"]}]},
        "allergies":{"question":"Allergies","fields":[{"name":"Allergies","type":"multiselect","options":["Nuts","Gluten","Dairy","Eggs","Soy","Fish","Shellfish","Meat","Peanuts","None"]}]}
    }
    steps_order = ["pick_plan","duration","personal_data","preferences","allergies","generate_menu"]

    try:
        next_index = steps_order.index(step)+1
        next_step_name = steps_order[next_index]
    except IndexError:
        next_step_name="generate_menu"

    if next_step_name=="generate_menu":
        return generate_menu(session_id)

    return {"question":steps_mapping[next_step_name]["question"],"fields":steps_mapping[next_step_name]["fields"]}

# --- Add protein ---
@app.post("/add-protein")
def add_protein(input: AddProteinInput):
    session_id = input.session_id
    menu = sessions[session_id].get('menu', [])
    if not menu:
        raise HTTPException(status_code=400, detail="No menu generated")
    # Distribuir proteína
    if input.distribute_all:
        per_meal = input.extra_protein_g / len(menu)
        for m in menu:
            m['calories'] += per_meal*4
            m['price'] += per_meal*1  # $1 por gramo
    else:
        for m in menu:
            if m['name']==input.meal_name:
                m['calories'] += input.extra_protein_g*4
                m['price'] += input.extra_protein_g*1
    total_price = sum([m["price"] for m in menu])
    sessions[session_id]['menu'] = menu
    sessions[session_id]['price'] = total_price
    return {"menu":menu,"price":total_price,"message":"Protein added"}

