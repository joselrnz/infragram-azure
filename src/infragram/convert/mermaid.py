"""Mermaid: flowcharts, architecture diagrams and C4 diagrams.

- ``flowchart``/``graph``: nodes in every shape Mermaid has (a ``[(cylinder)]``
  is a database, ``@{ shape: cyl, icon: "aws:lambda" }`` the v11 form),
  ``subgraph`` blocks as frames, links in every weight with ``|labels|`` or
  ``-- inline labels -->``, ``A & B --> C`` fans, ``fa:fa-user`` icons;
- ``architecture-beta``: groups, services, junctions (folded into the lines
  they join) and icons, the built-in five and Iconify names
  (``logos:aws-lambda``);
- ``C4Context``, ``C4Container``, ``C4Component``, ``C4Dynamic`` and
  ``C4Deployment``, read by :mod:`.c4`.

Sequence, class, state, Gantt and the other kinds draw no architecture and
are refused by name. A Markdown file's ```` ```mermaid ```` blocks each read
as one diagram (:mod:`.sources`).
"""

from __future__ import annotations

import colorsys
import html
import re

from ..builders import metrics
from .c4 import C4_MACRO, C4Reader
from .model import Hint, Link, Shape, Sketch, clean_text, words

__all__ = ["MermaidError", "icon_hints", "read_mermaid"]


class MermaidError(ValueError):
    """The text is not a Mermaid diagram this reader draws."""


_FLOWS = {"TB": "column", "TD": "column", "BT": "column", "LR": "row", "RL": "row"}
_OTHER_KINDS = (
    "sequenceDiagram",
    "classDiagram",
    "stateDiagram",
    "erDiagram",
    "gantt",
    "pie",
    "journey",
    "gitGraph",
    "mindmap",
    "timeline",
    "quadrantChart",
    "requirementDiagram",
    "sankey",
    "xychart",
    "block",
    "packet",
    "kanban",
    "radar",
    "treemap",
    "zenuml",
)
#: Iconify prefix -> library, for ``logos:aws-lambda`` and packs registered
#: under a cloud's name (``aws:lambda``).
_ICON_PROVIDERS = (
    ("aws-", "aws"),
    ("amazon-", "aws"),
    ("google-cloud-", "gcp"),
    ("google-", "gcp"),
    ("gcp-", "gcp"),
    ("microsoft-azure", "azure"),
    ("azure-", "azure"),
    ("kubernetes", "kubernetes"),
    ("k8s-", "kubernetes"),
    ("ibm-", "ibm"),
    ("oracle-", "oracle"),
    ("digital-ocean", "digitalocean"),
    ("digitalocean", "digitalocean"),
    ("cloudflare", "cloudflare"),
    ("hetzner", "hetzner"),
    ("vmware", "vmware"),
    ("proxmox", "proxmox"),
)
_PACKS = {
    "aws": "aws",
    "azure": "azure",
    "gcp": "gcp",
    "google": "gcp",
    "k8s": "kubernetes",
    "kubernetes": "kubernetes",
    "ibm": "ibm",
    "oracle": "oracle",
}
_BUILTIN_ICONS = {
    "cloud": ("cloud", None),
    "database": ("database", None),
    "disk": ("storage", None),
    "internet": ("cloud", "internet"),
    "server": ("box", "server"),
}


def icon_hints(icon: str) -> tuple[str, list[Hint]]:
    """An icon name -> (shape family, hints): ``logos:aws-lambda`` -> ``aws`` ``lambda``."""
    icon = icon.strip().strip('"')
    if icon in _BUILTIN_ICONS:
        kind, phrase = _BUILTIN_ICONS[icon]
        return kind, [Hint(phrase=phrase, raw=icon)] if phrase else []
    pack, _, name = icon.partition(":")
    if not name:
        pack, name = "", pack
    name = re.sub(r"^fa-", "", name)
    provider = _PACKS.get(pack)
    phrase = name
    if provider:
        phrase = re.sub(r"^(?:arch-|res-|resource-|service-|aws-|amazon-|azure-|gcp-)+", "", name)
    else:
        for prefix, library in _ICON_PROVIDERS:
            if name.startswith(prefix):
                provider = library
                phrase = name[len(prefix) :]
                break
    phrase = words(re.sub(r"-icon$", "", phrase))
    kind = (
        "database"
        if phrase in {"database", "db"}
        else "actor"
        if phrase in {"user", "users"}
        else "box"
    )
    if not phrase and provider:
        # a cloud's own logo on a group: the cloud itself
        return "cloud", [Hint(provider=provider, phrase="cloud", frame=True, raw=icon)]
    return kind, [Hint(provider=provider, phrase=phrase, raw=icon)] if phrase else []


_FONT_ICON = re.compile(r"\b(?:fa[bsrl]?|fab|mdi):fa-([\w-]+)|\b(?:fa[bsrl]?|fab):([\w-]+)")


def _label(text: str) -> tuple[str, str, list[Hint]]:
    """A Mermaid label -> (caption, detail, icon hints)."""
    text = text.strip()
    if len(text) >= 2 and text[0] == text[-1] == '"':
        text = text[1:-1]
    if len(text) >= 2 and text[0] == text[-1] == "`":
        text = text[1:-1]
    hints = [
        Hint(phrase=words(a or b), raw=m.group(0))
        for m in _FONT_ICON.finditer(text)
        for a, b in [m.groups()]
    ]
    text = _FONT_ICON.sub("", text)
    text = re.sub(
        r"#(\d+|[a-zA-Z]+);",
        lambda m: html.unescape(f"&#{m.group(1)};" if m.group(1).isdigit() else f"&{m.group(1)};"),
        text,
    )
    text = re.sub(r"\*\*|__|(?<!\w)[*_](?=\S)|(?<=\S)[*_](?!\w)", "", text)
    lines = clean_text(text).splitlines()
    caption = lines[0] if lines else ""
    # each line under the caption stays a line: more than one draws a panel
    return caption, "\n".join(lines[1:]), hints


def _statements(text: str) -> list[str]:
    """Lines, split again at ``;`` outside quotes and brackets, comments gone."""
    out: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("%%"):
            continue
        current: list[str] = []
        depth = 0
        quote = False
        for char in stripped:
            if char == '"':
                quote = not quote
            elif not quote and char in "([{":
                depth += 1
            elif not quote and char in ")]}":
                depth = max(depth - 1, 0)
            if char == ";" and not quote and depth == 0:
                out.append("".join(current).strip())
                current = []
            else:
                current.append(char)
        out.append("".join(current).strip())
    return [s for s in out if s]


def _header(text: str) -> tuple[str | None, str]:
    """Front matter's title, and the text after it."""
    title = None
    match = re.match(r"\s*---\s*\n(.*?)\n\s*---\s*\n", text, re.DOTALL)
    if match:
        found = re.search(r"^\s*title\s*:\s*(.+?)\s*$", match.group(1), re.MULTILINE)
        if found:
            title = found.group(1).strip().strip("'\"")
        text = text[match.end() :]
    text = re.sub(r"%%\{.*?\}%%", "", text, flags=re.DOTALL)
    return title, text


# ------------------------------------------------------------------ flowchart
#: opener -> (closer, shape family); longest openers first.
_OPENERS = (
    ("(((", ")))", "ellipse"),
    ("([", "])", "box"),
    ("((", "))", "ellipse"),
    ("[[", "]]", "box"),
    ("[(", ")]", "database"),
    ("[/", "/]", "box"),
    ("[\\", "\\]", "box"),
    ("{{", "}}", "hexagon"),
    ("[", "]", "box"),
    ("(", ")", "box"),
    ("{", "}", "diamond"),
    (">", "]", "box"),
)
_V11_SHAPES = {
    "cyl": "database",
    "cylinder": "database",
    "db": "database",
    "database": "database",
    "lin-cyl": "storage",
    "das": "storage",
    "h-cyl": "storage",
    "disk": "storage",
    "doc": "file",
    "document": "file",
    "docs": "file",
    "documents": "file",
    "lin-doc": "file",
    "tag-doc": "file",
    "cloud": "cloud",
    "hex": "hexagon",
    "hexagon": "hexagon",
    "diam": "diamond",
    "diamond": "diamond",
    "circle": "ellipse",
    "circ": "ellipse",
    "text": "text",
    "notch-rect": "box",
    "stadium": "box",
}
#: The shapes that draw as a panel's own outline (compose.md, Panels).
_OUTLINES = {"(((": "ellipse", "((": "ellipse", "{{": "hexagon"}
_V11_OUTLINES = {
    "circle": "ellipse",
    "circ": "ellipse",
    "dbl-circ": "ellipse",
    "double-circle": "ellipse",
    "hex": "hexagon",
    "hexagon": "hexagon",
    "doc": "note",
    "document": "note",
}


def _rgb(colour: str) -> tuple[float, float, float] | None:
    """``#f96``, ``#ff9966`` -> (r, g, b) in 0..1; anything else -> None."""
    found = re.fullmatch(r"#([0-9a-fA-F]{3}|[0-9a-fA-F]{6})", colour.strip())
    if not found:
        return None
    digits = found.group(1)
    if len(digits) == 3:
        digits = "".join(d * 2 for d in digits)
    r, g, b = (int(digits[i : i + 2], 16) / 255 for i in (0, 2, 4))
    return r, g, b


def tone_of(name: str, fill: str) -> str:
    """The panel tone a source's class or fill reads as.

    A class named for a tone (``edge``, ``blockerCell``) is that tone. Else
    the fill's hue picks the tone whose outline is nearest in hue, and a grey
    the neutral one; white, or a fill that is no colour, reads as no tone.
    """
    tones = metrics.tones()
    for word in words(name).split():
        if word in tones:
            return word
    rgb = _rgb(fill)
    if rgb is None:
        return ""
    hue, lightness, saturation = colorsys.rgb_to_hls(*rgb)
    if lightness > 0.985:
        return ""  # white: the card's own ground
    if saturation < 0.12:
        return "neutral" if "neutral" in tones else ""
    best, distance = "", 2.0
    for tone_name, tone in tones.items():
        line = _rgb(tone.stroke)
        if line is None:
            continue
        their_hue, _, their_saturation = colorsys.rgb_to_hls(*line)
        if their_saturation < 0.12:
            continue
        apart = min(abs(hue - their_hue), 1 - abs(hue - their_hue))
        if apart < distance:
            best, distance = tone_name, apart
    return best


def _style(text: str) -> dict[str, str]:
    """``fill:#f9f,stroke:#333`` -> {fill: #f9f, stroke: #333}."""
    return {
        key.strip(): value.strip()
        for key, _, value in (part.partition(":") for part in text.split(","))
        if value.strip()
    }


_ARROW = re.compile(
    r"""
    (?:[A-Za-z0-9_]+@)?
    (?:
        (?P<l_open>[<ox]?)(?P<l_line>--|==|-\.)\s*(?P<l_text>[^|>\-.=\s][^|]*?)\s*
        (?P<l_close>-{2,}|={2,}|\.+-)(?P<l_head>[>ox]?)
      |
        (?P<start>[<ox]?)(?P<line>-{2,}|={2,}|-\.+-|~{3,})(?P<head>[>ox]?)
    )
    (?:\s*\|(?P<pipe>[^|]*)\|)?
""",
    re.VERBOSE,
)
_ID_STOP = re.compile(r"\s|[\[\](){}<>&;|\"@]|--|==|-\.|~~")


class _Flowchart:
    """A flowchart's nodes, links and subgraphs.

    A subgraph holds every node its body names, wherever that node was first
    declared: ``subgraph vpc`` listing ``alb`` and ``api`` holds them even
    when a link above declared them. Mermaid settles a node two subgraphs
    name at the ``end`` of each: the first subgraph to close keeps it, so an
    inner subgraph keeps its nodes from the one around it. A body's members
    are its own mentions and the ids of the subgraphs directly inside it.
    """

    def __init__(self, sketch: Sketch) -> None:
        self.sketch = sketch
        self.shapes: dict[str, Shape] = {}
        self.stack: list[str] = []
        #: The keys each open subgraph's body names, in the stack's order.
        self.members: list[list[str]] = []
        #: Keys a closed subgraph already holds.
        self.claimed: set[str] = set()
        #: classDef name -> its style; node key -> its class; node key -> its style
        self.classes: dict[str, dict[str, str]] = {}
        self.classed: dict[str, str] = {}
        self.styled: dict[str, dict[str, str]] = {}

    def node(self, key: str) -> Shape:
        if key not in self.shapes:
            shape = Shape(key=key, label=key, source=f"node {key}")
            self.shapes[key] = shape
            self.sketch.shapes.append(shape)
        if self.members and key not in self.stack and key not in self.members[-1]:
            self.members[-1].append(key)
        return self.shapes[key]

    def close(self) -> None:
        """End the innermost subgraph: it holds each member no subgraph holds yet."""
        key, members = self.stack.pop(), self.members.pop()
        for member in members:
            if member not in self.claimed:
                self.shapes[member].parent = key
                self.claimed.add(member)

    def read_node(self, text: str, pos: int) -> tuple[str | None, int]:
        match = _ID_STOP.search(text, pos)
        end = match.start() if match else len(text)
        key = text[pos:end]
        named = re.search(r":::([\w-]+)$", key)
        key = key[: named.start()] if named else key
        if not key:
            return None, pos
        if named:
            self.classed[key] = named.group(1)
        shape = self.node(key)
        pos = end
        if text.startswith("@{", pos):
            close = text.find("}", pos)
            body = text[pos + 2 : close if close >= 0 else len(text)]
            pos = close + 1 if close >= 0 else len(text)
            fields = {
                m.group(1): (m.group(3) if m.group(3) is not None else m.group(2)).strip()
                for m in re.finditer(r'(\w+)\s*:\s*("([^"]*)"|[^,}]+)', body)
            }
            if "label" in fields:
                shape.label, shape.detail, hints = _label(fields["label"])
                shape.hints += hints
            if fields.get("shape") in _V11_SHAPES:
                shape.kind = _V11_SHAPES[fields["shape"]]  # type: ignore[assignment]
            if fields.get("shape") in _V11_OUTLINES:
                shape.outline = _V11_OUTLINES[fields["shape"]]  # type: ignore[assignment]
            if fields.get("icon"):
                kind, hints = icon_hints(fields["icon"])
                shape.hints += hints
                if shape.kind == "box" and kind != "box":
                    shape.kind = kind  # type: ignore[assignment]
            return key, pos
        for opener, closer, kind in _OPENERS:
            if not text.startswith(opener, pos):
                continue
            start = pos + len(opener)
            body_start = start
            while body_start < len(text) and text[body_start] == " ":
                body_start += 1
            if body_start < len(text) and text[body_start] == '"':
                quote_end = text.find('"', body_start + 1)
                close = text.find(closer, quote_end + 1 if quote_end >= 0 else body_start)
            elif len(closer) == 1:
                close, depth = -1, 0
                for index in range(start, len(text)):
                    char = text[index]
                    if char == opener[-1] and opener[-1] != closer:
                        depth += 1
                    elif char == closer:
                        if depth == 0:
                            close = index
                            break
                        depth -= 1
            else:
                close = text.find(closer, start)
                if closer == "/]" and close < 0:
                    close = text.find("\\]", start)
            if close < 0:
                self.sketch.notes.append(f"node {key}: its {opener!r} is never closed")
                return key, len(text)
            caption, detail, hints = _label(text[start:close])
            shape.label, shape.detail = caption or key, detail
            shape.hints += hints
            if shape.kind == "box":
                shape.kind = kind  # type: ignore[assignment]
            if opener in _OUTLINES:
                shape.outline = _OUTLINES[opener]  # type: ignore[assignment]
            end = close + len(closer)
            styled = re.match(r":::([\w-]+)", text[end:])
            if styled:
                self.classed[key] = styled.group(1)
            return key, end + (styled.end() if styled else 0)
        return key, pos

    def read_group(self, text: str, pos: int) -> tuple[list[str], int]:
        keys: list[str] = []
        while True:
            while pos < len(text) and text[pos] == " ":
                pos += 1
            key, pos = self.read_node(text, pos)
            if key is None:
                break
            keys.append(key)
            rest = text[pos:].lstrip(" ")
            if not rest.startswith("&"):
                break
            pos = len(text) - len(rest) + 1
        return keys, pos

    def chain(self, text: str) -> None:
        sources, pos = self.read_group(text, 0)
        if not sources:
            self.sketch.notes.append(f"passed over {text!r}")
            return
        while pos < len(text):
            while pos < len(text) and text[pos] == " ":
                pos += 1
            if pos >= len(text):
                break
            arrow = _ARROW.match(text, pos)
            if not arrow:
                self.sketch.notes.append(f"passed over {text[pos:]!r} in {text!r}")
                return
            pos = arrow.end()
            targets, pos = self.read_group(text, pos)
            if not targets:
                self.sketch.notes.append(f"a link in {text!r} has no far end")
                return
            self.links(arrow, sources, targets, text)
            sources = targets

    def links(
        self, arrow: re.Match[str], sources: list[str], targets: list[str], text: str
    ) -> None:
        if arrow.group("l_line"):
            line, start, head = arrow.group("l_line"), arrow.group("l_open"), arrow.group("l_head")
            label = arrow.group("l_text") or ""
        else:
            line, start, head = arrow.group("line"), arrow.group("start"), arrow.group("head")
            label = ""
        if line.startswith("~"):
            return  # an invisible link only spaces the picture
        if arrow.group("pipe") is not None:
            label = arrow.group("pipe")
        caption, detail, _ = _label(label)
        label = " ".join(t for t in (caption, detail) if t)
        backwards = start == "<" and not head
        direction = "both" if start and head else "forward" if start or head else "none"
        for source in sources:
            for target in targets:
                a, b = (target, source) if backwards else (source, target)
                self.sketch.links.append(
                    Link(
                        source=a,
                        target=b,
                        label=label,
                        dashed="." in line,
                        direction=direction,
                        origin=text,
                    )
                )

    def subgraph(self, rest: str) -> None:
        rest = rest.strip()
        match = re.match(r'^([^\s\["]+)\s*\[(.*)\]\s*$', rest)
        if match:
            key, (title, _detail, _hints) = match.group(1), _label(match.group(2))
        elif rest.startswith('"'):
            title = _label(rest)[0]
            key = title
        else:
            key = title = rest or f"subgraph {len(self.stack) + 1}"
        shape = self.node(key)
        shape.label = title or key
        shape.container = True
        shape.source = f"subgraph {key}"
        self.stack.append(key)
        self.members.append([])

    def read(self, statements: list[str]) -> None:
        for statement in statements:
            head = statement.split(None, 1)
            word = head[0]
            if word == "subgraph":
                self.subgraph(head[1] if len(head) > 1 else "")
            elif word == "end" and len(head) == 1:
                if self.stack:
                    self.close()
            elif word == "direction" and len(head) > 1:
                flow = _FLOWS.get(head[1].strip().upper())
                if self.stack and flow:
                    self.shapes[self.stack[-1]].flow = flow  # type: ignore[assignment]
            elif word in {
                "classDef",
                "class",
                "style",
                "linkStyle",
                "click",
                "accTitle:",
                "accDescr:",
                "accTitle",
                "accDescr",
            }:
                if word == "click" and len(head) > 1:
                    link = re.search(r'"(https?://[^"]+)"', head[1])
                    key = head[1].split()[0]
                    if link and key in self.shapes:
                        self.shapes[key].rows.append(("Link", link.group(1)))
                elif word in {"classDef", "class", "style"} and len(head) > 1:
                    self.styles(word, head[1])
                continue
            else:
                self.chain(statement)
        while self.stack:
            self.close()  # a subgraph left open still holds what it named
        self.tone()

    def styles(self, word: str, rest: str) -> None:
        """``classDef a,b fill:...``, ``class x,y a`` and ``style x fill:...``."""
        names, _, tail = rest.strip().partition(" ")
        if word == "classDef":
            for name in names.split(","):
                self.classes[name] = _style(tail)
        elif word == "class":
            for key in names.split(","):
                self.classed[key] = tail.strip()
        else:
            self.styled[names] = _style(tail)

    def tone(self) -> None:
        """Each node's fill as a panel tone, and what each tone means: the
        names of the classes that fill with it, for the legend."""
        meanings: dict[str, list[str]] = {}
        for key, shape in self.shapes.items():
            if shape.container:
                continue
            name = self.classed.get(key, "")
            style = {
                **self.classes.get("default", {}),
                **self.classes.get(name, {}),
                **self.styled.get(key, {}),
            }
            if not name and key not in self.styled:
                continue
            tone = tone_of(name, style.get("fill", ""))
            if not tone:
                continue
            shape.tone = tone
            meaning = words(name) if name else ""
            if meaning and meaning not in meanings.setdefault(tone, []):
                meanings[tone].append(meaning)
        for tone, said in meanings.items():
            if said:
                self.sketch.tones[tone] = " / ".join(said)


def _flowchart(statements: list[str], sketch: Sketch) -> None:
    first = statements[0].split()
    if len(first) > 1:
        sketch.flow = _FLOWS.get(first[1].upper())  # type: ignore[assignment]
    _Flowchart(sketch).read(statements[1:])


# --------------------------------------------------------------- architecture
_ARCH_ITEM = re.compile(
    r"^(?P<what>group|service)\s+(?P<key>[\w-]+)\s*(?:\((?P<icon>[^)]*)\))?\s*"
    r"(?:\[(?P<title>[^\]]*)\])?\s*(?:in\s+(?P<parent>[\w-]+))?\s*$"
)
_ARCH_JUNCTION = re.compile(r"^junction\s+(?P<key>[\w-]+)\s*(?:in\s+(?P<parent>[\w-]+))?\s*$")
_ARCH_EDGE = re.compile(
    r"^(?P<a>[\w-]+)(?:\{group\})?\s*(?::\s*[TBLR])?\s*"
    r"(?P<l><)?-(?:\[(?P<label>[^\]]*)\])?-(?P<r>>)?\s*"
    r"(?:[TBLR]\s*:)?\s*(?P<b>[\w-]+)(?:\{group\})?\s*$"
)


def _architecture(statements: list[str], sketch: Sketch) -> None:
    junctions: set[str] = set()
    for statement in statements[1:]:
        if statement.startswith("title "):
            sketch.title = statement[6:].strip()
            continue
        item = _ARCH_ITEM.match(statement)
        if item:
            key = item.group("key")
            shape = Shape(
                key=key,
                label=_label(item.group("title") or key)[0],
                parent=item.group("parent"),
                container=item.group("what") == "group",
                source=f"{item.group('what')} {key}",
            )
            if item.group("icon"):
                kind, hints = icon_hints(item.group("icon"))
                shape.hints = hints
                if shape.container:
                    for hint in hints:
                        hint.frame = True
                else:
                    shape.kind = kind  # type: ignore[assignment]
            sketch.shapes.append(shape)
            continue
        junction = _ARCH_JUNCTION.match(statement)
        if junction:
            junctions.add(junction.group("key"))
            continue
        edge = _ARCH_EDGE.match(statement)
        if edge:
            left, right = bool(edge.group("l")), bool(edge.group("r"))
            a, b = edge.group("a"), edge.group("b")
            if left and not right:
                a, b = b, a
            sketch.links.append(
                Link(
                    source=a,
                    target=b,
                    label=_label(edge.group("label") or "")[0],
                    direction="both" if left and right else "forward" if left or right else "none",
                    origin=statement,
                )
            )
            continue
        sketch.notes.append(f"passed over {statement!r}")
    if junctions:
        _fold_junctions(sketch, junctions)


def _fold_junctions(sketch: Sketch, junctions: set[str]) -> None:
    """A junction only joins lines: each line into it meets each line out of it."""
    # junctions joined to junctions are one junction
    owner = {key: key for key in junctions}

    def find(key: str) -> str:
        while owner[key] != key:
            key = owner[key]
        return key

    kept: list[Link] = []
    for link in sketch.links:
        if link.source in junctions and link.target in junctions:
            owner[find(link.source)] = find(link.target)
        else:
            kept.append(link)
    into: dict[str, list[Link]] = {}
    out_of: dict[str, list[Link]] = {}
    plain: list[Link] = []
    for link in kept:
        if link.target in junctions:
            into.setdefault(find(link.target), []).append(link)
        elif link.source in junctions:
            out_of.setdefault(find(link.source), []).append(link)
        else:
            plain.append(link)
    for junction in {find(key) for key in junctions}:
        ins, outs = into.get(junction, []), out_of.get(junction, [])
        if not ins or not outs:
            # every line undirected: the first end meets each other end
            ends = [link.source for link in ins] + [link.target for link in outs]
            ins = [Link(source=ends[0], target=ends[0])] if ends else []
            outs = [Link(source=ends[0], target=end, direction="none") for end in ends[1:]]
        for a in ins:
            for b in outs:
                if a.source != b.target:
                    plain.append(
                        Link(
                            source=a.source,
                            target=b.target,
                            label=b.label or a.label,
                            direction=b.direction if b.direction != "forward" else a.direction,
                            dashed=a.dashed or b.dashed,
                            origin=f"through junction {junction}",
                        )
                    )
    sketch.links = plain


# ------------------------------------------------------------------------ C4
def _c4(statements: list[str], sketch: Sketch) -> None:
    reader = C4Reader(sketch)
    stack: list[str | None] = []
    for number, statement in enumerate(statements[1:], start=2):
        if statement.startswith("title "):
            sketch.title = statement[6:].strip()
            continue
        if statement == "}":
            if stack:
                stack.pop()
            continue
        if statement == "{":
            continue
        match = C4_MACRO.match(statement)
        if not match or not reader.handles(match.group("name")):
            sketch.notes.append(f"passed over {statement!r}")
            continue
        parent = next((key for key in reversed(stack) if key), None)
        shape = reader.statement(
            match.group("name"), match.group("args"), parent=parent, where=f"statement {number}"
        )
        if match.group("open"):
            stack.append(shape.key if shape else None)


# ---------------------------------------------------------------------- entry
def read_mermaid(text: str, *, name: str, origin: str | None = None) -> Sketch:
    """One Mermaid diagram."""
    title, body = _header(text)
    statements = _statements(body)
    if not statements:
        raise MermaidError(f"{name}: no diagram in it")
    kind = statements[0].split()[0]
    sketch = Sketch(title=title or name, origin=origin or name, format="mermaid")
    if kind in {"flowchart", "graph", "flowchart-elk"}:
        _flowchart(statements, sketch)
    elif kind in {"architecture-beta", "architecture"}:
        _architecture(statements, sketch)
    elif kind in {"C4Context", "C4Container", "C4Component", "C4Dynamic", "C4Deployment"}:
        _c4(statements, sketch)
    elif kind.startswith(_OTHER_KINDS):
        raise MermaidError(
            f"{name}: a Mermaid {kind} draws no architecture; flowchart, graph, "
            "architecture-beta and the C4 diagrams do"
        )
    else:
        raise MermaidError(f"{name}: {kind!r} is not a Mermaid diagram this reader knows")
    return sketch
