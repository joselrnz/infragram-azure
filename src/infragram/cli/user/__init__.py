"""The commands a user runs, as package code.

``export:project`` renders a ``.infragram.json`` document, ``compose`` runs a
Python diagram file, ``export:set`` exports a folder of them, ``check`` reads
what was written, and ``verify:render`` renders a page several times to prove
it holds still. They run in-process, in the user's own directory, and work the
same from a checkout and from an installed copy. The maintainer commands stay
scripts under ``scripts/``, which only a checkout carries.
"""
