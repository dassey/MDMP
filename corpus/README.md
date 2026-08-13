# Doctrine library

Anything you put in this folder is indexed and searched when the tool generates
options. Retrieved passages are shown next to the options they informed, with
the document they came from.

Readable formats: **PDF, DOCX, PPTX, TXT, Markdown, HTML, CSV.**

After adding files: **Settings → Doctrine library → Index new documents**, or
restart with `python3 serve.py --reindex`.

## What ships here

`seed/` holds distilled reference notes written for this tool, so retrieval works
before you have added anything. They are summaries, not publications — treat
them as a starting point and replace them with the real thing.

## What is worth adding

Drop the current editions of the publications your unit actually uses. The ones
that pay off most here:

| Publication | Why it helps |
|---|---|
| **FM 5-0** Planning and Orders Production | The MDMP itself — every step, every output |
| **FM 6-0** Commander and Staff Organization and Operations | Order formats, annexes, staff duties, CCIRs |
| **ADP 5-0** The Operations Process | Intent, planning fundamentals, the operations process |
| **ADP 3-0 / FM 3-0** Operations | Operational framework, warfighting functions, types of operations |
| **ATP 2-01.3** Intelligence Preparation of the Battlefield | Terrain, weather, threat COA development |
| **ATP 2-01** Plan Requirements and Assess Collection | Information collection, PIR management |
| **ATP 5-19** Risk Management | The risk matrix and the five steps |
| **ADP 1-02** Terms and Military Symbols | Tactical mission tasks, graphics, symbology |
| **TC 7-100 series** | Opposing force doctrine — threat structures and tactics |
| **TC 7-101** Exercise Design | Exercise framework, MSEL construction |
| **Your unit's TACSOP** | The local way of doing it, which usually matters more |

Unit-specific material — your TACSOP, a previous OPORD you liked, an exercise
framework, an OC/T observation report — is often more useful than the manuals,
because it is what your staff actually recognises.

## Notes

- A PDF that indexes as empty is almost certainly a scan. Run OCR on it first.
  `pip install pypdf` improves extraction from generated PDFs.
- Nothing here leaves the machine. Indexing is local and the index lives in the
  same SQLite file as the plans.
