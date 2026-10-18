"""
==============================================================================
SOMOS RECOMIENDA | MOTOR MASIVO DE RESEÑAS TRANSACCIONALES (escritor.py)
==============================================================================
Arquitectura de Afiliación Directa y Conversión para Amazon España.
Rol: Senior Python Data Engineer & Lead Backend.

Agente Único:
  - agente_reviewer: Procesa masivamente un archivo CSV local ('keywords_productos.csv')
    con columnas (keyword, categoria, asin_amazon) y redacta reseñas transaccionales
    optimizadas para SEO y conversión (CTR) con botones Above-The-Fold obligatorios.
==============================================================================
"""

import os
import re
import csv
import time
import json
import argparse
import unicodedata
from datetime import datetime
from typing import Dict, Set, List, Optional
import requests
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass
from openai import OpenAI

OPENAI_KEY = os.getenv("OPENAI_API_KEY")
PIXABAY_API_KEY = os.getenv("PIXABAY_API_KEY")
AMAZON_AFFILIATE_TAG = (
    os.getenv("AMAZON_AFFILIATE_TAG")
    or os.getenv("PUBLIC_AMAZON_AFFILIATE_TAG")
    or "TU_NUEVO_TAG_AQUI"
)

CONTENT_DIR = os.path.join("src", "content", "blog")
PUBLIC_IMG_DIR = os.path.join("public", "img")
MEMORIA_IMAGENES_FILE = "memoria_imagenes.json"
CSV_DEFAULT_PATH = "keywords_productos.csv"

_openai_client = None


def get_openai_client() -> OpenAI:
    """Instancia y devuelve el cliente de OpenAI con control de errores y timeout."""
    global _openai_client
    if _openai_client is None:
        key = os.getenv("OPENAI_API_KEY") or OPENAI_KEY
        if not key:
            raise RuntimeError(
                "ERROR CRÍTICO: Falta OPENAI_API_KEY en el entorno o archivo .env. "
                "Por favor, configure la clave de API para continuar."
            )
        _openai_client = OpenAI(api_key=key, timeout=45.0)
    return _openai_client


# ==============================================================================
# UTILIDADES DE NORMALIZACIÓN Y SLUGS
# ==============================================================================

def normalizar_para_comparar(texto: str) -> str:
    """Normaliza texto eliminando tildes, signos diacríticos y pasando a minúsculas."""
    if not texto:
        return ""
    t = unicodedata.normalize("NFKD", str(texto).strip().lower())
    return "".join(c for c in t if not unicodedata.combining(c))


def slugify(texto: str) -> str:
    """Genera un slug URL limpio, seguro y optimizado para SEO."""
    t = normalizar_para_comparar(texto)
    t = re.sub(r"[^a-z0-9]+", "-", t).strip("-")
    return t[:80] or "producto-amazon"


# ==============================================================================
# GESTIÓN DE HISTORIAL E IMÁGENES
# ==============================================================================

def cargar_memoria_imagenes() -> Set[str]:
    """Carga el conjunto de imágenes utilizadas para evitar duplicidades en el sitio."""
    usadas: Set[str] = set()

    if os.path.exists(MEMORIA_IMAGENES_FILE):
        try:
            with open(MEMORIA_IMAGENES_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    for item in data:
                        usadas.add(str(item).strip())
        except Exception:
            pass

    if os.path.exists(PUBLIC_IMG_DIR):
        try:
            for f in os.listdir(PUBLIC_IMG_DIR):
                usadas.add(f)
                usadas.add(f"/img/{f}")
        except Exception:
            pass

    return usadas


def guardar_memoria_imagenes(imagenes: Set[str]) -> None:
    """Persiste el listado de imágenes usadas en memoria_imagenes.json."""
    try:
        with open(MEMORIA_IMAGENES_FILE, "w", encoding="utf-8") as f:
            json.dump(sorted(list(imagenes)), f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"    [Aviso Memoria] Error guardando {MEMORIA_IMAGENES_FILE}: {e}")


# ==============================================================================
# MOTOR VISUAL Y FALLBACK DE IMÁGENES (PIXABAY + FALLBACK LOCAL)
# ==============================================================================

MAPA_FALLBACK_IMAGENES = {
    "hogar y cocina": "/images/fallbacks/hogar-y-cocina-default.jpg",
    "hogar-y-cocina": "/images/fallbacks/hogar-y-cocina-default.jpg",
    "informatica": "/images/fallbacks/informatica-default.jpg",
    "productos para mascotas": "/images/fallbacks/productos-para-mascotas-default.jpg",
    "productos-para-mascotas": "/images/fallbacks/productos-para-mascotas-default.jpg",
    "deportes y aire libre": "/images/fallbacks/deportes-default.jpg",
    "deportes-y-aire-libre": "/images/fallbacks/deportes-default.jpg",
    "bricolaje y herramientas": "/images/fallbacks/bricolaje-y-herramientas-default.jpg",
    "bricolaje-y-herramientas": "/images/fallbacks/bricolaje-y-herramientas-default.jpg",
    "electronica": "/images/fallbacks/electronica-default.jpg",
    "salud y cuidado personal": "/images/fallbacks/salud-default.jpg",
    "salud-y-cuidado-personal": "/images/fallbacks/salud-default.jpg",
    "cuidado personal": "/images/fallbacks/salud-default.jpg",
    "cuidado-personal": "/images/fallbacks/salud-default.jpg",
    "general": "/images/fallbacks/consejos-default.jpg",
}


def obtener_imagen_fallback(categoria: str) -> str:
    """Devuelve la ruta a la imagen local genérica predefinida por categoría."""
    cat_norm = normalizar_para_comparar(categoria).replace("-", " ")
    return MAPA_FALLBACK_IMAGENES.get(cat_norm, MAPA_FALLBACK_IMAGENES.get(categoria.lower(), "/images/fallbacks/consejos-default.jpg"))


def descargar_imagen(url: str, ruta_destino: str) -> None:
    """Descarga una imagen verificando cabeceras y tamaño mínimo seguro."""
    r = requests.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0 (SomosRecomienda/2.0)"})
    r.raise_for_status()
    if not r.headers.get("Content-Type", "").startswith("image/") and len(r.content) < 1024:
        raise ValueError("La respuesta recibida no es una imagen válida.")
    os.makedirs(os.path.dirname(ruta_destino), exist_ok=True)
    with open(ruta_destino, "wb") as f:
        f.write(r.content)


def buscar_imagen_pixabay(query: str) -> List[dict]:
    """Consulta la API de Pixabay buscando fotografías horizontales del producto."""
    if not PIXABAY_API_KEY:
        return []
    if not query or not str(query).strip():
        return []

    try:
        url = "https://pixabay.com/api/"
        params = {
            "key": PIXABAY_API_KEY,
            "q": str(query).strip(),
            "image_type": "photo",
            "orientation": "horizontal",
            "safesearch": "true",
            "per_page": 10,
        }
        r = requests.get(url, params=params, timeout=12)
        if r.status_code == 200:
            hits = r.json().get("hits", [])
            return [h for h in hits if h.get("largeImageURL") or h.get("webformatURL")]
    except Exception as e:
        print(f"    [Aviso Pixabay] No se pudo obtener imagen desde Pixabay: {e}")
    return []


def resolver_hero_image(
    keyword: str,
    termino_imagen_en: str,
    categoria: str,
    slug: str,
    memoria_imagenes: Set[str],
) -> str:
    """
    Resuelve y descarga la imagen destacada para el producto:
    1. Búsqueda en Pixabay con 'termino_imagen_en' limpio (sin números de modelo).
    2. Fallback local predefinido por categoría si Pixabay falla o no devuelve resultados.
    """
    os.makedirs(PUBLIC_IMG_DIR, exist_ok=True)
    
    # Limpiar alfanuméricos de modelo (ej: 's500', '18v', 'hx9911', 'dhp482z') para evitar falsos positivos como coches o camiones
    termino_limpio = re.sub(r'\b[A-Za-z]*\d+[A-Za-z0-9]*\b', '', termino_imagen_en).strip()
    termino_limpio = re.sub(r'\s+', ' ', termino_limpio)
    
    queries = [q for q in [termino_limpio, termino_imagen_en] if q and len(q) >= 3]

    for q in queries:
        hits = buscar_imagen_pixabay(q)
        for h in hits:
            img_url = h.get("largeImageURL") or h.get("webformatURL")
            if not img_url or img_url in memoria_imagenes:
                continue

            nombre_archivo = f"{slug}.jpg"
            ruta_disco = os.path.join(PUBLIC_IMG_DIR, nombre_archivo)
            ruta_publica = f"/img/{nombre_archivo}"

            try:
                descargar_imagen(img_url, ruta_disco)
                memoria_imagenes.add(img_url)
                memoria_imagenes.add(ruta_publica)
                print(f"    [Imagen OK] Descargada desde Pixabay: {ruta_publica} (Query: '{q}')")
                return ruta_publica
            except Exception as e:
                print(f"    [Aviso Imagen] Error descargando {img_url}: {e}")
                continue

    fallback = obtener_imagen_fallback(categoria)
    print(f"    [Imagen Fallback] Asignada imagen local de categoría: {fallback}")
    return fallback


# ==============================================================================
# INGENIERÍA DE PROMPTS Y GENERACIÓN EDITORIAL TRANSACCIONAL
# ==============================================================================

def generar_resena_producto(
    keyword: str,
    categoria: str,
    asin_amazon: str,
    anio_actual: int,
    memoria_imagenes: Set[str],
    content_dir: str = CONTENT_DIR,
    amazon_tag: str = AMAZON_AFFILIATE_TAG,
    extension: str = "mdx",
) -> str:
    """
    Genera un artículo de reseña de producto transaccional de alta conversión para Amazon.
    Estructura MDX / Markdown forzada para maximizar conversión (CRO):
      - Titular (H1): Puramente transaccional (ej: 'Mejor [Keyword] en 2026: Análisis y Opiniones').
      - Intro Corta: Párrafo de enganche de 50 palabras basado en el problema del usuario.
      - Componente MDX ProsCons: Caja Glassmorphism interactiva con pros (✅) y contras (❌).
      - Above the Fold CTA: Botón de conversión directo hacia Amazon.
      - Análisis: Rendimiento, especificaciones y H2 con 'Pros y Contras'.
      - Guía: H2 con 'Guía de Compra' y Veredicto Final.
    """
    client = get_openai_client()

    system_prompt = (
        f"Estamos en el año {anio_actual}. Eres el redactor senior y copywriter de conversión de 'Somos Recomienda', "
        "un portal especializado en reseñas de productos y comparativas de afiliación de Amazon España.\n"
        "Tu misión es redactar reseñas transaccionales exhaustivas, directas y persuasivas en formato MDX, "
        "orientadas a resolver el problema del comprador y maximizar la intención de clic hacia Amazon.\n\n"
        "REGLAS ESTRUCTURALES OBLIGATORIAS:\n"
        f"1. TITULAR (H1): Puramente transaccional. Fórmula: 'Mejor [Keyword] en {anio_actual}: Análisis y Opiniones'.\n"
        "2. INTRODUCCIÓN CORTA: Exactamente un párrafo de unas 50 palabras enfocado en el dolor/necesidad real del usuario y por qué necesita este producto.\n"
        "3. PROS Y CONTRAS MDX: Genera obligatoriamente el componente interactivo <ProsCons pros={[...]} cons={[...]} /> con 3 o 4 ventajas directas y 2 inconvenientes honestos.\n"
        "4. ANÁLISIS: Análisis riguroso explicando especificaciones, calidad, durabilidad y experiencia real de uso.\n"
        "5. PROS Y CONTRAS: Sección detallada con título '## Pros y Contras' en formato de listas con viñetas destacando pros y contras.\n"
        "6. GUÍA DE COMPRA: Sección con título '## Guía de Compra' explicando de forma sintética los 3 o 4 criterios decisivos antes de comprar.\n"
        "7. TONO: Experto, honesto, empático y 100% transaccional."
    )

    user_prompt = f"""Redacta una reseña de producto transaccional para la siguiente palabra clave:
- Keyword: '{keyword}'
- Categoría: '{categoria}'
- ASIN Amazon: '{asin_amazon}'
- Año: {anio_actual}

Responde EXACTAMENTE con la siguiente estructura y etiquetas de campos (sin ningún texto antes ni después):

TITULO: [Titular H1 transaccional de alta conversión, ej: 'Mejor {keyword.title()} en {anio_actual}: Análisis y Opiniones']
DESCRIPCION: [Meta descripción SEO persuasiva para CTR en Google de 140 a 155 caracteres]
TERMINO_IMAGEN: [2 a 3 palabras genéricas en inglés que describan el OBJETO o TIPO DE PRODUCTO para buscar fotografía en Pixabay (ej: 'electric shaver', 'cordless drill', 'running smartwatch', 'coffee maker'). NUNCA incluyas números de modelo, marcas ni códigos como S500, DHP, 18V ya que provocarían imágenes erróneas como coches o camiones.]
INTRO:
[Párrafo de introducción y enganche de aproximadamente 50 palabras abordando directamente el dolor, problema o necesidad inmediata del comprador]
PROS_CONS_MDX:
<ProsCons pros={["[Ventaja breve 1]", "[Ventaja breve 2]", "[Ventaja breve 3]"]} cons={["[Desventaja breve 1]", "[Desventaja breve 2]"]} />
ANALISIS:
[Análisis exhaustivo con subtítulos explicando características clave, materiales, funcionamiento, ergonomía y experiencia de usuario]
PROS_CONTRAS:
## Pros y Contras
### Ventajas Destacadas
- [Punto positivo clave 1]
- [Punto positivo clave 2]
- [Punto positivo clave 3]
### Aspectos a Tener en Cuenta
- [Limitación o punto de mejora 1]
- [Limitación o punto de mejora 2]
GUIA_COMPRA:
## Guía de Compra
[Explicación concisa y práctica de los factores determinantes para acertar con la compra: potencia/calidad, ergonomía, durabilidad y relación calidad-precio]
VEREDICTO:
## Veredicto Final
[Conclusión definitiva sobre para qué tipo de usuario merece la pena comprar este producto y recomendación clara]
"""

    print(f"-> Convocando modelo de IA para generar reseña de '{keyword}'...")
    r = client.chat.completions.create(
        model="gpt-4o-mini",
        temperature=0.7,
        timeout=45.0,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    )
    raw_text = r.choices[0].message.content.strip()

    # Parsear campos de la respuesta del LLM
    match_titulo = re.search(r"TITULO:\s*(.+)", raw_text, re.IGNORECASE)
    match_desc = re.search(r"DESCRIPCION:\s*(.+)", raw_text, re.IGNORECASE)
    match_img_en = re.search(r"TERMINO_IMAGEN:\s*(.+)", raw_text, re.IGNORECASE)
    match_intro = re.search(r"INTRO:\s*([\s\S]*?)(?=PROS_CONS_MDX:|ANALISIS:|$)", raw_text, re.IGNORECASE)
    match_pros_cons_mdx = re.search(r"PROS_CONS_MDX:\s*(<ProsCons[\s\S]*?/>)", raw_text, re.IGNORECASE)
    match_analisis = re.search(r"ANALISIS:\s*([\s\S]*?)(?=PROS_CONTRAS:|$)", raw_text, re.IGNORECASE)
    match_pros = re.search(r"PROS_CONTRAS:\s*([\s\S]*?)(?=GUIA_COMPRA:|$)", raw_text, re.IGNORECASE)
    match_guia = re.search(r"GUIA_COMPRA:\s*([\s\S]*?)(?=VEREDICTO:|$)", raw_text, re.IGNORECASE)
    match_veredicto = re.search(r"VEREDICTO:\s*([\s\S]*)$", raw_text, re.IGNORECASE)

    titulo = (
        match_titulo.group(1).strip().strip("\"'")
        if match_titulo
        else f"Mejor {keyword.title()} en {anio_actual}: Análisis y Opiniones"
    )
    descripcion = (
        match_desc.group(1).strip().strip("\"'")
        if match_desc
        else f"Guía y análisis a fondo del mejor {keyword} en {anio_actual}. Descubre características, pros, contras y el mejor precio en Amazon."
    )
    termino_imagen_en = (
        match_img_en.group(1).strip().strip("\"'[]")
        if match_img_en
        else keyword
    )
    intro = match_intro.group(1).strip() if match_intro else ""
    analisis = match_analisis.group(1).strip() if match_analisis else ""
    pros_contras = match_pros.group(1).strip() if match_pros else ""
    guia_compra = match_guia.group(1).strip() if match_guia else ""
    veredicto = match_veredicto.group(1).strip() if match_veredicto else ""

    # Extraer o construir componente MDX ProsCons
    pros_cons_mdx = match_pros_cons_mdx.group(1).strip() if match_pros_cons_mdx else ""
    if not pros_cons_mdx:
        m = re.search(r"(<ProsCons\s+[\s\S]*?/>)", raw_text)
        if m:
            pros_cons_mdx = m.group(1).strip()
        elif pros_contras:
            # Fallback seguro: extraer puntos de pros_contras
            partes = pros_contras.split("### Aspectos")
            ventajas = re.findall(r"-\s*(.+)", partes[0]) if len(partes) > 0 else []
            aspectos = re.findall(r"-\s*(.+)", partes[1]) if len(partes) > 1 else []
            pros_list = [v.strip().replace('"', '\\"') for v in ventajas[:3]] or ["Excelente rendimiento", "Gran durabilidad", "Fácil de usar"]
            cons_list = [a.strip().replace('"', '\\"') for a in aspectos[:2]] or ["Precio elevado", "Disponibilidad limitada"]
            p_json = json.dumps(pros_list, ensure_ascii=False)
            c_json = json.dumps(cons_list, ensure_ascii=False)
            pros_cons_mdx = f'<ProsCons pros={{{p_json}}} cons={{{c_json}}} />'
        else:
            pros_cons_mdx = '<ProsCons pros={["Gran calidad de construcción", "Excelente relación calidad-precio"]} cons={["Inversión inicial algo elevada"]} />'

    # Respaldo si el LLM no separó con etiquetas
    if not intro and not analisis:
        cuerpo_limpio = re.sub(r"^---[\s\S]*?---\s*", "", raw_text)
        cuerpo_limpio = re.sub(r"^TITULO:.*\n+", "", cuerpo_limpio, flags=re.IGNORECASE)
        cuerpo_limpio = re.sub(r"^DESCRIPCION:.*\n+", "", cuerpo_limpio, flags=re.IGNORECASE)
        analisis = cuerpo_limpio

    # Construir slug y comprobar duplicados
    slug_base = slugify(f"mejor-{keyword}-{anio_actual}" if len(keyword) < 40 else keyword)
    ext_limpia = extension.lstrip(".")
    nombre_archivo = f"{slug_base}.{ext_limpia}"
    ruta_articulo = os.path.join(content_dir, nombre_archivo)

    if os.path.exists(ruta_articulo):
        print(f"    [Aviso Archivo] Ya existe '{nombre_archivo}'. Se actualizará con la nueva reseña.")

    # Resolver imagen destacada
    hero_image = resolver_hero_image(
        keyword=keyword,
        termino_imagen_en=termino_imagen_en,
        categoria=categoria,
        slug=slug_base,
        memoria_imagenes=memoria_imagenes,
    )

    fecha_hoy = datetime.now().strftime("%Y-%m-%d")

    # Ensamblar estructura MDX / Markdown optimizada para conversión (CRO)
    # Nota: El botón CTA de Amazon es renderizado de forma única y centrada por BlogPost.astro al final del artículo
    bloques_markdown = []
    if ext_limpia == "mdx":
        bloques_markdown.append("import ProsCons from '../../components/ProsCons.astro';\n")
    bloques_markdown.append(f"# {titulo}\n")
    bloques_markdown.append(f"![{titulo}]({hero_image})\n")
    if intro:
        bloques_markdown.append(f"{intro}\n")
    if pros_cons_mdx:
        bloques_markdown.append(f"{pros_cons_mdx}\n")
    if analisis:
        bloques_markdown.append(f"{analisis}\n")
    if pros_contras:
        bloques_markdown.append(f"{pros_contras}\n")
    if guia_compra:
        bloques_markdown.append(f"{guia_compra}\n")
    if veredicto:
        bloques_markdown.append(f"{veredicto}\n")

    cuerpo_final = "\n".join(bloques_markdown)

    # Frontmatter compatible con Astro
    documento = f"""---
title: "{titulo}"
description: "{descripcion}"
pubDate: "{fecha_hoy}"
keyword: "{keyword}"
category: "{categoria}"
asin_amazon: "{asin_amazon}"
producto_afiliado: "{keyword}"
texto_boton: "🔥 Ver Mejor Precio y Ofertas en Amazon"
heroImage: "{hero_image}"
---

{cuerpo_final}
"""

    os.makedirs(content_dir, exist_ok=True)
    with open(ruta_articulo, "w", encoding="utf-8") as f:
        f.write(documento)

    return ruta_articulo


# ==============================================================================
# AGENTE ÚNICO: AGENTE_REVIEWER (PROCESADOR MASIVO CSV)
# ==============================================================================

def agente_reviewer(
    csv_path: str = CSV_DEFAULT_PATH,
    content_dir: str = CONTENT_DIR,
    anio_actual: Optional[int] = None,
    amazon_tag: Optional[str] = None,
    limite: Optional[int] = None,
    extension: str = "mdx",
) -> List[str]:
    """
    Agente único de reseñas transaccionales de afiliación para 'Somos Recomienda'.
    
    Flujo:
      1. Lee 'keywords_productos.csv' (columnas obligatorias: keyword, categoria, asin_amazon).
      2. Aplica control de errores exhaustivo (archivo inexistente, vacío o sin ASIN).
      3. Itera fila por fila y genera un artículo Markdown (.md o .mdx) por cada producto válido.
    """
    if anio_actual is None:
        anio_actual = datetime.now().year

    if not amazon_tag:
        amazon_tag = AMAZON_AFFILIATE_TAG

    print("\n" + "=" * 80)
    print("  SOMOS RECOMIENDA | AGENTE REVIEWER (GENERADOR TRANSACCIONAL)")
    print(f"  CSV Origen: '{csv_path}' | Año: {anio_actual} | Tag: '{amazon_tag}'")
    print("=" * 80)

    # --------------------------------------------------------------------------
    # 1. Manejo de Errores: Existencia del archivo CSV
    # --------------------------------------------------------------------------
    try:
        if not os.path.exists(csv_path):
            raise FileNotFoundError(f"El archivo CSV '{csv_path}' no existe en el directorio de trabajo.")
        if not os.path.isfile(csv_path):
            raise ValueError(f"La ruta '{csv_path}' no corresponde a un archivo regular.")
    except (FileNotFoundError, ValueError) as err_existencia:
        print(f"\n[ERROR CRÍTICO] {err_existencia}")
        print("   Por favor, verifica que 'keywords_productos.csv' esté presente en la raíz del proyecto.")
        print("   Columnas esperadas: keyword, categoria, asin_amazon\n")
        return []

    # --------------------------------------------------------------------------
    # 2. Manejo de Errores: Archivo CSV vacío (0 bytes)
    # --------------------------------------------------------------------------
    try:
        if os.path.getsize(csv_path) == 0:
            print(f"\n[AVISO] El archivo CSV '{csv_path}' está completamente vacío (0 bytes).\n")
            return []
    except Exception as err_size:
        print(f"\n[AVISO] No se pudo comprobar el tamaño del CSV '{csv_path}': {err_size}")

    # --------------------------------------------------------------------------
    # 3. Manejo de Errores: Apertura y parseo del archivo CSV
    # --------------------------------------------------------------------------
    rows: List[Dict[str, str]] = []
    try:
        with open(csv_path, mode="r", encoding="utf-8-sig") as f:
            sample = f.read(2048)
            f.seek(0)
            delimiter = ","
            if sample:
                try:
                    dialect = csv.Sniffer().sniff(sample, delimiters=";,|\t")
                    delimiter = dialect.delimiter
                except Exception:
                    delimiter = ","
            reader = csv.DictReader(f, delimiter=delimiter)
            rows = [r for r in reader if r]
    except Exception as err_csv:
        print(f"\n[ERROR CRÍTICO] Error al abrir o parsear el archivo CSV '{csv_path}': {err_csv}\n")
        return []

    if not rows:
        print(f"\n[AVISO] El archivo CSV '{csv_path}' no contiene filas con datos para procesar.\n")
        return []

    print(f"-> Archivo CSV cargado correctamente con {len(rows)} filas.")

    memoria_imagenes = cargar_memoria_imagenes()
    articulos_generados: List[str] = []
    filas_omitidas: int = 0

    # --------------------------------------------------------------------------
    # 4. Bucle principal de iteración por fila (agente_reviewer)
    # --------------------------------------------------------------------------
    for idx, row in enumerate(rows, start=1):
        if limite is not None and len(articulos_generados) >= limite:
            print(f"\n[LÍMITE ALCANZADO] Se ha alcanzado el límite de {limite} artículo(s) generado(s).")
            break

        # Normalizar claves y valores de la fila
        row_norm = {str(k).strip().lower(): str(v).strip() for k, v in row.items() if k is not None}

        keyword = row_norm.get("keyword", "")
        categoria = row_norm.get("categoria") or row_norm.get("category") or "General"
        asin_amazon = row_norm.get("asin_amazon") or row_norm.get("asin", "")

        # Manejo de Errores: Fila sin keyword
        if not keyword:
            print(f"   [FILA {idx} SALTADA] Campo 'keyword' vacío. Fila omitida.")
            filas_omitidas += 1
            continue

        # Manejo de asin_amazon: si falta (ej. autopiloto), avisar y usar búsqueda transaccional
        if not asin_amazon:
            print(f"   [AVISO] Fila {idx} sin 'asin_amazon'. Se generará enlace de búsqueda transaccional para '{keyword}'.")
            asin_amazon = ""

        print(f"\n[{idx}/{len(rows)}] Procesando: '{keyword}' (Categoría: {categoria} | ASIN: {asin_amazon})...")

        try:
            ruta_generada = generar_resena_producto(
                keyword=keyword,
                categoria=categoria,
                asin_amazon=asin_amazon,
                anio_actual=anio_actual,
                memoria_imagenes=memoria_imagenes,
                content_dir=content_dir,
                amazon_tag=amazon_tag,
                extension=extension,
            )
            if ruta_generada:
                articulos_generados.append(ruta_generada)
                print(f"   [ÉXITO] Reseña publicada en: {ruta_generada}")
        except Exception as err_fila:
            print(f"   [ERROR EN FILA {idx}] No se pudo generar la reseña para '{keyword}': {err_fila}")
            filas_omitidas += 1

        # Pausa preventiva entre llamadas a APIs para evitar rate limits
        if idx < len(rows):
            time.sleep(2)

    # Persistir historial de imágenes descargadas
    guardar_memoria_imagenes(memoria_imagenes)

    # --------------------------------------------------------------------------
    # 5. Resumen final de ejecución
    # --------------------------------------------------------------------------
    print("\n" + "=" * 80)
    print("  SOMOS RECOMIENDA | RESUMEN DE EJECUCIÓN AGENTE REVIEWER")
    print(f"  * Total de filas en CSV: {len(rows)}")
    print(f"  * Reseñas generadas con éxito: {len(articulos_generados)}")
    print(f"  * Filas omitidas por validación/error: {filas_omitidas}")
    print("=" * 80 + "\n")

    return articulos_generados


# ==============================================================================
# PUNTO DE ENTRADA CLI
# ==============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Somos Recomienda - Generador masivo de reseñas transaccionales de Amazon basado en CSV."
    )
    parser.add_argument(
        "--csv",
        type=str,
        default=CSV_DEFAULT_PATH,
        help=f"Ruta al archivo CSV con columnas (keyword, categoria, asin_amazon). Por defecto: {CSV_DEFAULT_PATH}",
    )
    parser.add_argument(
        "--anio",
        type=int,
        default=None,
        help="Año de referencia para las reseñas (por defecto: año actual)",
    )
    parser.add_argument(
        "--tag",
        type=str,
        default=None,
        help="Tag de afiliado de Amazon (por defecto: variable de entorno AMAZON_AFFILIATE_TAG o 'TU_NUEVO_TAG_AQUI')",
    )
    parser.add_argument(
        "--test",
        action="store_true",
        help="Modo test: procesa únicamente la primera fila válida del CSV.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Límite máximo de artículos a generar.",
    )
    parser.add_argument(
        "--ext",
        type=str,
        default="mdx",
        choices=["md", "mdx"],
        help="Extensión del archivo a generar: 'md' o 'mdx' (por defecto: mdx).",
    )

    args = parser.parse_args()

    limite = 1 if args.test else args.limit

    agente_reviewer(
        csv_path=args.csv,
        anio_actual=args.anio,
        amazon_tag=args.tag,
        limite=limite,
        extension=args.ext,
    )


if __name__ == "__main__":
    main()