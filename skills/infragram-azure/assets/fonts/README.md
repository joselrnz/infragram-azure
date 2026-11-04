# fonts/

The two faces every picture sets its text in -- Inter and Geist Mono -- ship
here, so the editor page, the static page and the standalone SVG carry them
inline and draw the same anywhere: offline, embedded as an image, or rendered
on a machine with no route out. Nothing is fetched.

- Subsetted woff2 exactly as the Google Fonts CSS API serves them to a current
  Chrome; latin and latin-ext only, which covers every label the shipped
  libraries and templates set. Inter (weight 400 to 700) and Geist Mono (400
  to 600) are the variable files.
- Inter sets the editor, the static page and every label in a diagram, as one
  face across the whole product; Geist Mono sets monospaced frame titles and
  is the second face the Text panel offers.
- `catalog.json` records each face: family, style, weight range, subset,
  unicode range, file, size, sha256 and the source URL. `infragram.catalog.fonts`
  refuses a file whose digest drifted from the catalog.
- Both families are under the SIL Open Font License 1.1. The notices are
  `OFL-inter.txt` and `OFL-geist-mono.txt`, as published in google/fonts.

Regenerate only from the URLs in `catalog.json`; never hand-edit a font.
