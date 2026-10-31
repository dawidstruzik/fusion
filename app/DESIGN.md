# Design: Fusion

- **Direction:** a trial exhibit. A copied document entered into evidence: a solid label on the corner carrying the one fact that matters, the words relied on marked in highlighter, a source line at the foot of the page. It fits because the whole product is whether a dated document counts. The world lends type, palette and one signature move; the layout is an ordinary list and detail screen, so it reads as a working tool first.
- **Must not look like:** a patent-search dashboard, a chat window, a legal theme of cream paper and serifs. No rubber stamps, rotated labels or paper textures.
- **References:** trial exhibit labels and marked-up copies, US patent file wrappers, plain-text mailing-list archives.

Chosen by Impeccable's direction roll (seed:a4bdc960eae63e88) without the decision page, because the build couldn't wait. Top-ranked alternative if this one fails on stage: a plain claim chart with all elements in one table.

## Tokens

```css
:root {
  --blue: #1538c4;   /* the rail, the date label, actions and links */
  --yellow: #ffe83d; /* the words from the record, and dates in the rail */
  --ink: #0d1220;
  --meta: #4a5366;   /* provenance and source lines only */
  --desk: #e7ebf2;
  --paper: #ffffff;  /* the message sheet, inputs */
  --sans: 'Libre Franklin Variable';
  --mono: 'Courier Prime'; /* the message itself, because it's plain text */
}
```

## Rules

- Type scale: 60 for the not-found line, 36 for the cutoff, 34 for the date label, 28 for the element, 17 to 19 for reading, 15 at the smallest.
- Fonts are bundled through `@fontsource`, never a CDN.
- One color, one job: yellow appears only on words from the record and on found dates. Blue is the only action color.
- Signature: the date label on the corner of the sheet, with its distance from your date. A not-found result has no sheet and no label, so the two read differently from the back of a room.
- Emails and patents are different documents: an email is plain text in Courier Prime under mail headers with a blue label. A patent is set in Libre Franklin under its number and title with an ink label, and its first drawing beside the abstract if there is one.
- Motion: only the label landing on a sheet, 260 ms, off under reduced motion. No fake progress: a live question shows a real seconds counter.
- The user's slop list in `AGENTS.md` applies. The date label is the one element near that line: it's a large solid block carrying content, not a small tag.
- Live and saved are always stated.
