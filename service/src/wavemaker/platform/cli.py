"""The `wavemaker` command.

```
wavemaker plugin build   <app-folder> [--out DIR]                 a folder -> name-version.wmp
wavemaker plugin keygen  <private-key-file>                        an Ed25519 key pair
wavemaker plugin publish <archive> --registry DIR --key FILE       sign it and list it
wavemaker plugin install <name>@<version> [--registry DIR] [--plugins-dir DIR]
                                          [--trusted-keys DIR] [--database-url URL]
```

Every option of `install` falls back to the service's own setting (`WAVEMAKER_PLUGIN_REGISTRY`,
`WAVEMAKER_PLUGINS_DIRECTORY`, `WAVEMAKER_TRUSTED_KEYS_DIRECTORY`, `WAVEMAKER_DATABASE_URL`), so
the command installs into exactly the service the environment describes. A refusal is printed
as one line saying why, with exit status 1; nothing is left half-installed.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from wavemaker.platform.config import Settings
from wavemaker.platform.kernel.errors import ConfigurationError, PlatformError


def main(argv: Sequence[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    try:
        message: str = arguments.run(arguments)
    except PlatformError as refused:
        print(f"refused: {refused}", file=sys.stderr)
        return 1
    print(message)
    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="wavemaker")
    commands = parser.add_subparsers(dest="command", required=True)
    plugin = commands.add_parser("plugin", help="build, sign, publish and install plugins")
    actions = plugin.add_subparsers(dest="action", required=True)

    build = actions.add_parser("build", help="package an app folder as <name>-<version>.wmp")
    build.add_argument("app", type=Path)
    build.add_argument("--out", type=Path, default=Path("."))
    build.set_defaults(run=_build)

    keygen = actions.add_parser("keygen", help="write an Ed25519 private key and its .pub")
    keygen.add_argument("private_key", type=Path)
    keygen.set_defaults(run=_keygen)

    publish = actions.add_parser("publish", help="sign a package and list it in a registry")
    publish.add_argument("archive", type=Path)
    publish.add_argument("--registry", type=Path, required=True)
    publish.add_argument("--key", type=Path, required=True)
    publish.set_defaults(run=_publish)

    install = actions.add_parser("install", help="verify and install name@version")
    install.add_argument("spec")
    install.add_argument("--registry", type=Path)
    install.add_argument("--plugins-dir", type=Path)
    install.add_argument("--trusted-keys", type=Path)
    install.add_argument("--database-url")
    install.set_defaults(run=_install)
    return parser


def _build(arguments: argparse.Namespace) -> str:
    from wavemaker.platform.plugins.package import build

    return f"built {build(arguments.app, arguments.out)}"


def _keygen(arguments: argparse.Namespace) -> str:
    from wavemaker.platform.plugins.signing import generate

    key = generate(arguments.private_key)
    public = arguments.private_key.with_suffix(".pub")
    return f"key {key}: private {arguments.private_key}, public {public}"


def _publish(arguments: argparse.Namespace) -> str:
    from wavemaker.platform.plugins.index import publish

    entry = publish(arguments.archive, arguments.registry, arguments.key)
    return f"published {entry.name}@{entry.version} ({entry.sha256}), signed by key {entry.key}"


def _install(arguments: argparse.Namespace) -> str:
    from wavemaker.platform.plugins.install import install

    settings = Settings()
    registry = arguments.registry or settings.plugin_registry
    plugins = arguments.plugins_dir or settings.plugins_directory
    if registry is None:
        raise ConfigurationError("No registry: pass --registry or set WAVEMAKER_PLUGIN_REGISTRY.")
    if plugins is None:
        raise ConfigurationError(
            "No plugins directory: pass --plugins-dir or set WAVEMAKER_PLUGINS_DIRECTORY."
        )
    manifest = install(
        arguments.spec,
        registry=registry,
        plugins_directory=plugins,
        trusted_keys=arguments.trusted_keys or settings.trusted_keys_directory,
        database_url=arguments.database_url or settings.database_url,
    )
    return f"installed {manifest.name}@{manifest.version} into {plugins / manifest.name}"


if __name__ == "__main__":
    sys.exit(main())
