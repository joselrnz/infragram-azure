"""Reading Terraform's HCL: the blocks and attributes of a configuration.

Enough of HCL's native syntax to read a configuration's structure the way
Terraform does: top-level blocks and their labels, bodies of attributes and
nested blocks, one-line blocks, the three kinds of comment, heredocs, and
string templates with interpolations nested to any depth. An attribute's
value is kept as its source text (:class:`Expr`); :func:`evaluate` reads what
of it is literal, ``for`` expressions included, and :func:`references` the
addresses it names. Nothing is
run, and an expression the reader cannot evaluate is :data:`UNKNOWN` rather
than an error: a configuration is read for its shape, and an exotic value
must not cost the whole file.

The JSON syntax (``*.tf.json``) is read by :func:`parse_json` into the same
shape.
"""

from __future__ import annotations

import bisect
import ipaddress
import itertools
import json
import re
from collections.abc import Callable, Iterable, Mapping
from typing import Any

from pydantic import ConfigDict, Field

from .model import Record

__all__ = [
    "UNKNOWN",
    "Body",
    "Expr",
    "HclBlock",
    "HclError",
    "convert",
    "element_calls",
    "evaluate",
    "is_known",
    "iterators_read",
    "object_entries",
    "parse",
    "type_of",
    "parse_json",
    "references",
    "symbols",
]


class HclError(ValueError):
    """A file the reader cannot follow; the message names the line."""


class _Unknown:
    """A value the reader cannot know without running Terraform."""

    def __repr__(self) -> str:
        return "UNKNOWN"

    def __bool__(self) -> bool:
        return False


#: What :func:`evaluate` returns for anything it cannot read.
UNKNOWN: Any = _Unknown()


class Expr(Record):
    """An attribute's value as written, and the line it starts on."""

    model_config = ConfigDict(frozen=True)

    text: str
    line: int = 0


class HclBlock(Record):
    type: str
    labels: tuple[str, ...]
    body: Body
    line: int = 0


class Body(Record):
    attributes: dict[str, Expr] = Field(default_factory=dict)
    blocks: list[HclBlock] = Field(default_factory=list)

    def blocks_of(self, kind: str) -> list[HclBlock]:
        return [block for block in self.blocks if block.type == kind]


_IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_-]*")
_HEREDOC = re.compile(r"<<(-?)([A-Za-z_][A-Za-z0-9_-]*)[ \t]*\r?\n")


class _Reader:
    """The native syntax, character by character."""

    def __init__(self, text: str, name: str) -> None:
        self.text = text
        self.name = name
        self.pos = 0
        self.newlines = [i for i, ch in enumerate(text) if ch == "\n"]

    # ---------------------------------------------------------------- basics
    def line(self, pos: int | None = None) -> int:
        return bisect.bisect_left(self.newlines, self.pos if pos is None else pos) + 1

    def fail(self, message: str) -> HclError:
        return HclError(f"{self.name}:{self.line()}: {message}")

    def peek(self, offset: int = 0) -> str:
        index = self.pos + offset
        return self.text[index] if index < len(self.text) else ""

    def at(self, token: str) -> bool:
        return self.text.startswith(token, self.pos)

    def skip_line(self) -> None:
        end = self.text.find("\n", self.pos)
        self.pos = len(self.text) if end < 0 else end

    def skip_block_comment(self) -> None:
        end = self.text.find("*/", self.pos + 2)
        if end < 0:
            raise self.fail("a /* comment is never closed")
        self.pos = end + 2

    def skip_space(self, newlines: bool) -> None:
        while self.pos < len(self.text):
            ch = self.text[self.pos]
            if ch in " \t\r\ufeff" or (newlines and ch == "\n"):
                self.pos += 1
            elif ch == "#" or self.at("//"):
                self.skip_line()
            elif self.at("/*"):
                self.skip_block_comment()
            else:
                return

    # ---------------------------------------------------------------- strings
    def skip_string(self) -> None:
        """Past a quoted template, its interpolations included."""
        self.pos += 1
        while self.pos < len(self.text):
            ch = self.text[self.pos]
            if ch == "\\":
                self.pos += 2
            elif ch == '"':
                self.pos += 1
                return
            elif ch in "$%" and self.peek(1) == ch and self.peek(2) == "{":
                self.pos += 3
            elif ch in "$%" and self.peek(1) == "{":
                self.pos += 2
                self.skip_interpolation()
            elif ch == "\n":
                raise self.fail("a quoted string runs past the end of its line")
            else:
                self.pos += 1
        raise self.fail("a quoted string is never closed")

    def skip_interpolation(self) -> None:
        depth = 1
        while self.pos < len(self.text):
            ch = self.text[self.pos]
            if ch == '"':
                self.skip_string()
                continue
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    self.pos += 1
                    return
            self.pos += 1
        raise self.fail("an interpolation is never closed")

    def skip_heredoc(self) -> bool:
        match = _HEREDOC.match(self.text, self.pos)
        if match is None:
            return False
        marker = match.group(2)
        self.pos = match.end()
        while self.pos < len(self.text):
            end = self.text.find("\n", self.pos)
            line = self.text[self.pos : len(self.text) if end < 0 else end]
            if line.strip() == marker:
                self.pos = len(self.text) if end < 0 else end
                return True
            self.pos = len(self.text) if end < 0 else end + 1
        raise self.fail(f"the heredoc {marker} is never closed")

    def quoted(self) -> str:
        start = self.pos
        self.skip_string()
        return _decode(self.text[start + 1 : self.pos - 1])

    # ---------------------------------------------------------------- structure
    def identifier(self) -> str:
        match = _IDENT.match(self.text, self.pos)
        if match is None:
            raise self.fail(f"expected a name, found {self.peek()!r}")
        self.pos = match.end()
        return match.group(0)

    def expression(self) -> Expr:
        """The text of one attribute's value: up to the end of its line, or
        the brace that closes a one-line block, outside brackets."""
        self.skip_space(newlines=False)
        start, line, depth = self.pos, self.line(), 0
        while self.pos < len(self.text):
            ch = self.text[self.pos]
            if ch in "([{":
                depth += 1
            elif ch in ")]}":
                if depth == 0:
                    break
                depth -= 1
            elif ch == '"':
                self.skip_string()
                continue
            elif ch == "<" and self.at("<<") and self.skip_heredoc():
                continue
            elif ch == "#" or self.at("//"):
                if depth == 0:
                    break
                self.skip_line()
                continue
            elif self.at("/*"):
                self.skip_block_comment()
                continue
            elif ch == "\n" and depth == 0:
                break
            self.pos += 1
        text = self.text[start : self.pos].strip()
        if not text:
            raise self.fail("an attribute with no value")
        return Expr(text, line)

    def body(self, closing: str | None) -> Body:
        body = Body()
        while True:
            self.skip_space(newlines=True)
            if self.pos >= len(self.text):
                if closing:
                    raise self.fail("a block is never closed")
                return body
            ch = self.peek()
            if closing and ch == closing:
                self.pos += 1
                return body
            if ch == ",":
                self.pos += 1
                continue
            line = self.line()
            name = self.quoted() if ch == '"' else self.identifier()
            self.skip_space(newlines=False)
            if self.peek() == "=" and self.peek(1) != "=":
                self.pos += 1
                body.attributes[name] = self.expression()
                continue
            labels: list[str] = []
            while True:
                self.skip_space(newlines=False)
                ch = self.peek()
                if ch == '"':
                    labels.append(self.quoted())
                elif ch == "{":
                    self.pos += 1
                    body.blocks.append(HclBlock(name, tuple(labels), self.body("}"), line))
                    break
                elif ch and _IDENT.match(ch):
                    labels.append(self.identifier())
                else:
                    raise self.fail(f"expected '=' or '{{' after {name!r}")


def parse(text: str, name: str = "<hcl>") -> Body:
    """A file's body: its attributes (a ``.tfvars`` file) and blocks."""
    return _Reader(text, name).body(None)


#: How many labels each top-level block type has, for the JSON syntax.
_JSON_LABELS = {
    "resource": 2,
    "data": 2,
    "variable": 1,
    "output": 1,
    "module": 1,
    "provider": 1,
    "locals": 0,
    "terraform": 0,
    "moved": 0,
    "import": 0,
    "check": 1,
    "removed": 0,
}


def parse_json(text: str, name: str = "<json>") -> Body:
    """A ``*.tf.json`` file in the shape :func:`parse` gives: a value is the
    JSON text of what it holds, which :func:`evaluate` reads as HCL."""
    try:
        document = json.loads(text)
    except json.JSONDecodeError as error:
        raise HclError(f"{name}:{error.lineno}: {error.msg}") from error
    if not isinstance(document, dict):
        raise HclError(f"{name}: a Terraform JSON file holds an object")
    body = Body()

    def blocks(kind: str, value: Any, depth: int, labels: tuple[str, ...]) -> None:
        if depth == 0:
            items = value if isinstance(value, list) else [value]
            for item in items:
                if isinstance(item, dict):
                    body.blocks.append(HclBlock(kind, labels, _json_body(item)))
            return
        if isinstance(value, dict):
            for label, inner in value.items():
                blocks(kind, inner, depth - 1, (*labels, label))
        elif isinstance(value, list):
            for item in value:
                blocks(kind, item, depth, labels)

    for kind, value in document.items():
        if kind == "//":
            continue
        if kind not in _JSON_LABELS:
            body.attributes[kind] = Expr(json.dumps(value))
            continue
        blocks(kind, value, _JSON_LABELS[kind], ())
    return body


def _json_body(value: dict[str, Any]) -> Body:
    return Body({key: Expr(json.dumps(item)) for key, item in value.items() if key != "//"})


def _decode(text: str) -> str:
    """A quoted string's characters, its escapes undone; interpolations stay."""
    out, i = [], 0
    while i < len(text):
        ch = text[i]
        if ch == "\\" and i + 1 < len(text):
            nxt = text[i + 1]
            simple = {"n": "\n", "t": "\t", "r": "\r", '"': '"', "\\": "\\"}
            if nxt in simple:
                out.append(simple[nxt])
                i += 2
                continue
            if nxt == "u" and i + 6 <= len(text):
                out.append(chr(int(text[i + 2 : i + 6], 16)))
                i += 6
                continue
            if nxt == "U" and i + 10 <= len(text):
                out.append(chr(int(text[i + 2 : i + 10], 16)))
                i += 10
                continue
        out.append(ch)
        i += 1
    return "".join(out)


# ==================================================================== values
class _Syntax(Exception):
    """An expression the evaluator does not read: its value is UNKNOWN."""


_TOKEN = re.compile(
    r"""
    (?P<space>[ \t\r\n]+|\#[^\n]*|//[^\n]*|/\*.*?\*/)
  | (?P<number>\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)
  | (?P<heredoc><<-?[A-Za-z_][A-Za-z0-9_-]*[ \t]*\r?\n)
  | (?P<ident>[A-Za-z_][A-Za-z0-9_-]*)
  | (?P<op>==|!=|<=|>=|&&|\|\||=>|\.\.\.|\[\*\]|\.\*|[-+*/%<>!?:=.,(){}\[\]])
  | (?P<quote>")
""",
    re.VERBOSE | re.DOTALL,
)


class _Tokens:
    def __init__(self, text: str) -> None:
        self.text = text
        self.pos = 0

    def skip(self) -> None:
        while True:
            match = _TOKEN.match(self.text, self.pos)
            if match is None or match.lastgroup != "space":
                return
            self.pos = match.end()

    def peek(self) -> tuple[str, str]:
        self.skip()
        if self.pos >= len(self.text):
            return ("end", "")
        match = _TOKEN.match(self.text, self.pos)
        if match is None:
            raise _Syntax(self.text[self.pos : self.pos + 10])
        return (match.lastgroup or "", match.group(0))

    def take(self, value: str | None = None) -> tuple[str, str]:
        kind, text = self.peek()
        if value is not None and text != value:
            raise _Syntax(f"expected {value!r}, found {text!r}")
        if kind == "quote":
            return ("string", self.string())
        if kind == "heredoc":
            return ("string", self.heredoc())
        self.pos += len(text)
        return (kind, text)

    def string(self) -> str:
        """The raw body of a quoted template, interpolations as written."""
        reader = _Reader(self.text, "<expr>")
        reader.pos = self.pos
        try:
            reader.skip_string()
        except HclError as error:
            raise _Syntax(str(error)) from error
        raw = self.text[self.pos + 1 : reader.pos - 1]
        self.pos = reader.pos
        return raw

    def heredoc(self) -> str:
        match = _HEREDOC.match(self.text, self.pos)
        if match is None:
            raise _Syntax("heredoc")
        strip, marker = match.group(1) == "-", match.group(2)
        lines, pos = [], match.end()
        while pos <= len(self.text):
            end = self.text.find("\n", pos)
            line = self.text[pos : len(self.text) if end < 0 else end]
            if line.strip() == marker:
                self.pos = len(self.text) if end < 0 else end
                break
            lines.append(line.rstrip("\r"))
            if end < 0:
                raise _Syntax("heredoc")
            pos = end + 1
        if strip:
            indent = min((len(x) - len(x.lstrip()) for x in lines if x.strip()), default=0)
            lines = [x[indent:] for x in lines]
        return "\n".join(lines) + "\n"


class _Evaluator:
    def __init__(
        self, scope: Mapping[str, Any], functions: Mapping[str, Callable[..., Any]]
    ) -> None:
        self.scope = scope
        self.functions = functions

    def run(self, text: str) -> Any:
        tokens = _Tokens(text)
        value = self.expression(tokens)
        if tokens.peek()[0] != "end":
            raise _Syntax(f"trailing {tokens.peek()[1]!r}")
        return value

    # precedence climbing, lowest first
    def expression(self, t: _Tokens) -> Any:
        condition = self.binary(t, 0)
        if t.peek()[1] == "?":
            t.take("?")
            yes = self.expression(t)
            t.take(":")
            no = self.expression(t)
            if condition is UNKNOWN:
                return UNKNOWN
            return yes if condition else no
        return condition

    _LEVELS = (("||",), ("&&",), ("==", "!="), ("<", ">", "<=", ">="), ("+", "-"), ("*", "/", "%"))

    def binary(self, t: _Tokens, level: int) -> Any:
        if level == len(self._LEVELS):
            return self.unary(t)
        left = self.binary(t, level + 1)
        while t.peek()[0] == "op" and t.peek()[1] in self._LEVELS[level]:
            op = t.take()[1]
            right = self.binary(t, level + 1)
            left = _apply(op, left, right)
        return left

    def unary(self, t: _Tokens) -> Any:
        if t.peek()[1] in ("!", "-"):
            op = t.take()[1]
            value = self.unary(t)
            if value is UNKNOWN:
                return UNKNOWN
            return (not value) if op == "!" else -value
        return self.postfix(t, self.primary(t))

    def postfix(self, t: _Tokens, value: Any) -> Any:
        while True:
            kind, text = t.peek()
            if text == ".":
                t.take(".")
                kind, name = t.take()
                if kind == "number":
                    value = _index(value, int(name))
                elif kind == "ident":
                    value = _attribute(value, name)
                else:
                    raise _Syntax("attribute")
            elif text == "[":
                t.take("[")
                key = self.expression(t)
                t.take("]")
                value = _index(value, key)
            elif text in ("[*]", ".*"):
                t.take()
                value = UNKNOWN
                # a splat's remaining attribute steps say nothing we can read
                while t.peek()[1] == ".":
                    t.take(".")
                    t.take()
            else:
                return value

    def primary(self, t: _Tokens) -> Any:
        kind, text = t.peek()
        if kind == "number":
            t.take()
            return float(text) if any(c in text for c in ".eE") else int(text)
        if kind in ("quote", "heredoc"):
            return self.template(t.take()[1])
        if text == "(":
            t.take("(")
            value = self.expression(t)
            t.take(")")
            return value
        if text == "[":
            return self.sequence(t)
        if text == "{":
            return self.mapping(t)
        if kind == "ident":
            t.take()
            if text in ("true", "false"):
                return text == "true"
            if text == "null":
                return None
            if t.peek()[1] == "(":
                return self.call(t, text)
            return self.variable(text)
        raise _Syntax(f"unexpected {text!r}")

    def variable(self, name: str) -> Any:
        if name in self.scope:
            return self.scope[name]
        return UNKNOWN

    def sequence(self, t: _Tokens) -> Any:
        t.take("[")
        if t.peek() == ("ident", "for"):
            return self.comprehension(t, "]")
        items: list[Any] = []
        while t.peek()[1] != "]":
            items.append(self.expression(t))
            if t.peek()[1] == ",":
                t.take(",")
            elif t.peek()[1] != "]":
                raise _Syntax("list")
        t.take("]")
        return items

    def mapping(self, t: _Tokens) -> Any:
        t.take("{")
        if t.peek() == ("ident", "for"):
            return self.comprehension(t, "}")
        out: dict[str, Any] = {}
        unknown = False
        while t.peek()[1] != "}":
            kind, text = t.peek()
            if kind == "ident":
                # a bare key is the key's name, not a variable
                t.take()
                key: Any = text
                if t.peek()[1] not in ("=", ":"):
                    key = self.postfix(t, self.variable(text))
            else:
                key = self.expression(t)
            if t.peek()[1] not in ("=", ":"):
                raise _Syntax("object")
            t.take()
            value = self.expression(t)
            if key is UNKNOWN or not isinstance(key, (str, int, float, bool)):
                unknown = True
            else:
                out[str(key).lower() if isinstance(key, bool) else str(key)] = value
            if t.peek()[1] == ",":
                t.take(",")
        t.take("}")
        return UNKNOWN if unknown else out

    def comprehension(self, t: _Tokens, closing: str) -> Any:
        """``[for i, v in xs : body if cond]``, ``{for k, v in m : key => value... if cond}``.

        The parts are read once to find where each ends, then evaluated per
        element with the names bound: a list's index and value, a map's key
        and value in the order of its keys. A key the reader cannot know, or
        one given twice without ``...``, makes the whole map unknown."""
        t.take("for")
        names = [t.take()[1]]
        if t.peek()[1] == ",":
            t.take(",")
            names.append(t.take()[1])
        if t.take()[1] != "in":
            raise _Syntax("for")
        collection = self.expression(t)
        t.take(":")
        unbound = _Evaluator({**self.scope, **dict.fromkeys(names, UNKNOWN)}, self.functions)
        parts: dict[str, str] = {}

        def part(label: str) -> None:
            t.peek()
            start = t.pos
            unbound.expression(t)
            parts[label] = t.text[start : t.pos]

        part("body")
        grouped = False
        if closing == "}":
            t.take("=>")
            part("value")
            if t.peek()[1] == "...":
                t.take("...")
                grouped = True
        if t.peek() == ("ident", "if"):
            t.take()
            part("if")
        t.take(closing)
        if isinstance(collection, dict):
            items = [(key, collection[key]) for key in sorted(collection)]
        elif isinstance(collection, list):
            items = list(enumerate(collection))
        else:
            return UNKNOWN
        listed: list[Any] = []
        mapped: dict[str, Any] = {}
        for key, value in items:
            bound = {names[0]: value} if len(names) == 1 else {names[0]: key, names[1]: value}
            inner = _Evaluator({**self.scope, **bound}, self.functions)
            if "if" in parts:
                keep = inner.run(parts["if"])
                if keep is UNKNOWN:
                    return UNKNOWN
                if not keep:
                    continue
            if closing == "]":
                listed.append(inner.run(parts["body"]))
                continue
            name = inner.run(parts["body"])
            if name is UNKNOWN or name is None or isinstance(name, (list, dict)):
                return UNKNOWN
            name = _text(name)
            if grouped:
                mapped.setdefault(name, []).append(inner.run(parts["value"]))
            elif name in mapped:
                return UNKNOWN
            else:
                mapped[name] = inner.run(parts["value"])
        return listed if closing == "]" else mapped

    def call(self, t: _Tokens, name: str) -> Any:
        t.take("(")
        args: list[Any] = []
        expand = False
        while t.peek()[1] != ")":
            args.append(self.expression(t))
            if t.peek()[1] == "...":
                t.take("...")
                expand = True
            if t.peek()[1] == ",":
                t.take(",")
        t.take(")")
        if expand and args and isinstance(args[-1], list):
            args = [*args[:-1], *args[-1]]
        elif expand:
            return UNKNOWN
        function = self.functions.get(name)
        if function is None:
            return UNKNOWN
        # a function that rearranges values keeps those it cannot know; any
        # other needs every value known
        known = (lambda arg: arg is not UNKNOWN) if name in _STRUCTURAL else is_known
        if name != "try" and not all(known(arg) for arg in args):
            return UNKNOWN
        try:
            return function(*args)
        except Exception:  # noqa: BLE001 - a function Terraform would reject is unknown here
            return UNKNOWN

    def template(self, raw: str) -> Any:
        """A string template: its interpolations filled, UNKNOWN if one cannot be."""
        if "%{" in raw.replace("%%{", ""):
            return UNKNOWN
        out: list[str] = []
        literal: list[str] = []
        i = 0
        while i < len(raw):
            if raw.startswith(("$${", "%%{"), i):
                literal.append(raw[i + 1 : i + 3])
                i += 3
                continue
            if raw.startswith("${", i):
                reader = _Reader(raw, "<template>")
                reader.pos = i + 2
                try:
                    reader.skip_interpolation()
                except HclError as error:
                    raise _Syntax(str(error)) from error
                inner = raw[i + 2 : reader.pos - 1].strip()
                value = self.run(inner.removeprefix("~").removesuffix("~").strip())
                if value is UNKNOWN or isinstance(value, (list, dict)):
                    return UNKNOWN
                out += [_decode("".join(literal)), _text(value)]
                literal = []
                i = reader.pos
                continue
            step = 2 if raw[i] == "\\" else 1
            literal.append(raw[i : i + step])
            i += step
        out.append(_decode("".join(literal)))
        return "".join(out)


def is_known(value: Any) -> bool:
    """Whether no part of ``value`` is :data:`UNKNOWN`."""
    return not _holds_unknown(value)


def _holds_unknown(value: Any) -> bool:
    if value is UNKNOWN:
        return True
    if isinstance(value, list):
        return any(_holds_unknown(item) for item in value)
    if isinstance(value, dict):
        return any(_holds_unknown(item) for item in value.values())
    return False


def _text(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return "" if value is None else str(value)


def _apply(op: str, left: Any, right: Any) -> Any:
    if left is UNKNOWN or right is UNKNOWN:
        if op == "&&" and (left is False or right is False):
            return False
        if op == "||" and (left is True or right is True):
            return True
        return UNKNOWN
    try:
        if op == "||":
            return bool(left) or bool(right)
        if op == "&&":
            return bool(left) and bool(right)
        if op == "==":
            return left == right
        if op == "!=":
            return left != right
        numbers = {
            "<": lambda a, b: a < b,
            ">": lambda a, b: a > b,
            "<=": lambda a, b: a <= b,
            ">=": lambda a, b: a >= b,
            "+": lambda a, b: a + b,
            "-": lambda a, b: a - b,
            "*": lambda a, b: a * b,
            "/": lambda a, b: a / b,
            "%": lambda a, b: a % b,
        }
        a, b = _number(left), _number(right)
        result = numbers[op](a, b)
        return (
            int(result)
            if isinstance(result, float) and result.is_integer() and op != "/"
            else result
        )
    except (TypeError, ValueError, ZeroDivisionError, KeyError):
        return UNKNOWN


def _number(value: Any) -> int | float:
    if isinstance(value, bool):
        raise TypeError("a bool is not a number")
    if isinstance(value, (int, float)):
        return value
    return float(value) if "." in str(value) else int(str(value))


def _attribute(value: Any, name: str) -> Any:
    if isinstance(value, dict):
        return value.get(name, UNKNOWN)
    return UNKNOWN


def _index(value: Any, key: Any) -> Any:
    if value is UNKNOWN or key is UNKNOWN:
        return UNKNOWN
    if isinstance(value, list):
        try:
            return value[int(key)]
        except (ValueError, IndexError, TypeError):
            return UNKNOWN
    if isinstance(value, dict):
        return value.get(_text(key), UNKNOWN)
    return UNKNOWN


# ------------------------------------------------------------ functions
def _format(spec: str, *args: Any) -> str:
    values = iter(args)

    def one(match: re.Match[str]) -> str:
        if match.group(0) == "%%":
            return "%"
        flags, verb, value = match.group(1), match.group(2), next(values)
        if verb == "q":
            return json.dumps(_text(value))
        if verb in "dfeEgGxXob":
            return ("%" + flags + verb) % _number(value)
        return ("%" + flags + "s") % _text(value)

    return re.sub(r"%%|%([-+ #0]*\d*(?:\.\d+)?)([a-zA-Z])", one, spec)


def _cidrsubnet(prefix: str, newbits: int, netnum: int) -> str:
    network = ipaddress.ip_network(prefix, strict=False)
    return str(list(network.subnets(prefixlen_diff=int(newbits)))[int(netnum)])


def _distinct(items: list[Any]) -> list[Any]:
    out: list[Any] = []
    for item in items:
        if item not in out:
            out.append(item)
    return out


def _fail() -> Any:
    raise ValueError("more than one item")


def _flatten(items: list[Any]) -> list[Any]:
    out: list[Any] = []
    for item in items:
        out.extend(_flatten(item) if isinstance(item, list) else [item])
    return out


def _try(*args: Any) -> Any:
    for arg in args:
        if not _holds_unknown(arg):
            return arg
    return UNKNOWN


def _replace(text: str, old: str, new: str) -> str:
    """Terraform's replace: a substring in slashes is a regular expression."""
    if len(old) > 1 and old.startswith("/") and old.endswith("/"):
        return re.sub(old[1:-1], re.sub(r"\$(\d+)", r"\\\1", new), text)
    return text.replace(old, new)


def _trim(text: str, characters: str) -> str:
    return text.strip(characters)


def _cidrsubnets(prefix: str, *newbits: Any) -> list[str]:
    """Consecutive subnets of the sizes asked, each aligned to its size."""
    network = ipaddress.ip_network(prefix, strict=False)
    out: list[str] = []
    start = int(network.network_address)
    for bits in newbits:
        length = network.prefixlen + int(bits)
        size = 1 << (network.max_prefixlen - length)
        start = -(-start // size) * size
        subnet = type(network)((start, length))
        if not subnet.subnet_of(network):  # type: ignore[arg-type]
            raise ValueError("the subnets do not fit")
        out.append(str(subnet))
        start += size
    return out


def _matched(match: re.Match[str]) -> Any:
    """What ``regex`` gives for a match: its captures by name, else in order, else the match."""
    if match.re.groupindex:
        return {name: match.group(name) for name in match.re.groupindex}
    if match.re.groups:
        return list(match.groups())
    return match.group(0)


def _regex(pattern: str, text: str) -> Any:
    match = re.search(pattern, text)
    if match is None:
        raise ValueError("no match")
    return _matched(match)


def _formatlist(spec: str, *args: Any) -> list[str]:
    lengths = {len(arg) for arg in args if isinstance(arg, list)}
    if len(lengths) > 1:
        raise ValueError("the lists differ in length")
    return [
        _format(spec, *(arg[i] if isinstance(arg, list) else arg for arg in args))
        for i in range(lengths.pop() if lengths else 1)
    ]


def _set_order(value: Any) -> tuple[int, Any]:
    """A set's order: numbers by value, then text."""
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return (0, value)
    return (1, _text(value))


def _truth(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return {"true": True, "false": False}[str(value)]


def _lookup(mapping: dict[str, Any], key: str, *default: Any) -> Any:
    if key in mapping:
        return mapping[key]
    if default:
        return default[0]
    raise KeyError(key)


#: Functions that rearrange values without reading them: an unknown value
#: inside a list or map is carried through, not the whole result unknown.
_STRUCTURAL = frozenset(
    {
        "merge",
        "concat",
        "length",
        "keys",
        "values",
        "lookup",
        "element",
        "slice",
        "reverse",
        "tolist",
        "tomap",
        "try",
        "coalescelist",
        "one",
    }
)

#: The functions whose results the evaluator computes; any other call is UNKNOWN.
FUNCTIONS: dict[str, Callable[..., Any]] = {
    "cidrsubnet": _cidrsubnet,
    "cidrsubnets": _cidrsubnets,
    "cidrhost": lambda prefix, host: str(ipaddress.ip_network(prefix, strict=False)[int(host)]),
    "cidrnetmask": lambda prefix: str(ipaddress.ip_network(prefix, strict=False).netmask),
    "abs": abs,
    "alltrue": lambda items: all(_truth(item) for item in items),
    "anytrue": lambda items: any(_truth(item) for item in items),
    # reached only with a known argument: a call with an unknown one is unknown
    "can": lambda value: True,
    "ceil": lambda number: -(-number // 1),
    "chomp": lambda text: text.rstrip("\r\n"),
    "chunklist": lambda items, size: (
        [items[i : i + int(size)] for i in range(0, len(items), int(size))]
        if int(size) > 0
        else [items]
    ),
    "coalesce": lambda *args: next(arg for arg in args if arg not in (None, "")),
    "coalescelist": lambda *lists: next(items for items in lists if items),
    "compact": lambda items: [item for item in items if item not in (None, "")],
    "contains": lambda items, value: value in items,
    "endswith": lambda text, suffix: text.endswith(suffix),
    "floor": lambda number: number // 1,
    "concat": lambda *lists: [item for items in lists for item in items],
    "distinct": _distinct,
    "element": lambda items, index: items[int(index) % len(items)],
    "flatten": _flatten,
    "format": _format,
    "formatlist": _formatlist,
    "index": lambda items, value: items.index(value),
    "jsonencode": lambda value: json.dumps(value, sort_keys=True, separators=(",", ":")),
    "join": lambda sep, items: sep.join(_text(item) for item in items),
    "keys": lambda mapping: sorted(mapping),
    "length": len,
    "lookup": _lookup,
    "lower": lambda text: text.lower(),
    "max": max,
    "min": min,
    "one": lambda items: items[0] if len(items) == 1 else (None if not items else _fail()),
    "reverse": lambda items: list(reversed(items)),
    "merge": lambda *maps: {key: value for mapping in maps for key, value in mapping.items()},
    "nonsensitive": lambda value: value,
    "parseint": lambda text, base: int(text, int(base)),
    "pow": lambda number, power: number**power,
    "range": lambda *args: list(range(*(int(arg) for arg in args))),
    "regex": _regex,
    "regexall": lambda pattern, text: [_matched(match) for match in re.finditer(pattern, text)],
    "replace": _replace,
    "sensitive": lambda value: value,
    "setintersection": lambda first, *rest: [
        item for item in _distinct(first) if all(item in s for s in rest)
    ],
    "setproduct": lambda *sets: [list(combination) for combination in itertools.product(*sets)],
    "setsubtract": lambda first, second: [item for item in _distinct(first) if item not in second],
    "setunion": lambda *sets: _distinct([item for s in sets for item in s]),
    "signum": lambda number: (number > 0) - (number < 0),
    "slice": lambda items, start, end: items[int(start) : int(end)],
    "sort": lambda items: sorted(items, key=_text),
    "split": lambda sep, text: text.split(sep),
    "startswith": lambda text, prefix: text.startswith(prefix),
    "strcontains": lambda text, part: part in text,
    "strrev": lambda text: text[::-1],
    "substr": lambda text, offset, length: (
        text[int(offset) :] if int(length) < 0 else text[int(offset) : int(offset) + int(length)]
    ),
    "sum": sum,
    "title": lambda text: text.title(),
    "tobool": _truth,
    "tolist": list,
    "tomap": dict,
    "tonumber": _number,
    "toset": lambda items: sorted(_distinct(items), key=_set_order),
    "tostring": _text,
    "trim": _trim,
    "trimprefix": lambda text, prefix: text.removeprefix(prefix),
    "trimspace": lambda text: text.strip(),
    "trimsuffix": lambda text, suffix: text.removesuffix(suffix),
    "try": _try,
    "upper": lambda text: text.upper(),
    "values": lambda mapping: [mapping[key] for key in sorted(mapping)],
    "zipmap": lambda keys, values: dict(zip(keys, values, strict=True)),
}


# ==================================================================== types
#: A type constraint: ``("string",)``, ``("list", T)``, ``("map", T)``,
#: ``("tuple", [T, ...])``, ``("object", {name: (T, optional, default)})``, ``("any",)``.
Type = tuple[Any, ...]
_ANY: Type = ("any",)


def type_of(expr: Expr | str | None) -> Type:
    """A variable's ``type`` as :func:`convert` reads it; any type it does
    not read is ``any``, which converts nothing."""
    if expr is None:
        return _ANY
    try:
        t = _Tokens(expr.text if isinstance(expr, Expr) else expr)
        kind = _type(t)
        return kind if t.peek()[0] == "end" else _ANY
    except (_Syntax, HclError, RecursionError):
        return _ANY


def _type(t: _Tokens) -> Type:
    kind, name = t.take()
    if kind != "ident":
        raise _Syntax("type")
    if name in ("string", "number", "bool", "any"):
        return (name,)
    t.take("(")
    if name in ("list", "set", "map"):
        inner = _type(t)
        t.take(")")
        return ("map" if name == "map" else "list", inner)
    if name == "tuple":
        t.take("[")
        items: list[Type] = []
        while t.peek()[1] != "]":
            items.append(_type(t))
            if t.peek()[1] == ",":
                t.take(",")
        t.take("]")
        t.take(")")
        return ("tuple", items)
    if name == "object":
        t.take("{")
        attributes: dict[str, tuple[Type, bool, Any]] = {}
        while t.peek()[1] != "}":
            key = t.take()[1].strip('"')
            t.take("=")
            optional, default = False, None
            if t.peek() == ("ident", "optional"):
                t.take()
                t.take("(")
                inner = _type(t)
                if t.peek()[1] == ",":
                    t.take(",")
                    default = _Evaluator({}, FUNCTIONS).expression(t)
                t.take(")")
                optional = True
            else:
                inner = _type(t)
            attributes[key] = (inner, optional, default)
            if t.peek()[1] == ",":
                t.take(",")
        t.take("}")
        t.take(")")
        return ("object", attributes)
    raise _Syntax(f"type {name}")


def convert(value: Any, kind: Type) -> Any:
    """``value`` as Terraform converts it to a type: an object's optional
    attributes given their defaults (or null), a number or bool read from
    its text, and the same inside lists, maps and tuples. What does not
    convert is left as it is; Terraform would refuse it, the reader reads on."""
    if value is UNKNOWN or value is None or kind[0] == "any":
        return value
    name = kind[0]
    if name == "string" and isinstance(value, (int, float, bool)):
        return _text(value)
    if name == "number" and isinstance(value, str):
        try:
            return _number(value)
        except (TypeError, ValueError):
            return value
    if name == "bool" and isinstance(value, str) and value in ("true", "false"):
        return value == "true"
    if name == "list" and isinstance(value, list):
        return [convert(item, kind[1]) for item in value]
    if name == "map" and isinstance(value, dict):
        return {key: convert(item, kind[1]) for key, item in value.items()}
    if name == "tuple" and isinstance(value, list):
        return [
            convert(item, kind[1][i]) if i < len(kind[1]) else item for i, item in enumerate(value)
        ]
    if name == "object" and isinstance(value, dict):
        out = dict(value)
        for key, (inner, optional, default) in kind[1].items():
            if key in value:
                out[key] = convert(value[key], inner)
            elif optional:
                out[key] = convert(default, inner)
        return out
    return value


def _strict_try(*args: Any) -> Any:
    """``try()`` for which a value the reader cannot know is no failure:
    ``try(aws_subnet.this[*].id, [])`` is what Terraform knows only once the
    subnets are made, not the empty list."""
    return args[0] if args and not _holds_unknown(args[0]) else UNKNOWN


#: The functions, ``try()`` never falling back past a value the reader cannot know.
STRICT_FUNCTIONS: dict[str, Callable[..., Any]] = {**FUNCTIONS, "try": _strict_try}


def evaluate(expr: Expr | str, scope: Mapping[str, Any] | None = None, strict: bool = False) -> Any:
    """The value of ``expr`` where it is literal: strings, numbers, bools,
    lists and objects, ``var.``/``local.``/``each.``/``count.`` from ``scope``,
    templates, conditionals and the common functions. Anything else, a
    resource attribute above all, is :data:`UNKNOWN`. ``try()`` falls back
    past what it cannot evaluate (a missing attribute and an unknown alike)
    unless ``strict``, where an unknown keeps it unknown."""
    text = expr.text if isinstance(expr, Expr) else expr
    try:
        return _Evaluator(scope or {}, STRICT_FUNCTIONS if strict else FUNCTIONS).run(text)
    except (_Syntax, RecursionError, HclError):
        return UNKNOWN


# ==================================================================== references
_REFERENCE = re.compile(
    r"(?<![\w.])(?:"
    r"(?P<data>data\.[a-z][a-z0-9_]*\.[A-Za-z_][\w-]*)"
    r"|(?P<module>module\.[A-Za-z_][\w-]*)(?P<instance>\[[^\]]*\])?\.(?P<output>[A-Za-z_][\w-]*)"
    r"|(?P<resource>(?P<type>[a-z][a-z0-9]*_[a-z0-9_]+)\.(?P<name>[A-Za-z_][\w-]*))"
    r"|(?P<whole>module\.[A-Za-z_][\w-]*)"
    r")(?P<index>\[[^\]]+\])?(?P<attribute>\.[A-Za-z_][\w-]*)?(?P<chain>(?:\[[^\]]+\]|\.[A-Za-z_][\w-]*)*)"
)
#: Names that look like a resource type but are Terraform's own.
_NOT_TYPES = frozenset({"path_module", "path_root"})
#: The names a ``for`` expression binds: ``for key, value in``, ``for item in``.
_FOR = re.compile(r"(?<![\w.])for\s+([A-Za-z_][\w-]*)(?:\s*,\s*([A-Za-z_][\w-]*))?\s+in\b")


def _code_only(text: str) -> str:
    """``text`` with its string characters and comments blanked, its
    interpolations kept, so a reference is found only where it is code."""
    out = list(text)
    i = 0

    def blank(start: int, end: int) -> None:
        for k in range(start, end):
            if out[k] != "\n":
                out[k] = " "

    while i < len(text):
        ch = text[i]
        if ch == '"':
            j = i + 1
            start = j
            while j < len(text) and text[j] != '"':
                if text[j] == "\\":
                    j += 2
                    continue
                if text.startswith("${", j) or (text.startswith("%{", j)):
                    blank(start, j)
                    reader = _Reader(text, "<expr>")
                    reader.pos = j + 2
                    try:
                        reader.skip_interpolation()
                    except HclError:
                        return "".join(out)
                    j = reader.pos
                    start = j
                    continue
                j += 1
            blank(start, j)
            i = j + 1
        elif ch == "#" or text.startswith("//", i):
            end = text.find("\n", i)
            end = len(text) if end < 0 else end
            blank(i, end)
            i = end
        elif text.startswith("/*", i):
            end = text.find("*/", i + 2)
            end = len(text) if end < 0 else end + 2
            blank(i, end)
            i = end
        else:
            i += 1
    return "".join(out)


_SYMBOL = re.compile(r"(?<![\w.])(var|local|each)\.([A-Za-z_][\w-]*)")


def symbols(expr: Expr | str) -> list[str]:
    """The ``var.<name>``, ``local.<name>`` and ``each.key``/``each.value`` an
    expression reads, each once: what a module's input, a local or a
    ``for_each`` stands for is followed through them."""
    text = _code_only(expr.text if isinstance(expr, Expr) else expr)
    return list(dict.fromkeys(f"{kind}.{name}" for kind, name in _SYMBOL.findall(text)))


def iterators_read(expr: Expr | str, names: Iterable[str]) -> list[str]:
    """Which of ``names`` -- ``dynamic`` blocks' iterators -- the expression
    reads, through ``<name>.key`` or ``<name>.value``."""
    text = _code_only(expr.text if isinstance(expr, Expr) else expr)
    return [
        name for name in names if re.search(rf"(?<![\w.]){re.escape(name)}\.(?:key|value)\b", text)
    ]


def _key(index: str, scope: Mapping[str, Any] | None) -> str:
    """``[count.index]`` as ``[1]``, ``[each.key]`` as ``["a"]``; ``""`` when
    the key is not known."""
    key = evaluate(index[1:-1], scope)
    if isinstance(key, bool) or key is UNKNOWN or isinstance(key, (list, dict)):
        return ""
    return f"[{int(key)}]" if isinstance(key, (int, float)) else f'["{key}"]'


#: One step of what is read of a value: ``["key"]``, ``[1]`` or ``.attribute``.
_STEP = re.compile(r"\[[^\]]+\]|\.[A-Za-z_][\w-]*")


def _chain(text: str, scope: Mapping[str, Any] | None) -> str:
    """The steps of ``text`` whose keys are known, up to the first that is not."""
    out = ""
    for step in _STEP.findall(text):
        if step.startswith("["):
            key = _key(step, scope)
            if not key:
                break
            out += key
        else:
            out += step
    return out


_ELEMENT = re.compile(r"(?<![\w.])element\s*\(")


def _arguments(text: str, opening: int) -> list[tuple[int, int]]:
    """The spans of a call's arguments, from the position of its ``(``; a
    trailing comma is no argument."""
    spans: list[tuple[int, int]] = []
    depth, start = 0, opening + 1
    for i in range(opening, len(text)):
        if text[i] in "([{":
            depth += 1
        elif text[i] in ")]}":
            depth -= 1
            if depth == 0:
                spans.append((start, i))
                return [span for span in spans if text[span[0] : span[1]].strip()]
        elif text[i] == "," and depth == 1:
            spans.append((start, i))
            start = i + 1
    return []


def object_entries(expr: Expr | str) -> list[tuple[str, str]] | None:
    """The key and value text of each entry of an object written out
    (``{ web = {...}, db = {...} }``), in order; ``None`` for any other
    expression, a ``for`` expression and a computed key among them."""
    text = expr.text if isinstance(expr, Expr) else expr
    try:
        t = _Tokens(text)
        if t.peek()[1] != "{":
            return None
        t.take("{")
        if t.peek() == ("ident", "for"):
            return None
        reader = _Evaluator({}, FUNCTIONS)
        entries: list[tuple[str, str]] = []
        while t.peek()[1] != "}":
            kind, key = t.peek()
            if kind == "ident":
                t.take()
            elif kind == "quote":
                key = t.take()[1]
                if "${" in key or "%{" in key:
                    return None
            else:
                return None
            if t.take()[1] not in ("=", ":"):
                return None
            t.peek()
            start = t.pos
            reader.expression(t)
            entries.append((key, t.text[start : t.pos]))
            if t.peek()[1] == ",":
                t.take(",")
        t.take("}")
        return entries if t.peek()[0] == "end" else None
    except (_Syntax, HclError, RecursionError):
        return None


def element_calls(expr: Expr | str) -> list[tuple[str, str]]:
    """The list and the index of each ``element(list, index)`` in ``expr``,
    as written: what names the list names its ``[index]`` instance."""
    source = expr.text if isinstance(expr, Expr) else expr
    text = _code_only(source)
    out: list[tuple[str, str]] = []
    for call in _ELEMENT.finditer(text):
        spans = _arguments(text, call.end() - 1)
        if len(spans) == 2:
            out.append((source[spans[0][0] : spans[0][1]], source[spans[1][0] : spans[1][1]]))
    return out


def references(expr: Expr | str, scope: Mapping[str, Any] | None = None) -> list[str]:
    """The addresses ``expr`` names, in order, each once: ``aws_vpc.main``,
    ``aws_subnet.private[1]`` (an index is kept when it is literal, or
    ``count.index``/``each.key`` that ``scope`` knows), ``data.aws_ami.web``,
    ``module.network.private_subnet_ids`` (a module output, of one instance of
    the module, or ``[1]`` of it)."""
    source = expr.text if isinstance(expr, Expr) else expr
    # found in the code alone, but an index read as written: ["a"] is a key
    # the blanked text no longer holds
    text = _code_only(source)
    # a name a for expression binds is the element, not a resource type:
    # { for key, security_group in module.security_group : key => security_group.id }
    bound = {name for match in _FOR.finditer(text) for name in match.groups() if name}
    # nor is a name the scope binds: a dynamic block's iterator,
    # network_configuration.value.security_groups
    bound |= set(scope or ())
    found: list[str] = []
    for match in _REFERENCE.finditer(text):
        if match.group("data"):
            address = match.group("data")
        elif match.group("resource") and match.group("type") in bound:
            continue
        else:
            if match.group("module"):
                # the module's instance and the output's element are kept:
                # module.sg["api"].id, module.net.subnet_ids[1]
                instance = match.group("instance")
                key = (
                    _key(source[match.start("instance") : match.end("instance")], scope)
                    if instance
                    else ""
                )
                address = f"{match.group('module')}{key}.{match.group('output')}"
            elif match.group("whole"):
                # a module as a value, all its instances or one: an output
                # holding it lets a caller reach an instance's own outputs
                address = match.group("whole")
            else:
                if match.group("type") in _NOT_TYPES:
                    continue
                address = match.group("resource")
            if match.group("index"):
                address += _key(source[match.start("index") : match.end("index")], scope)
            # an output's element's attribute is kept, for an element that is
            # a module instance: module.vnet.subnets["web"].resource_id
            if (
                (match.group("module") or match.group("whole"))
                and match.group("attribute")
                and address.endswith("]")
            ):
                address += match.group("attribute")
                # and what is read of it, as far as the keys are known:
                # module.network.vpcs["vpc"].private_subnets[1],
                # module.network.virtual_networks["vnet"].subnets["web"].resource_id
                address += _chain(source[match.start("chain") : match.end("chain")], scope)
        if address not in found:
            found.append(address)
    return found
