"""Fail-closed Git release-transition gate for immutable published evidence.

A valid manifest alone cannot detect a previously approved release that was
removed by merging a stale independent data branch. This tool compares the
candidate merge tree against the *current* base branch publication registry.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import PurePosixPath
import re
import subprocess

from tools.release_registry import valid_id
from tools.governance_transition import (check_review_transition, check_revisions,
                                         check_changeset_transition)


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



def check_geography_transition(before:dict|None, after:dict|None,
                               old_blobs:dict[str,str],
                               new_blobs:dict[str,str])->dict:
    """Additive-only history for independent county reference geometries."""
    if before is None and after is None:
        if old_blobs or new_blobs:
            raise ValueError("Unindexed geography blobs cannot exist without an approved registry")
        return {"previousGeographies":0,"proposedGeographies":0,"newGeographies":[]}
    if before is not None and before.get("publicationStatus")!="published":
        raise ValueError("Invalid historical approved geography status")
    if after is None or after.get("publicationStatus")!="published":
        raise ValueError("Approved geography index was removed or made unpublishable")
    old=entries(before) if before is not None else {}
    new=entries(after)
    if not old.keys() <= new.keys():
        raise ValueError("Rejected: approved geography release removed")
    for rid,prior in old.items():
        if new[rid]!=prior:
            raise ValueError("Rejected: approved geography release entry mutated: "+rid)
        prefix=f"publication/geographies/releases/{rid}/"
        old_files={k:v for k,v in old_blobs.items() if k.startswith(prefix)}
        new_files={k:v for k,v in new_blobs.items() if k.startswith(prefix)}
        if not old_files or old_files!=new_files:
            raise ValueError("Rejected: immutable approved geography files mutated: "+rid)
    additions=new.keys()-old.keys()
    for rid in additions:
        prefix=f"publication/geographies/releases/{rid}/"
        if (new[rid].get("manifestPath")!=prefix+"manifest.json"
                or new[rid].get("geometryPath")!=prefix+"counties.geojson"
                or not {"manifest.json","counties.geojson","original.zip"}
                    <= {p.removeprefix(prefix) for p in new_blobs if p.startswith(prefix)}):
            raise ValueError("New geography release missing canonical source or geometry")
    for name in new_blobs:
        parts=PurePosixPath(name).parts
        if (len(parts)<5 or parts[:3]!=("publication","geographies","releases")
                or parts[3] not in new):
            raise ValueError("Unregistered geography release artifact: "+name)
        if name not in old_blobs and parts[3] not in additions:
            raise ValueError("Cannot add to an immutable geography release directory")
    return {"previousGeographies":len(old),"proposedGeographies":len(new),
            "newGeographies":sorted(additions)}

def git_bytes(*args: str) -> bytes:
    proc=subprocess.run(("git",*args),check=False,capture_output=True)
    if proc.returncode:
        raise RuntimeError("Failed to read Git publication history")
    return proc.stdout


def git_blobs(ref: str, directory: str="publication/releases") -> dict[str,str]:
    output=git_bytes("ls-tree","-rz","--full-tree",ref,"--",directory)
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


def git_optional_geography_index(ref: str) -> dict|None:
    location="publication/geographies/index.json"
    exists=git_bytes("ls-tree","--name-only",ref,"--",location)
    if not exists.strip():
        return None
    return json.loads(git_bytes("show",f"{ref}:{location}"))


def git_optional_json(ref: str, path: str) -> dict | None:
    exists = git_bytes("ls-tree", "--name-only", ref, "--", path)
    return json.loads(git_bytes("show", f"{ref}:{path}")) if exists.strip() else None


def git_release_document(ref: str, rid: str, filename: str) -> dict:
    if not valid_id(rid) or filename not in ("manifest.json", "observations.json"):
        raise ValueError("Unsafe release-document lookup")
    return json.loads(git_bytes("show", f"{ref}:publication/releases/{rid}/{filename}"))


def verify_source_commit_references(governance: dict) -> None:
    """Require the cited source commit to actually contain these exact manifest bytes."""
    for path in governance["decisionPaths"]:
        decision = json.loads(git_bytes("show", "HEAD:" + path))
        rid, kind, source = (decision["releaseId"], decision["publicationKind"],
                             decision["sourceCommit"])
        if not valid_id(rid) or not re.fullmatch(r"[0-9a-f]{40}", source):
            raise ValueError("Untrusted immutable review provenance")
        folder = ("publication/releases/" if kind == "indicator" else
                  "publication/geographies/releases/")
        manifest_path = folder + rid + "/manifest.json"
        previous = git_bytes("show", f"{source}:{manifest_path}")
        current = git_bytes("show", "HEAD:" + manifest_path)
        digest = decision["manifestSha256"]
        if (hashlib.sha256(previous).hexdigest() != digest or
                hashlib.sha256(current).hexdigest() != digest or
                previous != current):
            raise ValueError("Review record references changed or unavailable source commit")


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base",default="origin/main")
    args=parser.parse_args()
    if not re.fullmatch(r"origin/[a-z0-9][a-z0-9-]{0,80}",args.base):
        parser.error("Unsupported Git base ref")
    result=check_transition(git_index(args.base),git_index("HEAD"),
                            git_blobs(args.base),git_blobs("HEAD"))
    result.update(check_geography_transition(
        git_optional_geography_index(args.base),git_optional_geography_index("HEAD"),
        git_blobs(args.base,"publication/geographies/releases"),
        git_blobs("HEAD","publication/geographies/releases")))
    old_governance = git_optional_json(args.base, "governance/index.json")
    new_governance = git_optional_json("HEAD", "governance/index.json")
    if new_governance is None:
        raise ValueError("The append-only review ledger must exist")
    result.update(check_review_transition(
        old_governance, new_governance,
        git_blobs(args.base, "governance/decisions"),
        git_blobs("HEAD", "governance/decisions")))
    result.update(check_revisions(
        git_index(args.base), git_index("HEAD"),
        lambda rid: git_release_document(args.base, rid, "manifest.json"),
        lambda rid: git_release_document("HEAD", rid, "manifest.json"),
        lambda rid: git_release_document(args.base, rid, "observations.json"),
        lambda rid: git_release_document("HEAD", rid, "observations.json"),
        lambda path: git_optional_json("HEAD", path)))
    result.update(check_changeset_transition(
        git_blobs(args.base, "governance/changesets"),
        git_blobs("HEAD", "governance/changesets")))
    verify_source_commit_references(new_governance)
    print(json.dumps(result,sort_keys=True))


if __name__=="__main__":
    main()
