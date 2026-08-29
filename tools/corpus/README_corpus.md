# Corpus sintético de requerimientos AEAT — evaluación del triaje

14 documentos PDF ficticios que imitan el formato de las notificaciones de la
Agencia Tributaria, con su anotación de referencia en `eval/golden_triaje.json`.

## Ubicación en el repositorio

```
poc-rag-aeat/
├── eval/
│   ├── golden_set.json          # evaluación del recuperador (ya existente)
│   ├── golden_triaje.json       # anotación de este corpus
│   └── corpus_triaje/           # los 14 PDF — se versionan (72 KB en total)
│       ├── req_001.pdf … req_014.pdf
└── tools/
    └── corpus/                  # generador; no forma parte del MVP
        ├── corpus_spec.py
        ├── build_corpus.py
        ├── verify_corpus.py
        └── README_corpus.md
```

Los scripts resuelven sus rutas contra la raíz del repositorio a partir de
`__file__`, así que funcionan se lancen desde donde se lancen.

## Reproducibilidad

```powershell
# Desde la raíz del repositorio
pip install reportlab pdfplumber

python tools\corpus\build_corpus.py     # regenera los 14 PDF y el golden
python tools\corpus\verify_corpus.py    # extrae el texto y lo contrasta con el golden
```

`corpus_spec.py` es la **fuente única de verdad**: tanto el PDF como su anotación
se derivan de la misma estructura, de modo que no pueden divergir. Para ampliar
el corpus basta añadir entradas a `DOCS`.

Los PDF se versionan pese a ser generados: sin ellos el golden no significa
nada y la evaluación deja de ser reproducible por un tercero. Ocupan 72 KB.

## Reparto por tipo

| tipo_documento | n | ficheros |
|---|---:|---|
| `requerimiento_documentacion` | 4 | req_001 – req_004 |
| `propuesta_liquidacion_provisional` | 3 | req_005 – req_007 |
| `requerimiento_iva_no_deducible` | 3 | req_008 – req_010 |
| `tramite_audiencia` | 2 | req_011, req_012 |
| `acuerdo_inicio_sancionador` | 2 | req_013, req_014 |

Reparto por impuesto: 8 IVA / 6 IRPF. Por plazo: 9 de 10 días / 5 de 15 días.
Por importe: 9 con cantidad exigida / 5 sin ella.

## Casos difíciles

| # | Dificultad | Fichero |
|---|---|---|
| 1 | Plazo relativo (`10 días hábiles contados a partir del siguiente a la notificación`), sin fecha límite | `req_003` |
| 2 | Dos NIF: obligado tributario y representante | `req_006` |
| 3 | Cinco artículos mezclando ley y reglamento (LGT, RGAT, LIVA ×2, RIVA) | `req_012` |
| 4 | Sin importe reclamado, con tres cifras en euros como distractores | `req_010` |
| 5a | Datos clave en tabla de cabecera | `req_001` |
| 5b | Los **mismos** datos embebidos en el cuerpo del texto | `req_002` |

`req_001` y `req_002` forman un **par de ablación**: comparten los nueve campos
del golden y difieren únicamente en la maquetación. Cualquier diferencia de
extracción entre ambos es atribuible al formato, no al contenido.

Dificultades secundarias no solicitadas, pero presentes:

- `req_002`, `req_010` y `req_014` llevan los datos en el cuerpo, para que el
  formato de tabla no sea trivialmente predictivo.
- `req_002` escribe el período como «segundo trimestre», sin el código `2T`.
- `req_014` nombra el impuesto solo por su denominación desarrollada, sin la
  sigla `IRPF`.
- `req_009` es un IVA con período **anual** (`0A`, discrepancia 303 / 390): el
  extractor no puede asumir que IVA implica trimestre.
- Todos los documentos sin importe contienen cifras en euros con formato de
  cantidad.

## Convenciones de anotación

- **`periodo`** — código AEAT: `1T`…`4T` para períodos trimestrales, `0A` para
  el anual. Se anota el período real aunque el documento lo exprese en letra.
- **`impuesto`** — sigla normalizada (`IVA`, `IRPF`) aunque el documento use
  solo la denominación desarrollada.
- **`ejercicio`** — entero.
- **`importe`** — número en euros que el documento **exige o propone ingresar**
  (deuda, cuota a ingresar o sanción). *No* es cualquier cifra en euros: las
  bases imponibles, cuotas soportadas y diferencias detectadas son distractores
  deliberados. `null` cuando el documento no exige cantidad alguna.
- **`nif`** — el del **obligado tributario**. En `req_006` el NIF del
  representante aparece en el documento pero **no** es la respuesta correcta.
- **`articulos_citados`** — normalizados a nivel de artículo, sin apartado, en
  formato `"<NORMA> art. <N>"` y en el orden en que aparecen. Normas usadas:
  `LGT`, `LIVA`, `LIRPF`, `RGAT` (RD 1065/2007), `RIVA` (RD 1624/1992).
- **`plazo_dias`** — entero de días concedido, también cuando el documento no
  ancla el plazo a una fecha concreta (`req_003`). El matiz *hábiles* frente a
  *naturales* queda fuera del esquema; todos los documentos usan días hábiles.

## Naturaleza sintética de los documentos

Los documentos son ficticios y lo declaran en cabecera y pie de cada página.
Nombres, NIF, direcciones, referencias y CSV son inventados; la sede electrónica
que figura es un dominio de prueba. Los NIF y CIF llevan letra o dígito de
control **formalmente válido** (módulo 23 y algoritmo del NIF de persona
jurídica, respectivamente) para no romper una validación aguas abajo, pero sus
dígitos siguen patrones evidentemente artificiales.

No se ha usado ninguna notificación real, ni siquiera anonimizada: evita el
tratamiento de datos personales de contribuyentes reales y permite publicar el
corpus como anexo de la memoria.

## Comprobaciones automáticas

`verify_corpus.py` valida, documento a documento: extraibilidad del texto,
ausencia de glifos perdidos, validez del dígito de control del NIF, presencia
del NIF anotado, del ejercicio, del período en alguna forma de superficie y del
número de días de plazo; aparición literal de la cita normativa completa;
coherencia del importe (o declaración expresa de que no se exige cantidad);
y **coherencia aritmética interna** — que el desglose sume el total, que la
sanción sea el porcentaje de su base y que la paralela varíe exactamente en la
cuota propuesta. Sobre el conjunto valida el reparto por tipo, la unicidad de
ficheros y la presencia de los cinco casos difíciles.
