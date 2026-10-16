"""Fail-closed Git release-transition gate for immutable published evidence.

A valid manifest alone cannot detect a previously approved release that was
removed by merging a stale independent data branch. This tool compares the
candidate merge tree against the *current* base branch publication registry.
"""
from __future__ import annotations

import argparse
import json
from pathlib import PurePosixPath
import re
import subprocess

from tools.release_registry import valid_id


def entries(index: dict) -> dict[str, dict]:
    if not isinstance(index,dict) or index.get("schemaVersion") != "1.0.0":
        raise ValueError("Malformed publication index")
    raw=index.get("releases")
    if not isinstance(raw,list):
        raise ValueError("Missing publication release array")
    result={}
    for release in raw:
        if not isinstance(release,dict) or not valid_id(release.get("releaseId")):
            raise ValueError("Untrusted publication release identity")
        name=release["releaseId"]
        if name in result:
            raise ValueError("Duplicate release identity")
        result[name]=release
    return result


def check_transition(before: dict, after: dict,
                     previous_blobs: dict[str, str],
                     proposed_blobs: dict[str, str]) -> dict:
    """Require additive releases. Disallow any edits to earlier reviewed bytes."""
    old=entries(before)
    new=entries(after)
    if before.get("publicationStatus") != "published" or after.get("publicationStatus") != "published":
        raise ValueError("Publication registry must remain published")
    deleted=old.keys()-new.keys()
    if deleted:
        raise ValueError("Rejected: approved release removed from registry: "+
                         ", ".join(sorted(deleted)))
    for rid,item in old.items():
        if new[rid]!=item:
            raise ValueError("Rejected: existing approved release index entry changed: "+rid)
        prefix=f"publication/releases/{rid}/"
        historical={key:val for key,val in previous_blobs.items()
                    if key.startswith(prefix)}
        proposed={key:val for key,val in proposed_blobs.items()
                  if key.startswith(prefix)}
        if not historical or historical != proposed:
            raise ValueError("Rejected: immutable approved source files changed: "+rid)
    additions=new.keys()-old.keys()
    for rid in additions:
        prefix=f"publication/releases/{rid}/"
        files={p for p in proposed_blobs if p.startswith(prefix)}
        if f"{prefix}manifest.json" not in files or f"{prefix}observations.json" not in files:
            raise ValueError("New release is missing its manifest or canonical observations")
        if new[rid].get("manifestPath")!=f"{prefix}manifest.json":
            raise ValueError("New release references a noncanonical manifest")
    # Only fresh release ids may add files under publication/releases.
    for name in proposed_blobs:
        if not name.startswith("publication/releases/"):
            continue
        fragments=PurePosixPath(name).parts
        if len(fragments)<4 or fragments[2] not in new:
            raise ValueError("Unregistered or malformed release blob: "+name)
        if name not in previous_blobs and fragments[2] not in additions:
            raise ValueError("Cannot add files to an approved release directory: "+name)
    return {"previousReleases":len(old),"proposedReleases":len(new),
            "newReleases":sorted(additions),"status":"approved-transition-shape"}


def git_bytes(*args: str) -> bytes:
    proc=subprocess.run(("git",*args),check=False,capture_output=True)
    if proc.returncode:
        raise RuntimeError("Failed to read Git publication history")
    return proc.stdout


def git_blobs(ref: str) -> dict[str,str]:
    output=git_bytes("ls-tree","-rz","--full-tree",ref,"--","publication/releases")
    result={}
    for item in output.split(b"\0"):
        if not item:
            continue
        try:
            head,path=item.split(b"\t",1)
            mode,kind,sha=head.decode("ascii").split(" ")
            name=path.decode("utf-8")
        except (UnicodeDecodeError,ValueError) as exc:
            raise ValueError("Invalid Git tree entry") from exc
        if kind!="blob" or mode not in ("100644","100755"):
            raise ValueError("Published evidence must be regular files")
        result[name]=sha
    return result


def git_index(ref: str) -> dict:
    blob=git_bytes("show",f"{ref}:publication/index.json")
    return json.loads(blob)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base",default="origin/main")
    args=parser.parse_args()
    if not re.fullmatch(r"origin/[a-z0-9][a-z0-9-]{0,80}",args.base):
        parser.error("Unsupported Git base ref")
    result=check_transition(git_index(args.base),git_index("HEAD"),
                            git_blobs(args.base),git_blobs("HEAD"))
    print(json.dumps(result,sort_keys=True))


if __name__=="__main__":
    main()
