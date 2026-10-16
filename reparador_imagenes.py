import os
import re
import glob

# ==============================================================================
# REPARADOR RETROACTIVO DE IMÁGENES DESTACADAS (heroImage)
# Sincroniza las imágenes descargadas en public/img/ con el frontmatter de los posts
# ==============================================================================

RUTA_BLOG = os.path.join("src", "content", "blog")
RUTA_IMG = os.path.join("public", "img")


def procesar_imagenes():
    archivos_md = glob.glob(os.path.join(RUTA_BLOG, "*.md"))
    if not archivos_md:
        print("No se encontraron artículos en src/content/blog/")
        return

    imagenes_disponibles = [f for f in os.listdir(RUTA_IMG) if f.lower().endswith((".jpg", ".jpeg", ".png", ".webp"))]
    print("==================================================================")
    print(f"Iniciando sincronización de heroImage sobre {len(archivos_md)} artículos...")
    print(f"Imágenes disponibles en public/img: {len(imagenes_disponibles)}")
    print("==================================================================")

    actualizados = 0

    for ruta in archivos_md:
        nombre_md = os.path.basename(ruta)
        slug = nombre_md[:-3].lower()  # quitar .md

        with open(ruta, "r", encoding="utf-8") as f:
            contenido = f.read()

        imagen_asignada = None

        # 1. Buscar coincidencia exacta: {slug}-1.jpg
        candidata_exacta = f"{slug}-1.jpg"
        if os.path.exists(os.path.join(RUTA_IMG, candidata_exacta)):
            imagen_asignada = f"/img/{candidata_exacta}"
        else:
            # 2. Coincidencia inteligente por relevancia de términos (evitando palabras genéricas)
            palabras_genericas = {
                "comprar", "mejores", "barato", "baratos", "barata", "baratas",
                "online", "calidad", "precio", "precios", "oferta", "ofertas",
                "segunda", "mano", "para", "como", "con", "las", "los", "del"
            }
            palabras_clave = [p for p in slug.split("-") if len(p) > 2 and p not in palabras_genericas]

            candidatas = [img for img in imagenes_disponibles if img != "equipo.jpg" and img.endswith("-1.jpg")]
            if not candidatas:
                candidatas = [img for img in imagenes_disponibles if img != "equipo.jpg"]

            mejor_img = None
            mejor_score = 0

            for img in candidatas:
                img_lower = img.lower()
                score = 0
                for p in palabras_clave:
                    # Coincidencia de raíz (ej: dron coincide con drones)
                    if p in img_lower or (len(p) > 4 and p[:4] in img_lower):
                        score += 2
                if score > mejor_score:
                    mejor_score = score
                    mejor_img = img

            if mejor_img and mejor_score > 0:
                imagen_asignada = f"/img/{mejor_img}"
            else:
                # 3. Fallback seguro: primera imagen -1.jpg disponible
                if candidatas:
                    imagen_asignada = f"/img/{candidatas[0]}"
                else:
                    imagen_asignada = "/img/equipo.jpg"

        # Reemplazar heroImage en frontmatter si existe, o inyectarlo
        if re.search(r'heroImage:\s*["\']?[^"\'\n\r]+["\']?', contenido):
            nuevo_contenido = re.sub(
                r'(heroImage:\s*)[^\n\r]+',
                f'heroImage: "{imagen_asignada}"',
                contenido,
                count=1,
            )
        else:
            # Inyectar después de title
            nuevo_contenido = re.sub(
                r'(title:\s*[^\n\r]+\n)',
                f'\\1heroImage: "{imagen_asignada}"\n',
                contenido,
                count=1,
            )

        with open(ruta, "w", encoding="utf-8", newline="\n") as f:
            f.write(nuevo_contenido)

        print(f"-> {nombre_md} -> heroImage: '{imagen_asignada}'")
        actualizados += 1

    print("==================================================================")
    print(f"¡Sincronización completada! {actualizados} artículos actualizados con heroImage local.")
    print("==================================================================")


if __name__ == "__main__":
    procesar_imagenes()
