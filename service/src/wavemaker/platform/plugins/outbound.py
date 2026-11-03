"""`outbound_http = false`, held in the process: a plugin's code may not open a network
connection.

Python raises an *audit event* before every socket connect, name lookup and datagram send
(PEP 578), and a hook installed with `sys.addaudithook` sees each one before it happens and may
refuse it by raising. The hook here refuses when the code asking is a plugin's that was not
granted the network. "Whose code is asking" is answered two ways:

- **while the platform runs a plugin's code on purpose** — importing it, running its
  migrations — a context variable names the plugin, so nothing that code does reaches out;
- **while a request is being served**, the hook walks the calling stack and refuses if any
  frame belongs to a denied plugin's modules, so a library the plugin calls is refused too.

This is a guard against a plugin that reaches the network by accident or by habit — an SDK that
phones home, a schema library that fetches a reference. **It is not a sandbox.** Code that runs
in this process can hand a function to a thread pool so that no frame of its own is on the
stack, call a C library that opens sockets beneath Python, or start a subprocess. Holding code
someone else wrote to a promise it does not want to keep needs a separate process, which is the
third step of the trust model and not this release.

An audit hook cannot be removed once installed, so there is one, installed the first time it
is needed, reading a table of denied plugins that grows as they load.
"""

from __future__ import annotations

import sys
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from types import FrameType
from typing import Any

from wavemaker.platform.kernel.manifest import AppManifest

# The events that put bytes on a network, or resolve a name in order to. `socket.bind` is not
# here: listening is not reaching out.
NETWORK_EVENTS = frozenset(
    {
        "socket.connect",
        "socket.getaddrinfo",
        "socket.gethostbyname",
        "socket.gethostbyaddr",
        "socket.sendto",
        "socket.sendmsg",
        "urllib.Request",
    }
)

_denied: dict[str, str] = {}
_acting: ContextVar[str | None] = ContextVar("wavemaker_acting_plugin", default=None)
_installed = False


class OutboundRefused(PermissionError):
    """Raised inside the plugin's own call, so the plugin sees an ordinary refusal."""


def deny(manifest: AppManifest) -> None:
    """Refuse the network to every module under this plugin's import name, unless granted."""
    _install()
    if manifest.permissions.outbound_http:
        _denied.pop(manifest.import_name, None)
    else:
        _denied[manifest.import_name] = manifest.name


def is_denied(manifest: AppManifest) -> bool:
    return _denied.get(manifest.import_name) == manifest.name


@contextmanager
def acting_as(manifest: AppManifest) -> Iterator[None]:
    """Run a block as the plugin: if it is denied the network, so is everything in the block."""
    _install()
    token = _acting.set(None if manifest.permissions.outbound_http else manifest.name)
    try:
        yield
    finally:
        _acting.reset(token)


def _install() -> None:
    global _installed
    if not _installed:
        sys.addaudithook(_hook)
        _installed = True


def _hook(event: str, args: tuple[Any, ...]) -> None:
    if event not in NETWORK_EVENTS:
        return
    culprit = _acting.get() or _from_stack(sys._getframe(1))
    if culprit is not None:
        raise OutboundRefused(
            f"Plugin '{culprit}' may not reach the network ({event} {_target(args)}): its "
            "manifest does not grant outbound_http."
        )


def _from_stack(frame: FrameType | None) -> str | None:
    if not _denied:
        return None
    while frame is not None:
        module = frame.f_globals.get("__name__")
        if isinstance(module, str):
            culprit = _denied.get(module.partition(".")[0])
            if culprit is not None:
                return culprit
        frame = frame.f_back
    return None


def _target(args: tuple[Any, ...]) -> str:
    for value in args:
        if isinstance(value, (str, tuple)):
            return repr(value)
    return ""
