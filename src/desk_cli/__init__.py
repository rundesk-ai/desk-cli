"""desk-cli — an installable command-line client for the Rundesk API.

The package pairs the Rundesk REST client (``client.py``) and its full-API
command tree (``rundesk.py``) with local multi-profile credential storage
(``profiles.py``), a version-aware self-updater (``updater.py``), and the
``desk`` command surface (``cli.py``).

``__version__`` is the single source of truth consulted by ``desk --version`` and
``desk update``; bump it and push a matching ``vX.Y.Z`` git tag for every release.
"""

__version__ = "0.1.0"
