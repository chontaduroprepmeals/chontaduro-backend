# Importaciones necesarias
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
import random
import json
from typing import List, Dict, Any, Optional

app = FastAPI() # Versión FINAL de despliegue - Acepta POST

# --- SERVICIO DE ARCHIVOS ESTÁTICOS Y ROOT ---
# Monta el directorio actual para servir index.html.
# Esto hace que FastAPI busque 'index.html' en la carpeta raíz para la ruta '/'
app.mount("/", StaticFiles(directory=".", html=True), name="static")


# --- CORS (Permite la comunicación entre frontend y backend) ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- BASE DE DATOS Y ESTADO DE LA SESIÓN ---
# Carga la base de datos de comidas
try:
    with open("meals.json", "r") as f:
        MEALS_DATA = json.load(f)
except FileNotFoundError:
    MEALS_DATA = []

# Almacenamiento de sesiones (simula una base de datos de usuario)
sessions: Dict[str, Dict[str, Any]] = {}

# Mapeo del flujo de la aplicación
steps_mapping = {
    "start": "pick_plan",
    "pick_plan": "duration",
    "duration": "dislikes",
    "dislikes": "allergies",
    "allergies": "extra_protein",
    "extra_protein": "review",
}

# --- MODELOS DE DATOS (Pydantic) ---

class Meal(BaseModel):
    name: str
    type: str
    ingredients: List[str]
    calories: int
    price: float
    image_url: Optional[str] = None

class SessionState(BaseModel):
    plan: Optional[int] = None
    days: Optional[int] = None
    dislikes: List[str] = []
    allergies: List[str] = []
    extra_protein_grams: int = 0
    menu: List[Meal] = []
    current_step: str = "start"
    history: List[Dict[str, Any]] = [] # Para el botón 'Back'

class NextStepRequest(BaseModel):
    session_id: str
    step: str
    answer: Dict[str, Any]

class SwapMealRequest(BaseModel):
    session_id: str
    meal_to_swap: str

class RedoMenuRequest(BaseModel):
    session_id: str

# --- LÓGICA DE NEGOCIO ---

def calculate_price(menu: List[Meal], extra_protein: int) -> float:
    """Calcula el precio total del menú, incluyendo proteína extra."""
    base_price = sum(meal.price for meal in menu)
    protein_cost = extra_protein * 1.00  # $1.00 por gramo extra
    return round(base_price + protein_cost, 2)

def filter_meals(dislikes: List[str], allergies: List[str]) -> List[Meal]:
    """Filtra las comidas que contienen ingredientes no deseados."""
    undesired = set([d.lower() for d in dislikes] + [a.lower() for a in allergies])
    
    filtered_meals = []
    for meal in MEALS_DATA:
        if not any(ing.lower() in undesired for ing in meal.ingredients):
            filtered_meals.append(Meal(**meal))
    return filtered_meals

def generate_menu(state: SessionState) -> List[Meal]:
    """Genera el menú completo basado en las preferencias del usuario."""
    if not state.plan or not state.days:
        return []

    meals_per_day = {1: 1, 2: 2, 3: 3, 4: 3}[state.plan]
    total_meals_required = state.days * meals_per_day
    
    # Filtrar comidas
    available_meals = filter_meals(state.dislikes, state.allergies)

    if not available_meals:
        # En caso de filtros muy restrictivos
        return []

    # Crear categorías de comidas para balancear
    categories = {
        "Breakfast": [m for m in available_meals if m.type == "Breakfast"],
        "Main Meal": [m for m in available_meals if m.type == "Main Meal"]
    }

    # Lógica de selección: intentar balancear comidas principales y desayunos
    menu = []
    for day in range(state.days):
        day_meals = []
        
        # Siempre un desayuno si el plan lo requiere
        if meals_per_day >= 1 and categories["Breakfast"]:
            # Usar random.choice para seleccionar una comida al azar y evitar repetición inmediata
            breakfast = random.choice(categories["Breakfast"])
            day_meals.append(breakfast)
        
        # El resto son comidas principales
        main_meals_required = meals_per_day - (1 if meals_per_day >= 1 else 0)
        
        for _ in range(main_meals_required):
            if categories["Main Meal"]:
                main_meal = random.choice(categories["Main Meal"])
                day_meals.append(main_meal)
        
        menu.extend(day_meals)

    # Asegurarse de que el menú tenga la longitud requerida (si hay suficientes comidas)
    return menu[:total_meals_required]


# --- ENDPOINTS DE LA APLICACIÓN ---

# Endpoint para obtener la estructura del formulario (si el frontend lo necesita)
@app.get("/form")
async def get_form_structure():
    """Devuelve la estructura del formulario y los pasos."""
    return {
        "steps_order": list(steps_mapping.keys()),
        "meals_types": list(set(m['type'] for m in MEALS_DATA))
    }

def get_form_fields(step_name: str, state: Optional[SessionState] = None):
    """Genera la pregunta y los campos de entrada para el paso actual."""
    
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

# Endpoint principal para navegar el flujo
@app.api_route("/next-step", methods=["POST", "GET"])
async def next_step(req: NextStepRequest):
    session_id = req.session_id
    step_name = req.step
    answer = req.answer

    # Inicializar o cargar estado
    if session_id not in sessions:
        sessions[session_id] = SessionState().model_dump()

    state = SessionState(**sessions[session_id])
    
    # --- Manejo del botón 'Back' ---
    if step_name == "back" and state.history:
        # Recuperar el estado del paso anterior
        prev_state_data = state.history.pop()
        prev_state = SessionState(**prev_state_data)
        sessions[session_id] = prev_state.model_dump()
        
        # Regresar al paso anterior (el último paso en el historial antes de hacer pop)
        return get_form_fields(prev_state.current_step, prev_state)

    # --- Procesar Respuesta y Actualizar Estado ---
    
    # Guardar el estado actual antes de avanzar
    if step_name != "start":
        state.history.append(sessions[session_id].copy())
    
    if step_name == "pick_plan" and "Plan" in answer:
        plan_str = answer["Plan"].split(":")[0].replace("Plan ", "").strip()
        state.plan = int(plan_str)
        state.current_step = steps_mapping["pick_plan"]
    
    elif step_name == "duration" and "Días" in answer:
        try:
            state.days = int(answer["Días"])
            state.current_step = steps_mapping["duration"]
        except ValueError:
            pass # No actualizar si no es un número
    
    elif step_name == "dislikes" and "Ingredientes_No_Deseados" in answer:
        state.dislikes = answer["Ingredientes_No_Deseados"] if isinstance(answer["Ingredientes_No_Deseados"], list) else [answer["Ingredientes_No_Deseados"]]
        state.current_step = steps_mapping["dislikes"]

    elif step_name == "allergies" and "Alergias" in answer:
        state.allergies = answer["Alergias"] if isinstance(answer["Alergias"], list) else [answer["Alergias"]]
        state.current_step = steps_mapping["allergies"]

    elif step_name == "extra_protein" and "Gramos_Extra_Proteína" in answer:
        try:
            state.extra_protein_grams = int(answer["Gramos_Extra_Proteína"])
            state.current_step = steps_mapping["extra_protein"]
        except ValueError:
             state.extra_protein_grams = 0 # Valor por defecto
             state.current_step = steps_mapping["extra_protein"]

    elif step_name == "review":
        # Se asume que el usuario confirmó el review, pasamos a generar el menú
        state.current_step = steps_mapping["extra_protein"] # El paso de review es el penúltimo en la navegación lógica
        
        # --- GENERACIÓN FINAL DEL MENÚ ---
        state.menu = generate_menu(state)
        sessions[session_id] = state.model_dump()
        
        if not state.menu:
             # Retornar a la revisión con un mensaje de error si el menú está vacío
            return {
                "question": "Error: Los filtros son muy restrictivos. Vuelve atrás y ajusta tus preferencias.",
                "fields": []
            }

        total_price = calculate_price(state.menu, state.extra_protein_grams)
        
        return {
            "menu": state.menu,
            "price": total_price,
            "message": "¡Tu menú está listo!"
        }
        
    elif step_name == "start":
        state.current_step = steps_mapping["start"]

    # Guardar el estado actualizado
    sessions[session_id] = state.model_dump()

    # Devolver el formulario para el siguiente paso
    next_step_name = steps_mapping.get(state.current_step, "review")
    return get_form_fields(next_step_name, state)


# Endpoint para cambiar una comida individual
@app.api_route("/swap-meal", methods=["POST", "GET"])
async def swap_meal(req: SwapMealRequest):
    session_id = req.session_id
    meal_to_swap_name = req.meal_to_swap

    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found.")
    
    state = SessionState(**sessions[session_id])
    
    # 1. Encontrar la comida a reemplazar
    meal_to_swap_info = next((m for m in state.menu if m.name == meal_to_swap_name), None)
    
    if not meal_to_swap_info:
        raise HTTPException(status_code=404, detail="Meal not found in current menu.")
        
    meal_type = meal_to_swap_info.type
    
    # 2. Generar nueva comida
    available_meals = filter_meals(state.dislikes, state.allergies)
    
    # Filtra solo las comidas del mismo tipo y que NO estén ya en el menú
    potential_replacements = [
        m for m in available_meals 
        if m.type == meal_type and m.name != meal_to_swap_name and m.name not in [x.name for x in state.menu]
    ]

    if not potential_replacements:
        return {"message": "No hay reemplazos disponibles con tus filtros."}
    
    new_meal = random.choice(potential_replacements)
    
    # 3. Reemplazar en la lista del menú
    for i, meal in enumerate(state.menu):
        if meal.name == meal_to_swap_name:
            state.menu[i] = new_meal
            break
            
    # 4. Actualizar estado y calcular nuevo precio
    sessions[session_id] = state.model_dump()
    total_price = calculate_price(state.menu, state.extra_protein_grams)

    return {
        "menu": state.menu,
        "price": total_price,
        "message": f"Comida '{meal_to_swap_name}' reemplazada por '{new_meal.name}'."
    }

# Endpoint para regenerar el menú completo
@app.api_route("/redo-menu", methods=["POST", "GET"])
async def redo_menu(req: RedoMenuRequest):
    session_id = req.session_id
    
    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found.")
        
    state = SessionState(**sessions[session_id])
    
    # Generar un nuevo menú completo
    state.menu = generate_menu(state)
    
    if not state.menu:
        return {"message": "No se pudo generar un nuevo menú con tus filtros actuales."}
        
    # Actualizar estado y calcular precio
    sessions[session_id] = state.model_dump()
    total_price = calculate_price(state.menu, state.extra_protein_grams)

    return {
        "menu": state.menu,
        "price": total_price,
        "message": "¡Menú completo regenerado!"
    }
