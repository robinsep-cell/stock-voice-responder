# 📱 Stock Voice - Automatización de Consultas

He creado una aplicación optimizada para móviles que te permite responder a las consultas del Call Center de forma rápida, incluso usando tu voz.

## ✨ Características Principales
- **📱 Mobile First**: Diseño premium pensado para ser usado desde el celular.
- **🎤 Respuesta por Voz**: Botón de micrófono integrado para dictar respuestas sin escribir.
- **🔍 Detección de Duplicados**: El sistema te avisa si el mismo producto ya fue respondido en otra fila anteriormente.
- **⚡ Sincronización Real**: Lee directamente de tu Google Sheet y actualiza al instante las columnas de "La Reina".
- **🎨 Diseño Premium**: Interfaz moderna con efectos de cristal y animaciones fluidas.

## 🛠️ Estructura del Proyecto
- `app.py`: Servidor Backend en Python (Flask).
- `templates/index.html`: Estructura de la aplicación móvil.
- `static/css/style.css`: Estilo visual premium.
- `static/js/script.js`: Lógica de voz y comunicación con la hoja de cálculo.

## 🚀 Cómo empezar
1. **Credenciales**: Necesitas un archivo `credentials.json` de una Cuenta de Servicio de Google Cloud (con acceso a Google Sheets API).
    - Asegúrate de compartir tu Google Sheet con el correo de la cuenta de servicio (ej: `tu-cuenta@proyecto.iam.gserviceaccount.com`).
2. **Instalación**:
   ```bash
   pip install -r requirements.txt
   ```
3. **Ejecución**:
   ```bash
   python3 app.py
   ```
4. **Acceso**: Abre `http://localhost:5001` (o la IP de tu computadora en la red local) desde tu celular.

---
**¿Deseas que te ayude a configurar las credenciales de Google o prefieres que despleguemos esto en la nube (como Railway) para que puedas acceder desde cualquier lugar?**
