from __future__ import annotations

import re
import sys
import time
from collections import defaultdict
from datetime import datetime
from typing import Any

import httpx

NETEASE_TAGS_CACHE: dict[int | str, dict[str, str]] = {}
COVER_IMAGE_CACHE: dict[str, bytes | None] = {}

HEADERS = {
    "Accept": "application/json",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
}


def merge_bilingual_lyrics(lyric_text: str, tlyric_text: str) -> str:
    """Merge original and translated lyrics by millisecond timestamps, filtering empty lines."""
    if not lyric_text:
        return ""
    if not tlyric_text:
        return lyric_text

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
                s_part, _, ms_part = s_val.partition(".")
                s = int(s_part)
                ms = int(ms_part[:3].ljust(3, "0")) if ms_part else 0
                time_ms = (m * 60 + s) * 1000 + ms
                content = line[match.end() :].strip()
                if not content:
                    continue
                timestamp_str = line[: match.end()]
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

    if trans_map:
        leftovers = sorted(
            [(t_str, t_ms, c) for t_str, t_ms, c in translation_lines if t_ms in trans_map],
            key=lambda x: x[1],
        )
        for t_str, t_ms, c in leftovers:
            merged_lines.append(f"{t_str}{c}")

    return "\n".join(merged_lines)


class NetEaseClient:
    """HTTP client for NetEase Cloud Music API powered by HTTPX."""

    def __init__(self, retries: int = 3, backoff: float = 2.0) -> None:
        self.retries = retries
        self.backoff = backoff
        self.client = httpx.Client(headers=HEADERS, timeout=10.0, follow_redirects=True)

    def fetch_json(self, url: str) -> dict[str, Any]:
        delay = self.backoff
        for attempt in range(self.retries):
            try:
                resp = self.client.get(url)
                if resp.status_code == 404:
                    raise httpx.HTTPStatusError("404 Not Found", request=resp.request, response=resp)
                resp.raise_for_status()
                return resp.json()
            except (httpx.HTTPError, OSError) as e:
                if isinstance(e, httpx.HTTPStatusError) and e.response.status_code == 404:
                    raise e
                if attempt == self.retries - 1:
                    raise e
                print(f"  [重试] API 请求失败 (第 {attempt + 1}/{self.retries} 次尝试): {e}。将在 {delay} 秒后重试...", file=sys.stderr)
                time.sleep(delay)
                delay *= 2
        raise RuntimeError("Max retries exceeded")

    def download_image(self, url: str) -> bytes | None:
        if not url:
            return None
        url = url.partition("?")[0].strip()
        if url in COVER_IMAGE_CACHE:
            return COVER_IMAGE_CACHE[url]

        time.sleep(0.3)  # Anti-scraping delay
        delay = self.backoff
        for attempt in range(self.retries):
            try:
                resp = self.client.get(url, timeout=15.0)
                if resp.status_code == 404:
                    break
                resp.raise_for_status()
                data = resp.content
                COVER_IMAGE_CACHE[url] = data
                return data
            except (httpx.HTTPError, OSError) as e:
                if isinstance(e, httpx.HTTPStatusError) and e.response.status_code == 404:
                    break
                if attempt == self.retries - 1:
                    print(f"Warning: Failed to download cover image from {url}: {e}", file=sys.stderr)
                    break
                print(f"  [重试] 封面下载失败 (第 {attempt + 1}/{self.retries} 次尝试): {e}。将在 {delay} 秒后重试...", file=sys.stderr)
                time.sleep(delay)
                delay *= 2

        COVER_IMAGE_CACHE[url] = None
        return None

    def fetch_tags(self, music_id: int | str, title: str | None = None) -> dict[str, str]:
        if not music_id:
            return {}
        if music_id in NETEASE_TAGS_CACHE:
            return dict(NETEASE_TAGS_CACHE[music_id])

        time.sleep(0.3)  # Anti-scraping delay
        url = f"http://music.163.com/api/song/detail?ids=[{music_id}]"
        try:
            data = self.fetch_json(url)
            songs = data.get("songs")
            if isinstance(songs, list) and songs:
                song = songs[0]
                tags: dict[str, str] = {}

                # Album Artist
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

                # Publish Date
                publish_time = album.get("publishTime")
                if publish_time:
                    try:
                        dt = datetime.fromtimestamp(int(publish_time) / 1000.0)
                        tags["DATE"] = dt.strftime("%Y-%m-%d")
                    except (ValueError, TypeError):
                        pass

                # Track Number (force >=1)
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

                # Track Total (force >=1)
                track_total = album.get("size")
                if track_total not in (None, ""):
                    try:
                        total_val = int(track_total)
                        if total_val <= 0:
                            print(f"  [修正] 歌曲《{song_name}》(ID: {music_id}) 的总音轨数为 {track_total}，已修正为 1。")
                            track_total = "1"
                        else:
                            track_total = str(total_val)
                    except (ValueError, TypeError):
                        pass
                    tags["TRACKTOTAL"] = str(track_total)

                # Disc Number & Total (force >=1)
                disc = song.get("disc")
                disc_val = 1
                if disc:
                    try:
                        parsed_val = int(disc)
                        if parsed_val < 1:
                            print(f"  [修正] 歌曲《{song_name}》(ID: {music_id}) 的碟片号为 {disc}，已修正为 1。")
                            disc_val = 1
                        else:
                            disc_val = parsed_val
                    except (ValueError, TypeError):
                        pass
                tags["DISCNUMBER"] = str(disc_val)
                tags["DISCTOTAL"] = str(disc_val)

                # Publisher / Organization
                company = album.get("company")
                if company and str(company).strip():
                    tags["ORGANIZATION"] = str(company).strip()

                # Album Cover URL
                pic_url = album.get("picUrl")
                if pic_url and pic_url.strip():
                    tags["COVER_URL"] = pic_url.strip()

                # Lyrics
                try:
                    lyric_url = f"http://music.163.com/api/song/lyric?id={music_id}&lv=-1&tv=-1"
                    lyric_data = self.fetch_json(lyric_url)
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
