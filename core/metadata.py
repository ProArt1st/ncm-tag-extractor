from __future__ import annotations

import base64
import io
import json
import re
import sys
from pathlib import Path
from typing import Any

import mutagen
from mutagen.flac import FLAC, Picture
from mutagen.id3 import (
    APIC,
    ID3,
    TALB,
    TDRC,
    TIT2,
    TPE1,
    TPE2,
    TPOS,
    TPUB,
    TRCK,
    USLT,
    ID3NoHeaderError,
)
from mutagen.mp3 import MP3

from core.decoder import MODIFY_KEY, aes_ecb_decrypt


def detect_image_mime(data: bytes) -> str:
    """Detect MIME type from image binary header."""
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith(b"GIF87a") or data.startswith(b"GIF89a"):
        return "image/gif"
    if data.startswith(b"BM"):
        return "image/bmp"
    return "image/jpeg"


def sanitize_filename(name: str) -> str:
    """Sanitize string for file name compatibility."""
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


def extract_artists(meta: dict[str, Any]) -> list[str]:
    """Extract list of artist names from NCM JSON metadata."""
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


def split_artist_value(value: str | None) -> list[str]:
    """Split concatenated artist string into individual names."""
    if not value:
        return []
    for sep in [";", "；"]:
        if sep in value:
            return [part.strip() for part in value.split(sep) if part.strip()]
    return [part.strip() for part in re.split(r"\s*,\s*|\s+&\s+", value) if part.strip()]


def infer_tags_from_filename(path: Path) -> tuple[str | None, list[str]]:
    """Infer song title and artists from filename (Title - Artist)."""
    stem = path.stem.strip()
    if " - " not in stem:
        return stem or None, []
    title, artist_text = stem.rsplit(" - ", 1)
    return title.strip() or None, split_artist_value(artist_text)


def extract_music_id_from_163_key(value: str) -> tuple[int | str | None, dict[str, Any] | None]:
    """Decrypt 163 key comment to extract musicId and embedded metadata."""
    if not value:
        return None, None
    value = value.strip()
    prefix_str = "163 key(Don't modify):"
    if not value.startswith(prefix_str):
        return None, None
    try:
        b64_data = value[len(prefix_str) :].strip()
        payload = base64.b64decode(b64_data)
        decrypted = aes_ecb_decrypt(payload, MODIFY_KEY)
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


def update_flac_metadata(
    flac_data: bytes,
    title: str | None,
    album: str | None,
    artists: list[str],
    image_data: bytes | None,
    extra_tags: dict[str, str] | None = None,
) -> tuple[bytes, bool]:
    """Update FLAC tags using Mutagen."""
    bio = io.BytesIO(flac_data)
    try:
        audio = FLAC(bio)
    except Exception:
        return flac_data, False

    # Filter out unwanted keys & blacklisted encoder/comment fields
    blacklisted_keys = {"COMMENT", "DESCRIPTION", "URL", "WWW", "WWWAUDIOFILE", "ENCODER", "ENCODEDBY"}
    for key in list(audio.keys()):
        key_upper = key.upper()
        if key_upper in blacklisted_keys:
            del audio[key]
        elif key_upper == "PUBLISHER":
            val = audio[key]
            del audio[key]
            audio["ORGANIZATION"] = val

    # Set Title & Album
    if title:
        audio["TITLE"] = [title]
    if album:
        audio["ALBUM"] = [album]

    # Set Artists
    if artists:
        clean_artists = [a.strip() for a in artists if a.strip()]
        if clean_artists:
            audio["ARTIST"] = clean_artists

    # Set Extra Tags (NetEase API tags)
    if extra_tags:
        for k, v in extra_tags.items():
            k_upper = k.upper()
            val_clean = v.strip()
            if not val_clean:
                continue
            if k_upper == "PUBLISHER":
                audio["ORGANIZATION"] = [val_clean]
            elif k_upper in {"ARTIST", "ALBUMARTIST"}:
                parts = split_artist_value(val_clean)
                if parts:
                    audio[k_upper] = parts
            elif k_upper not in {"COVER_URL"}:
                audio[k_upper] = [val_clean]

    # Set Picture / Cover Art
    if image_data:
        audio.clear_pictures()
        pic = Picture()
        pic.type = 3  # Cover (front)
        pic.mime = detect_image_mime(image_data)
        pic.data = image_data
        audio.add_picture(pic)

    bio.seek(0)
    audio.save(bio)
    return bio.getvalue(), True


def update_mp3_metadata(
    mp3_data: bytes,
    extra_tags: dict[str, str] | None = None,
    title: str | None = None,
    album: str | None = None,
    artists: list[str] | None = None,
    cover_data: bytes | None = None,
) -> tuple[bytes, bool]:
    """Update MP3 ID3v2 tags using Mutagen."""
    extra_tags = extra_tags or {}
    
    try:
        tags = ID3(io.BytesIO(mp3_data))
    except (ID3NoHeaderError, Exception):
        tags = ID3()

    # Blacklisted frames removal (Comments, URLs, Encoder frames)
    remove_prefixes = ("COMM", "WXXX", "WOAR", "WOAS", "WOAF", "WWW", "TENC", "TSSE")
    keys_to_delete = [k for k in tags.keys() if k.startswith(remove_prefixes)]

    # Remove requested overwrite keys
    if title:
        keys_to_delete.extend([k for k in tags.keys() if k.startswith("TIT2")])
    if album:
        keys_to_delete.extend([k for k in tags.keys() if k.startswith("TALB")])
    if artists:
        keys_to_delete.extend([k for k in tags.keys() if k.startswith("TPE1")])
    if cover_data:
        keys_to_delete.extend([k for k in tags.keys() if k.startswith("APIC")])

    if "ALBUMARTIST" in extra_tags:
        keys_to_delete.extend([k for k in tags.keys() if k.startswith("TPE2")])
    if "DATE" in extra_tags:
        keys_to_delete.extend([k for k in tags.keys() if k.startswith(("TDRC", "TYER"))])
    if "TRACKNUMBER" in extra_tags:
        keys_to_delete.extend([k for k in tags.keys() if k.startswith("TRCK")])
    if "DISCNUMBER" in extra_tags:
        keys_to_delete.extend([k for k in tags.keys() if k.startswith("TPOS")])
    if "LYRICS" in extra_tags:
        keys_to_delete.extend([k for k in tags.keys() if k.startswith("USLT")])
    if "ORGANIZATION" in extra_tags:
        keys_to_delete.extend([k for k in tags.keys() if k.startswith("TPUB")])

    for k in keys_to_delete:
        tags.delall(k)

    # Set Title
    if title:
        tags.add(TIT2(encoding=3, text=[title]))

    # Set Album
    if album:
        tags.add(TALB(encoding=3, text=[album]))

    # Set Artists
    if artists:
        clean_artists = [a.strip() for a in artists if a.strip()]
        if clean_artists:
            tags.add(TPE1(encoding=3, text=clean_artists))

    # Set Album Artist
    if "ALBUMARTIST" in extra_tags:
        parts = split_artist_value(extra_tags["ALBUMARTIST"])
        if parts:
            tags.add(TPE2(encoding=3, text=parts))

    # Set Date
    if "DATE" in extra_tags:
        tags.add(TDRC(encoding=3, text=[extra_tags["DATE"]]))

    # Set Track Number / Track Total
    if "TRACKNUMBER" in extra_tags:
        track_str = extra_tags["TRACKNUMBER"]
        if extra_tags.get("TRACKTOTAL"):
            track_str += f"/{extra_tags['TRACKTOTAL']}"
        tags.add(TRCK(encoding=3, text=[track_str]))

    # Set Disc Number / Disc Total
    if "DISCNUMBER" in extra_tags:
        disc_str = extra_tags["DISCNUMBER"]
        if extra_tags.get("DISCTOTAL"):
            disc_str += f"/{extra_tags['DISCTOTAL']}"
        tags.add(TPOS(encoding=3, text=[disc_str]))

    # Set Lyrics
    if "LYRICS" in extra_tags and extra_tags["LYRICS"].strip():
        tags.add(USLT(encoding=3, lang="eng", desc="", text=extra_tags["LYRICS"]))

    # Set Publisher / Organization
    if "ORGANIZATION" in extra_tags and extra_tags["ORGANIZATION"].strip():
        tags.add(TPUB(encoding=3, text=[extra_tags["ORGANIZATION"].strip()]))

    # Set APIC Cover Art
    if cover_data:
        tags.add(
            APIC(
                encoding=3,
                mime=detect_image_mime(cover_data),
                type=3,  # Cover (front)
                desc="",
                data=cover_data,
            )
        )

    # Save ID3 tags to a clean memory buffer
    tag_bio = io.BytesIO()
    tags.save(tag_bio, v2_version=4)
    new_id3_bytes = tag_bio.getvalue()

    # Safely separate original audio frames from old ID3 headers
    audio_start = 0
    if mp3_data.startswith(b"ID3") and len(mp3_data) >= 10:
        size_bytes = mp3_data[6:10]
        tag_size = (
            (size_bytes[0] & 0x7F) << 21
            | (size_bytes[1] & 0x7F) << 14
            | (size_bytes[2] & 0x7F) << 7
            | (size_bytes[3] & 0x7F)
        )
        audio_start = 10 + tag_size
        if audio_start > len(mp3_data):
            audio_start = 0

    audio_payload = mp3_data[audio_start:]

    # Remove old ID3v1 footer if present
    if len(audio_payload) >= 128 and audio_payload[-128:-125] == b"TAG":
        audio_payload = audio_payload[:-128]

    return new_id3_bytes + audio_payload, True


def get_audio_comments(data: bytes, ext: str) -> dict[str, str]:
    """Extract comment key-value dictionary from FLAC or MP3 binary data."""
    comments: dict[str, str] = {}
    bio = io.BytesIO(data)
    ext = ext.lower().lstrip(".")

    if ext == "flac":
        try:
            audio = FLAC(bio)
            for k, v_list in audio.items():
                k_upper = k.upper()
                v_str = ";".join(v_list)
                if k_upper in comments:
                    comments[k_upper] += ";" + v_str
                else:
                    comments[k_upper] = v_str
        except Exception:
            pass
    elif ext == "mp3":
        try:
            tags = ID3(bio)
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
            }
            for frame in tags.values():
                fid = frame.FrameID
                frame_text_str = (
                    ";".join(str(val) for val in frame.text)
                    if hasattr(frame, "text") and isinstance(frame.text, list)
                    else str(getattr(frame, "text", ""))
                )
                if fid == "USLT":
                    comments["LYRICS"] = frame_text_str
                elif fid == "COMM":
                    if frame_text_str.strip().startswith("163 key(Don't modify):") or "COMMENT" not in comments:
                        comments["COMMENT"] = frame_text_str
                elif fid == "WXXX":
                    comments["URL"] = str(getattr(frame, "url", ""))
                key = text_map.get(fid)
                if key:
                    text_val = frame_text_str
                    if fid == "TRCK":
                        n, _, t = text_val.partition("/")
                        if n.strip():
                            comments["TRACKNUMBER"] = n.strip()
                        if t.strip():
                            comments["TRACKTOTAL"] = t.strip()
                    elif fid == "TPOS":
                        n, _, t = text_val.partition("/")
                        if n.strip():
                            comments["DISCNUMBER"] = n.strip()
                        if t.strip():
                            comments["DISCTOTAL"] = t.strip()
                    elif text_val:
                        if key in comments:
                            comments[key] += ";" + text_val
                        else:
                            comments[key] = text_val
        except Exception:
            pass

    return comments
