# Bot RSI + filtro SMA200 — paper trading en Hyperliquid (ETH)

Paper trading ($100, sin apalancamiento, sin claves ni wallet). Datos publicos de Hyperliquid.

- Senal: RSI(14) en 1h. Largo al cruzar 30 hacia arriba; corto al cruzar 70 hacia abajo.
- Filtro: largo solo si precio > SMA200 (velas 4h); corto solo si precio < SMA200.
- Salida: solo trailing stop (4%). Maximo 2 entradas/dia (UTC). Fee 0.045%/lado.
- Corre cada hora en GitHub Actions; el estado se guarda con commits en `data/`.

## Puesta en marcha
1. Settings -> Actions -> General -> Workflow permissions -> "Read and write permissions".
2. Actions -> "RSI paper-trading bot (Hyperliquid)" -> Run workflow.
3. Primera ejecucion: solo inicializa. Revisa `data/metrics.json` y `data/trades_log.csv`.

Cambiar de activo: `symbol` en `config.json`. Evaluar con 20-30 operaciones cerradas (~6 meses).
Limitaciones: el stop se evalua con el High/Low de cada vela 1h; sin slippage ni funding.
