from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import random
import json

app = FastAPI()

# Agregar CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # o ["https://plan1chontaduro.carrd.co"] para restringir
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Cargar comidas desde JSON
with open("meals.json", "r") as f:
    meals = json.load(f)

# Sessions temporales en memoria
sessions = {}

# Modelo de entrada
class UserInput(BaseModel):
    session_id: str
    step: str
    answer: dict  # Diccionario con respuestas del usuario

# Flujo principal
@app.post("/next-step")
def next_step(input: UserInput):
    session_id = input.session_id
    step = input.step
    answer = input.answer

    if session_id not in sessions:
        sessions[session_id] = {}
    sessions[session_id][step] = answer

    steps_order = [
        "pick_plan",
        "duration",
        "personal_data",
        "preferences",
        "allergies",
        "generate_menu"
    ]

    try:
        next_index = steps_order.index(step) + 1
        next_step_name = steps_order[next_index]
    except IndexError:
        next_step_name = "generate_menu"

    if next_step_name == "personal_data":
        return {"question": "Por favor ingresa tus datos personales",
                "fields": ["Edad", "Peso", "Sexo de nacimiento", "% Grasa corporal (opcional)", "Objetivos"]}
    elif next_step_name == "preferences":
        return {"question": "Indica tus preferencias alimenticias",
                "fields": ["Preferencias alimenticias", "Ingredientes que no te gustan"]}
    elif next_step_name == "allergies":
        return {"question": "Indica tus alergias",
                "fields": ["Alergias"]}
    elif next_step_name == "generate_menu":
        return generate_menu(session_id)
    else:
        return {"question": f"Siguiente paso: {next_step_name}"}

# Generar menú
def generate_menu(session_id: str):
    user_data = sessions.get(session_id, {})
    preferences = user_data.get("preferences", {})
    allergies = user_data.get("allergies", {}).get("Alergias", [])

    filtered_meals = [
        meal for meal in meals
        if meal.get("category") in preferences.get("Preferencias alimenticias", ["Omnivoro"])
        and meal.get("name") not in allergies
    ]

    if not filtered_meals:
        filtered_meals = meals

    menu = random.sample(filtered_meals, min(5, len(filtered_meals)))
    sessions[session_id]["menu"] = menu
    price = sum([meal.get("price", 10) for meal in menu])

    return {"menu": [{"name": m["name"], "image": m["image_url"], "calories": m["calories"]} for m in menu],
            "price": price,
            "message": "Aquí está tu menú personalizado"}

# Swap de comida
class SwapInput(BaseModel):
    session_id: str
    meal_name: str

@app.post("/swap-meal")
def swap_meal(input: SwapInput):
    session_id = input.session_id
    meal_name = input.meal_name

    if session_id not in sessions or "menu" not in sessions[session_id]:
        raise HTTPException(status_code=404, detail="Menú no encontrado")

    current_menu = sessions[session_id]["menu"]
    possible_meals = [meal for meal in meals if meal["name"] != meal_name]

    if not possible_meals:
        raise HTTPException(status_code=400, detail="No hay comidas disponibles para swap")

    new_meal = random.choice(possible_meals)
    for i, meal in enumerate(current_menu):
        if meal["name"] == meal_name:
            current_menu[i] = new_meal
            break

    price = sum([m.get("price", 10) for m in current_menu])
    sessions[session_id]["menu"] = current_menu

    return {"menu": [{"name": m["name"], "image": m["image_url"], "calories": m["calories"]} for m in current_menu],
            "price": price,
            "message": f"{meal_name} ha sido reemplazado"}

# Redo completo del menú
@app.post("/redo-menu")
def redo_menu(input: UserInput):
    session_id = input.session_id
    return generate_menu(session_id)

# Extra proteína
class ProteinInput(BaseModel):
    session_id: str
    extra_protein_g: int

@app.post("/add-protein")
def add_protein(input: ProteinInput):
    session_id = input.session_id
    if session_id not in sessions or "menu" not in sessions[session_id]:
        raise HTTPException(status_code=404, detail="Menú no encontrado")

    current_menu = sessions[session_id]["menu"]
    extra_cost = input.extra_protein_g * 0.5
    base_price = sum([meal.get("price", 10) for meal in current_menu])
    total_price = base_price + extra_cost

    return {"menu": [{"name": m["name"], "image": m["image_url"], "calories": m["calories"]} for m in current_menu],
            "price": total_price,
            "message": f"Se agregó {input.extra_protein_g}g de proteína extra"}