# Tày Translator — Project Overview

*A plain-language description of what this project is and what came out of it.
For the engineering detail, see [TECHNICAL.md](TECHNICAL.md).*

---

## The problem

**Tày** is a language spoken by around 1.8 million people in the mountains of
northern Vietnam. It is one of the country's larger minority languages, and it is
almost completely invisible to modern technology.

There is no Google Translate for Tày. Speech recognition software does not have a
setting for it. The large AI language models that handle English, Vietnamese and
Chinese have effectively never seen it. If you are a Tày speaker who wants to read
something in Vietnamese, or a student trying to learn the language, there is no
software that helps you.

The reason is data. Modern translation systems learn by reading millions of
sentences that have already been translated by humans. For Tày, that collection
does not exist.

What does exist is a **dictionary** — one Vietnamese–Tày dictionary, compiled by
linguists, digitised into a spreadsheet of about 18,000 entries.

This project asks: **how good a translator can you build from a single
dictionary?**

---

## What it does

It is a small web application that runs entirely on one computer, with no
internet connection and no paid services.

You type a Tày sentence and it gives you the Vietnamese — or the other way
round. Alongside the translation it shows you:

- **how confident it is**, and it is honest when the answer is a guess
- **which words it actually recognised**, and which it did not
- **the similar sentences it consulted** to work out what each word meant

That last part matters more than it sounds. Most translation tools give you an
answer and no way to judge it. This one shows its working.

---

## Why it is harder than it looks

The dictionary runs in the wrong direction.

It is organised Vietnamese-first: look up a Vietnamese word, get the Tày. But
translating *from* Tày means running it backwards, and backwards it is
enormously ambiguous. The Tày word `mẻ` is listed as the translation of *mẹ*
(mother), *vợ* (wife), *cái*, *gái* (girl), *bà* (grandmother) and several more.
The dictionary can tell you all the possibilities. It cannot tell you which one
belongs in *this* sentence.

That single problem accounts for roughly **85% of everything the system still
gets wrong**. Not missing words — it recognises 99.9% of the words it is given.
Not word order — that accounts for under 1% of errors. Just choosing which
meaning was intended.

---

## The most important thing that happened

Early on, the system reported **93.7% accuracy**.

That number was false, and finding out why became the most valuable part of the
project.

The test set had been built from the same dictionary the system had already
memorised. It was being asked to translate sentences it had effectively been
given the answers to — like marking your own exam with the answer sheet open.
Once the test was rebuilt properly, using sentences the system had genuinely
never seen, real accuracy turned out to be around **10%**.

That failure was hiding a straightforward bug: three lines of code were throwing
away the part of each dictionary entry that held the actual word translations. The
system had memorised thousands of complete example sentences while being unable to
translate a single individual word it had not seen before.

**This exact mistake then happened twice more**, in new parts of the system, and
was caught both times. Anything that learns from the dictionary has to be blocked
from seeing the test answers — not just the obvious part.

---

## Results

Measured properly, on sentences held back from the system:

| | Roughly |
|---|---|
| At the start | **10%** of a perfect translation |
| Now, Tày → Vietnamese | **44%** |
| Now, Vietnamese → Tày | **47%** |

For comparison, published research on translating languages with this little data
usually lands in the 30–50% range — so this sits inside the normal band for the
problem, built from a single dictionary rather than a research corpus.

In practice that means short, common sentences are usually right — `ăn cơm`
("eat rice") and `nó đi rồi à?` ("has he gone?") come out correctly — while
longer or more idiomatic sentences come out understandable but clumsy.

---

## The finding I did not expect

The obvious way to improve a translator today is to add an AI model. I tried
that, and measured it carefully, and **it made the translations worse**.

Two different local AI models were tested, each in four configurations — eight
measurements in total. Every single one scored below the plain dictionary method.
The larger model was better than the smaller one, but still not good enough to
beat a carefully built lookup system.

So the AI step is switched off, and the code records why, along with the score any
future model has to beat before it gets switched back on.

The same thing then happened four more times with other clever additions: a
statistical model of Vietnamese word order, a machine-learning model that taught
itself word translations, extra retrieved context, and more example sentences.
Several of them were genuinely working — the machine-learning model correctly
learned that `mẻ` most often means *mẹ* (mother), which the hand-written rules had
got wrong — and they *still* did not improve the final result, because something
already in the system was solving the same problem.

The lesson I would take from this: **an improvement that sounds sophisticated is
not an improvement until you have measured it.** Six times in this project the
sophisticated option lost to the simple one, and the only reason I know that is
that the test was honest.

---

## What it cannot do

Being straight about the limits:

- It is **not a fluent translator**. It gets the meaning across; it does not write
  natural Vietnamese.
- **Idioms defeat it.** `mẻn slua khôm phêt` means "bitter defeat", but assembled
  word by word it becomes "eat lose suffering hardship".
- **Speech input is a workaround.** No speech recogniser supports Tày, so it uses
  the Vietnamese one and nudges it toward Tày spelling. Results are rough.
- **It cannot speak Tày** — there is no text-to-speech for the language.
- Everything it knows comes from **one dictionary**, whose examples are short and
  idiomatic rather than natural conversation.

---

## What would make it better

Not more clever algorithms — six have now been tried and measured, and the
returns have flattened.

What it actually needs is **more Tày text**: real sentences in real context, which
is the one thing a dictionary cannot provide. That is a language-documentation
effort rather than a programming one, and it is the honest answer to "what's
next".

---

## A note on credit

This was built with substantial AI assistance. The code was written in
collaboration with an AI coding assistant; the direction, the experiments chosen,
and the interpretation of the results are mine. The dictionary itself is the work
of Vietnamese linguists and is not mine at all — see [DATA.md](DATA.md).
