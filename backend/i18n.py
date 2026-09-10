"""
QBASwing MyServer - sistema multilingue centralizado.

Carga los diccionarios de traduccion desde translations/*.json y expone
una funcion t(key, lang) para backend, ademas de servir el diccionario
completo al frontend (frontend/static/js/i18n.js lo aplica a toda la UI).
"""
import json
import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TRANSLATIONS_DIR = os.path.join(BASE_DIR, "translations")

SUPPORTED_LANGUAGES = ["es", "en", "fr", "de", "pt", "it"]
DEFAULT_LANGUAGE = "es"

_cache = {}


def _load(lang):
    if lang in _cache:
        return _cache[lang]
    path = os.path.join(TRANSLATIONS_DIR, f"{lang}.json")
    if not os.path.isfile(path):
        return {}
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    _cache[lang] = data
    return data


def get_dict(lang):
    """Devuelve el diccionario completo de un idioma, con 'es' como
    respaldo para claves faltantes (para que nunca aparezca una clave
    cruda en la interfaz si una traduccion aun no existe)."""
    lang = lang if lang in SUPPORTED_LANGUAGES else DEFAULT_LANGUAGE
    base = dict(_load(DEFAULT_LANGUAGE))
    base.update(_load(lang))
    return base


def t(key, lang=DEFAULT_LANGUAGE, **kwargs):
    value = get_dict(lang).get(key, key)
    if kwargs:
        try:
            return value.format(**kwargs)
        except (KeyError, IndexError):
            return value
    return value


def language_options():
    return [
        {"code": "es", "label": "Español", "flag": "🇪🇸"},
        {"code": "en", "label": "English", "flag": "🇺🇸"},
        {"code": "fr", "label": "Français", "flag": "🇫🇷"},
        {"code": "de", "label": "Deutsch", "flag": "🇩🇪"},
        {"code": "pt", "label": "Português", "flag": "🇵🇹"},
        {"code": "it", "label": "Italiano", "flag": "🇮🇹"},
    ]
