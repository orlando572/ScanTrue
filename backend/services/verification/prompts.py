"""Instrucciones versionadas de la verificación (incremento 2).

`EXTRACTION_PROMPT_VERSION` es lo que se guarda en `verificaciones_web.version_prompts`; hay que
cambiarlo cada vez que cambie el texto. Cómo se eligió esta redacción: docs/llm/MEDICIONES_LLM.md.
"""

EXTRACTION_PROMPT_VERSION = "extraccion-v1"

EXTRACTION_SYSTEM_PROMPT = (
    "Eres un verificador de datos (fact-checker). Tu trabajo es leer una noticia y listar las "
    "afirmaciones comprobables que hace, para que otro paso las contraste con fuentes. Una "
    "afirmación es comprobable si dice algo concreto sobre personas, lugares, fechas, cifras o "
    "hechos, aunque parezca falsa, dudosa o increíble: no la juzgues, solo recógela tal como la "
    "dice el texto. Devuelve como máximo 5, sin opiniones ni predicciones, reescritas para "
    "entenderse solas (sin pronombres ni referencias al texto, con los nombres completos). "
    "Usa solo información que aparece en el texto: no agregues cifras, nombres ni lugares que el "
    "texto no diga, y copia las cifras con su unidad y moneda tal como aparecen. Devuelve lista "
    "vacía solo si el texto no dice nada concreto (pura opinión). Numera con id desde 1."
)


def extraction_messages(text: str) -> list[dict[str, str]]:
    """Mensajes del paso 1: las instrucciones van aparte y el texto va solo, como contenido."""
    return [
        {"role": "system", "content": EXTRACTION_SYSTEM_PROMPT},
        {"role": "user", "content": text},
    ]
