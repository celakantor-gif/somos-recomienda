"""
==============================================================================
SOMOS RECOMIENDA | GENERADOR OAUTH 2.0 DE LLAVE MAESTRA PINTEREST (API v5)
==============================================================================
Obtiene un Access Token oficial con permisos completos de lectura y escritura:
  - Scopes: boards:read, boards:write, pins:read, pins:write
  - Endpoint: POST https://api.pinterest.com/v5/oauth/token
==============================================================================
"""

import sys
import urllib.parse
import json
import requests

# Forzar salida UTF-8 en consolas Windows
try:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


def extraer_codigo_oauth(entrada_usuario: str) -> str:
    """Extrae el parámetro 'code' de la URL de redirección o devuelve el código limpio."""
    texto = entrada_usuario.strip()
    if "code=" in texto:
        parsed = urllib.parse.urlparse(texto)
        params = urllib.parse.parse_qs(parsed.query)
        if "code" in params and params["code"]:
            return params["code"][0].strip()
        # Fallback por si pegaron un fragmento parcial con code=
        parte = texto.split("code=", 1)[1]
        return parte.split("&", 1)[0].strip()
    return texto


def main():
    print("\n" + "=" * 78)
    print("  🔑 GENERADOR DE LLAVE MAESTRA OAUTH 2.0 - PINTEREST API v5")
    print("=" * 78)
    print("NOTA PREVIA: Asegúrate de que en tu App de Pinterest Developers")
    print("(apartado 'Redirect URIs') tengas añadido exactamente: https://localhost/\n")

    client_id = input("1️⃣  Introduce tu App ID (Client ID): ").strip()
    client_secret = input("2️⃣  Introduce tu App Secret key (Client Secret): ").strip()

    if not client_id or not client_secret:
        print("\n❌ [ERROR] Debes introducir tanto el Client ID como el Client Secret.")
        return

    redirect_uri = "https://localhost/"
    scopes = "boards:read,boards:write,pins:read,pins:write"
    auth_url = (
        f"https://www.pinterest.com/oauth/"
        f"?client_id={client_id}"
        f"&redirect_uri={redirect_uri}"
        f"&response_type=code"
        f"&scope={scopes}"
    )

    print("\n" + "-" * 78)
    print("🌐 PASO 1: Abre la siguiente URL en tu navegador y pulsa 'Dar acceso' (Give access):")
    print("-" * 78)
    print(f"\n{auth_url}\n")
    print("-" * 78)
    print("💡 Al aceptar, el navegador intentará abrir https://localhost/?code=...")
    print("   (Es normal que el navegador diga 'No se puede acceder a este sitio').")
    print("   Simplemente copia la URL completa de la barra de direcciones superior.\n")

    url_redirigida = input(
        "Pega aquí la URL completa a la que te ha redirigido el navegador (empezará por https://localhost/?code=...): "
    ).strip()

    codigo = extraer_codigo_oauth(url_redirigida)
    if not codigo:
        print("\n❌ [ERROR] No se pudo detectar el parámetro 'code' en la URL proporcionada.")
        return

    print(f"\n⏳ Código detectado ('{codigo[:10]}...'). Canjeando por Access Token en Pinterest API v5...")

    token_url = "https://api.pinterest.com/v5/oauth/token"
    payload = {
        "grant_type": "authorization_code",
        "code": codigo,
        "redirect_uri": redirect_uri,
    }
    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
    }

    try:
        response = requests.post(
            token_url,
            auth=(client_id, client_secret),
            data=payload,
            headers=headers,
            timeout=20,
        )
    except requests.RequestException as e:
        print(f"\n❌ [ERROR DE RED] No se pudo conectar con Pinterest: {e}")
        return

    if response.status_code == 200:
        datos = response.json()
        access_token = datos.get("access_token", "")
        refresh_token = datos.get("refresh_token", "")
        scope_concedido = datos.get("scope", "")

        print("\n" + "#" * 80)
        print("#" + " " * 78 + "#")
        print("#" + "      🎉 ¡ÉXITO! AQUÍ TIENES TU PINTEREST_ACCESS_TOKEN MAESTRO 🎉      ".center(78) + "#")
        print("#" + " " * 78 + "#")
        print("#" * 80)
        print("\nCOPIA EL SIGUIENTE TOKEN (empieza por pina_...):\n")
        print("=" * 80)
        print(access_token)
        print("=" * 80)
        print(f"\n✅ Permisos (Scopes) activos: {scope_concedido}")
        if refresh_token:
            print(f"🔄 Refresh Token (guárdalo por seguridad): {refresh_token}")
        print("\n📌 PRÓXIMOS PASOS:")
        print("   1. Pega este token en tu archivo .env -> PINTEREST_ACCESS_TOKEN=...")
        print("   2. Actualiza el secreto PINTEREST_ACCESS_TOKEN en GitHub Actions Secrets.")
        print("#" * 80 + "\n")
    else:
        print(f"\n❌ [ERROR HTTP {response.status_code}] Pinterest rechazó el canje del código:")
        try:
            print(json.dumps(response.json(), indent=2, ensure_ascii=False))
        except Exception:
            print(response.text)


if __name__ == "__main__":
    main()
