# Ablación de la estrategia de troceado: artículo vs. longitud fija

Contraste del apartado 3.3.3 de la memoria. Una sola variable frente a la
configuración base ya medida (`eval/resultados_0_base.json`): la estrategia de
troceado (`CHUNK_STRATEGY` en `src/config.py`). Todo lo demás idéntico —
modelo `multilingual-e5-base`, chunk=1800, overlap=200, mismo golden set de 15
preguntas, mismos prefijos E5.

## Tabla de resultados

| Estrategia | Recall@1 | Recall@3 | Recall@5 | Recall@10 | MRR | Cobertura | Ingesta | Fragmentos | Frag. >1 artículo |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Artículo (base) | **80,0 %** | 86,7 % | 93,3 % | 93,3 % | **0,8467** | 93,3 % | 903 s | 984 | 0 (0,0 %) |
| Longitud fija | 26,7 % | 80,0 % | 86,7 % | **100,0 %** | 0,5345 | **100,0 %** | 791 s | 793 | 402 (50,7 %) |

Fragmentos por ley — artículo: LGT 529 / LIVA 455. Longitud fija: LGT 415 /
LIVA 378. Longitud fija genera además 45 fragmentos (5,7 %) sin ningún
artículo asociado: texto anterior al primer encabezado (exposición de
motivos), que la estrategia por artículo no indexa como unidad propia.

> Nota: el tiempo de ingesta, igual que en `tabla_comparativa_prototipo1.md`,
> se midió en un equipo de desarrollo sin control de carga y es orientativo.

## Posición del primer acierto, pregunta a pregunta

| # | Artículo esperado | Artículo (base) | Longitud fija |
|---:|---|---:|---:|
| 1 | LGT art. 66 — prescripción | 1 | 7 |
| 2 | LGT art. 223 — recurso de reposición | 2 | 2 |
| 3 | LGT art. 235 — reclamación econ.-adm. | 5 | 8 |
| 4 | LGT art. 62 — plazos de pago | 1 | 3 |
| 5 | LGT art. 27 — recargos extemporáneos | 1 | 1 |
| 6 | LGT art. 112 — notificación comparecencia | 1 | 4 |
| 7 | LGT art. 93/94 — deber de información | 1 | 1 |
| 8 | LGT art. 136-138 — comprobación limitada | 1 | 1 |
| 9 | LGT art. 150 — plazo de inspección | 1 | 1 |
| 10 | LGT art. 188 — reducción de sanciones | 1 | 2 |
| 11 | LGT art. 95 — datos reservados | 1 | 2 |
| 12 | LIVA art. 75 — devengo | 1 | 3 |
| 13 | LIVA art. 97 — requisitos de deducción | 1 | 2 |
| 14 | LIVA art. 84 — inversión sujeto pasivo | ✗ | 3 |
| 15 | LIVA art. 102-104 — prorrata | 1 | 2 |

Cuatro preguntas mantienen la posición 1 en ambas estrategias. Las once
restantes empeoran con longitud fija — ninguna mejora su posición exacta,
salvo el caso límite de la pregunta 14, que pasa de no recuperarse nunca a
la posición 3.

## Hallazgos

**1. El troceado por artículo gana con claridad en las métricas que importan
para generación (Recall@1, MRR).** Recall@1 cae 53,3 puntos (80,0 % → 26,7 %)
y MRR cae de 0,8467 a 0,5345 (-37 %). Si el sistema inyecta en el prompt de
generación solo el primer resultado o los tres primeros, la estrategia por
artículo entrega el artículo correcto de forma mucho más fiable.

**2. Recall@10 y cobertura mejoran precisamente porque dejan de ser
discriminativos.** Ambos llegan al 100 % con longitud fija, superando incluso
a la configuración base. Esto no es una ventaja real de la estrategia: con
fragmentos más grandes y solapados, es más fácil que ALGÚN fragmento entre
los 10 primeros contenga el artículo correcto, aunque no sea el fragmento que
mejor lo representa. Es la misma lección ya registrada para Recall@5 en el
sondeo de modelo/chunk (`decisiones.md`, 2026-08-27): un recall con k grande
no sirve como criterio de decisión en este corpus.

**3. El dato que explica el resultado: el 50,7 % de los fragmentos de
longitud fija solapan más de un artículo (402 de 793).** Al dividir el texto
sin respetar las fronteras del articulado, cada fragmento mezcla el final de
un artículo con el principio del siguiente (o de dos o tres siguientes, como
en los artículos 1-7 de la LGT, muy breves). El embedding resultante
representa una mezcla, no un artículo, así que los artículos vecinos entran
a competir por las primeras posiciones del ranking. El caso del art. 66 LGT
(pregunta 1) lo ilustra directamente: antes de recuperarlo a él mismo en la
posición 7, el sistema devuelve el 66 bis, el 67 y los artículos 127-129
(todos sobre plazos de prescripción relacionados) — contenido relevante, pero
disperso, en lugar de concentrado en el primer puesto.

**4. Efecto secundario positivo: se recupera el fallo sistemático de LIVA
art. 84.** La pregunta sobre inversión del sujeto pasivo, que no se recuperaba
en NINGUNA de las cinco configuraciones del sondeo anterior (desajuste de
vocabulario doctrinal/legal, ver decisiones.md 2026-08-27), sí aparece aquí en
posición 3. La explicación más plausible es que el fragmento de longitud fija
que contiene el art. 84 arrastra también texto del art. 83 ("Sujeto pasivo"),
lo que amplía el vocabulario del fragmento y mejora su solapamiento léxico con
la consulta. Es un efecto real, pero puntual: no compensa la pérdida de
precisión en las otras 14 preguntas, y no es controlable (depende de qué
artículo quede adyacente por azar de la ventana de longitud fija).

**5. Longitud fija no es más barata.** Genera un 19 % menos de fragmentos
(793 frente a 984) y tarda un 12 % menos en ingerir (791 s frente a 903 s),
pero la diferencia es pequeña y no compensa ni de lejos la pérdida de Recall@1
y MRR. No hay argumento de coste a favor de longitud fija en este corpus.

## Confound declarado

La estrategia por artículo antepone a cada fragmento una línea de contexto
fija ("LGT · Artículo 66. Plazos de prescripción") que longitud fija no puede
construir: un fragmento de longitud fija puede solapar varios artículos, uno
solo, o ninguno (preámbulo), así que no hay un único título que anteponer.
Esta diferencia está documentada en el código
(`src/legal_splitter.py::split_ley_longitud_fija`) y debe declararse en la
memoria: **la comparación de esta tabla es entre dos estrategias completas
—troceado estructural y presencia/ausencia de línea de contexto—, no el
efecto de un único parámetro aislado.** No es posible, con este diseño de
experimento, atribuir qué parte de la caída de Recall@1/MRR se debe a la
pérdida de las fronteras de artículo y qué parte a la ausencia de la línea de
contexto.

## Limitaciones

Mismas limitaciones del golden set de 15 preguntas ya registradas en
`tabla_comparativa_prototipo1.md`: granularidad mínima de 6,7 puntos por
pregunta y vocabulario cercano al texto legal. Se mantienen aquí sin
cambios; esta tabla no las vuelve a desarrollar.
