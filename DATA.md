# Data provenance and licensing

## What is in this repository

`tu_dien_viet_tay_nung_parsed.xlsx` — a machine-readable parse of a
Vietnamese–Tày–Nùng dictionary, 18,788 rows. Every lexical entry, sentence pair
and evaluation example in this project is derived from this one file.

## What is deliberately excluded

The scanned source dictionaries and reference materials are **not** committed
(see `.gitignore`). They are published works — notably *TỪ ĐIỂN TÀY-VIỆT*
(editor-in-chief Lương Bèn) — and redistribution rights have not been cleared.
The code will not run without a dictionary file present at the path given by
`EXCEL_GLOSSARY_PATH`.

## Licensing caveat

The MIT licence in `LICENSE` covers **the source code only**. It does not grant
any rights over the dictionary content, which remains the property of its
original authors and publishers. The parsed spreadsheet is included so the
project is reproducible and inspectable; if you intend to redistribute or use
the lexical data commercially, clear that separately with the rights holders.

If you are the rights holder and would prefer the parsed data removed, please
open an issue.

## A note on the language

Tày is a Tai-Kadai language with roughly 1.8 million speakers in northern
Vietnam. This project does not claim an absence of other translation tools.
Its implementation depends heavily on
dictionaries compiled by community linguists, and that labour deserves
attribution rather than silent absorption into a dataset.
