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

def obtener_productos_previos():
    """Recopila palabras clave o productos ya existentes para evitar repeticiones."""
    previos = []
    blog_dir = os.path.join("src", "content", "blog")
    if os.path.exists(blog_dir):
        for fname in os.listdir(blog_dir):
            if fname.endswith((".md", ".mdx")):
                filepath = os.path.join(blog_dir, fname)
                try:
                    with open(filepath, "r", encoding="utf-8") as f:
                        for line in f:
                            if line.startswith("keyword:"):
                                val = line.split(":", 1)[1].strip().strip('"\'')
                                if val:
                                    previos.append(val)
                                break
                except Exception:
                    pass
    return previos

productos_generados = obtener_productos_previos()
total_categorias = len(categorias)

print(f"🤖 Iniciando autopiloto escalado ({total_categorias} categorías diarias)...")

for idx, categoria in enumerate(categorias, start=1):
    print(f"\n--- 📂 [{idx}/{total_categorias}] Categoría: {categoria} ---")

    exclusion_text = ""
    if productos_generados:
        ultimos = productos_generados[-25:]
        exclusion_text = f" IMPORTANTE: NO repitas ninguno de estos productos: {ultimos}."

    prompt = (
        f"Genera el nombre exacto de un modelo de producto muy vendido en Amazon España de la categoría '{categoria}'. "
        f"Debe ser un producto específico y real (ej: 'Makita DHP482Z' o 'Logitech MX Master 3S').{exclusion_text} "
        f"Responde ÚNICAMENTE con el nombre del producto, sin comillas ni texto adicional."
    )

    try:
        respuesta = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.9
        )

        producto = respuesta.choices[0].message.content.strip().strip('"\'')
        productos_generados.append(producto)
        print(f"📦 Producto seleccionado por IA: {producto}")

        # Preparamos el CSV para escritor.py
        with open("keywords_productos.csv", "w", encoding="utf-8") as f:
            f.write("keyword,categoria,asin_amazon\n")
            f.write(f"{producto},{categoria},\n")

        # Llamamos a la fábrica principal
        print(f"⚙️ Ejecutando escritor.py para '{producto}'...")
        os.system("python escritor.py")
        print(f"✅ Artículo generado para '{categoria}'.")

    except Exception as e:
        print(f"❌ Error al procesar categoría '{categoria}': {e}")

    # Pausa de 10 segundos entre categorías para no saturar APIs ni conexiones
    if idx < total_categorias:
        print("⏳ Pausa de 10 segundos antes de la siguiente categoría...")
        time.sleep(10)

print("\n🚀 ¡Autopiloto completado! Todos los artículos del lote diario han sido procesados.")
