# Unpaywall — guida di integrazione tecnica e best practice

> Documento operativo per un modello/agent che deve progettare o sviluppare un sistema di ricerca della letteratura scientifica.
>
> Stato della documentazione verificato: 7 ottobre 2026.

---

## 1. Executive summary

Unpaywall non deve essere considerato un motore di ricerca bibliografica general purpose.

Nel 2026 il suo ruolo ideale è:

1. ricevere un **DOI** già noto;
2. determinare se esiste una copia Open Access;
3. restituire la migliore posizione disponibile;
4. fornire URL del PDF o della landing page;
5. classificare tipo di Open Access, licenza, host e versione del manoscritto.

Il vecchio endpoint di ricerca testuale `GET /v2/search` è stato ritirato il **18 settembre 2026** e restituisce `410 Gone`.

Per la fase di discovery bibliografica bisogna quindi usare principalmente:

- OpenAlex;
- Crossref;
- arXiv, quando appropriato;
- eventualmente altre fonti verticali.

Unpaywall va poi utilizzato come **OA resolver / enrichment layer** sui DOI ottenuti dalle fonti di discovery.

### Risposte rapide

| Domanda | Risposta |
|---|---|
| Serve una API key per la REST API? | **No** |
| Serve registrarsi? | **No**, per la REST API standard |
| Serve indicare qualcosa nella richiesta? | **Sì: un indirizzo email** |
| L'API standard è gratuita? | **Sì** |
| Limite raccomandato | **100.000 chiamate/giorno** |
| Serve un abbonamento? | **No**, salvo Data Feed |
| Serve essere membri? | **No** |
| Esiste un servizio premium/bulk? | **Sì, Data Feed**, a pagamento |
| Serve API key per il Data Feed? | **Sì**, fornita con la sottoscrizione |
| Snapshot Unpaywall gratuita aggiornata? | **Non più prodotta** |
| Alternativa bulk gratuita | **OpenAlex snapshot** |
| Motore di ricerca da usare nel 2026 | **OpenAlex**, non Unpaywall |

---

# 2. Che cos'è Unpaywall

Unpaywall è un database gestito da OurResearch/OpenAlex che raccoglie informazioni sulle copie Open Access della letteratura accademica.

Non aggira paywall e non recupera materiale pirata.

Indicizza copie legalmente disponibili presso:

- publisher;
- repository istituzionali;
- repository disciplinari;
- archivi di preprint;
- altre infrastrutture Open Access.

Unpaywall utilizza anche dati provenienti da fonti aperte come:

- Crossref;
- DOAJ;
- PubMed Central;
- DataCite;

ma la maggior parte della copertura OA deriva dal monitoraggio diretto di **oltre 50.000 location online**.

Dal 2026 Unpaywall e OpenAlex sono ancora più strettamente integrati: Unpaywall gira sui dati OpenAlex. OpenAlex contiene le stesse informazioni OA, ma aggiunge capacità di ricerca, citazioni, autori, venue, topic e altre relazioni.

---

# 3. Ruolo corretto nell'architettura

## 3.1 Pattern raccomandato

```text
USER QUERY
   │
   ▼
QUERY EXPANSION
   │
   ├── OpenAlex
   ├── Crossref
   ├── arXiv
   ├── PubMed / Europe PMC (se dominio biomedicale)
   └── eventuali fonti verticali
   │
   ▼
NORMALIZATION + DEDUPLICATION
   │
   ▼
DOI RESOLUTION
   │
   ▼
UNPAYWALL
   │
   ├── is_oa
   ├── oa_status
   ├── best_oa_location
   ├── oa_locations[]
   ├── version
   ├── license
   └── url_for_pdf
   │
   ▼
FULL-TEXT RETRIEVAL
   │
   ▼
PARSING / CHUNKING / EMBEDDING / ANALYSIS
```

## 3.2 Cosa NON fare

Non usare Unpaywall come:

- motore di keyword search;
- motore semantico;
- indice citazionale;
- sistema di ranking per rilevanza;
- unica fonte bibliografica;
- unica fonte per identificare paper senza DOI.

---

# 4. API REST

Base URL:

```text
https://api.unpaywall.org/v2/
```

Endpoint principale:

```http
GET /v2/{doi}?email=YOUR_EMAIL
```

Esempio:

```bash
curl "https://api.unpaywall.org/v2/10.1038/nature12373?email=research-bot@example.org"
```

## 4.1 Autenticazione

La REST API standard **non richiede una API key**.

È però obbligatorio inviare un indirizzo email tramite il parametro:

```text
email=
```

Esempio:

```text
?email=research-bot@example.org
```

Usare preferibilmente:

- una mailbox monitorata;
- un indirizzo tecnico stabile;
- un indirizzo associato al progetto o all'organizzazione.

Non inserire email casuali o inesistenti.

---

# 5. Rate limit

La documentazione Unpaywall chiede di limitare l'utilizzo a:

```text
100.000 chiamate al giorno
```

Non è necessario avvicinarsi a questo limite in condizioni normali.

Per un literature crawler conviene implementare:

- caching;
- deduplicazione dei DOI;
- retry con backoff;
- rate limiter;
- persistenza dei risultati.

## 5.1 Esempio di rate limiter prudente

Una configurazione conservativa:

```text
concurrency: 5–10
target requests/sec: 2–5
retry: exponential backoff
max retries: 3–5
```

Non è un requisito imposto dalla documentazione: è una scelta architetturale prudente.

Con 100.000 richieste/giorno la media teorica sarebbe circa:

```text
1,157 richieste/secondo
```

ma NON bisogna interpretare il limite giornaliero come autorizzazione a generare burst di questo ordine.

Preferire traffico regolare e moderato.

---

# 6. Endpoint di ricerca ritirato

Il vecchio endpoint:

```http
GET /v2/search?query=...
```

è stato ritirato il:

```text
18 settembre 2026
```

Ora restituisce:

```text
410 Gone
```

Unpaywall raccomanda esplicitamente OpenAlex per la ricerca.

Per esempio:

```text
https://api.openalex.org/works?search=cell%20thermometry
```

Di conseguenza un nuovo progetto NON deve implementare dipendenze dal vecchio endpoint `/v2/search`.

---

# 7. Schema della risposta

Ogni risposta rappresenta un **DOI Object**.

I campi più importanti per un sistema di literature research sono:

```json
{
  "doi": "...",
  "doi_url": "...",
  "title": "...",
  "publisher": "...",
  "published_date": "...",
  "year": 2026,
  "genre": "journal-article",
  "is_oa": true,
  "oa_status": "green",
  "has_repository_copy": true,
  "best_oa_location": {},
  "first_oa_location": {},
  "oa_locations": [],
  "oa_locations_embargoed": []
}
```

Il parser deve essere **forward-compatible**.

La documentazione avverte che nuovi campi possono essere aggiunti in qualsiasi momento.

Quindi:

- non validare la risposta con `additionalProperties: false`;
- ignorare campi sconosciuti;
- non assumere un numero fisso di proprietà.

---

# 8. `is_oa`

```json
"is_oa": true
```

È il controllo più semplice per determinare se Unpaywall conosce almeno una location Open Access.

Concettualmente:

```text
is_oa = best_oa_location != null
```

Uso raccomandato:

```python
if record["is_oa"] and record["best_oa_location"]:
    ...
```

Non assumere che:

```text
is_oa == true
```

implichi necessariamente:

```text
url_for_pdf != null
```

Potrebbe essere disponibile soltanto una landing page.

---

# 9. `best_oa_location`

È normalmente il campo più utile dell'intera risposta.

Unpaywall seleziona la location "migliore" privilegiando, in linea generale:

1. contenuto ospitato dal publisher;
2. versione più vicina alla Version of Record;
3. repository ritenuti più autorevoli.

Esempio:

```json
{
  "endpoint_id": "...",
  "host_type": "repository",
  "is_best": true,
  "license": "cc-by",
  "oa_date": "2025-04-12",
  "url": "...",
  "url_for_landing_page": "...",
  "url_for_pdf": "...",
  "version": "acceptedVersion"
}
```

Per la maggior parte dei sistemi, partire da:

```text
best_oa_location
```

è preferibile a costruire subito un algoritmo proprietario.

---

# 10. `oa_locations`

Contiene tutte le copie OA individuate.

È particolarmente utile quando:

- il PDF della `best_oa_location` non è raggiungibile;
- serve un fallback;
- si vuole preferire un repository specifico;
- serve distinguere versioni;
- si vuole scegliere una licenza specifica;
- si vuole massimizzare il recupero full text.

## Strategia consigliata

1. prova `best_oa_location.url_for_pdf`;
2. se assente o non raggiungibile, prova `best_oa_location.url`;
3. se fallisce, ordina `oa_locations` con uno scoring locale;
4. prova progressivamente le alternative.

---

# 11. `host_type`

Valori principali:

```text
publisher
repository
```

Interpretazione:

### `publisher`

Il contenuto è ospitato dal publisher.

In genere è da preferire perché ha maggiore probabilità di essere:

- Version of Record;
- HTML strutturato;
- PDF ufficiale.

### `repository`

Il contenuto è ospitato in un repository.

Può essere:

- preprint;
- accepted manuscript;
- published version depositata.

Non va considerato automaticamente di qualità inferiore: bisogna controllare `version`.

---

# 12. `version`

Valori principali:

```text
submittedVersion
acceptedVersion
publishedVersion
```

## `submittedVersion`

Manoscritto prima della peer review.

Tipicamente:

- preprint;
- versione autore;
- contenuto scientifico potenzialmente diverso dal paper finale.

## `acceptedVersion`

Versione accettata dopo peer review ma senza impaginazione editoriale definitiva.

È spesso una fonte eccellente per analisi del contenuto scientifico.

## `publishedVersion`

Version of Record.

È la versione da preferire quando disponibile.

## Ranking consigliato

```text
publishedVersion
    >
acceptedVersion
    >
submittedVersion
```

Per analisi scientifiche sensibili, salvare sempre il valore di `version` insieme al testo acquisito.

---

# 13. `license`

Esempi:

```text
cc-by
cc-by-nc
cc-by-sa
implied-oa
null
```

`null` non significa necessariamente che il documento non sia accessibile.

Significa che Unpaywall non ha determinato una licenza OA valida per quella location.

`implied-oa` indica evidenza di Open Access senza una licenza esplicitamente rilevata sulla pagina.

Non usare quindi:

```python
license is not None
```

come unico criterio per decidere se scaricare il documento.

Usare invece la combinazione:

```text
is_oa
best_oa_location
url_for_pdf / url
version
license
```

---

# 14. `oa_status`

Possibili valori:

```text
gold
hybrid
bronze
green
closed
```

## Gold

Articolo pubblicato in una rivista completamente Open Access.

## Hybrid

Articolo Open Access all'interno di una rivista che pubblica anche articoli a pagamento.

## Bronze

Articolo disponibile gratuitamente sul sito del publisher, ma senza licenza OA chiaramente rilevata.

È importante trattarlo con cautela.

Il fatto che sia leggibile oggi non garantisce necessariamente disponibilità permanente.

## Green

Copia disponibile in un repository.

## Closed

Nessuna copia OA nota a Unpaywall.

Per un agente di ricerca non bisogna filtrare esclusivamente `gold`.

Un paper `green` può essere perfettamente valido e avere una `acceptedVersion` peer-reviewed.

---

# 15. URL utili

Una location può avere:

```text
url
url_for_landing_page
url_for_pdf
```

## Ordine consigliato per full-text ingestion

```text
url_for_pdf
   ↓
url
   ↓
url_for_landing_page
```

Ma verificare sempre:

- HTTP status;
- Content-Type;
- redirect;
- dimensione;
- contenuto reale.

Un URL con suffisso `.pdf` non garantisce necessariamente un PDF e un URL senza `.pdf` potrebbe comunque restituirlo.

---

# 16. Strategia di full-text retrieval

Pseudo-codice:

```python
async def get_open_fulltext(doi):
    record = await unpaywall_lookup(doi)

    if not record or not record.get("is_oa"):
        return None

    candidates = []

    best = record.get("best_oa_location")
    if best:
        candidates.append(best)

    for loc in record.get("oa_locations", []):
        if not loc.get("is_best"):
            candidates.append(loc)

    candidates = rank_locations(candidates)

    for location in candidates:
        for url in candidate_urls(location):
            result = await fetch_and_validate(url)

            if result.is_valid_fulltext:
                return {
                    "content": result.content,
                    "doi": doi,
                    "source": "unpaywall",
                    "location": location,
                }

    return None
```

---

# 17. Ranking locale consigliato

Unpaywall ha già il proprio `best_oa_location`, ma un sistema avanzato può usare uno scoring secondario.

Esempio:

```text
+100 publishedVersion
 +70 acceptedVersion
 +30 submittedVersion

 +40 publisher
 +20 repository

 +30 url_for_pdf presente
 +20 licenza Creative Commons
 +10 repository affidabile

 -50 URL non raggiungibile
 -30 content-type non coerente
```

Non sostituire arbitrariamente `best_oa_location`: usare questo ranking principalmente come fallback.

---

# 18. Normalizzazione DOI

Prima della chiamata:

1. lowercase;
2. rimuovere `https://doi.org/`;
3. rimuovere `http://doi.org/`;
4. rimuovere `doi:`;
5. trim whitespace;
6. URL-encode quando necessario.

Esempio:

```text
https://doi.org/10.1038/NATURE12373
```

diventa:

```text
10.1038/nature12373
```

Unpaywall restituisce normalmente il DOI lowercase.

---

# 19. Deduplicazione

La chiave primaria raccomandata è:

```text
normalized_doi
```

Database:

```sql
CREATE TABLE oa_resolutions (
    doi VARCHAR(255) PRIMARY KEY,
    is_oa BOOLEAN,
    oa_status VARCHAR(32),
    best_url TEXT,
    pdf_url TEXT,
    version VARCHAR(64),
    license VARCHAR(128),
    raw_response JSON,
    retrieved_at TIMESTAMP,
    source_updated_at TIMESTAMP NULL
);
```

Questo evita chiamate ripetute.

---

# 20. Caching

Unpaywall cambia nel tempo:

- vengono pubblicati nuovi articoli;
- scadono embargo;
- gli autori depositano copie;
- cambiano disponibilità e licenze;
- alcuni contenuti Bronze possono tornare chiusi.

Quindi la cache non dovrebbe essere eterna.

## TTL suggeriti

Questi TTL sono raccomandazioni progettuali, non limiti ufficiali.

### Record OA positivo

```text
30–90 giorni
```

### Record Closed

```text
7–30 giorni
```

È utile aggiornare più spesso i record chiusi perché una nuova copia OA può apparire successivamente.

### Errori temporanei

```text
5–60 minuti
```

---

# 21. Error handling

Gestire almeno:

```text
200
404
410
429
5xx
timeout
network error
invalid JSON
```

## 404

Possibili cause:

- DOI inesistente;
- DOI non conosciuto;
- DOI malformato.

Non interpretare automaticamente 404 come "closed access".

Sono concetti diversi.

## 410

Se proviene dal vecchio `/search`, significa che l'endpoint è stato ritirato.

## 429

Applicare:

```text
exponential backoff + jitter
```

Esempio:

```text
1s
2s
4s
8s
16s
```

## 5xx

Retry limitato.

Non creare loop infiniti.

---

# 22. Timeout e retry

Configurazione pratica:

```yaml
connect_timeout: 5s
read_timeout: 15s
max_retries: 4
backoff: exponential
jitter: true
```

Separare:

- retry chiamata Unpaywall;
- retry download del PDF.

Unpaywall può rispondere perfettamente anche se il server repository indicato è temporaneamente offline.

---

# 23. Simple Query Tool

Per piccoli batch manuali Unpaywall offre il Simple Query Tool.

Supporta fino a:

```text
500 DOI
```

per richiesta/interazione.

Produce:

- CSV;
- JSON Lines.

È utile per:

- test;
- validazione;
- debugging;
- analisi ad hoc.

Non è adatto a una pipeline automatizzata di produzione.

---

# 24. Database snapshot

Le vecchie snapshot semestrali Unpaywall **non vengono più prodotte**.

La documentazione raccomanda di utilizzare:

```text
OpenAlex snapshot
```

che contiene tutti i dati Unpaywall e molte informazioni aggiuntive.

La snapshot OpenAlex viene indicata come aggiornata circa una volta al mese.

Per un progetto nuovo:

```text
NON costruire un'importazione basata sulle vecchie snapshot Unpaywall.
```

---

# 25. Data Feed

Il Data Feed è l'opzione commerciale/premium.

È pensato per organizzazioni che vogliono mantenere una copia locale molto aggiornata del database.

Offre:

- snapshot completa corrente;
- aggiornamento della snapshot giornaliero;
- changefile giornalieri;
- changefile settimanali;
- API per elencare i changefile.

La documentazione parla di circa:

```text
120 milioni di record
```

nella snapshot completa.

## Accesso

Il Data Feed richiede:

- sottoscrizione;
- accordo commerciale;
- API key.

La tariffazione non è pubblica/fissa sul sito.

Per un preventivo bisogna contattare OurResearch indicando:

- dimensione dell'organizzazione;
- use case.

## Quando serve

Usare Data Feed se:

- si devono risolvere milioni di DOI;
- serve aggiornamento quotidiano;
- non si vuole dipendere da chiamate API online;
- si sta costruendo un servizio enterprise ad alto throughput;
- il database OA deve essere interrogato localmente.

## Quando NON serve

Non è necessario se:

- il corpus è di decine o migliaia di paper;
- si fanno ricerche periodiche;
- 100.000 lookup/giorno sono sufficienti;
- è accettabile interrogare Unpaywall on-demand.

---

# 26. Data Feed changefiles

Endpoint:

```http
GET https://api.unpaywall.org/feed/changefiles
    ?api_key=YOUR_API_KEY
    &interval=day
```

oppure:

```text
interval=week
```

Strategia:

```text
FULL SNAPSHOT
     │
     ▼
IMPORT DB
     │
     ▼
DAILY CHANGEFILE
     │
     ▼
UPSERT BY DOI
     │
     ▼
NEXT CHANGEFILE
```

Ogni record del changefile dovrebbe sovrascrivere/aggiornare il record precedente per lo stesso DOI.

---

# 27. Qualità dei risultati

Unpaywall è particolarmente affidabile per la domanda:

> "Esiste una copia Open Access legalmente disponibile di questo DOI, e dove si trova?"

Non è invece il sistema corretto per la domanda:

> "Quali sono i migliori paper su questo argomento?"

Per questo motivo bisogna separare due concetti:

## Retrieval quality

Quanto è buono Unpaywall nel trovare una copia OA di un DOI noto.

## Discovery quality

Quanto è buono il sistema nel trovare tutti i paper scientificamente rilevanti.

Unpaywall ottimizza soprattutto il primo problema.

---

# 28. Migliorare recall e precision

Per massimizzare il recall complessivo:

```text
OpenAlex search
      +
Crossref search
      +
arXiv search
      +
fonti disciplinari
      ↓
DOI normalization
      ↓
deduplication
      ↓
Unpaywall
```

Questo approccio è superiore a:

```text
Unpaywall only
```

perché molti documenti possono:

- non avere DOI;
- essere preprint;
- essere indicizzati diversamente;
- essere presenti su arXiv prima dell'assegnazione DOI.

---

# 29. Relazione con OpenAlex

Nel 2026 OpenAlex deve essere considerato parte fondamentale della strategia Unpaywall.

Unpaywall dichiara che:

- OpenAlex è il suo successore;
- è sviluppato dallo stesso team;
- contiene le informazioni OA di Unpaywall;
- aggiunge search, citazioni, autori, venue e topic;
- Unpaywall gira ora sul database OpenAlex.

Quindi, per un progetto greenfield, valutare seriamente se interrogare direttamente OpenAlex durante la discovery e usare Unpaywall solo dove serve mantenere compatibilità o sfruttare il formato Unpaywall.

---

# 30. Pipeline raccomandata per literature research

```text
1. User query
2. Query decomposition
3. Synonym / acronym expansion
4. Search OpenAlex
5. Search Crossref
6. Search arXiv
7. Search domain-specific indexes
8. Normalize metadata
9. DOI normalization
10. Deduplicate
11. Rank by scientific relevance
12. Call Unpaywall for DOI-bearing papers
13. Retrieve OA full text
14. Validate document
15. Parse
16. Chunk
17. Embed/index
18. Extract evidence
19. Citation graph expansion
20. Repeat until convergence
```

---

# 31. Priorità delle fonti

Per un sistema generico:

```text
DISCOVERY
1. OpenAlex
2. Crossref
3. arXiv
4. domain indexes

FULL TEXT RESOLUTION
1. Unpaywall
2. URLs already supplied by source
3. publisher/repository fallback
```

Non usare Unpaywall per sostituire Crossref.

Crossref e Unpaywall risolvono problemi diversi.

---

# 32. Strategia "quality first"

Per massimizzare la qualità:

1. usa OpenAlex/Crossref per metadata discovery;
2. conserva DOI, titolo, autori, anno e venue;
3. deduplica prima di interrogare Unpaywall;
4. preferisci `publishedVersion`;
5. fallback su `acceptedVersion`;
6. tratta `submittedVersion` come preprint;
7. registra esplicitamente la versione usata;
8. registra URL e licenza;
9. conserva risposta raw di Unpaywall;
10. non confondere disponibilità OA con qualità scientifica.

---

# 33. Strategia "quantity first"

Per massimizzare il numero di documenti recuperati:

1. esegui discovery multi-source;
2. non richiedere DOI come condizione per conservare un candidato;
3. risolvi DOI mancanti tramite Crossref/OpenAlex;
4. chiama Unpaywall sui DOI risolti;
5. esamina tutte le `oa_locations`;
6. usa fallback URL;
7. riprova in futuro i record `closed`;
8. conserva i preprint separatamente;
9. usa citation expansion;
10. usa Data Feed/OpenAlex snapshot solo per scale molto elevate.

---

# 34. Versione scientifica e provenance

Ogni documento acquisito dovrebbe conservare almeno:

```json
{
  "doi": "...",
  "source": "unpaywall",
  "oa_status": "...",
  "host_type": "...",
  "version": "...",
  "license": "...",
  "landing_page_url": "...",
  "pdf_url": "...",
  "unpaywall_retrieved_at": "...",
  "fulltext_retrieved_at": "..."
}
```

Questo è essenziale per:

- audit;
- riproducibilità;
- citazioni;
- debugging;
- aggiornamento futuro.

---

# 35. Non confondere Open Access con peer review

Unpaywall segnala la disponibilità OA.

Non certifica la qualità scientifica.

In particolare:

```text
submittedVersion
```

può essere un preprint non peer-reviewed.

Un agente deve quindi mantenere separati:

```text
ACCESS STATUS
```

e:

```text
SCIENTIFIC QUALITY
```

La qualità può essere valutata con altri segnali:

- venue;
- peer review status;
- citation count;
- study design;
- replication;
- retraction status;
- publication date;
- methodological quality.

---

# 36. Controllo retraction e correction

Unpaywall non deve essere usato come unico controllo per:

- retraction;
- expression of concern;
- erratum;
- correction.

Aggiungere fonti specifiche o metadata provider quando questo è rilevante.

Un documento OA può essere comunque:

- ritirato;
- corretto;
- superato.

---

# 37. Sicurezza durante il download

Gli URL restituiti da Unpaywall puntano a servizi esterni.

Il downloader deve quindi essere trattato come un componente che accede a URL non fidati.

Implementare:

- timeout;
- limite massimo file;
- validazione MIME;
- blocco di IP privati/loopback dopo DNS resolution;
- protezione SSRF;
- redirect limit;
- antivirus se necessario;
- sandbox del parser.

Esempio di limite:

```text
MAX_PDF_SIZE = 100 MB
```

da adattare al progetto.

---

# 38. Privacy

L'API richiede l'invio di un indirizzo email.

La privacy policy segnala che tale indirizzo può essere raccolto quando viene fornito nelle API call.

Per un'applicazione:

- usare una mailbox tecnica;
- non usare l'email dell'utente finale;
- non passare informazioni personali nel parametro;
- configurare l'indirizzo via environment variable.

Esempio:

```bash
UNPAYWALL_EMAIL=literature-bot@example.org
```

---

# 39. Configurazione consigliata

```yaml
unpaywall:
  base_url: "https://api.unpaywall.org/v2"
  email_env: "UNPAYWALL_EMAIL"

  timeout_seconds: 15

  rate_limit:
    requests_per_second: 3
    concurrency: 8

  retry:
    max_attempts: 4
    exponential_backoff: true
    jitter: true

  cache:
    oa_ttl_days: 60
    closed_ttl_days: 14
    error_ttl_minutes: 30
```

Questi valori sono suggerimenti applicativi, non valori ufficiali Unpaywall.

---

# 40. Modello dati applicativo

```sql
CREATE TABLE publications (
    id BIGINT PRIMARY KEY,
    doi VARCHAR(255) UNIQUE,
    title TEXT,
    publication_year INTEGER
);

CREATE TABLE unpaywall_records (
    doi VARCHAR(255) PRIMARY KEY,
    is_oa BOOLEAN NOT NULL,
    oa_status VARCHAR(32),
    best_location JSON,
    all_locations JSON,
    raw_response JSON NOT NULL,
    fetched_at TIMESTAMP NOT NULL,
    source_updated_at TIMESTAMP NULL
);

CREATE TABLE fulltext_assets (
    id BIGINT PRIMARY KEY,
    doi VARCHAR(255),
    source VARCHAR(32),
    version VARCHAR(64),
    license VARCHAR(128),
    url TEXT,
    content_hash VARCHAR(128),
    downloaded_at TIMESTAMP
);
```

---

# 41. Evitare duplicati di full text

Uno stesso paper può essere presente in più repository.

Calcolare un hash:

```text
SHA-256
```

del file o del testo normalizzato.

Esempio:

```python
sha256(pdf_bytes).hexdigest()
```

Deduplicare sia per:

```text
DOI
```

sia eventualmente per:

```text
content_hash
```

---

# 42. Osservabilità

Metriche consigliate:

```text
unpaywall_requests_total
unpaywall_success_total
unpaywall_404_total
unpaywall_429_total
unpaywall_5xx_total

unpaywall_cache_hit_ratio

unpaywall_oa_found_total
unpaywall_closed_total

unpaywall_pdf_url_found_total
unpaywall_pdf_download_success_total
unpaywall_pdf_download_failure_total
```

Distribuzioni utili:

```text
oa_status
version
host_type
license
```

---

# 43. Logging

Log strutturato:

```json
{
  "event": "unpaywall_lookup",
  "doi": "10.xxxx/xxxx",
  "status_code": 200,
  "is_oa": true,
  "oa_status": "green",
  "version": "acceptedVersion",
  "cache": false,
  "duration_ms": 142
}
```

Non loggare dati utente non necessari.

---

# 44. Testing

## Unit test

Testare:

- DOI normalization;
- parsing risposta;
- `best_oa_location == null`;
- PDF URL null;
- licenza null;
- campi aggiuntivi sconosciuti;
- malformed response.

## Integration test

Usare un set stabile di DOI:

- OA publisher;
- Green OA;
- closed;
- preprint;
- DOI inesistente.

Non assumere però che lo stato OA rimanga immutabile nel tempo.

---

# 45. Fallback se Unpaywall non trova il paper

```text
Unpaywall miss
     │
     ├── OpenAlex locations
     ├── arXiv
     ├── Europe PMC / PubMed Central
     ├── repository URL già noto
     ├── publisher landing page
     └── no legal OA copy found
```

Non effettuare scraping aggressivo o bypass di paywall.

---

# 46. Sinergia con Crossref

Crossref è ottimo per:

- DOI;
- metadata;
- title;
- authors;
- publisher;
- references;
- query bibliografiche.

Unpaywall è ottimo per:

- OA status;
- OA locations;
- PDF OA;
- manuscript version;
- OA license.

Pattern:

```text
Crossref
    ↓
DOI
    ↓
Unpaywall
    ↓
OA full text
```

---

# 47. Sinergia con arXiv

arXiv è importante perché:

- alcuni paper non hanno ancora DOI;
- il preprint può esistere prima della pubblicazione;
- spesso il full text è immediatamente disponibile.

Pattern:

```text
arXiv record
   │
   ├── DOI exists ──► Unpaywall
   │
   └── no DOI ─────► use arXiv full text directly
```

Non scartare record senza DOI prima di aver valutato la fonte.

---

# 48. Sinergia con OpenAlex

Architettura moderna raccomandata:

```text
OpenAlex = discovery + graph + metadata + OA hints
Unpaywall = DOI-centric OA resolver
Crossref  = DOI metadata authority / complement
arXiv     = preprint source
```

Per molti progetti OpenAlex può già fornire:

```text
open_access
best_oa_location
```

Quindi evitare doppie chiamate inutili quando l'informazione OA già presente è sufficiente.

Interrogare Unpaywall direttamente quando:

- si vuole il formato/schema Unpaywall;
- si vuole compatibilità con sistemi esistenti;
- si vuole verificare direttamente il resolver DOI;
- il workflow è già costruito attorno all'API Unpaywall.

---

# 49. Regola per evitare chiamate ridondanti

Pseudo-codice:

```python
if candidate.openalex_best_oa_location_is_sufficient:
    use_openalex_data()

elif candidate.doi:
    use_unpaywall(candidate.doi)

elif candidate.arxiv_id:
    use_arxiv()

else:
    try_resolve_doi()
```

Questo riduce:

- latenza;
- traffico;
- rate-limit consumption.

---

# 50. API key, abbonamento e membership

## REST API

```text
API key: NO
Subscription: NO
Membership: NO
Registration: NO
Email parameter: YES
Cost: FREE
```

## Simple Query Tool

```text
API key: NO
Subscription: NO
Membership: NO
Cost: FREE
```

## Data Feed

```text
API key: YES
Subscription: YES
Membership: NO
Pricing: custom quote
```

---

# 51. Quando passare al Data Feed

Valutare il Data Feed quando:

```text
daily DOI lookup volume ≈ 100k+
```

oppure quando:

- la latenza API diventa un problema;
- serve una copia locale;
- serve aggiornamento giornaliero;
- il prodotto dipende criticamente da Unpaywall;
- bisogna elaborare una porzione enorme del DOI space.

Prima di acquistarlo valutare anche la snapshot OpenAlex.

---

# 52. Decision tree

```text
Quanti DOI devo controllare?

< 500 manualmente
    └── Simple Query Tool

fino a decine/migliaia al giorno
    └── REST API + cache

fino a ~100k/giorno
    └── REST API + cache + throttling

milioni / bulk
    ├── OpenAlex snapshot
    └── Data Feed se servono aggiornamenti Unpaywall giornalieri
```

---

# 53. Algoritmo raccomandato completo

```python
async def enrich_candidate(candidate):

    candidate = normalize_metadata(candidate)

    if not candidate.doi:
        candidate.doi = await resolve_doi(candidate)

    # Non perdere paper senza DOI.
    if not candidate.doi:
        return await handle_non_doi_candidate(candidate)

    cached = await oa_cache.get(candidate.doi)

    if cached and not cached.is_expired:
        return merge(candidate, cached)

    response = await unpaywall.get(candidate.doi)

    if response.status == 404:
        await cache_not_found(candidate.doi)
        return candidate

    oa = parse_unpaywall(response)

    await oa_cache.store(
        candidate.doi,
        oa,
        ttl=ttl_for(oa)
    )

    candidate = merge(candidate, oa)

    if oa.is_oa:
        fulltext = await retrieve_best_fulltext(oa)

        if fulltext:
            candidate.fulltext = fulltext

    return candidate
```

---

# 54. Cosa deve fare un LLM developer

Quando implementi Unpaywall:

1. **NON** creare una API key per la REST API.
2. Configura `UNPAYWALL_EMAIL`.
3. Implementa solo API v2.
4. NON usare `/v2/search`.
5. Normalizza DOI.
6. Inserisci cache persistente.
7. Implementa rate limiting.
8. Implementa retry con backoff.
9. Conserva la risposta raw.
10. Usa `best_oa_location` come prima scelta.
11. Implementa fallback su `oa_locations`.
12. Registra `version`.
13. Registra `license`.
14. Non richiedere `license != null` per accettare un documento.
15. Non assumere che OA significhi peer-reviewed.
16. Non assumere che `closed` rimanga closed per sempre.
17. Ri-controlla periodicamente i record closed.
18. Proteggi il downloader da SSRF e file malevoli.
19. Deduplica per DOI e hash.
20. Integra Unpaywall dentro una pipeline multi-source.

---

# 55. Acceptance criteria

L'integrazione può essere considerata corretta quando:

- [ ] recupera correttamente un DOI OA;
- [ ] gestisce un DOI closed;
- [ ] gestisce 404;
- [ ] gestisce timeout;
- [ ] gestisce 429;
- [ ] usa cache;
- [ ] normalizza DOI;
- [ ] usa email configurabile;
- [ ] non usa API key per REST;
- [ ] non usa `/v2/search`;
- [ ] salva `oa_status`;
- [ ] salva `version`;
- [ ] salva `license`;
- [ ] salva best location;
- [ ] mantiene tutte le alternative;
- [ ] verifica HTTP e MIME del PDF;
- [ ] prova fallback se il PDF primario fallisce;
- [ ] non perde paper senza DOI;
- [ ] espone metriche;
- [ ] conserva provenance.

---

# 56. Raccomandazione architetturale finale

Per un nuovo literature-research system:

```text
             ┌──────────────┐
             │ Query Agent  │
             └──────┬───────┘
                    │
       ┌────────────┼────────────┐
       ▼            ▼            ▼
   OpenAlex      Crossref       arXiv
       │            │            │
       └────────────┼────────────┘
                    ▼
             Normalization
                    │
                    ▼
              Deduplication
                    │
                    ▼
             DOI Resolution
                    │
                    ▼
              Unpaywall
                    │
          ┌─────────┴──────────┐
          ▼                    ▼
  best_oa_location       oa_locations[]
          │                    │
          └─────────┬──────────┘
                    ▼
             Full-text fetch
                    │
                    ▼
              PDF validator
                    │
                    ▼
               Text parser
                    │
                    ▼
                 Index
```

Questa architettura offre un buon equilibrio fra:

- qualità;
- recall;
- legalità;
- scalabilità;
- costo;
- riproducibilità.

---

# 57. Conclusione operativa

La regola più importante è:

> **Use Unpaywall to locate Open Access copies of known DOI-bearing works; do not use it as your primary literature search engine.**

Nel 2026 la combinazione consigliata è:

```text
OpenAlex + Crossref + arXiv
            ↓
       DOI candidates
            ↓
        Unpaywall
            ↓
     legal OA full text
```

Per la maggior parte dei progetti:

```text
REST API gratuita + cache
```

è più che sufficiente.

Non servono:

```text
API key
membership
paid subscription
```

per l'API standard.

Il Data Feed è giustificato solo per esigenze enterprise/bulk con aggiornamenti giornalieri e accesso locale a una porzione molto ampia o all'intero database.

---

# 58. Fonti ufficiali consultate

Documentazione ufficiale Unpaywall / OurResearch:

- REST API  
  https://unpaywall.org/api

- Data format  
  https://unpaywall.org/data-format

- Data sources  
  https://unpaywall.org/sources

- Products  
  https://unpaywall.org/products/

- Simple Query Tool  
  https://unpaywall.org/products/simple-query-tool

- Data Feed  
  https://unpaywall.org/products/data-feed

- Data Feed changefiles  
  https://unpaywall.org/products/data-feed/changefiles

- Database Snapshot  
  https://unpaywall.org/products/snapshot

- FAQ  
  https://unpaywall.org/faq

- Terms of Service  
  https://unpaywall.org/legal/terms-of-service

- Privacy Policy  
  https://unpaywall.org/legal/privacy

- Unpaywall → OpenAlex / retired article search  
  https://unpaywall.org/articles

- OpenAlex  
  https://openalex.org/

Per cambiamenti futuri dell'API è opportuno controllare periodicamente la documentazione ufficiale e la mailing list indicata da Unpaywall.

---

## TL;DR per il coding agent

```yaml
purpose: "Resolve legal Open Access locations for known DOIs"

api:
  version: 2
  key_required: false
  email_required: true
  cost: free
  daily_limit: 100000

search:
  unpaywall_search_endpoint: "RETIRED"
  retired_since: "2026-09-18"
  use_instead: "OpenAlex"

recommended_stack:
  discovery:
    - OpenAlex
    - Crossref
    - arXiv
  oa_resolution:
    - Unpaywall

lookup_priority:
  - best_oa_location.url_for_pdf
  - best_oa_location.url
  - alternative oa_locations

version_priority:
  - publishedVersion
  - acceptedVersion
  - submittedVersion

bulk:
  free: "OpenAlex snapshot"
  paid_daily_updates: "Unpaywall Data Feed"

must_have:
  - DOI normalization
  - persistent cache
  - retry/backoff
  - rate limiting
  - provenance
  - fulltext validation
  - SSRF protection
  - deduplication
```
