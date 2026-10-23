import os
import time
from openai import OpenAI

# Cargar variables de entorno locales si dotenv está disponible
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

categorias = [
    "bricolaje-y-herramientas",
    "informatica",
    "productos-para-mascotas",
    "hogar-y-cocina",
    "deportes-y-aire-libre",
    "cuidado-personal"
]

HISTORIAL_FILE = "historial_productos.txt"

# Si el archivo no existe, crearlo vacío
if not os.path.exists(HISTORIAL_FILE):
    with open(HISTORIAL_FILE, "w", encoding="utf-8") as f:
        pass

# Leer el contenido del archivo y guardarlo en una lista de Python (eliminando saltos de línea)
with open(HISTORIAL_FILE, "r", encoding="utf-8") as f:
    lista_historial = [line.strip() for line in f if line.strip()]

total_categorias = len(categorias)
print(f"🤖 Iniciando autopiloto escalado ({total_categorias} categorías diarias)...")
print(f"🧠 Memoria a largo plazo cargada: {len(lista_historial)} productos en el historial.")

for idx, categoria in enumerate(categorias, start=1):
    print(f"\n--- 📂 [{idx}/{total_categorias}] Categoría: {categoria} ---")

    prompt = (
        f"Genera el nombre exacto de un modelo de producto muy vendido en Amazon España de la categoría '{categoria}'. "
        f"Debe ser un producto específico y real (ej: 'Makita DHP482Z' o 'Logitech MX Master 3S'). "
        f"REGLA ABSOLUTA: Bajo ningún concepto puedes generar un producto que esté en esta lista de excluidos: {lista_historial}. "
        f"Si la lista tiene elementos, busca un producto diferente, quizás el 2º, 3º o 4º más vendido. "
        f"Responde ÚNICAMENTE con el nombre del producto, sin comillas ni texto adicional."
    )

    try:
        respuesta = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.9
        )

        producto = respuesta.choices[0].message.content.strip().strip('"\'')

        # Añadir a la lista en memoria (para que no lo repita en el mismo ciclo)
        lista_historial.append(producto)

        # Escribirlo inmediatamente en historial_productos.txt (usando modo append 'a')
        with open(HISTORIAL_FILE, "a", encoding="utf-8") as f:
            f.write(f"{producto}\n")

        print(f"📦 Producto seleccionado por IA: {producto}")

        # Preparamos el CSV para escritor.py
        with open("keywords_productos.csv", "w", encoding="utf-8") as f:
            f.write("keyword,categoria,asin_amazon\n")
            f.write(f"{producto},{categoria},\n")

        # Llamamos a la fábrica principal
        print(f"⚙️ Ejecutando escritor.py para '{producto}'...")
        os.system("python escritor.py")
        print(f"✅ Artículo generado para '{categoria}'.")

        # Generar Pin de Pinterest de alta conversión (1000x1500)
        print(f"📌 Generando Pin de Pinterest para '{producto}'...")
        os.system("python generador_pinterest.py")
        print(f"📌 Pin de Pinterest completado para '{categoria}'.")

        # Publicación automática en Pinterest (API v5 activa)
        print("🚀 Publicando Pin en Pinterest...")
        os.system("python publicador_pinterest.py")

    except Exception as e:
        print(f"❌ Error al procesar categoría '{categoria}': {e}")

    # Pausa de 10 segundos entre categorías para no saturar APIs ni conexiones
    if idx < total_categorias:
        print("⏳ Pausa de 10 segundos antes de la siguiente categoría...")
        time.sleep(10)

print("\n🚀 ¡Autopiloto completado! Todos los artículos del lote diario han sido procesados.")
