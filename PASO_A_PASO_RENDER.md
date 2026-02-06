# 🎯 PASO A PASO: Cambiar la Rama en Render

## 📋 Instrucciones Completas

### PASO 1: Ir a Render Dashboard
```
🌐 Abre tu navegador
📍 Ve a: https://dashboard.render.com
🔑 Inicia sesión si no lo has hecho
```

### PASO 2: Encontrar tu Servicio
```
En el dashboard verás una lista de servicios.

Busca el que se llama:
┌─────────────────────────────────┐
│ 🟢 chontaduro-backend           │
│    Web Service                   │
│    https://chontaduro-backen... │
└─────────────────────────────────┘

👆 HAZ CLIC AQUÍ
```

### PASO 3: Ir a Settings
```
En la parte superior verás pestañas:

┌─────────────────────────────────────────────┐
│ Overview | Environment | Settings | Events  │
│                         ^^^^^^^^             │
│                         HAZ CLIC AQUÍ       │
└─────────────────────────────────────────────┘
```

### PASO 4: Buscar la Sección "Build & Deploy"
```
Desplázate hacia abajo hasta encontrar:

┌──────────────────────────────────────┐
│ Build & Deploy                       │
├──────────────────────────────────────┤
│                                      │
│ Branch                               │
│ ┌────────────────────────────┐      │
│ │ main                    ▼  │  ◄── AQUÍ
│ └────────────────────────────┘      │
│                                      │
│ Build Command                        │
│ ┌────────────────────────────┐      │
│ │ ...                         │      │
│ └────────────────────────────┘      │
└──────────────────────────────────────┘

👆 HAZ CLIC EN EL DROPDOWN "main"
```

### PASO 5: Cambiar a la Rama Correcta
```
Al hacer clic en el dropdown verás:

┌────────────────────────────────────────┐
│ Select Branch                          │
├────────────────────────────────────────┤
│ ◉ main                                 │
│ ○ copilot/fix-register-route-issues   │ ◄── SELECCIONA ESTA
└────────────────────────────────────────┘

👆 HAZ CLIC EN "copilot/fix-register-route-issues"
```

### PASO 6: Guardar Cambios
```
Después de seleccionar la rama, verás un botón:

┌────────────────────┐
│  Save Changes      │  ◄── HAZ CLIC AQUÍ
└────────────────────┘

Render mostrará un mensaje confirmando el cambio.
```

### PASO 7: Esperar el Deploy
```
Render automáticamente empezará a desplegar:

┌─────────────────────────────────────────┐
│ 🔄 Deploying...                         │
│                                          │
│ ████████░░░░░░░░░░░░ 40%               │
│                                          │
│ Building application...                 │
└─────────────────────────────────────────┘

⏱️ Esto tarda 2-5 minutos normalmente.

Puedes ir a la pestaña "Events" para ver el progreso.
```

### PASO 8: Verificar que Terminó
```
Cuando termine, verás:

┌─────────────────────────────────────────┐
│ 🟢 Live                                 │
│                                          │
│ Your service is live at:                │
│ https://chontaduro-backend.onrender.com │
└─────────────────────────────────────────┘

✅ ¡El deploy está completo!
```

### PASO 9: Probar el Botón
```
1. Abre una nueva pestaña
2. Ve a: https://chontaduro-backend.onrender.com
3. Completa el formulario de preferencias
4. Genera un menú
5. Busca el botón:

   ┌─────────────────┐  ┌──────────────────┐
   │ Regenerate Menu │  │ 🛒 Place Order  │ ◄── DEBE APARECER
   └─────────────────┘  └──────────────────┘

6. Haz clic en "🛒 Place Order"
7. Debe aparecer un formulario pidiendo:
   - Nombre
   - Email
   - Contraseña
```

---

## 🔍 VERIFICACIÓN: ¿Cuál rama está usando Render?

Puedes verificar en cualquier momento cuál rama está desplegando:

```
1. Ve a Render Dashboard
2. Haz clic en tu servicio
3. En la parte superior derecha verás:

   ┌──────────────────────────────────────┐
   │ Branch: copilot/fix-register-rou...  │ ◄── DEBE DECIR ESTO
   └──────────────────────────────────────┘

   Si dice "main" → Cambiar siguiendo los pasos arriba
   Si dice "copilot/fix-..." → ✅ Está correcto
```

---

## 📸 SI NECESITAS CAPTURAS DE PANTALLA

Si no encuentras algo:

1. Ve a la sección de Settings en Render
2. Toma una captura de pantalla
3. Compártela conmigo
4. Te ayudaré a encontrar la configuración exacta

---

## ⚠️ PROBLEMAS COMUNES

### "No veo la rama copilot/fix-register-route-issues"

**Solución:**
- Asegúrate de que estés viendo el servicio correcto
- La rama existe en GitHub, así que Render debería verla
- Intenta refrescar la página de Render
- Si no aparece, puede que Render necesite reconectar con GitHub

### "El deploy falla"

**Qué hacer:**
1. Ve a Events o Logs en Render
2. Busca el mensaje de error
3. Copia el error completo
4. Compártelo conmigo para ayudarte

### "El botón sigue sin aparecer"

**Checklist:**
- ✅ ¿La rama está cambiada a "copilot/fix-register-route-issues"?
- ✅ ¿El deploy dice "Live" en verde?
- ✅ ¿Has refrescado la página con Ctrl+F5?
- ✅ ¿El cache del navegador está limpio?

Si todo esto está correcto y sigue sin aparecer:
→ Revisa los logs de Render
→ Busca errores en la consola del navegador (F12)

---

## 🎉 DESPUÉS DE CAMBIAR LA RAMA

Una vez que cambies la rama, NO necesitas:
- ❌ Sincronizar tu VSCode local
- ❌ Hacer nada en tu laptop
- ❌ Volver a hacer deploy manual
- ❌ Cambiar configuraciones adicionales

Solo necesitas:
- ✅ Esperar que termine el deploy
- ✅ Refrescar la página
- ✅ Probar el botón

---

## 💡 NOTA IMPORTANTE

**Una vez que funcione, si quieres seguir usando la rama main:**

Opción 1: Dejar Render en la rama "copilot/..." (funciona perfectamente)

Opción 2: Hacer merge a main:
1. Ve a GitHub
2. Crea un Pull Request de "copilot/..." a "main"
3. Haz merge
4. Vuelve a cambiar Render a la rama "main"

---

**¿Listo para cambiar la rama?** 🚀

Sígueme estos pasos y en 5 minutos el botón debería aparecer.

Si tienes cualquier duda en algún paso, pregúntame. 😊
