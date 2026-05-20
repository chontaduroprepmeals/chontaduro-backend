# 🎨 Cambios Visuales y Flujo de Checkout (Actualizado)

## ✅ Flujo actual implementado
1. Usuario completa formulario nutricional.
2. Se genera y muestra el menú personalizado.
3. Botón visible: **🛒 Order Now**.
4. Se abre modal de checkout en 2 pasos:
	- **Paso 1:** registro/autenticación (nombre, email, password).
	- **Paso 2:** resumen del pedido + impuesto WA 10.25% + método de pago.
5. Pago con:
	- **Stripe (tarjeta)**, o
	- **Zelle** + subida de screenshot + confirmación.
6. Confirmación de pedido y envío de email (si SMTP está configurado).

## ✅ Cambios visuales en frontend
- Botón del menú cambiado a **Order Now**.
- Modal de checkout con estilos consistentes en naranja (igual al resto del flujo).
- Paso de registro con validaciones claras.
- Campo password con botón **mostrar/ocultar** (👁️ / 🙈).
- Paso de resumen con:
  - subtotal,
  - tax Washington 10.25%,
  - total final,
  - acciones separadas para Stripe y Zelle.

## ✅ Correcciones recientes incluidas
- Fix de persistencia de sesión: se guarda `state.menu` al generar menú en `review`.
- Solucionado error: **"No generated menu found in session"**.
- Alergias mostradas correctamente en UI con tipo `multiselect`.

## 💵 Precios y total
- `main_menu`: $15
- `breakfast`: $11
- Impuesto WA: **10.25%**

Ejemplo:
- 1 breakfast + 1 main_menu = $26.00
- Tax = $2.67
- **Total = $28.67**

## 🔒 Seguridad (estado actual)
- Password hashing con **bcrypt** (no SHA-256).
- CORS restringido a orígenes explícitos.
- Login con lockout temporal por intentos fallidos.
- `session_id` generado con `uuid4`.

## 🧪 Checklist de validación manual E2E
1. Generar menú y verificar botón **Order Now**.
2. Abrir modal, validar toggle de password.
3. Completar registro con datos válidos.
4. Confirmar que aparece resumen con tax 10.25%.
5. Probar pago tarjeta (Stripe) y redirección.
6. Probar flujo Zelle:
	- subir screenshot,
	- confirmar pago,
	- ver mensaje final de confirmación.
7. Revisar logs para confirmación de email enviado (si SMTP activo).

## ⚙️ Variables de entorno necesarias en producción
- `STRIPE_SECRET_KEY`
- `STRIPE_WEBHOOK_SECRET`
- `SMTP_HOST`
- `SMTP_PORT`
- `SMTP_USERNAME`
- `SMTP_PASSWORD`
- `SMTP_FROM_EMAIL`
- `ZELLE_PAYEE_NAME`
- `ZELLE_PAYEE_EMAIL`
- `ZELLE_PAYEE_PHONE`
- `CORS_ALLOWED_ORIGINS`
