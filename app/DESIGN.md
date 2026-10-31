# Design: Fusion

- **Direction:** a trial exhibit. A copied document entered into evidence: a solid label on the corner carrying the one fact that matters, the words relied on marked in highlighter, a source line at the foot of the page. It fits because the whole product is whether a dated document counts. The world lends type, palette and one signature move; the layout is an ordinary list and detail screen, so it reads as a working tool first.
- **Must not look like:** a patent-search dashboard, a chat window, a legal theme of cream paper and serifs. No rubber stamps, rotated labels or paper textures.
- **References:** trial exhibit labels and marked-up copies, US patent file wrappers, plain-text mailing-list archives.

Chosen by Impeccable's direction roll (seed:a4bdc960eae63e88) without the decision page, because the build couldn't wait. The palette was later matched to the pitch deck's red theme (`docs/handover/deck/index.html`), and the team settled the home page and the idea page in review.

## Tokens

```css
:root {
  --red: #ae1018;    /* the home page, the rail, the email date label, actions, links */
  --ink: #141412;    /* text, and the patent date label */
  --meta: #45433e;   /* provenance and source lines only */
  --desk: #f2efe8;
  --paper: #ffffff;  /* the document sheet, the idea box, text on red */
  --yellow: #ffe83d; /* the words from the record, and nowhere else */
  --sans: 'Archivo Variable'; /* everything else; on the idea page 900 only for the wordmark */
  --mono: 'Space Mono'; /* the email itself, because it's plain text, and the home page's streams */
}
```

## Rules

- Type scale: 80 for the home question, 60 for the not-found line, 34 for the date label, 30 for the cutoff, 28 for the part, 17 to 19 for reading, 15 at the smallest.
- Fonts are bundled through `@fontsource`, never a CDN.
- The logo is the Core mark, in the current text color left of the name on both pages, and in red as the favicon.
- Text on red is always white, never ink: the user rejected ink on red for low contrast. Red text on the desk is for large text or links only.
- The record's own words are ink on a plain yellow highlight, with no underline or extra weight. Found dates in the sidebar are red.
- The idea page is a product screen: a red toolbar, a light sidebar with the case and its parts, and white panels on the desk. A found part reads in this order: the part, the document with its date, Reactor's answer, a table of the cited documents, then what was searched.
- Home is one red page: the question, the idea box and the previous searches in one centered column, over a red that darkens toward the bottom with patent numbers and dates from the corpus rising behind everything. With live off, pressing Search says so and points at the previous searches.
- A label's limit stays on screen: "Earliest cited" is what the code knows, since it sorts what Reactor cited by date.
- Signature: the date in red at the corner of the document, with its distance from your date. A not-found result has no sheet and no label, so the two read differently from the back of a room.
- Emails and patents are different documents: an email is plain text in Space Mono under mail headers. A patent is set in Archivo under its number and title, with its drawing beside the abstract.
- A short abstract fits with no scrolling, and a long email scrolls to its marked words on a whole line.
- Motion: only the streams on the home page, off under reduced motion. No fake progress: a live question shows a real seconds counter.
- The user's slop list in `AGENTS.md` applies.- Live and saved are always stated.
