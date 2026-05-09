Buenas preguntas. Vamos a hacer un análisis completo y estructurado. Te presento primero el mapa completo de alertas (incluyendo las que faltan), y luego el pipeline de datos y modelos.

## Alertas identificadas vs. las que faltan

Las tres alertas que propones son sólidas, pero el briefing pide más. Aquí el cuadro completo:

**Las que ya tienes:**
1. "Le toca pedir pronto" (commodity) — predicción de reposición
2. "Está dejando de comprar commodity" — deterioro en cliente leal
3. "Está dejando de comprar producto técnico" — riesgo de abandono

**Las que faltan y el briefing exige explícitamente:**
4. **Ventana de captura competidora** — cliente promiscuo detectado en momento donde su compra habitual a la competencia debería haberse producido y no ha vuelto aún
5. **Cliente recuperable** — llevaba meses sin comprar, empieza a dar señales (pedido pequeño, consulta) → momento óptimo para reincidir
6. **Anomalía de volumen** — cliente leal compra de repente muchísimo menos (o muchísimo más) de lo esperado → puede ser señal de fuga parcial, cambio de clínica, o promoción de competidor
7. **Cliente nuevo sin consolidar** — ha comprado 1-2 veces pero no ha repetido en el tiempo esperado → riesgo de no conversión temprana

---

Ahora el diagrama de la arquitectura completa:---

## Capa 2 — Limpieza y normalización (detalle)

**Anomalías a tratar antes de cualquier modelo:**

- **Pedidos extraordinarios** (stockaje por promo, fin de año): detectar outliers estadísticos por cliente × familia (IQR o z-score), marcarlos como "evento especial" y excluirlos del cálculo de recurrencia media. No eliminarlos del histórico, solo etiquetarlos.
- **Rupturas de stock**: si múltiples clientes dejan de comprar una familia simultáneamente, es señal de ruptura, no de fuga. Se detecta por correlación temporal entre clientes de la misma zona o familia.
- **Promociones**: crear una columna `is_promo_period` basada en el calendario comercial. Los modelos de tendencia deben excluir esos períodos o tratarlos como covariable.
- **Sustituciones de producto**: mapear referencias discontinuadas a su familia normalizada. La unidad de análisis es siempre la familia, no el SKU.
- **Clientes con histórico incompleto**: clientes con menos de 6 meses de datos se tratan aparte, con modelos más conservadores basados en medias de segmento similar (perfil de clínica, tamaño, especialidad).

**Normalización:**

- Convertir volumen a una métrica comparable entre clínicas: `ratio_compra = compra_observada / potencial_estimado`. El potencial viene del dato de cliente (tamaño, especialidad).
- Crear una curva de consumo esperado *por tipología de clínica* (clúster de tamaño, especialidad, zona). Esto es el benchmark contra el que se mide cada cliente.

---

## Capa 3 — Features clave por modelo

| Feature | Cómo se calcula | Usado en |
|---|---|---|
| `days_since_last_order` | Fecha hoy − última fecha de pedido | M1, M2, M3 |
| `inter_order_avg` | Media de días entre pedidos (últimos 12m) | M0, M1 |
| `inter_order_std` | Desviación estándar de esos intervalos | M0 (clientes esporádicos) |
| `ratio_vs_potential` | Volumen comprado / potencial estimado | M0, M2 |
| `trend_slope_90d` | Regresión lineal del volumen en 90 días | M2, M3 |
| `trend_slope_30d` | Ídem para ventana corta | M3 (señal temprana) |
| `seasonal_index` | Ratio mes actual vs. media histórica del mismo mes | M1, M2 |
| `pct_families_active` | % de familias que sigue comprando | M3 (abandono gradual) |
| `silence_streak` | Días consecutivos sin pedido en esa familia | M2, M3 |
| `reactivation_signal` | Pedido pequeño tras silencio largo | A5 |

---

## Capa 4 — Modelos en detalle

### M0 — Clasificación Leal / Promiscuo / Esporádico

Este modelo es el más importante porque su output condiciona qué alertas se activan para cada cliente. Se ejecuta una vez a la semana (no necesita recalcularse a diario).

**Algoritmo recomendado**: clustering jerárquico o K-Means sobre `ratio_vs_potential` + `inter_order_std` + `silence_streak`, seguido de reglas de negocio para etiquetar los clústeres.

La lógica conceptual:
- `ratio_vs_potential > 0.8` y `inter_order_std` baja → **Leal**
- `ratio_vs_potential` entre 0.3–0.7 y compra irregular → **Promiscuo**
- `inter_order_std` muy alta, compra esporádica → **Esporádico** (válido para productos técnicos)
- `ratio_vs_potential < 0.1`, sin patrón → **Marginal / sin clasificar**

El label de M0 se añade como feature a todos los demás modelos y como filtro del motor de alertas (por ejemplo, la alerta A2 solo se activa en clientes etiquetados como Promiscuos).

### M1 — Predicción de reposición (A1)

**Algoritmo**: Survival analysis (Kaplan-Meier por segmento, o modelo de Cox con covariables). Alternativa más simple y explicable: regresión lineal sobre `inter_order_avg` ajustada por `seasonal_index`.

Output: **probabilidad de que el cliente pida en los próximos N días**. La alerta A1 se activa cuando esa probabilidad supera umbral y `days_since_last_order` está dentro de la ventana esperada.

### M2 — Fuga en commodity (A3, A2)

**Algoritmo**: CUSUM (cumulative sum control chart) sobre la serie temporal de `ratio_vs_potential`. El CUSUM es ideal porque detecta cambios sostenidos de forma acumulativa, evitando disparar alertas por variación puntual.

Un z-score sobre la ventana de 30 días es la alternativa más simple. Si el z-score está por debajo de −1.5 desviaciones durante 3+ semanas consecutivas, hay señal real.

El label M0 filtra: si el cliente es Promiscuo, la misma señal activa A2 (ventana de captura). Si es Leal, activa A3 (fuga preocupante).

### M3 — Fuga en producto técnico (A4)

**Algoritmo**: Isolation Forest por cliente individual, entrenado sobre su propio histórico. La ventaja es que no necesita un benchmark grupal: detecta anomalías respecto al patrón *propio* de cada cliente, lo que es crucial para productos técnicos con alta heterogeneidad.

Input: `silence_streak`, `trend_slope_30d`, `pct_families_active` del cliente en esa familia. Si el modelo lo clasifica como anomalía y el cliente era comprador activo, se activa A4.

---

## Motor de alertas y priorización (Capa 5)

Cada alerta lleva tres campos obligatorios según el briefing:

1. **Motivo** — explicación en lenguaje natural de qué variable activó la alerta (ej: "lleva 18 días sin pedir anestesia; su media histórica es 12 días")
2. **Impacto económico esperado** — `ratio_vs_potential × potencial_cliente × ticket_medio_familia`
3. **Urgencia** — días hasta que la ventana de captura se cierra (estimado por M1) o días de silencio acumulado

La priorización final es: `score = impacto_económico × (1 / días_restantes)`, ordenado descendente. El delegado ve primero las alertas de mayor valor y mayor urgencia.

---

## Feedback loop (Capa 6)

Para que el sistema aprenda, cada alerta debe registrar:
- Alerta generada (tipo, fecha, cliente, familia, score)
- Acción tomada (quién, cuándo, canal)
- Resultado a 30 días (pidió / no pidió, volumen recuperado)

Con ese registro se pueden calcular la tasa de conversión por tipo de alerta, detectar falsos positivos sistemáticos (ej. clientes esporádicos que siempre se clasifican mal) y recalibrar los umbrales de los modelos periódicamente.