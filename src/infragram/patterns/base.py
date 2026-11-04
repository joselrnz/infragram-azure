"""The one abstraction under every pattern.

A :class:`Pattern` is a named, reusable piece of infrastructure built from the
generated node classes: two Availability Zones with the same tiers in each, a
row of account-wide guardrails, a site's edge and the circuit it lands on.
It builds once, on demand, and afterwards answers two questions a caller has:
*which elements did you make* (:attr:`Pattern.elements`, to attach them to a
parent) and *where is the thing I need to wire up* (:attr:`Pattern.parts`,
by a stable key), so a diagram that uses a pattern never reaches into its
structure.

Patterns compose into a :class:`~infragram.patterns.blueprint.Blueprint`,
which turns them into one project document and exports it.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterator, Mapping, Sequence
from types import MappingProxyType
from typing import Any, Self, TypeVar

from ..models.topology import TopologyElement

__all__ = ["Pattern", "PatternError"]


_E = TypeVar("_E", bound=TopologyElement)


class PatternError(ValueError):
    """A pattern was asked for something its build cannot give."""


class Pattern(ABC):
    """A reusable piece of infrastructure with a name, elements and parts.

    Subclasses implement :meth:`build`, returning the top-level element or
    elements they make, and register the ones a caller may need to connect
    with :meth:`part`. Everything else -- lazy building, immutability once
    built, attaching to a parent -- is here.
    """

    def __init__(self, name: str) -> None:
        self._name = str(name)
        self._parts: dict[str, TopologyElement] = {}
        self._elements: tuple[TopologyElement, ...] | None = None

    # ------------------------------------------------------------ identity
    @property
    def name(self) -> str:
        """The label the pattern's frame carries."""
        return self._name

    @name.setter
    def name(self, value: str) -> None:
        self._guard_unbuilt("name")
        if not str(value).strip():
            raise PatternError("a pattern needs a non-empty name")
        self._name = str(value)

    @property
    def built(self) -> bool:
        return self._elements is not None

    def _guard_unbuilt(self, what: str) -> None:
        """Settings shape the build; after it they would silently do nothing."""
        if self.built:
            raise PatternError(
                f"{type(self).__name__} is already built; set {what} before using it"
            )

    # ------------------------------------------------------------- building
    @abstractmethod
    def build(self) -> TopologyElement | Sequence[TopologyElement]:
        """Make the elements. Register the connectable ones with :meth:`part`."""

    def realise(self) -> tuple[TopologyElement, ...]:
        """Build once and return the top-level elements; later calls are free."""
        if self._elements is None:
            made = self.build()
            elements = (made,) if isinstance(made, TopologyElement) else tuple(made)
            if not elements:
                raise PatternError(f"{type(self).__name__}.build() produced nothing")
            self._elements = elements
        return self._elements

    @property
    def elements(self) -> tuple[TopologyElement, ...]:
        """The top-level elements, built on first access."""
        return self.realise()

    def attach(self, parent: TopologyElement) -> Self:
        """Place every top-level element under ``parent`` and return self."""
        parent.add(*self.realise())
        return self

    # ---------------------------------------------------------------- parts
    def part(self, key: str, element: _E) -> _E:
        """Register an element under ``key`` and hand it straight back, so a
        build reads ``nat = self.part("nat", subnet >> Gateway(...))``."""
        if key in self._parts:
            raise PatternError(f"{type(self).__name__} already has a part named {key!r}")
        self._parts[key] = element
        return element

    @property
    def parts(self) -> Mapping[str, TopologyElement]:
        """Every registered element by key, read-only."""
        self.realise()
        return MappingProxyType(self._parts)

    def __getitem__(self, key: str) -> Any:
        """The part registered under ``key``: a node or a frame, whichever the
        build put there, so it wires with ``>>`` or opens as a ``with`` block
        as that class does. The keys are strings the build chose, so the type
        of each is not something a checker can know."""
        self.realise()
        try:
            return self._parts[key]
        except KeyError:
            known = ", ".join(sorted(self._parts)) or "none"
            raise PatternError(
                f"{type(self).__name__} has no part {key!r}; it has: {known}"
            ) from None

    def __contains__(self, key: object) -> bool:
        self.realise()
        return key in self._parts

    def __iter__(self) -> Iterator[str]:
        self.realise()
        return iter(self._parts)

    def __len__(self) -> int:
        self.realise()
        return len(self._parts)

    def __repr__(self) -> str:
        state = f"{len(self._parts)} parts" if self.built else "unbuilt"
        return f"{type(self).__name__}({self._name!r}, {state})"
