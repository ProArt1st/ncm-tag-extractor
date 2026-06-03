#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import json
import re
import struct
import sys
import time
import tomllib
from dataclasses import dataclass
from datetime import date, datetime, time as date_time
from pathlib import Path
from typing import Iterable
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen


CORE_KEY = bytes.fromhex("687a4852416d736f356b496e62617857")
MODIFY_KEY = bytes.fromhex("2331346C6A6B5F215C5D2630553C2728")
NCM_MAGIC = b"CTENFDAM"
DEFAULT_CONFIG_NAME = "ncm_to_audio_config.toml"
NETEASE_TAGS_CACHE: dict[int | str, dict[str, str]] = {}
COVER_IMAGE_CACHE: dict[str, bytes | None] = {}


def _rot_word(word: int) -> int:
    return ((word << 8) & 0xFFFFFFFF) | (word >> 24)


def _sub_word(word: int, sbox: list[int]) -> int:
    return (
        (sbox[(word >> 24) & 0xFF] << 24)
        | (sbox[(word >> 16) & 0xFF] << 16)
        | (sbox[(word >> 8) & 0xFF] << 8)
        | sbox[word & 0xFF]
    )


def _gf_mul(a: int, b: int) -> int:
    res = 0
    for _ in range(8):
        if b & 1:
            res ^= a
        hi = a & 0x80
        a = (a << 1) & 0xFF
        if hi:
            a ^= 0x1B
        b >>= 1
    return res


def _gf_pow(a: int, n: int) -> int:
    res = 1
    while n:
        if n & 1:
            res = _gf_mul(res, a)
        a = _gf_mul(a, a)
        n >>= 1
    return res


def _build_aes_tables() -> tuple[list[int], list[int]]:
    sbox = [0] * 256
    inv_sbox = [0] * 256
    for i in range(256):
        inv = 0 if i == 0 else _gf_pow(i, 254)
        x = inv
        s = x ^ ((x << 1) | (x >> 7)) ^ ((x << 2) | (x >> 6)) ^ ((x << 3) | (x >> 5)) ^ ((x << 4) | (x >> 4))
        s = (s & 0xFF) ^ 0x63
        sbox[i] = s
        inv_sbox[s] = i
    return sbox, inv_sbox


SBOX, INV_SBOX = _build_aes_tables()
RCON = [0x01]
for _ in range(1, 10):
    RCON.append(_gf_mul(RCON[-1], 0x02))


class AES128ECB:
    def __init__(self, key: bytes) -> None:
        if len(key) != 16:
            raise ValueError("AES-128 key must be 16 bytes")
        self.round_keys = self._expand_key(key)

    def _expand_key(self, key: bytes) -> list[list[int]]:
        words = [int.from_bytes(key[i : i + 4], "big") for i in range(0, 16, 4)]
        for i in range(4, 44):
            temp = words[i - 1]
            if i % 4 == 0:
                temp = _sub_word(_rot_word(temp), SBOX) ^ (RCON[i // 4 - 1] << 24)
            words.append(words[i - 4] ^ temp)
        round_keys = []
        for i in range(0, 44, 4):
            rk = []
            for word in words[i : i + 4]:
                rk.extend(word.to_bytes(4, "big"))
            round_keys.append(rk)
        return round_keys

    @staticmethod
    def _add_round_key(state: list[int], round_key: list[int]) -> None:
        for i in range(16):
            state[i] ^= round_key[i]

    @staticmethod
    def _inv_shift_rows(state: list[int]) -> None:
        state[1], state[5], state[9], state[13] = state[13], state[1], state[5], state[9]
        state[2], state[6], state[10], state[14] = state[10], state[14], state[2], state[6]
        state[3], state[7], state[11], state[15] = state[7], state[11], state[15], state[3]

    @staticmethod
    def _inv_sub_bytes(state: list[int]) -> None:
        for i in range(16):
            state[i] = INV_SBOX[state[i]]

    @staticmethod
    def _inv_mix_columns(state: list[int]) -> None:
        for col in range(4):
            i = col * 4
            a0, a1, a2, a3 = state[i : i + 4]
            state[i + 0] = _gf_mul(a0, 14) ^ _gf_mul(a1, 11) ^ _gf_mul(a2, 13) ^ _gf_mul(a3, 9)
            state[i + 1] = _gf_mul(a0, 9) ^ _gf_mul(a1, 14) ^ _gf_mul(a2, 11) ^ _gf_mul(a3, 13)
            state[i + 2] = _gf_mul(a0, 13) ^ _gf_mul(a1, 9) ^ _gf_mul(a2, 14) ^ _gf_mul(a3, 11)
            state[i + 3] = _gf_mul(a0, 11) ^ _gf_mul(a1, 13) ^ _gf_mul(a2, 9) ^ _gf_mul(a3, 14)

    def decrypt_block(self, block: bytes) -> bytes:
        if len(block) != 16:
            raise ValueError("AES block must be 16 bytes")
        state = list(block)
        self._add_round_key(state, self.round_keys[10])
        for round_idx in range(9, 0, -1):
            self._inv_shift_rows(state)
            self._inv_sub_bytes(state)
            self._add_round_key(state, self.round_keys[round_idx])
            self._inv_mix_columns(state)
        self._inv_shift_rows(state)
        self._inv_sub_bytes(state)
        self._add_round_key(state, self.round_keys[0])
        return bytes(state)

    def decrypt_ecb(self, data: bytes) -> bytes:
        if len(data) % 16 != 0:
            raise ValueError("ECB ciphertext length must be a multiple of 16")
        out = bytearray()
        for i in range(0, len(data), 16):
            out.extend(self.decrypt_block(data[i : i + 16]))
        return bytes(out)


def pkcs7_unpad(data: bytes) -> bytes:
    if not data:
        raise ValueError("empty PKCS#7 payload")
    pad = data[-1]
    if pad < 1 or pad > 16 or data[-pad:] != bytes([pad]) * pad:
        raise ValueError("invalid PKCS#7 padding")
    return data[:-pad]


def aes_ecb_decrypt_padded(data: bytes, key: bytes) -> bytes:
    cipher = AES128ECB(key)
    return pkcs7_unpad(cipher.decrypt_ecb(data))


def sanitize_filename(name: str) -> str:
    replacements = {
        "<": "＜",
        ">": "＞",
        ":": "：",
        '"': "＂",
        "/": "⁄",
        "\\": "＼",
        "|": "｜",
        "?": "？",
        "*": "＊",
    }
    cleaned = "".join(replacements.get(ch, ch) for ch in name).strip().rstrip(".")
    return cleaned or "output"


def extract_artists(meta: dict) -> list[str]:
    artists: list[str] = []
    raw_artists = meta.get("artist")
    if isinstance(raw_artists, list):
        for item in raw_artists:
            if isinstance(item, list) and item:
                artist = str(item[0]).strip()
                if artist:
                    artists.append(artist)
            elif isinstance(item, str):
                artist = item.strip()
                if artist:
                    artists.append(artist)
    return artists


def join_artist_names(names: list[str]) -> str | None:
    cleaned = [name.strip() for name in names if name and name.strip()]
    return ";".join(cleaned) or None


def split_artist_value(value: str | None) -> list[str]:
    if not value:
        return []
    separators = [";", "；"]
    for sep in separators:
        if sep in value:
            return [part.strip() for part in value.split(sep) if part.strip()]
    return [part.strip() for part in re.split(r"\s*,\s*|\s+&\s+", value) if part.strip()]


def infer_tags_from_filename(path: Path) -> tuple[str | None, list[str]]:
    stem = path.stem.strip()
    if " - " not in stem:
        return stem or None, []
    title, artist_text = stem.rsplit(" - ", 1)
    return title.strip() or None, split_artist_value(artist_text)


def detect_audio_ext(data: bytes, fallback: str = "mp3") -> str:
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


def detect_image_mime(data: bytes) -> str | None:
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith(b"GIF87a") or data.startswith(b"GIF89a"):
        return "image/gif"
    if data.startswith(b"BM"):
        return "image/bmp"
    return None


def get_image_dimensions(data: bytes) -> tuple[int, int, int, int]:
    if data.startswith(b"\x89PNG\r\n\x1a\n") and len(data) >= 24:
        width = int.from_bytes(data[16:20], "big")
        height = int.from_bytes(data[20:24], "big")
        bit_depth = data[24] if len(data) > 24 else 0
        color_type = data[25] if len(data) > 25 else 0
        channels = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}.get(color_type, 0)
        depth = bit_depth * channels if channels else 0
        return width, height, depth, 0

    if data.startswith(b"\xff\xd8\xff"):
        i = 2
        while i + 9 < len(data):
            if data[i] != 0xFF:
                i += 1
                continue
            marker = data[i + 1]
            i += 2
            if marker in {0xD8, 0xD9}:
                continue
            if i + 2 > len(data):
                break
            seg_len = int.from_bytes(data[i : i + 2], "big")
            if seg_len < 2 or i + seg_len > len(data):
                break
            if marker in {
                0xC0,
                0xC1,
                0xC2,
                0xC3,
                0xC5,
                0xC6,
                0xC7,
                0xC9,
                0xCA,
                0xCB,
                0xCD,
                0xCE,
                0xCF,
            }:
                precision = data[i + 2]
                height = int.from_bytes(data[i + 3 : i + 5], "big")
                width = int.from_bytes(data[i + 5 : i + 7], "big")
                components = data[i + 7]
                return width, height, precision * components, 0
            i += seg_len

    return 0, 0, 0, 0


def build_flac_picture_block(image_data: bytes, description: str = "") -> bytes:
    mime = detect_image_mime(image_data) or "application/octet-stream"
    width, height, depth, colors = get_image_dimensions(image_data)
    desc_bytes = description.encode("utf-8")
    mime_bytes = mime.encode("ascii")

    payload = bytearray()
    payload.extend((3).to_bytes(4, "big"))
    payload.extend(len(mime_bytes).to_bytes(4, "big"))
    payload.extend(mime_bytes)
    payload.extend(len(desc_bytes).to_bytes(4, "big"))
    payload.extend(desc_bytes)
    payload.extend(width.to_bytes(4, "big"))
    payload.extend(height.to_bytes(4, "big"))
    payload.extend(depth.to_bytes(4, "big"))
    payload.extend(colors.to_bytes(4, "big"))
    payload.extend(len(image_data).to_bytes(4, "big"))
    payload.extend(image_data)
    return bytes(payload)


def parse_flac_metadata_blocks(flac_data: bytes) -> tuple[list[tuple[int, bytes]], bytes] | None:
    if not flac_data.startswith(b"fLaC"):
        return None

    pos = 4
    blocks: list[tuple[int, bytes]] = []
    while pos + 4 <= len(flac_data):
        header = flac_data[pos : pos + 4]
        pos += 4
        is_last = bool(header[0] & 0x80)
        block_type = header[0] & 0x7F
        block_len = int.from_bytes(header[1:4], "big")
        if pos + block_len > len(flac_data):
            return None
        payload = flac_data[pos : pos + block_len]
        pos += block_len
        blocks.append((block_type, payload))
        if is_last:
            break
    return blocks, flac_data[pos:]


def parse_vorbis_comment_block(payload: bytes) -> tuple[str, list[str]]:
    if len(payload) < 8:
        return "python-ncm-decoder", []
    vendor_len = int.from_bytes(payload[0:4], "little")
    pos = 4
    if pos + vendor_len > len(payload):
        return "python-ncm-decoder", []
    vendor = payload[pos : pos + vendor_len].decode("utf-8", errors="replace")
    pos += vendor_len
    if pos + 4 > len(payload):
        return vendor or "python-ncm-decoder", []
    count = int.from_bytes(payload[pos : pos + 4], "little")
    pos += 4
    comments: list[str] = []
    for _ in range(count):
        if pos + 4 > len(payload):
            break
        item_len = int.from_bytes(payload[pos : pos + 4], "little")
        pos += 4
        if pos + item_len > len(payload):
            break
        comments.append(payload[pos : pos + item_len].decode("utf-8", errors="replace"))
        pos += item_len
    return vendor or "python-ncm-decoder", comments


def build_vorbis_comment_block(vendor: str, comments: list[str]) -> bytes:
    vendor_bytes = vendor.encode("utf-8")
    out = bytearray()
    out.extend(len(vendor_bytes).to_bytes(4, "little"))
    out.extend(vendor_bytes)
    out.extend(len(comments).to_bytes(4, "little"))
    for comment in comments:
        comment_bytes = comment.encode("utf-8")
        out.extend(len(comment_bytes).to_bytes(4, "little"))
        out.extend(comment_bytes)
    return bytes(out)


def get_flac_comment_map(flac_data: bytes) -> dict[str, str]:
    parsed = parse_flac_metadata_blocks(flac_data)
    if parsed is None:
        return {}

    blocks, _audio_frames = parsed
    comments_map: dict[str, str] = {}
    for block_type, payload in blocks:
        if block_type != 4:
            continue
        _vendor, comments = parse_vorbis_comment_block(payload)
        for comment in comments:
            key, sep, value = comment.partition("=")
            if sep:
                key_upper = key.upper()
                val = value.strip()
                if key_upper in comments_map:
                    comments_map[key_upper] += ";" + val
                else:
                    comments_map[key_upper] = val
    return comments_map


def get_flac_duration_ms(flac_data: bytes) -> int | None:
    parsed = parse_flac_metadata_blocks(flac_data)
    if parsed is None:
        return None

    blocks, _audio_frames = parsed
    for block_type, payload in blocks:
        if block_type != 0 or len(payload) < 34:
            continue
        info = int.from_bytes(payload[10:18], "big")
        sample_rate = (info >> 44) & 0xFFFFF
        total_samples = info & ((1 << 36) - 1)
        if sample_rate and total_samples:
            return round(total_samples * 1000 / sample_rate)
    return None


def fetch_json(url: str, retries: int = 3, backoff: float = 2.0) -> dict:
    delay = backoff
    for attempt in range(retries):
        try:
            request = Request(
                url,
                headers={
                    "Accept": "application/json",
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                },
            )
            with urlopen(request, timeout=10) as response:
                return json.loads(response.read().decode("utf-8"))
        except (URLError, HTTPError, OSError) as e:
            if isinstance(e, HTTPError) and e.code == 404:
                raise e
            if attempt == retries - 1:
                raise e
            print(f"  [重试] API 请求失败 (第 {attempt + 1}/{retries} 次尝试): {e}。将在 {delay} 秒后重试...", file=sys.stderr)
            time.sleep(delay)
            delay *= 2
    raise URLError("Max retries exceeded")


def extract_music_id_from_163_key(value: str) -> tuple[int | str | None, dict | None]:
    if not value:
        return None, None
    value = value.strip()
    prefix_str = "163 key(Don't modify):"
    if not value.startswith(prefix_str):
        return None, None
    try:
        b64_data = value[len(prefix_str):].strip()
        payload = base64.b64decode(b64_data)
        decrypted = aes_ecb_decrypt_padded(payload, MODIFY_KEY)
        text = decrypted.decode("utf-8", errors="replace")
        prefix, _, body = text.partition(":")
        obj = json.loads(body) if body else {}
        if prefix == "dj" and isinstance(obj, dict):
            obj = obj.get("mainMusic", {})
        if isinstance(obj, dict):
            music_id = obj.get("musicId")
            return music_id, obj
    except Exception as e:
        print(f"Warning: Failed to decrypt 163 key: {e}", file=sys.stderr)
    return None, None


def download_image(url: str, retries: int = 3, backoff: float = 2.0) -> bytes | None:
    if not url:
        return None
    url = url.partition("?")[0].strip()
    if url in COVER_IMAGE_CACHE:
        return COVER_IMAGE_CACHE[url]
    time.sleep(0.3)  # Anti-scraping rate limiting delay
    delay = backoff
    for attempt in range(retries):
        try:
            request = Request(
                url,
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                },
            )
            with urlopen(request, timeout=15) as response:
                data = response.read()
                COVER_IMAGE_CACHE[url] = data
                return data
        except (URLError, HTTPError, OSError) as e:
            if isinstance(e, HTTPError) and e.code == 404:
                break
            if attempt == retries - 1:
                print(f"Warning: Failed to download cover image from {url} after {retries} attempts: {e}", file=sys.stderr)
                break
            print(f"  [重试] 封面下载失败 (第 {attempt + 1}/{retries} 次尝试): {e}。将在 {delay} 秒后重试...", file=sys.stderr)
            time.sleep(delay)
            delay *= 2
            
    COVER_IMAGE_CACHE[url] = None
    return None


def build_apic_payload(image_data: bytes) -> bytes:
    mime = detect_image_mime(image_data) or "image/jpeg"
    mime_bytes = mime.encode("ascii")
    # Text encoding: 3 (UTF-8), MIME type (terminated with null), Picture type: 3 (Cover front), Description (empty UTF-8 -> single null)
    return bytes([3]) + mime_bytes + b"\x00" + bytes([3]) + b"\x00" + image_data


def merge_bilingual_lyrics(lyric_text: str, tlyric_text: str) -> str:
    if not lyric_text:
        return ""
    if not tlyric_text:
        return lyric_text

    from collections import defaultdict
    import re

    # Pattern to match standard timestamp like [00:15.186] or [00:15.18]
    pattern = re.compile(r"^\[(\d+):(\d+(?:\.\d+)?)]")
    
    def parse_lyric_lines(text: str) -> list[tuple[str, int, str]]:
        lines = []
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            match = pattern.match(line)
            if match:
                m = int(match.group(1))
                s_val = match.group(2)
                # Convert to milliseconds
                s_part, _, ms_part = s_val.partition(".")
                s = int(s_part)
                ms = 0
                if ms_part:
                    ms_part = ms_part[:3].ljust(3, '0')
                    ms = int(ms_part)
                time_ms = (m * 60 + s) * 1000 + ms
                content = line[match.end():].strip()
                if not content:
                    continue
                timestamp_str = line[:match.end()]
                lines.append((timestamp_str, time_ms, content))
            else:
                tag_match = re.match(r"^\[([a-zA-Z]+):(.*)]", line)
                if tag_match:
                    lines.append((line, -1, ""))
                else:
                    lines.append(("", -2, line))
        return lines

    original_lines = parse_lyric_lines(lyric_text)
    translation_lines = parse_lyric_lines(tlyric_text)

    # Group translation contents by time_ms
    trans_map = defaultdict(list)
    for _, time_ms, content in translation_lines:
        if time_ms >= 0 and content:
            trans_map[time_ms].append(content)

    merged_lines = []
    for timestamp_str, time_ms, content in original_lines:
        if time_ms < 0:
            merged_lines.append(timestamp_str)
        elif time_ms == -2:
            merged_lines.append(content)
        else:
            merged_lines.append(f"{timestamp_str}{content}")
            if time_ms in trans_map:
                for trans_content in trans_map[time_ms]:
                    merged_lines.append(f"{timestamp_str}{trans_content}")
                del trans_map[time_ms]

    # Append any translation lines that didn't match original timestamps (if any)
    if trans_map:
        leftovers = sorted(
            [(t_str, t_ms, c) for t_str, t_ms, c in translation_lines if t_ms in trans_map],
            key=lambda x: x[1]
        )
        for t_str, t_ms, c in leftovers:
            merged_lines.append(f"{t_str}{c}")

    return "\n".join(merged_lines)


def fetch_netease_tags(music_id: int | str, title: str | None = None) -> dict[str, str]:
    if not music_id:
        return {}
    if music_id in NETEASE_TAGS_CACHE:
        return dict(NETEASE_TAGS_CACHE[music_id])
    time.sleep(0.3)  # Anti-scraping rate limiting delay
    url = f"http://music.163.com/api/song/detail?ids=[{music_id}]"
    try:
        data = fetch_json(url)
        songs = data.get("songs")
        if isinstance(songs, list) and songs:
            song = songs[0]
            tags = {}
            
            # 1. Album Artist
            album = song.get("album") or {}
            album_artists = []
            for item in album.get("artists") or []:
                if isinstance(item, dict):
                    name = str(item.get("name") or "").strip()
                    if name:
                        album_artists.append(name)
            joined_album_artists = ";".join(album_artists)
            if joined_album_artists:
                tags["ALBUMARTIST"] = joined_album_artists
            
            # 2. Date / Year
            publish_time = album.get("publishTime")
            if publish_time:
                try:
                    dt = datetime.fromtimestamp(int(publish_time) / 1000.0)
                    tags["DATE"] = dt.strftime("%Y-%m-%d")
                except (ValueError, TypeError):
                    pass
            
            # 3. Track number
            song_name = song.get("name") or "未知歌曲"
            track_no = song.get("no")
            if track_no not in (None, ""):
                try:
                    track_val = int(track_no)
                    if track_val < 1:
                        print(f"  [修正] 歌曲《{song_name}》(ID: {music_id}) 的音轨号为 {track_no}，已修正为 1。")
                        track_no = "1"
                    else:
                        track_no = str(track_val)
                except (ValueError, TypeError):
                    pass
                tags["TRACKNUMBER"] = str(track_no)
                
            # 4. Track total
            track_total = album.get("size")
            if track_total not in (None, ""):
                tags["TRACKTOTAL"] = str(track_total)
                
            # 5. Disc number
            disc = song.get("disc")
            if disc:
                try:
                    disc_val = int(disc)
                    if disc_val < 1:
                        print(f"  [修正] 歌曲《{song_name}》(ID: {music_id}) 的碟片号为 {disc}，已修正为 1。")
                        disc = "1"
                    else:
                        disc = str(disc_val)
                except (ValueError, TypeError):
                    pass
                tags["DISCNUMBER"] = str(disc)
            else:
                tags["DISCNUMBER"] = "1"
                
            tags["DISCTOTAL"] = "1"
            
            # 6. Record Company / Publisher (using ORGANIZATION for Mp3tag compatibility in FLAC)
            company = album.get("company")
            if company and str(company).strip():
                tags["ORGANIZATION"] = str(company).strip()
                
            # 7. Album Cover URL
            pic_url = album.get("picUrl")
            if pic_url and pic_url.strip():
                tags["COVER_URL"] = pic_url.strip()

            
            # Fetch and merge lyrics
            try:
                lyric_url = f"http://music.163.com/api/song/lyric?id={music_id}&lv=-1&tv=-1"
                lyric_data = fetch_json(lyric_url)
                lrc = lyric_data.get("lrc", {}).get("lyric", "")
                tlyric = lyric_data.get("tlyric", {}).get("lyric", "")
                merged_lrc = merge_bilingual_lyrics(lrc, tlyric)
                if merged_lrc:
                    tags["LYRICS"] = merged_lrc
            except Exception as e:
                print(f"Warning: Failed to fetch lyrics for music_id {music_id}: {e}", file=sys.stderr)
            
            NETEASE_TAGS_CACHE[music_id] = tags
            return dict(tags)
        else:
            name_str = f"《{title}》" if title else ""
            print(f"  [提示] 歌曲{name_str}(ID: {music_id}) 在网易云已无版权或已下架，无法获取详细元数据。")
    except Exception as e:
        print(f"Error fetching NetEase tags for music_id {music_id}: {e}", file=sys.stderr)
    NETEASE_TAGS_CACHE[music_id] = {}
    return {}


def update_flac_metadata(
    flac_data: bytes,
    title: str | None,
    album: str | None,
    artists: list[str],
    image_data: bytes | None,
    extra_tags: dict[str, str] | None = None,
) -> tuple[bytes, bool]:
    parsed = parse_flac_metadata_blocks(flac_data)
    if parsed is None:
        return flac_data, False

    blocks, audio_frames = parsed
    vendor = "python-ncm-decoder"
    other_comments: list[str] = []
    rebuilt_blocks: list[tuple[int, bytes]] = []
    changed = False
    reserved_keys: set[str] = set()
    if title:
        reserved_keys.add("TITLE")
    if album:
        reserved_keys.add("ALBUM")
    if artists:
        reserved_keys.add("ARTIST")
    if extra_tags:
        for key in extra_tags:
            key_upper = key.upper()
            reserved_keys.add(key_upper)
            if key_upper == "PUBLISHER":
                reserved_keys.add("ORGANIZATION")

    for block_type, payload in blocks:
        if block_type == 4:
            existing_vendor, comments = parse_vorbis_comment_block(payload)
            vendor = existing_vendor or vendor
            for comment in comments:
                key = comment.split("=", 1)[0].upper()
                if key in {"COMMENT", "DESCRIPTION", "URL", "WWW", "WWWAUDIOFILE"}:
                    continue
                if key == "PUBLISHER":
                    val = comment.split("=", 1)[1]
                    comment = f"ORGANIZATION={val}"
                    key = "ORGANIZATION"
                elif key == "ENCODER":
                    val = comment.split("=", 1)[1]
                    comment = f"ENCODEDBY={val}"
                    key = "ENCODEDBY"
                if key not in reserved_keys:
                    other_comments.append(comment)
            changed = True
        elif block_type == 6 and image_data:
            changed = True
        else:
            rebuilt_blocks.append((block_type, payload))

    new_comments = list(other_comments)
    if title:
        new_comments.append(f"TITLE={title}")
    if album:
        new_comments.append(f"ALBUM={album}")
    if artists:
        for artist in artists:
            if artist.strip():
                new_comments.append(f"ARTIST={artist.strip()}")
    if extra_tags:
        for key, value in extra_tags.items():
            cleaned_value = value.strip()
            if cleaned_value:
                flac_key = "ORGANIZATION" if key.upper() == "PUBLISHER" else key.upper()
                if flac_key in {"ARTIST", "ALBUMARTIST"}:
                    parts = split_artist_value(cleaned_value)
                    for part in parts:
                        new_comments.append(f"{flac_key}={part}")
                else:
                    new_comments.append(f"{flac_key}={cleaned_value}")
    rebuilt_blocks.append((4, build_vorbis_comment_block(vendor, new_comments)))

    if image_data:
        rebuilt_blocks.append((6, build_flac_picture_block(image_data)))
        changed = True

    rebuilt = bytearray(b"fLaC")
    for index, (block_type, payload) in enumerate(rebuilt_blocks):
        is_last = index == len(rebuilt_blocks) - 1
        if len(payload) >= (1 << 24):
            return flac_data, changed
        rebuilt.append((0x80 if is_last else 0x00) | (block_type & 0x7F))
        rebuilt.extend(len(payload).to_bytes(3, "big"))
        rebuilt.extend(payload)
    rebuilt.extend(audio_frames)
    return bytes(rebuilt), True


def embed_flac_picture(flac_data: bytes, image_data: bytes) -> bytes:
    updated, _ = update_flac_metadata(flac_data, None, None, [], image_data)
    return updated


def write_flac_tags(
    flac_data: bytes,
    title: str | None,
    album: str | None,
    artists: list[str],
    image_data: bytes | None,
    extra_tags: dict[str, str] | None = None,
) -> tuple[bytes, bool]:
    return update_flac_metadata(flac_data, title, album, artists, image_data, extra_tags=extra_tags)


def syncsafe_to_int(data: bytes) -> int:
    value = 0
    for byte in data:
        value = (value << 7) | (byte & 0x7F)
    return value


def int_to_syncsafe(value: int) -> bytes:
    return bytes((value >> shift) & 0x7F for shift in (21, 14, 7, 0))


def decode_id3_text(payload: bytes) -> str:
    if not payload:
        return ""
    encoding = payload[0]
    data = payload[1:]
    if encoding == 0:
        text = data.decode("latin-1", errors="replace").rstrip("\x00")
    elif encoding == 1:
        text = data.decode("utf-16", errors="replace").rstrip("\x00")
    elif encoding == 2:
        text = data.decode("utf-16-be", errors="replace").rstrip("\x00")
    else:
        text = data.decode("utf-8", errors="replace").rstrip("\x00")
    return text.replace("\x00", ";")


def decode_id3_uslt(payload: bytes) -> str:
    if len(payload) < 5:
        return ""
    encoding = payload[0]
    # Skip language (3 bytes at indices 1, 2, 3)
    pos = 4
    # Find null terminator for descriptor
    if encoding in {0, 3}:  # Latin-1, UTF-8
        idx = payload.find(b"\x00", pos)
        if idx != -1:
            pos = idx + 1
    elif encoding in {1, 2}:  # UTF-16, UTF-16-BE
        # Find double null character (aligned to 2 bytes)
        while pos + 1 < len(payload):
            if payload[pos : pos + 2] == b"\x00\x00":
                pos += 2
                break
            pos += 2
            
    data = payload[pos:]
    if encoding == 0:
        return data.decode("latin-1", errors="replace").rstrip("\x00")
    if encoding == 1:
        return data.decode("utf-16", errors="replace").rstrip("\x00")
    if encoding == 2:
        return data.decode("utf-16-be", errors="replace").rstrip("\x00")
    return data.decode("utf-8", errors="replace").rstrip("\x00")


def encode_id3_text(value: str) -> bytes:
    return bytes([3]) + value.encode("utf-8")


def parse_id3v2(mp3_data: bytes) -> tuple[dict[str, str], list[tuple[str, bytes]], int]:
    if len(mp3_data) < 10 or not mp3_data.startswith(b"ID3"):
        return {}, [], 0

    version = mp3_data[3]
    tag_size = syncsafe_to_int(mp3_data[6:10])
    tag_end = min(10 + tag_size, len(mp3_data))
    if version not in {3, 4}:
        return {}, [], tag_end

    pos = 10
    frames: list[tuple[str, bytes]] = []
    comments: dict[str, str] = {}
    text_map = {
        "TIT2": "TITLE",
        "TPE1": "ARTIST",
        "TALB": "ALBUM",
        "TPE2": "ALBUMARTIST",
        "TDRC": "DATE",
        "TYER": "DATE",
        "TRCK": "TRACKNUMBER",
        "TPOS": "DISCNUMBER",
        "TPUB": "ORGANIZATION",
        "TENC": "ENCODEDBY",
        "TSSE": "ENCODEDBY",
    }

    while pos + 10 <= tag_end:
        frame_id = mp3_data[pos : pos + 4].decode("latin-1", errors="replace")
        if not frame_id.strip("\x00"):
            break
        raw_size = mp3_data[pos + 4 : pos + 8]
        frame_size = syncsafe_to_int(raw_size) if version == 4 else int.from_bytes(raw_size, "big")
        payload_start = pos + 10
        payload_end = payload_start + frame_size
        if frame_size < 0 or payload_end > tag_end:
            break
        payload = mp3_data[payload_start:payload_end]
        frames.append((frame_id, payload))
        if frame_id == "USLT":
            lyrics_text = decode_id3_uslt(payload)
            if lyrics_text:
                comments["LYRICS"] = lyrics_text
        elif frame_id == "COMM":
            comm_text = decode_id3_uslt(payload)
            if comm_text:
                comments["COMMENT"] = comm_text
        elif frame_id == "WXXX":
            if len(payload) >= 2:
                encoding = payload[0]
                pos = 1
                if encoding in {0, 3}:
                    idx = payload.find(b"\x00", pos)
                    if idx != -1:
                        pos = idx + 1
                elif encoding in {1, 2}:
                    while pos + 1 < len(payload):
                        if payload[pos : pos + 2] == b"\x00\x00":
                            pos += 2
                            break
                        pos += 2
                url_str = payload[pos:].decode("latin-1", errors="replace").rstrip("\x00")
                if url_str:
                    comments["URL"] = url_str
        key = text_map.get(frame_id)
        if key:
            text = decode_id3_text(payload)
            if frame_id == "TRCK":
                number, _, total = text.partition("/")
                if number.strip():
                    comments["TRACKNUMBER"] = number.strip()
                if total.strip():
                    comments["TRACKTOTAL"] = total.strip()
            elif frame_id == "TPOS":
                number, _, total = text.partition("/")
                if number.strip():
                    comments["DISCNUMBER"] = number.strip()
                if total.strip():
                    comments["DISCTOTAL"] = total.strip()
            elif text:
                if key in comments:
                    comments[key] += ";" + text
                else:
                    comments[key] = text
        pos = payload_end

    return comments, frames, tag_end


def build_id3_frame(frame_id: str, payload: bytes) -> bytes:
    return frame_id.encode("latin-1") + int_to_syncsafe(len(payload)) + b"\x00\x00" + payload


def update_mp3_metadata(
    mp3_data: bytes,
    extra_tags: dict[str, str],
    title: str | None = None,
    album: str | None = None,
    artists: list[str] | None = None,
    cover_data: bytes | None = None,
) -> tuple[bytes, bool]:
    has_id3v1 = len(mp3_data) >= 128 and mp3_data[-128:-125] == b"TAG"
    if not extra_tags and not title and not album and not artists and not cover_data and not has_id3v1:
        return mp3_data, False

    _comments, frames, audio_start = parse_id3v2(mp3_data)
    frame_map = {
        "TITLE": "TIT2",
        "ARTIST": "TPE1",
        "ALBUM": "TALB",
        "ALBUMARTIST": "TPE2",
        "DATE": "TDRC",
        "TRACKNUMBER": "TRCK",
        "DISCNUMBER": "TPOS",
        "LYRICS": "USLT",
        "ORGANIZATION": "TPUB",
        "ENCODEDBY": "TENC",
        "ENCODER": "TSSE",
    }
    requested_keys = set(extra_tags)
    if title:
        requested_keys.add("TITLE")
    if artists:
        requested_keys.add("ARTIST")
    if album:
        requested_keys.add("ALBUM")
    remove_ids = {frame_map[key] for key in requested_keys if key in frame_map}
    remove_ids.update({"TYER"} if "DATE" in extra_tags else set())
    remove_ids.update({"COMM", "WXXX", "WOAR", "WOAS", "WOAF", "WWW"})  # 强行过滤评论与URL网址帧
    if cover_data:
        remove_ids.add("APIC")
    rebuilt_frames = [(frame_id, payload) for frame_id, payload in frames if frame_id not in remove_ids]

    if title:
        rebuilt_frames.append(("TIT2", encode_id3_text(title)))
    if artists:
        for artist in artists:
            if artist.strip():
                rebuilt_frames.append(("TPE1", encode_id3_text(artist.strip())))
    if album:
        rebuilt_frames.append(("TALB", encode_id3_text(album)))
    if "ALBUMARTIST" in extra_tags:
        parts = split_artist_value(extra_tags["ALBUMARTIST"])
        for part in parts:
            rebuilt_frames.append(("TPE2", encode_id3_text(part)))
    if "DATE" in extra_tags:
        rebuilt_frames.append(("TDRC", encode_id3_text(extra_tags["DATE"])))
    if "TRACKNUMBER" in extra_tags:
        track_text = extra_tags["TRACKNUMBER"]
        if extra_tags.get("TRACKTOTAL"):
            track_text += f"/{extra_tags['TRACKTOTAL']}"
        rebuilt_frames.append(("TRCK", encode_id3_text(track_text)))
    if "DISCNUMBER" in extra_tags:
        disc_text = extra_tags["DISCNUMBER"]
        if extra_tags.get("DISCTOTAL"):
            disc_text += f"/{extra_tags['DISCTOTAL']}"
        rebuilt_frames.append(("TPOS", encode_id3_text(disc_text)))
    if "LYRICS" in extra_tags:
        lyric_val = extra_tags["LYRICS"]
        if lyric_val.strip():
            lyric_payload = bytes([3]) + b"eng" + b"\x00" + lyric_val.encode("utf-8")
            rebuilt_frames.append(("USLT", lyric_payload))
    if "ORGANIZATION" in extra_tags:
        pub_val = extra_tags["ORGANIZATION"]
        if pub_val.strip():
            rebuilt_frames.append(("TPUB", encode_id3_text(pub_val)))
    if "ENCODEDBY" in extra_tags:
        enc_val = extra_tags["ENCODEDBY"]
        if enc_val.strip():
            rebuilt_frames.append(("TENC", encode_id3_text(enc_val)))
    if "ENCODER" in extra_tags:
        enc_val = extra_tags["ENCODER"]
        if enc_val.strip():
            rebuilt_frames.append(("TSSE", encode_id3_text(enc_val)))

    # 如果原文件只含 TSSE，没有 TENC，则自动将 TSSE 转换为 TENC (对应 Encoded By)
    has_tenc = any(fid == "TENC" for fid, _ in rebuilt_frames)
    if not has_tenc:
        for idx, (fid, payload) in enumerate(rebuilt_frames):
            if fid == "TSSE":
                rebuilt_frames[idx] = ("TENC", payload)
                break

    if cover_data:
        rebuilt_frames.append(("APIC", build_apic_payload(cover_data)))

    body = bytearray()
    for frame_id, payload in rebuilt_frames:
        if len(frame_id) == 4 and payload:
            body.extend(build_id3_frame(frame_id, payload))
    header = b"ID3" + bytes([4, 0, 0]) + int_to_syncsafe(len(body))
    
    audio_payload = mp3_data[audio_start:]
    if len(audio_payload) >= 128 and audio_payload[-128:-125] == b"TAG":
        audio_payload = audio_payload[:-128]
        
    return header + bytes(body) + audio_payload, True


ALBUM_ARTIST_COMMENT_KEYS = {"ALBUMARTIST", "ALBUM ARTIST", "ALBUM_ARTIST", "ALBUMARTISTS", "ALBUM ARTISTS", "ALBUM_ARTISTS"}


def get_first_comment_value(comments: dict[str, str], keys: set[str]) -> str | None:
    for key in keys:
        value = comments.get(key)
        if value and value.strip():
            return value.strip()
    return None


def has_album_artist_tag(comments: dict[str, str]) -> bool:
    return get_first_comment_value(comments, ALBUM_ARTIST_COMMENT_KEYS) is not None


def missing_supplemental_tag_keys(comments: dict[str, str]) -> set[str]:
    wanted = {"ALBUMARTIST", "DATE", "TRACKNUMBER", "TRACKTOTAL", "DISCNUMBER", "DISCTOTAL"}
    missing = {key for key in wanted if not comments.get(key, "").strip()}
    if has_album_artist_tag(comments):
        missing.discard("ALBUMARTIST")
    return missing


@dataclass
class NCMResult:
    source: Path
    output: Path
    ext: str
    title: str | None
    artist: str | None
    album: str | None
    cover_embedded: bool = False
    tags_written: bool = False
    netease_attempted: bool = False
    netease_tags: dict[str, str] | None = None
    netease_missing: list[str] | None = None
    warnings: list[str] | None = None


class NCMDecoder:
    def __init__(self, raw: bytes, filename: str) -> None:
        if raw[:8] != NCM_MAGIC:
            raise ValueError("invalid NCM header")
        self.raw = raw
        self.filename = filename
        self.offset = 10
        self.meta: dict = {}

    def _read_u32(self, offset: int | None = None) -> int:
        offset = self.offset if offset is None else offset
        return struct.unpack_from("<I", self.raw, offset)[0]

    def _get_key_data(self) -> bytes:
        key_len = self._read_u32()
        self.offset += 4
        key_data = bytes(b ^ 0x64 for b in self.raw[self.offset : self.offset + key_len])
        self.offset += key_len
        return aes_ecb_decrypt_padded(key_data, CORE_KEY)[17:]

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

    def _get_metadata(self) -> dict:
        meta_len = self._read_u32()
        self.offset += 4
        if meta_len == 0:
            return {}
        meta_data = bytes(b ^ 0x63 for b in self.raw[self.offset : self.offset + meta_len])
        self.offset += meta_len
        payload = base64.b64decode(meta_data[22:])
        text = aes_ecb_decrypt_padded(payload, MODIFY_KEY).decode("utf-8", errors="replace")
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

    def decode(self) -> tuple[bytes, dict, str, bytes | None]:
        key_box = self._get_key_box()
        self.meta = self._get_metadata()
        cover = self._get_cover()
        audio = self._get_audio(key_box)
        ext = str(self.meta.get("format") or detect_audio_ext(audio)).lower()
        return audio, self.meta, ext, cover


def pick_output_name(source: Path, title: str | None, artists: list[str], ext: str) -> str:
    title_text = (title or source.stem).strip()
    artist_text = ",".join(artist.strip() for artist in artists if artist and artist.strip())
    if artist_text:
        base_name = f"{title_text} - {artist_text}"
    else:
        base_name = title_text
    return sanitize_filename(base_name) + f".{ext}"


def decode_file(path: Path, output_dir: Path, enrich_netease: bool = False) -> NCMResult:
    decoder = NCMDecoder(path.read_bytes(), path.name)
    audio, meta, ext, cover = decoder.decode()
    cover_embedded = False
    tags_written = False
    netease_attempted = False
    netease_tags = None
    netease_missing = None
    title = str(meta.get("musicName") or "") or None
    album = str(meta.get("album") or "") or None
    artists = extract_artists(meta)
    music_id = meta.get("musicId")

    cover_data = cover
    if ext == "flac":
        extra_tags = None
        if enrich_netease and music_id:
            netease_attempted = True
            extra_tags = fetch_netease_tags(music_id, title=title)
            wanted = {"ALBUMARTIST", "DATE", "TRACKNUMBER", "TRACKTOTAL", "DISCNUMBER", "DISCTOTAL"}
            netease_missing = [key for key in wanted if not extra_tags.get(key)]
            netease_tags = dict(extra_tags)
            if extra_tags and "COVER_URL" in extra_tags:
                downloaded = download_image(extra_tags["COVER_URL"])
                if downloaded:
                    cover_data = downloaded
            if extra_tags:
                extra_tags.pop("COVER_URL", None)
        audio, changed = write_flac_tags(audio, title, album, artists, cover_data, extra_tags=extra_tags)
        tags_written = changed
        cover_embedded = changed and cover_data is not None
    elif ext == "mp3":
        extra_tags = {}
        if enrich_netease and music_id:
            netease_attempted = True
            extra_tags = fetch_netease_tags(music_id, title=title)
            wanted = {"ALBUMARTIST", "DATE", "TRACKNUMBER", "TRACKTOTAL", "DISCNUMBER", "DISCTOTAL"}
            netease_missing = [key for key in wanted if not extra_tags.get(key)]
            netease_tags = dict(extra_tags)
            if extra_tags and "COVER_URL" in extra_tags:
                downloaded = download_image(extra_tags["COVER_URL"])
                if downloaded:
                    cover_data = downloaded
            if extra_tags:
                extra_tags.pop("COVER_URL", None)
        audio, changed = update_mp3_metadata(audio, extra_tags, title=title, album=album, artists=artists, cover_data=cover_data)
        tags_written = changed
        cover_embedded = changed and cover_data is not None

    output_name = pick_output_name(path, title, artists, ext)
    output_path = output_dir / output_name
    output_path.write_bytes(audio)

    warnings = []
    if not title:
        warnings.append("歌曲名")
    if not artists:
        warnings.append("艺人")
    if not album:
        warnings.append("专辑名")
    if cover is None or len(cover) == 0:
        warnings.append("封面数据")

    return NCMResult(
        source=path,
        output=output_path,
        ext=ext,
        title=title,
        artist=";".join(artists) if artists else None,
        album=album,
        cover_embedded=cover_embedded,
        tags_written=tags_written,
        netease_attempted=netease_attempted,
        netease_tags=netease_tags,
        netease_missing=netease_missing,
        warnings=warnings,
    )


def process_audio_file(path: Path, output_dir: Path, enrich_netease: bool = False) -> NCMResult:
    data = path.read_bytes()
    ext = path.suffix.lower().lstrip(".")
    comments = {}

    if ext == "flac":
        comments = get_flac_comment_map(data)
    elif ext == "mp3":
        comments, _frames, _audio_start = parse_id3v2(data)

    # Check for 163 key in comments
    key_value = None
    if ext == "flac":
        key_value = comments.get("DESCRIPTION") or comments.get("COMMENT")
    elif ext == "mp3":
        key_value = comments.get("COMMENT")

    music_id = None
    key_meta = None
    is_163_key = False
    if key_value and key_value.strip().startswith("163 key(Don't modify):"):
        is_163_key = True
        music_id, key_meta = extract_music_id_from_163_key(key_value)

    inferred_title, inferred_artists = infer_tags_from_filename(path)
    
    meta_title = str(key_meta.get("musicName") or "") or None if key_meta else None
    meta_album = str(key_meta.get("album") or "") or None if key_meta else None
    meta_artists = extract_artists(key_meta) if key_meta else []

    title = meta_title or comments.get("TITLE") or inferred_title
    album = meta_album or comments.get("ALBUM") or None
    artists = meta_artists or split_artist_value(comments.get("ARTIST")) or inferred_artists

    tags_written = False
    netease_attempted = False
    netease_tags = None
    netease_missing = None
    cover_data = None
    cover_embedded = False

    if is_163_key:
        extra_tags = {}
        if enrich_netease and music_id:
            netease_attempted = True
            extra_tags = fetch_netease_tags(music_id, title=title)
            wanted = {"ALBUMARTIST", "DATE", "TRACKNUMBER", "TRACKTOTAL", "DISCNUMBER", "DISCTOTAL"}
            netease_missing = [key for key in wanted if not extra_tags.get(key)]
            netease_tags = dict(extra_tags)
            if extra_tags and "COVER_URL" in extra_tags:
                downloaded = download_image(extra_tags["COVER_URL"])
                if downloaded:
                    cover_data = downloaded
            if extra_tags:
                extra_tags.pop("COVER_URL", None)
        
        if ext == "flac":
            data, changed = write_flac_tags(data, title, album, artists, cover_data, extra_tags=extra_tags or None)
            tags_written = changed
            cover_embedded = changed and cover_data is not None
        elif ext == "mp3":
            data, changed = update_mp3_metadata(data, extra_tags, title=title, album=album, artists=artists, cover_data=cover_data)
            tags_written = changed
            cover_embedded = changed and cover_data is not None

    output_path = output_dir / path.name
    if output_path.resolve() != path.resolve() or tags_written:
        output_path.write_bytes(data)

    warnings = []
    if not title:
        warnings.append("歌曲名")
    if not artists:
        warnings.append("艺人")
    if not album:
        warnings.append("专辑名")

    return NCMResult(
        source=path,
        output=output_path,
        ext=ext,
        title=title,
        artist=";".join(artists) if artists else None,
        album=album,
        cover_embedded=cover_embedded,
        tags_written=tags_written,
        netease_attempted=netease_attempted,
        netease_tags=netease_tags,
        netease_missing=netease_missing,
        warnings=warnings,
    )


def iter_media_files(paths: Iterable[Path], recursive: bool, extensions: set[str], sort_by: str = "name") -> list[Path]:
    files: list[Path] = []
    for path in paths:
        if path.is_file() and path.suffix.lower() in extensions:
            files.append(path)
        elif path.is_dir():
            for ext in sorted(extensions):
                pattern = f"**/*{ext}" if recursive else f"*{ext}"
                files.extend(sorted(path.glob(pattern)))
    seen: set[Path] = set()
    uniq = []
    for f in files:
        resolved = f.resolve()
        if resolved not in seen:
            seen.add(resolved)
            uniq.append(f)
    if sort_by == "mtime":
        uniq.sort(key=lambda f: (f.stat().st_mtime, str(f).casefold()))
    elif sort_by == "mtime_desc":
        uniq.sort(key=lambda f: (-f.stat().st_mtime, str(f).casefold()))
    elif sort_by == "name":
        uniq.sort(key=lambda f: str(f).casefold())
    else:
        raise ValueError('sort_by 只能是 "name"、"mtime" 或 "mtime_desc"')
    return uniq


def prompt_run_mode() -> str:
    print("请选择模式：")
    print("1. 仅转换 NCM")
    print("2. 转换 NCM 并从网易云音乐补充元数据信息")
    while True:
        try:
            choice = input("请输入 1 或 2：").strip()
        except EOFError:
            return "1"
        if choice in {"1", "2"}:
            return choice
        print("请输入 1 或 2。")


def write_netease_failure_log(log_dir: Path, failures: list[tuple[str, list[str]]]) -> Path:
    log_path = log_dir / "netease_failed.txt"
    lines = ["网易云音乐信息获取失败或不完整的文件", ""]
    if failures:
        for filename, missing in failures:
            missing_text = ", ".join(missing) if missing else "未获取到信息"
            lines.append(f"{filename}：{missing_text}")
    else:
        lines.append("无失败记录。")
    log_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return log_path


def load_config(config_path: Path) -> dict:
    if not config_path.is_file():
        return {}
    with config_path.open("rb") as fp:
        data = tomllib.load(fp)
    if not isinstance(data, dict):
        raise ValueError("配置文件根对象必须是 TOML table")
    return data


def coerce_path_list(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        paths: list[str] = []
        for item in value:
            if not isinstance(item, str):
                raise ValueError("input_dirs / input_paths 只能包含字符串路径")
            paths.append(item)
        return paths
    raise ValueError("input_dirs / input_paths 必须是字符串或字符串数组")


def resolve_config_path(path_text: str, base_dir: Path) -> Path:
    path = Path(path_text).expanduser()
    if path.is_absolute():
        return path.resolve()
    return (base_dir / path).resolve()


def config_bool(value: object, default: bool = False, name: str = "配置项") -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().casefold()
        if lowered in {"1", "true", "yes", "y", "on"}:
            return True
        if lowered in {"0", "false", "no", "n", "off"}:
            return False
    raise ValueError(f"{name} 必须是 true/false")


def parse_config_mtime(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool):
        raise ValueError("process_after_mtime 不能是 true/false")
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, datetime):
        return value.timestamp()
    if isinstance(value, date):
        return datetime.combine(value, date_time.min).timestamp()
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        try:
            return datetime.fromisoformat(text).timestamp()
        except ValueError as exc:
            raise ValueError("process_after_mtime 必须为空，或形如 2026-04-29 18:30:00") from exc
    raise ValueError("process_after_mtime 必须为空、数字时间戳或日期时间字符串")


def format_config_mtime(timestamp: float) -> str:
    return datetime.fromtimestamp(timestamp).isoformat(sep=" ", timespec="microseconds")


def update_config_mtime_checkpoint(config_path: Path, timestamp: float) -> None:
    if not config_path.is_file():
        return
    line = f'process_after_mtime = "{format_config_mtime(timestamp)}"'
    text = config_path.read_text(encoding="utf-8")
    if re.search(r"(?m)^process_after_mtime\s*=", text):
        text = re.sub(r"(?m)^process_after_mtime\s*=.*$", line, text, count=1)
    else:
        text = text.rstrip() + "\n\n" + line + "\n"
    config_path.write_text(text, encoding="utf-8")


def main() -> int:
    script_dir = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description="将 NCM 文件解码为原始音频文件。")
    parser.add_argument("paths", nargs="*", default=None, help="NCM 文件或目录，默认为脚本所在目录。")
    parser.add_argument("--config", default=str(script_dir / DEFAULT_CONFIG_NAME), help="TOML 配置文件路径。")
    parser.add_argument("--no-config", action="store_true", help="忽略 TOML 配置文件。")
    parser.add_argument("-o", "--output-dir", default=None, help="输出目录，默认为脚本所在目录。")
    parser.add_argument("-r", "--recursive", action="store_true", help="递归搜索目录。")
    args = parser.parse_args()

    config_path = Path(args.config).expanduser().resolve()
    config = {} if args.no_config else load_config(config_path)
    config_dir = config_path.parent

    config_output_dir = config.get("output_dir")
    if args.output_dir:
        output_dir = Path(args.output_dir).expanduser().resolve()
    elif isinstance(config_output_dir, str) and config_output_dir.strip():
        output_dir = resolve_config_path(config_output_dir, config_dir)
    else:
        output_dir = script_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    run_mode = prompt_run_mode()
    enrich_netease = run_mode == "2"
    extensions = {".ncm", ".flac", ".mp3"} if enrich_netease else {".ncm"}

    sort_by = str(config.get("sort_by") or "name").strip().casefold()
    only_process_failed = not args.no_config and config_bool(config.get("only_process_failed"), default=False, name="only_process_failed")
    failed_list_path = script_dir / "failed_list.txt"
    files = []

    if only_process_failed and failed_list_path.is_file():
        try:
            lines = failed_list_path.read_text(encoding="utf-8").splitlines()
            for line in lines:
                line = line.strip()
                if line:
                    p = Path(line).resolve()
                    if p.is_file():
                        files.append(p)
            print(f"已启用只处理失败文件选项，从 {failed_list_path.name} 加载了 {len(files)} 个待重试文件。")
        except Exception as e:
            print(f"读取失败文件列表出错: {e}", file=sys.stderr)

    if not files:
        if args.paths:
            search_paths = [Path(p).expanduser().resolve() for p in args.paths]
        else:
            config_inputs = coerce_path_list(config.get("input_dirs")) + coerce_path_list(config.get("input_paths"))
            search_paths = [resolve_config_path(path_text, config_dir) for path_text in config_inputs] or [script_dir]
        recursive = args.recursive or config_bool(config.get("recursive"), default=False, name="recursive")
        files = iter_media_files(search_paths, recursive=recursive, extensions=extensions, sort_by=sort_by)
        process_after_mtime = None if args.no_config else parse_config_mtime(config.get("process_after_mtime"))
        if process_after_mtime is not None:
            files = [file for file in files if file.stat().st_mtime > process_after_mtime]
    if not files:
        wanted = "、".join(sorted(extensions))
        print(f"未找到可处理文件（{wanted}）。", file=sys.stderr)
        try:
            input("按回车退出程序...")
        except EOFError:
            pass
        return 1

    failures = 0
    successes = 0
    failed_names: list[str] = []
    failed_paths: list[Path] = []
    netease_failed: list[tuple[str, list[str]]] = []
    auto_update_mtime = (
        not args.no_config
        and sort_by == "mtime"
        and config_bool(config.get("auto_update_process_after_mtime"), default=False, name="auto_update_process_after_mtime")
    )
    checkpoint_mtime: float | None = None
    checkpoint_blocked = False
    for file in files:
        try:
            if file.suffix.lower() == ".ncm":
                result = decode_file(file, output_dir, enrich_netease=enrich_netease)
            else:
                result = process_audio_file(file, output_dir, enrich_netease=enrich_netease)

            if result.netease_attempted and result.netease_missing:
                netease_failed.append((file.name, result.netease_missing))
                failures += 1
                checkpoint_blocked = True
                failed_names.append(file.name)
                failed_paths.append(file.resolve())
                print(f"{file.name}：失败（网易云信息不完整：{', '.join(result.netease_missing)}）", file=sys.stderr)
                continue

            successes += 1
            if auto_update_mtime and not checkpoint_blocked:
                file_mtime = file.stat().st_mtime
                checkpoint_mtime = file_mtime if checkpoint_mtime is None else max(checkpoint_mtime, file_mtime)

            if enrich_netease and result.netease_attempted:
                print(f"{file.name}：成功（已补充网易云元数据）")
            elif enrich_netease:
                print(f"{file.name}：成功（无需补充）")
            else:
                print(f"{file.name}：成功")

            if result.warnings:
                print(f"  [警告] 缺失信息：{', '.join(result.warnings)}")


        except Exception as exc:
            failures += 1
            checkpoint_blocked = True
            failed_names.append(file.name)
            failed_paths.append(file.resolve())
            print(f"{file.name}：失败 - {exc}", file=sys.stderr)

    print("")
    print(f"成功：{successes}")
    print(f"失败：{failures}")
    if failed_names:
        print("失败的文件：")
        for name in failed_names:
            print(f"- {name}")


    if auto_update_mtime and checkpoint_mtime is not None:
        update_config_mtime_checkpoint(config_path, checkpoint_mtime)
        print(f"已更新处理起点时间：{format_config_mtime(checkpoint_mtime)}")

    # Write or delete failed_list.txt
    if failed_paths:
        try:
            failed_list_path.write_text("\n".join(str(p) for p in failed_paths) + "\n", encoding="utf-8")
            print(f"已更新失败文件列表：{failed_list_path}")
        except Exception as e:
            print(f"写入失败文件列表出错: {e}", file=sys.stderr)
    else:
        if failed_list_path.is_file():
            try:
                failed_list_path.unlink()
                print("所有文件处理成功，已清除失败文件列表。")
            except Exception as e:
                try:
                    failed_list_path.write_text("", encoding="utf-8")
                except:
                    pass

    try:
        input("按回车退出程序...")
    except EOFError:
        pass

    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
