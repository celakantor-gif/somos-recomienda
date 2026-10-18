"""
==============================================================================
SOMOS RECOMIENDA | MOTOR DE GENERACIÓN DE PINES PARA PINTEREST
==============================================================================
Genera pines verticales de alta conversión (1000x1500px, ratio 2:3) con:
- Recorte inteligente y centrado de imagen de producto.
- Capas de gradiente de alto contraste para máxima legibilidad.
- Tipografía destacada, insignias de categoría y botones CTA de alto impacto.
==============================================================================
"""

import os
import re
import csv
import sys
import argparse
import unicodedata
from typing import Optional, List, Tuple
from PIL import Image, ImageDraw, ImageFont

try:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

PIN_WIDTH = 1000
PIN_HEIGHT = 1500
OUTPUT_DIR = os.path.join("public", "social", "pinterest")
DEFAULT_CSV = "keywords_productos.csv"

MAPA_FALLBACK_IMAGENES = {
    "hogar y cocina": "public/images/fallbacks/hogar-y-cocina-default.jpg",
    "hogar-y-cocina": "public/images/fallbacks/hogar-y-cocina-default.jpg",
    "informatica": "public/images/fallbacks/informatica-default.jpg",
    "productos para mascotas": "public/images/fallbacks/productos-para-mascotas-default.jpg",
    "productos-para-mascotas": "public/images/fallbacks/productos-para-mascotas-default.jpg",
    "deportes y aire libre": "public/images/fallbacks/deportes-default.jpg",
    "deportes-y-aire-libre": "public/images/fallbacks/deportes-default.jpg",
    "bricolaje y herramientas": "public/images/fallbacks/bricolaje-y-herramientas-default.jpg",
    "bricolaje-y-herramientas": "public/images/fallbacks/bricolaje-y-herramientas-default.jpg",
    "electronica": "public/images/fallbacks/electronica-default.jpg",
    "salud y cuidado personal": "public/images/fallbacks/salud-default.jpg",
    "salud-y-cuidado-personal": "public/images/fallbacks/salud-default.jpg",
    "cuidado personal": "public/images/fallbacks/salud-default.jpg",
    "cuidado-personal": "public/images/fallbacks/salud-default.jpg",
    "general": "public/images/fallbacks/consejos-default.jpg",
}


def normalizar_para_comparar(texto: str) -> str:
    """Normaliza texto eliminando tildes y signos diacríticos."""
    if not texto:
        return ""
    t = unicodedata.normalize("NFKD", str(texto).strip().lower())
    return "".join(c for c in t if not unicodedata.combining(c))


def slugify(texto: str) -> str:
    """Genera un slug URL limpio idéntico al de escritor.py."""
    t = normalizar_para_comparar(texto)
    t = re.sub(r"[^a-z0-9]+", "-", t).strip("-")
    return t[:80] or "producto-amazon"


def obtener_fuente(tamano: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    """Carga fuentes del sistema garantizando compatibilidad con Windows y Linux (GitHub Actions)."""
    candidatas = []
    if bold:
        candidatas = [
            "C:\\Windows\\Fonts\\arialbd.ttf",
            "C:\\Windows\\Fonts\\segoeuib.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
            "arialbd.ttf",
            "DejaVuSans-Bold.ttf",
        ]
    else:
        candidatas = [
            "C:\\Windows\\Fonts\\arial.ttf",
            "C:\\Windows\\Fonts\\segoeui.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
            "arial.ttf",
            "DejaVuSans.ttf",
        ]

    for ruta in candidatas:
        if os.path.exists(ruta):
            try:
                return ImageFont.truetype(ruta, tamano)
            except Exception:
                pass
        try:
            return ImageFont.truetype(ruta, tamano)
        except Exception:
            pass

    try:
        return ImageFont.load_default(size=tamano)
    except TypeError:
        return ImageFont.load_default()


def ajustar_texto(texto: str, draw: ImageDraw.ImageDraw, font: ImageFont.ImageFont, max_ancho: int) -> List[str]:
    """Divide un texto en varias líneas sin desbordar el ancho máximo."""
    palabras = texto.split()
    lineas: List[str] = []
    linea_actual: List[str] = []

    for palabra in palabras:
        prueba = " ".join(linea_actual + [palabra])
        bbox = draw.textbbox((0, 0), prueba, font=font)
        ancho = bbox[2] - bbox[0]
        if ancho <= max_ancho:
            linea_actual.append(palabra)
        else:
            if linea_actual:
                lineas.append(" ".join(linea_actual))
                linea_actual = [palabra]
            else:
                lineas.append(palabra)
                linea_actual = []

    if linea_actual:
        lineas.append(" ".join(linea_actual))

    return lineas


def crear_gradiente_contraste(width: int, height: int) -> Image.Image:
    """Genera una máscara semitransparente oscura en las zonas superior e inferior."""
    overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    # Gradiente superior (y: 0 a 620)
    top_limit = 620
    for y in range(top_limit):
        ratio = 1.0 - (y / top_limit)
        alpha = int(225 * (ratio ** 1.3))
        draw.line([(0, y), (width, y)], fill=(10, 15, 25, alpha))

    # Gradiente inferior (y: 880 a 1500)
    bottom_start = 880
    bottom_range = height - bottom_start
    for y in range(bottom_start, height):
        ratio = (y - bottom_start) / bottom_range
        alpha = int(240 * (ratio ** 1.2))
        draw.line([(0, y), (width, y)], fill=(10, 15, 25, alpha))

    return overlay


def resolver_imagen_origen(keyword: str, categoria: str, ruta_especifica: Optional[str] = None) -> Optional[str]:
    """
    Localiza con precisión absoluta la imagen exacta del producto usada en su artículo.
    1. Si se pasa ruta específica válida, la utiliza.
    2. Lee el artículo correspondiente en src/content/blog/ y extrae la ruta del campo 'heroImage'.
    3. Si no localiza el artículo, comprueba coincidencias directas en public/img por slug.
    4. Si falla, usa la imagen fallback oficial de la categoría.
    """
    if ruta_especifica and os.path.exists(ruta_especifica):
        return ruta_especifica

    slug_producto = slugify(keyword)
    anio_actual = 2026

    # 1. Buscar en los artículos de src/content/blog/ para sincronizar 100% con heroImage
    blog_dir = os.path.join("src", "content", "blog")
    if os.path.exists(blog_dir):
        archivos_blog = [
            os.path.join(blog_dir, f)
            for f in os.listdir(blog_dir)
            if f.endswith((".md", ".mdx")) and not f.startswith(".")
        ]
        # Ordenar por fecha de modificación (los más recientes primero)
        archivos_blog.sort(key=os.path.getmtime, reverse=True)

        for ruta_post in archivos_blog:
            try:
                with open(ruta_post, "r", encoding="utf-8") as fp:
                    contenido = fp.read(2000)
                    
                    coincide = False
                    if f'keyword: "{keyword}"' in contenido or f"keyword: '{keyword}'" in contenido:
                        coincide = True
                    elif slug_producto in ruta_post.lower():
                        coincide = True
                    
                    if coincide:
                        m = re.search(r'heroImage:\s*["\']([^"\']+)["\']', contenido)
                        if m:
                            hero_val = m.group(1).strip()
                            ruta_local = os.path.join("public", hero_val.lstrip("/\\"))
                            if os.path.exists(ruta_local):
                                print(f"    [Pinterest Imagen] Coincidencia exacta con artículo '{os.path.basename(ruta_post)}': {ruta_local}")
                                return ruta_local
            except Exception:
                pass

    # 2. Candidatas directas por nombre de archivo en public/img
    candidatas_directas = [
        os.path.join("public", "img", f"mejor-{slug_producto}-{anio_actual}.jpg"),
        os.path.join("public", "img", f"{slug_producto}.jpg"),
        os.path.join("public", "img", f"mejor-{slug_producto}.jpg"),
    ]
    for c in candidatas_directas:
        if os.path.exists(c):
            print(f"    [Pinterest Imagen] Archivo directo encontrado: {c}")
            return c

    # 3. Fallbacks de categoría (sin búsqueda parcial difusa que traiga imágenes erróneas)
    cat_norm = normalizar_para_comparar(categoria).replace("-", " ")
    fallback = MAPA_FALLBACK_IMAGENES.get(cat_norm, MAPA_FALLBACK_IMAGENES.get(categoria.lower(), MAPA_FALLBACK_IMAGENES["general"]))
    if os.path.exists(fallback):
        print(f"    [Pinterest Imagen] Usando fallback de categoría: {fallback}")
        return fallback

    return None


def recortar_y_centrar(img: Image.Image, target_w: int = PIN_WIDTH, target_h: int = PIN_HEIGHT) -> Image.Image:
    """Escala y recorta al centro para llenar exactamente la proporción 2:3."""
    target_ratio = target_w / target_h
    img_ratio = img.width / img.height

    if img_ratio > target_ratio:
        # La imagen es más ancha: escalar por alto y recortar laterales
        new_h = target_h
        new_w = int(img.width * (target_h / img.height))
        resized = img.resize((new_w, new_h), Image.Resampling.LANCZOS)
        left = (new_w - target_w) // 2
        return resized.crop((left, 0, left + target_w, target_h))
    else:
        # La imagen es más alta o cuadrada: escalar por ancho y recortar arriba/abajo
        new_w = target_w
        new_h = int(img.height * (target_w / img.width))
        resized = img.resize((new_w, new_h), Image.Resampling.LANCZOS)
        top = (new_h - target_h) // 2
        return resized.crop((0, top, target_w, top + target_h))


def calcular_color_texto_contraste(color_fondo_rgba: Tuple[int, ...]) -> Tuple[Tuple[int, int, int], Tuple[int, int, int]]:
    """
    Garantiza alto contraste entre el texto y el fondo de las etiquetas.
    - Si el fondo es blanco o claro (luminancia > 140): texto gris oscuro/negro casi puro (17, 24, 39) y borde gris claro (209, 213, 219).
    - Si el fondo es oscuro (luminancia <= 140): texto blanco puro (255, 255, 255) y borde turquesa (45, 212, 191).
    """
    r, g, b = color_fondo_rgba[:3]
    luminancia = 0.299 * r + 0.587 * g + 0.114 * b
    if luminancia > 140:
        return (17, 24, 39), (209, 213, 219)
    else:
        return (255, 255, 255), (45, 212, 191)


def crear_pin(
    keyword: str,
    categoria: str,
    ruta_imagen: Optional[str] = None,
    ruta_salida: Optional[str] = None,
    estilo_pildoras: str = "blanco",
) -> str:
    """
    Crea un Pin de Pinterest de alta conversión (1000x1500) para un producto.
    Retorna la ruta absoluta del archivo generado.
    """
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    slug = slugify(keyword)

    if not ruta_salida:
        ruta_salida = os.path.join(OUTPUT_DIR, f"pin_{slug}.jpg")

    # 1. Cargar imagen original o generar fondo estético
    img_path = resolver_imagen_origen(keyword, categoria, ruta_imagen)
    if img_path and os.path.exists(img_path):
        try:
            base_img = Image.open(img_path).convert("RGBA")
            base_canvas = recortar_y_centrar(base_img, PIN_WIDTH, PIN_HEIGHT)
        except Exception as e:
            print(f"    [Aviso] Error cargando {img_path}: {e}. Creando fondo de respaldo.")
            base_canvas = Image.new("RGBA", (PIN_WIDTH, PIN_HEIGHT), (20, 24, 33, 255))
    else:
        base_canvas = Image.new("RGBA", (PIN_WIDTH, PIN_HEIGHT), (20, 24, 33, 255))

    # 2. Aplicar capa de gradiente de alto contraste
    gradiente = crear_gradiente_contraste(PIN_WIDTH, PIN_HEIGHT)
    lienzo = Image.alpha_composite(base_canvas, gradiente)
    draw = ImageDraw.Draw(lienzo)

    # 3. Badge de Categoría (Pill superior)
    font_badge = obtener_fuente(24, bold=True)
    cat_text = f"• {categoria.upper().replace('-', ' ')} · GUÍA 2026 •"
    bbox_b = draw.textbbox((0, 0), cat_text, font=font_badge)
    w_b = bbox_b[2] - bbox_b[0]
    h_b = bbox_b[3] - bbox_b[1]

    badge_pad_x = 28
    badge_pad_y = 12
    badge_x0 = (PIN_WIDTH - (w_b + badge_pad_x * 2)) // 2
    badge_y0 = 70
    badge_x1 = badge_x0 + w_b + badge_pad_x * 2
    badge_y1 = badge_y0 + h_b + badge_pad_y * 2

    # Fondo y borde del badge
    draw.rounded_rectangle([badge_x0, badge_y0, badge_x1, badge_y1], radius=20, fill=(13, 148, 136, 230), outline=(45, 212, 191, 255), width=2)
    draw.text((badge_x0 + badge_pad_x, badge_y0 + badge_pad_y - 2), cat_text, font=font_badge, fill=(255, 255, 255))

    # 4. Título Principal
    # Calcular tamaño de fuente según longitud
    longitud = len(keyword)
    font_size_title = 64 if longitud < 32 else (54 if longitud < 50 else 46)
    font_title = obtener_fuente(font_size_title, bold=True)

    titulo_texto = f"¿Merece la pena el {keyword}?" if longitud < 26 else keyword
    lineas_titulo = ajustar_texto(titulo_texto, draw, font_title, max_ancho=860)

    y_cursor = 160
    line_spacing = int(font_size_title * 1.22)
    for linea in lineas_titulo:
        bbox_l = draw.textbbox((0, 0), linea, font=font_title)
        w_l = bbox_l[2] - bbox_l[0]
        x_l = (PIN_WIDTH - w_l) // 2

        # Sombra de alto contraste para destacar sobre cualquier foto
        draw.text((x_l + 3, y_cursor + 3), linea, font=font_title, fill=(0, 0, 0, 230))
        draw.text((x_l, y_cursor), linea, font=font_title, fill=(255, 255, 255, 255))
        y_cursor += line_spacing

    # 5. Subtítulo Destacado
    font_sub = obtener_fuente(32, bold=True)
    sub_text = "Análisis, Pros y Contras · Opiniones 2026"
    bbox_s = draw.textbbox((0, 0), sub_text, font=font_sub)
    w_s = bbox_s[2] - bbox_s[0]
    x_s = (PIN_WIDTH - w_s) // 2

    draw.text((x_s + 2, y_cursor + 18), sub_text, font=font_sub, fill=(0, 0, 0, 200))
    draw.text((x_s, y_cursor + 16), sub_text, font=font_sub, fill=(251, 191, 36, 255))  # Dorado / Ámbar

    # 6. Píldoras de Valor Centrales (Alto Contraste Garantizado)
    font_pills = obtener_fuente(22, bold=True)
    pills = ["Pros y Contras", "Opinión Real", "Mejor Precio"]
    pill_y = y_cursor + 72
    total_pills_w = 0
    pill_widths = []

    for p in pills:
        bb = draw.textbbox((0, 0), p, font=font_pills)
        pw = (bb[2] - bb[0]) + 32
        pill_widths.append(pw)
        total_pills_w += pw

    gap = 14
    total_w_with_gaps = total_pills_w + (len(pills) - 1) * gap
    start_x = (PIN_WIDTH - total_w_with_gaps) // 2

    # Configuración de fondo según estilo ('blanco' o 'oscuro')
    if estilo_pildoras.lower() in ("blanco", "white", "claro", "light"):
        fill_pills = (255, 255, 255, 235)  # Fondo blanco translúcido
    else:
        fill_pills = (15, 23, 42, 225)  # Fondo oscuro

    # Color de texto y borde garantizando contraste estricto
    color_texto_pills, outline_pills = calcular_color_texto_contraste(fill_pills)

    # Renderizado sobre capa overlay para mezcla alfa suave y sin pérdida de calidad
    overlay_pills = Image.new("RGBA", (PIN_WIDTH, PIN_HEIGHT), (0, 0, 0, 0))
    draw_overlay = ImageDraw.Draw(overlay_pills)

    current_px = start_x
    for idx, p in enumerate(pills):
        pw = pill_widths[idx]
        draw_overlay.rounded_rectangle(
            [current_px, pill_y, current_px + pw, pill_y + 44],
            radius=14,
            fill=fill_pills,
            outline=outline_pills,
            width=2,
        )
        current_px += pw + gap

    lienzo = Image.alpha_composite(lienzo, overlay_pills)
    draw = ImageDraw.Draw(lienzo)

    # Dibujar texto con máximo contraste garantizado
    current_px = start_x
    for idx, p in enumerate(pills):
        pw = pill_widths[idx]
        draw.text((current_px + 16, pill_y + 9), p, font=font_pills, fill=color_texto_pills)
        current_px += pw + gap

    # 7. Call To Action (Botón inferior de alta conversión)
    cta_w = 820
    cta_h = 100
    cta_x0 = (PIN_WIDTH - cta_w) // 2
    cta_y0 = 1250
    cta_x1 = cta_x0 + cta_w
    cta_y1 = cta_y0 + cta_h

    # Sombra del botón
    draw.rounded_rectangle([cta_x0 + 4, cta_y0 + 6, cta_x1 + 4, cta_y1 + 6], radius=50, fill=(0, 0, 0, 160))
    # Botón principal en color naranja Amazon / conversión
    draw.rounded_rectangle([cta_x0, cta_y0, cta_x1, cta_y1], radius=50, fill=(255, 153, 0), outline=(255, 184, 77), width=2)

    font_cta = obtener_fuente(34, bold=True)
    cta_texto = "VER PRECIO Y OFERTAS EN AMAZON  >"
    bbox_cta = draw.textbbox((0, 0), cta_texto, font=font_cta)
    w_cta = bbox_cta[2] - bbox_cta[0]
    h_cta = bbox_cta[3] - bbox_cta[1]
    draw.text((cta_x0 + (cta_w - w_cta) // 2, cta_y0 + (cta_h - h_cta) // 2 - 2), cta_texto, font=font_cta, fill=(17, 24, 39))

    # 8. Marca de agua y dominio
    font_brand = obtener_fuente(22, bold=False)
    brand_text = "somos-recomienda.es · Análisis y Guías de Compra 100% Independientes"
    bbox_br = draw.textbbox((0, 0), brand_text, font=font_brand)
    w_br = bbox_br[2] - bbox_br[0]
    draw.text(((PIN_WIDTH - w_br) // 2, 1385), brand_text, font=font_brand, fill=(209, 213, 219, 220))

    # Guardar en JPEG alta calidad (convertir a RGB)
    pin_rgb = lienzo.convert("RGB")
    pin_rgb.save(ruta_salida, "JPEG", quality=95, optimize=True)
    print(f"    [Pinterest OK] Pin generado con éxito: {ruta_salida}")
    return ruta_salida


def procesar_ultimo_articulo(csv_path: str = DEFAULT_CSV, estilo_pildoras: str = "blanco") -> Optional[str]:
    """Lee el CSV y genera el Pin para el último producto añadido."""
    if not os.path.exists(csv_path):
        print(f"[Error Pinterest] CSV '{csv_path}' no encontrado.")
        return None

    filas = []
    with open(csv_path, mode="r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for r in reader:
            if r and r.get("keyword"):
                filas.append(r)

    if not filas:
        print("[Aviso Pinterest] CSV sin filas para procesar.")
        return None

    ultima_fila = filas[-1]
    keyword = ultima_fila.get("keyword", "").strip()
    categoria = ultima_fila.get("categoria", "").strip() or "General"

    print(f"\n[Pinterest Motor] Creando Pin para: '{keyword}' ({categoria})...")
    return crear_pin(keyword=keyword, categoria=categoria, estilo_pildoras=estilo_pildoras)


def main():
    parser = argparse.ArgumentParser(description="Somos Recomienda - Generador de Pines Automáticos para Pinterest (2:3).")
    parser.add_argument("--keyword", type=str, default=None, help="Nombre del producto.")
    parser.add_argument("--categoria", type=str, default=None, help="Categoría del producto.")
    parser.add_argument("--imagen", type=str, default=None, help="Ruta a la imagen de origen.")
    parser.add_argument("--csv", type=str, default=DEFAULT_CSV, help="Ruta al CSV con el último producto.")
    parser.add_argument("--estilo-pildoras", type=str, default="blanco", choices=["blanco", "oscuro", "white", "dark"], help="Estilo visual de las píldoras de valor ('blanco' con texto negro o 'oscuro' con texto blanco).")
    parser.add_argument("--all", action="store_true", help="Generar pines para todos los artículos en src/content/blog/")

    args = parser.parse_args()

    if args.all:
        import glob
        blog_files = glob.glob("src/content/blog/*.md*")
        print(f"[Pinterest] Generando pines para {len(blog_files)} artículos existentes...")
        for f in blog_files:
            try:
                kw, cat = "", "General"
                with open(f, "r", encoding="utf-8") as fp:
                    for line in fp:
                        if line.startswith("keyword:"):
                            kw = line.split(":", 1)[1].strip().strip('"\'')
                        elif line.startswith("category:"):
                            cat = line.split(":", 1)[1].strip().strip('"\'')
                if kw:
                    crear_pin(keyword=kw, categoria=cat, estilo_pildoras=args.estilo_pildoras)
            except Exception as e:
                print(f"Error procesando {f}: {e}")
        return

    if args.keyword:
        cat = args.categoria or "General"
        crear_pin(keyword=args.keyword, categoria=cat, ruta_imagen=args.imagen, estilo_pildoras=args.estilo_pildoras)
    else:
        procesar_ultimo_articulo(csv_path=args.csv, estilo_pildoras=args.estilo_pildoras)


if __name__ == "__main__":
    main()
