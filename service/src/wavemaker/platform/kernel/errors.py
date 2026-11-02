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
