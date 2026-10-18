"""
==============================================================================
SOMOS RECOMIENDA | EXPLORADOR DE TABLEROS DE PINTEREST (API v5)
==============================================================================
Consulta la API oficial de Pinterest para listar los tableros disponibles
en tu cuenta con sus respectivos IDs para configurar PINTEREST_BOARD_ID.
==============================================================================
"""

import os
import sys
import requests

# Forzar UTF-8 en terminal de Windows
try:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

# Cargar variables de entorno si existe python-dotenv
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

TOKEN = os.getenv("PINTEREST_ACCESS_TOKEN")


def listar_tableros():
    print("=" * 70)
    print("  CONSULTANDO TABLEROS DE PINTEREST (API v5)")
    print("=" * 70)

    if not TOKEN:
        print("\n[ERROR CRÍTICO] No se encontró la variable PINTEREST_ACCESS_TOKEN.")
        print("Asegúrate de definirla en tu archivo .env con el token de acceso de Pinterest.")
        print("Ejemplo en .env:")
        print("PINTEREST_ACCESS_TOKEN=\"pina_...\"\n")
        return

    url = "https://api.pinterest.com/v5/boards"
    headers = {
        "Authorization": f"Bearer {TOKEN.strip()}",
        "Content-Type": "application/json"
    }
    params = {
        "page_size": 50
    }

    try:
        response = requests.get(url, headers=headers, params=params, timeout=15)
    except requests.RequestException as e:
        print(f"\n[ERROR DE CONEXIÓN] No se pudo conectar con la API de Pinterest: {e}\n")
        return

    if response.status_code == 200:
        data = response.json()
        items = data.get("items", [])

        if not items:
            print("\n[AVISO] No se encontraron tableros en esta cuenta de Pinterest.")
            print("Crea al menos un tablero en tu perfil de Pinterest (ej. 'Recomendaciones') y vuelve a ejecutar este script.\n")
            return

        print(f"\n[ÉXITO] Se encontraron {len(items)} tablero(s) en tu cuenta:\n")
        print(f"{'NOMBRE DEL TABLERO':<35} | {'BOARD ID':<25} | {'PRIVACIDAD'}")
        print("-" * 75)

        for board in items:
            nombre = board.get("name", "Sin nombre")
            board_id = board.get("id", "Sin ID")
            privacidad = board.get("privacy", "PUBLIC")
            print(f"{nombre:<35} | {board_id:<25} | {privacidad}")

        print("-" * 75)
        print("\nINSTRUCCIONES:")
        print("1. Copia el 'BOARD ID' del tablero donde quieras publicar tus pines.")
        print("2. Abre tu archivo .env y añade la siguiente línea:")
        print(f"   PINTEREST_BOARD_ID=\"{items[0].get('id')}\"")
        print("=" * 70 + "\n")

    elif response.status_code == 401:
        print("\n[ERROR 401] Token no autorizado o expirado.")
        try:
            print(f"Detalle de Pinterest: {response.json()}")
        except Exception:
            print(f"Respuesta cruda: {response.text}")
        print("Verifica que tu PINTEREST_ACCESS_TOKEN sea correcto y tenga los permisos 'boards:read' y 'pins:write'.\n")
    else:
        print(f"\n[ERROR {response.status_code}] Respuesta de Pinterest:")
        try:
            print(response.json())
        except Exception:
            print(response.text)
        print()


if __name__ == "__main__":
    listar_tableros()
