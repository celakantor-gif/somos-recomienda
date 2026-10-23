"""
==============================================================================
SOMOS RECOMIENDA | MOTOR DE PUBLICACIÓN AUTOMÁTICA EN PINTEREST (API v5)
==============================================================================
Publica pines automáticamente utilizando la API oficial de Pinterest:
- Endpoint: POST https://api.pinterest.com/v5/pins
- Propiedad: media_source de tipo 'image_url' apuntando a la URL pública en Vercel
- Enlace destino: URL oficial de la reseña en el blog
==============================================================================
"""

import os
import re
import csv
import sys
import json
import base64
import argparse
import unicodedata
from datetime import datetime
from typing import Optional, Dict
import requests
from PIL import Image, ImageStat

# Forzar UTF-8 en consolas Windows
try:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

# Cargar variables locales desde .env si existe
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

def _limpiar_secreto(valor: Optional[str]) -> str:
    """Elimina espacios en blanco, saltos de línea, comillas accidentales y prefijo 'Bearer '."""
    if not valor:
        return ""
    limpio = str(valor).strip().strip('"\'').strip()
    if limpio.lower().startswith("bearer "):
        limpio = limpio[7:].strip().strip('"\'').strip()
    return "".join(limpio.split())


SITE_URL = (os.getenv("PUBLIC_SITE_URL") or "https://somos-recomienda.vercel.app").strip().rstrip("/")
PINTEREST_API_BASE = "https://api-sandbox.pinterest.com/v5"
PINTEREST_TOKEN = _limpiar_secreto(os.getenv("PINTEREST_ACCESS_TOKEN"))
PINTEREST_BOARD_ID = _limpiar_secreto(os.getenv("PINTEREST_BOARD_ID"))


def normalizar_para_comparar(texto: str) -> str:
    """Normaliza texto eliminando acentos y caracteres especiales."""
    if not texto:
        return ""
    t = unicodedata.normalize("NFKD", str(texto).strip().lower())
    return "".join(c for c in t if not unicodedata.combining(c))


def slugify(texto: str) -> str:
    """Genera un slug limpio y seguro para URLs."""
    t = normalizar_para_comparar(texto)
    t = re.sub(r"[^a-z0-9]+", "-", t).strip("-")
    return t[:80] or "producto-amazon"


def obtener_datos_ultimo_articulo(csv_path: str = "keywords_productos.csv") -> Dict[str, str]:
    """
    Obtiene los metadatos necesarios del último producto generado para crear el Pin.
    Lee del CSV actual o busca en la colección de artículos del blog.
    """
    keyword = ""
    categoria = "General"

    if os.path.exists(csv_path):
        try:
            with open(csv_path, "r", encoding="utf-8-sig") as f:
                filas = [r for r in csv.DictReader(f) if r and r.get("keyword")]
                if filas:
                    ultima = filas[-1]
                    keyword = ultima.get("keyword", "").strip()
                    categoria = ultima.get("categoria", "").strip() or "General"
        except Exception as e:
            print(f"[Aviso] No se pudo leer '{csv_path}': {e}")

    # Fallback al archivo más reciente en src/content/blog/
    if not keyword:
        blog_dir = os.path.join("src", "content", "blog")
        if os.path.exists(blog_dir):
            archivos = [
                os.path.join(blog_dir, f)
                for f in os.listdir(blog_dir)
                if f.endswith((".md", ".mdx")) and not f.startswith(".")
            ]
            if archivos:
                archivos.sort(key=os.path.getmtime, reverse=True)
                ultimo_archivo = archivos[0]
                try:
                    with open(ultimo_archivo, "r", encoding="utf-8") as fp:
                        for line in fp:
                            if line.startswith("keyword:"):
                                keyword = line.split(":", 1)[1].strip().strip('"\'')
                            elif line.startswith("category:"):
                                categoria = line.split(":", 1)[1].strip().strip('"\'')
                except Exception:
                    pass

    anio_actual = datetime.now().year
    slug_articulo = slugify(f"mejor-{keyword}-{anio_actual}" if len(keyword) < 40 else keyword)
    slug_pin = slugify(keyword)

    # Identificar el nombre del archivo del Pin generado
    pin_filename = f"pin_{slug_pin}.jpg"
    pin_local_path = os.path.join("public", "social", "pinterest", pin_filename)
    if not os.path.exists(pin_local_path):
        pin_filename_alt = f"pin_{slug_articulo}.jpg"
        alt_local = os.path.join("public", "social", "pinterest", pin_filename_alt)
        if os.path.exists(alt_local):
            pin_filename = pin_filename_alt
            pin_local_path = alt_local

    url_articulo = f"{SITE_URL}/blog/{slug_articulo}/"
    url_imagen_pin = f"{SITE_URL}/social/pinterest/{pin_filename}"

    titulo_pin = f"¿Merece la pena el {keyword}? Opiniones y Análisis {anio_actual}"
    if len(titulo_pin) > 100:
        titulo_pin = f"Análisis y Opiniones: {keyword}"[:100]

    descripcion_pin = (
        f"¿Estás pensando en comprar el {keyword}? Consulta nuestro análisis a fondo, "
        f"pros, contras y dónde conseguir el mejor precio garantizado en Amazon España. "
        f"Guía de compra independiente actualizada a {anio_actual}."
    )[:800]

    return {
        "keyword": keyword,
        "categoria": categoria,
        "slug": slug_articulo,
        "url_articulo": url_articulo,
        "pin_filename": pin_filename,
        "pin_local_path": pin_local_path,
        "url_imagen_pin": url_imagen_pin,
        "titulo_pin": titulo_pin,
        "descripcion_pin": descripcion_pin,
    }


def _resolver_board_id_sandbox(auth_token: str, preferred_board_id: str = "") -> str:
    """
    Obtiene o verifica el Board ID en https://api-sandbox.pinterest.com/v5/boards.
    Si en el entorno Sandbox aún no existe ningún tablero, crea uno automáticamente.
    """
    headers = {
        "Authorization": f"Bearer {auth_token}",
        "Content-Type": "application/json",
    }
    url_boards = f"{PINTEREST_API_BASE}/boards"
    try:
        r = requests.get(url_boards, headers=headers, params={"page_size": 25}, timeout=15)
        if r.status_code == 200:
            items = r.json().get("items", [])
            if items:
                ids_disponibles = {str(b.get("id", "")): b.get("name", "Tablero") for b in items}
                if preferred_board_id and preferred_board_id in ids_disponibles:
                    return preferred_board_id
                primer_id = str(items[0].get("id", ""))
                primer_nombre = items[0].get("name", "Tablero")
                print(f"[Pinterest Sandbox Board] Usando tablero de Sandbox: '{primer_nombre}' (ID: {primer_id})")
                return primer_id
            else:
                # Si la cuenta en Sandbox no tiene tableros, creamos uno automáticamente
                print("[Pinterest Sandbox Board] No había tableros en Sandbox. Creando tablero 'Somos Recomienda'...")
                r_create = requests.post(
                    url_boards,
                    headers=headers,
                    json={
                        "name": "Somos Recomienda - Análisis y Ofertas",
                        "description": "Las mejores guías de compra, comparativas y análisis de productos en Amazon España.",
                        "privacy": "PUBLIC",
                    },
                    timeout=15,
                )
                if r_create.status_code in (200, 201):
                    nuevo_id = str(r_create.json().get("id", ""))
                    print(f"[Pinterest Sandbox Board] ¡Tablero creado con éxito en Sandbox! ID: {nuevo_id}")
                    return nuevo_id
    except Exception as e:
        print(f"[Aviso Sandbox Board] Error consultando tableros en Sandbox: {e}")
    return preferred_board_id


def publicar_pin(
    board_id: Optional[str] = None,
    titulo: Optional[str] = None,
    descripcion: Optional[str] = None,
    url_articulo: Optional[str] = None,
    url_imagen_pin: Optional[str] = None,
    pin_local_path: Optional[str] = None,
    token: Optional[str] = None,
) -> dict:
    """
    Publica un nuevo Pin en el tablero especificado mediante la API v5 de Pinterest.
    Soporta carga directa base64 desde archivo local (ideal antes del despliegue en Vercel)
    y fallback automático a image_url y entorno Sandbox (Trial).
    """
    auth_token = _limpiar_secreto(token or os.getenv("PINTEREST_ACCESS_TOKEN") or PINTEREST_TOKEN)
    target_board_id = _limpiar_secreto(board_id or os.getenv("PINTEREST_BOARD_ID") or PINTEREST_BOARD_ID)

    if not auth_token:
        print("\n[ERROR CRÍTICO] Falta la variable PINTEREST_ACCESS_TOKEN en el entorno o archivo .env.")
        print("Configura el token de acceso de Pinterest para continuar.\n")
        return {"error": "missing_token"}

    print(f"[Pinterest Auth] Token cargado correctamente (longitud: {len(auth_token)} caracteres, prefijo: '{auth_token[:8]}...')")

    # Verificar/obtener el tablero válido en el entorno Sandbox (creándolo si no existe)
    target_board_id = _resolver_board_id_sandbox(auth_token, preferred_board_id=target_board_id)

    if not target_board_id:
        print("\n[AVISO PINTEREST] Falta configurar PINTEREST_BOARD_ID o no se pudo obtener automáticamente en Sandbox.")
        print("Para solucionarlo:")
        print("1. Ejecuta 'python obtener_tableros.py'")
        print("2. Copia el 'BOARD ID' del tablero donde desees publicar.")
        print("3. Añade en tu archivo .env y GitHub Secrets: PINTEREST_BOARD_ID=\"tu_board_id_aqui\"\n")
        return {"error": "missing_board_id"}

    # Resolver datos automáticos si faltan parámetros
    datos = obtener_datos_ultimo_articulo()
    titulo = titulo or datos["titulo_pin"]
    descripcion = descripcion or datos["descripcion_pin"]
    url_articulo = url_articulo or datos["url_articulo"]
    url_imagen_pin = url_imagen_pin or datos["url_imagen_pin"]
    pin_local_path = pin_local_path or datos.get("pin_local_path")

    headers = {
        "Authorization": f"Bearer {auth_token}",
        "Content-Type": "application/json",
    }

    # Validar que el Pin local no esté corrupto ni vacío antes de enviarlo a la API
    media_source_url = {
        "source_type": "image_url",
        "url": url_imagen_pin,
    }
    media_source_b64 = None
    if pin_local_path and os.path.exists(pin_local_path):
        try:
            peso = os.path.getsize(pin_local_path)
            if peso < 5120:
                print(f"[ERROR VALIDACIÓN PIN] El archivo local '{pin_local_path}' pesa menos de 5KB ({peso}B). Abortando subida de imagen corrupta.")
                return {"error": "corrupt_pin_size"}
            with Image.open(pin_local_path) as im:
                w, h = im.size
                if w < 500 or h < 500:
                    print(f"[ERROR VALIDACIÓN PIN] Dimensiones inválidas ({w}x{h}px) en '{pin_local_path}'.")
                    return {"error": "corrupt_pin_dimensions"}
                centro = im.crop((100, 620, 900, 880)).convert("RGB")
                if max(ImageStat.Stat(centro).stddev) < 5.0:
                    print(f"[ERROR VALIDACIÓN PIN] El Pin '{pin_local_path}' contiene un fondo plano vacío/corrupto. Se rechaza su publicación.")
                    return {"error": "corrupt_pin_flat_background"}

            with open(pin_local_path, "rb") as img_f:
                b64_data = base64.b64encode(img_f.read()).decode("utf-8")
            media_source_b64 = {
                "source_type": "image_base64",
                "content_type": "image/jpeg",
                "data": b64_data,
            }
        except Exception as val_err:
            print(f"[AVISO VALIDACIÓN PIN] No se pudo procesar '{pin_local_path}' en base64: {val_err}")
            media_source_b64 = None

    payload = {
        "board_id": target_board_id,
        "title": titulo[:100],
        "description": (descripcion or "")[:800],
        "link": url_articulo,
        "media_source": media_source_b64 or media_source_url,
    }

    print("\n" + "=" * 70)
    print("  ENVIANDO PIN A LA API v5 DE PINTEREST")
    print("=" * 70)
    print(f"• Tablero (Board ID): {target_board_id}")
    print(f"• Título: {titulo}")
    print(f"• Enlace del Artículo: {url_articulo}")
    print(f"• Archivo Local Pin: {pin_local_path}")
    print(f"• URL Imagen en Vercel: {url_imagen_pin}")
    print("-" * 70)

    url_api = f"{PINTEREST_API_BASE}/pins"

    try:
        r = requests.post(url_api, json=payload, headers=headers, timeout=25)
        if r.status_code == 400 and media_source_b64 is not None:
            print(f"[Aviso API Pinterest] Reintentando envío mediante image_url en {url_api}...")
            payload_url = dict(payload, media_source=media_source_url)
            r = requests.post(url_api, json=payload_url, headers=headers, timeout=25)

        if r.status_code in (200, 201):
            pin_data = r.json()
            pin_id = pin_data.get("id")
            print(f"\n[ÉXITO] ¡Pin publicado correctamente en Pinterest Sandbox!")
            print(f"• Endpoint: {url_api}")
            print(f"• Pin ID: {pin_id}")
            print(f"• Enlace directo al Pin: https://www.pinterest.com/pin/{pin_id}/")
            print("=" * 70 + "\n")
            return pin_data
        else:
            print(f"\n[ERROR API PINTEREST - HTTP {r.status_code}] Pinterest Sandbox rechazó la publicación ({url_api}):")
            try:
                err_json = r.json()
                print("Response JSON exacto de Pinterest:")
                print(json.dumps(err_json, indent=2, ensure_ascii=False))
                return err_json
            except Exception:
                print(f"Respuesta cruda (No-JSON): {r.text}")
                return {"status_code": r.status_code, "raw_response": r.text}
    except Exception as e:
        print(f"\n[EXCEPCIÓN EN PUBLICADOR PINTEREST] Error inesperado al llamar a {url_api}: {e}")
        return {"error": str(e)}


def main():
    parser = argparse.ArgumentParser(description="Somos Recomienda - Publicador automático de Pines en Pinterest (API v5).")
    parser.add_argument("--board", type=str, default=None, help="Board ID de Pinterest.")
    parser.add_argument("--title", type=str, default=None, help="Título del Pin.")
    parser.add_argument("--description", type=str, default=None, help="Descripción del Pin.")
    parser.add_argument("--link", type=str, default=None, help="URL de destino del artículo.")
    parser.add_argument("--image-url", type=str, default=None, help="URL pública de la imagen en producción.")
    parser.add_argument("--csv", type=str, default="keywords_productos.csv", help="Ruta al CSV con el último producto.")

    args = parser.parse_args()

    datos = obtener_datos_ultimo_articulo(csv_path=args.csv)

    publicar_pin(
        board_id=args.board,
        titulo=args.title or datos.get("titulo_pin"),
        descripcion=args.description or datos.get("descripcion_pin"),
        url_articulo=args.link or datos.get("url_articulo"),
        url_imagen_pin=args.image_url or datos.get("url_imagen_pin"),
        pin_local_path=datos.get("pin_local_path"),
    )


if __name__ == "__main__":
    main()
