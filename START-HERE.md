# ATLAS RMS — Pacchetto operativo

**Stato verificato:** prototipo API + UI, test locale superato. **Non è un SaaS pronto per clienti reali.**

## Avvio con Docker
1. Installa Docker Desktop o Docker Engine + Compose.
2. Copia `.env.example` in `.env`.
3. Imposta `SETUP_KEY` con un segreto casuale robusto (almeno 32 byte). Non pubblicarlo su Git.
4. Esegui `docker compose up --build -d` dalla cartella `atlas-rms`.
5. Apri `http://localhost:8000/` per la UI e `http://localhost:8000/docs` per le API.
6. Crea il primo hotel con POST `/setup` e header `x-setup-key`, JSON `{"name":"Hotel Demo","email":"admin@example.com","password":"una-password-unica-di-almeno-12-caratteri"}`.
7. Accedi tramite la UI.

## Test
`python -m pip install -r requirements.txt && python test_api.py`

## Limiti bloccanti prima della vendita
- SQLite locale e sessioni custom: da migrare a PostgreSQL/Supabase Auth.
- Nessun backup cloud e restore verificato; nessuna HA.
- Nessuna pipeline GitHub o deploy Vercel pubblicato verificato.
- Mancano security review, rate limiting, RBAC approfondito, logging/monitoraggio e test E2E.
- Nessuna integrazione PMS, OTA, channel manager o pagamenti.
- Forecast operativo basato su OTB, non previsione statistica avanzata.

## Dipendenze cloud
Supabase ha rifiutato un terzo progetto gratuito: limite di 2 progetti attivi. Tax Enforcer non è stato sospeso. La connessione GitHub non espone la creazione di repository. Non è stato creato alcun URL SaaS.

## Regola di sicurezza
Usare solo dati fittizi e password non riutilizzate. Non pubblicare la porta API su Internet senza hardening.
