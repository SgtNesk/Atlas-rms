# ATLAS RMS — Epoch 01
A runnable, local-first **API prototype**, not a production SaaS or microservice deployment.

## Start
1. Copy `.env.example` to `.env` and replace `SETUP_KEY` with a long random secret.
2. Run `docker compose up --build -d`.
3. Open http://localhost:8000/docs (when running locally).
4. POST `/setup` with header `x-setup-key` and JSON `{"name":"Hotel Demo","email":"owner@example.com","password":"use-a-unique-long-password"}`.
5. POST `/login` and use the bearer token in the Swagger Authorize dialog.
6. Create rooms, then bookings; query `/metrics` and `/forecast`.

## Implemented
Tenant-scoped rooms/bookings, provisioned hotel admin, password hashing, expiring bearer sessions, booking collision protection, ADR/RevPAR/occupancy and OTB snapshot forecast (not a statistical demand forecast).

## Not implemented
Frontend, public registration, tenant provisioning console, real PMS/channel manager integrations, production-grade auth, RBAC depth, immutable audit log, payment processing, competitor data, statistical forecasting, nesting, overbooking, corporate bids, ancillary revenue, automated pricing, observability, backups, microservices or production deployment. SQLite and in-process modules are intentional prototype choices. Production requires PostgreSQL, isolated service boundaries, migration management, row-level security or equivalent tenant authorization, secrets management, tests, rate limits, disaster recovery and operational review.

## Epoca 02 — aggiornamento
- UI responsive servita da `GET /` (login, camere, prenotazioni, tariffe, dashboard, benchmark).
- API aggiuntive: `/me`, `/ancillary`, `/rate-plans`, `/market`, `/revenue-intelligence`, `/audit`, `/logout`.
- Test locale: `python test_api.py` (usa database temporaneo).
- **Non pronto per produzione**: SQLite locale, nessuna pipeline di deployment verificata, nessuna integrazione PMS/OTA, assenza di test di sicurezza e di carico. Non inserire dati reali degli ospiti in questa versione.
