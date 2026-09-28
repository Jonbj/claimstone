# Mappa della documentazione

Quale file risponde a quale domanda. *In English: [README.md](README.md).*

## Da qui

| Voglio… | leggi |
|---|---|
| sapere cos'è questo progetto, in due minuti | [`../README.it.md`](../README.it.md) |
| eseguire un giro e capire cosa ne esce | [`GUIDE.it.md`](GUIDE.it.md) |
| sapere cosa sta girando e cosa è in sospeso adesso | [`HANDOFF.md`](HANDOFF.md) *(inglese)* |
| lavorare sul codice come agente | [`../CLAUDE.md`](../CLAUDE.md), poi [`../AGENTS.md`](../AGENTS.md) *(inglese)* |
| discutere una scelta architetturale | [`DESIGN_DECISIONS.md`](DESIGN_DECISIONS.md) *(inglese)* — prima trova la voce |
| scrivere su un registro, o leggerne uno | [`contracts/`](contracts/) *(inglese)* — un file per registro |
| sapere cosa uno stadio doveva fare | [`superpowers/specs/`](superpowers/specs/) *(inglese)* |

## Il registro delle decisioni

[`DESIGN_DECISIONS.md`](DESIGN_DECISIONS.md) sono 49 decisioni numerate in circa 2.000 righe, ognuna con **la
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
| [`contracts/acquisitions.md`](contracts/acquisitions.md) | ogni tentativo di scarico, la sua licenza, e perché è fallito |
| [`contracts/normalize.md`](contracts/normalize.md) | documenti e blocchi |
| [`contracts/claims.md`](contracts/claims.md) | un'affermazione, la sua citazione, e i valori convertiti dal motore |
| [`contracts/reviews.md`](contracts/reviews.md) | il verdetto di un secondo lettore su un'affermazione |
| [`contracts/model_calls.md`](contracts/model_calls.md) | il confine su file che ogni stadio con modello attraversa |

## Le specifiche degli stadi

[`superpowers/specs/`](superpowers/specs/) contiene un disegno per stadio, ognuno marcato implementato o no,
più due che non sono stadi:

- **il contratto dei verdetti** — i cinque stati, perché le domande `operational` non ne ricevono nessuno, e
  la divisione in due livelli che rende ogni verdetto di una persona. Da leggere prima di toccare lo stadio 5
  o il 6.
- **la dashboard** — specificata, lasciata deliberatamente per ultima, e non costruita. Il suo valore ha
  bisogno di dati in ogni stadio.

Una specifica dice cosa era previsto. Il registro dice cosa è stato misurato dopo, e dove non concordano vince
il registro.

## Lingua

I documenti rivolti a chi legge sono in **inglese e italiano**: questa mappa, il README principale e la guida.

Tutto il resto è **solo in inglese**: il registro delle decisioni, i contratti, le specifiche e i commenti nel
codice. È una scelta, non una dimenticanza. Quei file cambiano quasi a ogni commit, e due copie di una regola
divergono — e la copia che diverge è quella che inganna qualcuno. Questo repository vincola `cli.BACKENDS` a
`runners.available()` con un test esattamente per questo, e tre test scritti in un giorno sono stati corretti
perché pescavano nella **prosa di un commento** invece che nel codice che descriveva.

Quindi: bilingue dove è stabile e si legge di rado, una lingua sola dove si lavora.
