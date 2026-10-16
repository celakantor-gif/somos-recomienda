import os
import re
import html
import unicodedata
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime
import requests
from dotenv import load_dotenv
from openai import OpenAI

# ==============================================================================
# MOTOR DE ACTUALIDAD 'CLARAMENTE' (noticiero.py)
# Automatización de Noticias Diarias de España con Reescritura Periodística
# - Blindado con timeout=15 en todas las conexiones y llamadas de red.
# ==============================================================================

load_dotenv()
OPENAI_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_KEY:
    raise SystemExit("ERROR: Falta OPENAI_API_KEY en el archivo .env. Añádela para ejecutar el noticiero.")

PIXABAY_KEY = os.getenv("PIXABAY_API_KEY")
client = OpenAI(api_key=OPENAI_KEY, timeout=15.0)

# Feeds RSS de actualidad general en España (con redundancia)
FEEDS_ESPANA = [
    ("El País Portada", "https://feeds.elpais.com/mrss-s/pages/ep/site/elpais.com/portada"),
    ("20 Minutos Portada", "https://www.20minutos.es/rss/"),
    ("Xataka Actualidad", "https://feeds.weblogssl.com/xataka2"),
]


def limpiar_texto_html(raw_html: str) -> str:
    """Elimina etiquetas HTML, saltos residuales y decodifica entidades XML/HTML."""
    if not raw_html:
        return ""
    texto = re.sub(r"<[^>]+>", " ", raw_html)
    texto = html.unescape(texto)
    texto = re.sub(r"\s+", " ", texto).strip()
    return texto


def obtener_primera_noticia():
    """Lee el feed RSS de referencia con timeout=15s y extrae la noticia más reciente."""
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) ClaramenteBot/1.0"}

    for nombre_medio, url_rss in FEEDS_ESPANA:
        print(f"-> Conectando con feed RSS: {nombre_medio} ({url_rss[:45]}...)...")
        try:
            req = urllib.request.Request(url_rss, headers=headers)
            with urllib.request.urlopen(req, timeout=15) as response:
                arbol = ET.fromstring(response.read())
                canal = arbol.find("channel")
                if canal is None:
                    continue

                item = canal.find("item")
                if item is None:
                    continue

                titulo_raw = item.findtext("title", "")
                desc_raw = item.findtext("description", "")
                enlace = item.findtext("link", "")

                titulo = limpiar_texto_html(titulo_raw)
                desc = limpiar_texto_html(desc_raw)

                if titulo and len(titulo) > 10:
                    print(f"   [OK] Noticia capturada de {nombre_medio}: '{titulo[:65]}...'")
                    return titulo, desc, enlace, nombre_medio
        except Exception as e:
            print(f"   [AVISO] No se pudo leer {nombre_medio} (timeout/error): {e}. Probando siguiente feed...")

    raise RuntimeError("No se pudo obtener ninguna noticia válida de los feeds RSS configurados.")


def reescribir_noticia_con_openai(titulo_original: str, desc_original: str):
    """Envía la noticia a OpenAI con timeout=15s y rol periodístico objetivo sin venta."""
    prompt_sistema = (
        "Eres un periodista de 'Claramente', un medio digital premium. "
        "Tu objetivo es reescribir esta noticia de forma objetiva, directa y sin paja, con un tono profesional. "
        "El texto debe tener unos 300-400 palabras. "
        "Tienes PROHIBIDO inventar datos y PROHIBIDO incluir intenciones de venta o enlaces."
    )

    prompt_usuario = f"""
Noticia original de última hora:
- Titular: {titulo_original}
- Resumen/Contexto: {desc_original}

Genera un artículo periodístico riguroso y estructurado. 
Responde EXACTAMENTE con la siguiente estructura (conserva las etiquetas en mayúsculas):

TITULO: [Titular periodístico definitivo, claro, atractivo y directo]
DESCRIPCION: [Resumen conciso en una frase de máximo 150 caracteres para SEO]
FOTO_BUSQUEDA: [1 o 2 palabras clave en inglés para buscar una imagen representativa en Pixabay, ej: 'solar energy' o 'city transport']
CUERPO:
[Cuerpo de la noticia en formato Markdown de 300-400 palabras. Usa subtítulos ## (H2) para estructurar los hechos principales, párrafos cortos de lectura ágil, y datos clave o fechas en **negrita**. NO incluyas título # (H1). Sin enlaces ni autopromoción.]
"""

    print("-> Enviando noticia al redactor de Claramente (OpenAI)...")
    modelos_a_probar = ["gpt-4o-mini", "gpt-3.5-turbo"]
    respuesta = None

    for mod in modelos_a_probar:
        try:
            r = client.chat.completions.create(
                model=mod,
                temperature=0.3,
                timeout=15.0,
                messages=[
                    {"role": "system", "content": prompt_sistema},
                    {"role": "user", "content": prompt_usuario},
                ],
            )
            respuesta = r.choices[0].message.content
            print(f"   [OK] Noticia reescrita con éxito usando {mod}.")
            break
        except Exception as err:
            print(f"   [Aviso] Intento con {mod} falló o timeout de 15s ({err}). Probando alternativa...")

    if not respuesta:
        raise RuntimeError("OpenAI no pudo generar la noticia a tiempo.")

    match_tit = re.search(r"TITULO:\s*(.+)", respuesta, re.IGNORECASE)
    match_desc = re.search(r"DESCRIPCION:\s*(.+)", respuesta, re.IGNORECASE)
    match_foto = re.search(r"FOTO_BUSQUEDA:\s*(.+)", respuesta, re.IGNORECASE)
    match_cuerpo = re.search(r"CUERPO:\s*([\s\S]+)", respuesta, re.IGNORECASE)

    titulo_final = match_tit.group(1).strip().strip('"\'') if match_tit else titulo_original
    desc_final = match_desc.group(1).strip().strip('"\'') if match_desc else desc_original[:140]
    termino_foto = match_foto.group(1).strip().strip('"\'') if match_foto else "news report"
    cuerpo_final = match_cuerpo.group(1).strip() if match_cuerpo else respuesta

    cuerpo_final = re.sub(r"^\s*#\s+[^\n]+\n+", "", cuerpo_final)
    cuerpo_final = re.sub(r"^```markdown\s*", "", cuerpo_final, flags=re.IGNORECASE)
    cuerpo_final = re.sub(r"^```\s*", "", cuerpo_final)
    cuerpo_final = re.sub(r"\s*```$", "", cuerpo_final)

    return titulo_final, desc_final, termino_foto, cuerpo_final


def generar_slug(texto: str) -> str:
    """Convierte cualquier texto a slug ASCII seguro para URLs y nombres de archivo."""
    s = unicodedata.normalize("NFKD", texto.strip().lower())
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s[:70].rstrip("-")


def descargar_foto(url_origen: str, ruta_disco: str):
    """Descarga físicamente una imagen con timeout estricto de 15s."""
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Claramente/1.0"}
    res = requests.get(url_origen, headers=headers, timeout=15)
    res.raise_for_status()
    if len(res.content) < 1000:
        raise ValueError("Archivo de imagen descargado demasiado pequeño o inválido.")
    with open(ruta_disco, "wb") as f:
        f.write(res.content)


def obtener_imagen_noticia(termino_busqueda: str, slug: str) -> str:
    """Obtiene y descarga una imagen de Pixabay (o Pollinations) con timeout de 15s."""
    os.makedirs(os.path.join("public", "img"), exist_ok=True)
    nombre_archivo = f"{slug}-1.jpg"
    ruta_disco = os.path.join("public", "img", nombre_archivo)
    ruta_web = f"/img/{nombre_archivo}"

    termino_limpio = re.sub(r"[^a-zA-Z0-9\s]", "", termino_busqueda).strip()
    termino_limpio = " ".join(termino_limpio.split()[:2]) or "spain news"

    print(f"-> Buscando imagen libre de derechos para: '{termino_limpio}'...")

    if PIXABAY_KEY:
        try:
            res = requests.get(
                "https://pixabay.com/api/",
                params={
                    "key": PIXABAY_KEY,
                    "q": termino_limpio,
                    "lang": "en",
                    "image_type": "photo",
                    "orientation": "horizontal",
                    "safesearch": "true",
                    "per_page": 10,
                },
                timeout=15,
            )
            if res.status_code == 200:
                hits = [h for h in res.json().get("hits", []) if h.get("largeImageURL")]
                if hits:
                    foto_url = hits[0]["largeImageURL"]
                    descargar_foto(foto_url, ruta_disco)
                    print(f"   [OK] Imagen descargada de Pixabay guardada en: {ruta_web}")
                    return ruta_web
        except Exception as e:
            print(f"   [Aviso] Consulta o descarga de Pixabay falló (timeout/error): {e}")

    url_respaldo = f"https://image.pollinations.ai/prompt/{slug}-news-photography-editorial-aspect-ratio-16:9"
    try:
        print("   [INFO] Descargando imagen de respaldo editorial...")
        descargar_foto(url_respaldo, ruta_disco)
        return ruta_web
    except Exception as err_respaldo:
        print(f"   [Aviso] No se pudo guardar la foto de respaldo local ({err_respaldo}). Usando enlace directo.")
        return url_respaldo


def publicar_noticia():
    """Flujo principal: Extrae RSS -> Reescribe con OpenAI -> Descarga Foto -> Guarda Markdown en Astro."""
    print("=" * 65)
    print("  CLARAMENTE | NOTICIERO AUTOMÁTICO DE ACTUALIDAD (ESPAÑA)")
    print("=" * 65)

    titulo_rss, desc_rss, fuente_link, medio = obtener_primera_noticia()
    titulo, descripcion, termino_foto, cuerpo = reescribir_noticia_con_openai(titulo_rss, desc_rss)

    slug = generar_slug(titulo)
    if not slug:
        slug = f"noticia-{datetime.now().strftime('%Y%m%d-%H%M')}"

    ruta_md = os.path.join("src", "content", "blog", f"{slug}.md")

    if os.path.exists(ruta_md):
        print(f"-> AVISO: El artículo '{slug}.md' ya existía. Se actualizará con la última versión.")

    hero_img = obtener_imagen_noticia(termino_foto, slug)

    fecha_hoy = datetime.now().strftime("%Y-%m-%d")
    frontmatter = (
        "---\n"
        f'title: "{titulo}"\n'
        f'description: "{descripcion}"\n'
        f'pubDate: "{fecha_hoy}"\n'
        f'category: "Noticias"\n'
        f'heroImage: "{hero_img}"\n'
        "---\n\n"
    )

    os.makedirs(os.path.dirname(ruta_md), exist_ok=True)
    with open(ruta_md, "w", encoding="utf-8") as f:
        f.write(frontmatter + cuerpo.strip() + "\n")

    print("\n" + "=" * 65)
    print("  ¡NOTICIA PUBLICADA CON ÉXITO EN EL SISTEMA!")
    print(f"  • Titular:   {titulo}")
    print(f"  • Categoría: Noticias")
    print(f"  • Archivo:   {ruta_md}")
    print(f"  • Imagen:    {hero_img}")
    print(f"  • Fuente:    {medio} ({fuente_link})")
    print("=" * 65)
    return ruta_md


if __name__ == "__main__":
    publicar_noticia()
