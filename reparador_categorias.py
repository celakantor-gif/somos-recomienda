import os
import re
import glob
import unicodedata
from dotenv import load_dotenv
from openai import OpenAI

# ==============================================================================
# REPARADOR RETROACTIVO DE CATEGORÍAS (CLARAMENTE / SILOS AMAZON)
# Clasifica cada artículo existente según la taxonomía estricta de departamentos
# de Amazon y actualiza su frontmatter en src/content/blog/*.md
# ==============================================================================

load_dotenv()
API_KEY = os.getenv("OPENAI_API_KEY")
if not API_KEY:
    raise SystemExit("ERROR: No se encontró OPENAI_API_KEY en el archivo .env.")

client = OpenAI(api_key=API_KEY)

CATEGORIAS_AMAZON = [
    'Electrónica',
    'Informática',
    'Hogar y Cocina',
    'Deportes y Aire Libre',
    'Productos para Mascotas',
    'Salud y Cuidado Personal',
    'Videojuegos',
    'Bricolaje y Herramientas',
]


def normalizar(texto):
    t = unicodedata.normalize("NFKD", texto.strip().lower())
    return "".join(c for c in t if not unicodedata.combining(c))


MAPA_CATEGORIAS = {normalizar(c): c for c in CATEGORIAS_AMAZON}


def validar_categoria(candidata):
    if not candidata:
        return None
    cand_norm = normalizar(candidata)
    if cand_norm in MAPA_CATEGORIAS:
        return MAPA_CATEGORIAS[cand_norm]
    for norm_key, oficial in MAPA_CATEGORIAS.items():
        if norm_key in cand_norm or cand_norm in norm_key:
            return oficial
    return None


def clasificar_articulo(titulo):
    prompt = f"""
Actúa como un clasificador estricto de e-commerce de Amazon.
Título del artículo: '{titulo}'

Debes clasificar este artículo en EXACTAMENTE UNA de estas categorías oficiales de Amazon:
{', '.join(CATEGORIAS_AMAZON)}

Responde ÚNICAMENTE con el nombre exacto de la categoría seleccionada, sin comillas ni texto adicional.
"""
    try:
        r = client.chat.completions.create(
            model="gpt-3.5-turbo",
            temperature=0,
            max_tokens=25,
            messages=[{"role": "user", "content": prompt.strip()}],
        )
        resp = r.choices[0].message.content.strip().strip('"\'')
        cat = validar_categoria(resp)
        if cat:
            return cat
    except Exception as e:
        print(f"    Error al consultar OpenAI para '{titulo}': {e}")

    # Fallback heurístico básico
    t_norm = normalizar(titulo)
    if any(k in t_norm for k in ["pesca", "pescar", "deporte", "camping", "bici"]):
        return "Deportes y Aire Libre"
    if any(k in t_norm for k in ["monitor", "pc", "portatil", "teclado", "raton"]):
        return "Informática"
    if any(k in t_norm for k in ["dron", "camara", "auricular", "altavoz", "tv", "pantalla"]):
        return "Electrónica"
    if any(k in t_norm for k in ["herramienta", "tijera", "oxido", "podar", "taladro"]):
        return "Bricolaje y Herramientas"
    if any(k in t_norm for k in ["cactus", "lavadora", "cocina", "limpiar", "filtro"]):
        return "Hogar y Cocina"
    return CATEGORIAS_AMAZON[0]


def procesar_articulos():
    archivos = glob.glob(os.path.join("src", "content", "blog", "*.md"))
    if not archivos:
        print("No se encontraron archivos en src/content/blog/")
        return

    print("==================================================================")
    print(f"Iniciando reparación de categorías sobre {len(archivos)} artículos...")
    print(f"Taxonomía permitida: {', '.join(CATEGORIAS_AMAZON)}")
    print("==================================================================")

    actualizados = 0

    for ruta in archivos:
        nombre = os.path.basename(ruta)
        with open(ruta, "r", encoding="utf-8") as f:
            contenido = f.read()

        # Extraer el título del frontmatter
        match_title = re.search(r'title:\s*["\']?([^"\'\n\r]+)["\']?', contenido)
        titulo = match_title.group(1).strip() if match_title else nombre.replace(".md", "").replace("-", " ")

        print(f"-> Analizando: '{titulo}'...")
        nueva_cat = clasificar_articulo(titulo)

        # Actualizar o inyectar category en el frontmatter
        if re.search(r'category:\s*["\']?[^"\'\n\r]+["\']?', contenido):
            nuevo_contenido = re.sub(
                r'(category:\s*)[^\n\r]+',
                f'category: "{nueva_cat}"',
                contenido,
                count=1,
            )
        else:
            # Si no tenía category, insertar después de title
            nuevo_contenido = re.sub(
                r'(title:\s*[^\n\r]+\n)',
                f'\\1category: "{nueva_cat}"\n',
                contenido,
                count=1,
            )

        with open(ruta, "w", encoding="utf-8", newline="\n") as f:
            f.write(nuevo_contenido)

        print(f"   [OK] Asignado a: '{nueva_cat}'")
        actualizados += 1

    print("==================================================================")
    print(f"¡Reparación completada! {actualizados} artículos actualizados con éxito.")
    print("Ahora puedes ejecutar 'npm.cmd run build' para actualizar las rutas.")
    print("==================================================================")


if __name__ == "__main__":
    procesar_articulos()
