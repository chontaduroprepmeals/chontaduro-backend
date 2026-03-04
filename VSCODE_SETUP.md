# 🎨 Guía Visual: VS Code y Git

## ¿Dónde Hacer el Push en VS Code?

### MÉTODO 1: Terminal Integrada (Más Fácil)

1. **Abrir Terminal en VS Code:**
   ```
   Menu: Terminal → New Terminal
   Atajo: Ctrl + Ñ (Windows/Linux) o Cmd + Ñ (Mac)
   ```

2. **Ejecutar Comandos:**
   ```bash
   git checkout copilot/fix-register-route-issues
   git checkout -b main
   git push -u origin main
   ```

3. **¡Listo!** 🎉

---

### MÉTODO 2: Interfaz Gráfica de VS Code

#### PASO 1: Abrir Source Control
```
📍 Ubicación: Barra lateral izquierda
🔍 Icono: Ramificación (🌿)
⌨️ Atajo: Ctrl + Shift + G
```

#### PASO 2: Cambiar de Branch
```
📍 Ubicación: Esquina inferior izquierda
👆 Click en el nombre del branch
📋 Selecciona: copilot/fix-register-route-issues
```

#### PASO 3: Crear Branch Main
```
1. Click en los 3 puntos (···) en Source Control
2. Branch → Create Branch
3. Nombre: main
4. Enter
```

#### PASO 4: Publicar Branch
```
📍 Ubicación: Botón en la parte inferior de Source Control
🔵 Botón: "Publish Branch"
👆 Click
✅ Ingresa credenciales si lo pide
```

---

## 🖼️ Mapeo Visual de VS Code

```
┌────────────────────────────────────────────────────────────┐
│  VS Code - Vista Principal                                 │
├────────────────────────────────────────────────────────────┤
│                                                            │
│  ┌─────────┬──────────────────────────────────────────┐  │
│  │ 📁 Exp  │  main.py                                  │  │
│  │ 🔍 Bus  │  ┌─────────────────────────────────────┐ │  │
│  │ 🌿 SCM  │  │ def compute_activity_factor(...):   │ │  │
│  │ 🐛 Deb  │  │     days_map = {                    │ │  │
│  │ 🧩 Ext  │  │         "0": 1.2,                   │ │  │
│  │         │  │         "1-2": 1.375,               │ │  │
│  └─────────┤  │         "3-4": 1.50,                │ │  │
│            │  │         "5-7": 1.55  ← NUEVO       │ │  │
│            │  │     }                                │ │  │
│            │  └─────────────────────────────────────┘ │  │
│            └──────────────────────────────────────────┘  │
│                                                            │
│  ┌──────────────────────────────────────────────────────┐ │
│  │ TERMINAL                                              │ │
│  │ $ git checkout copilot/fix-register-route-issues     │ │
│  │ $ git checkout -b main                                │ │
│  │ $ git push -u origin main                             │ │
│  └──────────────────────────────────────────────────────┘ │
│                                                            │
│  [🌿 copilot/fix-register-route-issues] ← Branch actual  │
└────────────────────────────────────────────────────────────┘
```

---

## 🎯 Ubicación de Cada Elemento en VS Code

### Barra Lateral Izquierda:
```
📁 Explorer (Ctrl+Shift+E)
   → Ver archivos del proyecto

🔍 Search (Ctrl+Shift+F)
   → Buscar en archivos

🌿 Source Control (Ctrl+Shift+G)  ← AQUÍ ESTÁ GIT
   → Ver cambios, commits, branches

🐛 Debug (Ctrl+Shift+D)
   → Depuración

🧩 Extensions (Ctrl+Shift+X)
   → Instalar extensiones
```

### Barra Inferior:
```
┌──────────────────────────────────────────────────────┐
│ 🌿 copilot/fix-... │ ⚠️ 0 🚫 0 │ LF │ Python │ UTF-8 │
└──────────────────────────────────────────────────────┘
    ↑ Branch actual     Errores   Idioma  Encoding
    CLICK AQUÍ para cambiar branch
```

---

## 📋 Source Control Panel (Ctrl+Shift+G)

```
┌─────────────────────────────────────────┐
│ SOURCE CONTROL                    ···  │ ← Click en ··· para más opciones
├─────────────────────────────────────────┤
│ Message: "..."                          │
│ [✓ Commit]  [↻ Sync]                   │
├─────────────────────────────────────────┤
│ CHANGES (0)                             │
│   (no changes)                          │
├─────────────────────────────────────────┤
│ COMMITS                                 │
│   📌 3f02f49 - MERGE: Instructions      │
│   📌 d9b484d - Snack recommendations    │
│   📌 60b4db6 - Universal minimums       │
│   📌 b528757 - Age validations          │
│   ...                                   │
└─────────────────────────────────────────┘
         ↑ Historial de commits
```

---

## 🎮 Atajos de Teclado Útiles

### Generales:
- `Ctrl + Ñ` → Abrir/cerrar terminal
- `Ctrl + Shift + P` → Command Palette
- `Ctrl + Shift + G` → Source Control

### Git:
- `Ctrl + Shift + P` → Tipo "Git: Checkout to..."
- `Ctrl + Shift + P` → Tipo "Git: Create Branch..."
- `Ctrl + Shift + P` → Tipo "Git: Push"

---

## 🔄 Flujo Completo en VS Code

### Opción A: Todo con Terminal
```bash
# 1. Abrir terminal (Ctrl+Ñ)
# 2. Ejecutar:
git checkout copilot/fix-register-route-issues
git checkout -b main
git push -u origin main
```

### Opción B: Todo con UI
```
1. Source Control (Ctrl+Shift+G)
2. Click en branch (esquina inferior izquierda)
3. Seleccionar: copilot/fix-register-route-issues
4. Command Palette (Ctrl+Shift+P)
5. Escribir: "Git: Create Branch"
6. Nombre: main
7. Source Control → Publish Branch
```

### Opción C: Mixto (Recomendado)
```
1. Source Control (Ctrl+Shift+G)
2. Click en branch → copilot/fix-register-route-issues
3. Terminal (Ctrl+Ñ):
   git checkout -b main
   git push -u origin main
```

---

## ⚡ Comandos Rápidos desde Command Palette

Presiona `Ctrl + Shift + P` y escribe:

```
> Git: Checkout to...
  → Cambiar de branch

> Git: Create Branch...
  → Crear nuevo branch

> Git: Push
  → Hacer push

> Git: Pull
  → Traer cambios

> Git: Fetch
  → Actualizar info de branches
```

---

## 🎨 Personalización Útil

### Settings (Ctrl + ,):
```json
{
  "git.autofetch": true,
  "git.confirmSync": false,
  "git.enableSmartCommit": true,
  "terminal.integrated.defaultProfile.windows": "Git Bash"
}
```

---

## 🆘 Problemas Comunes

### "No veo Source Control"
```
Solución:
1. View → SCM
2. O Ctrl+Shift+G
```

### "Git no está instalado"
```
Solución:
1. Descargar: https://git-scm.com/
2. Instalar
3. Reiniciar VS Code
```

### "No veo el branch nuevo"
```
Solución en terminal:
git fetch origin
git branch -a
```

### "Credenciales requeridas"
```
Solución:
1. GitHub → Settings → Developer Settings
2. Personal Access Tokens → Generate
3. Copiar token
4. Usar como password en VS Code
```

---

## 📚 Recursos Adicionales

- **GitLens Extension:** Visualización avanzada de Git
- **Git Graph Extension:** Ver historial gráfico
- **GitHub Extension:** Integración con GitHub

Instalar:
1. `Ctrl+Shift+X`
2. Buscar: "GitLens"
3. Install

---

## ✅ Verificación Final

Después de hacer el push, deberías ver:

```
✅ En VS Code (esquina inferior):
   🌿 main ← Branch actual

✅ En GitHub:
   Branch "main" existe

✅ En terminal:
   Successfully pushed to origin/main
```

---

## 🎯 TL;DR (Demasiado Largo; No Leí)

**La manera más fácil:**
1. Abre terminal en VS Code (`Ctrl+Ñ`)
2. Ejecuta:
   ```bash
   git checkout copilot/fix-register-route-issues
   git checkout -b main
   git push -u origin main
   ```
3. ¡Listo!

---

**¿Aún tienes dudas?** Revisa el archivo `MERGE_INSTRUCTIONS.md` para más detalles.
