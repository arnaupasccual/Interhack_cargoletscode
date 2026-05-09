Aquí el resumen actualizado de todas las capas, sin diagrama:

---

## Capa 1 — Datos brutos

Histórico de más de cinco años a nivel de cliente × producto × día. Incluye pedidos confirmados, cancelaciones y devoluciones como entidades propias (no como ajuste negativo del volumen). Cada registro de cancelación y devolución mantiene su fecha, familia de producto, volumen y motivo si está disponible. Esta separación es fundamental: tratarlos como meros descuentos sobre el pedido haría invisible la señal de fricción que contienen.

---

## Capa 2 — Limpieza y normalización

El objetivo no es eliminar registros sino clasificarlos: separar lo que es ruido (distorsiona los modelos) de lo que es señal (debe convertirse en feature).

**Pedidos:**
- Pedidos extraordinarios por stockaje o fin de año se detectan como outliers estadísticos por cliente × familia (IQR o z-score) y se etiquetan como `evento_especial`. Se excluyen del cálculo de recurrencia media pero no se borran del histórico.
- Rupturas de stock de Inibsa se identifican por correlación temporal entre múltiples clientes de la misma zona o familia en la misma ventana. No son señal de fuga.
- Períodos promocionales se marcan con una columna `is_promo_period` basada en el calendario comercial. Los modelos de tendencia los excluyen o los tratan como covariable.
- Sustituciones de producto se resuelven mapeando referencias discontinuadas a su familia normalizada. La unidad de análisis es siempre la familia, nunca el SKU.

**Cancelaciones:**
- Cancelación el mismo día con mismo volumen que un pedido duplicado → ruido administrativo, descartar.
- Cancelación por ruptura de stock del lado de Inibsa → ruido externo, descartar.
- Cancelación recurrente en un cliente con historial limpio → señal. Se convierte en feature `cancelacion_streak` y se alimenta a M4 y M5.

**Devoluciones:**
- Devolución por defecto de producto (motivo explícito o patrón puntual aislado) → ruido, descartar del cálculo de volumen activo.
- Devolución recurrente de una misma familia → señal de fricción o de entrada de competidor con mejor producto. Se calcula el ratio `devoluciones / pedidos` en ventana de 90 días por cliente × familia.
- Primera devolución en un cliente sin historial previo de devoluciones → flag binario `primera_devolucion`, señal de alerta temprana para M5.

**Clientes con histórico incompleto:**
- Menos de seis meses de datos: se tratan con modelos más conservadores basados en medias de segmento similar (perfil de clínica, tamaño, especialidad). No se mezclan con clientes con histórico largo.

---

## Capa 3 — Feature engineering

Se calculan por cliente × familia de producto, con actualización diaria. El volumen bruto nunca entra directamente en los modelos; todo se expresa en métricas comparables entre clínicas de distinto tamaño y especialidad.

| Feature | Cómo se calcula | Modelos que la usan |
|---|---|---|
| `days_since_last_order` | Fecha hoy − última fecha de pedido | M1, M2, M3 |
| `inter_order_avg` | Media de días entre pedidos (últimos 12 meses) | M0, M1 |
| `inter_order_std` | Desviación estándar de esos intervalos | M0 (clientes esporádicos) |
| `ratio_vs_potential` | Volumen comprado / potencial estimado del cliente | M0, M2 |
| `trend_slope_90d` | Regresión lineal del volumen en 90 días | M2, M3 |
| `trend_slope_30d` | Ídem para ventana corta | M3, M5 (señal temprana) |
| `seasonal_index` | Ratio mes actual vs. media histórica del mismo mes | M1, M2 |
| `pct_families_active` | % de familias que el cliente sigue comprando | M3, M5 |
| `silence_streak` | Días consecutivos sin pedido en esa familia | M2, M3, M5 |
| `reactivation_signal` | Pedido pequeño tras silencio largo | A5 |
| `ratio_devoluciones` | Devoluciones / pedidos en los últimos 90 días | M4, M5 |
| `cancelacion_streak` | Cancelaciones consecutivas recientes | M4, M5 |
| `primera_devolucion` | Flag binario: primera devolución en cliente limpio | M5 |

---

## Capa 4 — Modelos

Se ejecutan con actualización diaria, salvo M0 que recalcula el label de perfil semanalmente. La salida de cada modelo es siempre a nivel cliente × familia.

**M0 — Perfil de cliente (Leal / Promiscuo / Esporádico)**
Clasifica a cada cliente según su patrón estructural de compra en cada familia. Es el modelo transversal: su output condiciona qué alertas se activan y con qué canal. La misma señal de M2 genera una alerta de captura competidora si el cliente es Promiscuo, o una alerta de fuga preocupante si es Leal. Algoritmo: clustering (K-Means o jerárquico) sobre `ratio_vs_potential`, `inter_order_std` y `silence_streak`, seguido de reglas de negocio para etiquetar los clústeres de forma interpretable.

**M1 — Predicción de reposición**
Estima los días hasta el próximo pedido esperado de cada cliente en cada familia. Alimenta la alerta A1 (reponer pronto) en clientes Leales, y la alerta A7 (cliente nuevo sin segunda compra) cuando no aparece señal de reposición en el plazo esperado. Algoritmo: survival analysis (Kaplan-Meier por segmento o modelo de Cox con covariables). Alternativa más explicable: regresión sobre `inter_order_avg` ajustada por `seasonal_index`.

**M2 — Fuga en commodity**
Detecta desviaciones sostenidas entre el consumo observado y el consumo esperado según el potencial del cliente. Distingue variación puntual (ruido) de deterioro acumulado (señal). Alimenta A2 (ventana de captura en promiscuos), A3 (fuga en leales) y A6 (caída brusca de volumen). Algoritmo: CUSUM sobre la serie temporal de `ratio_vs_potential`. Complemento: z-score en ventana de 30 días como detector de caídas agudas.

**M3 — Fuga en producto técnico**
Detecta anomalías en el patrón histórico individual de cada cliente, sin necesidad de benchmark grupal. Adecuado para productos técnicos con alta heterogeneidad entre clientes. Alimenta A4 (fuga técnico) y A5 (cliente recuperable tras silencio largo). Algoritmo: Isolation Forest entrenado por cliente sobre `silence_streak`, `trend_slope_30d` y `pct_families_active`.

---

## Capa 5 — Motor de alertas y priorización

Recibe las salidas de todos los modelos y genera alertas a nivel cliente × familia × momento. Cada alerta incluye obligatoriamente: motivo en lenguaje natural, familia afectada, canal recomendado, impacto económico esperado (`ratio_vs_potential × potencial_cliente × ticket_medio_familia`) y urgencia temporal (días hasta que la ventana se cierra o días de silencio acumulado). La priorización se calcula como `score = impacto_económico × (1 / días_restantes)`. El label de M0 determina el canal: delegado para clientes de alto valor o señales urgentes, televendedor para reposición y nuevos clientes, marketing automation para recuperación de inactivos.

El catálogo completo de alertas es: A1 reponer pronto, A2 ventana de captura en promiscuo, A3 fuga en leal (commodity), A4 fuga en técnico, A5 cliente recuperable, A6 anomalía de volumen brusca, A7 cliente nuevo sin segunda compra, A8 fricción oculta por devoluciones, A9 pre-fuga temprana multimodal.

## Catálogo de alertas — detalle completo

Cada alerta se describe con su lógica de activación, condiciones exactas, output que produce, canal recomendado y cómo se desactiva.

---

### A1 — Reponer pronto

**Qué detecta:** un cliente Leal está próximo a agotar su stock estimado de una familia commodity y se acerca su ventana habitual de pedido.

**Condiciones de activación:**
- Label M0 = Leal
- M1 estima que el próximo pedido esperado se producirá en los próximos N días (umbral configurable, típicamente 3–7 días según la familia)
- `days_since_last_order` ≥ 70% del `inter_order_avg` histórico del cliente
- No hay pedido ya en curso para esa familia

**Output de la alerta:**
- Cliente, familia, fecha estimada de necesidad
- Volumen habitual del cliente en esa familia (referencia para el televendedor)
- Días restantes estimados hasta agotamiento
- Motivo: "Este cliente pide anestesia cada 14 días de media. Su último pedido fue hace 11 días."

**Canal:** Televendedor. Es una alerta de baja urgencia y alta previsibilidad; no requiere delegado.

**Desactivación:** se cierra automáticamente cuando entra un pedido de esa familia, o si pasan más de 5 días desde la fecha estimada sin pedido (en ese caso puede escalar a A3 o A6).

---

### A2 — Ventana de captura en promiscuo

**Qué detecta:** un cliente Promiscuo ha entrado en una ventana temporal en la que, según su patrón histórico, debería estar comprando pero no lo está haciendo con Inibsa. Es el momento óptimo para intentar capturar demanda que habitualmente va a la competencia.

**Condiciones de activación:**
- Label M0 = Promiscuo
- M2 detecta que `ratio_vs_potential` está por debajo de la media histórica del cliente en esa familia
- `days_since_last_order` supera el `inter_order_avg` del cliente pero sin llegar al umbral de fuga
- El cliente tiene historial de compra en esa familia (no es primera vez)

**Output de la alerta:**
- Cliente, familia, días desde último pedido, ratio actual vs. potencial
- Estimación del volumen que podría capturarse (potencial no materializado en los últimos 90 días)
- Motivo: "Este cliente compra anestesia aproximadamente cada 10 días. Lleva 13 días sin pedir. Su ratio de captura habitual es del 40% del potencial estimado."

**Canal:** Delegado. Requiere conversación comercial, no solo llamada de pedido.

**Desactivación:** entra un pedido (captura conseguida), o el silencio supera el umbral de fuga y la alerta escala a A3.

---

### A3 — Fuga en cliente leal (commodity)

**Qué detecta:** un cliente históricamente Leal muestra una desviación sostenida y estadísticamente significativa respecto a su consumo esperado en una familia commodity. No es variación puntual: es un cambio de patrón.

**Condiciones de activación:**
- Label M0 = Leal
- M2 CUSUM acumula desviación negativa sostenida durante 3 o más semanas consecutivas
- Z-score de `ratio_vs_potential` en los últimos 30 días por debajo de −1.5 desviaciones
- No hay ningún evento conocido que lo explique (promo, ruptura de stock, pedido extraordinario previo)

**Output de la alerta:**
- Cliente, familia, semanas de deterioro acumulado, magnitud de la desviación
- Comparación entre volumen esperado y volumen observado en los últimos 60 días
- Motivo: "Este cliente compraba una media de 8 cajas de anestesia al mes. En los últimos dos meses ha comprado 3. La desviación es sostenida y no coincide con ningún evento conocido."

**Canal:** Delegado. Urgencia media-alta. El delegado debe visitar o llamar para entender qué está pasando antes de que la fuga se consolide.

**Desactivación:** el volumen vuelve al rango esperado durante dos semanas consecutivas, o se registra un motivo conocido que explica la caída (cierre temporal de clínica, baja del profesional, etc.).

---

### A4 — Fuga en producto técnico

**Qué detecta:** un cliente comprador de un producto técnico muestra un patrón anómalo respecto a su propio historial individual: caída de frecuencia, caída de volumen, desaparición de compra o combinación de varias. La referencia no es un benchmark grupal sino el comportamiento previo del propio cliente.

**Condiciones de activación:**
- Cliente con historial de compra activo en esa familia técnica (al menos 3 pedidos en los últimos 12 meses)
- M3 (Isolation Forest) clasifica el patrón actual como anómalo respecto al histórico individual
- Al menos una de: `silence_streak` supera 2 veces la mediana del cliente, `trend_slope_30d` negativo y acelerado, `pct_families_active` ha caído respecto a los 90 días anteriores

**Output de la alerta:**
- Cliente, familia técnica, tipo de anomalía detectada (silencio, caída de volumen, reducción de familias)
- Historial resumido: frecuencia habitual, último pedido, desviación actual
- Motivo: "Este cliente pedía implantes cada 6 semanas. Lleva 14 semanas sin pedir. Su patrón histórico no contempla silencios de esta duración."

**Canal:** Delegado. Alta prioridad, especialmente si el producto técnico tiene alto ticket. Requiere visita o llamada de diagnóstico, no solo de pedido.

**Desactivación:** entra un pedido en esa familia, o el delegado registra un motivo válido (cambio de especialidad, cierre de clínica, caso clínico resuelto).

---

### A5 — Cliente recuperable

**Qué detecta:** un cliente que llevaba un silencio prolongado (clasificado como inactivo) emite una señal débil de reactivación: un pedido pequeño, una consulta, una búsqueda en catálogo si el dato está disponible. Es el momento óptimo para reincidir antes de que el cliente se consolide como perdido.

**Condiciones de activación:**
- Cliente con silencio previo superior a 3 veces su `inter_order_avg` histórico (inactivo de facto)
- M3 detecta una señal de reactivación: pedido de volumen inferior al 30% de su ticket habitual, o primer contacto tras el silencio
- El cliente tiene historial previo relevante (no es cliente marginal)

**Output de la alerta:**
- Cliente, familia, duración del silencio previo, señal de reactivación detectada
- Valor histórico del cliente (volumen anual en su mejor período)
- Motivo: "Este cliente estuvo 8 meses sin pedir. Ha realizado un pedido pequeño de material de desinfección. Históricamente compraba por valor de X€ anuales."

**Canal:** Marketing automation en primera instancia (email o mensaje personalizado). Si no hay respuesta en 7 días, escala a Televendedor.

**Desactivación:** el cliente recupera un patrón de compra mínimamente activo (al menos 2 pedidos en 60 días), o no responde tras los intentos de contacto y se reclasifica como perdido.

---

**Output de la alerta:**
- Cliente, familia o familias afectadas, score total, desglose de señales que contribuyeron
- Horizonte temporal estimado: "Si el patrón continúa, riesgo de fuga confirmada en 3–6 semanas"
- Motivo detallado: "Score 6/10. Contribuye: primera devolución hace 12 días (+3), tendencia negativa en 30 días sin llegar a umbral (+1), silencio actual 20% más largo que su media (+1), ha dejado de pedir en una familia que compraba habitualmente (+2)."


---

## Capa 6 — Activación y feedback loop

Distribuye las alertas priorizadas al canal correspondiente: delegado comercial, televendedor o plataforma de marketing automation (HubSpot o equivalente). La arquitectura es agnóstica de CRM: las alertas se exponen vía API o fichero estructurado, preparadas para integración futura.

Cada alerta registra tres momentos: generación (tipo, fecha, cliente, familia, score, modelo fuente), acción (quién actuó, cuándo, canal utilizado) y resultado a 30 días (pidió o no, volumen recuperado, devolución o no). Este registro alimenta el feedback loop: permite calcular la tasa de conversión por tipo de alerta, detectar falsos positivos sistemáticos por modelo, recalibrar umbrales periódicamente y, en el caso de M5, identificar qué combinaciones de señales débiles predicen mejor la fuga real.