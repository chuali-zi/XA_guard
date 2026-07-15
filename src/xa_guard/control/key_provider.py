"""Async envelope-key providers for local and external KEK custody."""

from __future__ import annotations

import base64
import binascii
import os
from pathlib import Path
from typing import Any, Protocol, runtime_checkable
from urllib.parse import urlsplit

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from xa_guard.control.crypto import CryptoError, EncryptedEnvelope, Keyring


class KeyProviderError(CryptoError):
    """A sanitized, fail-closed key-provider failure."""


@runtime_checkable
class KeyProvider(Protocol):
    """Async provider used by effect persistence and recovery."""

    @property
    def active_key_id(self) -> str: ...

    async def start(self) -> None: ...

    async def close(self) -> None: ...

    async def ready(self) -> bool: ...

    async def encrypt(self, plaintext: bytes, aad: bytes) -> EncryptedEnvelope: ...

    async def decrypt(self, envelope: EncryptedEnvelope, aad: bytes) -> bytes: ...

    async def rewrap(self, envelope: EncryptedEnvelope) -> EncryptedEnvelope: ...


class LocalKeyProvider:
    """Async compatibility adapter around the existing in-process Keyring."""

    def __init__(self, keyring: Keyring) -> None:
        self.keyring = keyring

    @property
    def active_key_id(self) -> str:
        return self.keyring.active_key_id

    async def start(self) -> None:
        return None

    async def close(self) -> None:
        return None

    async def ready(self) -> bool:
        return True

    async def encrypt(self, plaintext: bytes, aad: bytes) -> EncryptedEnvelope:
        return self.keyring.encrypt(plaintext, aad)

    async def decrypt(self, envelope: EncryptedEnvelope, aad: bytes) -> bytes:
        return self.keyring.decrypt(envelope, aad)

    async def rewrap(self, envelope: EncryptedEnvelope) -> EncryptedEnvelope:
        return self.keyring.rewrap(envelope)


class HttpKeyProvider:
    """Envelope encryption with KEK operations delegated to an HTTP KMS.

    The application still generates a random DEK and performs AES-GCM locally;
    only wrap/unwrap/rewrap operations cross the KMS boundary.  KEKs are never
    loaded into the XA-Guard process.
    """

    def __init__(
        self,
        base_url: str,
        auth_token: str,
        *,
        ca_file: str = "",
        timeout_seconds: float = 5.0,
        reference_http_hosts: tuple[str, ...] = (),
        client: Any | None = None,
    ) -> None:
        parsed = urlsplit(base_url)
        allowed_http_hosts = {
            host.strip().lower() for host in reference_http_hosts if host.strip()
        }
        reference_http = (
            parsed.scheme == "http"
            and str(parsed.hostname or "").lower() in allowed_http_hosts
        )
        if (
            (parsed.scheme != "https" and not reference_http)
            or not parsed.netloc
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
        ):
            raise KeyProviderError("key provider URL is not permitted")
        if not auth_token:
            raise KeyProviderError("key provider authentication is required")
        if ca_file and not Path(ca_file).is_file():
            raise KeyProviderError("key provider CA file is unavailable")
        self.base_url = base_url.rstrip("/")
        self._auth_token = auth_token
        self.ca_file = ca_file
        self.timeout_seconds = timeout_seconds
        self.client = client
        self._owns_client = client is None
        self._active_key_id = ""

    @property
    def active_key_id(self) -> str:
        return self._active_key_id

    async def start(self) -> None:
        if self.client is None:
            import httpx

            self.client = httpx.AsyncClient(
                timeout=self.timeout_seconds,
                verify=self.ca_file or True,
                headers={
                    "authorization": f"Bearer {self._auth_token}",
                    "accept": "application/json",
                },
            )

    async def close(self) -> None:
        if self.client is not None and self._owns_client:
            await self.client.aclose()
            self.client = None

    async def ready(self) -> bool:
        if self.client is None:
            return False
        try:
            response = await self.client.get(
                self.base_url + "/readyz", headers=self._request_headers()
            )
            response.raise_for_status()
            value = response.json()
            key_id = self._key_id(value.get("active_key_id"))
            if value.get("status") != "ready" or not key_id:
                return False
            self._active_key_id = key_id
            return True
        except Exception:
            return False

    async def encrypt(self, plaintext: bytes, aad: bytes) -> EncryptedEnvelope:
        self._require_started()
        dek = os.urandom(32)
        nonce = os.urandom(12)
        value = await self._post(
            "/v1/wrap", {"plaintext_key": self._encode(dek)}
        )
        key_id = self._key_id(value.get("key_id"))
        wrapped = self._decode(value.get("wrapped_key"), "wrapped key", max_bytes=16_384)
        self._active_key_id = key_id
        try:
            ciphertext = AESGCM(dek).encrypt(nonce, plaintext, aad)
        except Exception as exc:
            raise KeyProviderError("envelope encryption failed") from exc
        return EncryptedEnvelope(key_id, wrapped, nonce, ciphertext)

    async def decrypt(self, envelope: EncryptedEnvelope, aad: bytes) -> bytes:
        self._require_started()
        value = await self._post(
            "/v1/unwrap",
            {
                "key_id": envelope.key_id,
                "wrapped_key": self._encode(envelope.wrapped_dek),
            },
        )
        dek = self._decode(value.get("plaintext_key"), "plaintext key", max_bytes=32)
        if len(dek) != 32:
            raise KeyProviderError("key provider returned an invalid plaintext key")
        try:
            return AESGCM(dek).decrypt(envelope.nonce, envelope.ciphertext, aad)
        except (InvalidTag, ValueError) as exc:
            raise KeyProviderError("recovery material authentication failed") from exc

    async def rewrap(self, envelope: EncryptedEnvelope) -> EncryptedEnvelope:
        self._require_started()
        value = await self._post(
            "/v1/rewrap",
            {
                "key_id": envelope.key_id,
                "wrapped_key": self._encode(envelope.wrapped_dek),
            },
        )
        key_id = self._key_id(value.get("key_id"))
        wrapped = self._decode(value.get("wrapped_key"), "wrapped key", max_bytes=16_384)
        self._active_key_id = key_id
        return EncryptedEnvelope(key_id, wrapped, envelope.nonce, envelope.ciphertext)

    async def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            response = await self.client.post(
                self.base_url + path,
                json=payload,
                headers=self._request_headers(),
            )
            response.raise_for_status()
            value = response.json()
            if not isinstance(value, dict):
                raise ValueError("response is not an object")
            return value
        except Exception:
            # Never relay a response body, URL, token, or transport exception.
            raise KeyProviderError("key provider operation failed") from None

    def _request_headers(self) -> dict[str, str]:
        # Explicit headers also support injected test/connector clients.
        return {
            "authorization": f"Bearer {self._auth_token}",
            "accept": "application/json",
        }

    def _require_started(self) -> None:
        if self.client is None:
            raise KeyProviderError("key provider is not started")

    @staticmethod
    def _encode(value: bytes) -> str:
        return base64.b64encode(value).decode("ascii")

    @staticmethod
    def _decode(value: Any, label: str, *, max_bytes: int) -> bytes:
        if not isinstance(value, str) or len(value) > max_bytes * 2:
            raise KeyProviderError(f"key provider returned an invalid {label}")
        try:
            decoded = base64.b64decode(value, validate=True)
        except (ValueError, binascii.Error) as exc:
            raise KeyProviderError(f"key provider returned an invalid {label}") from exc
        if not decoded or len(decoded) > max_bytes:
            raise KeyProviderError(f"key provider returned an invalid {label}")
        return decoded

    @staticmethod
    def _key_id(value: Any) -> str:
        key_id = str(value or "")
        if not key_id or len(key_id) > 256 or any(ord(char) < 33 for char in key_id):
            raise KeyProviderError("key provider returned an invalid key identifier")
        return key_id
