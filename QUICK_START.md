# ⚡ QUICK START - Hacer el Push en 30 Segundos

## 🎯 SI SOLO QUIERES HACER EL PUSH RÁPIDO:

### EN VS CODE:

1. **Abre la terminal:** `Ctrl + Ñ`

2. **Copia y pega esto:**
   ```bash
   git checkout copilot/fix-register-route-issues && git checkout -b main && git push -u origin main
   ```

3. **Presiona ENTER**

4. **¡Listo!** 🎉

---

## 📚 SI QUIERES MÁS DETALLES:

- **VSCODE_SETUP.md** - Guía visual completa de VS Code
- **MERGE_INSTRUCTIONS.md** - Guía detallada del proceso completo
- **push_main.sh** - Script automático paso a paso

---

## ✅ VERIFICAR QUE FUNCIONÓ:

Después del push, verifica:

1. **En VS Code:**
   - Esquina inferior izquierda dice: "🌿 main"

2. **En GitHub:**
   - Ve a: https://github.com/chontaduroprepmeals/chontaduro-backend
   - Verifica que existe el branch "main"

---

## 🆘 SI HAY PROBLEMAS:

**Problema: "Git not found"**
```bash
# Instala Git primero:
# Windows: https://git-scm.com/download/win
# Mac: brew install git
# Linux: sudo apt install git
```

**Problema: "Authentication failed"**
```bash
# Usa un Personal Access Token de GitHub
# GitHub → Settings → Developer Settings → Tokens
```

**Problema: "Branch already exists"**
```bash
# Si ya existe main, haz merge:
git checkout main
git merge copilot/fix-register-route-issues
git push origin main
```

---

## 🎯 DESPUÉS DEL PUSH:

1. **Desplegar** a producción (Render, Heroku, etc.)
2. **Limpiar caché** del navegador
3. **Probar** con 5 días/semana de entrenamiento
4. **Verificar** que TDEE = ~2,068 kcal (no 1,600)

---

**¿TODO LISTO?** ¡Ejecuta el comando y termina en 30 segundos! 🚀
