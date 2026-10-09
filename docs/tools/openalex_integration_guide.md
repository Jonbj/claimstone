# OpenAlex — Guida completa di integrazione per sistemi di ricerca e agenti AI

> **Scopo del documento**  
> Questa guida è pensata per un modello/agent AI o per uno sviluppatore che deve integrare OpenAlex in un progetto software, con particolare attenzione a: qualità dei risultati, massimizzazione della copertura, precision/recall, costi, limiti API, strategie di query, paginazione, deduplicazione, sincronizzazione e uso in pipeline di literature discovery.
>
> **Verifica documentazione:** 7 ottobre 2026.  
> La documentazione OpenAlex è cambiata significativamente nel 2026: evitare guide vecchie che parlano di `mailto=`/“polite pool”, 100.000 chiamate/giorno o vecchi piani Premium/Institutional.

---

## 1. Executive summary

OpenAlex è un knowledge graph aperto della letteratura scientifica e dell'ecosistema della ricerca. Il fulcro è l'entità **Work**, collegata ad autori, fonti, istituzioni, editori, funder, topic, keyword, citazioni, location e altre entità.

### Risposte rapide

| Domanda | Risposta |
|---|---|
| Serve una API key? | **Non strettamente per test/casual use**, ma **sì, raccomandata per qualunque uso reale o produzione**. |
| La API key costa? | **No.** Si ottiene creando gratuitamente un account OpenAlex. |
| Serve un abbonamento? | **No** per la maggior parte dei progetti. Ogni account con key ha **$1/giorno di budget API gratuito**. |
| Posso usare OpenAlex senza key? | Sì, con budget molto ridotto: circa **$0,10/giorno**. Utile solo per prove. |
| Serve essere membri OpenAlex? | **No.** Membership e piani annuali servono a organizzazioni/heavy users e per servizi aggiuntivi. |
| I dati sono gratuiti? | Sì. I dati sono pubblicati con licenza **CC0**. Si paga il servizio/API oltre la quota gratuita, non la licenza dei metadati. |
| Posso scaricare tutto il database? | Sì, tramite **snapshot pubblico gratuito** su S3, senza account AWS. |
| Quanto è grande lo snapshot? | A settembre 2026 circa **745 GB JSONL** oppure **770 GB Parquet**, ognuno contenente una copia completa dei dati (~626M record complessivi tra tutte le entità). |
| Quanto costa una ricerca? | Keyword/full-text search: **$0,001/chiamata**; list/filter: **$0,0001/chiamata**; singleton lookup per ID/DOI: **gratis**. |
| Posso ottenere >10.000 risultati? | Sì, con **cursor pagination**. Non usare basic paging oltre 10.000. |
| Posso fare semantic search? | Sì, su Works. Max 2.000 caratteri, max 50 risultati, 1 req/s. |
| Posso fare reranking? | Sì. `rerank=true` riordina i primi 100 risultati; costa un ulteriore $0,001 per chiamata. |
| Per grandi estrazioni conviene l'API? | No, se si vuole gran parte o tutto il corpus. Usare lo **snapshot**. |

### Raccomandazione architetturale

Per un sistema di ricerca della letteratura:

1. usare **OpenAlex API con API key gratuita** per discovery, query mirate e lookup;
2. preferire **filter** quando si conoscono ID/attributi strutturati;
3. usare **keyword search** per recall testuale;
4. usare **semantic search** come canale complementare per scoprire paper semanticamente vicini ma lessicalmente differenti;
5. usare **rerank** solo sul candidate set iniziale quando la qualità dei top result conta più del costo;
6. combinare più strategie di retrieval e **deduplicare per OpenAlex ID + DOI/PMID/arXiv ID**;
7. recuperare le entità per ID quando possibile, perché il lookup singleton è gratuito;
8. usare `per_page=100`, `select=` e batch OR fino a 100 valori;
9. usare cursor paging per estrazioni estese;
10. se il volume diventa molto grande, spostare il bulk retrieval sullo **snapshot Parquet** e riservare l'API agli aggiornamenti e alle query interattive.

---

## 2. Cos'è OpenAlex

OpenAlex rappresenta il sistema globale della ricerca come un grafo di entità collegate. Tra le entità principali:

- Works
- Authors
- Sources
- Institutions
- Publishers
- Funders
- Topics
- Keywords
- Locations
- Awards
- source lists e altre entità ausiliarie

Il database contiene oltre 320 milioni di Works; il numero cresce continuamente.

Un `Work` può rappresentare, ad esempio:

- articolo di rivista;
- conference paper;
- libro;
- capitolo;
- dataset;
- tesi/dissertazione;
- preprint;
- altri documenti accademici.

OpenAlex integra metadati provenienti da varie fonti, tra cui Crossref, DataCite, PubMed, repository OAI-PMH, ORCID tramite i record delle pubblicazioni, Microsoft Academic Graph storico e altre fonti curate.

### Punto importante: Work vs copie/location

OpenAlex cerca di rappresentare **una pubblicazione come un Work**, anche se esistono più copie:

- versione publisher;
- preprint arXiv;
- manuscript accettato;
- deposito in repository istituzionale;
- copia su PubMed Central, ecc.

Queste copie diventano normalmente `locations` dello stesso Work anziché Work separati. Questo è molto utile per deduplicazione e per trovare il miglior accesso OA.

---

## 3. Licenza e riutilizzo

I metadati OpenAlex sono distribuiti con licenza **CC0/public domain dedication**.

Conseguenze pratiche:

- non serve una membership per riutilizzare i dati;
- non è limitato al solo uso personale;
- i dati possono essere utilizzati in applicazioni commerciali;
- OpenAlex monetizza servizi, API a volume, sincronizzazione e supporto, non l'accesso legale ai metadati.

Verificare separatamente eventuali licenze/copyright dei PDF o dei full text a cui OpenAlex rimanda: CC0 sui metadati non implica che il testo integrale di ogni pubblicazione sia liberamente riutilizzabile.

---

## 4. Autenticazione e API key

### 4.1 Serve una API key?

Per piccoli test, no. OpenAlex consente ancora richieste senza key, ma il budget anonimo è limitato a circa **$0,10/giorno**.

Per un'applicazione, un agente AI, una pipeline schedulata o un progetto di produzione, trattare la key come **obbligatoria di fatto**.

Con account gratuito si ottiene:

- API key gratuita;
- **$1/giorno** di budget API;
- dashboard/monitoraggio usage;
- capacità circa 10× superiore all'uso senza key.

### 4.2 Come ottenere la key

1. creare un account su OpenAlex;
2. andare nelle impostazioni API;
3. copiare la API key.

Pagina indicata dalla documentazione:

`https://openalex.org/settings/api`

### 4.3 Come inviarla

Query string:

```bash
curl "https://api.openalex.org/works?api_key=YOUR_KEY"
```

Oppure, preferibile in produzione, bearer token:

```bash
curl \
  -H "Authorization: Bearer YOUR_KEY" \
  "https://api.openalex.org/works"
```

### 4.4 Sicurezza

Non hardcodare la key nel repository.

Usare ad esempio:

```bash
OPENALEX_API_KEY=...
```

E lato applicazione:

- environment variable;
- secrets manager;
- vault;
- secret del sistema CI/CD.

La key può essere ruotata. OpenAlex permette di scegliere se invalidare la precedente immediatamente oppure mantenere una breve finestra di sovrapposizione per una rotazione senza downtime.

---

## 5. Pricing e budget API — modello 2026

Il modello corrente è usage-based.

### 5.1 Quota gratuita

Con account/key:

**$1 di usage API gratuito ogni giorno**, reset a mezzanotte UTC.

Senza key:

**$0,10/giorno**.

### 5.2 Costi principali

| Operazione | Prezzo indicativo per 1.000 chiamate | Costo/chiamata |
|---|---:|---:|
| Singleton per ID/DOI | $0 | $0 |
| List + filter | $0,10 | $0,0001 |
| Search | $1 | $0,001 |
| Group-by su list/filter | $0,10 | $0,0001 |
| Group-by su search | $1 | $0,001 |
| Semantic search | $1 | $0,001 |
| Rerank | +$1 | +$0,001 |
| Download content/PDF | $10 | $0,01 |

Quindi il budget gratuito giornaliero di $1 vale indicativamente:

- **10.000** chiamate list/filter;
- **1.000** search;
- **500** search con rerank;
- **100** download content/PDF;
- singleton lookups per ID/DOI: gratuiti.

### 5.3 Prepaid / pay-as-you-go

Se si supera il budget gratuito, si può acquistare usage prepagato in incrementi da $1.

La documentazione corrente indica che il credito prepagato:

- viene consumato solo dopo il budget gratuito giornaliero;
- scade 3 mesi dopo l'acquisto più recente.

### 5.4 Membership/piani annuali

Non sono necessari per usare OpenAlex.

Piani indicati a ottobre 2026:

- **Member**: $5.000/anno, budget $20/giorno;
- **Member+**: $10.000/anno, budget $100/giorno, include daily sync/snapshot e altri vantaggi;
- **Partner**: da $20.000/anno, budget $200+/giorno e supporto maggiore.

Per un progetto software che fa retrieval di letteratura, partire dal piano gratuito e misurare l'uso prima di valutare un piano.

---

## 6. Rate limit e limiti tecnici

### 6.1 Request rate

Un `429 Too Many Requests` può essere restituito quando:

- si esaurisce il budget giornaliero;
- si supera il limite di **100 richieste/secondo**.

La semantic search ha inoltre un limite più severo specifico: **1 richiesta/secondo**.

### 6.2 Limiti query

| Limite | Valore |
|---|---:|
| valori OR per singolo filtro | 100 |
| `per_page` supportato | max 100 |
| `sample` | max 10.000 |
| basic paging | primi 10.000 risultati |
| semantic search | max 50 risultati/query |
| input semantic search | max 2.000 caratteri usati |

OpenAlex accetta ancora in alcuni casi `per_page=200` per compatibilità legacy, ma è deprecato. **Usare 100**.

### 6.3 Monitoraggio usage

Controllare gli header:

- `X-RateLimit-Limit`
- `X-RateLimit-Remaining`
- `X-RateLimit-Credits-Used`
- `X-RateLimit-Reset`

Endpoint utile:

```bash
curl "https://api.openalex.org/rate-limit?api_key=YOUR_KEY"
```

Registrare queste metriche in produzione.

---

## 7. Endpoint di base

Base URL:

```text
https://api.openalex.org
```

Pattern:

```text
/{entity_plural}
/{entity_plural}/{id}
```

Esempi:

```text
/works
/works/W2741809807
/authors
/authors/A5023888391
/sources
/institutions
/topics
/keywords
/locations
```

---

## 8. Regola fondamentale: preferire gli ID alle stringhe

OpenAlex raccomanda esplicitamente un pattern a due step quando si deve filtrare su entità quali:

- autore;
- istituzione;
- source/journal;
- topic;
- publisher;
- funder.

### Sbagliato

Concettualmente:

```text
works where author name = "John Smith"
```

Il nome è ambiguo.

### Corretto

1. cercare l'autore:

```http
GET /authors?search=John%20Smith
```

2. scegliere/validare l'ID corretto;
3. filtrare i Works tramite ID:

```http
GET /works?filter=authorships.author.id:A123456789
```

Questa regola aumenta drasticamente precisione e riproducibilità.

### Validazione entity resolution

Quando si risolve un autore o un'istituzione, non prendere automaticamente il primo risultato se la query è ambigua.

Usare segnali come:

- ORCID;
- ROR;
- affiliazione;
- lavori noti;
- topic;
- coautori;
- paese;
- URL esterni.

---

## 9. Lookup diretto: il canale più economico e preciso

Quando è noto un identificatore, preferire il lookup diretto.

Esempi:

```http
GET /works/W2741809807
```

Per DOI, usare le forme supportate dalla API/documentazione. È preferibile normalizzare gli identificatori in input.

I singleton sono gratuiti secondo il pricing corrente: sfruttarli per enrichment dopo la discovery.

### Pattern consigliato

**Discovery costosa → ID → enrichment gratuito.**

Non ripetere search costose per recuperare dettagli già associati a ID noti.

---

## 10. Filters: la tecnica più efficiente quando il requisito è strutturato

I filter costano circa 1/10 rispetto alle search e sono deterministici.

Sintassi:

```http
GET /works?filter=publication_year:2024,is_oa:true
```

### AND

Filtri separati da virgola:

```text
filter=publication_year:2024,is_oa:true
```

### NOT

```text
filter=country_code:!us
```

### OR

Usare `|` all'interno dello stesso filtro:

```text
filter=institutions.country_code:fr|gb
```

Fino a **100 valori**.

### Batch di DOI/ID

Esempio:

```http
GET /works?filter=doi:10.1234/a|10.1234/b|10.1234/c&per_page=100
```

Questo è uno dei pattern migliori per ridurre drasticamente numero di richieste e costo.

### Date

Esempio:

```text
filter=from_publication_date:2024-01-01,to_publication_date:2026-12-31
```

### Utilizzo consigliato

Se una condizione è rappresentabile da un campo strutturato, **usare filter invece di inserire quella condizione nella query testuale**.

Esempio:

Meglio:

```text
search="machine learning" + filter publication_year >= 2024
```

che:

```text
search="machine learning papers published after 2024"
```

---

## 11. Keyword/full-text search

Parametro principale:

```http
GET /works?search=dna
```

Per Works, la search può considerare:

- titolo;
- abstract;
- full text indicizzato;
- keyword.

La ricerca applica normalmente:

- stemming;
- rimozione stopword;
- matching di parole intere;
- ranking per relevance.

### 11.1 Scope più controllati

Per Works sono disponibili anche scope specifici come:

```text
search.title=
search.title_and_abstract=
search.title_abstract_keywords=
```

E le corrispondenti forme `.exact`.

Per un motore di ricerca bibliografica, `search.title_abstract_keywords` è spesso una scelta molto utile perché riduce il rumore rispetto al full-text completo, pur mantenendo buona recall.

### 11.2 Exact search

```text
search.exact=surgery
```

Disabilita lo stemming.

Usarla quando:

- servono token esatti;
- nomenclature tecniche non devono essere conflated;
- si usano wildcard.

### 11.3 Boolean search

Operatori uppercase:

- `AND`
- `OR`
- `NOT`

Esempio:

```text
(elmo AND "sesame street") NOT (cookie OR monster)
```

Per query sistematiche, costruire esplicitamente i gruppi booleani invece di affidarsi a una frase naturale.

### 11.4 Phrase search

```text
"climate change"
```

Le virgolette richiedono la frase.

### 11.5 Proximity search

```text
"climate change"~5
```

Trova termini vicini entro una finestra/positional budget.

È disponibile anche la prossimità tra frasi:

```text
"machine learning"~5~"neural network"
```

Questa funzionalità è molto utile per systematic review e high-recall retrieval.

### 11.6 Wildcard

Supportate:

- `*` = zero o più caratteri;
- `?` = un carattere.

Esempio:

```text
search.exact=machin*
```

Vincoli:

- almeno 3 caratteri prima della wildcard;
- niente leading wildcard;
- usare la variante `.exact`.

### 11.7 Fuzzy search

```text
machin~1
```

Edit distance consentita: 0, 1 o 2.

Usarla con parsimonia perché può aumentare il rumore.

---

## 12. Relevance e reranking

La search restituisce `relevance_score` e, di default, ordina per rilevanza.

Il ranking incorpora tra i segnali:

- similarità testuale;
- numero di citazioni con contributo limitato/cappato;
- piccolo boost da keyword coerenti.

### Rerank

```http
GET /works?search.title_abstract_keywords=remote%20work%20productivity&rerank=true
```

Effetto:

- riordina i primi **100** candidati;
- produce `rerank_score`;
- dal risultato 101 in poi l'ordine è quello normale;
- costa +$0,001/chiamata;
- non cambia l'insieme complessivo, solo l'ordine dei primi 100;
- non si combina con sort alternativo, `group_by`, `sample` o semantic search.

### Quando usarlo

Usare rerank quando:

- si mostrano pochi risultati a un utente;
- si vuole massimizzare precision@10 / precision@20;
- il query intent è complesso;
- il costo aggiuntivo è accettabile.

Non usarlo durante sweep massivi o paginazione bulk se interessa solo raccogliere tutti i candidati.

---

## 13. Semantic search

Endpoint/logica:

```http
GET /works?search.semantic=predicting%20drug%20toxicity%20from%20molecular%20structure
```

OpenAlex genera embedding di titolo + abstract dei Works tramite **GTE Large EN**, vettori 1024-dimensionali, e confronta la query via cosine similarity.

### Vantaggi

È utile per:

- query concettuali;
- abstract;
- grant description;
- descrizioni lunghe;
- scoperta di sinonimi/terminologie non previste;
- recall semantica oltre il lessico esatto.

### Limiti

- usa max **2.000 caratteri** della query;
- max **50 risultati**;
- max **1 req/s**;
- non può essere combinata con altri parametri search;
- alcuni filter non sono supportati, tra cui `last_known_institutions.country_code`/`country_code` shorthand e `cited_by_count`.

### Strategia consigliata

**Non sostituire la keyword search con la semantic search.**

Usare entrambe:

1. query keyword/boolean ad alta precisione;
2. query più espansa ad alta recall;
3. semantic search con descrizione del problema;
4. union dei candidate set;
5. deduplicazione;
6. scoring/reranking downstream.

Per systematic review o literature discovery questo ensemble è normalmente più robusto di un singolo metodo.

---

## 14. Query decomposition per massimizzare quantità e qualità

Un agente non dovrebbe inviare una sola query lunga e considerare il risultato esaustivo.

Per una domanda di ricerca `Q`:

### Step A — estrazione concetti

Identificare:

- concetto principale;
- sinonimi;
- acronimi;
- nomi storici;
- spelling US/UK;
- termini tecnici;
- concetti correlati ma non equivalenti;
- popolazione;
- intervento/esposizione;
- outcome;
- dominio;
- periodo.

### Step B — query families

Generare almeno:

- query precisa;
- query estesa;
- query sinonimi;
- query acronimi;
- query proximity;
- query semantic.

### Step C — filtri strutturati

Applicare separatamente:

- anni;
- tipo documento;
- lingua se necessaria;
- OA se richiesto;
- source/index se richiesto;
- istituzione/autore tramite ID.

### Step D — consolidamento

Unire i risultati tramite chiave primaria:

1. OpenAlex Work ID;
2. DOI normalizzato;
3. PMID;
4. arXiv ID;
5. in ultima istanza fingerprint titolo+anno+primo autore.

Non usare il solo titolo come identità.

---

## 15. Core corpus vs expansion corpus

OpenAlex distingue un **core corpus** e un **expansion corpus**.

Il core è il default ed è raccomandato per:

- bibliometria;
- analisi affidabili;
- ricerca con metadati ben descritti.

L'expansion corpus contiene record mediamente più sottili/noisy, spesso provenienti da repository o DataCite.

Per ampliare al massimo la copertura:

```text
corpus=all
```

### Strategia qualità/quantità

- **alta qualità / analisi bibliometrica** → `core`;
- **massimo recall / finding obscure datasets o documenti** → `all`;
- mantenere `is_xpac`/corpus origin nel record locale per poter distinguere le due classi.

Le vecchie opzioni `include_xpac=true` e `is_xpac` sono legacy/deprecate: preferire `corpus=` nel nuovo codice.

---

## 16. Source quality e controllo del rumore

OpenAlex punta a copertura ampia, non a essere esclusivamente un indice selettivo di riviste.

Quindi, a seconda del caso d'uso, un agente dovrebbe poter applicare segnali di qualità.

OpenAlex espone informazioni su:

- source type;
- indexing;
- presenza in liste curate;
- DOAJ;
- citazioni;
- source metrics;
- OA;
- publication type;
- retraction status;
- repository/publisher location.

Sono disponibili `source lists` curate, ad esempio liste istituzionali/disciplinari. Non equivalgono agli `indexed_in`.

### Modello consigliato

Separare due concetti:

**relevance_score** = quanto il contenuto sembra pertinente.

**quality_score** = quanto la fonte/documento soddisfa i criteri metodologici del progetto.

Non usare citation count come unico quality score.

Per lavori recenti, citation count favorisce artificialmente lavori più vecchi.

---

## 17. Citazioni: utilità e limiti

Ogni Work può fornire:

- `referenced_works`;
- `cited_by_count`;
- metriche derivate come FWCI quando disponibili.

OpenAlex costruisce le citazioni estraendo le reference list dalle fonti metadata e, quando possibile, dal full text OA, quindi tenta di associarle a Works esistenti.

La citation graph può essere incompleta perché:

- alcune fonti non depositano le reference;
- alcune citazioni non hanno DOI;
- metadata matching può fallire;
- il lavoro citato può non esistere in OpenAlex.

### Uso consigliato per discovery

Dopo aver trovato seed paper molto pertinenti:

1. backward chaining tramite `referenced_works`;
2. forward chaining tramite citing works;
3. related/semantic retrieval;
4. ripetizione per 1–2 hop con limiti.

Questo migliora sensibilmente il recall rispetto alle sole keyword.

---

## 18. Autori e disambiguazione

OpenAlex usa entity resolution/ML per raggruppare varianti di nomi sotto una stessa entità autore.

Segnali includono, tra gli altri:

- nome;
- coautori;
- affiliazioni;
- topic;
- citazioni;
- ORCID.

Non assumere che l'author ID sia infallibile.

### ORCID

ORCID è molto utile ma non è presente ovunque. Un `orcid: null` non implica un problema.

OpenAlex non interroga ORCID per ogni autore: normalmente riceve l'ORCID dai metadata del work (publisher, Crossref, DataCite, repository ecc.).

Per disambiguazione critica, verificare più segnali.

---

## 19. Abstract

OpenAlex non distribuisce normalmente l'abstract come semplice stringa; il campo storico è spesso:

```text
abstract_inverted_index
```

che mappa parole → posizioni.

L'applicazione può ricostruire il plaintext ordinando i token per posizione.

### Attenzione alla copertura

La presenza di abstract non è uniforme nel tempo. La documentazione indica, a titolo di esempio, una copertura superiore al 60% per lavori del 2022 contro circa 45% per lavori pre-2000.

Quindi:

- non filtrare sempre `has_abstract:true` se il recall storico è importante;
- distinguere `missing abstract` da `irrelevant`;
- usare title/keyword/topic/citation graph come fallback.

---

## 20. Open Access e full text

Il Work può contenere:

- `open_access.is_oa`;
- `open_access.oa_status`;
- `open_access.oa_url`;
- `best_oa_location`;
- `locations`;
- `content_urls` quando OpenAlex ha contenuto cache disponibile.

OpenAlex considera OA un'opera per cui esiste un URL legalmente leggibile senza pagamento/login.

Il sistema sceglie una `best_oa_location` privilegiando, tra gli altri criteri:

- publisher rispetto a repository;
- published version rispetto ad accepted/submitted;
- direct PDF;
- repository principali.

### Per un downloader

Ordine suggerito:

1. OpenAlex `content_urls` se il caso d'uso e le condizioni lo consentono;
2. `best_oa_location.pdf_url` / OA URL;
3. altre `locations` OA;
4. fallback ad altri servizi autorizzati.

Non confondere metadata CC0 con licenza del documento.

---

## 21. `select=` per performance e costi indiretti

Usare:

```http
GET /works?search=...&select=id,doi,title,publication_year,cited_by_count
```

Benefici:

- payload ridotto;
- meno banda;
- parsing più veloce;
- cache più efficiente;
- minore RAM;
- migliori performance dell'agente.

`select` supporta solo campi root-level, non nested path.

Esempio valido:

```text
select=id,open_access
```

Non valido:

```text
select=open_access.is_oa
```

### Strategia two-pass

Per discovery massiva:

**Pass 1** — pochi campi:

```text
id,doi,title,publication_year,cited_by_count,relevance_score
```

**Pass 2** — singleton lookup gratuito solo sui candidati realmente selezionati.

---

## 22. Pagination corretta

### Basic paging

```http
GET /works?page=2&per_page=100
```

Usarla solo entro i primi 10.000 risultati.

### Cursor pagination

Prima pagina:

```http
GET /works?filter=publication_year:2024&per_page=100&cursor=*
```

Estrarre:

```json
meta.next_cursor
```

Poi:

```http
GET /works?filter=publication_year:2024&per_page=100&cursor=<next_cursor>
```

Continuare finché:

- `next_cursor == null`, oppure
- `results` è vuoto.

### Regola

Non generare/modificare il cursor. Usare esattamente quello restituito dal server.

### Resume

Per job lunghi salvare in checkpoint:

- canonical query;
- cursor;
- numero pagine;
- record acquisiti;
- timestamp;
- budget residuo.

---

## 23. Non usare l'API per scaricare l'intero database

OpenAlex raccomanda esplicitamente di **non cursor-pageare `/works` o `/authors` per scaricare tutto**.

Per bulk completo usare lo snapshot.

---

## 24. Snapshot OpenAlex

Bucket pubblico S3:

```text
s3://openalex
```

Download senza account AWS:

```bash
aws s3 sync "s3://openalex" "openalex-snapshot" --no-sign-request
```

Meglio scaricare un solo formato.

### Formati

- JSON Lines gzip;
- Apache Parquet/Snappy.

Per analytics, data lake, DuckDB, Spark o query batch, **preferire Parquet**.

A settembre 2026:

- JSONL ~745 GB compressi;
- Parquet ~770 GB compressi;
- Works da soli rappresentano la maggior parte del volume.

Lo snapshot pubblico è aggiornato periodicamente/trimestralmente secondo il prodotto corrente.

### Use case ideali

Usare snapshot se:

- si vuole una grande percentuale del corpus;
- si fanno analisi globali;
- si costruisce un indice locale;
- si fanno milioni di query ripetitive sullo stesso dataset;
- si vuole ridurre dipendenza dall'API.

---

## 25. Daily sync e aggiornamenti

I piani Member+ e Partner includono snapshot/dati aggiornati giornalmente e filtri premium di sync come:

- `from_created_date`;
- `from_updated_date`.

Esempio concettuale:

```text
filter=from_updated_date:2026-10-01
```

Per progetti piccoli non è necessario.

Possibili strategie:

### Livello 1 — piccolo progetto

Query live e cache locale.

### Livello 2 — progetto medio

Ingest iniziale tramite API mirata + requery periodica dei topic/query interessati.

### Livello 3 — grande progetto

Snapshot + DB/warehouse locale + API per enrichment/freshness.

### Livello 4 — mission critical/freshness giornaliera

Valutare Member+ / Partner e sync ufficiale.

---

## 26. Error handling

Implementare almeno:

- retry con exponential backoff;
- jitter;
- retry solo su errori transient;
- rispetto di `Retry-After` se presente;
- timeout connessione e lettura;
- circuit breaker se necessario;
- logging structured;
- idempotenza degli ingest.

Esempio concettuale:

```python
for attempt in range(max_retries):
    response = request(...)

    if response.status_code == 200:
        return response

    if response.status_code in (429, 500, 502, 503, 504):
        sleep(backoff_with_jitter(attempt))
        continue

    raise_permanent_error(response)
```

Non fare retry cieco su `400`.

---

## 27. Cache

Una buona integrazione OpenAlex dovrebbe usare cache aggressiva per:

- singleton entity lookup;
- ID resolution;
- DOI → Work;
- author/source/institution metadata;
- query già eseguite;
- pagine statiche di risultati quando appropriato.

### Cache key

Usare una canonicalizzazione deterministica di:

- endpoint;
- parametri query ordinati;
- corpus;
- select;
- sort;
- versione interna del retrieval strategy.

### TTL suggerito

Indicativamente:

- entity metadata: giorni/settimane;
- vecchi Works: TTL lungo;
- lavori molto recenti: TTL più breve;
- search result: 6–24h se freshness non critica.

---

## 28. Query cost-aware

L'agente deve essere consapevole del costo.

Priorità:

1. singleton gratuito;
2. filter/list;
3. keyword search;
4. semantic search;
5. rerank;
6. content download.

Prima di una grande operazione:

- leggere `meta.count`;
- stimare pagine = `ceil(count / 100)`;
- stimare costo;
- confrontare con budget residuo.

OpenAlex espone anche `/query`/OQL con controllo del costo prima dell'esecuzione per query compatibili.

---

## 29. OQL — OpenAlex Query Language

OpenAlex dispone di OQL per query più espressive e salvabili.

È utile quando servono:

- analisi aggregate;
- split;
- calcoli;
- query complesse leggibili;
- query che devono essere generate da un agente AI in forma più semantica.

La valutazione costi segue grosso modo gli stessi principi dell'API classica.

L'endpoint `/query` può verificare una query e mostrarne il costo prima dell'esecuzione.

### Raccomandazione

Per una prima integrazione applicativa, costruire bene il client REST classico. Aggiungere OQL come secondo livello per analytics/agent queries complesse, non come prerequisito.

---

## 30. Strategia consigliata per un agente di literature research

### Fase 1 — Query planning

Input: domanda dell'utente.

Il planner produce una struttura tipo:

```json
{
  "concepts": [],
  "synonyms": {},
  "acronyms": [],
  "exact_phrases": [],
  "date_range": null,
  "document_types": [],
  "must_include": [],
  "must_exclude": [],
  "semantic_query": "",
  "quality_constraints": {},
  "target_recall": "high"
}
```

### Fase 2 — Entity resolution

Risolvere nomi → ID per:

- author;
- institution;
- source;
- topic;
- funder;
- publisher.

Conservare candidate + confidence.

### Fase 3 — Multi-query retrieval

Eseguire in parallelo controllato:

1. precise boolean query;
2. broad synonym query;
3. title/abstract/keyword query;
4. proximity query;
5. semantic query;
6. eventuali topic/keyword filters;
7. citation expansion da seed paper.

### Fase 4 — Merge/dedup

Deduplicare per OpenAlex Work ID come chiave primaria.

### Fase 5 — Enrichment

Per i candidati selezionati recuperare dettagli tramite singleton gratuito.

### Fase 6 — Local scoring

Calcolare un punteggio separato da OpenAlex:

```text
final_score =
    semantic_relevance
  + lexical_relevance
  + query_coverage
  + source_quality
  + recency_adjustment
  + citation_signal_normalized_by_age
  + evidence_availability
  - exclusion_penalties
```

Non lasciare che `cited_by_count` domini il ranking.

### Fase 7 — Snowballing

Per top seed:

- references;
- citing works;
- stesso autore se rilevante;
- stessa topic/keyword cluster;
- semantic neighbors.

### Fase 8 — Stop condition

Possibili criteri:

- nessun nuovo paper rilevante negli ultimi N batch;
- novelty rate sotto soglia;
- coverage dei concetti sufficiente;
- budget massimo raggiunto;
- saturation della citation expansion.

---

## 31. Recall vs precision: profili suggeriti

### Profilo `HIGH_PRECISION`

- `corpus=core`;
- `search.title_abstract_keywords`;
- phrase/exact quando possibile;
- filtri strutturati;
- rerank;
- source-quality constraints;
- top 20–100.

### Profilo `BALANCED`

- `corpus=core`;
- 2–4 keyword query variants;
- semantic search;
- no filtri di source troppo aggressivi;
- citation expansion top seeds;
- rerank solo sul primo set.

### Profilo `HIGH_RECALL`

- `corpus=all` dove opportuno;
- synonym expansion;
- wildcard;
- proximity;
- query multiple;
- semantic search;
- citation snowballing;
- repository/preprint inclusi;
- dedup forte;
- ranking e screening downstream.

---

## 32. Systematic-review-like retrieval

Per flussi che cercano elevata esaustività:

1. tradurre la domanda in blocchi concettuali;
2. creare sinonimi per ogni blocco;
3. usare OR dentro il blocco e AND fra blocchi;
4. aggiungere wildcard solo dove linguisticamente sensato;
5. usare phrase/proximity;
6. eseguire una variante stemmed e una exact/truncated quando serve;
7. mantenere log di ogni query;
8. salvare data/ora e `meta.count`;
9. deduplicare;
10. aggiungere semantic retrieval;
11. eseguire backward/forward citation chasing;
12. documentare motivi di inclusione/esclusione.

### Riproducibilità

Salvare:

- query completa URL-encoded o canonicalizzata;
- timestamp;
- OpenAlex API/version assumptions;
- corpus (`core/all`);
- filtri;
- `select`;
- sorting;
- eventuale rerank;
- cursor progress;
- conteggio iniziale;
- numero finale deduplicato.

---

## 33. Full text: quando e come usarlo

Il retrieval full-text può aumentare notevolmente costi e complessità.

Non scaricare PDF per tutti i risultati iniziali.

Pipeline suggerita:

1. metadata discovery;
2. title/abstract screening;
3. ranking;
4. solo top candidati → full-text retrieval;
5. parsing/TEI/local indexing.

Il download content OpenAlex è tariffato circa **$0,01 per file** secondo il pricing corrente.

OpenAlex mantiene decine di milioni di full-text OA/PDF e versioni TEI XML; per sincronizzare l'intero archivio full-text esiste un add-on separato associato ai piani annuali.

---

## 34. Data quality: cosa OpenAlex fa bene

Punti forti:

- copertura molto ampia;
- entity graph integrato;
- DOI/PMID/arXiv/location consolidation;
- forte accesso a repository;
- author disambiguation;
- institutional linkage;
- citation graph;
- OA detection;
- source metadata;
- topics/keywords;
- search moderna + semantic search;
- snapshot open.

Per un sistema di discovery, OpenAlex è particolarmente utile come **backbone di normalizzazione e graph enrichment**.

---

## 35. Data quality: limiti da considerare

Non assumere che OpenAlex sia ground truth perfetta.

### Possibili problemi

- author disambiguation errata;
- merge/split imperfetti dei Works;
- abstract mancanti;
- reference list incompleta;
- citazioni mancanti;
- repository metadata poveri;
- record expansion più rumorosi;
- publication date variabile tra online/print;
- classificazioni topic/keyword generate algoritmicamente;
- source metadata non sempre perfetti;
- lavori molto recenti con metadata incompleti.

### Regola applicativa

Per decisioni critiche, conservare provenance e identificatori esterni e poter validare contro le fonti originali.

---

## 36. Deduplicazione locale

Anche se OpenAlex fa già molta deduplicazione, un aggregatore multi-source deve deduplicare di nuovo.

Ordine consigliato:

### Livello 1 — identità forte

- OpenAlex Work ID;
- DOI normalizzato;
- PMID;
- PMCID;
- arXiv ID;
- altri PID.

### Livello 2 — identità fuzzy

Solo se mancano PID:

- titolo normalizzato;
- primo autore;
- anno ±1;
- source;
- similarity score.

### Normalizzazione DOI

Convertire ad esempio:

```text
https://doi.org/10.xxxx/yyyy
DOI:10.xxxx/yyyy
10.xxxx/yyyy
```

alla forma canonica:

```text
10.xxxx/yyyy
```

lowercase, trim, rimozione prefissi.

---

## 37. Esempi di query operative

### OA works dal 2024

```http
GET https://api.openalex.org/works?filter=from_publication_date:2024-01-01,is_oa:true&per_page=100
```

### Search mirata

```http
GET https://api.openalex.org/works?search.title_abstract_keywords=%22retrieval%20augmented%20generation%22&per_page=100
```

### Search + rerank

```http
GET https://api.openalex.org/works?search.title_abstract_keywords=LLM%20agent%20scientific%20literature&rerank=true&per_page=100
```

### Semantic

```http
GET https://api.openalex.org/works?search.semantic=systems%20that%20use%20large%20language%20models%20to%20automatically%20discover%20and%20review%20scientific%20literature
```

### Batch DOI

```http
GET https://api.openalex.org/works?filter=doi:10.1234/a|10.1234/b|10.1234/c&per_page=100
```

### Cursor

```http
GET https://api.openalex.org/works?filter=publication_year:2025&per_page=100&cursor=*
```

---

## 38. Client implementation — requisiti minimi

Creare un modulo OpenAlex separato con responsabilità chiare.

Esempio:

```text
openalex/
  client.py
  auth.py
  models.py
  filters.py
  search.py
  pagination.py
  entity_resolution.py
  dedup.py
  scoring.py
  cache.py
  rate_limit.py
  exceptions.py
  telemetry.py
```

### `OpenAlexClient`

Dovrebbe esporre almeno:

```text
get_work(id_or_doi)
get_author(id)
search_works(...)
semantic_search_works(...)
filter_works(...)
resolve_author(...)
resolve_institution(...)
resolve_source(...)
iterate_cursor(...)
batch_lookup_dois(...)
get_rate_limit_status()
```

---

## 39. Configurazione raccomandata

```yaml
openalex:
  base_url: https://api.openalex.org
  api_key_env: OPENALEX_API_KEY
  timeout_seconds: 30
  max_retries: 5
  per_page: 100
  concurrency: 8
  semantic_concurrency: 1
  cache_enabled: true
  default_corpus: core
  default_select:
    - id
    - doi
    - title
    - publication_year
    - type
    - authorships
    - primary_location
    - open_access
    - cited_by_count
    - relevance_score
```

Non impostare 100 req/s come target. È un limite, non una raccomandazione. Usare concorrenza conservativa e adattiva.

---

## 40. Telemetria

Registrare per ogni chiamata:

```text
provider = openalex
endpoint
query_hash
http_status
latency_ms
result_count
page_size
credits_used
remaining_budget
retry_count
cache_hit
request_type = singleton|filter|search|semantic|rerank|content
```

Dashboard utili:

- cost/day;
- calls/day per tipo;
- hit cache;
- error rate;
- 429 count;
- P50/P95 latency;
- risultati unici per query;
- costo per nuovo Work trovato;
- precision@K se esiste feedback umano.

---

## 41. Budget optimizer

Per un agente autonomo, aggiungere una policy cost-aware.

Pseudo-logica:

```text
if identifier_known:
    singleton_lookup()
elif structured_condition_available:
    filter_query()
else:
    search_query()

if top_results_need_better_precision and budget_ok:
    rerank()

if lexical_search_saturates or vocabulary_uncertain:
    semantic_search()

if expected_result_count_is_huge:
    consider_snapshot_or_narrow_query()
```

---

## 42. Anti-pattern da evitare

### 1. Una sola query naturale

Non garantisce copertura.

### 2. Filtrare per nome invece che per ID

Ambiguo e meno riproducibile.

### 3. Scaricare milioni di record con cursor API

Usare snapshot.

### 4. `per_page=25` in batch

Usare 100.

### 5. Richiedere l'oggetto completo per ogni candidate

Usare `select` e two-pass retrieval.

### 6. Usare solo cited_by_count come qualità

Bias per anzianità/campo.

### 7. Ignorare il core/expansion corpus

Può alterare qualità e quantità drasticamente.

### 8. Ignorare gli identificatori esterni

Peggiora dedup e verificabilità.

### 9. Rerankare ogni pagina

Costoso e inutile per bulk recall; il rerank serve soprattutto ai primi 100.

### 10. Treating missing abstract as exclusion

Crea bias verso pubblicazioni recenti e metadata-rich.

### 11. Fare retry su qualunque 4xx

Un 400 è quasi sempre un errore della query e va corretto.

### 12. Usare documentazione vecchia sul polite pool

Il modello 2026 è basato su API key + usage budget.

---

## 43. Strategia consigliata per massima qualità con costo contenuto

Per una ricerca tipica:

### Stage 1

`search.title_abstract_keywords` con query precisa, `per_page=100`, `select` ridotto.

### Stage 2

2–5 query lessicali alternative con sinonimi/acronimi.

### Stage 3

1–3 semantic search con descrizioni differenti dell'intento.

### Stage 4

Merge/dedup.

### Stage 5

Rerank locale oppure `rerank=true` solo sulla query principale/top candidate.

### Stage 6

Singleton enrichment dei top N.

### Stage 7

Citation snowballing dai migliori seed.

### Stage 8

Seconda dedup + relevance scoring.

Questo massimizza il rapporto qualità/costo molto meglio di migliaia di search generiche.

---

## 44. Strategia consigliata per massima quantità

Se il requisito è “trova tutto il possibile”:

1. `corpus=all` quando appropriato;
2. più query boolean;
3. stemming + exact/wildcard variants;
4. proximity queries;
5. semantic queries;
6. topic/keyword expansion;
7. references + citing works;
8. query per autori/istituzioni chiave emersi;
9. inclusion di repository/preprint;
10. stop per saturation;
11. se il candidate universe diventa enorme, usare snapshot locale.

---

## 45. Strategia consigliata per massima precisione

1. core corpus;
2. scoped search title/abstract/keywords;
3. exact phrase;
4. filter strutturati;
5. resolve IDs;
6. rerank;
7. exclusion terms;
8. quality/source constraints;
9. local LLM classifier sui top 100–500.

---

## 46. Interazione con un LLM

Non affidare all'LLM la verità bibliografica.

Ruoli corretti:

### LLM

- query planning;
- synonym generation;
- classificazione relevance;
- query expansion;
- interpretazione abstract;
- spiegazione;
- extraction strutturata.

### OpenAlex

- entity IDs;
- metadata;
- citation graph;
- source/institution graph;
- DOI/identifier mapping;
- OA/location discovery;
- retrieval candidate.

### Regola

Ogni paper riportato all'utente deve derivare da un record effettivamente recuperato, non da memoria del modello.

Conservare il Work ID e DOI nella evidence chain.

---

## 47. Schema locale suggerito

```sql
papers (
    openalex_id PRIMARY KEY,
    doi,
    pmid,
    arxiv_id,
    title,
    publication_date,
    publication_year,
    work_type,
    cited_by_count,
    fwci,
    is_oa,
    oa_status,
    best_oa_url,
    source_openalex_id,
    raw_json,
    first_seen_at,
    last_seen_at
)

paper_retrievals (
    openalex_id,
    retrieval_run_id,
    query_id,
    retrieval_method,
    rank,
    relevance_score,
    rerank_score,
    semantic_score,
    retrieved_at
)
```

Non perdere il raw JSON: consente di riutilizzare nuovi campi senza requery immediata.

---

## 48. Versioning della strategia di ricerca

Ogni run dovrebbe salvare una versione:

```text
retrieval_strategy_version = "openalex-v1.3"
```

Quando cambiano:

- query planner;
- synonym model;
- scoring;
- corpus;
- filtri;
- dedup;
- stop condition;

incrementare la versione.

Questo rende comparabili gli esperimenti.

---

## 49. Test automatici raccomandati

### Unit test

- normalizzazione DOI;
- OR batching 100;
- URL encoding;
- abstract reconstruction;
- dedup;
- cursor checkpoint;
- error parser;
- retry.

### Integration test

- singleton Work;
- filter;
- search;
- semantic search;
- rerank;
- cursor 2 pagine;
- rate-limit endpoint.

### Regression dataset

Creare 20–100 query note con un piccolo gold set di paper attesi.

Misurare:

- Recall@100;
- Precision@20;
- MRR;
- unique relevant works;
- cost/query;
- latency/query.

---

## 50. Decision tree finale

```text
Conosco DOI/OpenAlex ID?
  sì -> singleton lookup
  no  -> continua

La richiesta è esprimibile con attributi strutturati?
  sì -> filter/list
  no  -> continua

La terminologia è abbastanza nota?
  sì -> keyword/title-abstract-keyword search
  no  -> semantic search + keyword expansion

Mi interessano soprattutto i primi risultati?
  sì -> rerank

Mi servono >10.000 record?
  sì -> cursor

Mi serve una porzione enorme o tutto OpenAlex?
  sì -> snapshot

Mi serve freshness giornaliera su enorme scala?
  sì -> valutare Member+ / Partner / sync
```

---

## 51. Raccomandazione specifica per un nuovo progetto

Per iniziare, non comprare alcun piano.

Configurazione iniziale consigliata:

- account OpenAlex gratuito;
- API key gratuita;
- client REST;
- `per_page=100`;
- `select` aggressivo;
- cache locale;
- multi-query retrieval;
- `search.title_abstract_keywords` come default lessicale;
- semantic search come secondo retriever;
- rerank solo quando serve precisione top-K;
- dedup per OpenAlex ID/DOI;
- singleton enrichment;
- logging costi;
- `core` come default, `all` solo per high recall;
- citation expansion controllata;
- snapshot soltanto quando la scala lo giustifica.

Con $1/giorno gratuito è possibile fare, ad esempio, fino a circa 1.000 search API pure oppure 10.000 filter/list calls, e nella pratica un workflow ben ottimizzato può usare un mix di queste operazioni restando molto spesso nella quota gratuita.

---

## 52. Checklist di implementazione

- [ ] Creare account OpenAlex
- [ ] Generare API key
- [ ] Salvare key in secret/env
- [ ] Implementare Authorization header
- [ ] Implementare singleton lookup
- [ ] Implementare filter/list
- [ ] Implementare keyword search
- [ ] Implementare semantic search
- [ ] Implementare rerank opzionale
- [ ] Implementare `select`
- [ ] Impostare `per_page=100`
- [ ] Implementare cursor pagination
- [ ] Implementare OR batch max 100
- [ ] Implementare entity resolution name → ID
- [ ] Implementare DOI normalization
- [ ] Implementare dedup
- [ ] Implementare exponential backoff + jitter
- [ ] Monitorare rate-limit headers
- [ ] Implementare budget/cost tracking
- [ ] Implementare cache
- [ ] Salvare query provenance
- [ ] Salvare raw JSON
- [ ] Distinguere `core`/`all`
- [ ] Implementare citation snowballing
- [ ] Aggiungere quality scoring separato da relevance
- [ ] Definire regression benchmark
- [ ] Valutare snapshot solo a scala elevata

---

## 53. Fonti ufficiali consultate

Documentazione ufficiale OpenAlex, verificata il 7 ottobre 2026:

- API reference:  
  https://help.openalex.org/api/

- Authentication:  
  https://help.openalex.org/api/authentication/

- Pricing overview:  
  https://help.openalex.org/access/pricing/

- Example costs:  
  https://help.openalex.org/access/example-costs/

- Buying & renewing:  
  https://help.openalex.org/access/buying-and-renewing/

- Legacy plans / old API limits:  
  https://help.openalex.org/access/legacy-plans/

- Products overview:  
  https://help.openalex.org/access/overview/

- Endpoint overview:  
  https://help.openalex.org/api/endpoints/

- Filtering:  
  https://help.openalex.org/api/filtering/

- Searching:  
  https://help.openalex.org/api/searching/

- Semantic search:  
  https://help.openalex.org/api/semantic-search/

- Sorting:  
  https://help.openalex.org/api/sorting/

- Grouping:  
  https://help.openalex.org/api/grouping/

- Paging:  
  https://help.openalex.org/api/paging/

- Selecting fields:  
  https://help.openalex.org/api/selecting-fields/

- LLM Quick Reference:  
  https://help.openalex.org/api/llm-quick-reference/

- OQL:  
  https://help.openalex.org/api/oql/

- OQL overview:  
  https://help.openalex.org/access/oql/

- API recipes:  
  https://help.openalex.org/how-to/api-recipes/

- Data reference:  
  https://help.openalex.org/data/

- How OpenAlex is built:  
  https://help.openalex.org/data/how-its-built/

- Works:  
  https://help.openalex.org/data/works/

- Work attributes:  
  https://help.openalex.org/data/works/attributes/

- Expansion corpus:  
  https://help.openalex.org/data/works/corpus/

- Citations:  
  https://help.openalex.org/data/works/citations/

- Open access:  
  https://help.openalex.org/data/works/open-access/

- Locations:  
  https://help.openalex.org/data/locations/

- Authors:  
  https://help.openalex.org/data/authors/

- Author disambiguation:  
  https://help.openalex.org/data/authors/disambiguation/

- ORCID:  
  https://help.openalex.org/data/authors/orcid/

- Sources:  
  https://help.openalex.org/data/sources/

- Repositories:  
  https://help.openalex.org/data/sources/repositories/

- Keywords:  
  https://help.openalex.org/data/keywords/

- Snapshot:  
  https://help.openalex.org/access/snapshot/

- Download snapshot tutorial:  
  https://help.openalex.org/tutorials/download-the-snapshot/

- 2026 API/pricing announcement, utile per capire la transizione dal vecchio modello:  
  https://blog.openalex.org/openalex-api-new-features-and-usage-based-pricing/

---

## 54. Nota sulla documentazione storica

OpenAlex ha cambiato significativamente il sistema API nel 2026.

Se un modello trova online esempi che consigliano:

```text
mailto=you@example.com
```

per entrare nel “polite pool”, oppure parlano di:

- 100.000 richieste al giorno;
- vecchio polite pool;
- vecchi piani Premium/Institutional come piani acquistabili correnti;

considerarli **legacy** e verificare sempre contro `help.openalex.org`.

La documentazione corrente prevale.

---

## 55. Istruzioni operative da dare al coding agent

> Implementa OpenAlex come provider di letteratura strutturato, non come un semplice motore di ricerca testuale. Usa una API key gratuita via Bearer token, conserva segreti fuori dal codice, usa `per_page=100`, `select` minimale e cache. Preferisci singleton lookup e filter quando esistono ID o attributi strutturati; usa keyword search e semantic search come retriever complementari. Non filtrare autori, istituzioni, source, topic, publisher o funder direttamente per nome: prima risolvi il relativo OpenAlex ID. Per query ad alto recall genera più varianti, uniscile e deduplica per OpenAlex Work ID e DOI. Usa rerank soltanto quando serve precisione sui primi risultati. Per oltre 10.000 risultati usa cursor pagination; per acquisizioni vicine all'intero corpus usa lo snapshot Parquet, non l'API. Traccia costi, rate-limit headers, provenance delle query e raw JSON. Mantieni separati relevance score e quality score. Non considerare citation count come unico indicatore di qualità. Prevedi citation snowballing e semantic retrieval come canali aggiuntivi. Tratta `core` come corpus predefinito e abilita `corpus=all` soltanto quando la copertura massima è più importante della qualità media dei metadati. Ogni paper presentato all'utente deve corrispondere a un record realmente recuperato, con OpenAlex ID e, quando disponibile, DOI/PMID/arXiv ID.

