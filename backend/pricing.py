"""
QBASwing MyServer - calculo de precios con redondeo comercial
"""

GB = 1024 ** 3


def apply_rounding(value, mode):
    """Redondea 'value' segun el modo: 'none', 'round5' o 'round10'.

    Ejemplos con round5:  157 -> 155? No: se redondea al multiplo de 5 mas
    cercano (157 -> 155, 158 -> 160). Con round10: 157 -> 160, 163 -> 160... pero
    la especificacion pide 157->160, 163->165, 178->180, 201->205, es decir
    redondeo SIEMPRE HACIA ARRIBA (ceil) al multiplo indicado, no al mas cercano.
    """
    if mode == "round5":
        step = 5
    elif mode == "round10":
        step = 10
    else:
        return value

    if value <= 0:
        return 0
    remainder = value % step
    if remainder == 0:
        return value
    return value - remainder + step


def compute_price(size_bytes, price_per_gb, rounding_mode):
    """Devuelve (size_gb redondeado a 3 decimales, precio final sin decimales si hay redondeo)."""
    size_gb = size_bytes / GB
    raw_price = size_gb * price_per_gb
    if rounding_mode in ("round5", "round10"):
        final_price = apply_rounding(round(raw_price), rounding_mode)
    else:
        final_price = round(raw_price, 2)
    return round(size_gb, 3), final_price
