"""What the kernel refuses, and why. Every one of these stops the service starting.

A plugin that is wrong is wrong before the first request, not during one: a service that
boots into a broken state answers some requests correctly and others not at all, which is
far harder to diagnose than a service that refuses to start and says which file is at fault.
"""


class PlatformError(Exception):
    """Base class, so a caller can catch every refusal without naming each one."""


class ManifestError(PlatformError):
    """A manifest could not be read, or does not say what a manifest must say."""


class DuplicateAppError(PlatformError):
    """Two manifests claim the same app name."""


class IncompatiblePlatformError(PlatformError):
    """An app needs a platform version this one is not, or names a range that is not one."""


class ConfigurationError(PlatformError):
    """The service was asked to start in a state it cannot safely run in."""


class PermissionRefused(PlatformError):
    """A plugin tried to do something its manifest does not grant, or to take a name that is
    somebody else's: a table, a route, or a Python module."""


class PackageError(PlatformError):
    """A plugin archive is malformed or unsafe to unpack: a path that walks out of its
    directory, a link, an entry the format does not allow, or more bytes than it may hold."""


class TrustError(PlatformError):
    """A plugin cannot be shown to come from a key this service trusts: its checksum does not
    match the index, its signature does not verify, or the key that signed it is not trusted."""
