# Claimstone

[English](README.md) · **Italiano**

**Una macchina che legge la letteratura e si rifiuta di dire più di quello che ha letto.**

Le dai un insieme di temi e una lista congelata di domande. Trova la letteratura, ottiene legalmente quello
che può, legge ogni fonte e restituisce — per ogni domanda — l'evidenza che ha trovato, legata a citazioni
letterali, con la copertura su cui quell'evidenza si appoggia.

È costruita attorno a un errore che non commetterà: **riportare «non abbiamo trovato evidenza» come «non
c'è effetto».** Tutto ciò che è inusuale nel disegno viene da lì.

## Perché funziona così

**Un'affermazione senza una citazione verificata viene scartata, non ammorbidita.** Ogni affermazione porta
una citazione che viene controllata *dal codice* come sottostringa esatta del testo di partenza, e ogni
numero e ogni disuguaglianza nell'affermazione devono comparire anche nella citazione. Ciò che fallisce
finisce in un registro dei rifiuti, che è il denominatore: non puoi leggere il tasso di accettazione senza
vedere cosa ha rifiutato.

**Un corpus che non ha ottenuto quello che ha trovato non produce niente.** Se un giro ha ottenuto meno
della soglia che si era dichiarata, riporta `INSUFFICIENT_ACQUISITION` e non scrive nessuna conclusione. Non
esiste un'opzione per aggirarlo. Un corpus letto al 42% che si certifica completo è peggio di nessun corpus,
ed è la situazione reale per cui questo progetto è nato.

**Nessun verdetto è automatico.** Il motore produce un *profilo di evidenza* — i risultati, il conteggio di
direzione **etichettato come conteggio**, la copertura, i rifiuti, e ciò che un secondo lettore non ha
passato. Una persona lo legge e firma, contro l'hash di quello che le è stato mostrato. Se l'evidenza cambia
dopo, la firma viene marcata *stale* invece di restare in silenzio.

**Ogni cifra è citata con lo strumento che l'ha prodotta.** Parser, controlli e soglie portano un numero di
versione, uno strumento rifiuta di passare quando una versione cambia senza essere registrata, e il registro
delle decisioni contiene la **misura** che ha deciso ogni scelta, non il ragionamento che suonava bene.

## I sei stadi

| | cosa fa | scrive |
|---|---|---|
| **1 discover** | due canali indipendenti — ricerca per parole chiave e citazioni — trovano candidati | `candidates.jsonl` |
| **2 acquire** | ottiene la migliore copia legale, registrando ogni tentativo e perché è fallito | `acquisitions.jsonl`, `raw/` |
| **3 normalize** | PDF e HTML in una forma sola, poi in blocchi | `documents.jsonl`, `chunks.jsonl` |
| **4 extract** | un modello propone affermazioni; un controllo verifica ognuna contro la sua citazione | `claims.jsonl`, `rejections.jsonl` |
| **5 review** | un modello **diverso** rilegge ogni affermazione contro il passo intero | `reviews.jsonl` |
| **6 synthesize** | un profilo di evidenza per domanda. Nessun modello, nessuna rete, nessuna statistica | `profiles.jsonl` |
| *adjudicate* | *una persona registra il verdetto e lo firma* | `adjudications.jsonl` |

Gli stadi si parlano attraverso file JSONL in sola aggiunta. Nessuno tiene stato in memoria fra uno e
l'altro, un crash è ripartibile, e ogni cifra si trova con `grep`.

## Come si esegue

```bash
.venv/bin/pytest -q                                    # il conteggio è stampato, non registrato qui
.venv/bin/claimstone validate --all-projects           # il controllo del contratto
.venv/bin/claimstone report projects/<nome>            # il tasso di acquisizione e le sue perdite
.venv/bin/claimstone verdicts projects/<nome>          # i profili, e qualunque firma
```

`normalize` ha bisogno del parser dei documenti, che gira in un container: per quello si usa
`./claimstone.sh normalize projects/<nome>`. Le API scientifiche richiedono un indirizzo di contatto e il
codice si rifiuta di inventarne uno, quindi `.env` deve contenere `CLAIMSTONE_CONTACT_EMAIL`.

## Dove approfondire

- **[docs/README.it.md](docs/README.it.md)** — la mappa della documentazione: quale file risponde a quale
  domanda.
- **[docs/GUIDE.it.md](docs/GUIDE.it.md)** — un percorso attraverso un giro intero, stadio per stadio, con
  cosa significa ogni numero. Da qui, se vuoi eseguirne uno.
- **[docs/DESIGN_DECISIONS.md](docs/DESIGN_DECISIONS.md)** *(in inglese)* — 132 decisioni numerate al
  2026-10-16 (`grep -c '^## D' docs/DESIGN_DECISIONS.md` per il conteggio corrente), ognuna con la
  misura che l'ha decisa. Leggi la voce prima di discutere la scelta.
- **[docs/HANDOFF.md](docs/HANDOFF.md)** *(in inglese)* — cosa sta girando, cosa è in sospeso, e quali
  decisioni appartengono a una persona e non al motore.
- **[CLAUDE.md](CLAUDE.md)** / **[AGENTS.md](AGENTS.md)** *(in inglese)* — le regole che un agente che
  lavora qui deve seguire.

**Perché alcuni documenti sono solo in inglese:** quelli che cambiano a ogni commit — il registro delle
decisioni, i contratti dei dati, i commenti nel codice — restano in una sola lingua per scelta. Due copie
della stessa regola divergono, e la copia che diverge è quella che inganna. Questo repository vincola
`cli.BACKENDS` a `runners.available()` con un test proprio per quella ragione. Bilingue è ciò che si legge
raramente e cambia raramente; inglese è ciò su cui si lavora.

## Stato

Lo scheduler ha operazioni limitate per stadi con perimetro, chiamate a modelli, una query
accademica e un'acquisizione di candidato alla volta. Un mandato locale può far avanzare il
lavoro autorizzato attraverso gli stadi di ricerca e proporre batch di rete. Un operatore può
approvare batch esatti tramite il servizio di controllo autenticato, oppure approvare un
calendario finito e revocabile di batch già congelati. Un calendario finito può preparare round
di ricerca datati; una policy di copia approvata separatamente consente al worker di acquisire
futuri candidati corrispondenti su host esatti, entro tetti vitalizi. Un solo mandato di serie
può coprire i flussi figli datati esatti, con un tetto vitalizio condiviso sulle chiamate locali
a modelli. Il servizio di controllo autenticato può pianificare e approvare questi tre permessi
separatamente. I limiti attuali sono nel
[contratto dello scheduler](docs/contracts/scheduler_operations.md) *(inglese)*.
Per un calendario periodico, `scheduler periodic-dossier` mostra la consegna live di evidenza
cumulativa. `periodic-finalize` persiste i profili sull'intero corpus e un dossier in sola
aggiunta solo quando ogni gate — calendario, acquisizione e lettura — passa; il worker locale di
un flusso figlio datato lo tenta automaticamente. Nessun verdetto scientifico viene generato.
Vedi [il contratto del dossier](docs/contracts/periodic_dossiers.md) *(inglese)*.

Per un singolo flusso, `scheduler auto-enable PROGETTO FLOW_ID --extract-model MODELLO_A
--review-model MODELLO_B --max-total-local-calls N` registra un mandato di lavoro locale
limitato. `scheduler auto-worker PROGETTO MANDATE_ID` visita di nuovo quel flusso quando arrivano
nuovi dati; `auto-status`, `auto-once` e `auto-disable` ispezionano, eseguono un passaggio e
fermano. Il tetto totale di chiamate locali sopravvive ai riavvii del worker. Le operazioni di
rete restano soggette a un'autorizzazione esatta e separata.
`./portal.sh up` avvia un unico supervisore dell'installazione che scopre tutti i mandati
abilitati; non serve più un container `auto-worker` separato per ogni nuovo flusso.
`scheduler supervisor-status` ne riporta l'heartbeat. Le impostazioni opzionali `--discover-api`,
`--discover-host` e `--acquire-host` lasciano che quel worker prepari i prossimi batch limitati;
`auto-status` mostra quelli ancora in attesa di approvazione. Preparare un batch non fa nessuna
richiesta di rete. La control API autenticata può elencare e autorizzare un batch congelato in
una sola azione; da D132 il portale può anche creare il primo flusso di un progetto e pianificarne
il primo batch di rete congelato — suggerendo gli host di acquisizione dalle posizioni di copia
registrate — e il supervisore dell'installazione esegue solo ciò che una persona ha autorizzato.
L'indice scheduler del progetto ora impagina i propri archivi e riporta l'heartbeat del processo
worker separatamente dall'avanzamento dei ledger. Un dossier cumulativo finalizzato e corrente si
può scaricare come ZIP verificabile contenente JSON, CSV, Markdown e un manifest; nessuna copia
delle fonti è inclusa.

Tutti e sei gli stadi sono implementati e un giro ha percorso l'intera pipeline sulla letteratura
depositata in PubMed Central: 37 fonti su 40 confermate contro una soglia di 0,80, 1.721 annotazioni
accettate e 271 rifiutate.

**Nessun verdetto esiste. Q04 è formalmente completo e pronto per la lettura umana; gli altri sette
profili restano provvisori.** D52 completa le 734 letture del tipo effect e le 42 revisioni indipendenti
delle annotazioni complete di Q04. Restano quattro risultati da quattro delle 37 fonti esaminate.
La lettura umana deve verificarne rilevanza scientifica e posizioni assegnate: la completezza formale
non le certifica. Nel resto del corpus mancano 24 letture e 1.679 revisioni indipendenti.

D48 chiude le quindici correzioni del software; D49 applica il replay offline; D50/D51 preparano
il giro cloud con budget limitato e preservano i risultati parziali. D52 registra il giro Q04 completato
e la scheda di lettura. `docs/HANDOFF.md` contiene hash, scope, budget e decisione umana ancora pendente.

Gli altri due corpus rimangono sotto la propria soglia e correttamente non producono conclusioni. Leggi
`docs/HANDOFF.md` *(in inglese)* per cosa significa e cosa cambierebbe — e nota che ciò che ha chiuso il
primo giro è stato cambiare la *popolazione*, dichiarata in anticipo, non abbassare la soglia.
