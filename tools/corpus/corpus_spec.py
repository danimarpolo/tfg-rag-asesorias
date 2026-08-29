# -*- coding: utf-8 -*-
"""
Fuente unica de verdad del corpus sintetico de requerimientos AEAT.

Tanto los PDF como eval/golden_triaje.json se derivan de ESTA estructura, de
modo que documento y anotacion no pueden divergir.

Convenciones de anotacion (ver README_corpus.md):
  - periodo: codigo AEAT -> "1T".."4T" (IVA trimestral), "0A" (anual).
  - importe: cantidad que el documento EXIGE O PROPONE INGRESAR (deuda, cuota
    a ingresar o sancion). No es cualquier cifra en euros que aparezca en el
    texto; las bases imponibles, cuotas soportadas y diferencias detectadas
    son distractores deliberados y NO son el importe.
  - articulos_citados: normalizados a nivel de articulo (sin apartado), en
    formato "<NORMA> art. <N>", ordenados como aparecen en el documento.
  - nif: el del OBLIGADO TRIBUTARIO. Si el documento incluye ademas el NIF de
    un representante, ese NO es la respuesta correcta.
  - plazo_dias: numero entero de dias concedido, aunque el documento no ancle
    el plazo a una fecha concreta.
"""

from datetime import date

# --- Identidades ficticias -------------------------------------------------
# Los digitos siguen patrones evidentemente artificiales; la letra/digito de
# control se calcula en build_corpus.py para que el formato sea valido.

DOCS = [

    # =====================================================================
    # 1-4 · REQUERIMIENTOS DE DOCUMENTACION
    # =====================================================================

    # --- CASO DIFICIL: datos clave en TABLA DE CABECERA -------------------
    # req_001 y req_002 forman un par de ablacion: mismos valores en los 9
    # campos del golden, unica diferencia la maquetacion.
    dict(
        fichero="req_001.pdf",
        tipo_documento="requerimiento_documentacion",
        layout="tabla",
        titular="BAZAR ORION DE PRUEBA, S.L.",
        titular_render="BAZAR ORIÓN DE PRUEBA, S.L.",
        tipo_id="cif", id_seed="B0000001",
        domicilio=["Calle Inventada de los Naranjos, 14, 2.º B", "29013 MÁLAGA (MÁLAGA)"],
        representante=None,
        impuesto="IVA", modelo="303", ejercicio=2024, periodo="2T",
        periodo_texto="2T",
        articulos=["LGT art. 136", "LGT art. 137", "LGT art. 203"],
        importe=None,
        plazo_dias=10, plazo_con_fecha=True,
        fecha_notif=date(2026, 5, 12),
        referencia="2026GMA0000101", justificante="2610012345678",
        titulo="REQUERIMIENTO",
        subtitulo="Procedimiento de comprobación limitada · Requerimiento de documentación",
        oficina="Administración de Málaga-Este",
        firmante="LA JEFA DE LA UNIDAD DE GESTIÓN TRIBUTARIA",
        motivo=(
            "Como consecuencia de la revisión de la autoliquidación presentada por el concepto, "
            "ejercicio y período indicados, se han detectado posibles incidencias en la deducción "
            "de las cuotas soportadas consignadas en la casilla 29 del modelo 303."
        ),
        distractores=[
            ("Base imponible declarada en el período", "128.450,00"),
            ("Cuotas de IVA soportado deducidas", "21.780,00"),
        ],
        documentacion=[
            "Libro registro de facturas recibidas correspondiente al período requerido.",
            "Facturas originales que amparen las cuotas soportadas deducidas por importe "
            "superior a 600,00 euros.",
            "Justificantes bancarios del pago de las facturas anteriores.",
            "Detalle de la afectación a la actividad económica de los bienes y servicios "
            "adquiridos.",
        ],
    ),

    # --- CASO DIFICIL: los MISMOS datos embebidos en el CUERPO ------------
    dict(
        fichero="req_002.pdf",
        tipo_documento="requerimiento_documentacion",
        layout="cuerpo",
        titular="BAZAR ORION DE PRUEBA, S.L.",
        titular_render="BAZAR ORIÓN DE PRUEBA, S.L.",
        tipo_id="cif", id_seed="B0000001",
        domicilio=["Calle Inventada de los Naranjos, 14, 2.º B", "29013 MÁLAGA (MÁLAGA)"],
        representante=None,
        impuesto="IVA", modelo="303", ejercicio=2024, periodo="2T",
        periodo_texto="segundo trimestre",   # sin la cadena literal "2T"
        articulos=["LGT art. 136", "LGT art. 137", "LGT art. 203"],
        importe=None,
        plazo_dias=10, plazo_con_fecha=True,
        fecha_notif=date(2026, 5, 12),
        referencia="2026GMA0000102", justificante="2610012345679",
        titulo="REQUERIMIENTO",
        subtitulo=None,
        oficina="Administración de Málaga-Este",
        firmante="LA JEFA DE LA UNIDAD DE GESTIÓN TRIBUTARIA",
        motivo=None,
        distractores=[
            ("Base imponible declarada en el período", "128.450,00"),
            ("Cuotas de IVA soportado deducidas", "21.780,00"),
        ],
        documentacion=[
            "Libro registro de facturas recibidas del período de referencia.",
            "Facturas originales justificativas de las cuotas soportadas deducidas de importe "
            "superior a 600,00 euros.",
            "Justificantes del pago de dichas facturas mediante entidad de crédito.",
            "Explicación de la afectación de los bienes y servicios adquiridos a la actividad.",
        ],
    ),

    # --- CASO DIFICIL: plazo SIN FECHA CONCRETA ---------------------------
    dict(
        fichero="req_003.pdf",
        tipo_documento="requerimiento_documentacion",
        layout="tabla",
        titular="AMPARO VILLALCAZAR FINGIDO",
        titular_render="AMPARO VILLALCÁZAR FINGIDO",
        tipo_id="nif", id_seed="12345678",
        domicilio=["Avenida de la Ficción, 202, 5.º C", "29010 MÁLAGA (MÁLAGA)"],
        representante=None,
        impuesto="IRPF", modelo="100", ejercicio=2023, periodo="0A",
        periodo_texto="0A",
        articulos=["LGT art. 136", "LGT art. 203", "LIRPF art. 30"],
        importe=None,
        plazo_dias=10, plazo_con_fecha=False,     # <-- sin fecha límite
        fecha_notif=date(2026, 6, 3),
        referencia="2026GMA0000178", justificante="2610012399001",
        titulo="REQUERIMIENTO",
        subtitulo="Requerimiento de documentación · Rendimientos de actividades económicas",
        oficina="Administración de Málaga-Este",
        firmante="EL JEFE DE LA UNIDAD DE GESTIÓN TRIBUTARIA",
        motivo=(
            "Se han apreciado discrepancias entre el rendimiento neto de actividades económicas "
            "declarado en estimación directa simplificada y la información de que dispone esta "
            "Administración."
        ),
        distractores=[
            ("Rendimiento neto de actividades económicas declarado", "34.117,52"),
            ("Gastos deducibles consignados", "19.884,30"),
        ],
        documentacion=[
            "Libro registro de ingresos y de ventas del ejercicio.",
            "Libro registro de gastos y de compras del ejercicio.",
            "Libro registro de bienes de inversión.",
            "Facturas y justificantes de los gastos deducidos por suministros de la vivienda "
            "parcialmente afecta a la actividad.",
        ],
    ),

    dict(
        fichero="req_004.pdf",
        tipo_documento="requerimiento_documentacion",
        layout="tabla",
        titular="CASIMIRO RONDAVIEJA INVENTADO",
        titular_render="CASIMIRO RONDAVIEJA INVENTADO",
        tipo_id="nif", id_seed="87654321",
        domicilio=["Plaza del Supuesto, 7, bajo", "29601 MARBELLA (MÁLAGA)"],
        representante=None,
        impuesto="IRPF", modelo="100", ejercicio=2024, periodo="0A",
        periodo_texto="0A",
        articulos=["LGT art. 108", "LGT art. 136", "LGT art. 203"],
        importe=None,
        plazo_dias=10, plazo_con_fecha=True,
        fecha_notif=date(2026, 6, 17),
        referencia="2026GMA0000214", justificante="2610012399457",
        titulo="REQUERIMIENTO",
        subtitulo="Requerimiento de documentación · Contraste con información de terceros",
        oficina="Administración de Marbella",
        firmante="LA JEFA DE LA UNIDAD DE GESTIÓN TRIBUTARIA",
        motivo=(
            "Los datos declarados no coinciden con los que constan en poder de esta Administración "
            "procedentes de declaraciones informativas presentadas por terceros, que se presumen "
            "ciertos salvo prueba en contrario."
        ),
        distractores=[
            ("Rendimientos del trabajo imputados por terceros", "41.226,08"),
            ("Rendimientos del trabajo declarados", "38.910,00"),
        ],
        documentacion=[
            "Certificados de retenciones e ingresos a cuenta emitidos por todos los pagadores "
            "del ejercicio.",
            "Justificación documental de la discrepancia advertida respecto de la imputación "
            "practicada por el pagador.",
            "Contratos laborales o mercantiles vigentes durante el ejercicio.",
        ],
    ),

    # =====================================================================
    # 5-7 · PROPUESTAS DE LIQUIDACION PROVISIONAL ("PARALELAS")
    # =====================================================================

    dict(
        fichero="req_005.pdf",
        tipo_documento="propuesta_liquidacion_provisional",
        layout="tabla",
        titular="PURIFICACION TEBAR SIMULADA",
        titular_render="PURIFICACIÓN TÉBAR SIMULADA",
        tipo_id="nif", id_seed="11111111",
        domicilio=["Calle del Espantapájaros, 33", "29700 VÉLEZ-MÁLAGA (MÁLAGA)"],
        representante=None,
        impuesto="IRPF", modelo="100", ejercicio=2023, periodo="0A",
        periodo_texto="0A",
        articulos=["LGT art. 101", "LGT art. 138", "LIRPF art. 68"],
        importe=1847.63,
        plazo_dias=10, plazo_con_fecha=True,
        fecha_notif=date(2026, 5, 26),
        referencia="2026GMA0000305", justificante="2610012401122",
        titulo="PROPUESTA DE LIQUIDACIÓN PROVISIONAL Y TRÁMITE DE ALEGACIONES",
        subtitulo="Procedimiento de comprobación limitada",
        oficina="Administración de Vélez-Málaga",
        firmante="EL JEFE DE LA UNIDAD DE GESTIÓN TRIBUTARIA",
        motivo=(
            "Se minora la deducción por donativos aplicada, al no acreditarse mediante "
            "certificación de la entidad donataria la totalidad de las cantidades consignadas."
        ),
        paralela=[
            ("Rendimientos del trabajo", "31.420,00", "31.420,00"),
            ("Rendimientos del capital mobiliario", "1.208,44", "1.208,44"),
            ("Base liquidable general", "27.905,12", "27.905,12"),
            ("Deducción por donativos", "1.980,00", "267,60"),
            ("Cuota resultante de la autoliquidación", "3.104,20", "4.816,60"),
        ],
        desglose=[("Cuota", "1.712,40"), ("Intereses de demora", "135,23")],
    ),

    # --- CASO DIFICIL: DOS NIF (obligado + representante) ------------------
    dict(
        fichero="req_006.pdf",
        tipo_documento="propuesta_liquidacion_provisional",
        layout="tabla",
        titular="TRANSPORTES LA QUIMERA DE PRUEBA, S.L.U.",
        titular_render="TRANSPORTES LA QUIMERA DE PRUEBA, S.L.U.",
        tipo_id="cif", id_seed="B2222222",
        domicilio=["Polígono Industrial El Espejismo, nave 12", "29590 CAMPANILLAS (MÁLAGA)"],
        representante=dict(
            nombre="EULOGIO MANZANEDO APÓCRIFO",
            tipo_id="nif", id_seed="33333333",
            cargo="Administrador único y representante",
        ),
        impuesto="IVA", modelo="303", ejercicio=2024, periodo="3T",
        periodo_texto="3T",
        articulos=["LGT art. 101", "LGT art. 138", "LIVA art. 99"],
        importe=4312.90,
        plazo_dias=10, plazo_con_fecha=True,
        fecha_notif=date(2026, 6, 30),
        referencia="2026GMA0000341", justificante="2610012402887",
        titulo="PROPUESTA DE LIQUIDACIÓN PROVISIONAL Y TRÁMITE DE ALEGACIONES",
        subtitulo="Procedimiento de comprobación limitada",
        oficina="Administración de Málaga-Oeste",
        firmante="LA JEFA DE LA UNIDAD DE GESTIÓN TRIBUTARIA",
        motivo=(
            "Se regularizan cuotas soportadas deducidas en un período de liquidación distinto "
            "de aquel en que se soportaron, sin que haya transcurrido el plazo de caducidad "
            "del derecho a deducir."
        ),
        paralela=[
            ("IVA devengado. Base imponible", "96.310,00", "96.310,00"),
            ("IVA devengado. Cuota", "20.225,10", "20.225,10"),
            ("IVA soportado deducible", "14.902,40", "10.869,00"),
            ("Resultado de la autoliquidación", "5.322,70", "9.356,10"),
        ],
        desglose=[("Cuota", "4.033,40"), ("Intereses de demora", "279,50")],
    ),

    dict(
        fichero="req_007.pdf",
        tipo_documento="propuesta_liquidacion_provisional",
        layout="tabla",
        titular="NICOMEDES ALFARAZ HIPOTETICO",
        titular_render="NICOMEDES ALFARAZ HIPOTÉTICO",
        tipo_id="nif", id_seed="44444444",
        domicilio=["Camino de la Patraña, 88", "29140 CHURRIANA (MÁLAGA)"],
        representante=None,
        impuesto="IRPF", modelo="100", ejercicio=2024, periodo="0A",
        periodo_texto="0A",
        articulos=["LGT art. 101", "LGT art. 102", "LIRPF art. 33"],
        importe=6925.44,
        plazo_dias=15, plazo_con_fecha=True,
        fecha_notif=date(2026, 7, 8),
        referencia="2026GMA0000388", justificante="2610012404019",
        titulo="PROPUESTA DE LIQUIDACIÓN PROVISIONAL Y TRÁMITE DE ALEGACIONES",
        subtitulo="Ganancias y pérdidas patrimoniales no declaradas",
        oficina="Administración de Málaga-Este",
        firmante="EL JEFE DE LA UNIDAD DE GESTIÓN TRIBUTARIA",
        motivo=(
            "No se ha declarado la ganancia patrimonial derivada de la transmisión del inmueble "
            "que consta en la información remitida por el Colegio de Registradores."
        ),
        paralela=[
            ("Valor de transmisión", "0,00", "185.000,00"),
            ("Valor de adquisición actualizado", "0,00", "148.200,00"),
            ("Ganancia patrimonial", "0,00", "36.800,00"),
            ("Base imponible del ahorro", "1.940,00", "38.740,00"),
            ("Cuota resultante de la autoliquidación", "2.418,90", "8.951,60"),
        ],
        desglose=[("Cuota", "6.532,70"), ("Intereses de demora", "392,74")],
    ),

    # =====================================================================
    # 8-10 · IVA NO DEDUCIBLE / DISCREPANCIAS MODELO 303
    # =====================================================================

    dict(
        fichero="req_008.pdf",
        tipo_documento="requerimiento_iva_no_deducible",
        layout="tabla",
        titular="SUMINISTROS HOSTELEROS EL ESPEJISMO, S.L.",
        titular_render="SUMINISTROS HOSTELEROS EL ESPEJISMO, S.L.",
        tipo_id="cif", id_seed="B5555555",
        domicilio=["Calle de la Quimera, 45, local 3", "29004 MÁLAGA (MÁLAGA)"],
        representante=None,
        impuesto="IVA", modelo="303", ejercicio=2024, periodo="4T",
        periodo_texto="4T",
        articulos=["LIVA art. 95", "LIVA art. 96", "LGT art. 136"],
        importe=3104.55,
        plazo_dias=10, plazo_con_fecha=True,
        fecha_notif=date(2026, 7, 15),
        referencia="2026GMA0000412", justificante="2610012405560",
        titulo="REQUERIMIENTO Y PROPUESTA DE LIQUIDACIÓN PROVISIONAL",
        subtitulo="Cuotas soportadas no deducibles · Modelo 303",
        oficina="Administración de Málaga-Este",
        firmante="LA JEFA DE LA UNIDAD DE GESTIÓN TRIBUTARIA",
        motivo=(
            "Se han deducido cuotas soportadas en la adquisición de bienes y servicios destinados "
            "a atenciones a clientes y en la adquisición de un vehículo turismo respecto del que "
            "no se ha acreditado una afectación superior al cincuenta por ciento."
        ),
        distractores=[
            ("Cuotas soportadas por atenciones a clientes", "1.428,90"),
            ("Cuotas soportadas por el vehículo turismo", "3.095,10"),
        ],
        documentacion=[
            "Facturas recibidas correspondientes a las atenciones a clientes deducidas.",
            "Ficha técnica y permiso de circulación del vehículo turismo.",
            "Justificación del grado de afectación efectiva del vehículo a la actividad.",
        ],
        desglose=[("Cuota", "2.976,45"), ("Intereses de demora", "128,10")],
    ),

    dict(
        fichero="req_009.pdf",
        tipo_documento="requerimiento_iva_no_deducible",
        layout="tabla",
        titular="CLINICA DENTAL NUBARRON FICTICIA, S.L.P.",
        titular_render="CLÍNICA DENTAL NUBARRÓN FICTICIA, S.L.P.",
        tipo_id="cif", id_seed="B6666666",
        domicilio=["Avenida del Trampantojo, 118, 1.º", "29016 MÁLAGA (MÁLAGA)"],
        representante=None,
        impuesto="IVA", modelo="303", ejercicio=2024, periodo="0A",   # anual: 303 vs 390
        periodo_texto="0A",
        articulos=["LIVA art. 164", "RIVA art. 71", "LGT art. 136"],
        importe=2078.31,
        plazo_dias=10, plazo_con_fecha=True,
        fecha_notif=date(2026, 7, 22),
        referencia="2026GMA0000455", justificante="2610012406734",
        titulo="REQUERIMIENTO Y PROPUESTA DE LIQUIDACIÓN PROVISIONAL",
        subtitulo="Discrepancias entre el modelo 303 y el modelo 390",
        oficina="Administración de Málaga-Este",
        firmante="EL JEFE DE LA UNIDAD DE GESTIÓN TRIBUTARIA",
        motivo=(
            "La suma de los importes consignados en las autoliquidaciones trimestrales del "
            "modelo 303 no coincide con los declarados en la declaración-resumen anual, "
            "modelo 390, del mismo ejercicio. Se advierte, asimismo, deducción de cuotas "
            "soportadas afectas a operaciones exentas sin derecho a deducción."
        ),
        distractores=[
            ("Suma de los cuatro modelos 303 presentados", "17.940,26"),
            ("Importe declarado en el modelo 390", "19.926,71"),
        ],
        documentacion=[
            "Conciliación detallada entre las autoliquidaciones trimestrales y el resumen anual.",
            "Libros registro de facturas expedidas y recibidas del ejercicio.",
            "Detalle del porcentaje de prorrata aplicado y de su cálculo.",
        ],
        desglose=[("Cuota", "1.986,45"), ("Intereses de demora", "91,86")],
    ),

    # --- CASO DIFICIL: SIN IMPORTE RECLAMADO ------------------------------
    dict(
        fichero="req_010.pdf",
        tipo_documento="requerimiento_iva_no_deducible",
        layout="cuerpo",
        titular="BALTASAR QUINTEROS IMAGINARIO",
        titular_render="BALTASAR QUINTEROS IMAGINARIO",
        tipo_id="nif", id_seed="22222222",
        domicilio=["Calle del Bulo, 9, ático", "29620 TORREMOLINOS (MÁLAGA)"],
        representante=None,
        impuesto="IVA", modelo="303", ejercicio=2025, periodo="1T",
        periodo_texto="primer trimestre", mostrar_codigo_periodo=True,
        articulos=["LIVA art. 97", "LIVA art. 99", "LGT art. 203"],
        importe=None,                       # <-- ninguna cantidad se exige
        plazo_dias=10, plazo_con_fecha=True,
        fecha_notif=date(2026, 8, 5),
        referencia="2026GMA0000501", justificante="2610012408890",
        titulo="REQUERIMIENTO",
        subtitulo=None,
        oficina="Administración de Torremolinos",
        firmante="LA JEFA DE LA UNIDAD DE GESTIÓN TRIBUTARIA",
        motivo=None,
        distractores=[
            ("IVA soportado deducido en el período", "18.402,77"),
            ("IVA repercutido declarado en el período", "24.100,00"),
            ("Resultado a ingresar de la autoliquidación presentada", "5.697,23"),
        ],
        documentacion=[
            "Facturas originales que amparan la totalidad de las cuotas soportadas deducidas.",
            "Libro registro de facturas recibidas del período.",
            "Justificación de la afectación a la actividad de los bienes y servicios adquiridos.",
        ],
    ),

    # =====================================================================
    # 11-12 · TRAMITES DE AUDIENCIA Y ALEGACIONES
    # =====================================================================

    dict(
        fichero="req_011.pdf",
        tipo_documento="tramite_audiencia",
        layout="tabla",
        titular="REMEDIOS ALCANTARA SUPUESTA",
        titular_render="REMEDIOS ALCÁNTARA SUPUESTA",
        tipo_id="nif", id_seed="77777777",
        domicilio=["Calle Fabulada, 61, 3.º D", "29013 MÁLAGA (MÁLAGA)"],
        representante=None,
        impuesto="IRPF", modelo="100", ejercicio=2023, periodo="0A",
        periodo_texto="0A",
        articulos=["LGT art. 99", "LGT art. 138", "RGAT art. 96"],
        importe=2560.18,
        plazo_dias=15, plazo_con_fecha=True,
        fecha_notif=date(2026, 7, 29),
        referencia="2026GMA0000478", justificante="2610012407345",
        titulo="TRÁMITE DE AUDIENCIA Y ALEGACIONES",
        subtitulo="Procedimiento de comprobación limitada",
        oficina="Administración de Málaga-Este",
        firmante="EL JEFE DE LA UNIDAD DE GESTIÓN TRIBUTARIA",
        motivo=(
            "Concluidas las actuaciones de comprobación y con carácter previo a dictar la "
            "resolución que ponga fin al procedimiento, se pone de manifiesto el expediente "
            "para que pueda alegar cuanto convenga a su derecho."
        ),
        distractores=[("Base liquidable comprobada", "42.780,55")],
        alegaciones_ctx=(
            "Del expediente resulta la improcedencia de la reducción por tributación conjunta "
            "aplicada, al no concurrir los requisitos de la unidad familiar declarada."
        ),
    ),

    # --- CASO DIFICIL: CINCO ARTICULOS, LEY + REGLAMENTO ------------------
    dict(
        fichero="req_012.pdf",
        tipo_documento="tramite_audiencia",
        layout="tabla",
        titular="OBRA CIVIL Y ARIDOS EL SIMULACRO, S.A.",
        titular_render="OBRA CIVIL Y ÁRIDOS EL SIMULACRO, S.A.",
        tipo_id="cif", id_seed="A9999999",
        domicilio=["Carretera de la Entelequia, km 4,200", "29130 ALHAURÍN DE LA TORRE (MÁLAGA)"],
        representante=None,
        impuesto="IVA", modelo="303", ejercicio=2024, periodo="1T",
        periodo_texto="1T",
        articulos=["LGT art. 138", "RGAT art. 96", "LIVA art. 95",
                   "LIVA art. 97", "RIVA art. 63"],
        importe=8744.26,
        plazo_dias=15, plazo_con_fecha=True,
        fecha_notif=date(2026, 8, 12),
        referencia="2026GMA0000534", justificante="2610012409911",
        titulo="TRÁMITE DE AUDIENCIA Y ALEGACIONES",
        subtitulo="Procedimiento de comprobación limitada · Impuesto sobre el Valor Añadido",
        oficina="Administración de Málaga-Oeste",
        firmante="LA JEFA DE LA UNIDAD DE GESTIÓN TRIBUTARIA",
        motivo=(
            "Concluidas las actuaciones de comprobación limitada y con anterioridad a dictar la "
            "resolución correspondiente, se le comunica la puesta de manifiesto del expediente."
        ),
        distractores=[
            ("Cuotas soportadas cuya deducción se cuestiona", "9.860,40"),
            ("Cuotas admitidas tras la comprobación", "1.116,14"),
        ],
        alegaciones_ctx=(
            "Las incidencias advertidas afectan a la deducción de cuotas soportadas por bienes "
            "de inversión sin acreditación del grado de afectación, a facturas que no reúnen los "
            "requisitos formales exigidos y a anotaciones del libro registro de facturas "
            "recibidas que no se corresponden con las facturas aportadas."
        ),
    ),

    # =====================================================================
    # 13-14 · ACUERDOS DE INICIO DE EXPEDIENTE SANCIONADOR
    # =====================================================================

    dict(
        fichero="req_013.pdf",
        tipo_documento="acuerdo_inicio_sancionador",
        layout="tabla",
        titular="AUTOESCUELA VIENTO DE PRUEBA, S.L.",
        titular_render="AUTOESCUELA VIENTO DE PRUEBA, S.L.",
        tipo_id="cif", id_seed="B8888888",
        domicilio=["Calle del Sortilegio, 23, bajo", "29640 FUENGIROLA (MÁLAGA)"],
        representante=None,
        impuesto="IVA", modelo="303", ejercicio=2024, periodo="2T",
        periodo_texto="2T",
        articulos=["LGT art. 191", "LGT art. 209", "LGT art. 188"],
        importe=1284.60,
        plazo_dias=15, plazo_con_fecha=True,
        fecha_notif=date(2026, 8, 19),
        referencia="2026SMA0000067", justificante="2610012410455",
        titulo="ACUERDO DE INICIO Y COMUNICACIÓN DE LA PROPUESTA DE RESOLUCIÓN",
        subtitulo="Expediente sancionador · Procedimiento abreviado",
        oficina="Administración de Fuengirola",
        firmante="EL JEFE DE LA DEPENDENCIA DE GESTIÓN TRIBUTARIA",
        motivo=(
            "De las actuaciones de comprobación practicadas resulta que se dejó de ingresar, "
            "dentro del plazo establecido en la normativa del tributo, parte de la deuda "
            "tributaria que debiera resultar de la correcta autoliquidación."
        ),
        sancion=dict(
            base="2.569,20",
            calificacion="Leve",
            porcentaje="50",
            reduccion_conformidad="30",
            reduccion_pronto_pago="40",
        ),
    ),

    dict(
        fichero="req_014.pdf",
        tipo_documento="acuerdo_inicio_sancionador",
        layout="cuerpo",
        titular="ANACLETO BERRUGUETE ILUSORIO",
        titular_render="ANACLETO BERRUGUETE ILUSORIO",
        tipo_id="nif", id_seed="99999999",
        domicilio=["Calle de la Añagaza, 5, 1.º A", "29680 ESTEPONA (MÁLAGA)"],
        representante=None,
        impuesto="IRPF", modelo="100", ejercicio=2023, periodo="0A",
        periodo_texto="0A",
        articulos=["LGT art. 194", "LGT art. 209", "LGT art. 211"],
        importe=1612.50,
        plazo_dias=15, plazo_con_fecha=True,
        fecha_notif=date(2026, 8, 24),
        referencia="2026SMA0000081", justificante="2610012411002",
        titulo="ACUERDO DE INICIO Y COMUNICACIÓN DE LA PROPUESTA DE RESOLUCIÓN",
        subtitulo=None,
        oficina="Administración de Estepona",
        firmante="LA JEFA DE LA DEPENDENCIA DE GESTIÓN TRIBUTARIA",
        motivo=(
            "De la comprobación practicada resulta la solicitud indebida de una devolución "
            "mediante la omisión de datos relevantes en la autoliquidación presentada, sin que "
            "la devolución llegara a obtenerse."
        ),
        sancion=dict(
            base="10.750,00",
            calificacion="Grave",
            porcentaje="15",
            reduccion_conformidad="30",
            reduccion_pronto_pago="40",
        ),
    ),
]

# Nombre desarrollado de cada norma, para el cuerpo de los documentos.
NORMAS = {
    "LGT": "la Ley 58/2003, de 17 de diciembre, General Tributaria",
    "LIVA": "la Ley 37/1992, de 28 de diciembre, del Impuesto sobre el Valor Añadido",
    "LIRPF": ("la Ley 35/2006, de 28 de noviembre, del Impuesto sobre la Renta de las "
              "Personas Físicas"),
    "RGAT": ("el Reglamento General de las actuaciones y los procedimientos de gestión e "
             "inspección tributaria, aprobado por Real Decreto 1065/2007, de 27 de julio"),
    "RIVA": ("el Reglamento del Impuesto sobre el Valor Añadido, aprobado por Real Decreto "
             "1624/1992, de 29 de diciembre"),
}

IMPUESTOS = {
    "IVA": "Impuesto sobre el Valor Añadido",
    "IRPF": "Impuesto sobre la Renta de las Personas Físicas",
}

PERIODO_TEXTO = {
    "1T": "primer trimestre", "2T": "segundo trimestre",
    "3T": "tercer trimestre", "4T": "cuarto trimestre",
    "0A": "ejercicio anual",
}
