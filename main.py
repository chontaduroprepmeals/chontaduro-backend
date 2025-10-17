from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import random
import json

app = FastAPI()

# Configurar CORS para permitir llamadas desde cualquier origen (o tu dominio Carrd)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Cambia "*" por tu dominio Carrd si quieres más seguridad
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
# Almacenamiento en memoria de sesiones
# ---------------------------
sessions = {}

# ---------------------------
# Datos de ejemplo de menús
# ---------------------------
example_menu = [
    {"name": "Chicken Bowl", "calories": 500, "image": "https://via.placeholder.com/200"},
    {"name": "Vegan Salad", "calories": 350, "image": "https://via.placeholder.com/200"},
    {"name": "Beef Wrap", "calories": 450, "image": "https://via.placeholder.com/200"}
]

# ---------------------------
# Función para generar menú
# ---------------------------
def generate_menu(session_id):
    menu = random.sample(example_menu, 3)
    price = sum([10 for _ in menu])  # ejemplo simple: $10 cada plato
    sessions[session_id]['menu'] = menu
    return {"menu": menu, "price": price}

# ---------------------------
# Endpoint principal: siguiente paso
# ---------------------------
@app.post("/next-step")
def next_step(input: UserInput):
    session_id = input.session_id
    step = input.step
    answer = input.answer

    if session_id not in sessions:
        sessions[session_id] = {}

    # Guardar la respuesta solo si answer no está vacío
    if answer:
        sessions[session_id][step] = answer

    # ---------------------------
    # Mostrar el paso actual si no tiene datos (para forzar primer paso)
    # ---------------------------
    steps_mapping = {
        "pick_plan": {"question": "Selecciona tu plan", "fields": ["Plan"]},
        "duration": {"question": "Selecciona duración", "fields": ["Duración"]},
        "personal_data": {"question": "Ingresa tus datos personales", "fields": ["Edad", "Peso", "Sexo"]},
        "preferences": {"question": "Indica tus preferencias alimenticias", "fields": ["Preferencias alimenticias", "Ingredientes que no te gustan"]},
        "allergies": {"question": "Indica tus alergias", "fields": ["Alergias"]}
    }

    if step not in sessions[session_id]:
        step_info = steps_mapping.get(step, {"question": f"Siguiente paso: {step}", "fields": []})
        return {"question": step_info["question"], "fields": step_info["fields"]}

    # ---------------------------
    # Avanzar al siguiente paso
    # ---------------------------
    steps_order = ["pick_plan", "duration", "personal_data", "preferences", "allergies", "generate_menu"]
    try:
        next_index = steps_order.index(step) + 1
        next_step_name = steps_order[next_index]
    except IndexError:
        next_step_name = "generate_menu"

    if next_step_name == "generate_menu":
        return generate_menu(session_id)

    step_info = steps_mapping.get(next_step_name, {"question": f"Siguiente paso: {next_step_name}", "fields": []})
    return {"question": step_info["question"], "fields": step_info["fields"]}

# ---------------------------
# Endpoint para cambiar un plato
# ---------------------------
@app.post("/swap-meal")
def swap_meal(input: SwapMealInput):
    session_id = input.session_id
    meal_name = input.meal_name

    if session_id not in sessions or 'menu' not in sessions[session_id]:
        raise HTTPException(status_code=400, detail="No hay menú generado para esta sesión")

    menu = sessions[session_id]['menu']
    # Reemplazar plato seleccionado por uno nuevo aleatorio
    new_meal = random.choice([m for m in example_menu if m['name'] != meal_name])
    for i, m in enumerate(menu):
        if m['name'] == meal_name:
            menu[i] = new_meal
            break

    sessions[session_id]['menu'] = menu
    price = sum([10 for _ in menu])
    return {"menu": menu, "price": price}

# ---------------------------
# Endpoint para rehacer menú completo
# ---------------------------
@app.post("/redo-menu")
def redo_menu(input: UserInput):
    session_id = input.session_id
    return generate_menu(session_id)

# ---------------------------
# Endpoint para agregar proteína extra
# ---------------------------
@app.post("/add-protein")
def add_protein(input: AddProteinInput):
    session_id = input.session_id

    if session_id not in sessions or 'menu' not in sessions[session_id]:
        raise HTTPException(status_code=400, detail="No hay menú generado para esta sesión")

    menu = sessions[session_id]['menu']
    # Aumentar calorías como ejemplo por proteína extra
    for m in menu:
        m['calories'] += input.extra_protein_g * 4  # 4 cal por gr de proteína extra

    sessions[session_id]['menu'] = menu
    price = sum([10 for _ in menu])
    return {"menu": menu, "price": price, "message": f"Se agregaron {input.extra_protein_g}g de proteína extra a tu menú."}