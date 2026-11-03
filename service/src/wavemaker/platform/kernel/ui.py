"""What an app says about its editor screen: the `[ui]` table of its manifest.

```toml
[ui]
entry = "module.js"     # a file directly under the package's ui/ folder; this is the default
api = 2                 # the editor's module interface version the bundle was written for
```

The platform does not run the bundle and does not judge the interface version: the editor does,
and refuses one it does not implement. The platform checks that the declaration is well formed,
that the file it names is in the package, and records the file's hash when it installs it.

Read strictly, like `[permissions]`: an unknown key is refused, so `entyr = "app.js"` is an
error and not a plugin whose screen silently never appears.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from wavemaker.platform.kernel.errors import ManifestError

DEFAULT_ENTRY = "module.js"
KNOWN_KEYS = frozenset({"entry", "api"})

# One file name, directly under ui/, that is JavaScript. No directory part: the entry is what
# the editor imports, and a name that could say `../backend/x.js` is a name that must not exist.
ENTRY = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*(\.[A-Za-z0-9_-]+)*\.m?js$")


@dataclass(frozen=True, slots=True)
class UiDeclaration:
    entry: str = DEFAULT_ENTRY
    api: int = 0

    @classmethod
    def from_mapping(cls, data: Any, *, source: str = "") -> UiDeclaration | None:
        where = source or "manifest"
        if data is None:
            return None
        if not isinstance(data, Mapping):
            raise ManifestError(f"{where}: [ui] must be a table.")

        unknown = sorted(set(data) - KNOWN_KEYS)
        if unknown:
            raise ManifestError(
                f"{where}: [ui] does not know {', '.join(unknown)}. "
                f"It takes {', '.join(sorted(KNOWN_KEYS))}."
            )

        entry = data.get("entry", DEFAULT_ENTRY)
        if not isinstance(entry, str) or not ENTRY.match(entry):
            raise ManifestError(
                f"{where}: [ui] entry = {entry!r} is not the name of a JavaScript file directly "
                'under ui/, such as "module.js".'
            )

        api = data.get("api")
        # A bool is an int to Python; `api = true` is a mistake, not interface version 1.
        if not isinstance(api, int) or isinstance(api, bool) or api < 1:
            raise ManifestError(
                f"{where}: [ui] api must be the editor's module interface version the bundle was "
                "written for, a whole number such as 2."
            )
        return cls(entry=entry, api=api)

    @property
    def path(self) -> str:
        """The entry as a path inside the package."""
        return f"ui/{self.entry}"
