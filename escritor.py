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
import random
import shutil
import argparse
import unicodedata
import urllib.parse
from datetime import datetime
from typing import Dict, Set, List, Optional, Tuple
import requests
import bs4
from PIL import Image, ImageStat
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
# MOTOR VISUAL Y EXTRACTOR DE IMÁGENES OFICIALES DE AMAZON
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

USER_AGENTS_AMAZON = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:130.0) Gecko/20100101 Firefox/130.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_6_1) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36 Edg/129.0.0.0",
]


def obtener_headers_amazon() -> dict:
    """Devuelve cabeceras HTTP de navegador reales para evitar bloqueos y captchas."""
    return {
        "User-Agent": random.choice(USER_AGENTS_AMAZON),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
        "Accept-Encoding": "gzip, deflate, br",
        "DNT": "1",
        "Upgrade-Insecure-Requests": "1",
    }


def obtener_imagen_fallback(categoria: str) -> str:
    """Devuelve la ruta a la imagen local genérica predefinida por categoría."""
    cat_norm = normalizar_para_comparar(categoria).replace("-", " ")
    return MAPA_FALLBACK_IMAGENES.get(cat_norm, MAPA_FALLBACK_IMAGENES.get(categoria.lower(), "/images/fallbacks/consejos-default.jpg"))


def validar_imagen_visual(ruta_imagen: str, min_bytes: int = 5120, min_width: int = 250, min_height: int = 250) -> bool:
    """
    Filtro de Validación Visual con Pillow (PIL):
    - Descarta imágenes con peso menor a 5KB (5120 bytes).
    - Descarta imágenes minúsculas o píxeles de tracking (ej. 1x1 px, < 250x250 px).
    - Descarta imágenes corruptas o fondos planos vacíos (varianza cromática nula en el centro).
    """
    if not ruta_imagen or not os.path.exists(ruta_imagen):
        return False
    try:
        peso = os.path.getsize(ruta_imagen)
        if peso < min_bytes:
            print(f"    [Filtro Visual] Imagen descartada por tamaño insuficiente ({peso} bytes < {min_bytes} bytes): {ruta_imagen}")
            return False

        with Image.open(ruta_imagen) as im:
            im.verify()

        with Image.open(ruta_imagen) as im:
            w, h = im.size
            if w < min_width or h < min_height:
                print(f"    [Filtro Visual] Imagen descartada por dimensiones minúsculas ({w}x{h}px): {ruta_imagen}")
                return False

            # Verificar que el área central no sea un gradiente o color plano vacío
            centro = im.crop((w // 4, h // 4, 3 * w // 4, 3 * h // 4)).convert("RGB")
            stddev = max(ImageStat.Stat(centro).stddev)
            if stddev < 8.0:
                print(f"    [Filtro Visual] Imagen descartada por fondo plano/vacío (stddev={stddev:.2f}): {ruta_imagen}")
                return False

        return True
    except Exception as e:
        print(f"    [Filtro Visual] Imagen corrupta o ilegible ({e}): {ruta_imagen}")
        return False


def descargar_imagen(url: str, ruta_destino: str) -> None:
    """Descarga una imagen y aplica el Filtro de Validación Visual con Pillow (mínimo 5KB y dimensiones reales)."""
    r = requests.get(url, timeout=15, headers={"User-Agent": random.choice(USER_AGENTS_AMAZON)})
    r.raise_for_status()
    if len(r.content) < 5120:
        raise ValueError(f"La imagen descargada pesa menos de 5KB ({len(r.content)} bytes).")
    os.makedirs(os.path.dirname(ruta_destino), exist_ok=True)
    with open(ruta_destino, "wb") as f:
        f.write(r.content)

    if not validar_imagen_visual(ruta_destino):
        try:
            os.remove(ruta_destino)
        except OSError:
            pass
        raise ValueError("La imagen descargada no superó el filtro de validación visual (dimensiones minúsculas o corrupta).")


def limpiar_url_alta_resolucion_amazon(url_img: str) -> str:
    """
    Convierte cualquier miniatura o URL recortada de Amazon a su imagen original en máxima resolución.
    Ejemplo: https://m.media-amazon.com/images/I/71bmqgnZQdL._AC_UL320_.jpg -> https://m.media-amazon.com/images/I/71bmqgnZQdL.jpg
    """
    if not url_img:
        return ""
    # Quitar identificadores de escala tipo ._AC_UL320_., ._SX300_., etc.
    return re.sub(r"\._[A-Z0-9_,]+_\.", ".", url_img.strip())


def extraer_imagen_desde_html_amazon(html: str) -> Optional[str]:
    """Extrae la imagen principal de la página de producto de Amazon (landingImage o og:image)."""
    if not html:
        return None
    try:
        soup = bs4.BeautifulSoup(html, "html.parser")
    except Exception:
        soup = None

    if soup:
        # 1. Imagen principal #landingImage o #imgBlkFront
        landing = soup.find("img", id="landingImage") or soup.find("img", id="imgBlkFront")
        if landing:
            old_hires = landing.get("data-old-hires")
            if old_hires:
                return limpiar_url_alta_resolucion_amazon(old_hires)
            
            dyn = landing.get("data-a-dynamic-image")
            if dyn:
                try:
                    d = json.loads(dyn)
                    if d:
                        mejor_url = sorted(d.items(), key=lambda x: x[1][0] * x[1][1], reverse=True)[0][0]
                        return limpiar_url_alta_resolucion_amazon(mejor_url)
                except Exception:
                    pass

            src = landing.get("src")
            if src:
                return limpiar_url_alta_resolucion_amazon(src)

        # 2. Meta tag og:image
        og = soup.find("meta", property="og:image")
        if og and og.get("content"):
            c = og.get("content").strip()
            if "media-amazon.com/images/I/" in c:
                return limpiar_url_alta_resolucion_amazon(c)

    # 3. Expresiones regulares de seguridad
    m_hires = re.search(r'data-old-hires=["\']([^"\']+)["\']', html)
    if m_hires:
        return limpiar_url_alta_resolucion_amazon(m_hires.group(1))

    m_og = re.search(r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']', html)
    if m_og and "media-amazon.com/images/I/" in m_og.group(1):
        return limpiar_url_alta_resolucion_amazon(m_og.group(1))

    return None


def extraer_imagen_y_asin_amazon(keyword: str, asin: Optional[str] = None) -> Tuple[Optional[str], Optional[str]]:
    """
    Extrae la imagen oficial y el ASIN del producto desde Amazon España:
    1. Si hay un ASIN válido, consulta directamente https://www.amazon.es/dp/{asin}.
    2. Si no hay ASIN o falla, busca en https://www.amazon.es/s?k={keyword} y extrae el producto top 1.
    Retorna (url_imagen_alta_resolucion, asin_detectado).
    """
    asin_candidato = (asin or "").strip()

    # Paso 1: Si hay ASIN directo, intentar página de producto
    if asin_candidato and re.match(r"^[A-Z0-9]{10}$", asin_candidato):
        dp_url = f"https://www.amazon.es/dp/{asin_candidato}"
        try:
            r = requests.get(dp_url, headers=obtener_headers_amazon(), timeout=12)
            if r.status_code == 200:
                img_url = extraer_imagen_desde_html_amazon(r.text)
                if img_url:
                    print(f"    [Amazon Extractor] Foto oficial obtenida desde DP ({asin_candidato}): {img_url}")
                    return img_url, asin_candidato
            elif r.status_code in (503, 429):
                print(f"    [Amazon Extractor] Amazon respondió {r.status_code} (Anti-bot/Captcha) en {dp_url}")
        except Exception as e:
            print(f"    [Amazon Extractor] Error en DP {asin_candidato}: {e}")

    # Paso 2: Búsqueda orgánica en Amazon para obtener el producto principal
    search_url = f"https://www.amazon.es/s?k={urllib.parse.quote_plus(keyword)}"
    try:
        r = requests.get(search_url, headers=obtener_headers_amazon(), timeout=12)
        if r.status_code == 200:
            soup = bs4.BeautifulSoup(r.text, "html.parser")
            tarjetas = soup.select("div[data-asin]")
            for tarjeta in tarjetas:
                card_asin = tarjeta.get("data-asin", "").strip()
                if card_asin and len(card_asin) == 10 and not card_asin.startswith("0"):
                    img_tag = tarjeta.select_one("img.s-image")
                    if img_tag and img_tag.get("src"):
                        src_thumb = img_tag.get("src").strip()
                        if "media-amazon.com/images/I/" in src_thumb:
                            img_hd = limpiar_url_alta_resolucion_amazon(src_thumb)
                            print(f"    [Amazon Extractor] Foto oficial obtenida desde búsqueda (ASIN: {card_asin}): {img_hd}")
                            return img_hd, card_asin

            # Fallback en lista de imágenes de búsqueda
            for img_tag in soup.select("img.s-image"):
                src_thumb = img_tag.get("src", "").strip()
                if "media-amazon.com/images/I/" in src_thumb:
                    img_hd = limpiar_url_alta_resolucion_amazon(src_thumb)
                    print(f"    [Amazon Extractor] Foto obtenida desde búsqueda directa: {img_hd}")
                    return img_hd, asin_candidato or None

        elif r.status_code in (503, 429):
            print(f"    [Amazon Extractor] Amazon respondió {r.status_code} (Anti-bot en búsqueda).")
    except Exception as e:
        print(f"    [Amazon Extractor] Error en búsqueda de Amazon: {e}")

    return None, asin_candidato or None


MAPA_QUERIES_PIXABAY_CATEGORIA = {
    "bricolaje-y-herramientas": ["power drill tool", "cordless drill workshop", "power tools workbench"],
    "bricolaje y herramientas": ["power drill tool", "cordless drill workshop", "power tools workbench"],
    "informatica": ["laptop computer desk", "computer mouse keyboard", "modern workspace laptop"],
    "productos-para-mascotas": ["dog pet bed", "happy dog indoor", "cat dog accessories"],
    "productos para mascotas": ["dog pet bed", "happy dog indoor", "cat dog accessories"],
    "hogar-y-cocina": ["modern kitchen appliance", "coffee maker kitchen", "cooking kitchenware"],
    "hogar y cocina": ["modern kitchen appliance", "coffee maker kitchen", "cooking kitchenware"],
    "deportes-y-aire-libre": ["outdoor camping gear", "fitness sports equipment", "hiking backpack trail"],
    "deportes y aire libre": ["outdoor camping gear", "fitness sports equipment", "hiking backpack trail"],
    "cuidado-personal": ["electric shaver grooming", "personal care bathroom", "beauty grooming device"],
    "cuidado personal": ["electric shaver grooming", "personal care bathroom", "beauty grooming device"],
    "salud-y-cuidado-personal": ["electric shaver grooming", "personal care bathroom", "beauty grooming device"],
}


def obtener_termino_ingles_pixabay(keyword: str, categoria: str) -> str:
    """Usa OpenAI para traducir el tipo de producto a 2 palabras genéricas en inglés (sin marcas ni modelos)."""
    try:
        client = get_openai_client()
        r = client.chat.completions.create(
            model="gpt-4o-mini",
            temperature=0.2,
            timeout=10.0,
            messages=[
                {
                    "role": "user",
                    "content": (
                        f"Convierte el producto '{keyword}' (categoría '{categoria}') en un término genérico de búsqueda "
                        f"fotográfica en inglés de 2 palabras (SOLO el objeto físico sin marcas ni números de modelo, "
                        f"ej: 'cordless drill', 'air fryer', 'wireless mouse', 'dog bed', 'electric shaver', 'camping chair'). "
                        f"Responde únicamente con esas 2 palabras en inglés."
                    ),
                }
            ],
        )
        termino = re.sub(r"[^a-zA-Z\s]", "", r.choices[0].message.content.strip()).strip()
        if len(termino) >= 3:
            return " ".join(termino.split()[:3])
    except Exception:
        pass
    # Limpiar números de modelo como fallback
    limpio = re.sub(r"\b[A-Za-z]*\d+[A-Za-z0-9/-]*\b", "", keyword).strip()
    return re.sub(r"\s+", " ", limpio)[:35]


def buscar_imagen_pixabay(query: str) -> List[dict]:
    """Consulta la API de Pixabay buscando fotografías horizontales de alta resolución."""
    api_key = os.getenv("PIXABAY_API_KEY") or PIXABAY_API_KEY
    if not api_key or not query or not str(query).strip():
        return []
    try:
        url = "https://pixabay.com/api/"
        params = {
            "key": api_key.strip(),
            "q": str(query).strip(),
            "image_type": "photo",
            "orientation": "horizontal",
            "safesearch": "true",
            "per_page": 15,
        }
        r = requests.get(url, params=params, timeout=12)
        if r.status_code == 200:
            hits = r.json().get("hits", [])
            return [h for h in hits if h.get("largeImageURL") or h.get("webformatURL")]
    except Exception as e:
        print(f"    [Aviso Pixabay] Error consultando Pixabay para '{query}': {e}")
    return []


def generar_imagen_fallback_openai(keyword: str, categoria: str, ruta_destino: str) -> Optional[str]:
    """
    Fallback con OpenAI (DALL-E 3): genera una fotografía de estudio fotorrealista del producto
    y la valida dimensionalmente con Pillow.
    """
    try:
        client = get_openai_client()
        prompt_dalle = (
            f"Professional commercial studio product photography of a modern generic {keyword}, "
            f"neutral light grey background, soft studio lighting, sharp focus, 8k resolution, photorealistic, "
            f"NO text, NO visible brands, NO logos, centered composition."
        )
        print(f"    [Fallback DALL-E] Generando imagen de producto con OpenAI para '{keyword}'...")
        response = client.images.generate(
            model="dall-e-3",
            prompt=prompt_dalle,
            size="1024x1024",
            quality="standard",
            n=1,
        )
        if response.data and response.data[0].url:
            descargar_imagen(response.data[0].url, ruta_destino)
            if validar_imagen_visual(ruta_destino):
                print(f"    [Fallback DALL-E OK] Imagen válida guardada en: {ruta_destino}")
                return ruta_destino
    except Exception as e:
        print(f"    [Aviso Fallback DALL-E] No se pudo generar imagen con OpenAI: {e}")
    return None


def generar_imagen_fallback_pollinations(termino_en: str, ruta_destino: str) -> Optional[str]:
    """Fallback generativo adicional libre de API key mediante Pollinations AI validado con Pillow."""
    try:
        prompt_q = urllib.parse.quote(f"professional studio product photo of {termino_en}, commercial lighting, high resolution, realistic")
        url_poll = f"https://image.pollinations.ai/prompt/{prompt_q}?width=1024&height=768&nologo=true&seed={random.randint(1, 99999)}"
        print(f"    [Fallback Pollinations] Solicitando imagen generativa para '{termino_en}'...")
        descargar_imagen(url_poll, ruta_destino)
        if validar_imagen_visual(ruta_destino):
            print(f"    [Fallback Pollinations OK] Imagen válida guardada en: {ruta_destino}")
            return ruta_destino
    except Exception as e:
        print(f"    [Aviso Pollinations] Falló descarga generativa: {e}")
    return None


def resolver_hero_image(
    keyword: str,
    categoria: str,
    slug: str,
    asin_amazon: Optional[str] = None,
    memoria_imagenes: Optional[Set[str]] = None,
) -> Tuple[str, Optional[str]]:
    """
    Pipeline blindado de obtención y validación de imagen (garantiza 0 imágenes vacías o de 1x1px):
    1. Extracción directa desde Amazon España + validación Pillow (>=5KB, >=250x250px, no plana).
    2. Fallback API de Pixabay con término en inglés del producto/categoría + validación Pillow.
    3. Fallback OpenAI DALL-E 3 + validación Pillow.
    4. Fallback Pollinations AI + validación Pillow.
    5. Copia verificada de fotografía real de categoría a 'public/img/{slug}.jpg'.
    """
    os.makedirs(PUBLIC_IMG_DIR, exist_ok=True)
    nombre_archivo = f"{slug}.jpg"
    ruta_disco = os.path.join(PUBLIC_IMG_DIR, nombre_archivo)
    ruta_publica = f"/img/{nombre_archivo}"

    # 1. Extracción directa desde Amazon (Objetivo Principal)
    img_url_amazon, asin_detectado = extraer_imagen_y_asin_amazon(keyword=keyword, asin=asin_amazon)
    if img_url_amazon:
        try:
            descargar_imagen(img_url_amazon, ruta_disco)
            if validar_imagen_visual(ruta_disco):
                if memoria_imagenes is not None:
                    memoria_imagenes.add(img_url_amazon)
                    memoria_imagenes.add(ruta_publica)
                print(f"    [Amazon OK] Imagen oficial validada y guardada con éxito: {ruta_publica}")
                return ruta_publica, asin_detectado
        except Exception as e:
            print(f"    [Aviso Descarga Amazon] Imagen descartada o error ({img_url_amazon}): {e}")

    # 2. Fallback Obligatorio a API de Imágenes (Pixabay) con validación Pillow
    print(f"    [Fallback Pixabay] Buscando fotografía real validada para '{keyword}'...")
    termino_en = obtener_termino_ingles_pixabay(keyword, categoria)
    cat_queries = MAPA_QUERIES_PIXABAY_CATEGORIA.get(categoria.lower(), ["modern product photography", "home technology"])
    candidatas_queries = [q for q in [termino_en] + cat_queries if q]

    for q in candidatas_queries:
        hits = buscar_imagen_pixabay(q)
        for h in hits:
            img_url = h.get("largeImageURL") or h.get("webformatURL")
            if not img_url or (memoria_imagenes is not None and img_url in memoria_imagenes):
                continue
            try:
                descargar_imagen(img_url, ruta_disco)
                if validar_imagen_visual(ruta_disco):
                    if memoria_imagenes is not None:
                        memoria_imagenes.add(img_url)
                        memoria_imagenes.add(ruta_publica)
                    print(f"    [Pixabay OK] Fotografía real validada con Pillow: {ruta_publica} (Query: '{q}')")
                    return ruta_publica, asin_detectado
            except Exception as e:
                print(f"    [Aviso Pixabay] Candidata descartada ({img_url}): {e}")
                continue

    # 3. Fallback OpenAI DALL-E 3 con validación Pillow
    print(f"    [Fallback OpenAI] Intentando generar imagen con DALL-E 3...")
    img_dalle = generar_imagen_fallback_openai(keyword=keyword, categoria=categoria, ruta_destino=ruta_disco)
    if img_dalle and validar_imagen_visual(ruta_disco):
        if memoria_imagenes is not None:
            memoria_imagenes.add(ruta_publica)
        return ruta_publica, asin_detectado

    # 4. Fallback Pollinations AI con validación Pillow
    img_poll = generar_imagen_fallback_pollinations(termino_en=termino_en, ruta_destino=ruta_disco)
    if img_poll and validar_imagen_visual(ruta_disco):
        if memoria_imagenes is not None:
            memoria_imagenes.add(ruta_publica)
        return ruta_publica, asin_detectado

    # 5. Respaldo fotográfico local validado (copiado a public/img/{slug}.jpg)
    fallback_rel = obtener_imagen_fallback(categoria)
    fallback_disco = os.path.join("public", fallback_rel.lstrip("/\\"))
    if os.path.exists(fallback_disco) and validar_imagen_visual(fallback_disco):
        shutil.copyfile(fallback_disco, ruta_disco)
        print(f"    [Fallback Fotográfico Local] Copiada imagen real validada a: {ruta_publica}")
        return ruta_publica, asin_detectado

    raise RuntimeError(f"No se pudo obtener ninguna imagen válida (>5KB y dimensiones reales) para '{keyword}'. Se aborta guardado para evitar artículos corruptos.")


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
INTRO:
[Párrafo de introducción y enganche de aproximadamente 50 palabras abordando directamente el dolor, problema o necesidad inmediata del comprador]
PROS_CONS_MDX:
<ProsCons pros={["Ventaja breve 1", "Ventaja breve 2", "Ventaja breve 3"]} cons={["Desventaja breve 1", "Desventaja breve 2"]} />
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
    intro = match_intro.group(1).strip() if match_intro else ""
    analisis = match_analisis.group(1).strip() if match_analisis else ""
    pros_contras = match_pros.group(1).strip() if match_pros else ""
    guia_compra = match_guia.group(1).strip() if match_guia else ""
    veredicto = match_veredicto.group(1).strip() if match_veredicto else ""

    # Extraer o construir componente MDX ProsCons de forma 100% determinista con json.dumps
    raw_pros_cons = match_pros_cons_mdx.group(1).strip() if match_pros_cons_mdx else ""
    if not raw_pros_cons:
        m = re.search(r"(<ProsCons\s+[\s\S]*?/>)", raw_text)
        if m:
            raw_pros_cons = m.group(1).strip()

    pros_list: List[str] = []
    cons_list: List[str] = []

    if raw_pros_cons:
        m_p = re.search(r"pros\s*=\s*\{?\s*\[([\s\S]*?)\]\s*\}?(?=\s+cons|\s*/>)", raw_pros_cons)
        m_c = re.search(r"cons\s*=\s*\{?\s*\[([\s\S]*?)\]\s*\}?(?=\s*/>|\s+pros)", raw_pros_cons)
        if m_p:
            pros_list = [
                s.strip()
                for s in re.findall(r"""['"]([^'"]+)['"]""", m_p.group(1))
                if s.strip()
            ]
        if m_c:
            cons_list = [
                s.strip()
                for s in re.findall(r"""['"]([^'"]+)['"]""", m_c.group(1))
                if s.strip()
            ]

    if (not pros_list or not cons_list) and pros_contras:
        partes = pros_contras.split("### Aspectos")
        ventajas = re.findall(r"-\s*(.+)", partes[0]) if len(partes) > 0 else []
        aspectos = re.findall(r"-\s*(.+)", partes[1]) if len(partes) > 1 else []
        if not pros_list:
            pros_list = [v.strip() for v in ventajas[:3] if v.strip()]
        if not cons_list:
            cons_list = [a.strip() for a in aspectos[:2] if a.strip()]

    if not pros_list:
        pros_list = ["Gran calidad de construcción", "Excelente relación calidad-precio", "Fácil de usar"]
    if not cons_list:
        cons_list = ["Disponibilidad sujeta a stock", "Inversión inicial media"]

    # Limpiar caracteres peligrosos dentro de los ítems y serializar con JSON válido dentro de llaves JSX {...}
    pros_clean = [re.sub(r"[<>\{\}]", "", p).strip() for p in pros_list[:4]]
    cons_clean = [re.sub(r"[<>\{\}]", "", c).strip() for c in cons_list[:3]]
    pros_cons_mdx = f"<ProsCons pros={{{json.dumps(pros_clean, ensure_ascii=False)}}} cons={{{json.dumps(cons_clean, ensure_ascii=False)}}} />"

    # Respaldo si el LLM no separó con etiquetas
    if not intro and not analisis:
        cuerpo_limpio = re.sub(r"^---[\s\S]*?---\s*", "", raw_text)
        cuerpo_limpio = re.sub(r"^TITULO:.*\n+", "", cuerpo_limpio, flags=re.IGNORECASE)
        cuerpo_limpio = re.sub(r"^DESCRIPCI[OÓ]N:.*\n+", "", cuerpo_limpio, flags=re.IGNORECASE | re.MULTILINE)
        cuerpo_limpio = re.sub(r"^#\s+.+\n+", "", cuerpo_limpio, flags=re.MULTILINE)
        cuerpo_limpio = re.sub(r"<ProsCons[\s\S]*?/>\s*", "", cuerpo_limpio)
        analisis = cuerpo_limpio.strip()

    # Filtro Anti-Errores MDX: eliminar etiquetas HTML/JSX extrañas y signos '<', '>', '{', '}' sueltos en el texto
    def sanitizar_bloque_mdx(bloque: str) -> str:
        if not bloque:
            return ""
        # 1. Eliminar cualquier etiqueta <ProsCons ... /> residual
        limpio = re.sub(r"<ProsCons[\s\S]*?/>", "", bloque)
        # 2. Eliminar cualquier etiqueta HTML/JSX (<div...>, </p>, <br>, etc.)
        limpio = re.sub(r"</?[a-zA-Z][^>]*>", "", limpio)
        # 3. Escapar o eliminar signos '<', '>', '{', '}' sueltos que rompen el compilador MDX
        limpio = limpio.replace("{", "(").replace("}", ")")
        limpio = limpio.replace("<", "&lt;").replace(">", "&gt;")
        return limpio.strip()

    intro = sanitizar_bloque_mdx(intro)
    analisis = sanitizar_bloque_mdx(analisis)
    pros_contras = sanitizar_bloque_mdx(pros_contras)
    guia_compra = sanitizar_bloque_mdx(guia_compra)
    veredicto = sanitizar_bloque_mdx(veredicto)
    titulo = re.sub(r'["<>\{\}]', "", titulo).strip()
    descripcion = re.sub(r'["<>\{\}]', "", descripcion).strip()

    # Construir slug y comprobar duplicados
    slug_base = slugify(f"mejor-{keyword}-{anio_actual}" if len(keyword) < 40 else keyword)
    ext_limpia = extension.lstrip(".")
    nombre_archivo = f"{slug_base}.{ext_limpia}"
    ruta_articulo = os.path.join(content_dir, nombre_archivo)

    if os.path.exists(ruta_articulo):
        print(f"    [Aviso Archivo] Ya existe '{nombre_archivo}'. Se actualizará con la nueva reseña.")

    # Resolver imagen destacada (Extractor Oficial de Amazon + Fallback OpenAI)
    hero_image, asin_detectado = resolver_hero_image(
        keyword=keyword,
        categoria=categoria,
        slug=slug_base,
        asin_amazon=asin_amazon,
        memoria_imagenes=memoria_imagenes,
    )

    # Si detectamos el ASIN oficial de Amazon y no venía en el CSV, lo sincronizamos
    if asin_detectado and not asin_amazon:
        asin_amazon = asin_detectado

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