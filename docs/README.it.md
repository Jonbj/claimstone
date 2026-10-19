# Mappa della documentazione

Quale file risponde a quale domanda. *In English: [README.md](README.md).*

## Da qui

| Voglio… | leggi |
|---|---|
| sapere cos'è questo progetto, in due minuti | [`../README.it.md`](../README.it.md) |
| eseguire un giro e capire cosa ne esce | [`GUIDE.it.md`](GUIDE.it.md) |
| sapere cosa sta girando e cosa è in sospeso adesso | [`HANDOFF.md`](HANDOFF.md) *(inglese)* |
| trovare i limiti implementati dello scheduler e le automazioni ancora da fare | [`SCHEDULER_BACKLOG.md`](SCHEDULER_BACKLOG.md) *(inglese)* |
| provare lo stack Docker Compose locale (portal, control, GROBID, worker dello scheduler) | [`LOCAL_COMPOSE_TRIAL.md`](LOCAL_COMPOSE_TRIAL.md) *(inglese)* |
| adattare il frontend allo scheduler | [`design/portal/SCHEDULER_FRONTEND_HANDOFF.md`](design/portal/SCHEDULER_FRONTEND_HANDOFF.md) *(inglese)* — stati dell'interfaccia, API disponibili, controlli mancanti e walkthrough di accettazione |
| servire il portale di sola lettura su tutti i progetti | `claimstone portal` — il successore multi-progetto della dashboard (D82); sola lettura, solo GET, loopback per impostazione predefinita |
| eseguire il portale nei container (frontend React + API in sola lettura) | `./portal.sh` (`./portal.sh down` per fermarlo) — D84; contratto API [`contracts/portal-api.schema.json`](contracts/portal-api.schema.json) *(inglese)* |
| sviluppare il frontend | `.venv/bin/claimstone control --allow-host localhost:5173` e `.venv/bin/claimstone api --session-authority http://127.0.0.1:8790` (due terminali; D152), poi `cd web && npm run dev` (http://localhost:5173); controlli: `npm run typecheck && npm test && npm run build` |
| lavorare sul codice come agente | [`../CLAUDE.md`](../CLAUDE.md), poi [`../AGENTS.md`](../AGENTS.md) *(inglese)* |
| discutere una scelta architetturale | [`DESIGN_DECISIONS.md`](DESIGN_DECISIONS.md) *(inglese)* — prima trova la voce |
| scrivere su un registro, o leggerne uno | [`contracts/`](contracts/) *(inglese)* — un file per registro |

## Il registro delle decisioni

[`DESIGN_DECISIONS.md`](DESIGN_DECISIONS.md) contiene tutte le decisioni numerate — 132 al 2026-10-16, in
circa 5.000 righe (`grep -c '^## D' docs/DESIGN_DECISIONS.md` per il conteggio corrente) — ognuna con **la
misura che l'ha decisa**. Non è fatto per essere letto dall'inizio alla fine.

Il suo scopo è stretto e vale dirlo: **che una scelta non venga rilitigata da principi primi.** Quasi tutte
le voci esistono perché qualcosa di plausibile è stato provato, misurato, e trovato sbagliato. Diverse
registrano una mia previsione che la misura ha falsificato — sono le più utili, perché dicono quali istinti
questo corpus punisce.

Per discutere una decisione, trova la sua voce e discuti la sua misura. Se la misura non tiene più, quella è
una voce nuova e datata, non una modifica alla vecchia: due cifre prodotte sotto strumenti diversi non sono
comparabili, e cancellare la prima lo nasconde.

## I contratti dei dati

Un file per registro, con ogni campo e perché esiste. Leggi quello del registro su cui stai per scrivere:
diversi campi esistono per prevenire un difetto preciso e sembrano opzionali finché non sai quale.

| file | registro |
|---|---|
| [`contracts/candidates.md`](contracts/candidates.md) | cosa ha trovato la scoperta, e da quale canale |
| [`contracts/query_hits.md`](contracts/query_hits.md) | ogni posizione di risultato per parole chiave, duplicati e fuori popolazione inclusi |
| [`contracts/search_page_probe.md`](contracts/search_page_probe.md) | ispezioni isolate e limitate di pagine OpenAlex |
| [`contracts/requests.md`](contracts/requests.md) | eventi di richiesta verso le API accademiche e query completate/fallite |
| [`contracts/acquisitions.md`](contracts/acquisitions.md) | ogni tentativo di scarico, la sua licenza, e perché è fallito |
| [`contracts/normalize.md`](contracts/normalize.md) | documenti e blocchi |
| [`contracts/source_selection.md`](contracts/source_selection.md) | audit preparatori e registri consultivi append-only di screening/identità; l'amissione di produzione non cambia |
| [`contracts/claims.md`](contracts/claims.md) | un'affermazione, la sua citazione, e i valori convertiti dal motore |
| [`contracts/reviews.md`](contracts/reviews.md) | il verdetto di un secondo lettore su un'affermazione |
| [`contracts/profiles.md`](contracts/profiles.md) | i profili dello stadio 6 e le adjudications che una persona firma |
| [`contracts/model_calls.md`](contracts/model_calls.md) | il confine su file che ogni stadio con modello attraversa |
| [`contracts/flows.md`](contracts/flows.md) | un selettore di round vincolato ai digest del protocollo sotto cui gira |
| [`contracts/scheduler_operations.md`](contracts/scheduler_operations.md) | operazioni limitate di singolo stadio e di rete, con i loro piani esatti e i loro esiti |
| [`contracts/network_schedules.md`](contracts/network_schedules.md) | finestre UTC finite costruite attorno a batch di rete già congelati |
| [`contracts/copy_policies.md`](contracts/copy_policies.md) | un margine limitato e revocabile per acquisire futuri candidati corrispondenti |
| [`contracts/local_mandates.md`](contracts/local_mandates.md) | lavoro ricorrente locale limitato per un flusso |
| [`contracts/worker_runtime.md`](contracts/worker_runtime.md) | heartbeat effimero del worker locale e suoi limiti |
| [`contracts/periodic_dossiers.md`](contracts/periodic_dossiers.md) | consegna periodica di evidenza sull'intero corpus e suoi gate di finalizzazione |
| [`contracts/periodic_exports.md`](contracts/periodic_exports.md) | dossier cumulativo impacchettato e sua verifica |
| [`contracts/exports.md`](contracts/exports.md) | uno snapshot verificabile di un flusso, e come si controlla |
| [`contracts/control_api.md`](contracts/control_api.md) | il confine autenticato di scrittura dietro il portale |
| [`contracts/operators.md`](contracts/operators.md) | chi può tenere una sessione della control API, e il registro degli eventi di autenticazione |
| [`contracts/decisions.md`](contracts/decisions.md) | decisioni dell'operatore prese tramite la control API |
| [`contracts/drafts.md`](contracts/drafts.md) | bozze di ragionamento dell'operatore — mai lette da uno stadio o da un export |
| [`contracts/intake.md`](contracts/intake.md) | materiale che un operatore propone, prima di ogni amissione |
| [`contracts/journey.md`](contracts/journey.md) | la pagina di ricerca guidata che il server calcola per il portale |
| [`contracts/new_project.md`](contracts/new_project.md) | bozze e percorsi della procedura guidata per nuovi progetti |
| [`contracts/notifications.md`](contracts/notifications.md) | l'outbox degli eventi che richiedono una persona, e i canali Telegram ed e-mail (D153, D154) |

## Materiale rimosso

Le specifiche e i piani per stadio, i resoconti di replay e review e le guide di integrazione dei provider
sono stati rimossi dall'albero il 2026-10-16 perché superati. Restano nella storia git: `git show 23a0a44:<percorso>`.
Dove `DESIGN_DECISIONS.md` o `HANDOFF.md` ne citano uno, la voce della decisione porta la misura.

## Lingua

I documenti rivolti a chi legge sono in **inglese e italiano**: questa mappa, il README principale e la guida.

Tutto il resto è **solo in inglese**: il registro delle decisioni, i contratti, i documenti di lavoro
(`HANDOFF.md`, `SCHEDULER_BACKLOG.md`, la prova compose, i handoff del frontend) e i commenti nel codice.
È una scelta, non una dimenticanza. Quei file cambiano quasi a ogni commit, e due copie di una regola
divergono — e la copia che diverge è quella che inganna qualcuno. Questo repository vincola `cli.BACKENDS` a
`runners.available()` con un test esattamente per questo, e tre test scritti in un giorno sono stati corretti
perché pescavano nella **prosa di un commento** invece che nel codice che descriveva.

Quindi: bilingue dove è stabile e si legge di rado, una lingua sola dove si lavora.
