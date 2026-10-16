import time
from datetime import datetime
from inteligencia import obtener_oportunidades_diversificadas
from escritor import redactar_y_publicar_articulo
from noticiero import publicar_noticia

# ==============================================================================
# ORQUESTADOR MAESTRO BLINDADO (orquestador.py)
# - Estrategia 4+1: 4 guías transaccionales en 4 categorías distintas + 1 noticia.
# - Resiliencia Absoluta: Control de excepciones y timeouts (timeout=15).
#   Si un artículo falla, registra el error y salta al siguiente sin abortar.
# ==============================================================================


def ejecutar_orquestador():
    inicio = time.time()
    fecha_actual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    print("\n" + "=" * 70)
    print("  CLARAMENTE | ORQUESTADOR MAESTRO 4+1 (PRODUCCIÓN BLINDADA)")
    print(f"  Inicio: {fecha_actual}")
    print("  Estrategia: 4 Guías de Compra (Categorías Distintas) + 1 Noticia")
    print("=" * 70)

    # --------------------------------------------------------------------------
    # FASE 1: Inteligencia con Diversificación Forzada
    # --------------------------------------------------------------------------
    print("\n[FASE 1/3] Extrayendo tendencias de Google Trends y asignando 4 categorías...")
    try:
        oportunidades = obtener_oportunidades_diversificadas()
    except Exception as e:
        print(f"   [Aviso en Inteligencia]: {e}. Usando oportunidades de respaldo diversificadas.")
        oportunidades = [
            {"keyword": "mejores freidoras de aire calidad precio", "categoria": "Hogar y Cocina"},
            {"keyword": "comprar zapatillas running asfalto baratas", "categoria": "Deportes y Aire Libre"},
            {"keyword": "mejores comederos automaticos para gatos", "categoria": "Productos para Mascotas"},
            {"keyword": "mejores monitores gaming 144hz calidad precio", "categoria": "Electrónica"},
        ]

    print("\n-> Plan de Publicación Diversificado para Hoy:")
    for idx, op in enumerate(oportunidades, 1):
        print(f"   {idx}. [{op['categoria']}] {op['keyword']}")

    # --------------------------------------------------------------------------
    # FASE 2: Bucle Resiliente de 4 Artículos Transaccionales
    # --------------------------------------------------------------------------
    print("\n[FASE 2/3] Generando 4 guías de compra de alta conversión...")
    articulos_generados = []
    fallos = []

    for i, op in enumerate(oportunidades, 1):
        kw = op.get("keyword") if isinstance(op, dict) else str(op)
        cat = op.get("categoria") if isinstance(op, dict) else None

        print(f"\n--- Redactando Guía {i}/{len(oportunidades)}: '{kw}' [{cat}] ---")
        try:
            ruta = redactar_y_publicar_articulo(kw, categoria_forzada=cat)
            articulos_generados.append({"ruta": ruta, "keyword": kw, "categoria": cat})
            # Pausa de cortesía para no saturar APIs
            if i < len(oportunidades):
                time.sleep(3)
        except Exception as e:
            print(f"   [FALLO REGISTRADO EN GUÍA {i}] Error procesando '{kw}': {e}")
            fallos.append({"keyword": kw, "categoria": cat, "error": str(e)})
            continue

    # --------------------------------------------------------------------------
    # FASE 3: Generación Resiliente de la Noticia de Actualidad
    # --------------------------------------------------------------------------
    print("\n[FASE 3/3] Generando la noticia de actualidad del día (España)...")
    noticia_ok = False
    try:
        publicar_noticia()
        noticia_ok = True
    except Exception as e:
        print(f"   [FALLO REGISTRADO EN NOTICIERO] Error publicando noticia: {e}. Continuando...")
        fallos.append({"keyword": "Noticia diaria", "categoria": "Noticias", "error": str(e)})

    # --------------------------------------------------------------------------
    # RESUMEN EJECUTIVO
    # --------------------------------------------------------------------------
    duracion = round(time.time() - inicio, 1)
    total_publicados = len(articulos_generados) + (1 if noticia_ok else 0)

    print("\n" + "=" * 70)
    print("  RESUMEN DE LA ORQUESTACION AUTOMATICA")
    print(f"  * Guias transaccionales creadas: {len(articulos_generados)} de {len(oportunidades)}")
    for g in articulos_generados:
        print(f"    [OK] [{g['categoria']}] {g['keyword']}")
    print(f"  * Noticia de actualidad creada:  {'[OK] Si (100% Ok)' if noticia_ok else '[X] Fallo'}")
    if fallos:
        print(f"  * Fallos registrados ({len(fallos)}):")
        for f in fallos:
            print(f"    ! [{f['categoria']}] {f['keyword']}: {f['error']}")
    print(f"  * Total de piezas publicadas:    {total_publicados}/5")
    print(f"  * Tiempo total de ejecucion:     {duracion} segundos")
    print("=" * 70 + "\n")


if __name__ == "__main__":
    ejecutar_orquestador()
