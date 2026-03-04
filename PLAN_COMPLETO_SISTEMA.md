# Plan Completo del Sistema Chontaduro

## Resumen de Cambios Solicitados

Este documento describe TODOS los cambios solicitados para el sistema de meal prep.

---

## 🎨 PARTE 1: UI Mejorada para Datos Personales

### Estado Actual:
- Formulario aburrido con dropdowns básicos
- No es dinámico ni atractivo
- No tiene ilustraciones

### Estado Deseado:
- Visual cards para todas las opciones
- Iconos/dibujitos según selección
- Más interactivo y bonito

### Cambios Específicos:

**Weight/Height Input:**
- Inputs más bonitos con unit toggle integrado
- Visual de persona cambiando según peso/altura

**Sex Selection:**
- Visual cards con iconos 👨 Male / 👩 Female
- Mismo estilo que diet preference

**Exercise Frequency (Days per week):**
- Visual cards: 0, 1-2, 3-4, 5-6, 7
- Iconos de actividad

**Session Duration:**
- Visual cards: <30, 30-45, 45-60, >60 minutos
- Icono de reloj

**Intensity:**
- Visual cards con colores:
  - 🟢 Low (verde)
  - 🟡 Moderate (amarillo)
  - 🔴 High (rojo)

---

## 🏷️ PARTE 2: Sistema de Dislikes Mejorado

### Cambios:
1. Mover dislikes DESPUÉS de allergies
2. Combinar en la misma sección
3. Si algo está en allergies, NO preguntar en dislikes
4. Dislikes como opciones específicas (no texto libre):
   - Eggs
   - Chicken
   - Beef
   - Pork
   - Fish/Seafood
   - Tofu
   - Dairy
   - Vegetables
   - Rice
   - Pasta
   - Oats
   - Avocado

### Lógica:
```
Si allergies contiene "chicken" → No mostrar "chicken" en dislikes
Si dislikes contiene "chicken" → Eliminar platos de pollo O sustituir
```

---

## 🍽️ PARTE 3: Nueva Base de Datos de 35 Platos

### Breakfasts (7):
1. Overnight Oats con Blueberries - 300 cal | 10g P, 50g C, 5g F
2. Huevos Revueltos con Aguacate y Tostada - 400 cal | 25g P, 25g C, 20g F
3. Omelette de Claras con Vegetales - 200 cal | 25g P, 10g C, 6g F
4. Overnight Oats de Mantequilla de Maní - 400 cal | 15g P, 55g C, 12g F
5. Huevos con Plátano Maduro - 350 cal | 15g P, 40g C, 12g F
6. Bowl de Avena Proteica - 380 cal | 20g P, 50g C, 10g F
7. Scramble de Tofu con Vegetales - 300 cal | 18g P, 30g C, 12g F

### Chicken (7):
8. Pollo a la Plancha con Papa Asada y Ensalada - 450 cal | 40g P, 45g C, 8g F
9. Bowl de Pollo con Arroz y Brócoli - 500 cal | 45g P, 55g C, 8g F
10. Pollo con Plátanos al Air Fryer y Ensalada - 480 cal | 40g P, 50g C, 10g F
11. Muslos de Pollo al Horno con Papa y Zucchini - 520 cal | 38g P, 45g C, 18g F
12. Pollo Salteado con Vegetales y Arroz - 480 cal | 42g P, 52g C, 9g F
13. Wrap de Pollo con Ensalada - 420 cal | 35g P, 35g C, 15g F
14. Pollo a la Plancha con Pasta y Tomate - 550 cal | 45g P, 60g C, 10g F

### Ground Beef (5):
15. Bowl de Carne Molida con Plátanos al Air Fryer - 600 cal | 40g P, 60g C, 18g F
16. Carne Molida con Papa y Vegetales - 550 cal | 38g P, 50g C, 20g F
17. Pasta con Carne Molida - 580 cal | 35g P, 65g C, 18g F
18. Tacos de Carne Molida con Ensalada - 520 cal | 35g P, 45g C, 22g F
19. Arroz con Carne Molida y Vegetales - 530 cal | 38g P, 55g C, 16g F

### Ground Turkey (4):
20. Bowl de Pavo Molido con Arroz y Ensalada - 480 cal | 42g P, 50g C, 10g F
21. Pavo Molido con Plátano Verde y Brócoli - 500 cal | 40g P, 52g C, 12g F
22. Pasta con Pavo Molido y Zucchini - 520 cal | 38g P, 58g C, 12g F
23. Stuffed Peppers con Pavo Molido - 450 cal | 35g P, 45g C, 12g F

### Tuna (4):
24. Ensalada de Atún con Aguacate - 320 cal | 30g P, 15g C, 15g F
25. Arroz con Atún y Vegetales - 400 cal | 32g P, 50g C, 6g F
26. Wrap de Atún - 350 cal | 28g P, 35g C, 8g F
27. Bowl de Atún con Papa y Ensalada - 420 cal | 32g P, 48g C, 8g F

### Tofu - Vegetarian (5):
28. Tofu Salteado con Arroz y Vegetales - 450 cal | 22g P, 60g C, 14g F
29. Bowl de Tofu con Plátano y Ensalada - 420 cal | 20g P, 52g C, 15g F
30. Tofu al Horno con Papa y Zucchini - 400 cal | 22g P, 45g C, 14g F
31. Wrap de Tofu con Vegetales - 380 cal | 18g P, 40g C, 16g F
32. Pasta con Tofu y Tomate - 480 cal | 24g P, 62g C, 14g F

### Light Options (3):
33. Ensalada Proteica con Huevo - 280 cal | 18g P, 12g C, 18g F
34. Bowl de Vegetales Rostizados - 320 cal | 10g P, 48g C, 10g F
35. Atún con Ensalada Grande - 250 cal | 28g P, 18g C, 6g F

---

## 🔄 PARTE 4: Sistema de Sustitución Inteligente

### Lógica de Sustitución:

**Si cliente NO quiere Chicken:**
- Todos los platos de pollo → sustituir con ground beef o ground turkey
- Ajustar macros:
  - Chicken: ~8-10g grasa por porción
  - Ground beef: ~18-22g grasa por porción
  - Ground turkey: ~10-12g grasa por porción
- Recalcular porciones para mantener calorías objetivo

**Si cliente NO quiere Beef:**
- Platos de carne → sustituir con ground turkey o chicken
- Ajustar macros según nueva proteína

**Si cliente NO quiere Fish:**
- Platos de atún → sustituir con chicken o turkey

**Si cliente NO quiere Eggs:**
- Breakfasts con huevo → sustituir con tofu scramble o oats

**Si cliente ES Vegetarian:**
- SOLO mostrar: Tofu meals, egg meals, vegetable meals
- NO mostrar: Chicken, beef, turkey, fish

### Ejemplo de Ajuste:
```
Plato original: Pollo con Arroz
- 45g proteína (pollo), 55g carbs, 8g grasa
- Total: 488 kcal

Cliente no quiere chicken → Cambiar a ground beef:
- 40g proteína (beef), 45g carbs, 18g grasa  
- Total: 518 kcal
- Ajustar porción de arroz para compensar (-10g arroz)
- Nuevo: 40g proteína, 45g carbs, 18g grasa = 502 kcal ✓
```

---

## 📅 PARTE 5: Sistema de Días

### Nueva Pregunta:
"How many days do you want meals for?"
- Options: 4, 5, 6, 7 days

### Cálculo de Comidas Totales:

**Plan 1 (1 main meal/day):**
- 4 días = 4 comidas
- Labels: "DAY 1 - LUNCH", "DAY 2 - LUNCH", "DAY 3 - LUNCH", "DAY 4 - LUNCH"

**Plan 2 (2 main meals/day):**
- 4 días = 8 comidas
- Labels: "DAY 1 - LUNCH", "DAY 1 - DINNER", "DAY 2 - LUNCH", "DAY 2 - DINNER", ...

**Plan 3 (1 breakfast + 1 main/day):**
- 4 días = 8 comidas
- Labels: "DAY 1 - BREAKFAST", "DAY 1 - LUNCH", "DAY 2 - BREAKFAST", "DAY 2 - LUNCH", ...

**Plan 4 (1 breakfast + 2 mains/day):**
- 4 días = 12 comidas
- Labels: "DAY 1 - BREAKFAST", "DAY 1 - LUNCH", "DAY 1 - DINNER", "DAY 2 - BREAKFAST", ...

---

## 📊 PARTE 6: Visualización de Macros Según Plan

### Rules:

**Plans 1, 2, 3:**
- MOSTRAR:
  - ✅ Protein (g)
  - ✅ Calories
  - ✅ Daily totals (protein + calories)
- NO MOSTRAR:
  - ❌ Carbs
  - ❌ Fats

**Plan 4 (Premium):**
- MOSTRAR TODO:
  - ✅ Protein (g)
  - ✅ Carbs (g)
  - ✅ Fats (g)
  - ✅ Calories
  - ✅ Daily totals (all macros)

### Visualización en UI:

**Plan 1, 2, 3:**
```
DAY 1 - LUNCH
Grilled Chicken with Rice and Broccoli
🥩 40g protein  |  🔥 500 calories

DAY 1 TOTALS: 40g protein  |  500 calories
```

**Plan 4:**
```
DAY 1 - LUNCH
Grilled Chicken with Rice and Broccoli
🥩 40g protein  |  🍞 55g carbs  |  🥑 8g fat  |  🔥 500 calories

DAY 1 TOTALS: 120g protein  |  165g carbs  |  24g fat  |  1500 calories
```

---

## 🎯 PARTE 7: Admin Dashboard (Future)

### Features Needed:
- List all clients for today
- Show all meals with exact ingredient weights (grams)
- Show all macros (regardless of client's plan)
- Packing checklist
- Filter by plan, day, client

### Example View:
```
CLIENT: John Doe | PLAN 4 | DAY 1

BREAKFAST - Scrambled Eggs with Avocado
Ingredients:
- Eggs: 150g (3 large eggs)
- Avocado: 60g
- Whole wheat toast: 40g
- Olive oil: 5g
Macros: 25g P, 25g C, 20g F, 400 cal
[ ] Packed

LUNCH - Chicken with Rice
Ingredients:
- Chicken breast: 180g
- White rice (cooked): 200g
- Broccoli: 100g
- Olive oil: 10g
Macros: 45g P, 55g C, 8g F, 500 cal
[ ] Packed
```

---

## 🚀 Orden de Implementación Sugerido

### Session 1 (NOW):
1. ✅ Visual personal data form (sex, exercise, intensity)
2. ✅ Dislikes integration with allergies
3. ✅ Option-based dislike selector
4. ✅ New 35-meal database

### Session 2:
5. Day-based system (number of days question)
6. Meal labeling (DAY X - TYPE)
7. Conditional macro display (hide carbs/fats for Plans 1-3)

### Session 3:
8. Smart protein substitution
9. Macro adjustment for substitutions
10. Portion scaling

### Session 4 (Future):
11. Admin dashboard
12. Client app view
13. Packing checklist

---

## ¿Por Dónde Empezar?

**Recomendación:** Empezar con Session 1 (UI improvements + new meals database)

**Razón:** Son cambios independientes que no afectan el sistema de sustitución complejo.

**Usuario:** ¿Procedo con Session 1 o prefieres otro orden?

