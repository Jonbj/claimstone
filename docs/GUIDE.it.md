# Un giro, da un capo all'altro

Cosa fa ogni stadio, cosa scrive, e cosa significano i numeri. *In English: [GUIDE.md](GUIDE.md).*

Scritta sul giro che si è chiuso il 2026-09-28 — `pmc-screen-time`, 40 fonti — quindi ogni cifra qui è una
che questo repository ha prodotto davvero.

## Prima di tutto

Un progetto sono tre file di input sotto `projects/<nome>/`, e il motore non contiene conoscenza di dominio
su nessuno dei tre:

- **`topics.yaml`** — cosa cercare.
- **`questions.yaml`** — il registro congelato. Ogni domanda ha un id, un testo e un `kind` (`effect`,
  `heterogeneity`, `method`, `premise`, `operational`), e il `kind` decide quale regola la giudica. Aggiungere
  o cambiare una domanda è un **aumento di versione datato**: il registro porta un digest di id, testi e kind,
  e ogni comando che apre uno store si rifiuta di girare se il digest si è mosso sotto una versione
  invariata. Senza quello, ogni confronto fra due giri confronterebbe in silenzio due registri diversi.
- **`sources.yaml`** — le classi di fonte ammissibili, la soglia di acquisizione con la data e la ragione per
  cui è stata fissata, gli host da non attraversare mai, e il vocabolario che questo campo richiede (stadio 4).

```bash
.venv/bin/claimstone validate projects/<nome>
```

Controlla il contratto e nient'altro. Costa poco ed è la prima cosa da eseguire dopo ogni modifica.

## 1 · discover — candidati, da due canali indipendenti

```bash
.venv/bin/claimstone discover projects/<nome> --round <nome-round>
.venv/bin/claimstone discover-report projects/<nome>
```

Due canali: **parole chiave** (OpenAlex, Crossref, arXiv) e **citazioni** (le bibliografie estratte dallo
stadio 3). Tieni separati i loro risultati: le citazioni possono far emergere opere che la ricerca per parole
chiave ha mancato. Né la loro sovrapposizione né una percentuale di acquisizione stabilisce la completezza
della letteratura. D10 registra perché le ipotesi della cattura-ricattura qui non reggono; `discover-report`
deliberatamente non dà nessuna percentuale di completezza.

Ogni candidato registra la query che l'ha trovato e il canale da cui è passato. Una lista di lettura curata
entra invece con `import-manifest`, che è il modo in cui un corpus scelto a mano diventa un round.

**I round contano.** La soglia si giudica per round, perché una passata di scoperta cambia il denominatore per
costruzione: una passata citazionale ha portato un corpus da 14/25 = 0,56 a 14/75 = 0,19, e solo il primo
confronta cose confrontabili.

Se la scoperta richiede una popolazione di metadati ristretta, dichiara `population` in `sources.yaml` prima
del primo candidato di quel round. Servono una `version` positiva, un `declared_at` in formato ISO, una
`rationale` e almeno uno fra `hosts`, `source_apis` o `venues`. Le corrispondenze di host e sedi sono esatte:
niente caratteri jolly di dominio. I predicati sono alternative e non dipendono mai dal successo
dell'acquisizione. Il seme del manifest dichiarato resta incluso. Le osservazioni di scoperta, accettate ed
escluse, sono conservate in `discovery_population.jsonl`; solo quelle accettate entrano in `candidates.jsonl`.
La politica è congelata in `populations.jsonl`: cambiarla o rimuoverla richiede un nuovo round (D54).

## 2 · acquire — la migliore copia legale, e ogni tentativo registrato

```bash
.venv/bin/claimstone acquire projects/<nome> --round <nome-round> --campaign <perché>
.venv/bin/claimstone report projects/<nome>
```

Per ogni candidato il resolver costruisce una cascata di posti in cui una copia potrebbe stare legalmente — le
posizioni di Unpaywall, quelle di OpenAlex, un indirizzo PubMed Central dove esiste, e per ultimo l'URL del
candidato. Ognuna viene provata a turno, i byte sono salvati per contenuto, e **ogni tentativo viene scritto
sia che funzioni sia che no**: un fallimento inghiottito gonfia il tasso che decide se questo giro può
concludere qualcosa.

Le regole di condotta non sono opzionali: `robots.txt` si onora, un host che ha risposto 403 non si richiama
fuori da una **campagna nominata**, e nessuna richiesta passa mai per una biblioteca ombra.

`report` è la cifra che conta:

```
  ACA            37/40 confirmed  0.93   floor 0.80
  obtained       38/40  0.95
  confirmed      37/40  0.93  <- the figure
  floor          0.80 (v1, 2026-09-27)   OK   basis: confirmed
  failures       BOT_CHALLENGE 2
```

Si legge in questo ordine. **La cifra è `confirmed`, non `obtained`** — una risposta 200 che porta una pagina
di atterraggio non è un documento, e la differenza fra le due righe è quanto di ciò che è arrivato era vero.
La riga della soglia dice `OK` o `INSUFFICIENT_ACQUISITION`, e nel secondo caso nessuno stadio successivo
concluderà niente. `failures` è raggruppato per causa, e una causa che nomina un limite **nostro**
(`BOT_CHALLENGE`) è deliberatamente distinta da una che nomina quello della fonte (`ABSTRACT_ONLY`):
registrare un CAPTCHA come «di questo paper esiste solo l'abstract» sarebbe scrivere un guasto di
infrastruttura nel registro come se fosse un fatto sulla letteratura.

`gate-audit` fa variare le soglie che hanno prodotto il tasso, perché un tasso citato senza le sue soglie
invita a confrontare due numeri non confrontabili.

## 3 · normalize — una forma sola, poi i blocchi

```bash
./claimstone.sh normalize projects/<nome>          # serve il container: vedi sotto
```

I PDF passano da GROBID, l'HTML da un parser in questo repository. Entrambi producono la **stessa** forma di
documento, così nulla a valle sa né deve sapere chi ha letto cosa. Le tabelle vengono estratte invece di
essere appiattite: un `4.2` nudo lasciato accanto a prosa non correlata è un numero che un modello
attribuirà a qualunque frase lo precede.

Poi la regola di conferma: un documento è vero se ha abbastanza riferimenti, oppure è abbastanza lungo per
stare in piedi senza una bibliografia. Ciò che non passa è `NOT_A_DOCUMENT` e lascia onesto il conteggio del
corpus.

**Questo è l'unico stadio che richiede il container**, perché GROBID sta su una rete interna senza porta
pubblicata. `./claimstone.sh` costruisce prima l'immagine e poi esegue la stessa CLI dentro: l'immagine porta
il codice, e `compose.yaml` monta solo `store/` e `projects/`.

## 4 · extract — un modello propone, un controllo verifica

```bash
.venv/bin/claimstone extract projects/<nome> --batch <nome>               # costruisci le unità
.venv/bin/claimstone model-run projects/<nome> extract --batch <nome> \
    --backend ollama-cloud --model <modello> --no-think --enforce-schema   # drenale
.venv/bin/claimstone extract projects/<nome> --batch <nome> --harvest      # passa le risposte al gate
.venv/bin/claimstone extract-report projects/<nome> --show-rejected
```

Tre comandi separati per scelta. Le unità di lavoro sono JSONL, le risposte sono JSONL, e il modello non sta
mai dentro uno stadio — così un batch è ripartibile per `call_id`, un backend è sostituibile, e le stesse
unità possono andare a due backend e essere confrontate.

Cosa si chiede al modello dipende dal `kind` della domanda: una `effect` vuole un risultato di studio con il
suo estimando, `heterogeneity` vuole il contrasto fra sottogruppi e la sua incertezza, `method` vuole se la
fonte avalla una pratica o ne dimostra il fallimento. Il modello riporta le cifre **solo come il paper le ha
scritte** — `2.4%`, `(0.008)`, `AOR=1.66` — e il motore converte. Così un valore non può essere sbagliato in
un modo che la sua citazione non riveli.

Poi il gate, che è l'invariante 1 reso eseguibile. Controlla che la citazione sia sottostringa esatta del
blocco, che ogni numerale asserito dall'affermazione compaia nella citazione, che un comparativo
nell'affermazione ci sia anche nella citazione, e che l'affermazione non stia riportando cosa ha trovato un
**altro** paper. Ciò che non passa va in `rejections.jsonl` con il record intero, così un rifiuto è
esaminabile e non solo contato.

**La notazione di una disciplina è dato di progetto.** `AOR`, `ß`, `Sharpe`, `95% CI` si dichiarano in
`extraction.value_labels` di quel progetto. Stavano nel motore, e un corpus di un altro campo ha dimostrato
che era sbagliato: la lista usciva con `sharpe` e senza `OR`, quindi il corpus finanziario leggeva e quello
epidemiologico rifiutava 63 stime.

## 5 · review — un modello diverso, che legge il passo intero

```bash
.venv/bin/claimstone review projects/<nome> --batch <b> --question <Q> \
    --reviewer claude-cli/claude-opus-5
.venv/bin/claimstone model-run projects/<nome> review --batch <b> --backend claude-cli --model …
.venv/bin/claimstone review projects/<nome> --batch <b> --harvest
```

Il revisore riceve la domanda, l'annotazione originale completa e quella convertita, **e il blocco intero** — e
deve essere un modello diverso da quello che ha estratto, cosa che è imposta e non chiesta. Un lettore che condivide i punti ciechi
dell'estrattore è un secondo parere dallo stesso parere.

Quattro verdetti: `SUPPORTED`, `OVERSTATED` (la citazione è vera e dice meno dell'affermazione), `AMBIGUOUS`,
e `NOT_APPLICABLE` (la citazione non parla della domanda citata). Solo le `SUPPORTED` arrivano a un profilo;
le altre sono contate e mostrate, mai cancellate — una riga `OVERSTATED` è la più informativa del registro,
perché è un caso che un controllo meccanico ha passato e un lettore no.

`--question` esiste perché un verdetto è per domanda, e un profilo aggiudicabile costa 43 chiamate di
revisione invece delle 7.000 di tutto il registro.

**Cosa misura questo stadio, e che ci ha sorpreso.** Su due domande di due tipi diversi, il revisore ha
marcato 23 su 41 e 36 su 42 affermazioni passate dal gate come `NOT_APPLICABLE` — non parlano della domanda
che citano, pur avendo passato tutte il controllo di tipo. Ogni blocco viene interrogato su ogni domanda del
suo tipo e il modello risponde invece di astenersi. Quindi **la copertura misurata dopo l'estrazione è
un'affermazione sull'estrattore**, e la copertura onesta è quella post-revisione.

## 6 · synthesize — un profilo, e mai un verdetto

```bash
.venv/bin/claimstone synthesize projects/<nome>
.venv/bin/claimstone verdicts projects/<nome> --question <Q>
```

Python deterministico. Nessun modello, nessuna rete, **nessuna statistica** — le regole del contratto dei
verdetti sono regole di conteggio e copertura, quindi una stima aggregata sarebbe informazione in più e la
base di nessun verdetto che quelle regole definiscono.

Rifiuta due volte. Un giro sotto la sua soglia non ottiene **nessun profilo**, non un avviso e non una
esecuzione parziale. E un profilo costruito mentre qualcosa sta ancora arrivando è marcato `provisional` e non
si può firmare, perché un giudizio registrato contro evidenza che stava cambiando è un giudizio su
qualcos'altro.

Un profilo contiene ogni risultato verificato con il suo estimando, **gli stessi campi per i risultati che
dissentono**, il conteggio di direzione *etichettato come conteggio*, la copertura, cosa ha rifiutato il gate
e per quale ragione, cosa il revisore non ha passato, e le etichette di campione alla lettera con il legame
dichiarato **non stabilito** — nessun confronto fra stringhe stabilisce che due paper hanno usato dataset
diversi.

Il suo unico esito categorico è `NO_VERIFIED_CLAIM`, che dice che nulla è sopravvissuto. **Non** è
`NEVER_ASKED`: una mancata estrazione, una domanda tutta rifiutata e una domanda davvero mai posta da qui si
somigliano, e solo uno screening le distingue.

D45 ha reso esplicita la completezza: un fallimento terminale del modello non è una lettura con zero claim, quindi il
profilo riporta `extraction.expected`, `unanswered`, `unharvested` e `unchunked_sources`. Quando D45 è stato scritto, 34 letture
del giro salvato non avevano una risposta valida, 10 delle quali di tipo effect che mantenevano Q04 provvisorio. D52 ha poi
completato tutte le 734 letture effect di Q04, e `verdicts` ora mostra 0 senza risposta per Q04.

Usare gli stessi `--round` e `--manifest-only` per `synthesize`, `verdicts` e `adjudicate`: il perimetro è
nell’hash e profili e firme restano distinti. `verdicts` ricalcola in memoria senza aggiungere righe; se il
profilo salvato differisce, eseguire `synthesize` e leggere il nuovo hash prima di firmare.

D46 aggiunge `extraction.unregated` e `awaiting_regate`: le annotazioni giudicate da un vecchio gate
non si possono firmare sotto quello attuale prima della ri-raccolta. Le revisioni del gate possono
superare sia un’accettazione sia un rifiuto, conservando entrambi i ledger. I ledger reali sono intatti;
D47 corregge il replay di risposte e annotazioni (R05/R09). La misura completa è riproducibile con
`tools/measure_answer_replay.py <progetto>`. D48 corregge anche le generazioni dei chunk e la revisione completa. D49 applica il replay ai ledger reali, conservando tutti i byte originali;
le vecchie revisioni attestano il compito v1 e non possono certificare le annotazioni complete v2.
Seguono completamento delle letture e nuove revisioni indipendenti,
prima di ricostruire e leggere un profilo v5 firmabile.

## adjudicate — l'unico posto da cui nasce un verdetto

```bash
.venv/bin/claimstone adjudicate projects/<nome> <Q> \
    --verdict SUPPORTED|CONTRADICTED|CONTESTED_IN_LITERATURE|UNANSWERED_IN_LITERATURE|NEVER_ASKED \
    --rationale-file r.md --by "<chi>" --profile-sha256 <hash>
```

Una persona legge il profilo e firma. La firma registra l'hash di ciò che le è stato mostrato, così se
l'evidenza cambia il verdetto viene mostrato come **stale** con entrambi gli hash invece di restare in
silenzio: un giudizio dato contro evidenza diversa è un giudizio su una domanda diversa.

Rifiuta un profilo provvisorio, rifiuta una motivazione sotto i 120 caratteri, e rifiuta una domanda di tipo
`operational`, che riceve una riga che dice che nessun verdetto si applica invece di un sesto stato.

**Cinque stati, e nessuno collassa in un altro.** `UNANSWERED_IN_LITERATURE` significa che il corpus è stato
letto e non lo risolve. `CONTESTED_IN_LITERATURE` significa che la letteratura parla e dissente. Riportare il
secondo come il primo è l'errore fondante del progetto, una categoria più in là.

## Ri-giudicare senza rete

Quattro percorsi non costano nulla e rileggono ciò che è già su disco. Usali invece di riscaricare:

| | rilegge |
|---|---|
| `regate --campaign <perché>` | i byte salvati sotto il gate di contenuto attuale |
| `normalize --force` | i blocchi, da ciò che è già parsato |
| `extract --harvest` | le risposte salvate sotto il gate delle affermazioni attuale |
| `model-run --rejudge` | le risposte salvate sotto le regole attuali, senza chiamate |

I registri sono in sola aggiunta, quindi una riesecuzione aggiunge e `latest_by` prende l'ultima. Niente si
perde e niente viene riscritto.

## L'unica regola sui numeri

**Cita quello che un ri-giudizio restituisce, mai quello che un campione suggerisce.** In un giorno, quattro
recuperi previsti contando la firma di un difetto su un campione piccolo sono stati 45→1, 166→18, 6→1, e una
ipotesi falsificata del tutto. Esegui la ri-raccolta e cita il suo output.


`tools/replay_answers.py <progetto>` misura il lavoro residuo senza modificare i ledger; con `--apply`
applica il replay delle risposte salvate. I selettori delimitano la misura, mentre il replay tratta tutti
i batch salvati. Vedi [la misura in produzione](replays/2026-09-28-production-replay.md).

## Testare un prompt prima di adottarlo

Per un piano di confronto già preparato, l'anteprima non fa chiamate di rete e non scrive nulla:

```bash
.venv/bin/python tools/run_prompt_comparison.py --plan <piano-di-confronto.json>
```

Con un'autorizzazione esplicita alla spesa di calibrazione, aggiungi `--execute` per eseguire o riprendere. Il
confronto usa uno store sperimentale separato e il budget cumulativo originale, comprese le chiamate fallite
precedenti dal costo ignoto. Lascia invariati i prompt di produzione e i registri scientifici. Confronta i casi
di riferimento diagnostici, rilegge il campione originale con un prompt di estrazione sperimentale e fa
rivedere in modo indipendente ogni annotazione appena accettata. Le chiamate riuscite vengono conservate alla
ripresa. `BACKEND_ERROR` si ferma dopo la chiamata tentata e conserva la sua riserva contabile.

Le etichette diagnostiche a coppie descrivono un riferimento provvisorio di sviluppo, scritto da un agente e
scelto dopo aver ispezionato gli errori. Non sono un'accuratezza generale, e i controlli positivi vanno
esaminati insieme ai casi problematici. Leggi le nuove annotazioni e i passi che le sostengono prima di
decidere se adottare un prompt. Nessuna variante viene adottata in automatico, e questo strumento non produce
profili né verdetti firmati.

Per un piano diagnostico preparato solo per il revisore:

```bash
.venv/bin/python tools/run_review_diagnostics.py --plan <piano-diagnostico.json>
```

Aggiungi `--execute` solo entro l'autorizzazione di spesa esistente. Questo compito tiene fisse annotazioni e
passi e chiede etichette separate di applicabilità, fedeltà e direzione, con le ragioni. La coda è isolata e il
budget cumulativo comprende entrambi gli esperimenti precedenti. Non esegue estrazioni e non scrive revisioni
di produzione. L'etichetta riassuntiva del report è sperimentale; la sua mappa dell'incertezza non cambia gli
stati di revisione in produzione. Gli assi di riferimento attesi e non valutati restano fuori dai denominatori
di accordo. Valuta le ragioni e i controlli positivi prima di adottare un nuovo compito di revisione
scientifica: un JSON valido da solo non lo convalida.

Una forma di output non valida resta `SCHEMA_INVALID` anche se il testo sembra utile. Una riparazione del
formato usa un prompt con versione esplicita e nuovi id di richiesta, invece di riscrivere la risposta fallita.
Il suo piano preparato congela la coda diagnostica precedente e porta ogni tentativo fallito nello stesso budget
cumulativo. Usa il piano riparato fornito dal flusso dell'operatore: una risposta originale non valida in modo
terminale non diventa completa rieseguendo il piano originale.

Per confrontare un revisore indipendente su un compito diagnostico completato, usa il suo piano preparato:

```bash
.venv/bin/python tools/compare_reviewers.py --plan <piano-confronto-revisori.json>
```

Con `--execute` esegue solo il secondo revisore, in un altro store isolato. Le richieste sono identiche byte per
byte alla base già completata: prompt, annotazioni, passi, schema, limiti di output e bersagli di annotazione
fusi. Le risposte della base e il riferimento di sviluppo non vengono mai inviati al nuovo lettore. I tentativi
precedenti con prezzo e le riserve di costo ignoto mantengono le tariffe e i limiti di contesto dei loro
lettori originali. Ogni chiamata successiva deve stare dentro il budget cumulativo originale prima del
contatto. Il report mette a confronto i controlli e le ragioni dei due lettori con il riferimento provvisorio,
separando i controlli positivi dai casi di sfida. L'accordo fra lettori e l'accordo con il riferimento sono
misure diverse, e nessuna delle due certifica l'accuratezza scientifica. Questo confronto non può adottare un
compito né scrivere revisioni di produzione.

## Un primo uso supervisionato

Un piano di passi curati può produrre un dossier di lettura consultivo senza chiamate a modelli:

```bash
.venv/bin/python tools/build_consultative_dossier.py --plan <piano-passi-curati.json>
```

L'anteprima è in sola lettura. `--write` crea JSON e Markdown indirizzati per contenuto sotto
`audits/consultative/` dello store di origine, conservando tutti i file originali. Il piano fissa gli hash del
registro, del testo corrente dei passi e dei documenti normalizzati. Ogni record curato deve passare il gate
delle affermazioni esistente; la classe di fonte resta attaccata. La soglia di acquisizione blocca comunque la
pubblicazione, e l'ammissione incompleta viene segnalata anche sopra la soglia. Questi documenti sono note di
lettura selezionate, non profili scientifici: non raccolgono affermazioni né revisioni, non firmano verdetti e
non certificano l'accuratezza semantica. La curatela interattiva va dichiarata esplicitamente e non va
riportata come misura di estrazione di un backend batch. La selezione e la copertura mancante devono
accompagnare l'interpretazione. I casi già ispezionati per questo dossier sono materiale di sviluppo, non una
convalida su dati mai visti di un prompt messo a punto.

## Copertura della ricerca e aggiornamenti

Un tasso di acquisizione misura i documenti confermati sui candidati trovati, non la quota di letteratura
scoperta. Nemmeno completare un protocollo di ricerca finito stabilisce un richiamo universale. Registra la
domanda, la popolazione ammissibile, i termini di ricerca, le API, i limiti sui risultati e le date di ricerca
prima di cercare. `tools/audit_research_search.py --plan <piano-di-ricerca.json>` confronta quella matrice di
query congelata con le query registrate, senza rete. Query mancanti, query fallite e profondità di ricerca
insufficiente restano distinte. Una query che raggiunge il suo limite di risultati richiede un'ispezione o un
approfondimento; l'esecuzione riuscita da sola non significa che i suoi risultati siano esauriti.

`--write` salva una linea di base indirizzata per contenuto sotto `audits/research-search/`. Elenca candidati,
hash e generazioni dei documenti, riferimenti bibliografici ancora da vagliare per rilevanza, completamento
attuale delle letture ed etichette di revisione per domanda. Nessuno screening semantico viene dedotto da
titoli, conteggi delle fonti, acquisizione o presenza di affermazioni. Richiamo sulla letteratura e precisione
dello screening restano ignoti finché non sono giustificati separatamente; nessun registro scientifico né
verdetto viene scritto.

Per valutare l'efficacia, registra le decisioni di rilevanza e le ragioni per ogni opera vagliata, individua gli
articoli noti ammissibili che la ricerca dovrebbe ritrovare, e ispeziona sia i risultati opposti o nulli sia
quelli positivi. Ritrovare questi articoli noti è un controllo di riferimento, non un richiamo sull'intera
letteratura. Tieni traccia delle nuove opere rilevanti per ogni ondata di ricerca completata e di cosa
aggiungono le citazioni rispetto alle parole chiave. Una resa bassa giustifica la fine di un protocollo
dichiarato solo dopo aver contabilizzato fallimenti di ricerca, risultati troncati e riferimenti non vagliati.
Non prova la saturazione di tutta la letteratura. La soglia di citazioni predefinita perde i riferimenti citati
una sola volta; una revisione bibliografica mirata deve ispezionare anche quelli. Lo screening di rilevanza
non toglie mai retroattivamente candidati ammessi dal denominatore dell'acquisizione.

Per gli aggiornamenti, usa un nuovo round di scoperta datato e conserva un audit del corpus cumulativo
precedente. `--previous <audit-linea-di-base.json>` riporta le nuove chiavi di candidato e le generazioni di
documento cambiate; le chiavi di candidato non sono studi deduplicati in modo indipendente, quindi i possibili
duplicati vanno ispezionati. Una combinazione invariata di byte, prompt e schema può riusare il lavoro
esistente. Un articolo rivisto o una nuova generazione del parser richiedono letture aggiornate; annotazioni
cambiate richiedono nuove revisioni indipendenti. Evidenza storica e firme restano registrate, e un'evidenza
viva cambiata rende stale una vecchia firma. Conserva sia il report di acquisizione del round di
aggiornamento sia quello cumulativo: i candidati appartengono al round che li ha trovati per primi, quindi il
round di aggiornamento da solo non è l'intero corpus aggiornato. I cambiamenti di popolazione richiedono una
nuova politica datata e un nuovo round; i cambiamenti di domanda richiedono un aumento di versione del
registro. I comandi esistenti non offrono un monitoraggio automatico delle pubblicazioni. All'inizio esegui un
aggiornamento settimanale esplicito; i ritardi di indicizzazione fanno sì che «scoperto di recente» non
significhi necessariamente «pubblicato di recente».

Per il recupero da OpenAlex, una `OPENALEX_API_KEY` gratuita e facoltativa in `.env` viene passata al container
e inviata come header Authorization solo alla sua origine HTTPS esatta. Non metterla mai in un URL di query né
in un input sotto controllo di versione. Una chiave aumenta il budget anonimo del fornitore ma non elimina i
limiti giornalieri. `tools/resume_research_search.py --plan <piano-di-ricerca.json> --limit <N>` mostra in
anteprima solo le query mancanti, fallite o con profondità insufficiente di un protocollo congelato. Con
`--execute` sull'host legge contatto e chiavi in modo sicuro da `.env`, condivide un solo fetcher fra le query
scelte e si ferma al primo fallimento. Le query completate, comprese quelle troncate, vengono saltate: una
ricerca più profonda richiede un protocollo di approfondimento esplicito. Il limite predefinito è una query;
non lancia chiamate a modelli.

## Lo scheduler: operazioni limitate (non ancora completo)

Questa parte del motore è ancora in completamento, per questo viene per ultima. Quanto segue è ciò che esiste
oggi. Non apre un nuovo round di ricerca, non approva richieste future sconosciute e non firma verdetti. I
limiti attuali sono nel [contratto dello scheduler](contracts/scheduler_operations.md).

Per un flusso di ricerca vincolato, `claimstone scheduler-preview PROGETTO FLOW_ID` stampa una proposta del
lavoro successivo, offline e in sola lettura. Non autorizza né avvia uno stadio. Nomina i blocchi di protocollo
e di integrità e tiene distinto un nuovo round vuoto da una coorte di candidati chiusa (D86).

Un flusso esistente può anche eseguire uno stadio offline limitato tramite il registro delle operazioni. Per
esempio, dopo che esistono candidati e copie acquisite:

```bash
.venv/bin/claimstone scheduler plan projects/<nome> <flow-id> normalize
.venv/bin/claimstone scheduler authorize projects/<nome> <operation-id>
.venv/bin/claimstone scheduler run projects/<nome> <operation-id>
.venv/bin/claimstone scheduler status projects/<nome> <operation-id>
```

Per costruire code mirate usa `extract-build --batch <nome>` o `review-build --batch <nome>
--reviewer <backend>/<modello>`. Una coda di modello locale si può drenare con `extract-drain` o `review-drain`
più `--batch`, `--model` e `--max-calls`; poi pianifica il corrispondente `extract-harvest` o
`review-harvest`. `synthesize` costruisce un profilo. L'operatore autorizza ogni piano esatto dall'account di
sistema locale. Queste operazioni non consentono richieste internet esterne, tranne un `acquire` pianificato
esplicitamente su un singolo candidato con `--candidate-key`, `--allow-host` ripetibile e `--max-requests`.
Un piano `discover` nomina invece `--api`, `--topic`, `--term`, `--per-query`, `--allow-host` e
`--max-requests`; esegue una query congelata per ogni autorizzazione.
Per un drenaggio a pagamento aggiungi `--backend ollama-cloud`, `--budget-id`, `--budget-cents`,
`--max-call-cents`, `--price-in-cents` e `--price-out-cents`. I prezzi sono stime massime dichiarate in
centesimi di dollaro per milione di token, e le riserve sono cumulative fra i piani con lo stesso budget ID.
Rivedi il piano esatto e autorizzalo prima che un worker possa chiamare il fornitore. I crediti in un account
non danno da soli alcuna autorizzazione. Una fattura del fornitore può superare una stima locale; usa i
controlli di spesa dell'account del fornitore come tetto massimo esterno. Le chiamate interrotte con costo
incerto si fermano per ispezione invece di essere reinviate.
Dopo un'operazione offline fallita, usa un nuovo `--run-label` una volta risolta la causa. Una richiesta
fisica incerta blocca il nuovo tentativo automatico anche con una nuova etichetta.
Per una query fallita prima di qualsiasi richiesta fisica, un nuovo piano di scoperta può indicare
`--run-label` e `--retry-reason`. Si lega alla riga di fallimento precedente e richiede comunque
un'autorizzazione separata dell'operatore prima dell'esecuzione.

Per più piani di query o di candidati, `scheduler batch-plan` accetta API e host espliciti, `--max-units` e
`--max-requests-each`, e stampa un solo batch ID con il tetto totale e gli elementi saltati. Rivedi quel JSON,
poi esegui `scheduler authorize-batch PROGETTO BATCH_ID`. `scheduler tick PROGETTO` esegue una volta un numero
limitato di operazioni approvate; `scheduler worker PROGETTO` controlla periodicamente se ce ne sono altre.
Il worker non approva nuovo lavoro.
Per un singolo passaggio locale senza supervisione dopo la raccolta, esegui `scheduler drive PROGETTO FLOW_ID
--extract-model MODELLO_A --review-model MODELLO_B --max-local-calls N`. Si ferma alla soglia di rete, di
acquisizione o di lettura umana; non può firmare un verdetto. Eseguilo dentro `./claimstone.sh` se la
normalizzazione dei PDF richiede il servizio GROBID interno.
La stessa invocazione esegue prima le unità di rete di quel flusso che erano già autorizzate al suo avvio; non
estende mai i loro elenchi di host né i loro tetti.

Per preparare offline una serie finita di round di aggiornamento datati, scrivi un array JSON come
`[ {"round":"update-2026-11", "title":"Aggiornamento di novembre",
"not_before":"2026-11-01T00:00:00Z", "expires_at":"2026-11-02T00:00:00Z"} ]`.
Poi usa `scheduler periodic-plan PROGETTO SOURCE_FLOW_ID --rounds-file FILE
--api crossref --allow-host api.crossref.org --max-units-each N --max-requests-each N`. Il tetto di unità per
round deve contenere *tutti* i termini di argomento per le API scelte. Questo crea nuovi legami di flusso e
batch di scoperta esatti, ma non fa nessuna richiesta. Ispeziona l'ID del calendario restituito e i suoi
batch, poi autorizza quel calendario finito con `scheduler schedule-authorize PROGETTO ID`.
`scheduler periodic-audit PROGETTO ID` riporta per ogni round gli esiti delle query e la soglia di
acquisizione, l'ammissione del flusso antenato e quella dell'intero corpus. Non emette mai un verdetto. Un
nuovo candidato richiede comunque un piano di acquisizione autorizzato separatamente; pianificare la scoperta
non pre-approva copie future sconosciute.
