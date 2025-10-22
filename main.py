# Importaciones necesarias
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, FileResponse
from pydantic import BaseModel, Field
import random
import json
from typing import List, Dict, Any, Optional

app = FastAPI() 

# --- CORS (Permite la comunicación entre frontend y backend) ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- ENDPOINT RAIZ (SOLUCIÓN AL ERROR 405) ---
@app.get("/", response_class=HTMLResponse)
async def serve_frontend():
    # Al servir index.html explícitamente con GET /, evitamos el conflicto
    # de StaticFiles que estaba bloqueando el POST /next-step.
    return FileResponse("index.html")


# --- BASE DE DATOS Y ESTADO DE LA SESIÓN ---
# Carga la base de datos de comidas
MEALS_DATA = []
try:
    with open("meals.json", "r") as f:
        data = json.load(f)
        if isinstance(data, list):
            MEALS_DATA = data
except FileNotFoundError:
    print("WARNING: meals.json not found. Meal generation will fail.")
except json.JSONDecodeError:
    print("WARNING: meals.json could not be decoded. Check JSON format.")

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

# Modelo de solicitud principal. Esta es la estructura que *debe* coincidir con el JSON enviado.
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
        if not any(ing.lower() in undesired for ing in meal["ingredients"]):
            # Convertir el diccionario crudo a un objeto Meal validado por Pydantic
            try:
                 filtered_meals.append(Meal(**meal))
            except Exception as e:
                 print(f"Error validating meal data: {e} for meal {meal.get('name')}")
                 # Skip invalid meals
    return filtered_meals

def generate_menu(state: SessionState) -> List[Meal]:
    """Genera el menú completo basado en las preferencias del usuario."""
    if not state.plan or not state.days:
        return []

    # Manejo de KeyError si el plan es inválido (aunque debería estar validado antes)
    try:
        meals_per_day = {1: 1, 2: 2, 3: 3, 4: 3}[state.plan]
    except KeyError:
        return []

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
    
    # Variable para almacenar el nombre del siguiente paso a renderizar
    step_to_render_name = state.current_step 
    
    # --- Manejo del botón 'Back' ---
    if step_name == "back" and state.history:
        # Recuperar el estado del paso anterior
        prev_state_data = state.history.pop()
        prev_state = SessionState(**prev_state_data)
        sessions[session_id] = prev_state.model_dump()
        
        # Regresar al paso anterior
        return get_form_fields(prev_state.current_step, prev_state)

    # --- Procesar Respuesta y Actualizar Estado ---
    
    # Guardar el estado actual antes de avanzar
    if step_name != "start":
        state.history.append(sessions[session_id].copy())

    # 1. Start/Initialization: Esto asegura que el primer paso sea 'pick_plan'
    if step_name == "start":
        step_to_render_name = steps_mapping["start"] # "pick_plan"
        
    # 2. Pick Plan (Ajuste para manejar con más seguridad el input nulo/faltante)
    elif step_name == "pick_plan":
        plan_answer = answer.get("Plan")
        
        # Validación estricta: debe existir y ser una cadena de texto para procesar
        if plan_answer and isinstance(plan_answer, str):
            try:
                # Safely extract the number from the string (e.g., "Plan 1: 1 comida al día" -> 1)
                plan_str = plan_answer.split(":")[0].replace("Plan ", "").strip()
                plan_num = int(plan_str)
                
                # Check if the extracted number is a valid plan ID (1, 2, 3, or 4)
                if plan_num in [1, 2, 3, 4]:
                    state.plan = plan_num
                    step_to_render_name = steps_mapping["pick_plan"] # Advances to "duration"
                else:
                    # Plan number is invalid, stay in the current step
                    step_to_render_name = "pick_plan"
                    
            except (ValueError, IndexError):
                # Error in parsing, stay in the current step
                step_to_render_name = "pick_plan"
        else:
            # Plan not selected or incorrect data, stay in the current step
            step_to_render_name = "pick_plan"
    
    # 3. Duration (Con validación para evitar 422 si el input es incorrecto)
    elif step_name == "duration":
        try:
            days_input = answer.get("Días")
            # Validation: must exist, be a digit, and be in range 1-30
            if days_input is not None and str(days_input).isdigit() and 1 <= int(days_input) <= 30:
                state.days = int(days_input)
                step_to_render_name = steps_mapping["duration"] # "dislikes"
            else:
                # Stay in the same step (duration) if the input is invalid
                step_to_render_name = "duration" 
        except Exception:
            # Stay in the same step if there is a parsing error
            step_to_render_name = "duration"
    
    # 4. Dislikes
    elif step_name == "dislikes" and "Ingredientes_No_Deseados" in answer:
        state.dislikes = answer["Ingredientes_No_Deseados"] if isinstance(answer["Ingredientes_No_Deseados"], list) else [answer["Ingredientes_No_Deseados"]]
        step_to_render_name = steps_mapping["dislikes"] # "allergies"

    # 5. Allergies
    elif step_name == "allergies" and "Alergias" in answer:
        state.allergies = answer["Alergias"] if isinstance(answer["Alergias"], list) else [answer["Alergias"]]
        step_to_render_name = steps_mapping["allergies"] # "extra_protein"

    # 6. Extra Protein
    elif step_name == "extra_protein" and "Gramos_Extra_Proteína" in answer:
        try:
            protein_input = answer.get("Gramos_Extra_Proteína")
            if protein_input is not None and str(protein_input).isdigit() and 0 <= int(protein_input) <= 100:
                state.extra_protein_grams = int(protein_input)
            elif protein_input == "" or protein_input is None:
                 state.extra_protein_grams = 0 # Empty input is treated as 0
            
            step_to_render_name = steps_mapping["extra_protein"] # "review"
        except Exception:
             state.extra_protein_grams = 0 # Default value in case of error
             step_to_render_name = steps_mapping["extra_protein"] # Advance to the next step (review)

    # 7. Review (Final menu generation)
    elif step_name == "review":
        # --- FINAL MENU GENERATION ---
        state.menu = generate_menu(state)
        sessions[session_id] = state.model_dump()
        
        if not state.menu:
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
        
    # --- Final Step Update and Return ---
    
    # Update the state with the new step to render
    state.current_step = step_to_render_name
    
    # Save the updated state
    sessions[session_id] = state.model_dump()

    # Return the form for the next step
    return get_form_fields(state.current_step, state)


# Endpoint for swapping an individual meal
@app.api_route("/swap-meal", methods=["POST", "GET"])
async def swap_meal(req: SwapMealRequest):
    session_id = req.session_id
    meal_to_swap_name = req.meal_to_swap

    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found.")
    
    state = SessionState(**sessions[session_id])
    
    # 1. Find the meal to be replaced
    meal_to_swap_info = next((m for m in state.menu if m.name == meal_to_swap_name), None)
    
    if not meal_to_swap_info:
        raise HTTPException(status_code=404, detail="Meal not found in current menu.")
        
    meal_type = meal_to_swap_info.type
    
    # 2. Generate a new meal
    available_meals = filter_meals(state.dislikes, state.allergies)
    
    # Filter only meals of the same type and that are NOT already in the menu
    potential_replacements = [
        m for m in available_meals 
        if m.type == meal_type and m.name != meal_to_swap_name and m.name not in [x.name for x in state.menu]
    ]

    if not potential_replacements:
        return {"message": "No hay reemplazos disponibles con tus filtros."}
    
    new_meal = random.choice(potential_replacements)
    
    # 3. Replace in the menu list
    for i, meal in enumerate(state.menu):
        if meal.name == meal_to_swap_name:
            state.menu[i] = new_meal
            break
            
    # 4. Update state and calculate new price
    sessions[session_id] = state.model_dump()
    total_price = calculate_price(state.menu, state.extra_protein_grams)

    return {
        "menu": state.menu,
        "price": total_price,
        "message": f"Comida '{meal_to_swap_name}' reemplazada por '{new_meal.name}'."
    }

# Endpoint for regenerating the full menu
@app.api_route("/redo-menu", methods=["POST", "GET"])
async def redo_menu(req: RedoMenuRequest):
    session_id = req.session_id
    
    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found.")
        
    state = SessionState(**sessions[session_id])
    
    # Generate a new complete menu
    state.menu = generate_menu(state)
    
    if not state.menu:
        return {"message": "No se pudo generar un nuevo menú con tus filtros actuales."}
        
    # Update state and calculate price
    sessions[session_id] = state.model_dump()
    total_price = calculate_price(state.menu, state.extra_protein_grams)

    return {
        "menu": state.menu,
        "price": total_price,
        "message": "¡Menú completo regenerado!"
    }
