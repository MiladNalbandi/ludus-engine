"""Ed25519 signatures over plugin packages, and the keys this service trusts.

**What is signed is a statement, not just the bytes:**

```
wavemaker-plugin-v1
<name>
<version>
<sha256 of the archive>
```

so a signature says "this archive *is* inventory 1.0.0". Signing only the bytes would let
anybody who can edit the index relabel a genuine archive — list `inventory-0.9.0.wmp`, with
its real signature, as version 1.0.0 — and the signature would still verify.

**Trusted keys are files an operator put in a directory,** one public key per `*.pub` file, in
PEM. A key is known by its id, the first sixteen hex digits of the SHA-256 of its raw bytes,
which is what an index entry names. An index can name any key it likes; only one in the
directory can make an install succeed. No directory, or an empty one, trusts nobody, and
nothing can be installed — there is no "trust on first use".
"""

from __future__ import annotations

import base64
import binascii
import hashlib
from dataclasses import dataclass
from pathlib import Path

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

from wavemaker.platform.kernel.errors import TrustError

STATEMENT = "wavemaker-plugin-v1"
PUBLIC_SUFFIX = ".pub"


def checksum(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def statement(name: str, version: str, sha256: str) -> bytes:
    return "\n".join((STATEMENT, name, version, sha256, "")).encode()


def key_id(public: Ed25519PublicKey) -> str:
    raw = public.public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    return hashlib.sha256(raw).hexdigest()[:16]


def generate(private_path: Path) -> str:
    """Write a new private key (readable by its owner only) and its `.pub`; return its id."""
    private = Ed25519PrivateKey.generate()
    private_path.parent.mkdir(parents=True, exist_ok=True)
    private_path.write_bytes(
        private.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    private_path.chmod(0o600)
    public = private.public_key()
    private_path.with_suffix(PUBLIC_SUFFIX).write_bytes(public_pem(public))
    return key_id(public)


def public_pem(public: Ed25519PublicKey) -> bytes:
    return public.public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
    )


def load_private(path: Path) -> Ed25519PrivateKey:
    try:
        key = serialization.load_pem_private_key(path.read_bytes(), password=None)
    except (OSError, ValueError, TypeError) as broken:
        raise TrustError(f"{path} is not a usable private key ({broken}).") from broken
    if not isinstance(key, Ed25519PrivateKey):
        raise TrustError(f"{path} is not an Ed25519 private key.")
    return key


def sign(private: Ed25519PrivateKey, name: str, version: str, sha256: str) -> str:
    return base64.b64encode(private.sign(statement(name, version, sha256))).decode()


@dataclass(frozen=True, slots=True)
class TrustedKeys:
    keys: dict[str, Ed25519PublicKey]

    @classmethod
    def load(cls, directory: Path | None) -> TrustedKeys:
        if directory is None:
            return cls({})
        if not directory.is_dir():
            raise TrustError(f"The trusted keys directory {directory} does not exist.")
        keys: dict[str, Ed25519PublicKey] = {}
        for path in sorted(directory.glob(f"*{PUBLIC_SUFFIX}")):
            try:
                key = serialization.load_pem_public_key(path.read_bytes())
            except (OSError, ValueError) as broken:
                raise TrustError(f"{path} is not a usable public key ({broken}).") from broken
            if not isinstance(key, Ed25519PublicKey):
                raise TrustError(f"{path} is not an Ed25519 public key.")
            keys[key_id(key)] = key
        return cls(keys)

    def verify(self, key: str, signature: str, name: str, version: str, sha256: str) -> None:
        if not self.keys:
            raise TrustError(
                "No trusted keys are configured, so no plugin can be installed. Put the "
                "publisher's public key in the trusted keys directory."
            )
        public = self.keys.get(key)
        if public is None:
            raise TrustError(
                f"{name}@{version} is signed by key {key}, which this service does not trust."
            )
        try:
            raw = base64.b64decode(signature, validate=True)
            public.verify(raw, statement(name, version, sha256))
        except (InvalidSignature, binascii.Error, ValueError) as forged:
            raise TrustError(
                f"The signature on {name}@{version} does not verify with key {key}: the "
                "package, or its entry in the index, is not what was signed."
            ) from forged
