# Triaje de requerimientos AEAT — extracción estructurada

Evaluación de `src/triaje.py` (modelo `qwen3b-tfg` vía Ollama) contra el golden set anotado a mano (`eval/golden_triaje.json`), 13 documentos (excluye `req_002.pdf`, reportado aparte como prueba de robustez frente a la maquetación).

## Accuracy por campo (coincidencia exacta)

| Campo | Accuracy |
|---|---:|
| nif | 92.3 % |
| impuesto | 100.0 % |
| ejercicio | 100.0 % |
| periodo | 100.0 % |
| plazo_dias | 100.0 % |
| tipo_documento | 100.0 % |

## Importe

| Caso | n | Accuracy |
|---|---:|---:|
| Esperado null | 4 | 100.0 % |
| Esperado con valor | 9 | 100.0 % |

## Matriz de confusión — tipo_documento

| esperado \ obtenido | acuerdo_inicio_sancionador | propuesta_liquidacion_provisional | requerimiento_documentacion | tramite_audiencia |
|---|---:|---:|---:|---:|
| acuerdo_inicio_sancionador | 2 | 0 | 0 | 0 |
| propuesta_liquidacion_provisional | 0 | 5 | 0 | 0 |
| requerimiento_documentacion | 0 | 0 | 4 | 0 |
| tramite_audiencia | 0 | 0 | 0 | 2 |

## articulos_citados: localizar vs. atribuir

Dos criterios distintos, no uno solo: **estricto** exige ley y número ("LGT art. 203"), y mide localizar la referencia Y atribuirla a la norma correcta a la vez. **Laxo** compara solo el número de artículo, ignorando la ley, y mide únicamente si el modelo localiza la referencia en el texto. La brecha entre ambos aísla los fallos de atribución de norma (ver decisiones.md): un F1 laxo alto con F1 estricto bajo indica que el modelo encuentra los artículos pero los atribuye a la ley equivocada, no que no los encuentre.

| Métrica | Estricto (ley + número) | Laxo (solo número) |
|---|---:|---:|
| Precisión media | 49.2 % | 100.0 % |
| Exhaustividad media | 46.7 % | 94.9 % |
| F1 media | 47.7 % | 96.9 % |

**Tasa de atribución correcta**: de los 39 números de artículo localizados correctamente (aciertos del criterio laxo), **19** llevan además la ley correcta — 48.7 %. Micro-promedio sobre todo el corpus (no media de tasas por documento, con recuentos por documento demasiado pequeños para que esa media sea representativa).

### F1 por documento (estricto vs. laxo) y atribución

| Fichero | F1 estricto | F1 laxo | Atribución correcta |
|---|---:|---:|---:|
| req_001.pdf | 100.0 % | 100.0 % | 100.0 % |
| req_003.pdf | 80.0 % | 80.0 % | 100.0 % |
| req_004.pdf | 0.0 % | 100.0 % | 0.0 % |
| req_005.pdf | 33.3 % | 100.0 % | 33.3 % |
| req_006.pdf | 100.0 % | 100.0 % | 100.0 % |
| req_007.pdf | 33.3 % | 100.0 % | 33.3 % |
| req_008.pdf | 33.3 % | 100.0 % | 33.3 % |
| req_009.pdf | 66.7 % | 100.0 % | 66.7 % |
| req_010.pdf | 33.3 % | 100.0 % | 33.3 % |
| req_011.pdf | 0.0 % | 80.0 % | 0.0 % |
| req_012.pdf | 40.0 % | 100.0 % | 40.0 % |
| req_013.pdf | 100.0 % | 100.0 % | 100.0 % |
| req_014.pdf | 0.0 % | 100.0 % | 0.0 % |

## Cobertura del índice (LGT/LIVA vs. otras normas)

Calculada sobre los artículos del GOLDEN (no sobre lo extraído): mide qué parte de la normativa realmente citada en los requerimientos es fundamentable con el índice actual, con independencia de los aciertos o errores de atribución del extractor.

De 24 artículos únicos citados en el golden set: **18** pertenecen a LGT o LIVA (fundamentables con el índice actual) y **6** a otras normas (LIRPF, RIVA, RGAT) — 75.0 % en índice.

## Validación de esquema, reintentos y latencia

| Métrica | Valor |
|---|---:|
| Válida a la primera | 100.0 % |
| Válida tras reintentos (máx. 2, temperaturas (0.1, 0.4, 0.7)) | 100.0 % |
| Documentos rescatados por variar la temperatura | 0 |
| Latencia media / documento | 9.27 s |

## Calidad de NIF (campo derivado, no invalida el esquema)

`nif_formato_valido` se calcula siempre a partir del NIF extraído, tenga o no dígito de control correcto; un NIF mal formado ya no invalida el documento ni arrastra a los otros ocho campos (ver decisiones.md).

Tasa de NIF con formato/dígito de control válido: 92.3 % (13 documentos evaluados).

## Ablación de maquetación — `req_001.pdf` vs. `req_002.pdf`

Mismo contenido de fondo (mismos 8 campos en el golden), maquetación de PDF distinta. Comparación de la extracción de un fichero contra la del otro, no contra el golden por separado, como prueba de robustez.

| Campo | Esperado | req_001 correcto | req_002 correcto | ¿Coinciden entre sí? |
|---|---|---:|---:|---:|
| nif | B00000018 | ✓ | ✓ | sí |
| impuesto | IVA | ✓ | ✓ | sí |
| ejercicio | 2024 | ✓ | ✓ | sí |
| periodo | 2T | ✓ | ✓ | sí |
| plazo_dias | 10 | ✓ | ✓ | sí |
| tipo_documento | requerimiento_documentacion | ✓ | ✓ | sí |
| importe | — | ✓ | ✓ | sí |
| articulos_citados | LGT art. 136, LGT art. 137, LGT art. 203 | F1=1.00 | F1=1.00 | sí |

