# Hermes AI Gateway (OpenRouter Free Router) ⚡

Un gateway intelligente, compatibile al 100% con le API OpenAI (`/v1/chat/completions` e `/v1/models`), progettato specificamente per agenti AI (come Hermes su ambiente Linux o locale).

Il gateway analizza in tempo reale ogni richiesta in ingresso, scopre e aggiorna dinamicamente l'elenco dei modelli **Free Tier ($0.00)** di OpenRouter, ed esegue una **doppia classificazione in simbiosi** (euristica a costo zero + classificatore LLM free rapido) per selezionare il miglior modello adatto al task, con supporto a **retry con backoff esponenziale** su `429` e fallback automatico a cascata.

---

## 🌟 Caratteristiche Principali

- **Filtro Free Tier Dinamico**: Interroga l'API di OpenRouter e filtra automaticamente solo i modelli con costo zero (`:free` o pricing prompt/completion = 0.00).
- **Doppia Classificazione in Simbiosi**:
  - `SYNERGY`: fusione ponderata tra analisi euristica (0 ms) e classificazione semantica LLM.
  - `HEURISTIC_ONLY`: decisione istantanea a latenza zero senza alcun consumo di rate limit.
  - `SHADOW_TEST`: l'euristica decide immediatamente per l'utente, mentre l'LLM analizza in background per telemetria comparativa.
- **Supporto Multimodale Intelligente**: Riconosce automaticamente immagini, audio, video e vincola la scelta a modelli provvisti di tali capacità (es. Gemini Flash, Mistral Vision).
- **Specializzazione Coding & Reasoning**: Riconosce compiti di programmazione (indirizzati a Qwen Coder / DeepSeek) o di logica/matematica (indirizzati a DeepSeek R1).
- **Resilienza ai 429 e Errori 5xx**: Fino a 3 tentativi con backoff esponenziale sullo stesso modello prima di scalare a cascata sul successivo miglior modello free disponibile.
- **Dashboard Web & Telemetria Live**: Interfaccia grafica dark mode moderna, feed delle richieste in tempo reale, esploratore di modelli e playground interattivo di simulazione.

---

## 📁 Struttura del Progetto

```
openrouter-agent-router/
├── app/
│   ├── api/
│   │   ├── openai_routes.py       # Endpoints standard: /v1/chat/completions, /v1/models
│   │   └── telemetry_routes.py    # Telemetria, cambio modalità runtime e playground
│   ├── core/
│   │   ├── heuristic_analyzer.py  # Analisi immediata payload (vision, code, reasoning, tools)
│   │   ├── llm_classifier.py      # Mini-classificatore semantico rapido
│   │   ├── model_registry.py      # Scoperta dinamica e cache modelli Free
│   │   ├── openrouter_client.py   # Client HTTP con retry esponenziale, streaming SSE e fallback
│   │   └── router_engine.py       # Motore di scoring e selezione modello
│   ├── web/
│   │   ├── static/                # CSS dark mode glassmorphism e JavaScript reattivo
│   │   └── templates/             # Dashboard HTML
│   ├── config.py                  # Pydantic Settings e variabili .env
│   └── main.py                    # Applicazione FastAPI e lifecycle
├── Dockerfile                     # Immagine per container Linux
├── docker-compose.yml             # Avvio rapido con Docker Compose
├── openrouter-gateway.service     # File di servizio systemd per Linux
├── requirements.txt               # Dipendenze Python
├── test_gateway.py                # Test suite locale
└── README.md                      # Documentazione
```

---

## 🚀 Avvio Rapido

### 1. Configurazione Ambiente
Copia il file delle variabili d'ambiente e inserisci la tua API Key di OpenRouter (puoi ottenerne una gratuita su [openrouter.ai/keys](https://openrouter.ai/keys)):

```bash
cp .env.example .env
```

Modifica `.env`:
```env
OPENROUTER_API_KEY=sk-or-v1-xxxxxxxxxxxxxxxxx
DEFAULT_ROUTING_MODE=SYNERGY
GATEWAY_PORT=8000
```

### 2. Esecuzione Locale con Python

```bash
# Crea e attiva l'ambiente virtuale
python -m venv .venv
source .venv/bin/activate   # Su Windows: .venv\Scripts\activate

# Installa le dipendenze
pip install -r requirements.txt

# Avvia il gateway
python -m app.main
```

Il gateway sarà attivo su `http://localhost:8000`:
- **Dashboard Web**: `http://localhost:8000/`
- **OpenAI Endpoint**: `http://localhost:8000/v1/chat/completions`
- **Models Endpoint**: `http://localhost:8000/v1/models`

### 3. Esecuzione con Docker Compose

```bash
docker compose up -d
```

---

## 🤖 Integrazione con Agenti Hermes (o client OpenAI)

Per collegare qualsiasi agente o script compatibile OpenAI al gateway locale:

### In Python (OpenAI SDK):
```python
from openai import OpenAI

client = OpenAI(
    base_url="http://localhost:8000/v1",
    api_key="not-needed"  # L'autenticazione è gestita dal gateway
)

response = client.chat.completions.create(
    model="openrouter/auto",  # Il router sceglierà il miglior modello free in base al prompt
    messages=[
        {"role": "user", "content": "Scrivi uno script Python per scaricare una pagina web e analizzarne i link"}
    ]
)

print(response.choices[0].message.content)
```

### In Hermes Agent (Linux):
Nelle impostazioni o nel file di configurazione dell'agente Hermes (o tramite variabili d'ambiente):
```bash
export OPENAI_BASE_URL="http://localhost:8000/v1"
export OPENAI_MODEL_NAME="openrouter/auto"
```

---

## 🧪 Verifica e Test

Puoi eseguire i test automatici dell'architettura di routing con:
```bash
python test_gateway.py
```
