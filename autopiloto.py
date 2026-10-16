import os
import random
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

categoria_elegida = random.choice(categorias)
print(f"🤖 Iniciando autopiloto. Categoría elegida: {categoria_elegida}")

prompt = f"Genera el nombre exacto de un modelo de producto muy vendido en Amazon España de la categoría '{categoria_elegida}'. Debe ser un producto específico (ej: 'Makita DHP482Z' o 'Logitech MX Master 3S'). Responde ÚNICAMENTE con el nombre del producto, sin comillas ni texto adicional."

respuesta = client.chat.completions.create(
    model="gpt-4o-mini",
    messages=[{"role": "user", "content": prompt}],
    temperature=0.9
)

producto = respuesta.choices[0].message.content.strip()
print(f"📦 Producto seleccionado por IA: {producto}")

# Preparamos el CSV con el único producto del día
with open("keywords_productos.csv", "w", encoding="utf-8") as f:
    f.write("keyword,categoria,asin_amazon\n")
    f.write(f"{producto},{categoria_elegida},\n")

# Llamamos a la fábrica principal
print("⚙️ Ejecutando escritor.py...")
os.system("python escritor.py")
print("✅ Artículo generado. Listo para commit.")
