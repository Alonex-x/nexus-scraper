# scraper-v1

Agente autónomo de web scraping sigiloso, parte del ecosistema **Nexus**
(API central de gestión de agentes). Se registra frente a la API, mantiene
un heartbeat periódico, consulta misiones de scraping pendientes, las
ejecuta con Playwright y reporta los resultados.

## Arquitectura

- **Heartbeat**: cada 60s, `POST /api/v1/agents/heartbeat`.
- **Consulta de misiones**: cada 30s, `GET /api/v1/missions/pending?agent=scraper-v1`.
- **Ejecución**: Playwright + Chromium headless, con contexto stealth
  (user-agent rotativo, viewport/locale/timezone aleatorios, banderas de
  automatización desactivadas).
- **Reporte**: `POST /api/v1/missions/{id}/report` con el resultado o el
  error.

Ambos bucles (heartbeat y misiones) corren de forma concurrente sobre
`asyncio`, y responden a `SIGTERM`/`SIGINT` deteniéndose limpiamente.

## Instalación

```bash
python3.10 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium
```

## Variables de entorno

Se pueden definir en un archivo `.env` en la raíz del proyecto (opcional,
cargado con `python-dotenv`):

| Variable | Descripción | Valor por defecto |
|---|---|---|
| `SCRAPER_API_KEY` | API Key del agente para autenticarse en Nexus (header `X-Agent-Key`). | Key de desarrollo embebida en `src/config.py` |
| `NEXUS_API_BASE_URL` | URL base de la API Nexus. | `http://localhost:8080` |

## Ejecución

```bash
python -m src.main
```

Detener el agente con `Ctrl+C` (SIGINT) o enviando `SIGTERM` al proceso;
ambos casos cierran el navegador y hacen flush de logs antes de salir.

## Pruebas

```bash
pytest tests/ -v
```

## Estructura del proyecto

```
.
├── .github/workflows/python-tests.yml   # CI: pytest en cada push/PR a main
├── src/
│   ├── config.py           # Configuración, constantes y stealth
│   ├── api_client.py       # Cliente HTTP de la API Nexus
│   ├── scraper_engine.py   # Lógica de scraping con Playwright
│   └── main.py             # Bucle principal del agente
└── tests/
    └── test_scraper.py     # Pruebas unitarias (pytest + pytest-mock)
```

## Notas sobre el manejo de errores

- **Timeout de navegación**: hasta 2 reintentos con backoff exponencial.
- **URL inaccesible (4xx/5xx)**: se reporta `FAILED` de inmediato, sin
  reintentos (no es un fallo transitorio).
- **Selector sin coincidencias**: se reporta `COMPLETED` con
  `scraped_text` vacío y una nota `selector_no_match`.
- **Error de red**: hasta 2 reintentos, luego `FAILED`.
- **Heartbeat y reporte de resultados**: hasta 3 reintentos con backoff
  exponencial (1s, 2s, 4s) ante fallos de red.

---

Este proyecto forma parte del [Ecosistema Nexus](https://github.com/Alonex-x/nexus-agent-api/blob/main/ECOSYSTEM.md).

## Demostración en video

[Ver demo del scraper en acción](https://raw.githubusercontent.com/Alonex-x/nexus-scraper/main/demos/demo-scraper.mp4)
