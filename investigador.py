import os
import re
import csv
import json
import unicodedata
from dotenv import load_dotenv
from openai import OpenAI

# ==========================================
# Cerebro de Rentabilidad: genera 3 keywords long-tail de alta intención
# de compra para un nicho y sobrescribe keywords.csv para escritor.py.
# La llave se lee de .env (OPENAI_API_KEY).
# ==========================================
load_dotenv()
MI_LLAVE = os.getenv("OPENAI_API_KEY")
if not MI_LLAVE:
    raise SystemExit("ERROR: falta OPENAI_API_KEY. Pégala en el archivo .env de la raíz del proyecto.")

client = OpenAI(api_key=MI_LLAVE)


def normalizar(texto):
    """Minúsculas, sin tildes ni signos: deja la keyword lista para usarla como slug."""
    texto = unicodedata.normalize("NFKD", texto.strip().lower())
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    texto = re.sub(r"[^a-z0-9\s]", " ", texto)
    return re.sub(r"\s+", " ", texto).strip()


print("Cerebro de Rentabilidad - Investigador de Keywords")
nicho = input("Nicho de mercado (ej: jardinería, cafeteras, bicicletas eléctricas): ").strip()
if not nicho:
    raise SystemExit("ERROR: debes indicar un nicho de mercado.")

instrucciones = f"""
Actúa como un experto en SEO de afiliación y comercio electrónico en español.
Nicho de mercado: '{nicho}'.

Genera EXACTAMENTE 3 palabras clave de cola larga (long-tail, entre 4 y 8 palabras) con ALTA intención de compra.
Cada una debe incluir términos transaccionales como 'comprar', 'mejores', 'precio', 'barato' u 'oferta',
y debe tener poca competencia pero búsquedas reales.

FORMATO DE SALIDA: devuelve SOLO un array JSON con 3 strings, sin texto adicional ni bloques de código.
Ejemplo: ["mejores cafeteras italianas baratas", "comprar cafetera de goteo precio", "cafetera espresso barata opiniones"]
"""

print(f"-> Investigando keywords para '{nicho}'...")
respuesta = client.chat.completions.create(
    model="gpt-3.5-turbo",
    messages=[{"role": "user", "content": instrucciones}],
)
bruto = respuesta.choices[0].message.content.strip()

try:
    # Tolera que la IA envuelva el JSON en texto o ``` por error
    lista = json.loads(re.search(r"\[.*\]", bruto, re.S).group(0))
except (AttributeError, json.JSONDecodeError):
    raise SystemExit(f"ERROR: respuesta inesperada de la IA, no se ha tocado keywords.csv:\n{bruto}")

# Normalizamos, quitamos vacíos y duplicados conservando el orden
keywords = list(dict.fromkeys(k for k in (normalizar(str(x)) for x in lista) if k))[:3]
if len(keywords) != 3:
    raise SystemExit(f"ERROR: se esperaban 3 keywords válidas y llegaron {len(keywords)}. No se ha tocado keywords.csv.")

with open("keywords.csv", mode="w", encoding="utf-8", newline="") as archivo:
    escritor_csv = csv.writer(archivo)
    escritor_csv.writerow(["Keyword"])
    for k in keywords:
        escritor_csv.writerow([k])

print("==========================================")
print("keywords.csv actualizado con las 3 keywords ganadoras:")
for k in keywords:
    print(f"  - {k}")
print("Ahora ejecuta: python escritor.py")
print("==========================================")
