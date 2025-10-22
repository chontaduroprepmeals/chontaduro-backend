from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
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

# --- Modelos Pydantic ---

class UserInput(BaseModel):
    session_id: str
    step: str # El paso actual (ej. 'pick_plan', 'allergies', o 'start', 'back')
    answer: Dict[str, Any] = {} # Respuesta del formulario

class AddProteinInput(BaseModel):
    session_id: str
    extra_protein_g: int
    distribute_all: bool = True
    meal_name: Optional[str] = None

class SwapInput(BaseModel):
    session_id: str
    meal_name: str

class SessionInput(BaseModel):
    session_id: str

# --- Sesiones y Data ---
sessions: Dict[str, Dict[str, Any]] = {}

try:
    with open("meals.json", "r") as f:
        all_meals = json.load(f)
except FileNotFoundError:
    print("WARNING: meals.json not found. Meal functions will not work.")
    all_meals = []

# --- Configuración del Flujo ---

# Pasos interactivos del formulario
steps_order = ["pick_plan", "duration", "personal_data", "preferences", "allergies"]

# Estructura de cada paso del formulario (para el frontend)
steps_mapping = {
    "pick_plan": {"question": "Pick your plan", "fields":[{"name":"Plan","type":"select","options":["Plan 1","Plan 2","Plan 3","Plan 4"]}]},
    "duration": {"question":"How many days?","fields":[{"name":"Days","type":"select","options":["1","2","3","4","5","6","7"]}]},
    "personal_data":{"question":"Enter your personal data","fields":[
        {"name":"Age","type":"number"},
        {"name":"Weight","type":"number", "unit":"lbs"},
        {"name":"Height","type":"number", "unit":"in"},
        {"name":"Gender","type":"select","options":["M","F"]},
        {"name":"Goal","type":"select","options":["lose fat","maintain","gain muscle"]}
    ]},
    "preferences":{"question":"Dietary Preferences","fields":[
        {"name":"Dietary Preferences","type":"select","options":["Vegetarian","Vegan","Pescatarian","Omnivore"]},
        {"name":"Dislikes","type":"multiselect","options":["Nuts","Gluten","Dairy","Eggs","Soy","Fish","Shellfish","Meat","Peanuts","None"]}
    ]},
    "allergies":{"question":"Allergies","fields":[
        {"name":"Allergies","type":"multiselect","options":["Nuts","Gluten","Dairy","Eggs","Soy","Fish","Shellfish","Meat","Peanuts","None"]}
    ]}
}

# --- Funciones Clave del Backend ---

def filter_meals(meal_type: Optional[str] = None, dislikes: List[str] = None, allergies: List[str] = None) -> List[Dict[str, Any]]:
    """Filtra comidas según tipo, aversiones e ingredientes alérgenos."""
    meals = all_meals.copy()
    
    if meal_type:
        meals = [m for m in meals if m.get("type") == meal_type]
    
    # Asegurar que las restricciones sean listas de strings en minúsculas
    dislikes = [d.lower() for d in dislikes or [] if d.lower() != "none"]
    allergies = [a.lower() for a in allergies or [] if a.lower() != "none"]

    def is_compatible(meal, restrictions):
        ingredients = [i.lower() for i in meal.get("ingredients", [])]
        return not any(r in ingredients for r in restrictions)

    if dislikes:
        meals = [m for m in meals if is_compatible(m, dislikes)]
    
    if allergies:
        meals = [m for m in meals if is_compatible(m, allergies)]
        
    return meals

def calculate_calories(weight_lbs: float, height_in: float, age: int, sex: str, goal: str) -> int:
    """Calcula las calorías diarias usando el BMR y factor de actividad/objetivo."""
    weight_kg = weight_lbs * 0.453592
    height_cm = height_in * 2.54
    sex_upper = sex.upper()
    
    # Fórmula de Mifflin-St Jeor (adaptada)
    if sex_upper == "M":
        bmr = 10 * weight_kg + 6.25 * height_cm - 5 * age + 5
    else: # F
        bmr = 10 * weight_kg + 6.25 * height_cm - 5 * age - 161

    # Factores de actividad/objetivo (simulación)
    if goal == "lose fat":
        factor = 1.2 
    elif goal == "gain muscle":
        factor = 1.5 
    else: # maintain
        factor = 1.35
        
    return int(bmr * factor)

def generate_menu(session_id: str) -> Dict[str, Any]:
    """Genera el menú completo basado en los datos de la sesión."""
    session = sessions.get(session_id)
    if not session or not session.get('personal_data'):
        raise HTTPException(status_code=400, detail="Incomplete data to generate menu")
        
    plan = session.get("pick_plan", {}).get("Plan")
    days = int(session.get("duration", {}).get("Days", 1))
    
    dislikes = session.get("preferences", {}).get("Dislikes", [])
    allergies = session.get("allergies", {}).get("Allergies", [])
    personal = session.get("personal_data", {})

    # Calcular calorías (aunque no se usa para filtrar, es bueno guardarlas)
    calories_needed = calculate_calories(
        weight_lbs=float(personal.get("Weight", 0)),
        height_in=float(personal.get("Height", 0)),
        age=int(personal.get("Age", 0)),
        sex=personal.get("Gender", "F"),
        goal=personal.get("Goal", "maintain")
    )
    session['calories_needed'] = calories_needed # Opcional: guardar el cálculo

    menu = []
    # Plan Map: Tipo de comida y número de veces que debe aparecer al día
    type_map = {
        "Plan 1": {"Main Meal": 1, "Breakfast": 0},
        "Plan 2": {"Main Meal": 2, "Breakfast": 0},
        "Plan 3": {"Main Meal": 1, "Breakfast": 1},
        "Plan 4": {"Main Meal": 2, "Breakfast": 1}
    }

    for day in range(days):
        for meal_type, count in type_map.get(plan, {}).items():
            if count == 0: continue
            
            # Filtrar disponibles para el tipo de comida
            available = filter_meals(meal_type, dislikes, allergies)
            
            if not available:
                # Esto es un error, pero para la demo simplemente lo salta
                continue
                
            for _ in range(count):
                # Usar random.choice para seleccionar un plato
                meal = random.choice(available)
                # Opcional: añadir información de día para el frontend
                meal['day'] = day + 1 
                menu.append(meal)

    total_price = sum(m.get("price", 0) for m in menu)
    sessions[session_id]['menu'] = menu
    sessions[session_id]['price'] = round(total_price, 2)
    return {"step": "menu_final", "menu": menu, "price": round(total_price, 2)}

# --- Endpoints ---

@app.get("/form")
def get_form():
    """Devuelve la estructura completa de pasos y data para iniciar el formulario (para HTML)."""
    return {
        "steps_order": steps_order, 
        "steps_data": steps_mapping 
    }

@app.post("/next-step")
def next_step(input: UserInput):
    """Maneja el flujo principal del formulario (Next y Back)."""
    session_id = input.session_id
    current_step = input.step.lower() 
    answer = input.answer or {}
    
    if session_id not in sessions:
        sessions[session_id] = {}

    # 1. Manejo del "Back"
    if current_step == "back":
        # Encuentra los pasos que ya tienen data guardada
        completed_steps = [s for s in steps_order if s in sessions[session_id]]
        
        if len(completed_steps) <= 1:
            next_step_name = steps_order[0] # Vuelve al primer paso
        else:
            # Vuelve al penúltimo paso completado
            next_step_name = completed_steps[-2]
            
        # Devolver la estructura del paso anterior
        return {
            "step": next_step_name,
            "question": steps_mapping[next_step_name]["question"],
            "fields": steps_mapping[next_step_name]["fields"]
        }

    # 2. Guardar respuesta del paso actual (si no es 'start' o 'back')
    if current_step != "start" and current_step in steps_order and answer:
        # La respuesta se guarda bajo el nombre del paso
        sessions[session_id][current_step] = answer

    # 3. Determinar el siguiente paso
    try:
        if current_step == "start":
            current_index = -1
        else:
            current_index = steps_order.index(current_step)
            
        next_index = current_index + 1
        next_step_name = steps_order[next_index]
        
    except (ValueError, IndexError):
        # Todos los pasos completados -> generar menú
        return generate_menu(session_id)

    # 4. Devolver la estructura del siguiente paso
    return {
        "step": next_step_name, 
        "question": steps_mapping[next_step_name]["question"],
        "fields": steps_mapping[next_step_name]["fields"]
    }

@app.post("/swap-meal")
def swap_meal_endpoint(input: SwapInput):
    """Sustituye un plato específico por otro compatible."""
    session = sessions.get(input.session_id)
    if not session or 'menu' not in session:
        raise HTTPException(status_code=400, detail="No active session or menu.")
        
    menu = session['menu']
    
    # Encontrar la comida a reemplazar
    original_meal_index = next((i for i, m in enumerate(menu) if m.get('name') == input.meal_name), -1)
    
    if original_meal_index == -1:
        raise HTTPException(status_code=404, detail=f"Meal '{input.meal_name}' not found in current menu.")

    original_meal = menu[original_meal_index]
    
    dislikes = session.get("preferences", {}).get("Dislikes", [])
    allergies = session.get("allergies", {}).get("Allergies", [])
    
    # Filtrar comidas compatibles (mismo 'type')
    available_meals = filter_meals(
        meal_type=original_meal.get('type'), 
        dislikes=dislikes, 
        allergies=allergies
    )
    
    # Excluir el plato actual para asegurar que sea un 'swap'
    swap_candidates = [m for m in available_meals if m.get('name') != original_meal.get('name')]
    
    if not swap_candidates:
        raise HTTPException(status_code=400, detail="No compatible alternative meals found.")
        
    # Seleccionar un nuevo plato aleatoriamente
    new_meal = random.choice(swap_candidates)
    
    # Reemplazar y recalcular precio
    # Opcional: mantener el día del plato original
    new_meal['day'] = original_meal.get('day')
    menu[original_meal_index] = new_meal
    
    total_price = sum(m.get("price", 0) for m in menu)
    
    sessions[input.session_id]['menu'] = menu
    sessions[input.session_id]['price'] = round(total_price, 2)
    
    return {"menu": menu, "price": round(total_price, 2)}

@app.post("/redo-menu")
def redo_menu(input: SessionInput):
    """Regenera todo el menú usando los datos de la sesión guardados."""
    if input.session_id not in sessions or not sessions[input.session_id].get('personal_data'):
        raise HTTPException(status_code=400, detail="Incomplete data to regenerate menu.")
    
    # La función generate_menu re-utiliza todos los datos guardados
    return generate_menu(input.session_id)

@app.post("/add-protein")
def add_protein(input: AddProteinInput):
    """Ajusta calorías y precio del menú según proteína extra."""
    session_id = input.session_id
    menu = sessions[session_id].get('menu', [])
    
    if not menu:
        raise HTTPException(status_code=400, detail="No menu generated")
        
    # La proteína tiene aprox. 4 kcal/g y asumimos 1 USD/g para el precio extra
    CAL_PER_PROTEIN_G = 4
    PRICE_PER_PROTEIN_G = 1.0
    
    if input.distribute_all:
        # Distribuir equitativamente en todas las comidas del menú
        if not menu:
            raise HTTPException(status_code=400, detail="Menu is empty.")
            
        protein_per_meal = input.extra_protein_g / len(menu)
        for m in menu:
            m['calories'] = m.get('calories', 0) + protein_per_meal * CAL_PER_PROTEIN_G
            m['price'] = m.get('price', 0) + protein_per_meal * PRICE_PER_PROTEIN_G
    else:
        # Añadir a una comida específica
        found = False
        for m in menu:
            if m.get('name') == input.meal_name:
                m['calories'] = m.get('calories', 0) + input.extra_protein_g * CAL_PER_PROTEIN_G
                m['price'] = m.get('price', 0) + input.extra_protein_g * PRICE_PER_PROTEIN_G
                found = True
                break
        if not found:
            raise HTTPException(status_code=404, detail=f"Meal '{input.meal_name}' not found for addition.")

    total_price = sum(m.get("price", 0) for m in menu)
    sessions[session_id]['menu'] = menu
    sessions[session_id]['price'] = round(total_price, 2)
    return {"menu": menu, "price": round(total_price, 2), "message": "Protein added and price adjusted."}