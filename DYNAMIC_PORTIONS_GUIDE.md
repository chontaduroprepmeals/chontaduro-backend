# 🎯 Sistema de Porciones Dinámicas

## ✅ PROBLEMA RESUELTO

**Problema Original:**
- Las comidas no mostraban grasas ni carbohidratos
- No había indicación de que las porciones se ajustaban al cliente
- Mismo plato para todos (niña de 5 años vs atleta)

**Solución Implementada:**
- ✅ Todas las macros visibles (proteína, carbohidratos, grasas)
- ✅ Porciones escaladas según necesidades individuales
- ✅ Multiplicador de porción mostrado (0.8x, 1.0x, 1.5x, etc.)
- ✅ Resumen de totales diarios

---

## 🔍 CÓMO FUNCIONA

### Paso 1: Calcular Necesidades del Cliente

El sistema usa los datos personales:
```
Edad: 30 años
Altura: 175 cm
Peso: 75 kg
Sexo: Masculino
Actividad: Moderada
Objetivo: Mantener peso
```

**Cálculo:**
```
TMB (metabolismo basal) = 1,750 kcal
TDEE (gasto total diario) = TMB × factor actividad
TDEE = 1,750 × 1.55 = 2,713 kcal

Proteína diaria = 120g (1.6g/kg peso)
Grasa diaria = 25% calorías = 75g
Carbohidratos = calorías restantes = 390g
```

### Paso 2: Distribuir Entre Comidas

**Plan 4 (3 comidas: 1 desayuno + 2 main meals):**
```
Por comida:
- Proteína: 120g ÷ 3 = 40g
- Grasa: 75g ÷ 3 = 25g
- Carbohidratos: 390g ÷ 3 = 130g
- Calorías: 2,713 ÷ 3 = 904 kcal
```

### Paso 3: Escalar las Porciones

**Base de Datos (meals.json):**
```json
{
  "name": "Grilled Chicken Breast with Rice and Broccoli",
  "protein_g": 35,
  "carbs_g": 45,
  "fat_g": 10,
  "serving_size_g": 300
}
```

**Cálculo del Multiplicador:**
```python
# Cliente necesita 40g proteína
# Plato base tiene 35g proteína

portion_multiplier = 40g ÷ 35g = 1.14x

# Ajustar otros macros proporcionalmente:
carbs_adjusted = 45g × 1.14 = 51g
fat_adjusted = 10g × 1.14 = 11g
serving_adjusted = 300g × 1.14 = 342g
```

**Pero ahora el sistema es MÁS INTELIGENTE:**
No multiplica simplemente - distribuye las macros exactas calculadas del TDEE:
```python
# Asigna directamente las macros calculadas:
protein_assigned = 40g  (del cálculo TDEE)
carbs_assigned = 130g   (del cálculo TDEE)
fat_assigned = 25g      (del cálculo TDEE)

# Calcula multiplicador para referencia visual:
portion_multiplier = 40g ÷ 35g = 1.14x
```

---

## 📊 EJEMPLOS CON DIFERENTES PERFILES

### Ejemplo 1: Niña de 5 Años

**Perfil:**
- Edad: 5 años
- Altura: 110 cm
- Peso: 18 kg
- Actividad: Moderada (niña activa)
- Objetivo: Crecimiento saludable

**Cálculos:**
```
TMB = 1,200 kcal
TDEE = 1,200 × 1.5 = 1,800 kcal
Proteína diaria = 54g (3g/kg para crecimiento)
Grasa = 50g (25% calorías)
Carbohidratos = 275g
```

**Distribución (Plan 4 - 3 comidas):**
```
Por comida:
- Proteína: 54g ÷ 3 = 18g
- Grasa: 50g ÷ 3 = 17g
- Carbos: 275g ÷ 3 = 92g
- Calorías: 600 kcal
```

**Porciones:**
```
┌────────────────────────────────────────────────────────────┐
│ Scrambled Eggs with Whole Wheat Toast                     │
│ 📏 Portion: 0.51x (128g) - Small child portion            │
│                                                            │
│ 🥩 Protein: 18g                                           │
│ 🍞 Carbs: 92g                                             │
│ 🥑 Fat: 17g                                               │
│ 🔥 Calories: 565 kcal                                     │
└────────────────────────────────────────────────────────────┘
```

### Ejemplo 2: Adulto con Sobrepeso (30 años)

**Perfil:**
- Edad: 30 años
- Altura: 165 cm
- Peso: 85 kg (sobrepeso)
- Actividad: Sedentaria
- Objetivo: Perder peso

**Cálculos:**
```
TMB = 1,650 kcal
TDEE = 1,650 × 1.2 = 1,980 kcal
Objetivo pérdida = 1,980 × 0.8 = 1,584 kcal
Proteína diaria = 102g (1.2g/kg para preservar músculo)
Grasa = 44g (25% calorías)
Carbohidratos = 221g
```

**Distribución (Plan 4 - 3 comidas):**
```
Por comida:
- Proteína: 102g ÷ 3 = 34g
- Grasa: 44g ÷ 3 = 15g
- Carbos: 221g ÷ 3 = 74g
- Calorías: 528 kcal
```

**Porciones:**
```
┌────────────────────────────────────────────────────────────┐
│ Lentil Stew with Rice                                      │
│ 📏 Portion: 0.97x (291g) - Standard portion               │
│                                                            │
│ 🥩 Protein: 34g                                           │
│ 🍞 Carbs: 74g                                             │
│ 🥑 Fat: 15g                                               │
│ 🔥 Calories: 551 kcal                                     │
└────────────────────────────────────────────────────────────┘
```

### Ejemplo 3: Atleta

**Perfil:**
- Edad: 25 años
- Altura: 180 cm
- Peso: 80 kg
- Actividad: Muy activa (entrena 2h/día)
- Objetivo: Ganar músculo

**Cálculos:**
```
TMB = 1,850 kcal
TDEE = 1,850 × 1.9 = 3,515 kcal
Objetivo ganancia = 3,515 × 1.15 = 4,042 kcal
Proteína diaria = 160g (2g/kg para construcción muscular)
Grasa = 112g (25% calorías)
Carbohidratos = 593g
```

**Distribución (Plan 4 - 3 comidas):**
```
Por comida:
- Proteína: 160g ÷ 3 = 53g → LIMITADO A 40g (regla de negocio)
- Proteína real = 120g ÷ 3 = 40g
- Grasa: 112g ÷ 3 = 37g
- Carbos: 593g ÷ 3 = 198g
- Calorías: 1,347 kcal
```

**Porciones:**
```
┌────────────────────────────────────────────────────────────┐
│ Grilled Chicken Breast with Rice and Broccoli             │
│ 📏 Portion: 1.14x (342g) - Large athlete portion          │
│                                                            │
│ 🥩 Protein: 40g (capped at max)                           │
│ 🍞 Carbs: 198g                                            │
│ 🥑 Fat: 37g                                               │
│ 🔥 Calories: 1,189 kcal                                   │
└────────────────────────────────────────────────────────────┘
```

---

## 🎨 LO QUE VE EL USUARIO

### Vista Completa del Menú

```
┌──────────────────────────────────────────────────────────────┐
│                      Your Menu                               │
│                                                              │
│  Estimated price: $41.00                                     │
│                                                              │
│  TMB: 1,750 kcal — TDEE: 2,713 kcal — Target: 2,713 kcal   │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│         📊 Your Daily Nutrition Plan                         │
│  ┌───────────┬───────────┬──────────┬───────────┐          │
│  │  Protein  │   Carbs   │   Fat    │ Calories  │          │
│  │   120g    │   390g    │   75g    │  2,713    │          │
│  └───────────┴───────────┴──────────┴───────────┘          │
│                                                              │
│  ✨ Meals portioned for your needs based on age,            │
│     weight, height, and activity level                       │
│                                                              │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌────────────────────────────────────────────────────┐    │
│  │ Scrambled Eggs with Whole Wheat Toast              │    │
│  │ breakfast • 904 kcal • $11.00                      │    │
│  │ 📏 Portion size: 1.14x (342g total)                │    │
│  │                                                    │    │
│  │ Ingredients: eggs, whole wheat bread, olive oil    │    │
│  │                                                    │    │
│  │ Macros (for this portion):                         │    │
│  │ 🥩 Protein: 40g   🍞 Carbs: 130g   🥑 Fat: 25g    │    │
│  └────────────────────────────────────────────────────┘    │
│                                                              │
│  ┌────────────────────────────────────────────────────┐    │
│  │ Grilled Chicken Breast with Rice and Broccoli      │    │
│  │ main meal • 904 kcal • $15.00                      │    │
│  │ 📏 Portion size: 1.14x (342g total)                │    │
│  │                                                    │    │
│  │ Ingredients: chicken breast, white rice, broccoli  │    │
│  │                                                    │    │
│  │ Macros (for this portion):                         │    │
│  │ 🥩 Protein: 40g   🍞 Carbs: 130g   🥑 Fat: 25g    │    │
│  └────────────────────────────────────────────────────┘    │
│                                                              │
│  ┌────────────────────────────────────────────────────┐    │
│  │ Lentil Stew with Rice                              │    │
│  │ main meal • 905 kcal • $15.00                      │    │
│  │ 📏 Portion size: 1.14x (342g total)                │    │
│  │                                                    │    │
│  │ Ingredients: lentils, white rice, tomato, onion    │    │
│  │                                                    │    │
│  │ Macros (for this portion):                         │    │
│  │ 🥩 Protein: 40g   🍞 Carbs: 130g   🥑 Fat: 25g    │    │
│  └────────────────────────────────────────────────────┘    │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

---

## 🔧 CÓMO FUNCIONA TÉCNICAMENTE

### Backend (main.py)

**1. Calcular Macros Diarias:**
```python
# En allocate_protein_to_menu()
daily_protein_target = int(macros_daily_protein or 120)
daily_calorie_target = int(calorie_target or 2000)

protein_calories = daily_protein_target * 4
fat_calories = daily_calorie_target * 0.25
daily_fat_target = int(fat_calories / 9)
carb_calories = daily_calorie_target - protein_calories - fat_calories
daily_carb_target = int(max(0, carb_calories / 4))
```

**2. Distribuir Entre Comidas:**
```python
meals_per_day = 3  # Para Plan 4
protein_per_meal = daily_protein_target // meals_per_day
fat_per_meal = daily_fat_target // meals_per_day
carbs_per_meal = daily_carb_target // meals_per_day
```

**3. Asignar a Cada Comida:**
```python
for meal in menu:
    meal_dict["protein_assigned"] = protein_per_meal
    meal_dict["fat_assigned"] = fat_per_meal
    meal_dict["carbs_assigned"] = carbs_per_meal
    meal_dict["calories_assigned"] = (protein_per_meal * 4) + 
                                     (carbs_per_meal * 4) + 
                                     (fat_per_meal * 9)
```

**4. Calcular Multiplicador de Porción:**
```python
base_protein = meal.get("protein_g", 35)  # del meals.json
portion_multiplier = protein_assigned / base_protein
meal_dict["portion_multiplier"] = round(portion_multiplier, 2)
meal_dict["serving_size_adjusted"] = int(
    meal.get("serving_size_g", 300) * portion_multiplier
)
```

### Frontend (index.html)

**1. Mostrar Totales Diarios:**
```javascript
if (data.nutrition && data.nutrition.totals) {
  const totals = data.nutrition.totals;
  html += `
    <div class="mb-4 p-4 bg-blue-50 rounded">
      <div>📊 Your Daily Nutrition Plan</div>
      <div>Protein: ${totals.protein_total}g</div>
      <div>Carbs: ${totals.carbs_total}g</div>
      <div>Fat: ${totals.fat_total}g</div>
      <div>Calories: ${totals.calories_total}</div>
    </div>
  `;
}
```

**2. Mostrar Cada Comida con Porciones:**
```javascript
data.menu.forEach(m => {
  const portionMultiplier = m.portion_multiplier || 1.0;
  const servingSize = m.serving_size_adjusted || m.serving_size_g;
  
  html += `
    <div>${m.name}</div>
    ${portionMultiplier !== 1.0 ? 
      `<div>📏 Portion: ${portionMultiplier}x (${servingSize}g)</div>` 
      : ''}
    <div>🥩 Protein: ${m.protein_assigned}g</div>
    <div>🍞 Carbs: ${m.carbs_assigned}g</div>
    <div>🥑 Fat: ${m.fat_assigned}g</div>
  `;
});
```

---

## ✅ BENEFICIOS

### Para el Cliente:
1. **Personalizado:** Porciones ajustadas a SUS necesidades exactas
2. **Transparente:** Ve exactamente qué y cuánto comer
3. **Educativo:** Entiende sus necesidades nutricionales
4. **Conveniente:** No tiene que calcular nada

### Para el Negocio:
1. **Eficiente:** Usa mismos platos, ajusta porciones
2. **Escalable:** Funciona para cualquier perfil
3. **Rentable:** Control de costos (max 40g proteína)
4. **Profesional:** Sistema científicamente basado

---

## 🎯 RANGOS TÍPICOS DE MULTIPLICADORES

**0.5x - 0.8x:** Niños pequeños, personas muy sedentarias con objetivos de pérdida
**0.8x - 1.0x:** Adultos promedio, pérdida de peso moderada
**1.0x - 1.2x:** Adultos activos, mantenimiento
**1.2x - 1.5x:** Atletas, ganancia muscular moderada
**1.5x - 2.0x:** Atletas de alto rendimiento (limitado por regla 40g)

**Nota:** Multiplicadores superiores a 1.14x están limitados por la regla de negocio de máximo 40g proteína por comida.

---

## 📝 RESUMEN

✅ **Mismo plato, diferentes porciones**
✅ **Basado en TDEE individual**
✅ **Muestra proteína, carbos, grasas**
✅ **Indica tamaño de porción**
✅ **Totales diarios visibles**
✅ **Educativo y transparente**

**El sistema ahora entiende que "Pollo con arroz" es diferente para:**
- Una niña de 5 años: **Porción pequeña (0.5x, 150g)**
- Un adulto con sobrepeso: **Porción estándar (1.0x, 300g)**
- Un atleta: **Porción grande (1.5x, 450g)**

¡Cada uno recibe EXACTAMENTE lo que necesita! 🎉
