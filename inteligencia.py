import os
import re
import json
import unicodedata
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, date
from dotenv import load_dotenv
from openai import OpenAI

# ==============================================================================
# MOTOR DE INTELIGENCIA DE MERCADO (inteligencia.py)
# - Memoria Semántica y Cuarentena (7 días) para evitar saturación de temas.
# - Filtro Cultural de España estricto.
# - Diversificación Forzada: 4 categorías distintas garantizadas por día.
# - Resiliencia: Timeout estricto de 15 segundos en todas las llamadas de red.
# ==============================================================================

load_dotenv()
OPENAI_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_KEY:
    raise SystemExit("ERROR: Falta OPENAI_API_KEY en el archivo .env.")

# Cliente OpenAI con timeout de 15 segundos blindado
client = OpenAI(api_key=OPENAI_KEY, timeout=15.0)

CATEGORIAS_VALIDAS = [
    'Electrónica',
    'Informática',
    'Hogar y Cocina',
    'Deportes y Aire Libre',
    'Productos para Mascotas',
    'Salud y Cuidado Personal',
    'Videojuegos',
    'Bricolaje y Herramientas',
]


def normalizar_texto(texto: str) -> str:
    t = unicodedata.normalize("NFKD", texto.strip().lower())
    return "".join(c for c in t if not unicodedata.combining(c))


MAPA_CATEGORIAS = {normalizar_texto(c): c for c in CATEGORIAS_VALIDAS}


def validar_categoria(nombre: str) -> str | None:
    if not nombre:
        return None
    norm = normalizar_texto(nombre)
    if norm in MAPA_CATEGORIAS:
        return MAPA_CATEGORIAS[norm]
    for key, oficial in MAPA_CATEGORIAS.items():
        if key in norm or norm in key:
            return oficial
    return None


# ==============================================================================
# GESTIÓN DE CUARENTENA Y MEMORIA SEMÁNTICA (cuarentena_temas.json)
# ==============================================================================
ARCHIVO_CUARENTENA = "cuarentena_temas.json"


def leer_cuarentena(ruta: str = ARCHIVO_CUARENTENA) -> tuple[list[dict], list[str]]:
    """
    Lee cuarentena_temas.json (si no existe, lo crea con []).
    Devuelve:
      - todos_los_registros: lista de diccionarios con formato {"tema_base": "...", "fecha": "YYYY-MM-DD"}
      - temas_prohibidos: lista de 'tema_base' cuya fecha sea inferior a 7 días respecto al día actual.
    """
    if not os.path.exists(ruta):
        try:
            with open(ruta, "w", encoding="utf-8") as f:
                json.dump([], f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"   [Aviso] No se pudo inicializar {ruta}: {e}")
        return [], []

    try:
        with open(ruta, "r", encoding="utf-8") as f:
            datos = json.load(f)
            if not isinstance(datos, list):
                datos = []
    except Exception as e:
        print(f"   [Aviso] Error al leer {ruta}: {e}. Se usará lista vacía.")
        return [], []

    hoy = datetime.now().date()
    temas_prohibidos = []
    for item in datos:
        if isinstance(item, dict) and "tema_base" in item and "fecha" in item:
            try:
                fecha_item = datetime.strptime(str(item["fecha"]).strip(), "%Y-%m-%d").date()
                dias = (hoy - fecha_item).days
                # Menos de 7 días respecto al día actual: tema en cuarentena
                if 0 <= dias < 7:
                    tema = str(item["tema_base"]).strip()
                    if tema and tema not in temas_prohibidos:
                        temas_prohibidos.append(tema)
            except Exception:
                continue

    return datos, temas_prohibidos


def guardar_cuarentena(nuevos_temas: list[str], ruta: str = ARCHIVO_CUARENTENA):
    """Añade los temas generados a cuarentena_temas.json con la fecha de hoy."""
    registros, _ = leer_cuarentena(ruta)
    hoy_str = datetime.now().strftime("%Y-%m-%d")

    for tema in nuevos_temas:
        t = str(tema).strip()
        if t:
            registros.append({"tema_base": t, "fecha": hoy_str})

    try:
        with open(ruta, "w", encoding="utf-8") as f:
            json.dump(registros, f, indent=2, ensure_ascii=False)
        print(f"   [Memoria Semántica] {len(nuevos_temas)} temas registrados en {ruta} con fecha {hoy_str}.")
    except Exception as e:
        print(f"   [Aviso] Error al escribir {ruta}: {e}")


def extraer_tema_base(keyword: str) -> str:
    """Extrae el concepto o producto base de la palabra clave."""
    k = keyword.lower().strip()
    k = re.sub(r"^(mejores|comprar|guia de|ofertas en|ofertas de|comparativa de|analisis de)\s+", "", k)
    k = re.sub(r"\s+(calidad precio|baratas|baratos|barata|barato|online|economicos|economicas|profesionales|profesional|2024|2025|2026)$", "", k)
    return k.strip()


TRENDS_URLS = [
    "https://trends.google.com/trending/rss?geo=ES",
    "https://trends.google.com/trends/trendingsearches/daily/rss?geo=ES",
    "https://trends.google.es/trending/rss?geo=ES",
]


def extraer_tendencias_google(max_tendencias: int = 15) -> list[str]:
    """Descarga el feed de Google Trends España con timeout de 15s y redundancia."""
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) ClaramenteTrends/1.0"}
    tendencias = []

    for url in TRENDS_URLS:
        print(f"-> Conectando con Google Trends España ({url[:45]}...)...")
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=15) as response:
                arbol = ET.fromstring(response.read())
                items = arbol.findall("channel/item")
                for it in items:
                    titulo = it.findtext("title", "").strip()
                    if titulo and titulo not in tendencias:
                        tendencias.append(titulo)
                    if len(tendencias) >= max_tendencias:
                        break

                if tendencias:
                    print(f"   [OK] {len(tendencias)} tendencias extraídas con éxito.")
                    return tendencias
        except Exception as e:
            print(f"   [Aviso] Fallo al consultar {url}: {e}. Probando endpoint alternativo...")

    print("   [Aviso] Usando temas de interés comercial como respaldo.")
    return [
        "tecnologia hogar",
        "deporte y fitness",
        "gaming y monitores",
        "mascotas y gatos",
        "bricolaje herramientas",
    ]


def generar_keywords_afiliacion(tendencias: list[str]) -> list[dict]:
    """Envía las tendencias a OpenAI exigiendo filtro cultural de España, cuarentena y rotación de categorías."""
    _, temas_prohibidos = leer_cuarentena()
    lista_temas_prohibidos = ", ".join(f"'{t}'" for t in temas_prohibidos) if temas_prohibidos else "ninguno por ahora"

    prompt_sistema = (
        "Eres un experto SEO de afiliación enfocado ÚNICA y EXCLUSIVAMENTE en el mercado de ESPAÑA. "
        "Ignora tendencias de otros países (ej. Inter de Miami) y céntrate en intereses españoles. "
        f"REGLA DE CUARENTENA: Tienes estrictamente prohibido generar palabras clave relacionadas con esta lista de temas: [{lista_temas_prohibidos}]. "
        "Genera temáticas completamente nuevas.\n"
        "Analiza estas tendencias de búsqueda y genera exactamente 4 ideas de artículos transaccionales de Amazon altamente rentables.\n"
        "REGLA ESTRICTA: Cada palabra clave DEBE pertenecer a una macro-categoría distinta de nuestra web "
        "(ej. 1 de Electrónica, 1 de Deportes, 1 de Mascotas, 1 de Hogar).\n"
        "Devuelve ÚNICAMENTE un array JSON de objetos, donde cada objeto tenga las claves 'keyword', 'categoria' y 'tema_base'."
    )

    lista_tendencias_str = ", ".join(tendencias)
    prompt_usuario = f"""
Tendencias de búsqueda destacadas hoy en España:
{lista_tendencias_str}

Macro-categorías permitidas en nuestra web (elige 4 DIFERENTES de esta lista):
{CATEGORIAS_VALIDAS}

Temas actualmente en cuarentena (PROHIBIDOS por haberse tratado en los últimos 7 días):
[{lista_temas_prohibidos}]

Devuelve ÚNICAMENTE el array JSON con exactamente 4 objetos y 4 categorías distintas, por ejemplo:
[
  {{"keyword": "mejores freidoras de aire calidad precio", "categoria": "Hogar y Cocina", "tema_base": "freidoras de aire"}},
  {{"keyword": "comprar zapatillas running hombre baratas", "categoria": "Deportes y Aire Libre", "tema_base": "zapatillas running"}},
  {{"keyword": "mejores comederos automaticos para gatos", "categoria": "Productos para Mascotas", "tema_base": "comederos para gatos"}},
  {{"keyword": "mejores monitores gaming 144hz calidad precio", "categoria": "Electrónica", "tema_base": "monitores gaming"}}
]
"""

    print("-> Analizando tendencias con OpenAI (Mercado España + Cuarentena + Diversificación)...")
    if temas_prohibidos:
        print(f"   [Cuarentena Activa] {len(temas_prohibidos)} temas prohibidos: {temas_prohibidos[:4]}...")

    modelos = ["gpt-4o-mini", "gpt-3.5-turbo"]
    respuesta = None

    for mod in modelos:
        try:
            r = client.chat.completions.create(
                model=mod,
                temperature=0.6,
                timeout=15.0,
                messages=[
                    {"role": "system", "content": prompt_sistema},
                    {"role": "user", "content": prompt_usuario},
                ],
            )
            respuesta = r.choices[0].message.content.strip()
            print(f"   [OK] Oportunidades generadas con éxito usando {mod}.")
            break
        except Exception as err:
            print(f"   [Aviso] Modelo {mod} falló o superó el timeout de 15s ({err}). Probando alternativa...")

    if not respuesta:
        raise RuntimeError("OpenAI no respondió a tiempo durante el análisis de mercado.")

    # Parsear JSON garantizando 4 categorías diferentes y excluyendo cuarentena
    oportunidades = []
    categorias_usadas = set()

    match_json = re.search(r"\[[\s\S]*?\]", respuesta)
    if match_json:
        try:
            items = json.loads(match_json.group(0))
            if isinstance(items, list):
                for item in items:
                    if isinstance(item, dict) and "keyword" in item and "categoria" in item:
                        kw = str(item["keyword"]).strip()
                        cat = validar_categoria(str(item["categoria"]))
                        tema_base = str(item.get("tema_base") or extraer_tema_base(kw)).strip()
                        # Verificar que no coincida con la cuarentena activa
                        if kw and cat and cat not in categorias_usadas and tema_base not in temas_prohibidos:
                            categorias_usadas.add(cat)
                            oportunidades.append({
                                "keyword": kw,
                                "categoria": cat,
                                "tema_base": tema_base,
                            })
        except Exception as e:
            print(f"   [Aviso] Error al parsear JSON ({e}). Aplicando respaldo diversificado...")

    # Relleno de seguridad diversificado si faltó alguna
    respaldo_diversificado = [
        {"keyword": "mejores freidoras de aire calidad precio", "categoria": "Hogar y Cocina", "tema_base": "freidoras de aire"},
        {"keyword": "comprar zapatillas running asfalto baratas", "categoria": "Deportes y Aire Libre", "tema_base": "zapatillas running"},
        {"keyword": "mejores comederos automaticos para gatos", "categoria": "Productos para Mascotas", "tema_base": "comederos para gatos"},
        {"keyword": "mejores monitores gaming 144hz calidad precio", "categoria": "Electrónica", "tema_base": "monitores gaming"},
        {"keyword": "mejores taladros percutores a bateria", "categoria": "Bricolaje y Herramientas", "tema_base": "taladros percutores"},
        {"keyword": "mejores cepillos de dientes electricos", "categoria": "Salud y Cuidado Personal", "tema_base": "cepillos de dientes electricos"},
        {"keyword": "mejores teclados mecanicos inalambricos", "categoria": "Informática", "tema_base": "teclados mecanicos"},
        {"keyword": "mejores auriculares gaming con microfono", "categoria": "Videojuegos", "tema_base": "auriculares gaming"},
    ]

    for fallback in respaldo_diversificado:
        if len(oportunidades) >= 4:
            break
        if fallback["categoria"] not in categorias_usadas and fallback["tema_base"] not in temas_prohibidos:
            categorias_usadas.add(fallback["categoria"])
            oportunidades.append(fallback)

    final_oportunidades = oportunidades[:4]

    # Extraer tema_base de cada una y guardarlo en cuarentena_temas.json con la fecha de hoy
    temas_nuevos = [op.get("tema_base") or extraer_tema_base(op["keyword"]) for op in final_oportunidades]
    guardar_cuarentena(temas_nuevos)

    return final_oportunidades


def obtener_oportunidades_diversificadas() -> list[dict]:
    """Función maestra: extrae tendencias y devuelve las 4 oportunidades (keyword + categoria)."""
    tendencias = extraer_tendencias_google()
    return generar_keywords_afiliacion(tendencias)


# Alias de retrocompatibilidad
obtener_keywords_tendencias = obtener_oportunidades_diversificadas


if __name__ == "__main__":
    print("=" * 65)
    print("  CLARAMENTE | TEST DE INTELIGENCIA (ESPAÑA + CUARENTENA)")
    print("=" * 65)
    resultados = obtener_oportunidades_diversificadas()
    for idx, item in enumerate(resultados, 1):
        print(f"  {idx}. [{item['categoria']}] {item['keyword']} (Tema: {item.get('tema_base')})")
    print("=" * 65)
