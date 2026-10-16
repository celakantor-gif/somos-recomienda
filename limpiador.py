"""
==============================================================================
SOMOS RECOMIENDA | LIMPIADOR Y EXTRACTOR DE PRODUCTOS (limpiador.py)
==============================================================================
Rol: Senior Data Engineer & Lead Backend.
Misión:
  1. Lee el archivo 'bruto.csv' con el scraping masivo de Amazon.
  2. Extrae 'asin' -> 'asin_amazon'.
  3. Extrae la última frase limpia de 'breadCrumbs' -> 'categoria'.
  4. Limpia el título sobrecargado ('title') usando OpenAI (gpt-4o-mini) -> 'keyword'.
  5. Genera 'keywords_productos.csv' con exactamente 3 columnas: keyword, categoria, asin_amazon.
==============================================================================
"""

import os
import sys
import csv
import re
import time
import argparse
from typing import Dict, List, Optional
from dotenv import load_dotenv
from openai import OpenAI

# Configurar salida segura UTF-8 para consola en Windows
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# Permitir campos de texto largos en CSVs con aPlusContent extenso
try:
    csv.field_size_limit(sys.maxsize)
except (OverflowError, Exception):
    csv.field_size_limit(10 * 1024 * 1024)

# ==============================================================================
# CONFIGURACIÓN GENERAL Y CREDENCIALES
# ==============================================================================

load_dotenv()
OPENAI_KEY = os.getenv("OPENAI_API_KEY")

DEFAULT_INPUT_CSV = "bruto.csv"
DEFAULT_OUTPUT_CSV = "keywords_productos.csv"
DEFAULT_LIMIT = 10


def get_openai_client() -> OpenAI:
    """Instancia y valida el cliente de OpenAI."""
    api_key = os.getenv("OPENAI_API_KEY") or OPENAI_KEY
    if not api_key:
        raise RuntimeError(
            "ERROR CRÍTICO: Falta OPENAI_API_KEY en el entorno o archivo .env. "
            "Por favor, configure la clave de API para continuar."
        )
    return OpenAI(api_key=api_key, timeout=30.0)


# ==============================================================================
# PARSEO Y LIMPIEZA DE DATOS
# ==============================================================================

def extraer_categoria(breadcrumbs_raw: Optional[str]) -> str:
    """
    Extrae la última palabra o frase limpia de la jerarquía breadCrumbs.
    Ejemplo:
      De: 'Bricolaje y herramientas > Herramientas manuales > Taladro percutor'
      A:  'Taladro percutor'
    """
    if not breadcrumbs_raw or not str(breadcrumbs_raw).strip():
        return "General"

    # Normalizar separadores habituales (>, ›, /, &gt;)
    texto = (
        str(breadcrumbs_raw)
        .replace("&gt;", ">")
        .replace("›", ">")
        .replace("»", ">")
        .strip()
    )

    partes = [p.strip() for p in texto.split(">") if p.strip()]
    if partes:
        ultima_categoria = partes[-1]
        # Limpieza de comillas y caracteres redundantes
        categoria_limpia = re.sub(r"^[\"'\s]+|[\"'\s]+$", "", ultima_categoria)
        return categoria_limpia.strip() or "General"

    return "General"


def limpiar_keyword_con_ia(client: OpenAI, titulo_original: str) -> str:
    """
    Utiliza gpt-4o-mini para transformar un título saturado de Amazon
    en una keyword comercial limpia de máxima conversión (5 o 6 palabras).
    """
    if not titulo_original or not str(titulo_original).strip():
        return ""

    system_prompt = (
        "Eres un Senior Data Engineer y especialista en SEO para comercio electrónico. "
        "Tu misión es limpiar títulos de productos de Amazon sobrecargados de palabras clave, "
        "accesorios y especificaciones técnicas irrelevantes.\n"
        "Reglas estrictas:\n"
        "1. Devuelve ÚNICAMENTE el nombre comercial principal y el modelo limpio ideal para una búsqueda en Google.\n"
        "2. Máximo 5 o 6 palabras.\n"
        "3. PROHIBIDO incluir comillas, punto final, explicaciones o prefijos como 'Keyword:' o 'Título:'."
    )

    user_prompt = (
        "Toma este título de Amazon lleno de spam y características técnicas, "
        "y devuélveme solo el nombre comercial principal y el modelo limpio, "
        "ideal para una búsqueda en Google. Máximo 5 o 6 palabras.\n\n"
        f"Título: {titulo_original.strip()}"
    )

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            temperature=0.2,
            max_tokens=30,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )
        texto = response.choices[0].message.content or ""
        # Limpieza estricta de la respuesta
        keyword_limpia = texto.strip().strip("\"'").strip()
        keyword_limpia = re.sub(r"^(keyword|título|producto|nombre):\s*", "", keyword_limpia, flags=re.IGNORECASE)
        # Limitar a máximo 6 palabras por seguridad
        palabras = keyword_limpia.split()
        if len(palabras) > 6:
            keyword_limpia = " ".join(palabras[:6])
        return keyword_limpia
    except Exception as e:
        print(f"      [Aviso IA] Error al procesar título con LLM: {e}")
        # Fallback determinista en caso de corte o timeout de API
        palabras = titulo_original.strip().split()
        return " ".join(palabras[:5]) if palabras else "Producto Amazon"


# ==============================================================================
# PROCESADOR PRINCIPAL (ETL)
# ==============================================================================

def procesar_bruto(
    input_path: str = DEFAULT_INPUT_CSV,
    output_path: str = DEFAULT_OUTPUT_CSV,
    limit: Optional[int] = DEFAULT_LIMIT,
) -> List[Dict[str, str]]:
    """
    Ejecuta el pipeline ETL:
      - Extract: Lectura de bruto.csv
      - Transform: Extracción de categoría y limpieza de título con gpt-4o-mini
      - Load: Escritura de keywords_productos.csv
    """
    print("\n" + "=" * 80)
    print("  SOMOS RECOMIENDA | PIPELINE ETL LIMPIADOR (bruto.csv -> keywords_productos.csv)")
    print(f"  Origen: '{input_path}' | Destino: '{output_path}' | Límite: {limit if limit else 'Completo'}")
    print("=" * 80)

    # 1. Validación de existencia del archivo origen
    if not os.path.isfile(input_path):
        print(f"\n[ERROR CRÍTICO] El archivo de entrada '{input_path}' no existe.")
        return []

    client = get_openai_client()

    productos_limpios: List[Dict[str, str]] = []
    filas_leidas = 0

    print(f"\n-> Abriendo '{input_path}' e iniciando procesamiento de registros...\n")

    with open(input_path, mode="r", encoding="utf-8", errors="replace") as f_in:
        reader = csv.DictReader(f_in)

        # Validar columnas mínimas requeridas en bruto.csv
        fieldnames = reader.fieldnames or []
        columnas_lower = {c.lower(): c for c in fieldnames}

        col_asin = columnas_lower.get("asin")
        col_breadcrumbs = columnas_lower.get("breadcrumbs")
        col_title = columnas_lower.get("title")

        if not col_asin or not col_title:
            print(f"[ERROR CRÍTICO] El archivo '{input_path}' no contiene las columnas necesarias ('asin', 'title').")
            return []

        for row in reader:
            filas_leidas += 1

            asin = (row.get(col_asin) or "").strip()
            titulo_raw = (row.get(col_title) or "").strip()
            breadcrumbs_raw = (row.get(col_breadcrumbs) or "") if col_breadcrumbs else ""

            # Descartar filas vacías o sin ASIN
            if not asin or not titulo_raw:
                continue

            idx_actual = len(productos_limpios) + 1
            print(f"[{idx_actual}/{limit}] Procesando ASIN: {asin}")

            # 1. Extraer categoría limpia
            categoria = extraer_categoria(breadcrumbs_raw)

            # 2. Limpiar título con IA
            keyword = limpiar_keyword_con_ia(client, titulo_raw)

            print(f"    - Título Original : {titulo_raw[:75]}...")
            print(f"    - Categoría       : {categoria}")
            print(f"    - Keyword Limpia  : {keyword}")
            print("-" * 70)

            productos_limpios.append({
                "keyword": keyword,
                "categoria": categoria,
                "asin_amazon": asin,
            })

            # Detener si alcanzamos el límite indicado para control de costes
            if limit is not None and len(productos_limpios) >= limit:
                print(f"\n[LÍMITE ALCANZADO] Se han procesado satisfactoriamente los primeros {limit} productos.")
                break

            # Pequeña pausa de cortesía para evitar rate-limits agresivos
            time.sleep(0.3)

    if not productos_limpios:
        print("\n[AVISO] No se encontraron productos válidos para exportar.")
        return []

    # 3. Guardar el nuevo CSV con exactamente las 3 columnas solicitadas
    print(f"\n-> Guardando archivo final en: '{output_path}'...")
    columnas_salida = ["keyword", "categoria", "asin_amazon"]

    with open(output_path, mode="w", encoding="utf-8", newline="") as f_out:
        writer = csv.DictWriter(f_out, fieldnames=columnas_salida)
        writer.writeheader()
        writer.writerows(productos_limpios)

    print("\n" + "=" * 80)
    print("  RESUMEN DE EJECUCIÓN ETL:")
    print(f"  * Filas inspeccionadas en bruto.csv : {filas_leidas}")
    print(f"  * Productos procesados y guardados  : {len(productos_limpios)}")
    print(f"  * Archivo de salida generado       : {output_path}")
    print("=" * 80 + "\n")

    return productos_limpios


# ==============================================================================
# PUNTO DE ENTRADA CLI
# ==============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Pipeline ETL limpiador de títulos y categorías de Amazon para Somos Recomienda."
    )
    parser.add_argument(
        "--input",
        type=str,
        default=DEFAULT_INPUT_CSV,
        help=f"Archivo CSV bruto de entrada (por defecto: {DEFAULT_INPUT_CSV})",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=DEFAULT_OUTPUT_CSV,
        help=f"Archivo CSV limpio de salida (por defecto: {DEFAULT_OUTPUT_CSV})",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=DEFAULT_LIMIT,
        help=f"Número máximo de filas a procesar (por defecto: {DEFAULT_LIMIT})",
    )

    args = parser.parse_args()
    procesar_bruto(
        input_path=args.input,
        output_path=args.output,
        limit=args.limit,
    )


if __name__ == "__main__":
    main()
