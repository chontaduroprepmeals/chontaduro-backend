# 📋 Instrucciones para Sincronizar tu Código Local (VSCode)

## ¿Qué se cambió?

Hemos agregado un flujo completo de pago al frontend que ahora incluye:

### ✅ Botón "Place Order" (Hacer Pedido)
- Ahora cuando generas un menú, verás un botón verde grande que dice **"🛒 Place Order"**
- Este botón aparece junto al botón "Regenerate Full Menu"

### ✅ Modal de Información del Cliente
Cuando haces clic en "Place Order", aparece un formulario que pide:
- **Nombre completo** (obligatorio)
- **Email** (obligatorio)
- **Contraseña** (obligatorio, mínimo 6 caracteres)

### ✅ Integración con Stripe
- Después de llenar el formulario, el sistema:
  1. Valida que todos los campos estén completos
  2. Crea tu cuenta de usuario en la base de datos
  3. Calcula el total de tu pedido basado en el menú
  4. Te redirige a Stripe para que pagues de forma segura

---

## 🔄 Cómo Sincronizar tu Código Local en VSCode

### Opción 1: Usando Git en VSCode (Recomendado)

1. **Abre VSCode** en tu laptop
2. **Abre la terminal** en VSCode (Terminal → New Terminal o Ctrl+`)
3. **Verifica que estés en la rama correcta:**
   ```bash
   git branch
   ```
   
4. **Descarga los cambios desde GitHub:**
   ```bash
   git fetch origin
   ```

5. **Cambia a la rama con los nuevos cambios:**
   ```bash
   git checkout copilot/fix-register-route-issues
   ```

6. **Actualiza tu código local con los cambios de GitHub:**
   ```bash
   git pull origin copilot/fix-register-route-issues
   ```

### Opción 2: Usando la Interfaz de VSCode

1. **Abre VSCode**
2. En el panel izquierdo, haz clic en el ícono de **Source Control** (Control de Código Fuente, parece tres círculos conectados)
3. Haz clic en los **tres puntos (...)** en la parte superior del panel
4. Selecciona **Pull** (o **Fetch** primero, luego **Pull**)

---

## 🚀 Para Ver los Cambios en Render

### Ya está automático:
Si configuraste Render para que se despliegue automáticamente cuando haces push a GitHub, los cambios ya deberían estar en https://chontaduro-backend.onrender.com después de unos minutos.

### Si necesitas desplegar manualmente en Render:
1. Ve a https://dashboard.render.com
2. Encuentra tu servicio "chontaduro-backend"
3. Haz clic en **"Manual Deploy"** → **"Deploy latest commit"**

---

## 🧪 Para Probar Localmente en tu Laptop

1. **Abre la terminal en VSCode**
2. **Asegúrate de tener las dependencias instaladas:**
   ```bash
   pip install -r requirements.txt
   ```

3. **Inicia el servidor:**
   ```bash
   python -m uvicorn main:app --reload
   ```

4. **Abre tu navegador y ve a:**
   ```
   http://localhost:8000
   ```

---

## 📝 Resumen de Archivos Modificados

### `index.html`
- ✅ Agregado modal de checkout (HTML + CSS)
- ✅ Agregado botón "Place Order" en la vista del menú
- ✅ Agregado función `proceedToCheckout()` para mostrar el modal
- ✅ Agregado función `handleCheckoutSubmit()` para procesar el pago

### `main.py`
- ✅ Corregido el endpoint `/register` para usar base de datos SQLite
- ✅ Corregido el endpoint `/create-checkout-session` para usar base de datos
- ✅ Eliminadas rutas duplicadas que causaban conflictos
- ✅ Corregida la inicialización de la base de datos

---

## ❓ Preguntas Frecuentes

### ¿Por qué no veo los cambios en mi laptop?
- Necesitas hacer `git pull` para descargar los cambios de GitHub a tu computadora local

### ¿Los cambios ya están en Render?
- Si configuraste auto-deploy: SÍ, deberían estar desplegados automáticamente
- Si no: Necesitas hacer un deploy manual desde el dashboard de Render

### ¿Cómo sé si funcionó?
- Visita https://chontaduro-backend.onrender.com
- Genera un menú
- Deberías ver el botón verde "🛒 Place Order"
- Al hacer clic, debería aparecer un formulario pidiendo Nombre, Email y Contraseña

---

## 🎯 Flujo Completo del Usuario

1. Usuario visita la página
2. Completa el formulario de preferencias (plan, duración, restricciones, etc.)
3. Se genera un menú personalizado
4. Usuario revisa el menú y puede:
   - Modificar proteínas
   - Intercambiar comidas (Swap)
   - Regenerar el menú completo
5. **NUEVO:** Usuario hace clic en "🛒 Place Order"
6. **NUEVO:** Aparece modal pidiendo:
   - Nombre
   - Email
   - Contraseña
7. **NUEVO:** Usuario llena el formulario y hace clic en "Proceed to Payment"
8. **NUEVO:** Sistema crea cuenta y redirige a Stripe
9. Usuario completa el pago en Stripe
10. Redirige de vuelta a la página de éxito/cancelación

---

## 💡 Siguiente Paso

Después de sincronizar tu código local, verifica que todo funcione:
1. Haz `git pull` para obtener los cambios
2. Ve a Render para confirmar que el deploy se completó
3. Prueba el flujo completo en https://chontaduro-backend.onrender.com

¡Los cambios están listos y funcionando! 🎉
