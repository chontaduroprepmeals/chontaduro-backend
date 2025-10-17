import requests
import json

BASE_URL = "http://127.0.0.1:8000"
session_id = "test123"

def print_json(title, data):
    print(f"\n=== {title} ===")
    print(json.dumps(data, indent=2))

# 1️⃣ Selección de plan
response = requests.post(f"{BASE_URL}/next-step", json={
    "session_id": session_id,
    "step": "pick_plan",
    "answer": {"plan": "Plan 1"}
})
print_json("Pick Plan Response", response.json())

# 2️⃣ Selección de duración
response = requests.post(f"{BASE_URL}/next-step", json={
    "session_id": session_id,
    "step": "duration",
    "answer": {"duration": "1 week"}
})
print_json("Duration Response", response.json())

# 3️⃣ Datos personales
response = requests.post(f"{BASE_URL}/next-step", json={
    "session_id": session_id,
    "step": "personal_data",
    "answer": {
        "Edad": 28,
        "Peso": 60,
        "Sexo de nacimiento": "F",
        "% Grasa corporal (opcional)": 22,
        "Objetivos": "Perder grasa"
    }
})
print_json("Personal Data Response", response.json())

# 4️⃣ Preferencias alimenticias
response = requests.post(f"{BASE_URL}/next-step", json={
    "session_id": session_id,
    "step": "preferences",
    "answer": {
        "Preferencias alimenticias": ["Vegetariano"],
        "Ingredientes que no te gustan": ["Brócoli", "Tofu"]
    }
})
print_json("Preferences Response", response.json())

# 5️⃣ Alergias
response = requests.post(f"{BASE_URL}/next-step", json={
    "session_id": session_id,
    "step": "allergies",
    "answer": {
        "Alergias": ["Nueces"]
    }
})
print_json("Allergies Response", response.json())

# 6️⃣ Generar menú final
response = requests.get(f"{BASE_URL}/generate-menu", params={"session_id": session_id})
print_json("Generated Menu", response.json())

# 7️⃣ Hacer swap de una comida
# Tomamos la primera comida del menú actual
menu = response.json()["menu"]
meal_to_swap = menu[0]["name"]

response = requests.post(f"{BASE_URL}/swap-meal", json={
    "session_id": session_id,
    "meal_name": meal_to_swap
})
print_json("Swap Meal Response", response.json())

# 8️⃣ Agregar proteína extra (+20g)
response = requests.post(f"{BASE_URL}/add-protein", json={
    "session_id": session_id,
    "extra_protein_g": 20
})
print_json("Add Protein Response", response.json())

# 9️⃣ Redo menú completo
response = requests.post(f"{BASE_URL}/redo-menu", json={
    "session_id": session_id,
    "step": "redo",
    "answer": {}
})
print_json("Redo Menu Response", response.json())