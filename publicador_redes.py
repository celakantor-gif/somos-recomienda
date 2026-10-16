"""
Motor Orquestador de Publicación en Redes Sociales - Fases 1 y 2
Módulos:
  - Módulo 1: El Lector (Fetcher de JSON Feed)
  - Módulo 2: La Memoria (State Tracker con SQLite)
  - Módulo 3: El Sastre (Formatter de Copy y Hashtags para X/Twitter)
  - Módulo 4: El Emisor (API Client para Postiz con Bearer Token)

Garantiza sincronización idempotente: los artículos solo se marcan en la base de datos
si el envío a la API de Postiz resulta exitoso (HTTP 200/201).
"""

import os
import re
import sqlite3
import logging
from datetime import datetime
from typing import List, Dict, Any, Optional
import requests
from dotenv import load_dotenv

# Cargar variables de entorno desde .env
load_dotenv()

# ==============================================================================
# CONFIGURACIÓN GENERAL Y LOGGING
# ==============================================================================

# URL del feed JSON generado por Astro
FEED_URL: str = os.getenv("FEED_URL", "http://localhost:4321/feed.json")

# Endpoint de la API de Postiz
POSTIZ_API_URL: str = os.getenv("POSTIZ_API_URL", "http://localhost:5000/api/posts")

# Bearer Token de autenticación para la API de Postiz
POSTIZ_BEARER_TOKEN: str = os.getenv("POSTIZ_BEARER_TOKEN", "")

# Ruta de la base de datos local SQLite para el historial de publicaciones
DB_PATH: str = os.getenv("HISTORY_DB_PATH", "history.db")

# Configuración del logger nativo
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("PublicadorRedes")


# ==============================================================================
# MÓDULO 1: EL LECTOR (FETCHER)
# ==============================================================================

def fetch_feed(url: str = FEED_URL, timeout: int = 15) -> List[Dict[str, Any]]:
    """
    Realiza una petición HTTP GET al endpoint JSON Feed y devuelve la lista de artículos.

    Args:
        url: URL completa del feed JSON (por defecto FEED_URL).
        timeout: Tiempo máximo de espera en segundos para la conexión HTTP.

    Returns:
        Lista de diccionarios con los artículos extraídos, o lista vacía en caso de error.
    """
    logger.info("Consultando feed en: %s", url)
    try:
        response = requests.get(
            url,
            timeout=timeout,
            headers={
                "User-Agent": "Claramente-SocialOrchestrator/1.0",
                "Accept": "application/json",
            },
        )
        response.raise_for_status()

        data = response.json()

        # Validación estructural de formato JSON Feed (v1.1) o lista plana
        if isinstance(data, dict):
            items = data.get("items", [])
            if not isinstance(items, list):
                logger.warning("El campo 'items' en el feed no es una lista válida.")
                return []
            logger.info("Feed obtenido exitosamente. %d artículos detectados.", len(items))
            return items
        elif isinstance(data, list):
            logger.info("Feed obtenido exitosamente (formato lista). %d artículos detectados.", len(data))
            return data
        else:
            logger.warning("Estructura de JSON desconocida recibida desde %s", url)
            return []

    except requests.exceptions.Timeout:
        logger.warning("Tiempo de espera agotado (timeout de %ds) al conectar con %s", timeout, url)
        return []
    except requests.exceptions.ConnectionError:
        logger.warning("Error de conexión al intentar acceder al feed en %s (¿está encendido el servidor?)", url)
        return []
    except requests.exceptions.HTTPError as err:
        logger.warning("Respuesta HTTP con error desde %s: %s", url, err)
        return []
    except requests.exceptions.RequestException as err:
        logger.warning("Fallo inesperado en la petición HTTP al feed: %s", err)
        return []
    except ValueError as err:
        logger.warning("No se pudo decodificar el contenido JSON del feed: %s", err)
        return []


# ==============================================================================
# MÓDULO 2: LA MEMORIA (STATE TRACKER CON SQLITE)
# ==============================================================================

def init_db(db_path: str = DB_PATH) -> None:
    """
    Inicializa la base de datos SQLite y asegura la existencia de la tabla published_posts.

    Args:
        db_path: Ruta al archivo SQLite (por defecto DB_PATH).
    """
    try:
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS published_posts (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    processed_at TEXT NOT NULL
                )
                """
            )
            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_published_posts_processed_at
                ON published_posts(processed_at)
                """
            )
            conn.commit()
        logger.debug("Base de datos '%s' inicializada y verificada correctamente.", db_path)
    except sqlite3.Error as err:
        logger.error("Error al inicializar la base de datos '%s': %s", db_path, err)
        raise


def is_processed(post_id: str, db_path: str = DB_PATH) -> bool:
    """
    Verifica si un artículo ya ha sido procesado y registrado previamente en la base de datos.

    Args:
        post_id: Identificador único del post (típicamente su URL o ID del feed).
        db_path: Ruta a la base de datos SQLite.

    Returns:
        True si el post ya existe en la base de datos, False si es un post nuevo.
    """
    if not post_id:
        return False

    try:
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT 1 FROM published_posts WHERE id = ? LIMIT 1", (str(post_id),))
            return cursor.fetchone() is not None
    except sqlite3.Error as err:
        logger.error("Error consultando estado del post '%s' en la base de datos: %s", post_id, err)
        return False


def mark_as_processed(post_id: str, title: str, db_path: str = DB_PATH) -> bool:
    """
    Registra un artículo como procesado en la base de datos SQLite con la fecha/hora actual.

    Args:
        post_id: Identificador único del post (URL o ID).
        title: Título legible del post.
        db_path: Ruta a la base de datos SQLite.

    Returns:
        True si se insertó con éxito, False si hubo algún error o ya existía.
    """
    if not post_id:
        logger.warning("Intento de marcar un artículo sin ID válido.")
        return False

    now_iso = datetime.now().isoformat()
    try:
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO published_posts (id, title, processed_at)
                VALUES (?, ?, ?)
                """,
                (str(post_id), str(title or "Sin título"), now_iso),
            )
            conn.commit()
            return True
    except sqlite3.IntegrityError:
        logger.debug("El artículo '%s' ya se encontraba registrado en la base de datos.", post_id)
        return False
    except sqlite3.Error as err:
        logger.error("Error guardando el artículo '%s' en la base de datos: %s", post_id, err)
        return False


# ==============================================================================
# MÓDULO 3: EL SASTRE (FORMATTER DE COPY Y HASHTAGS)
# ==============================================================================

def tag_to_hashtag(tag: str) -> str:
    """
    Convierte una etiqueta o categoría en un hashtag válido estilo PascalCase para X/Twitter.
    Ejemplo: 'Productos para Mascotas' -> '#ProductosParaMascotas'

    Args:
        tag: Cadena de texto de la categoría o tag.

    Returns:
        Hashtag formateado con prefijo '#' o cadena vacía si es inválido.
    """
    if not tag or not isinstance(tag, str):
        return ""

    # Separar por espacios, guiones, barras o puntuación
    words = [w for w in re.split(r"[\s\-_/]+", tag.strip()) if w]
    clean_words = []

    for word in words:
        # Conservar solo caracteres alfanuméricos
        cleaned = re.sub(r"[^\w]", "", word, flags=re.UNICODE)
        if not cleaned:
            continue
        # Si la palabra es un acrónimo corto en mayúsculas (ej: GPS, TV, PC), mantenerla
        if cleaned.isupper() and len(cleaned) <= 4:
            clean_words.append(cleaned)
        else:
            clean_words.append(cleaned.capitalize())

    if not clean_words:
        return ""

    return "#" + "".join(clean_words)


def format_post(article_data: Dict[str, Any]) -> str:
    """
    Formatea el texto de publicación para X/Twitter a partir de los datos de un artículo.

    Estructura generada:
      ¡Nuevo artículo en el blog! 🚀

      {title}

      Lee más aquí: {url}

      {hashtags}

    Args:
        article_data: Diccionario del artículo extraído del feed JSON.

    Returns:
        Texto formateado optimizado para redes sociales.
    """
    title = (article_data.get("title") or "Nuevo artículo disponible").strip()
    url = (article_data.get("url") or article_data.get("id") or "").strip()

    # Extraer tags y categorías evitando duplicados
    raw_tags = article_data.get("tags") or article_data.get("categories") or []
    if isinstance(raw_tags, str):
        raw_tags = [raw_tags]

    # Añadir categoría o keyword explícita si no estuvieran en la lista
    categoria = article_data.get("category")
    if categoria and categoria not in raw_tags:
        raw_tags.append(categoria)

    keyword = article_data.get("keyword")
    if keyword and keyword not in raw_tags:
        raw_tags.append(keyword)

    hashtags_list = []
    seen = set()

    for item in raw_tags:
        ht = tag_to_hashtag(str(item))
        if ht and ht.lower() not in seen:
            seen.add(ht.lower())
            hashtags_list.append(ht)

    # Limitar a máximo 4 hashtags para no saturar el post
    hashtags_str = " ".join(hashtags_list[:4])

    partes = [
        "¡Nuevo artículo en el blog! 🚀",
        title,
        f"Lee más aquí: {url}",
    ]

    if hashtags_str:
        partes.append(hashtags_str)

    return "\n\n".join(partes)


# ==============================================================================
# MÓDULO 4: EL EMISOR (API CLIENT DE POSTIZ)
# ==============================================================================

def send_to_postiz(
    formatted_text: str,
    image_url: Optional[str] = None,
    api_url: str = POSTIZ_API_URL,
    token: str = POSTIZ_BEARER_TOKEN,
    timeout: int = 15,
) -> bool:
    """
    Construye el payload y realiza la petición HTTP POST a la API de Postiz.

    Args:
        formatted_text: Texto redactado por el formateador.
        image_url: URL absoluta de la imagen multimedia (opcional).
        api_url: Endpoint de la API de Postiz (por defecto POSTIZ_API_URL).
        token: Bearer Token de autorización (por defecto POSTIZ_BEARER_TOKEN).
        timeout: Tiempo máximo de espera en segundos para la petición.

    Returns:
        True si la API responde con código de éxito (HTTP 200 o 201), False en caso contrario.
    """
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

    if token:
        headers["Authorization"] = f"Bearer {token}"
    else:
        logger.warning("POSTIZ_BEARER_TOKEN no está configurado. La petición se enviará sin cabecera de autenticación.")

    # Payload estándar de Postiz para publicación
    payload: Dict[str, Any] = {
        "content": formatted_text,
        "media_urls": [image_url] if image_url else [],
    }

    logger.info("Enviando publicación a Postiz (%s)...", api_url)
    try:
        response = requests.post(
            api_url,
            json=payload,
            headers=headers,
            timeout=timeout,
        )

        if response.status_code in (200, 201):
            logger.info("Publicación enviada exitosamente a Postiz (HTTP %d).", response.status_code)
            return True
        else:
            logger.warning(
                "Fallo en la API de Postiz (HTTP %d). Respuesta del servidor: %s",
                response.status_code,
                response.text[:300] if response.text else "Sin cuerpo de respuesta",
            )
            return False

    except requests.exceptions.Timeout:
        logger.warning("Tiempo de espera agotado (%ds) al conectar con la API de Postiz en %s", timeout, api_url)
        return False
    except requests.exceptions.ConnectionError:
        logger.warning("Error de conexión al conectar con Postiz en %s (¿está encendido el servicio local/remoto?)", api_url)
        return False
    except requests.exceptions.RequestException as err:
        logger.warning("Excepción de red al enviar el post a Postiz: %s", err)
        return False


# ==============================================================================
# BUCLE DE EJECUCIÓN PRINCIPAL
# ==============================================================================

def procesar_feed(
    feed_url: str = FEED_URL,
    postiz_url: str = POSTIZ_API_URL,
    db_path: str = DB_PATH,
) -> Dict[str, int]:
    """
    Ejecuta el ciclo completo de sindicación:
      1. Lee el feed JSON.
      2. Filtra artículos no procesados con SQLite.
      3. Formatea el texto y hashtags para redes.
      4. Emite a la API de Postiz.
      5. Solo si el envío tiene éxito (HTTP 200/201), marca como procesado en SQLite.

    Args:
        feed_url: URL del feed JSON de Astro.
        postiz_url: Endpoint de la API de Postiz.
        db_path: Ruta al archivo SQLite.

    Returns:
        Diccionario con métricas del ciclo (total, nuevos, ignorados, fallidos).
    """
    logger.info("=== Iniciando ciclo de automatización de redes sociales ===")
    init_db(db_path)

    items = fetch_feed(feed_url)
    total_items = len(items)
    nuevos_contador = 0
    ignorados_contador = 0
    fallidos_contador = 0

    if not items:
        logger.info("No hay artículos disponibles para procesar en este ciclo.")
        return {"total": 0, "nuevos": 0, "ignorados": 0, "fallidos": 0}

    for item in items:
        post_id: Optional[str] = item.get("id") or item.get("url")
        title: str = item.get("title", "Sin título")

        if not post_id:
            logger.warning("Artículo omitido por carecer de 'id' y 'url': %s", title)
            continue

        if is_processed(post_id, db_path):
            logger.debug("Artículo ya procesado: %s", title)
            ignorados_contador += 1
        else:
            logger.info("¡NUEVO ARTÍCULO DETECTADO!: %s", title)

            # Módulo 3: El Sastre (Formatear texto y hashtags)
            formatted_text = format_post(item)
            image_url = item.get("image") or item.get("heroImage")

            logger.debug("Texto formateado:\n%s", formatted_text)
            if image_url:
                logger.debug("Imagen adjunta: %s", image_url)

            # Módulo 4: El Emisor (Enviar a Postiz)
            enviado = send_to_postiz(
                formatted_text=formatted_text,
                image_url=image_url,
                api_url=postiz_url,
            )

            # Regla estricta: Solo registrar en DB si Postiz confirmó con 200/201
            if enviado:
                if mark_as_processed(post_id, title, db_path):
                    logger.info("Artículo registrado exitosamente en historial: %s", title)
                    nuevos_contador += 1
            else:
                logger.warning(
                    "Envío a Postiz fallido para '%s'. NO se marcará como procesado para reintentar en el próximo ciclo.",
                    title,
                )
                fallidos_contador += 1

    logger.info(
        "=== Ciclo finalizado: %d total | %d publicados y registrados | %d ya registrados | %d fallidos ===",
        total_items,
        nuevos_contador,
        ignorados_contador,
        fallidos_contador,
    )

    return {
        "total": total_items,
        "nuevos": nuevos_contador,
        "ignorados": ignorados_contador,
        "fallidos": fallidos_contador,
    }


if __name__ == "__main__":
    procesar_feed()
