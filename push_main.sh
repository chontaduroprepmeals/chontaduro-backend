#!/bin/bash

# Script para hacer push del branch main a GitHub
# Ejecutar con: ./push_main.sh

echo "🚀 Iniciando push del branch main..."
echo ""

# Verificar que estamos en el directorio correcto
if [ ! -d ".git" ]; then
    echo "❌ Error: No estás en el directorio del repositorio"
    echo "   Ejecuta: cd /ruta/a/chontaduro-backend"
    exit 1
fi

# Verificar que el branch main existe
if ! git rev-parse --verify main >/dev/null 2>&1; then
    echo "❌ Error: Branch 'main' no existe localmente"
    echo "   Creándolo desde copilot/fix-register-route-issues..."
    git checkout copilot/fix-register-route-issues
    git checkout -b main
fi

# Checkout al branch main
echo "📂 Cambiando a branch main..."
git checkout main

# Mostrar información
echo ""
echo "ℹ️  Información del branch:"
echo "   Branch actual: $(git branch --show-current)"
echo "   Último commit: $(git log -1 --oneline)"
echo ""

# Confirmar con el usuario
read -p "¿Deseas hacer push del branch main a origin? (s/n) " -n 1 -r
echo ""

if [[ $REPLY =~ ^[Ss]$ ]]; then
    echo "⬆️  Haciendo push..."
    
    # Intentar push
    if git push -u origin main; then
        echo ""
        echo "✅ ¡Push exitoso!"
        echo ""
        echo "📊 Siguiente paso:"
        echo "   1. Ve a: https://github.com/chontaduroprepmeals/chontaduro-backend"
        echo "   2. Verifica que el branch 'main' existe"
        echo "   3. Despliega a producción"
        echo "   4. Limpia caché del navegador"
        echo "   5. Prueba con 5 días/semana de entrenamiento"
        echo ""
        echo "🎉 ¡Merge completado!"
    else
        echo ""
        echo "❌ Error en el push"
        echo ""
        echo "💡 Posibles soluciones:"
        echo "   1. Verifica tus credenciales de GitHub"
        echo "   2. Usa SSH en vez de HTTPS:"
        echo "      git remote set-url origin git@github.com:chontaduroprepmeals/chontaduro-backend.git"
        echo "   3. Configura credenciales:"
        echo "      git config --global credential.helper store"
        echo ""
        exit 1
    fi
else
    echo ""
    echo "❌ Push cancelado"
    echo "   Puedes ejecutar manualmente: git push -u origin main"
    exit 0
fi
