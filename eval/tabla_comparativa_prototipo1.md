# Evaluación comparativa del recuperador

Conjunto de evaluación: 15 preguntas anotadas manualmente sobre LGT y LIVA.
Corpus: textos consolidados BOE-A-2003-23186 y BOE-A-1992-28740.

## Tabla de resultados

| Configuración | Modelo | Chunk | Overlap | Recall@1 | Recall@3 | Recall@5 | Recall@10 | MRR | Cobertura | Ingesta |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 0 · Base | `multilingual-e5-base` | 1800 | 200 | 80,0 % | 86,7 % | 93,3 % | 93,3 % | 0,8467 | 93,3 % | 903 s |
| 1 · Modelo pequeño | `multilingual-e5-small` | 1800 | 200 | 73,3 % | 93,3 % | 93,3 % | 93,3 % | 0,8333 | 93,3 % | 308 s |
| 2 · Fragmento corto | `multilingual-e5-base` | 1200 | 200 | 80,0 % | 93,3 % | 93,3 % | 93,3 % | **0,8667** | 93,3 % | 935 s |
| 3 · Fragmento largo | `multilingual-e5-base` | 3000 | 200 | 80,0 % | 93,3 % | 93,3 % | 93,3 % | **0,8667** | 93,3 % | 734 s |
| 4 · Sin prefijos E5 | `multilingual-e5-base` | 1800 | 200 | 66,7 % | 86,7 % | 93,3 % | 93,3 % | 0,7833 | 93,3 % | 895 s |

> Nota metodológica: los tiempos de ingesta se midieron en un equipo de
> desarrollo sin control de carga y solo son orientativos. No se registró el
> número de fragmentos por corrida, por lo que no es posible normalizar el
> tiempo por fragmento.

## Posición del primer acierto, pregunta a pregunta

| # | Artículo esperado | Base | Small | 1200 | 3000 | Sin pref. |
|---:|---|---:|---:|---:|---:|---:|
| 1 | LGT art. 66 — prescripción | 1 | 2 | 1 | 1 | 1 |
| 2 | LGT art. 223 — recurso de reposición | 2 | 2 | 2 | 1 | 2 |
| 3 | LGT art. 235 — reclamación econ.-adm. | 5 | 2 | 2 | 2 | 4 |
| 4 | LGT art. 62 — plazos de pago | 1 | 1 | 1 | 1 | 1 |
| 5 | LGT art. 27 — recargos extemporáneos | 1 | 1 | 1 | 1 | 1 |
| 6 | LGT art. 112 — notificación comparecencia | 1 | 1 | 1 | 1 | 1 |
| 7 | LGT art. 93/94 — deber de información | 1 | 1 | 1 | 1 | 2 |
| 8 | LGT art. 136-138 — comprobación limitada | 1 | 1 | 1 | 1 | 1 |
| 9 | LGT art. 150 — plazo de inspección | 1 | 1 | 1 | 2 | 2 |
| 10 | LGT art. 188 — reducción de sanciones | 1 | 1 | 1 | 1 | 1 |
| 11 | LGT art. 95 — datos reservados | 1 | 1 | 1 | 1 | 1 |
| 12 | LIVA art. 75 — devengo | 1 | 1 | 1 | 1 | 1 |
| 13 | LIVA art. 97 — requisitos de deducción | 1 | 1 | 1 | 1 | 1 |
| 14 | LIVA art. 84 — inversión sujeto pasivo | ✗ | ✗ | ✗ | ✗ | ✗ |
| 15 | LIVA art. 102-104 — prorrata | 1 | 1 | 1 | 1 | 1 |

Nueve preguntas obtienen la posición 1 en las cinco configuraciones. Cinco
varían. Una falla siempre.

## Hallazgos

**1. Recall@5 está saturado y no discrimina.** Las cinco configuraciones
obtienen 93,3 %, es decir, los mismos 14 aciertos sobre 15. La métrica que se
había fijado como criterio de decisión no distingue entre configuraciones en
este corpus, y por tanto la comparación debe apoyarse en MRR y Recall@1, que
miden la *posición* del acierto y no su mera presencia.

**2. Las diferencias entre las configuraciones 0 a 3 están dentro del ruido.**
Con n = 15, una pregunta equivale a 6,7 puntos de recall, y el rango completo
de MRR observado (0,8333–0,8667) corresponde al desplazamiento de una única
pregunta en una posición. No hay base estadística para preferir una de estas
cuatro configuraciones sobre otra.

**3. El tamaño de fragmento es indiferente** (configuraciones 2 y 3: métricas
idénticas con 1200 y 3000 caracteres). Esto es consecuencia directa del diseño:
como la unidad primaria de partición es el artículo y no la longitud, el límite
de caracteres solo afecta a la minoría de artículos que lo superan. La
insensibilidad a este parámetro es un argumento a favor del particionado
semántico-estructural, no una anomalía.

**4. Los prefijos E5 sí tienen efecto medible, pero sobre el orden, no sobre la
cobertura.** Desactivarlos deja Recall@5 intacto (93,3 %) y degrada Recall@1 de
80,0 % a 66,7 % y MRR de 0,8467 a 0,7833. La lectura correcta es que los
prefijos no cambian *qué* artículos entran en el conjunto recuperado, sino en
qué orden se colocan.

**5. El modelo pequeño es la mejor relación coste/calidad.** `e5-small` reduce
el tiempo de ingesta a un tercio (308 s frente a 903 s) con un MRR
prácticamente igual (0,8333 frente a 0,8467) y un Recall@3 superior (93,3 %
frente a 86,7 %). Dado que la reducción de latencia afecta también a la
codificación de cada consulta en tiempo de ejecución, es la opción
operativamente preferible.

**6. Fallo sistemático: LIVA art. 84.** La pregunta sobre inversión del sujeto
pasivo no recupera el artículo correcto en ninguna configuración. La causa es un
desajuste de vocabulario: «inversión del sujeto pasivo» es la denominación
doctrinal y profesional de la figura, mientras que el art. 84 LIVA se titula
«Sujetos pasivos» y su articulado la describe funcionalmente («serán sujetos
pasivos los empresarios o profesionales para quienes se realicen las operaciones
sujetas») sin emplear nunca esa expresión. Al ser un fallo de vocabulario y no
de segmentación, ninguna variación de los parámetros evaluados lo corrige.

## Limitaciones

El conjunto de evaluación de 15 preguntas resulta insuficiente para discriminar
entre configuraciones próximas: la granularidad mínima de la métrica es de 6,7
puntos porcentuales y solo cinco preguntas presentan variación entre corridas.

Las preguntas se redactaron partiendo del articulado, lo que introduce un sesgo
optimista: emplean vocabulario cercano al del texto legal. El caso del art. 84
sugiere que las consultas formuladas con terminología profesional, que son las
que realmente producirá el sistema en explotación, presentan una dificultad
mayor que la reflejada por estos resultados.
