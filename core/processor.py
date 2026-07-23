from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from core.decoder import NCMDecoder
from core.metadata import (
    extract_artists,
    extract_music_id_from_163_key,
    get_audio_comments,
    infer_tags_from_filename,
    sanitize_filename,
    split_artist_value,
    update_flac_metadata,
    update_mp3_metadata,
)
from core.netease import NetEaseClient


def pick_output_name(source: Path, title: str | None, artists: list[str], ext: str) -> str:
    """Generate sanitized output filename (Title - Artist.ext)."""
    title_text = (title or source.stem).strip()
    artist_text = ",".join(artist.strip() for artist in artists if artist and artist.strip())
    base_name = f"{title_text} - {artist_text}" if artist_text else title_text
    return sanitize_filename(base_name) + f".{ext}"


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


class BatchProcessor:
    """Batch audio conversion and metadata enrichment pipeline."""

    def __init__(self, netease_client: NetEaseClient | None = None) -> None:
        self.client = netease_client or NetEaseClient()

    def decode_file(self, path: Path, output_dir: Path, enrich_netease: bool = False) -> NCMResult:
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
        extra_tags: dict[str, str] | None = None

        if enrich_netease:
            if not music_id and title:
                music_id = self.client.search_music_id(title, artists)
            if music_id:
                netease_attempted = True
                extra_tags = self.client.fetch_tags(music_id, title=title)
                wanted = {"ALBUMARTIST", "DATE", "TRACKNUMBER", "TRACKTOTAL", "DISCNUMBER", "DISCTOTAL"}
                netease_missing = [key for key in wanted if not extra_tags.get(key)]
                netease_tags = dict(extra_tags)
                if extra_tags and "COVER_URL" in extra_tags:
                    downloaded = self.client.download_image(extra_tags["COVER_URL"])
                    if downloaded:
                        cover_data = downloaded
                if extra_tags:
                    extra_tags.pop("COVER_URL", None)

        if ext == "flac":
            audio, changed = update_flac_metadata(audio, title, album, artists, cover_data, extra_tags=extra_tags)
            tags_written = changed
            cover_embedded = changed and cover_data is not None
        elif ext == "mp3":
            audio, changed = update_mp3_metadata(
                audio, extra_tags or {}, title=title, album=album, artists=artists, cover_data=cover_data
            )
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
        if cover_data is None or len(cover_data) == 0:
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

    def process_audio_file(self, path: Path, output_dir: Path, enrich_netease: bool = False) -> NCMResult:
        data = path.read_bytes()
        ext = path.suffix.lower().lstrip(".")
        comments = get_audio_comments(data, ext)

        key_value = comments.get("DESCRIPTION") or comments.get("COMMENT")
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

        extra_tags: dict[str, str] = {}
        if enrich_netease:
            if not music_id and title:
                music_id = self.client.search_music_id(title, artists)
            if music_id:
                netease_attempted = True
                extra_tags = self.client.fetch_tags(music_id, title=title)
                wanted = {"ALBUMARTIST", "DATE", "TRACKNUMBER", "TRACKTOTAL", "DISCNUMBER", "DISCTOTAL"}
                netease_missing = [key for key in wanted if not extra_tags.get(key)]
                netease_tags = dict(extra_tags)
                if extra_tags and "COVER_URL" in extra_tags:
                    downloaded = self.client.download_image(extra_tags["COVER_URL"])
                    if downloaded:
                        cover_data = downloaded
                if extra_tags:
                    extra_tags.pop("COVER_URL", None)

        if ext == "flac":
            data, changed = update_flac_metadata(
                data, title, album, artists, cover_data, extra_tags=extra_tags or None
            )
            tags_written = changed
            cover_embedded = changed and cover_data is not None
        elif ext == "mp3":
            data, changed = update_mp3_metadata(
                data, extra_tags, title=title, album=album, artists=artists, cover_data=cover_data
            )
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

    @staticmethod
    def post_process_albums(processed_albums: dict[tuple[str, str], list[tuple[Path, int]]]) -> None:
        """Post-process batch to fix multi-disc album DISCTOTAL tag across all CDs."""
        for (album_name, album_artist), items in processed_albums.items():
            max_disc = max(disc_val for _, disc_val in items)
            if max_disc > 1:
                for out_path, disc_val in items:
                    try:
                        ext = out_path.suffix.lower().lstrip(".")
                        data = out_path.read_bytes()
                        comments = get_audio_comments(data, ext)
                        current_total = comments.get("DISCTOTAL")
                        if not current_total or current_total != str(max_disc):
                            changed = False
                            if ext == "flac":
                                updated_data, changed = update_flac_metadata(
                                    data,
                                    title=None,
                                    album=None,
                                    artists=[],
                                    image_data=None,
                                    extra_tags={"DISCTOTAL": str(max_disc)},
                                )
                            elif ext == "mp3":
                                updated_data, changed = update_mp3_metadata(
                                    data,
                                    extra_tags={"DISCTOTAL": str(max_disc)},
                                    title=None,
                                    album=None,
                                    artists=None,
                                    cover_data=None,
                                )
                            if changed:
                                out_path.write_bytes(updated_data)
                                print(f"  [修正] 总碟片数 DISCTOTAL={max_disc} ({out_path.name})")
                    except Exception as e:
                        print(f"  [警告] 修正 DISCTOTAL 失败 ({out_path.name}): {e}", file=sys.stderr)


def iter_media_files(
    paths: Iterable[Path], recursive: bool, extensions: set[str], sort_by: str = "name"
) -> list[Path]:
    """Find and sort media files in search paths."""
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
