from __future__ import annotations

import base64
import json
import struct
from typing import Any

from Crypto.Cipher import AES
from Crypto.Util.Padding import unpad

CORE_KEY = bytes.fromhex("687a4852416d736f356b496e62617857")
MODIFY_KEY = bytes.fromhex("2331346C6A6B5F215C5D2630553C2728")
NCM_MAGIC = b"CTENFDAM"


def aes_ecb_decrypt(data: bytes, key: bytes) -> bytes:
    """Decrypt AES-128-ECB encrypted data and unpad PKCS7."""
    cipher = AES.new(key, AES.MODE_ECB)
    decrypted = cipher.decrypt(data)
    try:
        return unpad(decrypted, 16)
    except Exception:
        pad = decrypted[-1]
        if 1 <= pad <= 16 and decrypted[-pad:] == bytes([pad]) * pad:
            return decrypted[:-pad]
        return decrypted


def detect_audio_ext(data: bytes, fallback: str = "mp3") -> str:
    """Detect audio format from magic bytes."""
    if data.startswith(b"ID3"):
        return "mp3"
    if data.startswith(b"fLaC"):
        return "flac"
    if data.startswith(b"OggS"):
        return "ogg"
    if len(data) >= 8 and data[4:8] == b"ftyp":
        return "m4a"
    if data.startswith(b"RIFF"):
        return "wav"
    if data.startswith(bytes([0xFF, 0xF1])) or data.startswith(bytes([0xFF, 0xF9])):
        return "aac"
    if data.startswith(b"FRM8"):
        return "dff"
    return fallback


class NCMDecoder:
    """NCM file decoder powered by PyCryptodome."""

    def __init__(self, raw: bytes, filename: str = "") -> None:
        if raw[:8] != NCM_MAGIC:
            raise ValueError("Invalid NCM magic header")
        self.raw = raw
        self.filename = filename
        self.offset = 10
        self.meta: dict[str, Any] = {}

    def _read_u32(self, offset: int | None = None) -> int:
        offset = self.offset if offset is None else offset
        return struct.unpack_from("<I", self.raw, offset)[0]

    def _get_key_data(self) -> bytes:
        key_len = self._read_u32()
        self.offset += 4
        key_data = bytes(b ^ 0x64 for b in self.raw[self.offset : self.offset + key_len])
        self.offset += key_len
        return aes_ecb_decrypt(key_data, CORE_KEY)[17:]

    def _get_key_box(self) -> list[int]:
        key = self._get_key_data()
        box = list(range(256))
        j = 0
        key_len = len(key)
        for i in range(256):
            j = (box[i] + j + key[i % key_len]) & 0xFF
            box[i], box[j] = box[j], box[i]
        out = []
        for i in range(256):
            idx = (i + 1) & 0xFF
            si = box[idx]
            sj = box[(idx + si) & 0xFF]
            out.append(box[(si + sj) & 0xFF])
        return out

    def _get_metadata(self) -> dict[str, Any]:
        meta_len = self._read_u32()
        self.offset += 4
        if meta_len == 0:
            return {}
        meta_data = bytes(b ^ 0x63 for b in self.raw[self.offset : self.offset + meta_len])
        self.offset += meta_len
        payload = base64.b64decode(meta_data[22:])
        text = aes_ecb_decrypt(payload, MODIFY_KEY).decode("utf-8", errors="replace")
        prefix, _, body = text.partition(":")
        obj = json.loads(body) if body else {}
        if prefix == "dj" and isinstance(obj, dict):
            obj = obj.get("mainMusic", {})
        return obj if isinstance(obj, dict) else {}

    def _get_cover(self) -> bytes | None:
        if self.offset + 13 > len(self.raw):
            return None
        cover_size = self._read_u32(self.offset + 5)
        cover_start = self.offset + 13
        cover_end = cover_start + cover_size
        self.offset = cover_end
        if cover_size <= 0 or cover_end > len(self.raw):
            return None
        cover = self.raw[cover_start:cover_end]
        return cover or None

    def _get_audio(self, key_box: list[int]) -> bytes:
        audio = self.raw[self.offset :]
        L = len(audio)
        if L == 0:
            return b""
        keystream = (bytes(key_box) * (L // 256 + 1))[:L]
        audio_int = int.from_bytes(audio, "big")
        key_int = int.from_bytes(keystream, "big")
        decrypted_int = audio_int ^ key_int
        return decrypted_int.to_bytes(L, "big")

    def decode(self) -> tuple[bytes, dict[str, Any], str, bytes | None]:
        key_box = self._get_key_box()
        self.meta = self._get_metadata()
        cover = self._get_cover()
        audio = self._get_audio(key_box)
        ext = str(self.meta.get("format") or detect_audio_ext(audio)).lower()
        return audio, self.meta, ext, cover
