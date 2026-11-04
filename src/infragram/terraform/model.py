"""The Terraform package's records: pydantic models built positionally too.

The emitter, the HCL writer and the HCL reader build thousands of small
records, and read best written the way they are spoken --
``Attr("name", value)``, ``Raw("var.region")``,
``Block("resource", (type, name), body)``. A :class:`Record` is a pydantic
model that takes its fields in declaration order as well as by name, so
every record is typed and validated without each call spelling its fields
out.

A record holding another record keeps that very object (pydantic does not
copy a model instance it is given), which the walk relies on: a place's unit
*is* the root, not an equal copy of it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar

from pydantic import BaseModel, ConfigDict

__all__ = ["Record"]


if TYPE_CHECKING:

    class Record:
        """What the type checker sees of a :class:`Record`.

        mypy's pydantic support gives every model a keyword-only
        ``__init__`` built from its fields, and a Record takes them
        positionally too. To the checker a Record's fields are typed
        attributes, its construction takes what the real ``__init__``
        takes, and the model methods the code uses are declared.
        """

        model_config: ClassVar[ConfigDict]
        model_fields: ClassVar[dict[str, Any]]

        def __init__(self, /, *args: Any, **kwargs: Any) -> None: ...
        def model_copy(
            self, *, update: dict[str, Any] | None = None, deep: bool = False
        ) -> Any: ...
        def model_dump(self, **kwargs: Any) -> dict[str, Any]: ...
else:

    class Record(BaseModel):
        """A pydantic model whose fields may also be given positionally."""

        model_config = ConfigDict(arbitrary_types_allowed=True)

        def __init__(self, /, *args: Any, **kwargs: Any) -> None:
            if args:
                names = list(type(self).model_fields)
                if len(args) > len(names):
                    raise TypeError(
                        f"{type(self).__name__} takes at most {len(names)} positional arguments, "
                        f"not {len(args)}"
                    )
                for name, value in zip(names, args, strict=False):
                    if name in kwargs:
                        raise TypeError(f"{type(self).__name__} got {name!r} twice")
                    kwargs[name] = value
            super().__init__(**kwargs)
