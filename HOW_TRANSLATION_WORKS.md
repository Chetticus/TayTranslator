# How TayTranslator translates

A guide for explaining the current text translator to a friend, teacher, or interviewer.
This describes the repository's default configuration. Railway environment variables
can override those defaults; `/api/health` reports whether the optional LLM is enabled.

## The 30-second explanation

TayTranslator starts with a digitised Vietnamese–Tày dictionary and its bilingual
example sentences. It matches phrases in the user's input, collects possible
translations, and chooses a combination using dictionary evidence and simple
statistics about which words occur together. When translating from Tày, it also
retrieves similar bilingual sentences to help choose between meanings. English
translation adds a pretrained English–Vietnamese neural model before or after
that process. The default Tày engine does not use a large language model.

## Before a request: preparing the resources

The server reads `tu_dien_viet_tay_nung_parsed.xlsx`. It extracts word translations
and bilingual examples and builds lookup indexes for both directions. It also
builds a searchable example collection, statistical word-pair counts, and a table
of additional phrases extracted from aligned examples.

These resources are cached in server memory and prepared when first needed.
They are reused across requests. There is no web search or call to taynung.com
in this translation path.

The dictionary's original direction matters: a Vietnamese entry gives Tày
translations. Inverting it can give one Tày word several Vietnamese meanings.
For example, dictionary entries associate `mẻ` with several meanings, including
`mẹ` and `vợ`. The system needs evidence to choose a meaning for a particular sentence.

## From input to output

### 1. The browser sends the translation request

The user selects a direction, types text, and optionally lists names or phrases
under **Keep unchanged**. The browser sends these values to `/api/translate`.

For the deployed website, this means the text travels to the Railway server.
The models run on that server, rather than on the student's phone or browser.

### 2. The server checks the input

The server checks that the direction is supported, the text is not blank, and
the input stays within 2,000 characters and 200 whitespace-separated words.
It rejects invalid control characters and checks the protected-term limits.

An English model step also has a token limit. Overly long intermediate results
are rejected rather than silently cut off.

### 3. It prepares text for matching and protects special values

The dictionary engine normalises Unicode and whitespace. It uses normalised
lookup keys while retaining the input's punctuation and protected text for output.

Before matching dictionary phrases, it identifies spans to preserve:

- Names or phrases explicitly entered by the user.
- Some names identified by introduction and capitalisation rules.
- Structured values such as URLs, email addresses, and numbers.

This is rule-based name protection, not a general named-entity AI model. It can
miss names or preserve ordinary capitalised words. The explicit **Keep unchanged**
field gives the user control when the automatic rules are insufficient.

### 4. It performs an initial dictionary translation

The engine scans the input from left to right, trying longer phrases before
shorter ones, up to a configured maximum of 14 whitespace-separated units.
It avoids matching across protected spans or punctuation boundaries.

This allows a known phrase to be translated together rather than assembling
separate word meanings. Candidate translations can come from dictionary words,
complete example phrases, or the additional phrase table extracted from examples.
Complete dictionary examples receive stronger base scores than individual words.

If an exact lookup fails, the engine can try a lookup without tone marks and,
later, a limited spelling-distance match. Those matches are guesses and are
reported as weaker evidence.

Some unmatched Tày input that also looks like a common Vietnamese word is left
unchanged and marked separately. An unknown word is generally shown in brackets,
such as `[unrecognisedword]`, rather than assigned an invented meaning.

### 5. For Tày → Vietnamese, it retrieves similar examples

After the initial pass, the server searches the bilingual example collection
using the cleaned Tày input. It returns **up to two** examples above its similarity
threshold under the default settings. It can return fewer, including none.

The search uses shared words, gives more weight to rarer words, penalises
unnecessarily long examples, and adds a character-trigram similarity score.
A character trigram is simply a sequence of three neighbouring characters.
Candidate sentences must share at least one matching word before this additional
character score is considered.

There is no embedding model or vector database in this retriever. It is a lexical
search algorithm over the dictionary's examples.

**Vietnamese → Tày skips this similar-sentence retrieval step in the live API.**
That direction still uses the dictionary, extracted phrase table, and statistical
decoder. Earlier experiments motivated keeping retrieval only in the Tày-input path.

### 6. Retrieved evidence changes candidate scores

If examples were retrieved, the server runs the dictionary engine again with
those examples as context.

A candidate meaning gets a stronger bonus when its words appear in the Vietnamese
translation of an example that contains the particular Tày phrase being translated.
More similar examples carry more weight. A smaller bonus can come from words
appearing elsewhere in the retrieved translations.

This helps resolve ambiguous meanings, but similarity is not proof that two
sentences intend the same meaning. The wrong example can still encourage a wrong choice.

### 7. A statistical decoder chooses a combination of meanings

Several spans may each have multiple candidate translations. The engine uses
**Viterbi decoding**, a dynamic-programming algorithm, to choose a sequence of
candidates that balances dictionary/context scores against a small fluency score.

That fluency score comes from a **bigram language model**: counts of how often
neighbouring words occur together in the example sentences. Translating into
Vietnamese uses Vietnamese statistics; translating into Tày uses Tày statistics.

It is a language model in the statistical sense, but it is not an LLM. It learns
word-pair probabilities from the supplied examples and helps rank existing
translation candidates. It does not freely write new explanations or rearrange
the entire sentence. Source spans generally retain their order, although a phrase's
stored translation can have its own internal word order.

### 8. It assembles the translation and its evidence

The engine joins the selected translations and restores punctuation around the
translated spans. Protected names and literals retain their preserved text.

It also builds a glossary showing what each input span became, where the match
came from, and alternative meanings where available. Retrieved examples are
included when used.

### 9. It adds coverage and a confidence label

Coverage measures how much of the input received a dictionary/phrase match.
It can include approximate matches. Protected names and unchanged common words
are tracked separately rather than counted as successful translation matches.

Confidence is a rule-based label based on coverage, ambiguous meanings, weak
matches, unknown terms, and whether tone marks appear to be missing. These are
warning signals, not a calibrated probability of correctness.

**100% coverage does not mean 100% accuracy.** Every word can have a match while
the chosen meanings are wrong. Likewise, a correctly preserved name can lower
coverage even when preserving it is exactly what the user wanted.

### 10. The browser displays the result

The server returns the translation and metadata. The interface shows the text,
confidence, coverage, glossary, and available example evidence.

Conversation history is stored in that browser. This does not automatically
create a central research dataset or a record of everyone who tested the site.
Ordinary use does not retrain the translator. Corrections must be collected and
reviewed through an explicit evaluation process before being used for improvements.

## What changes for English?

| Selected direction | Processing path |
| --- | --- |
| Tày → Vietnamese | Dictionary engine with retrieved context |
| Vietnamese → Tày | Dictionary engine without similar-sentence retrieval |
| English → Tày | Local English → Vietnamese neural model, then Vietnamese → Tày dictionary engine |
| Tày → English | Tày → Vietnamese dictionary engine with retrieved context, then local Vietnamese → English neural model |

The English bridge uses pretrained Argos 1.9 translation packages through
CTranslate2 on the server CPU. These are neural machine translation models,
not general-purpose chat LLMs, and they were not trained from scratch by this project.
Model files are downloaded during deployment; inference does not call an external
translation provider.

The bridge attempts to preserve explicitly protected text and some names/literals
by translating around them. Splitting sentences this way can reduce fluency.

The interface can show the intermediate Vietnamese text so users can inspect
where an error may have entered the two-stage translation. English output is
currently labelled low confidence because errors can compound across both stages.
Its coverage percentage refers only to the Vietnamese–Tày dictionary step.

## Is there any optional LLM?

Yes. The code contains an optional Ollama editing step for eligible
Tày → Vietnamese requests. `USE_LLM` defaults to `0`, so the ordinary deployment
does not use it unless someone enables it. It is also bypassed for English routes,
Vietnamese → Tày, and requests with preserved terms.

Historical held-out experiments in the repository found that the tested LLM
configurations lowered translation scores, which is why this stage is off.
That is a finding about those tested configurations, not proof that an LLM could
never help.

## How to demonstrate it

Start with `kin khẩu` in Tày → Vietnamese. Inspect the translation, then expand
the glossary and retrieved examples. Explain which evidence was actually used;
a short exact phrase may already be solved by phrase lookup.

Next, try `xin chào mình là Nguyễn Hải Nam` in Vietnamese → Tày. Check that the
name is preserved. If a different name is not protected automatically, put it
in **Keep unchanged** and repeat.

Finally, try an English sentence and inspect its intermediate Vietnamese. This
demonstrates the neural bridge separately from the Tày engine.

Two requests checked against the current default engine while writing this guide:

| Input | Direction | Observed output |
| --- | --- | --- |
| `kin khẩu` | Tày → Vietnamese | `ăn cơm` |
| `xin chào mình là Nguyễn Hải Nam` | Vietnamese → Tày | `xo slắng cần hêt Nguyễn Hải Nam` |

The second example verifies that the name survives; it does not establish that
the surrounding sentence is a good Tày translation. A speaker still needs to
assess its meaning and naturalness. The first example is already present in the
dictionary, so it demonstrates the workflow rather than performance on unseen text.

For a fair accuracy test, ask fluent speakers to write original sentences and
their intended meanings before seeing the model's output. Keep a test set aside
when using their corrections to improve the system. Historical chrF scores in
other repository documents measure character overlap with reference translations;
they must not be described as a percentage of sentences translated correctly.

## Accurate wording for a presentation

"I built a hybrid translator for a language with limited digital resources.
The Tày engine combines a digitised dictionary, phrase extraction, retrieval of
similar examples, and statistical decoding. English support uses pretrained
neural translation models through Vietnamese. The system exposes its evidence
and uncertainty, and I am evaluating it with Tày speakers."

Credit the dictionary's authors and the pretrained model providers. Describe
your own contribution as the application, integration, experiments, evaluation,
and improvements you actually directed or implemented; see `DATA.md` and
`ENGLISH.md` for provenance and model details.

## Code map

- `code/main.py`: request validation, direction routing, retrieval orchestration,
  confidence rules, and optional LLM editing.
- `code/translation_api/excel_glossary.py`: indexes, protection rules, matching,
  candidate scoring, Viterbi decoding, and output assembly.
- `code/translation_api/retriever.py`: lexical retrieval of bilingual examples.
- `code/translation_api/lm.py`: statistical word-pair language models.
- `code/translation_api/align.py` and `phrases.py`: alignment and phrase extraction.
- `code/translation_api/english_bridge.py`: local English–Vietnamese models.
- `code/templates/tay_chat.html`: browser requests, result display, and local history.
