#!/usr/bin/env python3
"""
triaje.py
=========
Extracción estructurada de los datos de un requerimiento de la AEAT (PDF) con
un LLM local servido por Ollama, y validación de la salida con Pydantic.

El texto se extrae con pypdf (sin OCR: los PDF del corpus tienen capa de
texto). El modelo recibe el texto completo y debe devolver un único objeto
JSON con los nueve campos del golden set. La respuesta se valida contra
RequerimientoAEAT; si no valida (JSON mal formado o campo que no cumple el
esquema), se reintenta hasta config.TRIAJE_MAX_REINTENTOS veces con el mismo
prompt.

Uso
---
    python src/triaje.py eval/corpus_triaje/req_001.pdf
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
import unicodedata
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional

import requests
from pydantic import BaseModel, ValidationError, field_validator, model_validator
from pypdf import PdfReader

import config


# ---------------------------------------------------------------------------
# Esquema
# ---------------------------------------------------------------------------

class TipoDocumento(str, Enum):
    """Conjunto cerrado de tipos de documento presentes en el corpus."""
    REQUERIMIENTO_DOCUMENTACION = "requerimiento_documentacion"
    PROPUESTA_LIQUIDACION_PROVISIONAL = "propuesta_liquidacion_provisional"
    REQUERIMIENTO_IVA_NO_DEDUCIBLE = "requerimiento_iva_no_deducible"
    TRAMITE_AUDIENCIA = "tramite_audiencia"
    ACUERDO_INICIO_SANCIONADOR = "acuerdo_inicio_sancionador"


class Impuesto(str, Enum):
    IVA = "IVA"
    IRPF = "IRPF"


_RE_PERIODO = re.compile(r"^(?:[1-4]T|0A)$")

# Algoritmo de validación de NIF/CIF español (persona física y entidad).
_LETRAS_NIF_PERSONA = "TRWAGMYFPDXBNJZSQVHLCKE"
_RE_NIF_PERSONA = re.compile(r"^(\d{8})([A-Z])$")
_RE_NIF_ENTIDAD = re.compile(r"^([ABCDEFGHJNPQRSUVW])(\d{7})([0-9A-J])$")
_LETRAS_CIF_CONTROL = "JABCDEFGHI"
_CIF_LETRA_OBLIGATORIA = set("KPQS")
_CIF_DIGITO_OBLIGATORIO = set("ABEH")


def _control_nif_persona(numero: str) -> str:
    return _LETRAS_NIF_PERSONA[int(numero) % 23]


def _controles_validos_cif(letra_inicial: str, numero: str) -> set[str]:
    """
    Dígito/letra de control válidos para un CIF de entidad.

    Algoritmo estándar: suma de las cifras en posición par + suma de dígitos
    del doble de las cifras en posición impar; el dígito de control es
    (10 - suma mod 10) mod 10. Según la letra inicial, el carácter de control
    exigido es una letra, un dígito, o cualquiera de los dos (ambigüedad
    real y documentada del CIF español).
    """
    pares = sum(int(numero[i]) for i in (1, 3, 5))
    impares = 0
    for i in (0, 2, 4, 6):
        doblado = int(numero[i]) * 2
        impares += doblado // 10 + doblado % 10
    digito = (10 - (pares + impares) % 10) % 10
    letra = _LETRAS_CIF_CONTROL[digito]
    if letra_inicial in _CIF_LETRA_OBLIGATORIA:
        return {letra}
    if letra_inicial in _CIF_DIGITO_OBLIGATORIO:
        return {str(digito)}
    return {str(digito), letra}


def normaliza_nif_texto(valor: str) -> str:
    """Normalización puramente sintáctica (mayúsculas, sin espacios/guiones)."""
    return valor.strip().upper().replace(" ", "").replace("-", "")


def nif_formato_valido(v: str) -> bool:
    """
    True si v (ya normalizado con normaliza_nif_texto) es un NIF de persona
    física o un CIF de entidad con dígito/letra de control correcto.

    Deliberadamente NO lanza excepción: es una comprobación de CALIDAD del
    dato, no de tipo. Un NIF mal formado no es un fallo de "no puedo
    interpretar esta respuesta como un RequerimientoAEAT", es un fallo de
    "el obligado tributario no existe", y no debe invalidar los otros ocho
    campos, que pueden ser perfectamente correctos.
    """
    m = _RE_NIF_PERSONA.match(v)
    if m:
        numero, letra = m.groups()
        return letra == _control_nif_persona(numero)

    m = _RE_NIF_ENTIDAD.match(v)
    if m:
        letra_inicial, numero, control = m.groups()
        return control in _controles_validos_cif(letra_inicial, numero)

    return False


def normaliza_periodo_texto(v) -> str:
    """
    Normaliza y valida la sintaxis de "periodo" ('1T'..'4T' o '0A').

    A diferencia de nif_formato_valido, aquí una sintaxis incorrecta SÍ debe
    invalidar el esquema: a diferencia del NIF, no existe un concepto de
    "periodo con formato inválido pero dato aprovechable" — un valor que no
    es trimestre ni anual no es un período AEAT en absoluto.
    """
    p = str(v).strip().upper()
    if not _RE_PERIODO.match(p):
        raise ValueError(f"periodo '{v}' no es '1T'..'4T' ni '0A'")
    return p


def coerce_importe(v):
    """
    Coacciona "importe" a float, aceptando el formato español habitual del
    modelo: punto de millar, coma decimal ("1.847,63"). Lanza ValueError si
    no es interpretable como número; se expone como función de módulo (no
    solo como validador Pydantic) para que evaluar_triaje.py pueda reutilizar
    exactamente esta misma regla de coerción sobre JSON crudo que no llegó a
    validar como RequerimientoAEAT completo.
    """
    if v is None or isinstance(v, (int, float)):
        return v
    s = str(v).strip().replace("€", "").replace(" ", "")
    if not s:
        return None
    if "," in s:
        s = s.replace(".", "").replace(",", ".")
    return float(s)  # ValueError si no es numérico: se propaga tal cual


class RequerimientoAEAT(BaseModel):
    """
    Datos estructurados de un requerimiento de la AEAT.

    Los ocho campos de contenido del golden set (eval/golden_triaje.json). El
    noveno campo del golden, "fichero", identifica el PDF de origen y no se le
    pide al modelo: lo añade el pipeline de triaje a partir del nombre real
    del fichero procesado.

    nif_formato_valido no se le pide al modelo: es un campo derivado, siempre
    recalculado en el validador posterior a partir de "nif". Un NIF con
    formato o dígito de control incorrecto NO invalida el documento (ver
    nif_formato_valido()); es una señal de calidad, no un fallo de esquema.
    """
    tipo_documento: TipoDocumento
    nif: str
    nif_formato_valido: bool = False
    impuesto: Impuesto
    ejercicio: int
    periodo: str
    articulos_citados: list[str] = []
    importe: Optional[float] = None
    plazo_dias: int

    @field_validator("nif", mode="before")
    @classmethod
    def _normaliza_nif(cls, v):
        if not isinstance(v, str):
            raise ValueError(f"nif debe ser una cadena, se recibió {type(v).__name__}")
        return normaliza_nif_texto(v)

    @model_validator(mode="after")
    def _marca_nif_formato_valido(self):
        self.nif_formato_valido = nif_formato_valido(self.nif)
        return self

    @field_validator("periodo", mode="before")
    @classmethod
    def _check_periodo(cls, v):
        return normaliza_periodo_texto(v)

    @field_validator("ejercicio")
    @classmethod
    def _check_ejercicio(cls, v):
        if not (config.TRIAJE_EJERCICIO_MIN <= v <= config.TRIAJE_EJERCICIO_MAX):
            raise ValueError(
                f"ejercicio {v} fuera de rango razonable "
                f"[{config.TRIAJE_EJERCICIO_MIN}, {config.TRIAJE_EJERCICIO_MAX}]"
            )
        return v

    @field_validator("plazo_dias")
    @classmethod
    def _check_plazo_dias(cls, v):
        if not (0 < v <= 60):
            raise ValueError(f"plazo_dias {v} fuera de rango razonable (1-60)")
        return v

    @field_validator("importe", mode="before")
    @classmethod
    def _coerce_importe(cls, v):
        # El modelo a veces devuelve el importe como cadena, a menudo en
        # formato español (punto de millar, coma decimal): "1.847,63".
        try:
            return coerce_importe(v)
        except ValueError:
            raise ValueError(f"importe '{v}' no es un número válido")

    @field_validator("articulos_citados", mode="before")
    @classmethod
    def _check_articulos(cls, v):
        if v is None:
            return []
        if not isinstance(v, list):
            raise ValueError("articulos_citados debe ser una lista de cadenas")
        return [str(a).strip() for a in v if str(a).strip()]


@dataclass
class ResultadoTriaje:
    """Resultado de intentar extraer un documento, con la telemetría del proceso."""
    fichero: str
    datos: Optional[RequerimientoAEAT]
    valido: bool
    intentos_usados: int
    latencia_s: float
    error: Optional[str] = None
    # Último JSON parseado con éxito (haya validado o no el esquema completo).
    # Permite comparar campo a campo incluso los documentos en los que
    # RequerimientoAEAT no llegó a validar en ningún intento.
    crudo: Optional[dict] = None
    # Temperatura de muestreo con la que se obtuvo la respuesta final.
    temperatura_usada: Optional[float] = None


# ---------------------------------------------------------------------------
# Prompt
# ---------------------------------------------------------------------------

_EJEMPLO_SALIDA = {
    "tipo_documento": "requerimiento_documentacion",
    "nif": "B12345674",
    "impuesto": "IVA",
    "ejercicio": 2024,
    "periodo": "2T",
    "articulos_citados": ["LGT art. 136", "LGT art. 137", "LGT art. 203"],
    "importe": None,
    "plazo_dias": 10,
}

_PROMPT = """Eres un asistente que extrae datos estructurados de requerimientos \
de la Agencia Tributaria (AEAT) española.

Lee el documento y devuelve ÚNICAMENTE un objeto JSON con estos campos:

- tipo_documento: uno de estos valores exactos (sin más opciones):
  "requerimiento_documentacion", "propuesta_liquidacion_provisional",
  "requerimiento_iva_no_deducible", "tramite_audiencia",
  "acuerdo_inicio_sancionador".
- nif: el NIF o CIF del obligado tributario, en mayúsculas y sin espacios.
- impuesto: "IVA" o "IRPF".
- ejercicio: el ejercicio fiscal, como número entero (ej. 2024).
- periodo: el período dentro del ejercicio: "1T", "2T", "3T", "4T"
  (trimestre) o "0A" (anual).
- articulos_citados: lista de los artículos legales citados, en forma
  abreviada "LEY art. N" (ej. "LGT art. 136", "LIVA art. 99"). Usa las
  siglas LGT, LIVA, LIRPF, RIVA o RGAT según la ley o reglamento citado.
  Una entrada por artículo, aunque el documento los cite juntos.
- importe: el importe total a ingresar o la sanción propuesta, como número
  con punto decimal (sin separador de miles). Si el documento no liquida ni
  propone ningún importe, usa null.
- plazo_dias: el plazo en días hábiles para atender el requerimiento o
  presentar alegaciones, como número entero.

Ejemplo de salida válida:
{ejemplo}

Devuelve solo el JSON, sin explicaciones ni texto adicional.

DOCUMENTO:
\"\"\"
{documento}
\"\"\"
"""


def _construye_prompt(texto: str) -> str:
    return _PROMPT.format(
        ejemplo=json.dumps(_EJEMPLO_SALIDA, ensure_ascii=False, indent=2),
        documento=texto,
    )


# ---------------------------------------------------------------------------
# Extracción
# ---------------------------------------------------------------------------

def extrae_texto_pdf(ruta: Path) -> str:
    """Extrae el texto de todas las páginas de un PDF con capa de texto."""
    reader = PdfReader(str(ruta))
    return "".join(p.extract_text() or "" for p in reader.pages)


def _llama_ollama(prompt: str, temperatura: float) -> str:
    resp = requests.post(
        config.OLLAMA_URL,
        json={
            "model": config.OLLAMA_MODEL,
            "prompt": prompt,
            "format": "json",
            "stream": False,
            "options": {"temperature": temperatura},
        },
        timeout=config.OLLAMA_TIMEOUT,
    )
    resp.raise_for_status()
    return resp.json()["response"]


def _temperatura_intento(intento: int) -> float:
    temps = config.TRIAJE_TEMPERATURAS
    return temps[min(intento, len(temps)) - 1]


def extrae_requerimiento(texto: str, fichero: str = "") -> ResultadoTriaje:
    """
    Extrae los datos estructurados de un requerimiento a partir de su texto.

    Reintenta hasta config.TRIAJE_MAX_REINTENTOS veces si la respuesta del
    modelo no valida contra RequerimientoAEAT (JSON mal formado o campo que
    incumple el esquema). intentos_usados registra cuántas llamadas al modelo
    hicieron falta.

    La temperatura escala entre intentos (config.TRIAJE_TEMPERATURAS): a
    temperatura fija el modelo es determinista y repite exactamente la misma
    respuesta, así que un reintento con la misma temperatura nunca cambia el
    resultado. Variarla le da al reintento una oportunidad real de obtener
    una respuesta distinta.
    """
    prompt = _construye_prompt(texto)
    max_intentos = config.TRIAJE_MAX_REINTENTOS + 1
    inicio = time.perf_counter()
    ultimo_error: Optional[str] = None
    ultimo_crudo: Optional[dict] = None

    for intento in range(1, max_intentos + 1):
        temperatura = _temperatura_intento(intento)
        try:
            bruto = _llama_ollama(prompt, temperatura)
            crudo = json.loads(bruto)
            if isinstance(crudo, dict):
                ultimo_crudo = crudo
            datos = RequerimientoAEAT.model_validate(crudo)
            return ResultadoTriaje(
                fichero=fichero,
                datos=datos,
                valido=True,
                intentos_usados=intento,
                latencia_s=time.perf_counter() - inicio,
                crudo=crudo,
                temperatura_usada=temperatura,
            )
        except json.JSONDecodeError as e:
            ultimo_error = f"JSON mal formado (intento {intento}, T={temperatura}): {e}"
        except ValidationError as e:
            ultimo_error = f"No valida contra el esquema (intento {intento}, T={temperatura}): {e}"
        except requests.RequestException as e:
            ultimo_error = f"Error de conexión con Ollama ({config.OLLAMA_URL}): {e}"

    return ResultadoTriaje(
        fichero=fichero,
        datos=None,
        valido=False,
        intentos_usados=max_intentos,
        latencia_s=time.perf_counter() - inicio,
        error=ultimo_error,
        crudo=ultimo_crudo,
        temperatura_usada=_temperatura_intento(max_intentos),
    )


def extrae_documento(ruta: Path) -> ResultadoTriaje:
    """Extrae texto de un PDF y ejecuta la extracción estructurada sobre él."""
    texto = extrae_texto_pdf(ruta)
    return extrae_requerimiento(texto, fichero=ruta.name)


# ---------------------------------------------------------------------------
# CLI de prueba manual (un único documento)
# ---------------------------------------------------------------------------

def main() -> int:
    p = argparse.ArgumentParser(description="Triaje de un requerimiento AEAT (PDF)")
    p.add_argument("pdf", type=Path, help="Ruta al PDF del requerimiento")
    args = p.parse_args()

    if not args.pdf.exists():
        print(f"[ERROR] No existe el fichero: {args.pdf}")
        return 1

    print(f"Extrayendo {args.pdf.name} vía {config.OLLAMA_MODEL} @ {config.OLLAMA_URL} ...")
    resultado = extrae_documento(args.pdf)

    print(f"\nválido           : {resultado.valido}")
    print(f"intentos_usados  : {resultado.intentos_usados}")
    print(f"temperatura_usada: {resultado.temperatura_usada}")
    print(f"latencia_s       : {resultado.latencia_s:.2f}")
    if resultado.datos:
        print("\ndatos extraídos:")
        print(json.dumps(resultado.datos.model_dump(mode="json"),
                          ensure_ascii=False, indent=2))
    else:
        print(f"\nerror: {resultado.error}")

    return 0 if resultado.valido else 1


if __name__ == "__main__":
    sys.exit(main())
