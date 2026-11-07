# 0009: Shared viewing and comments without a server

Status: accepted, 2026-11-06. The first step below is built, with one
change: the comments live in a panel the header opens, not in a tab of the
bottom drawer, because the drawer is hidden in review mode and on a phone,
where reviewers read.

## Context

A team wants to look at one diagram from a link and leave comments on its
cards, frames and wires. draw.io, Excalidraw and IcePanel all do this, and it
is the largest gap Infragram has against them.

What Infragram is today constrains the answer (ADR 0003):

- An exported page is one HTML file. It carries its editor, libraries, fonts
  and document (`<script id="infragram-project">`), works from `file://`, and
  loads nothing remote. `infragram check` fails a page that does.
- The editor keeps its working copy in the browser's local storage, under the
  document's slug. Nothing is sent anywhere.
- Every card, frame and wire has an id. An id survives a rename in the editor.
  A Python diagram derives an id from the name unless it passes `id=`, so
  renaming the card in the Python file changes its id.
- A document is a file in a repository, and `infragram diff` already draws what
  changed between two versions of it.

## The questions, and the options for each

**1. Where a shared copy lives.**

| Option | What it takes | Cost |
|---|---|---|
| A. A static host (GitHub Pages, Forgejo Pages, any web server) serves the exported page | A CI job that exports the page and publishes it | A link anyone can open. No accounts, and nobody can write back to the page |
| B. A comments file beside the document in the repository, `<slug>.comments.json` | A file format, plus reading and writing it | Comments travel with the document, reviewed in pull requests like any change |
| C. A small sync service, live and multi-user | A server to write, host, secure and keep running | Real-time comments, but it breaks "works offline, sends nothing" and adds an operator |

**2. How a comment stays on its element.** It names the element's id and kind
(`node`, `boundary`, `edge`), the document's slug, and the id's name when the
comment was made. On load, a comment finds its element by id. If the id is
gone, it tries the same kind with the same name. If neither matches, the
comment is shown as detached in the comments list, never dropped. Moving or
re-laying out an element changes nothing, because coordinates are not part of
the anchor.

**3. Who edits.** Editing stays single-author: the author changes the document,
everyone else comments. Two people's edits to one document already merge
through git, and `diff` shows what moved. Merging live edits (CRDTs, operation
logs) is not needed for comments, and nothing here depends on it.

**4. What the editor needs.**
- A Comments tab in the bottom drawer, beside the inventory: the thread for
  each element, the detached ones, and a count.
- **Add comment** in the right-click menu.
- A small numbered marker on each commented element. Like the drill-down
  stubs, it is a view layer and is never exported.
- **Download comments**, which writes `<slug>.comments.json`.
- An unsent comment is kept in local storage under the slug, as edits are now.

**5. Privacy.** Nothing about a diagram leaves the machine unless the user
publishes a file themselves. A comment carries the name its author typed, and
no account or e-mail address. Opening a page sends nothing, and the checker
keeps failing a page that loads something remote.

## Decision (proposed)

Take A and B together, and leave C out.

- Comments are data in a file: `<slug>.comments.json`, versioned, beside the
  `.infragram.json`. `export:project` carries the file into the page, as it
  carries the document, and `infragram check` validates it.
- Viewing is a static page. A CI job exports the page and publishes it to
  Pages, and the link is the shared copy.
- Writing a comment happens in the page: it is kept locally, then
  **Download comments** gives the reviewer a file to send back or commit. A
  pull request merges comments like any other change.
- A live service (C) needs its own ADR, if it is ever wanted. Nothing in this
  design blocks it: the same file can be what such a service stores.

## The smallest first step

Comments in the page, local only. That means the comments file format, the
Comments tab, **Add comment**, the markers, **Download comments**, and
`export:project` embedding `<slug>.comments.json` when it sits beside the
document. Done when a browser test adds a comment to a card and a frame,
renames the card in the editor, reloads, finds both comments, downloads them,
and sees an export carry them back, with the SVG, PNG and draw.io unchanged.

Publishing to Pages is a CI recipe in the docs and needs no code.

## Consequences

- No server to run or secure, and the offline, single-file promise holds.
- Comments are not live. A reviewer's comments reach the author as a file or a
  pull request, which suits review, not chat.
- A Python author who renames a card without `id=` detaches its comments. The
  comments list shows them, and the docs say to pass `id=` on elements that
  carry discussion.
- The file is plain JSON in the repository, so who said what is in git's
  history, not in a database.
- An author's name is whatever the reviewer typed: nothing verifies it.
  Who committed a comments file, in git, is the record to trust.
