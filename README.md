# OpenRouter Free Agent Gateway (Hermes AI Router) 🚀

Un gateway intelligente, compatibile al 100% con le API OpenAI (`/v1/chat/completions` e `/v1/models`), progettato specificamente per agenti AI (come Hermes).

## Caratteristiche Principali
- **Filtro Free Tier Dinamico**: Rileva in tempo reale tutti i modelli gratuiti disponibili su OpenRouter.
- **Doppia Classificazione in Simbiosi**: Analizzatore euristico immediato + Classificatore LLM rapido.
- **Supporto Multimodale**: Indirizzamento automatico a modelli con visione (immagini), audio e video.
- **Retry con Backoff Esponenziale**: Gestione intelligente degli errori `429 Too Many Requests` e fallback a cascata.
- **Dashboard Web & Telemetria**: Monitoraggio in tempo reale e playground interattivo.
