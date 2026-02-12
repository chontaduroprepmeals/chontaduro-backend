# Estado Actual del Sistema - 12 Feb 2026

## ✅ LO QUE ESTÁ IMPLEMENTADO Y FUNCIONANDO:

### 1. Sistema de Etiquetas por Día (BACKEND) ✅
**Archivo:** `main.py` (líneas 1230-1281)

El backend YA agrega las etiquetas de día a cada comida:
```python
meal_entry["day_number"] = 1, 2, 3, etc.
meal_entry["meal_type"] = "BREAKFAST", "LUNCH", "DINNER"
meal_entry["day_label"] = "DAY 1 - BREAKFAST"
```

**Ejemplo de lo que el backend envía:**
```json
{
  "menu": [
    {
      "name": "Overnight Oats",
      "day_number": 1,
      "meal_type": "BREAKFAST",
      "day_label": "DAY 1 - BREAKFAST",
      ...
    },
    {
      "name": "Chicken with Rice",
      "day_number": 1,
      "meal_type": "LUNCH",
      "day_label": "DAY 1 - LUNCH",
      ...
    }
  ]
}
```

**Lógica por Plan:**
- Plan 1: Solo "LUNCH"
- Plan 2: "LUNCH" + "DINNER"
- Plan 3: "BREAKFAST" + "LUNCH"
- Plan 4: "BREAKFAST" + "LUNCH" + "DINNER"

---

## ❌ LO QUE FALTA IMPLEMENTAR (FRONTEND):

### 1. Mostrar Etiquetas de Día en el Menú
**Archivo a modificar:** `index.html` función `renderMenu()`

**Problema actual:**
El frontend recibe los datos con `day_label` pero NO los muestra. Solo muestra:
```
Cottage Cheese with Papaya
breakfast • 1398 kcal • $11.00
```

**Lo que DEBE mostrar:**
```
📅 DAY 1
  🌅 BREAKFAST
  Cottage Cheese with Papaya
  breakfast • 1398 kcal • $11.00
  
  🍽️ LUNCH
  Chicken with Rice
  main meal • 904 kcal • $15.00
  
  🌙 DINNER
  Beef Tacos
  main meal • 905 kcal • $15.00

📅 DAY 2
  🌅 BREAKFAST
  ...
```

**Cambios necesarios:**
1. Agrupar las comidas por `day_number`
2. Agregar encabezados de día: "📅 DAY 1"
3. Agregar tipo de comida: "🌅 BREAKFAST", "🍽️ LUNCH", "🌙 DINNER"
4. Separación visual entre días

### 2. Mejorar Formulario de Datos Personales
**Archivo a modificar:** `index.html` crear función `renderPersonalInfo()`

**Problema actual:**
Los inputs de peso, altura, edad, etc. se ven aburridos:
```
Weight Unit *
[kg ▼]
Weight (kg or lbs) *
[e.g. 70]
```

**Lo que DEBE ser:**
Componentes visuales interactivos con:
- ⚖️ Peso: Toggle kg/lbs + input grande
- 📏 Altura: Toggle cm/in + input grande
- 🎂 Edad: Input con icono
- ♂️♀️ Sexo: Cards visuales
- 🏃‍♂️ Días ejercicio: Picker visual (0-7)
- ⏱️ Duración: Cards de tiempo
- 🟢🟡🔴 Intensidad: Cards con colores

---

## 📋 TAREAS PENDIENTES PARA PRÓXIMA SESIÓN:

### Prioridad 1: Mostrar Etiquetas de Día
```javascript
// En index.html, función renderMenu()
function renderMenu(data) {
  // 1. Agrupar comidas por día
  const mealsByDay = {};
  data.menu.forEach(meal => {
    const day = meal.day_number || 1;
    if (!mealsByDay[day]) mealsByDay[day] = [];
    mealsByDay[day].push(meal);
  });
  
  // 2. Renderizar por día
  let html = '';
  Object.keys(mealsByDay).sort().forEach(day => {
    html += `<div class="day-section mb-6">`;
    html += `<h3 class="text-xl font-bold mb-3">📅 DAY ${day}</h3>`;
    
    mealsByDay[day].forEach(meal => {
      const icon = meal.meal_type === 'BREAKFAST' ? '🌅' : 
                   meal.meal_type === 'LUNCH' ? '🍽️' : '🌙';
      html += `<div class="mb-4">`;
      html += `<div class="text-sm font-semibold text-gray-600">${icon} ${meal.meal_type}</div>`;
      html += renderMealCard(meal);
      html += `</div>`;
    });
    
    html += `</div>`;
  });
}
```

### Prioridad 2: Formulario Visual de Datos Personales
```javascript
// En index.html, nueva función
function renderPersonalInfo(question, fields) {
  // Crear componentes visuales para:
  // - Peso con toggle y icono
  // - Altura con toggle y icono
  // - Edad con icono
  // - Sexo con cards
  // - Ejercicio con cards/pickers
  // - Intensidad con cards de colores
}

// En renderForm(), agregar:
if (currentStep === "personal_info") {
  return renderPersonalInfo(question, fields);
}
```

---

## ARCHIVOS A MODIFICAR:

1. **index.html** (líneas ~781-900)
   - Función `renderMenu()` - agregar agrupación por día
   - Función `renderForm()` - detectar personal_info
   - Nueva función `renderPersonalInfo()` - formulario visual

2. **NINGÚN CAMBIO NECESARIO EN:**
   - ✅ `main.py` - Ya tiene todo implementado
   - ✅ `meals.json` - Ya tiene los datos necesarios

---

## RESUMEN:

**Backend:** ✅ COMPLETO - Envía todas las etiquetas correctamente

**Frontend:** ❌ PENDIENTE
- Mostrar etiquetas de día
- Formulario visual de datos personales

**Próximo paso:**
Implementar cambios en `index.html` para mostrar la información que el backend ya está enviando.
