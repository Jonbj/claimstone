# Integrazione arXiv — guida tecnica per massimizzare qualità e quantità dei risultati

> Documento operativo per un modello/agent che deve progettare o implementare un'integrazione con arXiv.
>
> Verificato sulla documentazione ufficiale arXiv il 7 ottobre 2026.

## 1. Executive summary

Per accedere ai metadati pubblici di arXiv **non serve una API key, non serve un abbonamento e non è necessario essere membri di arXiv**.

arXiv espone diversi meccanismi, che vanno usati per scopi diversi:

| Esigenza | Interfaccia consigliata |
|---|---|
| Cercare paper per parole chiave, autore, titolo, abstract, categoria o data | **arXiv Search API** |
| Recuperare un paper noto tramite arXiv ID | **Search API con `id_list`** |
| Fare harvesting massivo o mantenere un mirror dei metadati | **OAI-PMH** |
| Sincronizzare quotidianamente nuovi record/modifiche | **OAI-PMH incrementale** |
| Recuperare feed giornalieri per categoria | RSS |
| Analizzare l'intero corpus/full text | **Kaggle o Amazon S3** |
| Scaricare l'intero corpus di PDF/source | **Amazon S3 Requester Pays**, non crawling del sito |
| Discovery ad alta precisione | Search API con query multiple e mirate |
| Discovery ad alto recall | Search API multi-query + OAI-PMH/local index |

Per un sistema serio di literature discovery, la soluzione migliore non è utilizzare un'unica query arXiv molto ampia. È preferibile:

1. generare più query complementari;
2. interrogare separatamente titolo, abstract e categorie;
3. usare sinonimi, acronimi e varianti;
4. recuperare risultati ordinati sia per relevance sia per data;
5. deduplicare per arXiv ID canonico;
6. indicizzare localmente i metadati raccolti;
7. se il progetto richiede copertura molto ampia, usare OAI-PMH anziché paginare indefinitamente la Search API;
8. usare PDF/source solo quando realmente necessari.

---

# 2. Accesso, API key, account, abbonamenti e membership

## 2.1 API key

La **legacy arXiv Search API pubblica non richiede API key**.

L'endpoint è pubblico e viene interrogato direttamente via HTTP GET/POST.

Endpoint:

```text
https://export.arxiv.org/api/query
```

La documentazione storica mostra talvolta URL `http://`; nell'implementazione è preferibile usare HTTPS quando disponibile.

Esempio:

```text
https://export.arxiv.org/api/query?search_query=all:transformer&start=0&max_results=100
```

## 2.2 Account arXiv

Un account arXiv non è necessario per effettuare ricerche tramite Search API o OAI-PMH.

## 2.3 Abbonamento

Non esiste un abbonamento commerciale necessario per usare le API pubbliche.

L'accesso ai metadati tramite le API pubbliche è gratuito, nei limiti delle policy e dei rate limit.

## 2.4 Membership

Essere membri/supporter di arXiv **non è un prerequisito tecnico per accedere alle API**.

La membership di arXiv riguarda principalmente il sostegno istituzionale e la governance, non un livello premium delle API pubbliche.

## 2.5 Uso commerciale

arXiv permette l'utilizzo delle proprie API anche per progetti commerciali, ma invita esplicitamente tali progetti a leggere:

- Terms of Use;
- API documentation;
- bulk data policies;
- brand guidelines.

Per i metadati descrittivi, arXiv indica CC0.

Il contenuto completo dei paper, invece, resta soggetto alla licenza/copyright del singolo articolo.

---

# 3. Rate limit: requisito fondamentale

Le Terms of Use ufficiali stabiliscono per le API legacy, includendo:

- arXiv Search API;
- OAI-PMH;
- RSS;

il seguente limite:

> non più di **una richiesta ogni tre secondi**, con **una sola connessione alla volta**.

Il limite si applica complessivamente a **tutte le macchine sotto il controllo dello stesso utilizzatore**.

Quindi NON è consentito aggirarlo:

- distribuendo le richieste su più server;
- usando più container;
- usando più IP;
- parallelizzando worker;
- creando una connection pool concorrente.

## Implementazione raccomandata

Configurazione conservativa:

```yaml
arxiv:
  min_request_interval_seconds: 3.1
  max_concurrent_requests: 1
```

Meglio 3.1–3.5 secondi anziché esattamente 3 secondi, per evitare problemi di clock/jitter.

Implementare un **rate limiter globale**, non uno per worker.

Esempio concettuale:

```python
await global_arxiv_rate_limiter.acquire()
response = await client.get(url)
```

Il limiter deve garantire contemporaneamente:

```text
concurrency = 1
minimum_interval >= 3 seconds
```

## Retry

Per errori temporanei:

- HTTP 429
- HTTP 500
- HTTP 502
- HTTP 503
- HTTP 504
- timeout/rete

usare exponential backoff con jitter.

Esempio:

```text
3 s
6 s
12 s
24 s
48 s
```

Aggiungere jitter casuale.

Non effettuare retry aggressivi.

---

# 4. Search API

## 4.1 Endpoint

```text
https://export.arxiv.org/api/query
```

Parametri principali:

```text
search_query
id_list
start
max_results
sortBy
sortOrder
```

Esempio:

```text
https://export.arxiv.org/api/query?search_query=all:electron&start=0&max_results=100
```

La risposta è **Atom 1.0 XML**.

---

# 5. Campi di ricerca

arXiv permette di limitare una ricerca a specifici campi.

| Prefisso | Campo |
|---|---|
| `ti` | title |
| `au` | author |
| `abs` | abstract |
| `co` | comment |
| `jr` | journal reference |
| `cat` | subject category |
| `rn` | report number |
| `id` | arXiv ID; per ID è però preferibile `id_list` |
| `all` | tutti i campi precedenti |

Esempi:

```text
ti:transformer
```

```text
abs:"retrieval augmented generation"
```

```text
au:bengio
```

```text
cat:cs.AI
```

```text
cat:cs.LG
```

### Raccomandazione

Non usare sistematicamente `all:`.

`all:` massimizza il recall ma può aumentare notevolmente rumore e falsi positivi.

Per sistemi di ricerca bibliografica è spesso migliore una strategia multilivello:

```text
Tier 1: title exact/strong match
Tier 2: title + abstract
Tier 3: abstract
Tier 4: all fields
```

I risultati possono poi ricevere score diversi.

---

# 6. Operatori booleani

Sono supportati:

```text
AND
OR
ANDNOT
```

Esempio:

```text
ti:transformer AND abs:attention
```

Esempio:

```text
cat:cs.AI AND abs:"large language model"
```

Esempio di esclusione:

```text
abs:transformer ANDNOT cat:physics.optics
```

## Raggruppamento

Sono supportate parentesi.

Forma logica:

```text
(cat:cs.AI OR cat:cs.CL) AND abs:"large language model"
```

Quando costruita manualmente come URL:

```text
(
```

va codificato come:

```text
%28
```

e:

```text
)
```

come:

```text
%29
```

Nell'applicazione NON costruire manualmente l'URL: utilizzare il normale encoder della libreria HTTP.

---

# 7. Ricerca per frase esatta

Per cercare una frase:

```text
ti:"quantum criticality"
```

oppure:

```text
abs:"retrieval augmented generation"
```

Le virgolette devono essere URL encoded automaticamente dal client.

Questa tecnica migliora molto la precisione ma riduce il recall.

Per questo non va usata come unica query.

Strategia consigliata:

```text
Q1 exact phrase
Q2 AND tra parole principali
Q3 sinonimi
Q4 acronimo
Q5 varianti terminologiche
```

Esempio per "retrieval augmented generation":

```text
abs:"retrieval augmented generation"
```

```text
abs:retrieval AND abs:augmented AND abs:generation
```

```text
all:RAG AND cat:cs.CL
```

```text
abs:"retrieval-augmented generation"
```

---

# 8. Ricerca per categoria

Le categorie sono estremamente utili per ridurre rumore.

Esempi:

```text
cat:cs.AI
cat:cs.CL
cat:cs.LG
cat:stat.ML
```

Per coprire più categorie:

```text
(cat:cs.AI OR cat:cs.CL OR cat:cs.LG OR cat:stat.ML)
```

La tassonomia ufficiale va trattata come configurazione aggiornabile, non hardcoded permanentemente.

Fonte ufficiale:

https://arxiv.org/category_taxonomy

---

# 9. Date

La Search API supporta il filtro:

```text
submittedDate
```

Formato:

```text
[YYYYMMDDHHMM TO YYYYMMDDHHMM]
```

in GMT/UTC.

Esempio:

```text
submittedDate:[202601010000 TO 202612312359]
```

Combinazione:

```text
cat:cs.AI AND submittedDate:[202601010000 TO 202612312359]
```

## Importante

`submittedDate` riguarda la data di submission.

Per strategie di sincronizzazione massiva è preferibile OAI-PMH perché dispone di `datestamp` progettati per harvesting incrementale.

---

# 10. Ordinamento

`sortBy` accetta:

```text
relevance
lastUpdatedDate
submittedDate
```

`sortOrder`:

```text
ascending
descending
```

Esempio:

```text
sortBy=relevance
sortOrder=descending
```

oppure:

```text
sortBy=submittedDate
sortOrder=descending
```

## Strategia consigliata per massimizzare qualità + novità

Per ogni query importante effettuare idealmente due retrieval logici:

### Pass A — relevance

```text
sortBy=relevance
sortOrder=descending
```

serve a identificare i lavori semanticamente/lessicalmente più pertinenti.

### Pass B — recent

```text
sortBy=submittedDate
sortOrder=descending
```

serve a non perdere lavori recentissimi che non salgono abbastanza nel ranking.

Unire i due insiemi e deduplicare.

Questo è preferibile rispetto a scegliere una sola modalità.

---

# 11. Paginazione

Parametri:

```text
start
max_results
```

`start` è zero-based.

Esempio:

```text
start=0&max_results=100
start=100&max_results=100
start=200&max_results=100
```

La risposta contiene anche:

```text
opensearch:totalResults
opensearch:startIndex
opensearch:itemsPerPage
```

Utilizzarli per controllare la paginazione.

---

# 12. Limiti dei result set

La documentazione indica:

- massimo teorico: **30.000 risultati per query**;
- retrieval in slice di massimo **2.000 risultati**;
- arXiv raccomanda di raffinare query che producono oltre circa **1.000 risultati**;
- per grandi harvesting è preferibile **OAI-PMH**.

Questi numeri NON devono diventare la configurazione normale.

## Configurazione consigliata

Per ricerca interattiva:

```yaml
page_size: 50-100
```

Per job batch:

```yaml
page_size: 200-500
```

Solo se necessario:

```yaml
page_size: <= 2000
```

Non chiedere automaticamente 2.000 risultati se ne bastano 100.

---

# 13. `id_list`: recupero per ID

Per recuperare paper già noti usare:

```text
id_list
```

Esempio:

```text
https://export.arxiv.org/api/query?id_list=1706.03762
```

Più ID:

```text
id_list=1706.03762,2005.14165,2302.13971
```

È preferibile a:

```text
search_query=id:...
```

perché gestisce correttamente le versioni.

---

# 14. Versioni dei paper

Un arXiv ID può avere:

```text
1706.03762v1
1706.03762v2
...
```

Senza versione:

```text
1706.03762
```

si intende normalmente la versione più recente.

Per deduplicazione usare come chiave primaria il **base arXiv ID**:

```text
1706.03762
```

e salvare separatamente:

```json
{
  "arxiv_id": "1706.03762",
  "version": 7
}
```

Non considerare `v1` e `v2` paper distinti.

---

# 15. Dati restituiti dalla Search API

Ogni `<entry>` può contenere:

```text
title
id
published
updated
summary
author
link
category
primary_category
comment
affiliation
journal_ref
doi
```

In particolare:

- `published` = data della prima submission/versione 1;
- `updated` = data della versione restituita;
- `summary` = abstract;
- `category` = categorie;
- `primary_category` = categoria principale;
- `doi` = DOI se disponibile;
- `journal_ref` = riferimento alla pubblicazione, se disponibile.

## Modello dati consigliato

```json
{
  "source": "arxiv",
  "arxiv_id": "1706.03762",
  "version": 7,
  "title": "...",
  "abstract": "...",
  "authors": [],
  "primary_category": "cs.CL",
  "categories": [],
  "published_at": "...",
  "updated_at": "...",
  "doi": null,
  "journal_reference": null,
  "comment": null,
  "abstract_url": "...",
  "pdf_url": "...",
  "raw_metadata": {}
}
```

Conservare anche `raw_metadata`, almeno durante lo sviluppo, per evitare perdita di informazioni.

---

# 16. Normalizzazione dati

Prima di indicizzare:

## Title

- trim;
- sostituire newline multipli con spazio;
- normalizzare whitespace;
- NON rimuovere simboli matematici indiscriminatamente.

## Abstract

- trim;
- normalizzare whitespace;
- mantenere formule e token tecnici;
- conservare anche la versione raw.

## Authors

Conservare ordine originale.

Esempio:

```json
[
  {"name": "Ashish Vaswani"},
  {"name": "Noam Shazeer"}
]
```

Non cercare di deduplicare persone solo dal nome.

## Categories

Conservare:

```text
primary_category
categories[]
```

separatamente.

---

# 17. Deduplicazione

La deduplicazione minima deve essere:

```text
normalized arXiv ID without version
```

Esempio:

```text
https://arxiv.org/abs/1706.03762v7
```

normalizzato in:

```text
1706.03762
```

## Secondo livello opzionale

Per integrare fonti esterne:

1. DOI;
2. titolo normalizzato;
3. autore principale;
4. anno.

Non deduplicare esclusivamente tramite titolo perché:

- titoli possono cambiare tra versioni;
- possono esistere lavori diversi con titoli molto simili.

---

# 18. Strategia ottimale di query expansion

Per massimizzare recall e precisione, il sistema dovrebbe trasformare una domanda dell'utente in una **query plan**.

Esempio input:

```text
LLM agents for automated software engineering
```

Generare concetti:

```yaml
concepts:
  - large language model
  - LLM
  - agent
  - autonomous agent
  - coding agent
  - software engineering
  - program repair
  - code generation
```

Poi creare query per famiglie.

## A. High precision

```text
ti:"software engineering" AND abs:"large language model"
```

```text
ti:agent AND abs:"code generation"
```

## B. Medium precision

```text
abs:"large language model" AND abs:"software engineering"
```

```text
abs:LLM AND abs:"program repair"
```

## C. High recall

```text
all:"large language model" AND all:agent
```

```text
(all:LLM OR all:"large language model") AND
(all:"software engineering" OR all:"code generation" OR all:"program repair")
```

## D. Category restricted

```text
(cat:cs.AI OR cat:cs.SE OR cat:cs.CL OR cat:cs.LG)
AND
(all:agent OR all:"large language model")
```

---

# 19. Query portfolio invece di mega-query

NON costruire una singola query gigantesca.

Problemi:

- ranking poco interpretabile;
- difficile capire quale concetto ha prodotto il match;
- recall difficile da misurare;
- risultati dominati dai termini più comuni;
- debugging complicato.

Meglio generare un portafoglio:

```json
[
  {
    "id": "Q01",
    "intent": "exact_topic",
    "query": "ti:\"retrieval augmented generation\"",
    "weight": 1.0
  },
  {
    "id": "Q02",
    "intent": "abstract_match",
    "query": "abs:\"retrieval augmented generation\"",
    "weight": 0.9
  },
  {
    "id": "Q03",
    "intent": "synonym",
    "query": "abs:\"retrieval-augmented generation\"",
    "weight": 0.9
  }
]
```

Memorizzare per ogni risultato:

```text
matched_query_ids[]
```

Questo permette explainability e ranking migliore.

---

# 20. Ranking locale consigliato

Il ranking `relevance` di arXiv è utile ma non dovrebbe necessariamente essere il ranking finale di un sistema avanzato.

Dopo il retrieval, ricalcolare localmente lo score.

Esempio:

```text
final_score =
    0.30 * lexical_relevance
  + 0.30 * semantic_similarity
  + 0.15 * title_match
  + 0.10 * category_match
  + 0.10 * recency
  + 0.05 * query_consensus
```

Dove `query_consensus` aumenta se lo stesso paper viene trovato da più query indipendenti.

Esempio:

```text
Q1 -> paper A
Q2 -> paper A
Q3 -> paper A
```

paper A merita generalmente maggiore confidenza rispetto a un paper trovato solo da una query molto generica.

---

# 21. arXiv Search API non è ricerca semantica

Non assumere che:

```text
sortBy=relevance
```

equivalga a semantic search moderna.

La documentazione indica che il ranking è basato sul motore di ricerca interno/Lucene.

Per applicazioni di literature review avanzate:

1. fare retrieval lessicale con arXiv;
2. creare embedding di title + abstract;
3. rerankare localmente;
4. opzionalmente usare un reranker cross-encoder/LLM.

Pipeline:

```text
user question
    ↓
query expansion
    ↓
arXiv lexical retrieval
    ↓
deduplication
    ↓
embedding similarity
    ↓
reranker
    ↓
final papers
```

Questo aumenta fortemente la qualità rispetto ad affidarsi soltanto all'ordine restituito da arXiv.

---

# 22. Strategia Recall-first / Precision-second

Per review scientifiche è spesso preferibile:

```text
fase 1 = recall
fase 2 = ranking
fase 3 = filtering
```

Piuttosto che rendere la query iniziale troppo restrittiva.

Esempio:

```text
retrieve 300-1000 candidate papers
```

poi:

```text
metadata filter
semantic reranking
LLM screening
```

fino ad arrivare a:

```text
20-100 paper realmente rilevanti
```

---

# 23. OAI-PMH

Base URL attuale:

```text
https://oaipmh.arxiv.org/oai
```

arXiv ha riscritto l'infrastruttura OAI-PMH nel marzo 2025.

Il precedente endpoint:

```text
http://export.arxiv.org/oai2
```

non deve essere usato per nuove implementazioni.

## Quando usare OAI-PMH

Usarlo quando serve:

- harvest completo dei metadati;
- indicizzazione locale;
- sincronizzazione periodica;
- milioni di record;
- analisi corpus-wide;
- mantenimento di un database arXiv interno.

Non è la scelta migliore per query interattive ad hoc.

---

# 24. Metadata format OAI-PMH

arXiv supporta almeno:

```text
oai_dc
arXiv
arXivRaw
```

## `oai_dc`

Dublin Core semplice.

Usarlo solo se serve interoperabilità generica.

## `arXiv`

Formato arXiv specifico.

Contiene fra l'altro:

- autori separati;
- categorie;
- licenza.

È normalmente la scelta migliore per harvesting applicativo.

## `arXivRaw`

Più vicino al formato interno.

Include anche informazioni sulla cronologia/versioni precedenti.

Usarlo quando serve la storia delle versioni.

---

# 25. OAI-PMH e versioni

L'OAI-PMH espone un item per articolo.

La versione principale esposta è quella più recente.

Se serve la cronologia delle versioni utilizzare:

```text
metadataPrefix=arXivRaw
```

---

# 26. OAI-PMH incremental harvesting

Ogni record OAI-PMH ha un:

```text
datestamp
```

che rappresenta l'ultima modifica del record.

ATTENZIONE:

il datestamp OAI-PMH **non equivale necessariamente alla data originale di submission**.

Può cambiare per:

- aggiornamenti amministrativi;
- aggiornamenti bibliografici;
- operazioni bulk di arXiv.

Per sincronizzazione è esattamente ciò che serve.

## Procedura corretta

### Initial harvest

Harvest senza range oppure dall'`earliestDatestamp`.

### Incremental

Memorizzare il timestamp restituito dal server.

Al job successivo:

```text
from=<last_server_date>
```

arXiv consiglia di:

- usare come `from` la data dell'ultimo harvest;
- non impostare necessariamente `until`.

Questo riduce il rischio di gap.

---

# 27. OAI-PMH non filtra per data di submission

È importante non confondere:

```text
OAI datestamp
```

con:

```text
paper submittedDate
```

OAI-PMH non è pensato per richieste del tipo:

```text
dammi i paper originariamente pubblicati a febbraio 2020
```

È pensato per:

```text
dammi i record modificati da quando ho sincronizzato l'ultima volta
```

Per ricerche per data di submission usare Search API.

---

# 28. OAI-PMH Sets

È possibile harvestare sottoinsiemi per:

- group;
- archive;
- category.

Esempio:

```text
cs:cs:AI
```

Il set structure segue:

```text
group:archive:CATEGORY
```

Esempi indicati dalla documentazione:

```text
math:math:NA
physics:hep-lat
physics
```

Per ottenere l'elenco corrente usare:

```text
verb=ListSets
```

Non hardcodare la lista.

---

# 29. Resumption token OAI-PMH

Per raccolte ampie OAI-PMH restituisce un:

```text
resumptionToken
```

L'applicazione deve:

1. usare il token;
2. continuare finché non è vuoto;
3. persistire checkpoint;
4. sapere che dal rewrite 2025 i token scadono giornalmente.

Quindi un harvest lungo deve poter ripartire in sicurezza.

---

# 30. Aggiornamento OAI-PMH

arXiv aggiorna i metadati dopo l'annuncio giornaliero dei paper.

La documentazione indica tipicamente circa:

```text
22:30 Eastern Time
Sunday through Thursday
```

oltre a possibili piccole modifiche durante il giorno.

Per un sistema europeo non assumere un orario UTC fisso perché EST/EDT cambia con il daylight saving.

Per sincronizzazione semplice:

```text
1 job/giorno
```

è sufficiente per la maggior parte dei progetti.

---

# 31. Search API vs OAI-PMH

| Caratteristica | Search API | OAI-PMH |
|---|---:|---:|
| Search keyword | sì | no |
| Search title | sì | no |
| Search abstract | sì | no |
| Boolean query | sì | no |
| Relevance ranking | sì | no |
| Date submission filter | sì | no |
| Bulk metadata | limitato | eccellente |
| Incremental sync | mediocre | eccellente |
| Full mirror | no | sì |
| Category harvesting | sì | sì |
| Version history | limitata | `arXivRaw` |
| Interactive use | eccellente | scarso |

## Regola

```text
Search API = discovery
OAI-PMH = ingestion/synchronization
```

---

# 32. Full text

arXiv distingue chiaramente:

```text
metadata
```

da:

```text
e-print content
```

I metadati descrittivi sono liberamente riutilizzabili secondo CC0.

I PDF/source file possono avere licenze differenti.

Non assumere automaticamente che ogni PDF possa essere redistribuito.

---

# 33. Download completo del corpus

arXiv dice esplicitamente di **non scaricare l'intero corpus facendo crawling programmatico del sito**.

Per l'intero corpus usare:

```text
Amazon S3
```

oppure il dataset disponibile tramite:

```text
Kaggle
```

---

# 34. Amazon S3

arXiv rende disponibili:

- PDF processati;
- source files.

Il bucket è in:

```text
US East / N. Virginia
```

ed è configurato come:

```text
Requester Pays
```

Questo significa che il downloader sostiene i costi AWS di accesso/data transfer previsti.

Non serve una "arXiv API key", ma per S3 Requester Pays serve ovviamente un accesso AWS configurato.

La documentazione ufficiale riportava ad aprile 2025 circa:

```text
9.2 TB
```

complessivi di file disponibili, con crescita stimata di circa:

```text
100 GB/mese
```

Questi valori sono indicativi e aumentano nel tempo.

---

# 35. Kaggle

arXiv indica anche un dataset machine-readable su Kaggle comprendente:

- metadata;
- titles;
- authors;
- categories;
- abstracts;
- PDF/full text e altri elementi del corpus.

È molto più appropriato di crawling HTML quando serve lavorare sull'intero corpus.

L'autenticazione eventualmente necessaria per download automatizzati è quella di Kaggle, non di arXiv.

---

# 36. Politica corretta sui PDF

Per una normale piattaforma di literature discovery:

NON:

```text
scaricare e redistribuire tutti i PDF
```

Meglio:

```text
indicizzare metadati
↓
mostrare paper
↓
link alla pagina abstract arXiv
↓
utente apre/scarica da arXiv
```

arXiv incoraggia in particolare il link alla abstract page.

---

# 37. Caching

Dato il rate limit, è essenziale introdurre caching.

## Query cache

Chiave:

```text
SHA256(canonical_query + sort + page)
```

TTL suggerito:

```text
recent query: 1-6 ore
historical query: 1-7 giorni
ID lookup: 1-7 giorni
```

Per paper vecchi e immutati il TTL può essere maggiore.

## Metadata cache

Salvare i paper localmente per arXiv ID.

Prima di chiamare arXiv:

```text
lookup local cache
```

poi interrogare l'API solo per dati mancanti/stale.

---

# 38. Query canonicalization

Prima di generare la cache key:

- normalizzare whitespace;
- ordinare parametri HTTP;
- normalizzare `sortBy`;
- normalizzare `sortOrder`;
- NON alterare arbitrariamente la semantica della query booleana.

Esempio:

```text
abs:LLM  AND   cat:cs.CL
```

può essere normalizzato in:

```text
abs:LLM AND cat:cs.CL
```

ma non trasformare automaticamente:

```text
A OR B AND C
```

perché la precedence potrebbe cambiare.

---

# 39. Error handling

Gestire almeno:

```text
HTTP 200
HTTP 400
HTTP 429
HTTP 5xx
timeout
malformed XML
empty result
partial result
```

L'API può restituire informazioni di errore anche nel formato Atom.

Non assumere:

```text
HTTP 200 == valid paper data
```

Validare il feed.

---

# 40. XML parsing

Usare un parser XML robusto.

NON usare regex.

Considerare namespace:

```text
http://www.w3.org/2005/Atom
http://a9.com/-/spec/opensearch/1.1/
http://arxiv.org/schemas/atom
```

Mappare esplicitamente i namespace.

---

# 41. User-Agent

Anche se non sempre obbligatorio tecnicamente, un client di produzione dovrebbe inviare un User-Agent identificabile.

Esempio:

```text
MyResearchTool/1.0 (contact: research@example.org)
```

Questo è particolarmente utile per sistemi automatici e rende più responsabile l'uso dell'infrastruttura pubblica.

---

# 42. Pipeline raccomandata per un motore di literature research

```text
User Research Question
        │
        ▼
Topic decomposition
        │
        ▼
Synonym / acronym expansion
        │
        ▼
Category inference
        │
        ▼
Query portfolio generation
        │
        ├──── high precision
        ├──── high recall
        ├──── recent
        └──── category specific
        │
        ▼
arXiv Search API
        │
        ▼
Dedup by canonical arXiv ID
        │
        ▼
Metadata normalization
        │
        ▼
Local embedding
        │
        ▼
Semantic reranking
        │
        ▼
LLM relevance classification
        │
        ▼
Selected candidate papers
        │
        ▼
Optional full text retrieval
```

---

# 43. Architettura raccomandata per ricerche ripetute

Se il progetto effettua molte ricerche, la soluzione migliore è evitare di utilizzare arXiv come search backend remoto per ogni operazione.

Architettura:

```text
          OAI-PMH
             │
             ▼
      Metadata ingestion
             │
             ▼
         Local DB
             │
       ┌─────┴─────┐
       ▼           ▼
   BM25 index   Vector index
       │           │
       └─────┬─────┘
             ▼
        Hybrid search
             │
             ▼
           LLM
```

Tecnologie possibili:

```text
PostgreSQL + pgvector
OpenSearch
Elasticsearch
Qdrant + relational DB
Typesense/Meilisearch + vector DB
```

Il vantaggio è enorme:

- nessun rate limit durante le query locali;
- ranking personalizzato;
- semantic search;
- filtering rapido;
- migliore copertura;
- query riproducibili;
- costi ridotti;
- minor carico su arXiv.

---

# 44. Quando creare un mirror locale dei metadati

Conviene quando:

```text
query/giorno elevate
OR
ricerche corpus-wide
OR
embedding di massa
OR
letterature review ripetute
OR
analisi statistiche
OR
agent autonomo che lavora continuamente
```

Non è necessario per un'applicazione che esegue poche decine di query occasionali.

---

# 45. Strategia ibrida raccomandata

La soluzione migliore per un agente di ricerca continuativa è:

## Bootstrap

```text
OAI-PMH -> local metadata store
```

## Daily sync

```text
OAI-PMH incremental
```

## Query

```text
local lexical + vector search
```

## Very recent / verification

```text
Search API
```

## Full text

```text
on demand
```

Questa architettura combina:

```text
quantity + speed + quality + compliance
```

---

# 46. Quality strategy

arXiv contiene preprint e non rappresenta automaticamente una garanzia di peer review.

Quindi non usare:

```text
paper presente su arXiv = paper validato
```

Il sistema dovrebbe registrare:

```text
journal_ref
doi
version
updated date
categories
```

e, se il progetto lo permette, arricchire successivamente con altre fonti bibliografiche.

Questa parte è esterna ad arXiv ma può aumentare molto la qualità della literature review.

---

# 47. Valutazione della pertinenza con LLM

Non inviare immediatamente il PDF completo al modello.

Pipeline più efficiente:

### Stage 1

```text
title
```

### Stage 2

```text
title + abstract
```

### Stage 3

solo per candidati promettenti:

```text
full text
```

Questo riduce drasticamente:

- token;
- costo;
- latenza;
- rumore.

---

# 48. LLM screening schema consigliato

Output strutturato:

```json
{
  "arxiv_id": "xxxx.xxxxx",
  "relevant": true,
  "relevance_score": 0.92,
  "reason": "...",
  "topic_matches": [],
  "methodology_match": true,
  "needs_full_text": true
}
```

Lo score del modello non deve sostituire completamente retrieval/ranking ma aggiungersi ad essi.

---

# 49. Evitare bias da recency

Un sistema automatico tende facilmente a sovrastimare paper nuovi.

Per review profonde, suddividere la ricerca:

```text
historical/foundational
recent
very recent
```

Esempio:

```text
< 2018
2018-2022
2023-2024
2025+
```

Le finestre vanno adattate alla disciplina.

---

# 50. Snowballing

arXiv Search API non fornisce direttamente un citation graph completo.

Per una literature review approfondita, dopo aver trovato i paper seed:

```text
seed papers
   ↓
references
   ↓
related papers
   ↓
forward citations
```

La parte citation graph richiede normalmente parsing full-text o fonti bibliografiche complementari.

Non attribuire ad arXiv API funzionalità che non fornisce.

---

# 51. Strategia di stopping

Un agente autonomo non deve continuare le query indefinitamente.

Implementare saturation detection.

Esempio:

```text
round N new relevant papers < 2%
for 3 consecutive rounds
=> stop
```

oppure:

```text
no new high-score papers for N query families
=> stop
```

Misurare:

```text
new_ids
new_relevant_ids
duplicate_rate
query_yield
```

---

# 52. Metriche da registrare

Per ogni query:

```json
{
  "query_id": "...",
  "query": "...",
  "requested_at": "...",
  "sort_by": "...",
  "total_results": 0,
  "retrieved": 0,
  "new_unique": 0,
  "high_relevance": 0,
  "duration_ms": 0,
  "http_status": 200,
  "retry_count": 0
}
```

Metriche aggregate:

```text
API calls/day
rate-limit errors
results/query
unique papers/query
duplicate ratio
relevant papers/query
precision@10
precision@50
coverage by category
coverage by year
```

---

# 53. Query learning

Dopo lo screening, il sistema può imparare quali termini funzionano.

Esempio:

```text
"AI agent" -> molti falsi positivi
"coding agent" -> alta precisione
"software engineering agent" -> media precisione
```

Aggiornare dinamicamente:

```text
query_weight
```

ma conservare sempre audit log.

---

# 54. Raccomandazione concreta per qualità e quantità

Per un progetto orientato alla ricerca scientifica approfondita:

## Piccola scala

Usare:

```text
Search API
+ query expansion
+ dedup
+ semantic reranking
```

## Media scala

Usare:

```text
Search API
+ persistent metadata cache
+ embeddings
+ reranking
```

## Grande scala / agente continuo

Usare:

```text
OAI-PMH mirror
+ local search index
+ vector index
+ Search API only for fresh verification
```

## Corpus full text

Usare:

```text
Kaggle / S3
```

NON:

```text
crawl arxiv.org
```

---

# 55. Configurazione consigliata

```yaml
arxiv:
  search_api:
    base_url: "https://export.arxiv.org/api/query"

    rate_limit:
      min_interval_seconds: 3.1
      max_concurrency: 1

    pagination:
      interactive_page_size: 100
      batch_page_size: 300
      hard_page_size_limit: 2000

    retries:
      max_attempts: 5
      exponential_backoff: true
      jitter: true

    cache:
      enabled: true
      query_ttl_hours: 6
      metadata_ttl_hours: 168

  oai_pmh:
    base_url: "https://oaipmh.arxiv.org/oai"
    preferred_metadata_prefix: "arXiv"
    incremental_sync: true

  ranking:
    retrieve_by_relevance: true
    retrieve_recent: true
    local_semantic_reranking: true

  fulltext:
    download_on_demand: true
    redistribute: false
```

I valori TTL/page size sono raccomandazioni progettuali, non limiti imposti da arXiv.

---

# 56. Pseudocodice discovery

```python
def search_topic(topic):
    concepts = expand_topic(topic)

    queries = generate_query_portfolio(
        concepts=concepts,
        include_title_queries=True,
        include_abstract_queries=True,
        include_category_queries=True,
        include_exact_phrases=True,
        include_synonyms=True,
    )

    papers = {}

    for query in queries:
        for sort in ["relevance", "submittedDate"]:
            results = arxiv_search(
                search_query=query.expression,
                sort_by=sort,
                sort_order="descending",
                max_results=query.limit,
            )

            for paper in results:
                key = canonical_arxiv_id(paper.id)

                if key not in papers:
                    papers[key] = paper

                papers[key].matched_queries.add(query.id)

    candidates = list(papers.values())

    candidates = semantic_rerank(topic, candidates)

    candidates = llm_screen(topic, candidates)

    return candidates
```

---

# 57. Pseudocodice OAI sync

```python
def sync_arxiv():
    state = load_sync_state()

    params = {
        "verb": "ListRecords",
        "metadataPrefix": "arXiv",
    }

    if state.last_datestamp:
        params["from"] = state.last_datestamp

    while True:
        response = oai_request(params)

        persist_records(response.records)

        save_checkpoint(
            last_server_date=response.response_date,
            token=response.resumption_token,
        )

        if not response.resumption_token:
            break

        params = {
            "verb": "ListRecords",
            "resumptionToken": response.resumption_token,
        }
```

Implementare recovery perché i resumption token possono scadere.

---

# 58. Anti-pattern

## Non fare

```text
100 worker paralleli verso arXiv
```

```text
1 request/sec da 10 macchine
```

```text
crawl di milioni di pagine HTML
```

```text
download dell'intero corpus PDF attraverso /pdf/
```

```text
mega-query generica con max_results=30000
```

```text
usare all: per ogni ricerca
```

```text
considerare v1 e v2 paper diversi
```

```text
considerare relevance come semantic search
```

```text
confondere OAI datestamp con submission date
```

```text
redistribuire automaticamente PDF senza verificare la licenza
```

---

# 59. Decision tree

```text
Devo trovare paper su un argomento?
    YES -> Search API

Conosco gli arXiv ID?
    YES -> Search API id_list

Devo scaricare molti metadati?
    YES -> OAI-PMH

Devo mantenere un indice aggiornato?
    YES -> OAI-PMH incremental

Devo analizzare tutto il corpus?
    YES -> Kaggle / S3

Devo scaricare tutti i PDF?
    YES -> S3 Requester Pays

Devo fare semantic search?
    YES -> ingest metadata + local embeddings

Devo avere citation ranking?
    YES -> integrare un'altra fonte / parsing citazioni
```

---

# 60. Requisiti minimi di implementazione

Un'integrazione arXiv production-grade deve avere:

- [ ] rate limiter globale;
- [ ] max concurrency = 1 verso API legacy;
- [ ] intervallo >= 3 secondi;
- [ ] retry con exponential backoff;
- [ ] caching;
- [ ] XML parser con namespace;
- [ ] query URL encoding corretto;
- [ ] deduplicazione canonical arXiv ID;
- [ ] gestione versioni;
- [ ] logging delle query;
- [ ] metriche risultati/duplicati;
- [ ] pagination;
- [ ] `opensearch:totalResults`;
- [ ] query expansion;
- [ ] sort relevance;
- [ ] sort submittedDate;
- [ ] category filtering;
- [ ] local reranking;
- [ ] gestione licenze;
- [ ] OAI-PMH per bulk;
- [ ] checkpoint OAI;
- [ ] gestione resumption token;
- [ ] link alla pagina arXiv originale.

---

# 61. Migliore architettura per un agente di ricerca scientifica

La raccomandazione finale è:

```text
                   ┌──────────────────┐
                   │ Research Question │
                   └─────────┬────────┘
                             │
                   ┌─────────▼────────┐
                   │ Query Planner LLM │
                   └─────────┬────────┘
                             │
               ┌─────────────┼─────────────┐
               ▼             ▼             ▼
          exact query    synonyms      categories
               │             │             │
               └─────────────┼─────────────┘
                             ▼
                    ┌────────────────┐
                    │ Local arXiv DB │
                    └───────┬────────┘
                            │
                  insufficient/fresh?
                            │
                            ▼
                    ┌────────────────┐
                    │ arXiv Search API│
                    └───────┬────────┘
                            │
                            ▼
                       Deduplicate
                            │
                    ┌───────┴────────┐
                    ▼                ▼
                  BM25            Embedding
                    │                │
                    └───────┬────────┘
                            ▼
                       Hybrid rank
                            │
                            ▼
                       LLM screen
                            │
                            ▼
                      relevant set
                            │
                      needs full text?
                            │
                            ▼
                     fetch on demand
```

Il database locale viene mantenuto aggiornato tramite:

```text
OAI-PMH incremental sync
```

Questa è generalmente la soluzione con il miglior compromesso tra:

- quantità;
- qualità;
- velocità;
- riproducibilità;
- rispetto dei rate limit;
- scalabilità.

---

# 62. Risposte sintetiche alle domande iniziali

## Serve una API key?

**No**, non per Search API pubblica e OAI-PMH.

## Serve un account?

**No** per l'accesso pubblico ai metadati.

## Serve un abbonamento?

**No.**

## Bisogna essere membri di arXiv?

**No.**

## L'uso è gratuito?

L'accesso alle API/metadati pubblici è gratuito.

Il download massivo tramite Amazon S3 è **Requester Pays**, quindi possono esserci costi AWS.

## Quanto posso interrogare l'API?

Per le API legacy:

```text
1 request ogni >= 3 secondi
1 sola connessione contemporanea
```

considerando complessivamente tutte le macchine sotto il proprio controllo.

## Quanti risultati posso prendere?

La Search API documenta fino a:

```text
30.000 risultati/query
```

in slice di massimo:

```text
2.000
```

ma arXiv raccomanda di raffinare query oltre circa 1.000 risultati e di usare OAI-PMH per bulk harvesting.

## Qual è il metodo migliore?

Per ricerca qualitativa:

```text
multi-query Search API
+ dedup
+ semantic reranking
```

Per grande quantità:

```text
OAI-PMH
+ local index
```

Per full corpus:

```text
Kaggle/S3
```

---

# 63. Fonti ufficiali

Documentazione ufficiale utilizzata:

## API access

https://info.arxiv.org/help/api/index.html

## API Terms of Use

https://info.arxiv.org/help/api/tou.html

## API Basics

https://info.arxiv.org/help/api/basics.html

## API User Manual

https://info.arxiv.org/help/api/user-manual.html

## OAI-PMH

https://info.arxiv.org/help/oa/index.html

## Bulk data overview

https://info.arxiv.org/help/bulk_data.html

## Full Text / Amazon S3

https://info.arxiv.org/help/bulk_data_s3.html

## Category taxonomy

https://arxiv.org/category_taxonomy

---

# 64. Principio progettuale finale

L'integrazione non deve trattare arXiv come un motore di ricerca commerciale senza limiti.

Il pattern corretto è:

```text
arXiv = authoritative source of metadata/content
local system = intelligence, ranking, caching and high-volume querying layer
```

Quando il volume cresce:

```text
meno chiamate remote
più indicizzazione locale
```

Quando cresce la necessità di qualità:

```text
più query complementari
+ semantic reranking
+ screening
```

Quando cresce la necessità di copertura:

```text
OAI-PMH
```

Quando serve full text su scala corpus:

```text
Kaggle / S3
```

Questo design è più robusto di una semplice integrazione basata esclusivamente sulla Search API.
