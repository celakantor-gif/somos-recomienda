import os
import time
from openai import OpenAI
from dotenv import load_dotenv

# Cargamos las variables de entorno locales (por si acaso)
load_dotenv()

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

categorias = [
    "bricolaje-y-herramientas",
    "informatica",
    "productos-para-mascotas",
    "hogar-y-cocina",
    "deportes-y-aire-libre",
    "cuidado-personal"
]

productos_generados = []

print("🚀 Iniciando Generación Masiva (18 Artículos)...")

for categoria in categorias:
    print(f"\n--- 📂 Categoría: {categoria} ---")
    for i in range(3):
        prompt = f"Genera el nombre exacto de un modelo de producto muy vendido en Amazon España de la categoría '{categoria}'. Debe ser un producto específico y real (ej: 'Makita DHP482Z' o 'Secador Dyson Supersonic'). IMPORTANTE: NO repitas ninguno de estos productos: {productos_generados}. Responde ÚNICAMENTE con el nombre del producto, sin comillas ni texto adicional."
        
        try:
            respuesta = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.9
            )
            
            producto = respuesta.choices[0].message.content.strip()
            productos_generados.append(producto)
            
            print(f"📦 [{i+1}/3] Producto seleccionado: {producto} | Escribiendo...")
            
            # Escribimos el CSV para el escritor
            with open("keywords_productos.csv", "w", encoding="utf-8") as f:
                f.write("keyword,categoria,asin_amazon\n")
                f.write(f"{producto},{categoria},\n")
            
            # Llamamos a tu fábrica de artículos
            os.system("python escritor.py")
            
            # Pausa de seguridad para no saturar las APIs de OpenAI y Pixabay
            time.sleep(5)
            
        except Exception as e:
            print(f"❌ Error generando {producto}: {e}")

print("\n✅ ¡Generación masiva completada con éxito!")
