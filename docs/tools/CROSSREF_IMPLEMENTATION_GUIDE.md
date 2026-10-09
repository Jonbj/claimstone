# Crossref — Linee guida operative per integrazione API

## 1. Obiettivo

Questo documento definisce come integrare **Crossref REST API** in un progetto software che deve cercare, raccogliere, normalizzare e classificare letteratura scientifica con il miglior compromesso possibile tra:

- qualità dei risultati;
- quantità/recall;
- velocità;
- robustezza;
- rispetto dei limiti API;
- deduplicazione;
- aggiornamento incrementale;
- possibilità di combinare Crossref con altri motori bibliografici.

Crossref va considerato principalmente come:

> **fonte autorevole di metadati bibliografici e DOI + motore di candidate generation**

e non come unico motore di ricerca semantica.

---

# 2. Accesso a Crossref

## 2.1 Non serve essere membri

Per usare la REST API di Crossref per ricerca e recupero metadati:

- non serve essere membri Crossref;
- non serve avere un prefisso DOI;
- non serve depositare DOI;
- non serve un abbonamento.

La membership Crossref riguarda principalmente organizzazioni che devono registrare DOI e depositare metadati.

---

## 2.2 Non serve API key per l'accesso normale

Per l'utilizzo standard della REST API non serve API key.

La modalità consigliata è il cosiddetto **Polite Pool**.

Per accedervi bisogna:

1. inviare un indirizzo email valido tramite parametro `mailto`;
2. identificare l'applicazione tramite `User-Agent`.

Esempio concettuale:

```http
GET https://api.crossref.org/works?query.title=machine+learning&mailto=dev@example.com
```

Header consigliato:

```http
User-Agent: MyResearchBot/1.0 (mailto:dev@example.com)
```

Usare sempre un'email realmente monitorata.

---

# 3. Modalità di accesso

Crossref espone principalmente tre modalità operative.

## Public

Caratteristiche:

- gratuita;
- nessuna API key;
- limiti più restrittivi;
- adatta principalmente a test e utilizzi occasionali.

## Polite

Caratteristiche:

- gratuita;
- nessuna API key;
- richiede `mailto`;
- throughput superiore alla modalità anonima;
- è la modalità raccomandata per un'applicazione normale.

Questa deve essere la modalità predefinita del progetto.

## Metadata Plus

Caratteristiche:

- a pagamento;
- autenticazione dedicata;
- rate limit molto più elevati;
- accesso più prevedibile;
- snapshot completi del dataset;
- utile soprattutto per carichi molto elevati.

Importante:

> Metadata Plus non deve essere considerato un modo per ottenere risultati semanticamente migliori.

La qualità dei metadati è sostanzialmente la stessa.

Il vantaggio è soprattutto operativo:

- throughput;
- affidabilità;
- supporto;
- accesso a snapshot.

---

# 4. Configurazione raccomandata

La configurazione iniziale deve essere:

```text
Crossref REST API
+
Polite Pool
+
mailto
+
User-Agent identificabile
+
rate limiting conservativo
+
retry con exponential backoff
+
cache locale
```

Non acquistare Metadata Plus finché il volume reale non dimostra che i limiti gratuiti sono insufficienti.

---

# 5. Rate limiting

Il client deve trattare il rate limit come un vincolo dinamico.

Non hardcodare un throughput aggressivo.

Configurazione iniziale raccomandata:

```text
max_requests_per_second = 8
max_concurrent_requests = 2 o 3
```

anche se Crossref permette valori superiori nel Polite Pool.

Lasciare sempre margine.

Il client deve rispettare eventuali header HTTP relativi ai limiti e reagire ai codici:

```text
429 Too Many Requests
```

con retry progressivo.

---

# 6. Retry

Implementare retry automatici almeno per:

```text
429
500
502
503
504
timeout
connection reset
```

Strategia consigliata:

```text
attempt 1 -> 1 s
attempt 2 -> 2 s
attempt 3 -> 4 s
attempt 4 -> 8 s
attempt 5 -> 16 s
```

Aggiungere jitter casuale.

Esempio:

```text
sleep = min(base * 2^attempt + random_jitter, max_delay)
```

Valori consigliati:

```text
base = 1 secondo
max_delay = 60 secondi
max_retries = 5
```

Non effettuare retry automatico indiscriminato su errori HTTP 4xx diversi da 408/429.

---

# 7. Endpoint principale

L'endpoint principale per la ricerca è:

```http
GET https://api.crossref.org/works
```

Per recuperare un singolo record tramite DOI:

```http
GET https://api.crossref.org/works/{doi}
```

Esempio:

```http
GET https://api.crossref.org/works/10.1038/s41586-023-00000-0
```

---

# 8. Principio fondamentale: evitare una singola mega-query

Non costruire query enormi contenenti tutti i concetti della ricerca.

Esempio da evitare:

```text
financial news sentiment stock market trading event abnormal return machine learning
```

Crossref non interpreta questa stringa come una rigida condizione AND.

Una query lunga può quindi produrre molto rumore.

Usare invece più query compatte e semanticamente coerenti.

Esempio:

```text
financial news stock returns
news sentiment stock market
news event stock price
event study financial news
textual sentiment asset prices
news analytics algorithmic trading
```

Poi unire i risultati.

---

# 9. Crossref non è un motore booleano completo

Non assumere che Crossref interpreti correttamente:

```text
A AND B
A OR B
NOT C
(A OR B) AND C
```

come farebbe un motore bibliografico con sintassi booleana.

Non progettare la logica di ricerca basandosi su operatori booleani.

La logica booleana va implementata:

- generando più query;
- usando filtri strutturati;
- filtrando e facendo ranking a valle.

---

# 10. Non affidarsi alle virgolette come exact phrase

Non assumere che:

```text
"financial news sentiment"
```

sia trattato come una vera ricerca exact phrase.

Se serve una corrispondenza più precisa:

1. generare query più corte;
2. raccogliere candidati;
3. calcolare localmente la similarity del titolo;
4. applicare filtri e ranking.

---

# 11. Tipi di query più utili

## 11.1 query.title

Da usare quando il concetto dovrebbe comparire nel titolo.

Esempio:

```http
/works?query.title=news+sentiment+stock+market
```

Vantaggi:

- precisione generalmente maggiore;
- utile per discovery iniziale.

Svantaggi:

- recall inferiore;
- può perdere articoli rilevanti che esprimono il concetto solo nell'abstract o nel testo.

---

## 11.2 query.bibliographic

Molto utile per:

- matching bibliografico;
- ricerca per citazione;
- combinazione di titolo, autore, anno, rivista e altri elementi.

Esempio:

```http
/works?query.bibliographic=financial+news+market+reaction
```

Deve essere utilizzata insieme a `query.title` quando si vuole aumentare il recall.

---

## 11.3 query.author

Esempio:

```http
/works?query.author=Eugene+Fama
```

Da usare solo se l'autore è un criterio reale della ricerca.

---

## 11.4 query.container-title

Permette di cercare per nome della rivista o publication venue.

---

## 11.5 query.publisher-name

Utile quando si vuole restringere o identificare un publisher.

---

## 11.6 query.affiliation

Utile per ricerche relative a istituzioni/affiliazioni.

---

# 12. Strategia di discovery consigliata

Per ogni topic creare una batteria di query.

Esempio:

```text
TOPIC:
financial news and stock price reaction
```

Possibili query:

```text
query.title = financial news stock returns
query.title = news sentiment stock market
query.title = news event stock price
query.title = textual sentiment asset prices

query.bibliographic = financial news market reaction
query.bibliographic = news sentiment abnormal return
query.bibliographic = event study financial news
query.bibliographic = news analytics algorithmic trading
```

Il numero ideale dipende dal topic.

Valore iniziale consigliato:

```text
10-30 query per topic
```

Meglio molte query piccole che una sola query enorme.

---

# 13. Pipeline di candidate generation

Pipeline consigliata:

```text
topic
  |
  v
query generator
  |
  +--> query.title
  |
  +--> query.bibliographic
  |
  +--> query.author se necessario
  |
  +--> altre query specializzate
  |
  v
Crossref
  |
  v
candidate pool
  |
  v
deduplica DOI
  |
  v
normalizzazione
  |
  v
ranking locale
```

---

# 14. Score restituito da Crossref

Crossref può restituire uno score di rilevanza.

Esempio:

```json
{
  "score": 32.91
}
```

Importante:

> lo score non deve essere considerato globalmente confrontabile tra query differenti.

Usarlo principalmente per ordinare i risultati:

```text
all'interno della stessa query
```

Non assumere che:

```text
score 40 della query A
```

sia necessariamente migliore di:

```text
score 25 della query B
```

---

# 15. Ranking cross-query

Quando si uniscono risultati provenienti da più query, creare uno score interno.

Esempio:

```text
internal_score =
    semantic_similarity
  + title_similarity
  + crossref_rank_bonus
  + citation_signal
  + metadata_quality
  + query_coverage
```

Possibile configurazione iniziale:

```text
semantic_similarity        35%
title_similarity           25%
query_coverage              15%
citation_signal             10%
metadata_quality            10%
crossref_rank_bonus          5%
```

I pesi devono essere configurabili.

---

# 16. Query coverage

Un documento trovato da più query diverse deve ricevere un bonus.

Esempio:

```text
Paper A trovato da 7 query
Paper B trovato da 1 query
```

A parità di altri fattori, Paper A è probabilmente più centrale rispetto al topic.

Implementare:

```text
query_hit_count
```

e possibilmente:

```text
query_hit_ids[]
```

---

# 17. Deduplicazione

La chiave primaria deve essere:

```text
DOI normalizzato
```

Normalizzare sempre il DOI:

```text
lowercase
remove https://doi.org/
remove http://dx.doi.org/
trim whitespace
```

Esempio:

```text
https://doi.org/10.1000/XYZ
```

diventa:

```text
10.1000/xyz
```

---

# 18. Deduplicazione senza DOI

Alcuni record possono non avere un DOI utilizzabile.

Fallback consigliato:

```text
normalized_title
+
publication_year
+
first_author
```

Calcolare anche title similarity per rilevare duplicati quasi identici.

Esempio:

```text
title_similarity > 0.95
same_year
same_first_author
```

può essere trattato come probabile duplicato.

---

# 19. Abstract: limite importante

Crossref può restituire abstract quando sono stati depositati dal publisher.

Tuttavia:

> non bisogna progettare la discovery assumendo di poter cercare liberamente nel contenuto degli abstract tramite Crossref.

Conseguenza:

un articolo molto rilevante può avere un titolo generico e risultare difficile da scoprire.

Per questo motivo Crossref non deve essere l'unico motore di discovery.

---

# 20. Uso consigliato dell'abstract

Se l'abstract è presente nel record:

1. salvarlo;
2. pulire eventuale markup/JATS/XML;
3. usarlo per:
   - embedding;
   - semantic ranking;
   - LLM screening;
   - classificazione;
   - topic extraction.

Campo suggerito:

```text
abstract_raw
abstract_clean
```

---

# 21. Filtri

I filtri sono diversi dalle query.

Le query sono basate su relevance.

I filtri servono a imporre condizioni strutturate.

Esempio:

```http
filter=type:journal-article
```

---

# 22. Filtri utili

Possibili filtri:

```text
type
from-pub-date
until-pub-date
has-references
has-abstract
has-orcid
issn
isbn
doi
member
prefix
```

Esempio:

```http
/works?
query.title=news+sentiment&
filter=type:journal-article,from-pub-date:2010-01-01
```

---

# 23. Evitare filtri metadata troppo aggressivi

Non usare automaticamente:

```text
has-abstract:true
has-orcid:true
has-references:true
```

come filtri obbligatori.

Questi campi misurano soprattutto la completezza dei metadata depositati.

Non misurano direttamente la qualità scientifica.

Un paper eccellente potrebbe non avere abstract depositato in Crossref.

Meglio usare questi campi come:

```text
quality signals
```

anziché hard filter.

---

# 24. Date

Distinguere chiaramente:

```text
publication date
created date
indexed/update date
```

Non sono equivalenti.

---

# 25. Ricerca storica

Per una literature review:

```text
from-pub-date
until-pub-date
```

sono appropriati quando si vuole delimitare temporalmente la letteratura.

---

# 26. Aggiornamento incrementale

Per sincronizzare un database locale non affidarsi esclusivamente alla publication date.

Un articolo vecchio potrebbe essere:

- aggiunto successivamente;
- corretto;
- arricchito;
- reindicizzato.

Utilizzare finestre temporali basate sulle date di indicizzazione/aggiornamento disponibili nell'API.

Schema:

```text
last_successful_sync
        |
        v
from-index-date
        |
        v
until-index-date
        |
        v
download
        |
        v
checkpoint
```

---

# 27. Finestre chiuse

Durante sincronizzazioni grandi utilizzare sempre:

```text
from_date
+
until_date
```

Non lasciare l'estremo superiore aperto.

Motivo:

il dataset può cambiare mentre il crawler sta paginando.

---

# 28. Pagination

Per piccoli insiemi si possono usare pagine normali.

Per deep pagination usare:

```text
cursor
```

La prima richiesta:

```text
cursor=*
```

La risposta contiene:

```text
next-cursor
```

La richiesta successiva deve usare quel valore.

---

# 29. Non usare offset per dataset grandi

L'offset è comodo per piccoli risultati.

Per dataset grandi usare sempre cursor pagination.

Schema:

```text
cursor=*
    |
    v
next-cursor A
    |
    v
next-cursor B
    |
    v
...
```

---

# 30. Persistenza del cursor

Non considerare il cursor come un identificatore permanente.

Il processo deve:

- consumare i cursori in tempi ragionevoli;
- salvare checkpoint logici;
- essere capace di riavviare una finestra temporale se necessario.

Checkpoint consigliato:

```text
window_start
window_end
last_completed_page
processed_dois
```

Meglio ancora:

```text
finestra temporale atomica
```

che può essere riprocessata in modo idempotente.

---

# 31. rows

Per ridurre il numero di richieste utilizzare `rows` elevato quando appropriato.

Per bulk retrieval:

```text
rows=1000
```

è generalmente preferibile a molte richieste con poche decine di risultati.

Per discovery con ranking, può avere senso usare valori inferiori:

```text
100-300
```

se non interessa la lunga coda.

---

# 32. Strategia top-N

Per ogni query non scaricare automaticamente tutto.

Configurazione iniziale suggerita:

```text
top_n_per_query = 200
```

oppure:

```text
300
```

Esempio:

```text
20 query
x
200 risultati
=
massimo teorico 4.000 candidati
```

Dopo deduplicazione il numero reale sarà inferiore.

---

# 33. select

Usare `select` quando durante la discovery non servono tutti i campi.

Esempio concettuale:

```text
select=DOI,title,author,published,type,score
```

Benefici:

- meno traffico;
- meno parsing;
- meno memoria;
- minore latenza.

---

# 34. Enrichment in seconda fase

Usare una pipeline a due fasi.

## Fase A — Discovery

Scaricare solo:

```text
DOI
title
author
published
type
score
container-title
is-referenced-by-count
```

## Fase B — Enrichment

Solo per i candidati realmente interessanti:

```http
GET /works/{doi}
```

recuperando il record completo.

---

# 35. Campi da memorizzare

Schema minimo consigliato:

```text
doi
title
subtitle
authors
publisher
container_title
type
published_date
created_date
indexed_date
issn
isbn
url
abstract_raw
abstract_clean
references
reference_count
is_referenced_by_count
orcid
funder
license
relation
subject
crossref_member
crossref_prefix
crossref_score
raw_crossref_json
retrieved_at
```

---

# 36. Conservare il raw JSON

Salvare sempre:

```text
raw_crossref_json
```

Motivi:

- audit;
- debugging;
- future estrazioni;
- cambi dello schema interno;
- possibilità di ricalcolare campi senza richiamare Crossref.

Possibile alternativa:

salvare il raw JSON in object storage e mantenerne nel database solo il riferimento.

---

# 37. Citation count

Il campo:

```text
is-referenced-by-count
```

può essere utilizzato come segnale.

Non deve però diventare il criterio principale.

Bias possibili:

- favorisce paper vecchi;
- penalizza paper recenti;
- copertura citazionale non necessariamente completa.

Utilizzarlo come feature di ranking, non come hard filter.

---

# 38. References

Se disponibili, salvare le reference.

Sono utili per:

- citation graph;
- backward snowballing;
- identificazione di paper fondamentali;
- costruzione di cluster bibliografici.

---

# 39. Snowballing

Dopo aver identificato paper molto rilevanti:

## Backward snowballing

Analizzare i lavori citati dal paper.

## Forward snowballing

Cercare lavori che citano il paper.

Crossref può contribuire, ma per un citation graph più completo può essere utile integrare altre fonti.

---

# 40. Normalizzazione titoli

Creare:

```text
title_raw
title_normalized
```

Normalizzazione possibile:

```text
lowercase
unicode normalization
strip HTML/XML
collapse whitespace
remove punctuation non significativa
```

Non rimuovere parole informative in modo aggressivo.

---

# 41. Autori

Normalizzare:

```text
given
family
ORCID
sequence
affiliation
```

Non concatenare tutto in una sola stringa come unica rappresentazione.

Conservare anche la struttura originale.

---

# 42. DOI resolver

Il DOI deve essere sempre normalizzato.

Quando serve generare un link:

```text
https://doi.org/{normalized_doi}
```

Non dipendere dal campo URL del publisher come identificatore canonico.

---

# 43. Matching bibliografico

Se l'obiettivo è trovare il DOI di una citazione:

```text
input citation
    |
    v
query.bibliographic
    |
    v
top 5-10 Crossref candidates
    |
    v
local matching
```

Non assumere:

```text
first Crossref result == correct match
```

---

# 44. Score per citation matching

Possibile score:

```text
title_similarity      50%
author_similarity     20%
year_match             15%
journal_similarity     10%
identifier_match        5%
```

Configurabile.

Accettazione automatica solo sopra una soglia elevata.

Esempio:

```text
>= 0.92 -> auto-match
0.80-0.92 -> review
< 0.80 -> no match
```

Le soglie devono essere validate su dataset reali.

---

# 45. Semantic ranking locale

Dopo la discovery Crossref:

```text
title
+
abstract se presente
```

devono essere trasformati in embedding.

Calcolare similarity con:

```text
topic description
research question
```

Questo compensa molte limitazioni della ricerca keyword-based di Crossref.

---

# 46. Screening LLM

Pipeline consigliata:

```text
Crossref
  |
  v
deterministic filtering
  |
  v
embedding ranking
  |
  v
local LLM
  |
  v
frontier LLM solo su subset
```

Il modello locale può gestire:

- classificazione grossolana;
- extraction;
- relevance screening;
- normalizzazione semantica;
- clustering.

Il modello frontier può essere usato soltanto sui paper più promettenti.

---

# 47. Prompt di screening suggerito

Input:

```text
Research question
Title
Abstract
Year
Journal
Authors
Crossref metadata
```

Output strutturato:

```json
{
  "relevant": true,
  "relevance_score": 0.93,
  "reason": "...",
  "topics": [],
  "methodology": "...",
  "keep_for_full_text": true
}
```

---

# 48. Query generator

Un LLM può essere utilizzato per generare varianti delle query.

Input:

```text
research question
synonyms
domain
time range
```

Output:

```json
{
  "title_queries": [],
  "bibliographic_queries": [],
  "author_queries": [],
  "filters": {}
}
```

---

# 49. Regole per il query generator

Il modello deve:

- generare query corte;
- evitare mega-query;
- usare sinonimi;
- variare terminologia accademica;
- variare termini storici;
- generare sia query molto precise sia query ad alto recall;
- non usare boolean syntax come requisito fondamentale.

Esempio:

```text
news sentiment equity returns
financial news stock prices
textual sentiment asset pricing
media sentiment equity market
news analytics trading
information events abnormal returns
```

---

# 50. Query expansion

Possibile processo iterativo:

```text
initial queries
      |
      v
top results
      |
      v
extract terminology
      |
      v
generate additional queries
      |
      v
second Crossref pass
```

Limitare il numero di iterazioni.

Configurazione iniziale:

```text
max query expansion rounds = 2
```

---

# 51. Stop condition

La ricerca può fermarsi quando:

```text
new_unique_doi_rate
```

scende sotto una soglia.

Esempio:

```text
round 1: 1800 nuovi DOI
round 2: 420 nuovi DOI
round 3: 35 nuovi DOI
```

Se la terza iterazione aggiunge pochi risultati realmente rilevanti, fermarsi.

---

# 52. Saturation metric

Definire:

```text
saturation =
new_relevant_unique_results /
total_results_processed
```

Stop possibile quando:

```text
saturation < 1%
```

per più iterazioni consecutive.

La soglia va configurata.

---

# 53. Cache

Tutte le richieste devono essere cacheabili.

Cache key:

```text
endpoint
+
normalized query params
```

Esempio:

```text
SHA256(endpoint + canonical_query_string)
```

---

# 54. TTL cache

Possibile configurazione:

```text
search queries: 7-30 giorni
single DOI metadata: 30-90 giorni
```

Per metadata scientifici il dato cambia relativamente lentamente.

Per pipeline di aggiornamento dedicata può essere usato TTL più lungo.

---

# 55. Idempotenza

L'ingestion deve essere idempotente.

Ripetere la stessa finestra o query non deve creare duplicati.

Chiave primaria:

```text
normalized DOI
```

Fallback:

```text
bibliographic fingerprint
```

---

# 56. Provenance

Ogni record deve sapere da dove arriva.

Esempio:

```json
{
  "source": "crossref",
  "source_queries": [
    "news sentiment stock market",
    "financial news market reaction"
  ],
  "retrieved_at": "...",
  "source_rank": {
    "query_1": 3,
    "query_2": 17
  }
}
```

Questo è fondamentale per ranking e audit.

---

# 57. Log

Loggare almeno:

```text
request_id
timestamp
endpoint
query_hash
HTTP status
latency
retry_count
items_returned
cursor
rate_limit_event
```

Non loggare inutilmente dati personali.

---

# 58. Metriche

Metriche consigliate:

```text
crossref_requests_total
crossref_request_errors_total
crossref_429_total
crossref_latency_seconds
crossref_retry_total
crossref_items_received_total
crossref_unique_dois_total
crossref_duplicate_ratio
crossref_cache_hit_ratio
crossref_query_new_doi_ratio
```

---

# 59. Error handling

Il sistema non deve fallire l'intera pipeline per una singola query.

Struttura:

```text
topic
  |
  +-- query A -> success
  +-- query B -> success
  +-- query C -> failed
  +-- query D -> success
```

Persistenza degli errori:

```text
query
error
attempts
last_attempt_at
```

La query fallita può essere riprocessata successivamente.

---

# 60. Circuit breaker

Se Crossref restituisce ripetutamente:

```text
429
5xx
timeout
```

attivare un circuit breaker temporaneo.

Esempio:

```text
5 errori consecutivi
    ->
pause 60 secondi
```

---

# 61. Limite di parallelismo

Non creare centinaia di worker concorrenti.

Usare una queue con concurrency controllata.

Esempio:

```text
CrossrefQueue
workers = 2-3
```

---

# 62. Bulk download

Se il progetto arriva a dover scaricare:

```text
centinaia di migliaia
o
milioni di record
```

valutare il dataset completo/snapshot Crossref invece di usare la REST API come bulk downloader.

---

# 63. Quando valutare Metadata Plus

Valutare Metadata Plus se:

- il rate limit Polite è realmente un collo di bottiglia;
- servono sincronizzazioni massive frequenti;
- serve maggiore prevedibilità;
- servono snapshot mensili;
- i volumi diventano molto elevati.

Non acquistarlo solo per ottenere risultati "migliori".

---

# 64. Crossref non deve essere l'unica fonte

Architettura raccomandata:

```text
                 TOPIC
                   |
      +------------+------------+
      |            |            |
      v            v            v
   Crossref     OpenAlex    Semantic Scholar
      |            |            |
      +------------+------------+
                   |
                   v
             normalize DOI
                   |
                   v
                merge
                   |
                   v
               dedup
                   |
                   v
              ranking
```

---

# 65. Ruolo di Crossref in un sistema multi-source

Crossref deve essere considerato soprattutto:

```text
canonical DOI source
metadata enrichment source
bibliographic verification source
candidate generator
```

Altri sistemi possono essere migliori per:

```text
semantic search
citation graph
abstract/full-text discovery
```

---

# 66. Merge multi-source

Chiave primaria:

```text
DOI
```

Merge strategy:

```text
Crossref metadata
+
OpenAlex metadata
+
Semantic Scholar metadata
+
eventuali altri provider
```

Conservare provenance per ogni campo quando possibile.

---

# 67. Priorità dei metadati

Esempio:

```text
DOI -> Crossref
publisher -> Crossref
official publication date -> Crossref
citation graph -> OpenAlex/Semantic Scholar
semantic relevance -> embeddings/LLM
abstract -> migliore fonte disponibile
```

Queste priorità devono essere configurabili.

---

# 68. Esempio di chiamata cURL

```bash
curl \
  -H "User-Agent: LiteratureResearchBot/1.0 (mailto:dev@example.com)" \
  "https://api.crossref.org/works?query.title=news%20sentiment%20stock%20market&rows=200&mailto=dev@example.com"
```

---

# 69. Esempio con filtri

```bash
curl \
  -H "User-Agent: LiteratureResearchBot/1.0 (mailto:dev@example.com)" \
  "https://api.crossref.org/works?query.title=news%20sentiment&filter=type:journal-article,from-pub-date:2010-01-01&rows=200&mailto=dev@example.com"
```

---

# 70. Pseudocodice client

```python
def search_crossref(query, query_type="title", filters=None):
    params = {
        f"query.{query_type}": query,
        "rows": 200,
        "mailto": CROSSREF_EMAIL,
    }

    if filters:
        params["filter"] = build_filters(filters)

    return request_with_retry(
        method="GET",
        url="https://api.crossref.org/works",
        params=params,
        headers={
            "User-Agent": CROSSREF_USER_AGENT
        }
    )
```

---

# 71. Pseudocodice candidate generation

```python
candidate_map = {}

for query in generated_queries:
    results = search_crossref(
        query.text,
        query_type=query.type,
        filters=query.filters
    )

    for rank, item in enumerate(results):
        doi = normalize_doi(item.get("DOI"))

        if not doi:
            doi = bibliographic_fingerprint(item)

        candidate = candidate_map.setdefault(
            doi,
            create_candidate(item)
        )

        candidate.query_hits += 1
        candidate.query_sources.append(query.id)
        candidate.crossref_ranks.append(rank)
```

---

# 72. Pseudocodice ranking

```python
score = (
    0.35 * semantic_similarity
    + 0.25 * title_similarity
    + 0.15 * query_coverage_score
    + 0.10 * citation_score
    + 0.10 * metadata_quality_score
    + 0.05 * crossref_rank_score
)
```

Normalizzare tutte le componenti nell'intervallo:

```text
0..1
```

---

# 73. Ranking per recency

Non premiare automaticamente gli articoli recenti.

La recency va usata solo se la research question lo richiede.

Possibile feature separata:

```text
recency_score
```

da attivare per:

- tecnologie recenti;
- AI;
- software;
- medicina aggiornata;
- regolamentazione;
- mercati.

---

# 74. Metadata quality score

Possibile definizione:

```text
+ DOI valido
+ abstract presente
+ autori completi
+ ORCID
+ references
+ journal
+ ISSN
+ publication date
```

Questo score serve a valutare la facilità di analisi del record.

Non deve essere confuso con qualità scientifica.

---

# 75. Test

Creare test automatici per:

```text
DOI normalization
query encoding
pagination
cursor handling
429 retry
5xx retry
deduplication
title normalization
author normalization
date parsing
JATS/XML abstract cleaning
cache
idempotency
```

---

# 76. Integration test

Creare alcune query fisse usate solo per smoke test.

Esempio:

```text
machine learning
climate change
financial news sentiment
```

Il test non deve verificare una lista esatta di risultati, perché l'indice evolve.

Verificare invece:

```text
HTTP 200
message.items esiste
DOI parsing funziona
pagination funziona
```

---

# 77. Configurazione

Esempio:

```yaml
crossref:
  base_url: https://api.crossref.org
  mailto: dev@example.com
  user_agent: LiteratureResearchBot/1.0
  requests_per_second: 8
  concurrency: 3
  timeout_seconds: 30
  max_retries: 5
  rows_per_request: 200
  discovery_top_n: 200
  cache_ttl_days: 14
```

Non hardcodare email o parametri nell'applicazione.

---

# 78. Secrets

Crossref Polite non richiede segreti.

L'email può essere configurazione normale.

Se in futuro viene usato Metadata Plus:

- token/API credential devono essere gestiti tramite secrets manager;
- mai committati nel repository.

---

# 79. Privacy

Non inviare a Crossref:

- dati personali utenti;
- contenuti sensibili;
- prompt interni;
- documenti privati.

Inviare solo query bibliografiche.

---

# 80. Checklist di implementazione

## HTTP client

- [ ] base URL configurabile
- [ ] `mailto`
- [ ] `User-Agent`
- [ ] timeout
- [ ] retry
- [ ] exponential backoff
- [ ] jitter
- [ ] rate limit
- [ ] concurrency limit
- [ ] circuit breaker

## Search

- [ ] `query.title`
- [ ] `query.bibliographic`
- [ ] filters
- [ ] `rows`
- [ ] cursor pagination
- [ ] `select`

## Data

- [ ] DOI normalization
- [ ] title normalization
- [ ] structured authors
- [ ] dates
- [ ] abstract cleaning
- [ ] references
- [ ] raw JSON
- [ ] provenance

## Discovery

- [ ] multiple small queries
- [ ] query generator
- [ ] query expansion
- [ ] dedup
- [ ] query hit count
- [ ] local ranking
- [ ] semantic embeddings
- [ ] LLM screening

## Operations

- [ ] cache
- [ ] metrics
- [ ] logging
- [ ] checkpoint
- [ ] idempotency
- [ ] incremental sync

---

# 81. Anti-pattern da evitare

Non fare:

```text
una singola query enorme
```

Non assumere:

```text
AND / OR / NOT perfettamente supportati
```

Non assumere:

```text
virgolette == exact phrase
```

Non assumere:

```text
primo risultato == risultato corretto
```

Non confrontare direttamente:

```text
Crossref score
```

tra query differenti.

Non filtrare automaticamente:

```text
has-abstract:true
```

per tutta la letteratura.

Non utilizzare:

```text
offset
```

per deep pagination.

Non fare:

```text
centinaia di richieste concorrenti
```

Non usare Crossref come:

```text
unico semantic search engine
```

Non acquistare Metadata Plus solo per "migliorare la qualità dei risultati".

---

# 82. Architettura finale raccomandata

```text
Research Question
        |
        v
Query Generator
        |
        +-------------------------------+
        |                               |
        v                               v
High Precision Queries          High Recall Queries
        |                               |
        +---------------+---------------+
                        |
                        v
                     Crossref
                        |
                        v
                Raw Candidate Pool
                        |
                        v
                  DOI Normalize
                        |
                        v
                     Dedup
                        |
                        v
              Metadata Normalization
                        |
                        v
                Deterministic Ranking
                        |
                        v
                 Embedding Ranking
                        |
                        v
                 Local LLM Screening
                        |
                        v
              Cross-source Enrichment
                        |
            +-----------+-----------+
            |                       |
            v                       v
         OpenAlex           Semantic Scholar
            |                       |
            +-----------+-----------+
                        |
                        v
                 Final Candidate Set
                        |
                        v
              Frontier LLM Analysis
                        |
                        v
                  Literature Corpus
```

---

# 83. Strategia operativa consigliata

Configurazione iniziale:

```text
Crossref Polite Pool
8 requests/sec max
2-3 concurrent requests
200 results per discovery query
10-30 query per topic
DOI deduplication
local ranking
embedding screening
LLM screening
cache
incremental sync
```

Passare a volumi superiori solo quando necessario.

---

# 84. Obiettivo di qualità

Il sistema non deve cercare di chiedere a Crossref:

> "dammi i 100 articoli migliori".

Deve chiedere:

> "dammi un insieme ampio e ragionevolmente rilevante di candidati bibliografici".

La qualità finale deve essere ottenuta combinando:

```text
Crossref ranking
+
multi-query coverage
+
metadata
+
semantic similarity
+
citation signals
+
LLM screening
```

---

# 85. Principio architetturale finale

Crossref deve essere trattato come:

> **un componente di retrieval bibliografico ad alta affidabilità, non come un sistema completo di literature review.**

La strategia ottimale è:

```text
candidate generation
       +
metadata canonicalization
       +
DOI resolution
       +
deduplication
       +
multi-source enrichment
       +
local semantic ranking
```

Questa architettura permette di massimizzare contemporaneamente:

- recall;
- precisione;
- scalabilità;
- qualità;
- costo operativo.

---

# 86. Riferimenti ufficiali

Documentazione generale:

```text
https://www.crossref.org/documentation/retrieve-metadata/rest-api/
```

Accesso e autenticazione:

```text
https://www.crossref.org/documentation/retrieve-metadata/rest-api/access-and-authentication/
```

Filtri:

```text
https://www.crossref.org/documentation/retrieve-metadata/rest-api/rest-api-filters/
```

Suggerimenti d'uso:

```text
https://www.crossref.org/documentation/retrieve-metadata/rest-api/tips-for-using-the-crossref-rest-api/
```

Metadata Plus:

```text
https://www.crossref.org/documentation/metadata-plus/
```

API:

```text
https://api.crossref.org/
```

Community / support tecnico:

```text
https://community.crossref.org/
```

---

# 87. Decisione consigliata per il progetto

Per la prima implementazione:

```text
API: Crossref REST API
Accesso: Polite Pool
API key: NO
Membership: NO
Abbonamento: NO
Metadata Plus: NO, salvo futuri problemi di throughput
Primary key: DOI normalizzato
Discovery: multi-query
Pagination: cursor
Ranking finale: interno
Crossref score: solo segnale locale alla query
Abstract: enrichment, non requisito
Multi-source: raccomandato
Cache: obbligatoria
Retry/backoff: obbligatorio
Rate limiter: obbligatorio
```

Questa deve essere considerata la baseline tecnica dell'integrazione Crossref.
