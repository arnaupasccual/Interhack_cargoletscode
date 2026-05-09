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

**M4 — Riesgo de devolución** *(nuevo)*
Predice la probabilidad de que el próximo pedido de un cliente en una familia acabe siendo devuelto o cancelado, antes de que ocurra. Detecta fricción oculta que precede a la fuga y que M2 y M3 no ven todavía en el volumen. Alimenta A8 (fricción oculta). Features principales: `ratio_devoluciones`, `cancelacion_streak`, `primera_devolucion`, familia de producto, label M0. Algoritmo: regresión logística si los datos de motivo son limpios; XGBoost si hay muchas variables categóricas.

**M5 — Señal previa a fuga** *(nuevo)*
Combina múltiples señales débiles que individualmente no superan ningún umbral pero que en conjunto indican pre-fuga. Actúa entre dos y seis semanas antes que M2 o M3. Alimenta A9 (pre-fuga temprana). Funciona como score ponderado por reglas: cancelación reciente en cliente limpio (+2), primera devolución en menos de seis meses (+3), slope negativo en 30 días sin llegar al umbral de M2 (+1), silencio más largo de lo habitual (+1), reducción de familias activas (+2). El umbral de activación se calibra con el feedback loop para reducir falsos positivos progresivamente.

---

## Capa 5 — Motor de alertas y priorización

Recibe las salidas de todos los modelos y genera alertas a nivel cliente × familia × momento. Cada alerta incluye obligatoriamente: motivo en lenguaje natural, familia afectada, canal recomendado, impacto económico esperado (`ratio_vs_potential × potencial_cliente × ticket_medio_familia`) y urgencia temporal (días hasta que la ventana se cierra o días de silencio acumulado). La priorización se calcula como `score = impacto_económico × (1 / días_restantes)`. El label de M0 determina el canal: delegado para clientes de alto valor o señales urgentes, televendedor para reposición y nuevos clientes, marketing automation para recuperación de inactivos.

El catálogo completo de alertas es: A1 reponer pronto, A2 ventana de captura en promiscuo, A3 fuga en leal (commodity), A4 fuga en técnico, A5 cliente recuperable, A6 anomalía de volumen brusca, A7 cliente nuevo sin segunda compra, A8 fricción oculta por devoluciones, A9 pre-fuga temprana multimodal.

---

## Capa 6 — Activación y feedback loop

Distribuye las alertas priorizadas al canal correspondiente: delegado comercial, televendedor o plataforma de marketing automation (HubSpot o equivalente). La arquitectura es agnóstica de CRM: las alertas se exponen vía API o fichero estructurado, preparadas para integración futura.

Cada alerta registra tres momentos: generación (tipo, fecha, cliente, familia, score, modelo fuente), acción (quién actuó, cuándo, canal utilizado) y resultado a 30 días (pidió o no, volumen recuperado, devolución o no). Este registro alimenta el feedback loop: permite calcular la tasa de conversión por tipo de alerta, detectar falsos positivos sistemáticos por modelo, recalibrar umbrales periódicamente y, en el caso de M5, identificar qué combinaciones de señales débiles predicen mejor la fuga real.