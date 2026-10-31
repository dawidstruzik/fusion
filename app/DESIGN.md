# Design: Fusion

- **Direction:** a trial exhibit. A copied document entered into evidence: a solid label on the corner carrying the one fact that matters, the words relied on underlined in red, a source line at the foot of the page. It fits because the whole product is whether a dated document counts. The world lends type, palette and one signature move; the layout is an ordinary list and detail screen, so it reads as a working tool first.
- **Must not look like:** a patent-search dashboard, a chat window, a legal theme of cream paper and serifs. No rubber stamps, rotated labels or paper textures.
- **References:** trial exhibit labels and marked-up copies, US patent file wrappers, plain-text mailing-list archives.

Chosen by Impeccable's direction roll (seed:a4bdc960eae63e88) without the decision page, because the build couldn't wait. The palette and fonts were later matched to the pitch deck's red theme (`docs/handover/deck/index.html`), and the team settled the home page and the highlight in review.

## Tokens

```css
:root {
  --red: #ae1018;    /* the home page, the rail, the email date label, actions, links, the underline */
  --ink: #141412;    /* text, and the patent date label */
  --meta: #45433e;   /* provenance and source lines only */
  --desk: #f2efe8;
  --paper: #ffffff;  /* the document sheet, the idea box, text on red */
  --sans: 'Archivo Variable'; /* headlines at 900 */
  --mono: 'Space Mono'; /* the email itself, because it's plain text */
}
```

## Rules

- Type scale: 80 for the home question, 60 for the not-found line, 34 for the date label, 30 for the cutoff, 28 for the part, 17 to 19 for reading, 15 at the smallest.
- Fonts are bundled through `@fontsource`, never a CDN.
- Text on red is always white, never ink: the user rejected ink on red for low contrast. Red text on the desk is for large text or links only.
- The record's own words are bold ink on a 4px red underline, with no background. No yellow.
- Home is one red page: the question, the idea box and the previous searches in one centered column. With live off, pressing Search says so and points at the previous searches.
- A label's limit stays on screen: "Earliest cited" is what the code knows, since it sorts what Reactor cited by date.
- Signature: the date label on the corner of the sheet, with its distance from your date. A not-found result has no sheet and no label, so the two read differently from the back of a room.
- Emails and patents are different documents: an email is plain text in Space Mono under mail headers with a red label. A patent is set in Archivo under its number and title with an ink label. Its drawing is a link, because a flowchart can't be read beside the abstract.
- A short abstract fits with no scrolling, and a long email scrolls to its marked words on a whole line.
- Motion: only the label landing on a sheet, 260 ms, off under reduced motion. No fake progress: a live question shows a real seconds counter.
- The user's slop list in `AGENTS.md` applies. The date label is the one element near that line: it's a large solid block carrying content, not a small tag.
- Live and saved are always stated.
