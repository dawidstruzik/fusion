# Design: Fusion

- **Direction:** a trial exhibit. A copied document entered into evidence: a solid label on the corner carrying the one fact that matters, the words relied on marked in highlighter, a source line at the foot of the page. It fits because the whole product is whether a dated document counts. The world lends type, palette and one signature move; the layout is an ordinary list and detail screen, so it reads as a working tool first.
- **Must not look like:** a patent-search dashboard, a chat window, a legal theme of cream paper and serifs. No rubber stamps, rotated labels or paper textures.
- **References:** trial exhibit labels and marked-up copies, US patent file wrappers, plain-text mailing-list archives.

Chosen by Impeccable's direction roll (seed:a4bdc960eae63e88) without the decision page, because the build couldn't wait. Top-ranked alternative if this one fails on stage: a plain claim chart with all elements in one table.

## Tokens

The palette and fonts match the pitch deck's red theme (`docs/handover/deck/index.html`), at a teammate's request, except the highlight, which keeps its own color.

```css
:root {
  --red: #ae1018;       /* surfaces only: the home band and the rail */
  --highlight: #ffe83d; /* the words from the record, nothing else */
  --ink: #141412;       /* text, links, buttons */
  --meta: #45433e;      /* the quiet lines only */
  --desk: #f2efe8;
  --paper: #ffffff;     /* the document sheet, inputs, text on red */
  --sans: 'Archivo Variable'; /* headlines at 900 */
  --mono: 'Space Mono'; /* the email itself, because it's plain text */
}
```

## Rules

- Hierarchy, so one thing reads first from the back of a room: the date and its distance, huge, with no box. Then the record's words in highlighter on the sheet. Then Reactor's sentence at reading size, unedited. Then quiet lines: other citations, how it was written and what was searched.
- Type scale: 88 for the date and the not-found line, 24 for the distance, 21 for a patent's abstract, 17 for an email, 15 at the smallest.
- Fonts are bundled through `@fontsource`, never a CDN.
- Text on red is always white, never ink: the user rejected ink on red for low contrast.
- The rail holds the name, the idea's title and each part with its date or "Not found". The full idea is one click away.
- Home is the idea box on a red band and the saved ideas on the desk below it, each a title and "3 of 4 parts". With live off, pressing the button says so and points at the saved ideas.
- A label's limit stays on screen: "Earliest cited" is what the code knows, since it sorts what Reactor cited by date.
- Emails and patents are different documents: an email is plain text in Space Mono under mail headers. A patent is set in Archivo under its number and title. A patent's drawing is a link, because at the sheet's size a flowchart can't be read.
- Motion: none. No fake progress: a live question shows a real seconds counter.
- The user's slop list in `AGENTS.md` applies.
- Live and saved are always stated: the quiet line under each answer says "saved" or "asked live".
