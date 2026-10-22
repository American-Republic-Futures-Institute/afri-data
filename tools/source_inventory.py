"""Deterministic, extensible README inventory from reviewed source-programs and receipts.

No unverified discovered program may be promoted to "Imported" by merely
adding it to source-programs.json. Rolling source custody and published
curations remain distinct evidence categories.
"""
from __future__ import annotations
import argparse
from collections import Counter, defaultdict
from hashlib import sha1, sha256
import json
from pathlib import Path

PROGRAMS = Path("catalog/source-programs.json")
EVIDENCE = Path("catalog/source-inventory-evidence.json")
RELEASES = Path("publication/index.json")
README = Path("README.md")
START = "<!-- SOURCE-INVENTORY:BEGIN -->"
END = "<!-- SOURCE-INVENTORY:END -->"
INDICATOR_PROGRAM = {
    "state-unemployment-rate":"bls-lau",
    "county-modeled-obesity-prevalence":"cdc-places",
    "state-median-household-income":"census-acs",
    "state-resident-population":"census-popest",
    "state-federal-award-obligations":"usaspending-awards",
}


class InventoryError(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise InventoryError(message)


def mirror_program(source_id):
    """Map exact mirrored feed IDs to a registered official source program."""
    if source_id.startswith("bea-state-gdp-"):
        return "bea-regional-gdp"
    if source_id.startswith("bea-state-income-"):
        return "bea-income"
    prefixes = {
        "treasury-":"treasury-fiscaldata",
        "census-acs5-":"census-acs",
        "bls-qcew-":"bls-qcew",
        "cdc-places-":"cdc-places",
        "epa-airdata-":"epa-air",
        "eia-seds-":"eia-state-energy",
        "usgs-comcat-":"usgs-earthquakes",
        "usda-ers-":"ers-farm-finance",
    }
    for prefix, program in prefixes.items():
        if source_id.startswith(prefix):
            return program
    raise InventoryError("New imported source needs explicit program mapping: " + source_id)


def validate_programs(root):
    doc = json.loads((root / PROGRAMS).read_text("utf-8"))
    programs = doc.get("programs")
    require(type(programs) is list and 1 <= len(programs) <= 5000,
            "Source program registry missing or too large")
    ids = set()
    for item in programs:
        require(type(item) is dict and all(
            type(item.get(key)) is str and item[key] for key in
            ("id", "title", "publisherId", "domain", "url")
        ) and item["id"] not in ids and
            type(item.get("ingestionApproved")) is bool and
            item["url"].startswith("https://"),
            "Malformed or duplicate pending publisher program")
        ids.add(item["id"])
    return programs


def validated_evidence(root, programs):
    evidence = json.loads((root / EVIDENCE).read_text("utf-8"))
    ids = evidence.get("mirroredSourceIds")
    totals = evidence.get("totals")
    require(evidence.get("schemaVersion") == "1.0.0" and
            evidence.get("sourceLibraryRef") == "data/source-library" and
            type(evidence.get("sourceLibraryCommit")) is str and
            len(evidence["sourceLibraryCommit"]) == 40 and
            type(ids) is list and ids == sorted(set(ids)) and
            type(totals) is dict and totals.get("mirrored") == len(ids) and
            type(evidence.get("checkedAt")) is str,
            "Unverifiable mirrored-source inventory snapshot")
    registry = {p["id"] for p in programs}
    mapped = Counter()
    for source_id in ids:
        target = mirror_program(source_id)
        require(target in registry, "Mirrored data source not in program registry")
        mapped[target] += 1
    nass = evidence.get("nassAcquiredSourceIds", [])
    require(type(nass) is list and nass == sorted(set(nass)) and
            all(type(x) is str and x.startswith("nass-") for x in nass),
            "Invalid NASS independently verified custody")
    require(not nass or "nass-quickstats" in registry,
            "Acquired NASS program not registered")
    if nass:
        mapped["nass-quickstats"] += len(nass)
    return evidence, mapped


def publication_counts(root, programs):
    releases = json.loads((root / RELEASES).read_text("utf-8"))
    registered = {p["id"] for p in programs}
    count = Counter()
    for entry in releases.get("releases", []):
        if entry.get("status") != "published":
            continue
        program = INDICATOR_PROGRAM.get(entry.get("indicatorId"))
        require(program in registered,
                "New published indicator needs exact source-program mapping: "
                + str(entry.get("indicatorId")))
        count[program] += 1
    return count


def cell(value):
    return str(value).replace("|", "\\|").replace("\n"," ").replace("\r"," ")


def make_table(root):
    programs = validate_programs(root)
    evidence, mirrored = validated_evidence(root, programs)
    published = publication_counts(root, programs)
    total_mirrors = evidence["totals"]["mirrored"]
    groups = defaultdict(list)
    for item in programs:
        groups[item["domain"]].append(item)
    imported_programs = sum(bool(mirrored.get(p["id"])) for p in programs)
    published_programs = sum(bool(published.get(p["id"])) for p in programs)
    out = [
        START,
        "## Data source targets and acquisition status",
        "",
        "**Generated from the [reviewed program registry](catalog/source-programs.json), "
        "[source evidence snapshot](catalog/source-inventory-evidence.json), and "
        "[published release index](publication/index.json).** "
        "Never edit the statuses by hand; run `python -m tools.source_inventory --write` "
        "after updating the reviewed registry or source receipts.",
        "",
        f"- **{len(programs)} targeted source programs**; "
        f"**{total_mirrors} mirrored source feeds** from the rolling source ledger "
        f"(across {imported_programs} mapped programs); "
        f"**{published_programs} programs** have at least one curated publication.",
        f"- Source mirror evidence: "
        f"`{evidence['sourceLibraryRef']}@{evidence['sourceLibraryCommit'][:12]}` "
        f"(last checked `{evidence['checkedAt']}`). "
        "These are bounded source-native mirrors, not claims that every upstream full "
        "original archive was saved byte-for-byte.",
        "- **Imported** = an acquired source feed in the independently verified rolling "
        "source snapshot, or a curated source-backed release when marked *release only*. "
        "**Analyzed** = a source-backed curated indicator release exists; this does *not* "
        "claim independent methodological review. **Published** = listed in the "
        "ARFI publication index. **Pending** = no approved source import, or "
        "*expansion* when only a subset of a broad government program is held.",
        "- Program registration is a *discovery candidate*, not blanket ingestion approval. "
        "Source acquisition, statistical analysis and website publication remain separate.",
        "",
    ]
    for domain in sorted(groups):
        candidates = sorted(groups[domain], key=lambda x: (x["publisherId"],x["title"]))
        group_imported = sum(bool(mirrored.get(p["id"])) for p in candidates)
        out.extend([
            f"<details><summary>{cell(domain.title())} — {len(candidates)} programs; "
            f"{group_imported} with imported feeds</summary>",
            "",
            "| Target source program | Imported | Analyzed | Published | Pending |",
            "|---|---|---|---|---|",
        ])
        for item in candidates:
            id = item["id"]
            feeds, releases = mirrored.get(id,0),published.get(id,0)
            if feeds:
                imported = f"{feeds} feeds"
            elif releases:
                imported = "Release only"
            else:
                imported = "No"
            analyzed = "Curated" if releases else "No"
            publication = f"{releases} release{'s' if releases != 1 else ''}" if releases else "No"
            pending = "Expansion" if (feeds or releases) else "Yes"
            out.append(
                f"| [{cell(item['title'])}]({item['url']}) "
                f"(`{cell(id)}`) | {imported} | {analyzed} | {publication} | {pending} |"
            )
        out.extend(["","</details>",""])
    out.extend([
        "To extend coverage: add a *reviewed candidate* to "
        "`catalog/source-programs.json`; add exact import identity mapping to "
        "`tools/source_inventory.py` only when a verified original/source mirror "
        "exists; admit originals independently; then regenerate. "
        "The scheduled inventory-sync workflow proposes README updates when "
        "the rolling source ledger changes.",
        "",
        END,
    ])
    return "\n".join(out)


def render(readme, block):
    if START in readme or END in readme:
        require(readme.count(START) == readme.count(END) == 1 and
                readme.index(START) < readme.index(END),
                "README inventory markers corrupted")
        begin, finish = readme.index(START), readme.index(END)+len(END)
        return readme[:begin] + block + readme[finish:]
    anchor = "## Developer quickstart"
    require(anchor in readme, "README insertion anchor missing")
    return readme.replace(anchor, block+"\n\n"+anchor,1)


def refresh_evidence(root, source_index, ledger_path, commit, nass_manifest=None):
    """Source branch must be fetched and verified before syncing into main."""
    require(type(commit) is str and len(commit)==40 and
            all(c in "0123456789abcdef" for c in commit),
            "Missing pinned source-library Git commit")
    index = json.loads(Path(source_index).read_text("utf-8"))
    ledger = json.loads(Path(ledger_path).read_text("utf-8"))
    ids = sorted(item["id"] for item in index["datasets"])
    require(ids == sorted(set(ids)) and
            ledger["totals"]["mirrored"] == len(ids) and
            ledger["totals"]["registered"] >= len(ids) and
            ledger["totals"]["failed"] >= 0,
            "Source index / acquisition ledger are inconsistent")
    old = json.loads((root / EVIDENCE).read_text("utf-8"))
    old.update({
        "sourceLibraryCommit":commit,"checkedAt":ledger["checkedAt"],
        "totals":ledger["totals"],"mirroredSourceIds":ids,
    })
    # The original source index blob SHA is updated by GitHub sync itself,
    # not guessed from file bytes or an unverified mutable ref.
    # Preserve source-branch Git blob identities as well as independent SHA-256
    # receipts. Never silently remove an earlier publisher-evidence binding.
    source_bytes = Path(source_index).read_bytes()
    ledger_bytes = Path(ledger_path).read_bytes()
    def git_blob_sha(blob):
        return sha1(b"blob " + str(len(blob)).encode("ascii") + b"\0" + blob).hexdigest()
    old["sourceIndexBlobSha"] = git_blob_sha(source_bytes)
    old["acquisitionLedgerBlobSha"] = git_blob_sha(ledger_bytes)
    old["sourceIndexSha256"] = sha256(source_bytes).hexdigest()
    old["acquisitionLedgerSha256"] = sha256(ledger_bytes).hexdigest()
    if nass_manifest is not None:
        nass = json.loads(Path(nass_manifest).read_text("utf8"))
        require(nass.get("format") == "arfi-nass-original-api-custody-v1" and
                nass.get("publicationStatus") == "source-originals-only" and
                nass.get("noStatisticalApproval") is True and
                type(nass.get("datasets")) is list and nass["datasets"] and
                all(type(x.get("id")) is str and
                    type(x.get("latestSha256")) is str and
                    len(x["latestSha256"]) == 64 for x in nass["datasets"]),
                "NASS source manifest unqualified; require --verify on source branch")
        old["nassAcquiredSourceIds"] = sorted(x["id"] for x in nass["datasets"])
    (root / EVIDENCE).write_text(json.dumps(old,indent=2)+"\n",encoding="utf8")


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--write",action="store_true")
    p.add_argument("--check",action="store_true")
    p.add_argument("--refresh-index",type=Path)
    p.add_argument("--ledger",type=Path)
    p.add_argument("--source-commit")
    p.add_argument("--nass-manifest",type=Path)
    args = p.parse_args()
    require(args.write != args.check, "Specify exactly one of --write or --check")
    if args.refresh_index:
        require(args.write and args.ledger and args.source_commit,
                "Source evidence refresh requires pinned index, ledger and commit")
        refresh_evidence(Path("."),args.refresh_index,args.ledger,args.source_commit,
                         nass_manifest=args.nass_manifest)
    current = README.read_text("utf8")
    desired = render(current,make_table(Path(".")))
    if args.check:
        require(current == desired, "README source inventory out of date; run --write")
    elif current != desired:
        README.write_text(desired,encoding="utf8")
    print(json.dumps({"status":"verified" if args.check else "updated",
                      "trackedPrograms":len(validate_programs(Path(".")))}))


if __name__ == "__main__":
    main()
