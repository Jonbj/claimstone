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
stadio 3). Sono tenuti separati perché la completezza si stima confrontando due canali *indipendenti*:
contare quanto ha trovato un canale non dice niente su cosa manca.

Ogni candidato registra la query che l'ha trovato e il canale da cui è passato. Una lista di lettura curata
entra invece con `import-manifest`, che è il modo in cui un corpus scelto a mano diventa un round.

**I round contano.** La soglia si giudica per round, perché una passata di scoperta cambia il denominatore per
costruzione: una passata citazionale ha portato un corpus da 14/25 = 0,56 a 14/75 = 0,19, e solo il primo
confronta cose confrontabili.

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

Il revisore riceve la domanda, l'affermazione, la citazione **e il blocco intero** — e deve essere un modello
diverso da quello che ha estratto, cosa che è imposta e non chiesta. Un lettore che condivide i punti ciechi
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

D45 ha corretto la completezza del giro salvato: 34 letture di estrazione non hanno una risposta valida,
comprese le 10 letture di tipo effect che mantengono Q04 provvisorio. Un fallimento terminale del modello
non è una lettura con zero claim. Il profilo riporta `extraction.expected`, `unanswered`, `unharvested`
e `unchunked_sources`.

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
