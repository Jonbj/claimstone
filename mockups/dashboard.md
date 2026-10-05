# Console Claimstone — guida al mockup

*Companion di `mockups/dashboard.html`. Documento pensato per due lettori: una persona che apre il file nel
browser, e un modello a cui viene chiesto di revisionare il design. Le stesse informazioni, con la precisione
che serve al secondo.*

**Stato: rivisto e corretto** dopo due review esterne (Claude e Codex, 2026-09-28) — vedi §8 per il registro
punto-per-punto. Disciplina delle cifre: ogni numero reale porta *la data* e *il comando o il ledger* che lo
ha prodotto (CLAUDE.md: «a number quoted in a spec names the command that produces it»).

---

## 1. Che cos'è (e che cos'è la specifica)

Questo mockup ipotizza la **console operatore** di Claimstone: una vista sullo stato di un round e — nelle
parti marcate come estensioni — un banco di lettura e un compositore di comandi per operazioni che oggi
vivono nel CLI.

Il progetto ha già una specifica approvata per la dashboard: **`docs/superpowers/specs/2026-09-22-dashboard-design.md`**
(status: approved, not implemented). Regole principali di quella spec, che il mockup segue:

| § | Regola | Come appare nel mockup |
|---|---|---|
| §1 | Vista **derivata e di sola lettura**: legge i JSONL, calcola, non scrive mai | nessun elemento esegue: al massimo *compone comandi* da copiare |
| §3 | `round_state.py` (puro, testabile) separato da `dashboard.py` (solo trasporto) | card "Stato del round — StageState (§4)" |
| §4 | `inputs/outputs/rejected` sono `int \| None`: «—» = *non conoscibile in principio*, **mai** zero | tabella StageState; colonna Review della spina |
| §5 | La spina delle domande è il cuore; copertura = *fonti che ne parlano / fonti esaminate* **post-review**; ripartizione **per classe prima dell'aggregato** | vista Domande |
| §6 | Una regola di progresso per fase: discover mai in percentuale (e con canale unico la completezza *non è stimabile*); extract con ETA **accanto al backend** che l'ha prodotta; synthesize senza progresso | card Pipeline, ispettore di fase |
| §7 | Log attività: righe più recenti, «in corso» **inferito** dall'mtime (<30 s) e dichiarato inferenza | vista Attività live |
| §8 | Sette regole di onestà (vedi §5 di questo documento) | trasversali |
| §9–10 | `claimstone serve` su 127.0.0.1, rotte GET soltanto (405 altrove), stateless, coda strappata tollerata | card "Console & trasporto" in Amministrazione |
| §11 | Un documento HTML autonomo: inline CSS/JS, **niente CDN, niente web font, niente librerie di chart**; leggibile in chiaro e scuro; il colore non porta mai il significato da solo | il file è un unico `.html` senza dipendenze |
| §13 | **Fuori ambito, ora o poi**: piano di controllo, round-su-round, multi-progetto | le estensioni non eseguono: la sezione Amministrazione ispeziona e *compone*; il confronto tra progetti è dichiarato «tre popolazioni», non un trend |

Nota sul numero di stati: la spec (§8.5) dice «quattro stati, visivamente quattro» — i suoi quattro sono
SUPPORTED, CONTRADICTED, UNANSWERED_IN_LITERATURE, **NEVER_ASKED**. Lo stato aggiunto il 2026-09-25 è
**CONTESTED_IN_LITERATURE** (invariante 2 di `CLAUDE.md`). Gli stati di verdetto sono quindi **cinque**, e il
mockup li rende cinque. Accanto a loro, e mai confuso con loro, l'unico esito categorico del motore:
**NO_VERIFIED_CLAIM** (GUIDE §6) — «nulla è sopravvissuto», che da solo *non distingue* estrazione mancata,
tutto-scartato e domanda mai posta: solo lo screening umano le separa, e quindi NEVER_ASKED resta un verdetto
della persona, mai dedotto dall'assenza di claim.

### Riferimenti di design citati durante la progettazione

- **kestra.io** — topologia dichiarativa del flusso, esecuzioni tracciabili → la striscia pipeline a nodi
- **n8n.io** — ispezione di ogni esecuzione, umano nel ciclo → ispettore di fase, banco di lettura
- **tremor.so** — KPI card, meter, bar list → il linguaggio delle card e delle barre
- **ui.shadcn.com** — componenti composti, tema duale chiaro/scuro
- **rayyan.ai** e il diagramma di flusso **PRISMA** — il funnel con gli esclusi contati, non nascosti

---

## 2. Come si usa il file

- Aprire `mockups/dashboard.html` in un browser. Nessun server, nessuna dipendenza, nessuna richiesta di rete.
- **Tema**: il pulsante ☀/☾ in alto. Alla prima apertura segue il tema di sistema; il primo clic fissa la
  scelta in `localStorage` (chiave `cs-theme`).
- **Palette comandi**: `Ctrl+K`, filtrabile, navigabile con frecce e Invio (focus intrappolato, focus
  ripristinato alla chiusura, `Esc` chiude).
- **Navigazione**: ancore della sidebar (raggiungibili da Tab) o tasti `1`–`8`.
- **Feed attività**: righe simulate ogni ~4 s, dichiarate simulate nella nota. Nella console vera sarebbe
  polling di `/api/state` ogni 2 s con refetch delle rotte pesanti solo al cambio di mtime (§9).
- I selettori progetto/round nella barra sono **disabilitati**: un `serve` per progetto (§13); il mockup
  mostra solo pmc-screen-time.
- I pulsanti «copia comando» (banco di lettura, amministrazione) scrivono negli appunti: **compongono,
  non eseguono**.

---

## 3. Struttura: due gruppi, non otto viste equivalenti

1. **«Il round · spec v1 §4–8»** — Panoramica, Domande, Funnel & scarti, Attività live. La pagina della
   specifica: lettura, denominatori onesti, stime etichettate. La Panoramica contiene **un solo progetto**
   (§13 esclude la vista multi-progetto da qui).
2. **«Estensioni v2 · oltre la spec»** — Pipeline & batch, Andamenti, Adjudication, Amministrazione. Sono le
   funzioni che l'operatore ha chiesto; nessuna esegue: ispezionano (batch, budget, strumenti) o compongono
   comandi (firma, campagne). Il confronto tra progetti vive qui, etichettato «tre popolazioni».

---

## 4. Le viste, una per una

*Snapshot di riferimento: 2026-09-28, profili costruiti alle 12:24.*

### 4.1 Panoramica

**Scopo**: rispondere in una schermata a «quanto corpus abbiamo ottenuto legalmente, contro quale soglia, e
dove si trova il round».

| Elemento | Informazione | Da dove viene |
|---|---|---|
| KPI · Candidati | 40 da manifest curato; 199 scoperti nel pilota, 159 esclusi dal selettore depositi PMC | `candidates.jsonl` + `sources.yaml` |
| KPI · Confermati | 37/40 = **0.93**, floor 0.80 · v1 · 2026-09-27 | `claimstone report` |
| KPI · Annotazioni accettate | **1.721** correnti su 3.389 righe | `claims.jsonl`, ultimo esito per `claim_id` con supersede cross-ledger (D46) |
| KPI · Profili / Verdetti | 8 correnti — Q04 completo, 7 provvisori; **0 firme** | `verdicts` / `adjudications.jsonl` (assente: 0 è un conteggio conoscibile) |
| Pipeline a nodi | 6 fasi + adjudication; discover **canale unico → completezza non stimabile (§6)**; acquire 38/40 −2; normalize 37/38 −1; extract 1.721 + 24 letture mancanti; review Q04 letta, coda 1.679; synthesize 8 profili | `round_state.state()` |
| Soglia del round | solo pmc, marcatore floor a 0.80; rimando ad Andamenti per il confronto tra progetti | `report` |
| Stato del round (§4) | tabella `inputs/outputs/rejected/ultima scrittura`; stessa regola di conteggio per outputs e rejected | `round_state.py` |
| Adesso | Q04 attende la persona (D52); coda review 1.679, estensione a pagamento richiede autorizzazione (D59) | HANDOFF |

### 4.2 Domande — la spina (§5)

**Scopo**: il registro congelato è ciò per cui lo strumento esiste. Una riga per domanda, **nell'ordine del
registro** (v1, 2026-09-28), con i testi veri di `questions.yaml`.

Colonne:

- **Annotazioni · per classe** — conteggio corrente per domanda (252/474/138/42/90/125/427/173, somma 1.721)
  con la ripartizione per classe accanto (tutto ACA in questo round, mostrato, non dato per scontato).
- **Copertura / fonti esaminate** — **post-review**: Q04 4/37; le altre 0/37 *perché non ancora lette* —
  una domanda non reviewata mostra zero fonti confermate, non la conta dei claim grezzi.
- **Review** — Q04 «v2 completa · 4S / 31O / 7 N.A. su 42»; le altre «non eseguita»: *conteggio conoscibile
  di zero review*, distinto dal tasso non ancora misurabile (tooltip esplicito).
- **Stato del profilo** — i blocchi reali dai profili del 12:24 (`awaiting_extract`, `awaiting_review` con
  le code in numero: 252/474/138/90/125/427/173).
- **Verdetto** — chip tratteggiato «—»: nessun verdetto esiste.

Legenda: i **cinque verdetti umani** + **NO_VERIFIED_CLAIM** come esito categorico del motore, visivamente
distinto (tratteggiato ambra) e linguisticamente separato («non un verdetto»). `CONTRADICTED` è **blu**,
non rosso: concludere contro una domanda è un esito riuscito.

### 4.3 Funnel & scarti (§6 "rejections are shown, not hidden")

**Scopo**: il denominatore visibile — una pagina che mostra solo cosa è passato racconta metà della storia.

- **Percorso** (stile PRISMA): 199 scoperti (pilota, 2 canali) → −159 selettore PMC (D41) → 40 da manifest
  (canale unico) → **acquire** 38/40 (−2 BOT_CHALLENGE) → **normalize** 37/38 (−1 NOT_A_DOCUMENT; il dato del
  round resta 37/40 = 0.93) → 2.194 chunk → 1.721 annotazioni correnti (3.389 + 593 righe nei ledger) →
  24 letture senza risposta (effect 0 · het 4 · method 15 · premise 5) → review: Q04 letta, coda 1.679 →
  8 profili → 0 firme.
- **Scarti correnti per motivo — 271** (ultimo esito per `claim_id`, cross-ledger): UNPARSEABLE_VALUE 110,
  NUMBER_NOT_IN_QUOTE 73, VALUE_NOT_IN_QUOTE 42, QUOTE_NOT_FOUND 31, COMPARATIVE_NOT_IN_QUOTE 13,
  SECONDHAND_CLAIM 2. La «misurazione 586 di 593» di HANDOFF è citata **come misura storica con la sua
  data**, non come stato presente: non è riconducibile al mix corrente.
- **Perdite per causa, fase e host**: BOT_CHALLENGE (acquire, 2, sciencedirect.com, *nostra limitazione*)
  distinta da NOT_A_DOCUMENT (normalize, 1, *del contenuto*) e ABSTRACT_ONLY (0 questo round — conteggio
  conoscibile, «non registrato», non «—»).

### 4.4 Attività live (§7)

Le ultime righe dei ledger, più recenti prima. Nel mockup il feed è **simulato** (dichiarato in nota);
il comportamento vero: rilettura da disco a ogni richiesta, nessuna cache, coda strappata saltata con
conteggio dichiarato, «ultima scrittura X s fa» **dichiarata inferenza** da mtime.

### 4.5 Pipeline & batch *(estensione, ispettiva)*

- **Ispettore di fase** (extract): unità di lavoro, letture attese, estrattore
  (`ollama-cloud · deepseek-v4.1-flash`, harness registrato), gate v4 attivo (re-harvest D51/D52: 53 letture
  nuove), regola ETA di §6, completeness 24.
- **Batch** (stile `model-report`): `q04-full-v2` (mistral-large-3:675b, 42/42 valide, D52, corrente),
  `q04-opus-2026-09-27` (task v1, storico), estrattore drainato. Con il vincolo misurato: un piano in
  abbonamento interattivo non è infrastruttura batch (8/43 e 36/42 BACKEND_ERROR, storico).
- **Rigiudica offline**: i quattro percorsi a costo zero — `regate --campaign`, `normalize --force`,
  `extract --harvest`, `model-run --rejudge` — con la regola: append-only, `latest_by`, e *quota ciò che il
  re-harvest ritorna, mai ciò che un campione suggerisce*.

### 4.6 Andamenti *(estensione; §13 rimanda il round-su-round a dopo)*

- **Tre progetti, tre popolazioni**: pilot 0.45 (199 candidati, scoperta aperta), alembic-s4 0.56 (lista
  curata 14/25, soffitto misurato 18/25 = 0.72), pmc r1 0.93 (manifest 40, depositi PMC). **Punti separati,
  nessuna linea**: una traiettoria suggerirebbe un confronto che D24 e la regola dei registri vietano.
- **Il reviewer su claim gate-passed — misurazioni etichettate** per progetto e task:
  pmc·Q04 v2 (mistral) 4S/31O/7NA su 42 [corrente]; pmc·Q04 v1 (opus) 5S/1O/36NA su 42 [storico];
  **alembic-s4·H15** task v1, 23/41 NOT_APPLICABLE [misurazione D40] — H15 è una domanda metodologica *di
  alembic-s4*: mai attribuita a domande PMC.
- **Lane e backend**: D4 (11.6 min/call, ~5/h — misura di *quella* macchina), estrattore, mistral reviewer
  (42/42 valide, coda 1.679), claude-cli storico con i limiti misurati, API a consumo «non misurato qui».
  SameReader vieta all'estrattore di fare da reviewer.

### 4.7 Adjudication — il banco di lettura *(estensione, di sola lettura)*

**Scopo**: ciò che la spec non ha — ma senza diventare una scrittura. Il banco **mostra** il profilo da
leggere e **compone** il comando `claimstone adjudicate …` da copiare nel terminale. La firma resta un gesto
della persona al CLI; la console non firma, non esegue, non è un controllo.

- **Banner**: Q04 completo e in attesa della persona (D52): 4 risultati trattenuti, review v2 completa,
  zero blocchi; i quattro risultati richiedono valutazione umana di rilevanza/posizione.
- **Profilo in lettura** (dal profilo reale del 12:24): scope r1-deposits; 4 risultati da 42 annotazioni
  lette; direzione **SUPPORTS 1 · QUALIFIES 2 · CONTRADICTS 1** — conteggio etichettato conteggio, mai
  pooled (D17); copertura 4/37 post-review; gate_rejected UNPARSEABLE_VALUE 19 · VALUE_NOT_IN_QUOTE 2 ·
  SECONDHAND_CLAIM 1; linkage unestablished; hash completo `9340389c9aac…b20fdd`.
- **Compositore**: i cinque verdetti come radio che *parametrizzano il comando* (la scelta non registra
  nulla); textarea rationale con contatore 120; comando generato con hash completo; pulsanti copia comando
  / esporta rationale. Il rifiuto delle rationale corte e dei profili provvisori resta nel CLI.
- Firma **stale**: se l'evidenza cambia, il verdetto è mostrato con entrambi gli hash, mai silenziosamente
  mantenuto.

### 4.8 Amministrazione *(estensione, ispettiva + compositore)*

Apre con il banner §13 nella forma vincolante: **nessun piano di controllo nel browser, ora o poi** — non
«una revisione datata della spec», che non è negoziabile. Le due ragioni (budget per dominio, console che
diventerebbe scrittore) sono scritte nel banner.

Card:

- **Progetti & contratto** — ispezione dei 3 file; comandi `validate --all-projects` e `import-manifest` da
  copiare; registro domande: ispezione diff v1→bozza, il bump datato resta una mano che edita YAML.
- **Soglia di acquisizione** — floor 0.80 · v1; evidenza contraria D39 (0.64 su OA dichiarato); generatore
  di *bozza di proposta* markdown (la decisione è dell'operatore, in una nuova decisione datata).
- **Campagne & budget** — tabella di sola lettura; compositore che **esige il nome della campagna**:
  senza nome il comando non si genera (specchia il `--campaign` obbligatorio del CLI).
- **Strumenti & versioni** — gate v4 (D46), floor v1, profile v5 (D45), GROBID; il rifiuto di
  `check_instrument_versions` è la funzione.
- **Console & trasporto §9–10** — rotte (`GET /`, `/api/state`, `/api/round`, `/api/questions`,
  `/api/activity?limit=N` cap 500, 405 altrove), poll 2 s, stateless, coda strappata, bind 127.0.0.1.
- **Integrità dello store** — JSONL append-only; `Store.read`/`Store.repair`; corruzione a metà file =
  errore, non da saltare; 271 MB (`du -sh`, 28/09); SQLite solo derivato.

---

## 5. Le regole di onestà (§8) e dove sono incarnate

1. **Nessuna percentuale senza denominatore accanto** → ogni barra e KPI porta `n/N` e la base.
2. **Nessun assente reso come zero** → «—» solo per *non conoscibile in principio*; dove il conteggio è
   conoscibile e vale zero, è scritto zero con il perché («0 verdetti registrati», «ABSTRACT_ONLY: 0, non
   registrato questo round», «review: non eseguita» con tooltip che separa lo zero conteggiato dal tasso
   non misurabile).
3. **Ogni stima porta la parola "stima" e il suo intervallo** → e dove una stima *non esiste* (canale
   unico) è scritto «completezza non stimabile», mai un numero.
4. **Una fase non implementata lo dichiara** → nodo adjudication tratteggiato; nodi bloccati con il motivo.
5. **Gli stati di verdetto sono visualmente distinti** → cinque + NO_VERIFIED_CLAIM separato; colore + parola.
6. **Soglie e versioni dei gate sempre visibili accanto al tasso** → `gate v4`, `floor 0.80 · v1` accanto a ogni cifra.
7. **Sola lettura** → nessun elemento esegue: al massimo compone comandi da copiare.

Accessibilità (estensione della §11): ancore navigabili da Tab, palette con frecce/Invio/focus
trap/ripristino focus, icone sempre visibili sotto 900 px, contrasto `--faint` portato sopra 4.5:1 nei due temi.

---

## 6. Provenienza dei dati — *al 2026-09-28, con il comando*

### Misurati (verificati in questo repository, 28/09)

| Cifra | Comando / fonte | Valore |
|---|---|---|
| annotazioni correnti / scarti correnti | ultimo esito per `claim_id` su `claims.jsonl` ∪ `rejections.jsonl` (supersede D46) | **1.721 / 271** |
| righe grezze claims / rejections / reviews / profiles / chunks | `wc -l store/pmc-screen-time/*.jsonl` | 3.389 / 593 / 126 / 16 / 2.194 |
| annotazioni correnti per domanda | come sopra, per `question` | 252, 474, 138, 42, 90, 125, 427, 173 |
| scarti correnti per motivo | come sopra, per `failure` | 110, 73, 42, 31, 13, 2 |
| profili correnti (12:24) | ultime 8 righe di `profiles.jsonl` | Q04: blocchi [], 4 risultati, 4/37, SUPPORTS 1/QUALIFIES 2/CONTRADICTS 1, sha `9340389c…` |
| review per batch | `reviews.jsonl` per `batch` | q04-opus-2026-09-27: 5S/1O/36NA · q04-full-v2-2026-09-28: 4S/31O/7NA |
| 199/159/40, selettore PMC | `sources.yaml` di pmc-screen-time, D41 | popolazione dichiarata in anticipo |
| 37/40 = 0.93, floor 0.80 v1 | `GUIDE.md` (output di `report`) | il dato del round |
| 24 letture senza risposta | HANDOFF (D52) | effect 0 · het 4 · method 15 · premise 5 |
| coda review residua 1.679; D59 | HANDOFF | fuori da Q04 |
| alembic-s4 14/25 = 0.56, soffitto 18/25 = 0.72 | `sources.yaml` | lista curata |
| pilot 0.45; OA 0.64 (D39) | HANDOFF | popolazioni diverse |
| Q01–Q08 testi e kind | `projects/pmc-screen-time/questions.yaml` | registry v1 congelato |
| locale 11.6 min/call · ~5/h · 1.43 tok/s | `CLAUDE.md` (D4) | misura di quella macchina |
| claude-cli 8/43 e 36/42 BACKEND_ERROR | HANDOFF | storico |
| 23/41 NOT_APPLICABLE su H15 (alembic-s4) | D40/D44 | misurazione, corpus dichiarato |
| «586 di 593 NUMBER_NOT_IN_QUOTE» | HANDOFF | **misura storica datata**: non riconducibile al mix corrente (pmc 73, alembic 1.352 grezzi) |
| store 271 MB · pytest 1006 ok/7 skip | `du -sh store/`; `.venv/bin/pytest -q` (28/09) | |

### Simulati / di design (nessuna pretesa di misura)

- Timestamp delle scritture, righe del feed attività (dichiarate simulate).
- La card budget-per-host oltre i due fatti citati; i nomi visualizzati dei batch non in ledger.
- Le percentuali-barra della copertura (larghezze derivate dagli n/37 reali).

---

## 7. Istruzioni per il revisore (modello)

Se sei un modello a cui viene chiesto di revisionare questo design, questo è il contratto da verificare.
Rispondi punto per punto, citando la sezione del mockup o di questo documento.

1. **Conformità alla spec** (`docs/superpowers/specs/2026-09-22-dashboard-design.md`): ogni §4–§11 è rispettato?
   Dove il mockup se ne allontana, l'allontanamento è tra quelli dichiarati in §3?
2. **Audit delle regole di onestà (§8)**: trova *violazioni residue* — una percentuale senza denominatore, uno
   zero dove il dato è «non conoscibile», una stima senza intervallo o senza la parola *stima*.
3. **Cinque stati + NO_VERIFIED_CLAIM**: distinguibili in forma e parole? `CONTRADICTED` reso come esito
   riuscito (blu)? `NEVER_ASKED` definito via screening umano e mai via assenza di claim?
4. **Accuratezza dei dati**: le cifre di §6 combaciano con le fonti citate? Qualcuna etichettata «misurato»
   non dovrebbe esserlo, o viceversa?
5. **Ambito**: qualche elemento lascia intendere una scrittura o una richiesta di rete non esplicitamente
   marcata e inerte?
6. **Accessibilità**: colore mai solo; contrasto nei due temi; tastiera (Tab, frecce, Invio, Esc).
7. **Coerenza lessicale**: i termini del progetto (ledger, round, floor, gate, kind, awaiting_regate, stale,
   supersede) usati con lo stesso significato del repository?
8. **Proposte**: cosa manca per essere il prodotto di §9 — e quale aggiunta violerebbe un invariante?

Vincolo per il revisore: **non rilittigare una decisione registrata** citando il buonsenso; se contesti una
scelta, trova la sua voce in `DESIGN_DECISIONS.md` e argomenta contro la *misurazione*.

---

## 8. Review applicate — registro

Due review esterne, 2026-09-28 (Claude e Codex). Esito: **tutti i punti P1 corretti**, i punti di ambito
risolti riscrivendo le sezioni come *lettura + composizione comandi*. Esperimento riuscito del caso d'uso
della vista derivata: le cifre del mockup erano vecchie di mezza giornata perché un mockup non può che essere
uno snapshot — la console vera, che rilegge i ledger, non invecchia.

| # | Punto (fonte) | Risoluzione |
|---|---|---|
| 1 | Stato Q04 superato; totali vecchi (Claude P1-1, Codex P1-1) | aggiornato a D52: Q04 completo (4 risultati, 4/37, sha `9340389c…`), 1.721/271, 24 letture, 126 review, snapshot datato in ogni vista |
| 2 | colonna SUPPORTED fondeva OVERSTATED; H15 attribuita a Q05 (Claude P1-2, Codex P1-2) | split esatti per batch (5S/1O, 4S/31O/7NA); H15 riassegnata ad alembic-s4 come *misurazione D40*; l'assegnazione precedente era falsa, non «incerta» |
| 3 | NEVER_ASKED definito come «nessun claim l'ha citata»; quinto stato male attribuito (Claude P1-2, Codex P1-3) | definizione via screening umano; aggiunto NO_VERIFIED_CLAIM come esito del motore; nota corretta: aggiunto CONTESTED_IN_LITERATURE |
| 4 | provenienza solo nel .md; scarti incoerenti (593+138+…≠581) (Claude P1-3, Codex P1-4) | mix reale dei 271 correnti con regola di conteggio unica; «586/593» declassato a misura storica datata; etichette misurato/storico/simulato dentro l'HTML |
| 5 | piano di controllo presentato come negoziabile (Claude P5) | banner riscritto: §13 «ora o poi»; Amministrazione = ispezione + composizione comandi, zero esecuzione |
| 6 | firmare dal browser è una scrittura (Claude P6) | Adjudication → banco di lettura: profilo + compositore del comando `adjudicate` con hash; nessun pulsante di firma |
| 7 | multi-progetto nel gruppo v1 (Claude P7, Codex P2-8) | Soglia mono-progetto in Panoramica; confronto spostato in Andamenti; selettori disabilitati |
| 8 | grafico con linea tra progetti incomparabili; coordinate errate (Claude P8, Codex P2-5) | punti separati, scale derivate dalla stessa formula (y=160−150r), soffitto sotto il floor, etichetta di popolazione per punto |
| 9 | cifre non in tabella di provenienza (878 test, v0.9) (Claude P10, Codex P2-8) | rimosse le non verificabili; pytest e du -sh citati con data |
| 10 | conferma attribuita ad acquire (Claude P11) | acquire 40→38 (−2), normalize 38→37 (−1 NOT_A_DOCUMENT), in funnel e StageState |
| 11 | None≠0 solo parziale; «—» ambiguo (Codex P2-7) | etichette specifiche: «non eseguita», «non registrato questo round», «non misurato qui», «incluso nel piano» |
| 12 | accessibilità: link senza href, palette senza tastiera, icone nascoste <900px, contrasto --faint (Codex P2-6) | ancore reali, palette con frecce/Invio/trap/ripristino, CSS mobile che nasconde solo le etichette, --faint sopra 4.5:1 nei due temi |
| 13 | numerazione palette obsoleta (Codex P2-8) | comandi riordinati sul nav attuale |

*Mockup di design, 2026-09-28. Non è il prodotto: nessuna rotta, nessuna scrittura, nessuna rete. Il passo
successivo è `round_state.py` + `claimstone serve` come da §3 e §9 della spec.*
