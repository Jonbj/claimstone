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
.venv/bin/pytest -q                                    # 1026 test
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
- **[docs/DESIGN_DECISIONS.md](docs/DESIGN_DECISIONS.md)** *(in inglese)* — 68 decisioni, ognuna con la
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

Gli altri due corpus rimangono sotto la propria soglia e correttamente non producono conclusioni.
