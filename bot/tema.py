"""Colores de Voxia (app y overlay). Se elige en la app, abajo a la izquierda."""

# nombre: (acento, hover, texto sobre el acento, versión fuerte, versión clara)
COLORES = {
    "Naranjo":  ("#FF7A1A", "#FF9142", "#1A1208", "#D9600A", "#FFB37A"),
    "Lima":     ("#A3E635", "#B8F05A", "#141A08", "#5E9E10", "#D2F59A"),
    "Cian":     ("#22D3EE", "#5CE1F3", "#06191D", "#0891B2", "#A5F0FA"),
    "Rojo":     ("#FF4655", "#FF6B77", "#FFFFFF", "#D62F3E", "#FFA3AA"),
    "Rosa":     ("#FF4D8D", "#FF73A6", "#FFFFFF", "#E0306F", "#FFA8C8"),
    "Dorado":   ("#FFC531", "#FFD465", "#1C1505", "#C99400", "#FFE39C"),
    "Morado":   ("#9146FF", "#A66BFF", "#FFFFFF", "#772CE8", "#C4A3FF"),
}
POR_DEFECTO = "Naranjo"


def colores(nombre: str) -> tuple:
    return COLORES.get(nombre, COLORES[POR_DEFECTO])
