"""Bounded discovery probe for the USDA ERS original September 2026 farm ZIP.

Not an ingestion adapter: no publisher feed or derived measure is registered.
Never infer a measurement, its unit, or historical coverage from file names.
"""
from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
from io import BytesIO, StringIO
from pathlib import PurePosixPath
import csv
import json
import re
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener
import zipfile

PUBLISHER_PAGE = ("https://www.ers.usda.gov/data-products/"
                  "farm-income-and-wealth-statistics/"
                  "data-files-us-and-state-level-farm-income-and-wealth-statistics")
SOURCE_URL = "https://www.ers.usda.gov/media/29517/september-3-2026-release.zip"
HOSTS = frozenset(("www.ers.usda.gov", "ers.usda.gov"))
MAX_ARCHIVE = 80_000_000
MAX_EXTRACTED = 200_000_000
MAX_MEMBER = 35_000_000
MAX_MEMBERS = 300
MAX_PREVIEW = 32_768
FORMAT = "usda-ers-source-archive-format-probe-v1"


class USDAProbeError(ValueError):
    pass


def require(value, message):
    if not value:
        raise USDAProbeError(message)


def safe_publisher_url(url):
    try:
        parsed = urlsplit(url)
    except ValueError:
        return False
    return (parsed.scheme == "https" and parsed.netloc in HOSTS and
            parsed.username is None and parsed.password is None and
            parsed.query == "" and parsed.fragment == "" and
            PurePosixPath(parsed.path).name.lower() == "september-3-2026-release.zip" and
            (parsed.path.startswith("/media/") or
             parsed.path.startswith("/sites/default/files/")) and
            parsed.path.lower().endswith(".zip") and
            "//" not in parsed.path and ".." not in parsed.path.split("/"))


class ExactERSRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        original = req.full_url if req is not None else ""
        require(code in (301, 302, 307, 308) and
                original == SOURCE_URL and safe_publisher_url(newurl),
                "USDA ERS redirect changed official publisher identity")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def fetch_original():
    opener = build_opener(ExactERSRedirect())
    request = Request(SOURCE_URL, headers={
        "User-Agent": "ARFI-Original-Source-Probe/1.0 (https://arfinstitute.org)",
        "Accept": "application/zip,application/octet-stream",
        "Accept-Encoding": "identity",
    })
    try:
        with opener.open(request, timeout=90) as response:
            resolved = response.geturl()
            require((resolved == SOURCE_URL or safe_publisher_url(resolved)) and
                    getattr(response, "status", 200) == 200,
                    "USDA ERS publisher response is not approved")
            content_type = response.headers.get("Content-Type", "").split(";", 1)[0].lower()
            require(content_type in ("application/zip", "application/x-zip-compressed",
                                      "application/octet-stream", "binary/octet-stream",
                                      "application/x-download", ""),
                    "USDA original archive MIME changed")
            length = response.headers.get("Content-Length")
            require(length is None or (length.isdigit() and
                    1_000 < int(length) <= MAX_ARCHIVE),
                    "USDA publisher-declared archive length out of bounds")
            raw = response.read(MAX_ARCHIVE + 1)
            require(1_000 < len(raw) <= MAX_ARCHIVE and raw[:4] == b"PK\x03\x04",
                    "USDA original archive is empty, corrupt or oversized")
            return raw, resolved
    except (HTTPError, URLError, TimeoutError, OSError) as exc:
        raise USDAProbeError("USDA ERS official original download unavailable: "+str(exc)) from exc


def inspect_original(raw, *, resolved=SOURCE_URL):
    require(type(raw) is bytes and 200 < len(raw) <= MAX_ARCHIVE and
            raw.startswith(b"PK\x03\x04") and safe_publisher_url(resolved),
            "USDA ERS source bytes or publisher URL invalid")
    try:
        with zipfile.ZipFile(BytesIO(raw)) as archive:
            infos = archive.infolist()
            require(1 <= len(infos) <= MAX_MEMBERS and
                    True,
                    "Original USDA archive is empty or has too many files")
            members = []
            total_extracted = 0
            for member in infos:
                name = member.filename.replace("\\", "/")
                path = PurePosixPath(name)
                require(member.filename == name and not path.is_absolute() and
                        ".." not in path.parts and len(name) <= 220 and
                        not any(ord(c) < 32 for c in name) and
                        not member.flag_bits & 0x1 and
                        (member.compress_type in (zipfile.ZIP_STORED,zipfile.ZIP_DEFLATED)),
                        "Unsafe USDA archive entry")
                require(0 <= member.file_size <= MAX_MEMBER and
                        0 <= member.compress_size <= MAX_ARCHIVE,
                        "USDA archive member exceeds extraction budget")
                total_extracted += member.file_size
                require(total_extracted <= MAX_EXTRACTED,
                        "USDA archive exceeds decompressed source budget")
                if member.is_dir():
                    continue
                item = {"filename": name, "uncompressedBytes": member.file_size,
                        "compressedBytes": member.compress_size,
                        "crc32": format(member.CRC, "08x")}
                if name.lower().endswith(".csv"):
                    with archive.open(member) as stream:
                        preview = stream.read(MAX_PREVIEW)
                    try:
                        text = preview.decode("utf-8-sig")
                        encoding = "utf-8-sig"
                    except UnicodeDecodeError:
                        text = preview.decode("cp1252")
                        encoding = "windows-1252"
                    lines = text.splitlines()
                    if lines:
                        header = next(csv.reader(StringIO(lines[0]), strict=True))
                        require(1 <= len(header) <= 512 and
                                len(header) == len(set(header)) and
                                all(isinstance(x,str) and 0 < len(x) <= 140 for x in header),
                                "Original USDA CSV header drift or duplicate columns")
                        item.update({"header": header, "textEncodingPreview": encoding})
                members.append(item)
            require(archive.testzip() is None, "USDA archive file CRC verification failed")
            csv_members = [x for x in members if x["filename"].lower().endswith(".csv")]
            require(csv_members, "USDA original ZIP includes no CSV members")
            return {
                "format": FORMAT,
                "publisher": "USDA Economic Research Service",
                "publisherPage": PUBLISHER_PAGE,
                "requestUrl": SOURCE_URL,
                "finalPublisherUrl": resolved,
                "originalZipSha256": sha256(raw).hexdigest(),
                "originalZipBytes": len(raw),
                "archiveEntryCount": len(infos),
                "csvEntryCount": len(csv_members),
                "uncompressedSourceBytes": total_extracted,
                "csvMembers": csv_members,
                "noDataPublished": True,
                "publisherValuesPreserved": True,
                "publicationClaimed": False,
                "probeAt": datetime.now(timezone.utc).isoformat(),
            }
    except (zipfile.BadZipFile, EOFError, UnicodeError, csv.Error) as exc:
        raise USDAProbeError("USDA ERS original source archive is not parseable") from exc


def main():
    raw, resolved = fetch_original()
    print(json.dumps(inspect_original(raw, resolved=resolved), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
