"""Helpers shared by the standalone scripts under ``scripts/``.

A gate script puts the ``scripts`` directory first on ``sys.path`` and then
``from lib import gatelib``; nothing here is part of the ``infragram``
package, and the shipped skill scripts may not import it.
"""
