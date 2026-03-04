# 🚀 INSTRUCCIONES DE MERGE - EJECUTAR MANUALMENTE

## ✅ LO QUE YA ESTÁ HECHO:

He creado el branch `main` localmente con todos los fixes implementados.

**Branch creado:** `main`  
**Commits incluidos:** 10+ commits con todas las correcciones  
**Último commit:** `d9b484d` - Snack recommendations feature

---

## 🎯 LO QUE TÚ NECESITAS HACER:

### OPCIÓN 1: Push Simple (Recomendado)

Ejecuta este comando en tu terminal con tus credenciales de GitHub:

```bash
cd /ruta/a/chontaduro-backend
git checkout main
git push -u origin main
```

**Tiempo:** 30 segundos  
**Resultado:** Branch `main` en GitHub con todos los fixes

---

### OPCIÓN 2: Script Automático

He creado un script que puedes ejecutar:

```bash
cd /ruta/a/chontaduro-backend
./push_main.sh
```

---

## 📊 CONTENIDO DEL MERGE:

El branch `main` incluye estos commits:

- ✅ `d9b484d` - Snack recommendations (10 opciones)
- ✅ `60b4db6` - Universal activity minimums
- ✅ `b528757` - Age/calorie validations
- ✅ `21d0a56` - Recomp minimum 1.50 factor
- ✅ `c02e34e` - Activity factors increased (1.55 for 5-7 days)
- ✅ `62a009f` - Recomp deficit 12%
- ✅ `170b2df` - Objective string matching
- ✅ `f0f6620` - Daily macros fix
- ✅ `8452a6e` - Protein calculation fix
- ✅ `a84d77a` - Field names fix
- ... y más

**Total:** 10+ commits con TODAS las correcciones

---

## ✅ VERIFICACIÓN POST-PUSH:

Después de hacer el push, verifica en GitHub:

1. Ve a: https://github.com/chontaduroprepmeals/chontaduro-backend
2. Deberías ver el branch `main`
3. Último commit: `d9b484d`
4. Total commits: 10+

---

## 🚀 DEPLOYMENT:

Después del push:

1. **Si tienes auto-deploy:** Espera 2-5 minutos
2. **Si es manual:** 
   ```bash
   # En servidor de producción:
   git pull origin main
   sudo systemctl restart app  # o pm2 restart
   ```

---

## 🧪 TESTING POST-DEPLOYMENT:

1. **Limpiar caché:** Ctrl+Shift+Delete → Todo el tiempo → Caché
2. **Probar con:**
   - Peso: 140 lb (63.5 kg)
   - Altura: 160 cm
   - Edad: 28 años
   - Días: **5 días/semana**
   - Objetivo: **Body Recomposition**

3. **Verificar:**
   - ✅ TDEE: ~2,068 kcal (NO 1,600)
   - ✅ Target: ~1,820 kcal (NO 1,500)
   - ✅ Proteína: 133g
   - ✅ Carbs: 198g (NO 120g)
   - ✅ Snacks: 3 opciones visibles

---

## ❓ TROUBLESHOOTING:

**Si el push falla con "403 Forbidden":**
- Verifica que estés logueado en GitHub
- Usa: `git config --global credential.helper store`
- O usa SSH en vez de HTTPS

**Si ves valores viejos después del deployment:**
1. Limpia caché completamente
2. Prueba en ventana incógnito
3. Verifica que pusiste 5 días (no 0)

---

## 📞 SOPORTE:

Si necesitas ayuda, verifica:
- Estado del push: `git status`
- Logs del servidor: `sudo journalctl -u app -f`
- API response: Usa curl o Postman

---

**STATUS:** ✅ Branch main creado localmente, esperando push manual

**ACCIÓN:** Ejecutar `git push -u origin main` con tus credenciales

**TIEMPO:** 30 segundos

**¡LISTO PARA PUSH!** 🚀
