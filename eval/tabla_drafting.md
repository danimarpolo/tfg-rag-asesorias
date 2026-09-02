# Generación del borrador (drafting) — evaluación automática

Evaluación de `src/cadena.py` (modelo `qwen3b-tfg` vía Ollama) sobre 13 documentos (excluye `req_002.pdf`, igual que `evaluar_triaje.py`). Métricas exclusivamente automáticas y verificables: ninguna mide calidad subjetiva de la redacción.

## Fundamentación y alucinación normativa

La tasa de alucinación —artículos citados en el borrador que no proceden ni de un fragmento recuperado ni de la lista de referencias no fundamentables— es la métrica más importante de este informe: debería ser 0.

| Métrica | Valor |
|---|---:|
| Citas normativas totales en los borradores | 59 |
| Fundamentadas (proceden de un fragmento recuperado) | 54 (91.5 %) |
| Alucinadas (ni recuperadas ni reconocidas como no disponibles) | 2 (3.4 %) |

## Elementos estructurales presentes

| Sección | Presente en |
|---|---:|
| Encabezamiento | 100.0 % |
| Exposición de hechos | 100.0 % |
| Fundamentos de derecho | 100.0 % |
| Solicitud | 92.3 % |

## Longitud y latencia

| Métrica | Valor |
|---|---:|
| Longitud media del borrador | 585.6 palabras |
| Latencia media — triaje | 9.27 s |
| Latencia media — recuperación | 0.23 s |
| Latencia media — generación | 33.73 s |
| Latencia media — total | 43.23 s |

## Detalle por documento

| Fichero | Citas | Fundamentación | Alucinación | Estructura completa | Palabras |
|---|---:|---:|---:|---:|---:|
| req_001.pdf | 4 | 100.0 % | 0.0 % | si | 451 |
| req_003.pdf | 4 | 100.0 % | 0.0 % | si | 388 |
| req_004.pdf | 3 | 100.0 % | 0.0 % | si | 1129 |
| req_005.pdf | 5 | 80.0 % | 20.0 % | si | 441 |
| req_006.pdf | 6 | 100.0 % | 0.0 % | si | 492 |
| req_007.pdf | 5 | 100.0 % | 0.0 % | si | 501 |
| req_008.pdf | 5 | 100.0 % | 0.0 % | si | 392 |
| req_009.pdf | 0 | n/a | 0.0 % | si | 72 |
| req_010.pdf | 5 | 100.0 % | 0.0 % | si | 450 |
| req_011.pdf | 8 | 100.0 % | 0.0 % | si | 1202 |
| req_012.pdf | 5 | 20.0 % | 20.0 % | no | 1144 |
| req_013.pdf | 4 | 100.0 % | 0.0 % | si | 355 |
| req_014.pdf | 5 | 100.0 % | 0.0 % | si | 596 |

