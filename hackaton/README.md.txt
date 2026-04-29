# Puul Hackathon - Motor de Matching Geoespacial

Este proyecto implementa un **motor de matching geoespacial** que evalúa rutas de conductores y determina cuáles son compatibles con la solicitud de viaje de un pasajero.

Además, genera un archivo HTML interactivo para visualizar:

* Rutas válidas
* Rutas rechazadas
* Puntaje de compatibilidad
* Cobertura de trayecto
* Distancias de pickup y dropoff
* Métricas de evaluación

---

# Requisitos

Antes de ejecutar el proyecto, asegúrate de tener instalado:

* **Python 3.9 o superior**
* **pip**
* Librería **pandas**

---

# Instalación

## 1. Clonar el repositorio

```bash id="2y20w0"
git clone https://github.com/TU_USUARIO/puul-hackathon.git
```

## 2. Entrar al directorio del proyecto

```bash id="r0s1qk"
cd puul-hackathon
```

## 3. Instalar dependencias

```bash id="y1w7sa"
pip install pandas
```

---

# Estructura del proyecto

```bash id="vq5y5t"
puul-hackathon/
│── main.py
│── routes.csv
│── sample_searches.csv
│── resultado_hackathon.html
│── README.md
```

### Archivos:

* **main.py** → Script principal del motor de matching
* **routes.csv** → Base de rutas de conductores
* **sample_searches.csv** → Casos de prueba de pasajeros
* **resultado_hackathon.html** → Visualización interactiva generada por el script

---

# Cómo ejecutar

Corre el siguiente comando:

```bash id="u1e3y4"
python main.py
```

Esto generará automáticamente:

```bash id="vgpxqs"
resultado_hackathon.html
```

---

# Visualizar resultados

Una vez generado el archivo HTML, ábrelo en tu navegador:

```bash id="1xj7kx"
resultado_hackathon.html
```

Ahí podrás visualizar:

* Casos de prueba
* Matches encontrados
* Rutas rechazadas
* Score de coincidencia
* Métricas detalladas
* Visualización en mapa

---

# Lógica de evaluación

El algoritmo evalúa cada ruta usando los siguientes criterios:

### 1. Dirección (25%)

Verifica que el punto de subida ocurra antes que el punto de bajada en la ruta.

### 2. Cobertura (20%)

Mide cuánto del trayecto del pasajero es cubierto por la ruta del conductor.

### 3. Compatibilidad horaria (20%)

Evalúa la diferencia entre la hora solicitada y la salida del conductor.

### 4. Desvío estimado (20%)

Penaliza rutas que requieren mayor desvío para recoger o dejar al pasajero.

### 5. Utilidad (15%)

Combina cobertura y proximidad para priorizar rutas útiles.

---

# Salida esperada

Al ejecutar correctamente, verás algo como:

```bash id="8p0l0w"
Caso 1: 5 matches | 120 backtrack | 35 proximidad
Caso 2: 3 matches | 98 backtrack | 52 proximidad
HTML generado: resultado_hackathon.html
```

---

# Notas

* El archivo `resultado_hackathon.html` se genera dinámicamente en cada ejecución.
* Asegúrate de que `routes.csv` y `sample_searches.csv` estén en el mismo directorio que `main.py`.
* Si cambias los datos CSV, vuelve a ejecutar `main.py`.

---

# Autor

Proyecto desarrollado para el **Hackathon Puul - Motor de Matching Geoespacial**.
