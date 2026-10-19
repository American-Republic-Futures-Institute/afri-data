"""Append-only Git transition for method review and immutable analytic releases."""
from __future__ import annotations
import argparse
import json
import re
import subprocess
from tools.release_transition import git_bytes, git_blobs


def require(ok, reason):
    if not ok:
        raise ValueError("STAT-02B.2 transition rejected: " + reason)


def index(ref, name):
    listed = git_bytes("ls-tree", "--name-only", ref, "--", name)
    if not listed.strip():
        return {"schemaVersion": "1.0.0",
                "eventPaths" if name.startswith("governance/") else "releases": []}
    return json.loads(git_bytes("show", f"{ref}:{name}"))


def check_append_only(before, after, key, old_files, new_files, prefix):
    require(isinstance(before, dict) and isinstance(after, dict) and
            before.get("schemaVersion") == after.get("schemaVersion") == "1.0.0",
            "invalid indexed transition")
    prior = before.get(key)
    proposed = after.get(key)
    require(type(prior) is list and type(proposed) is list and
            proposed[:len(prior)] == prior, "published history was edited or reordered")
    for path, sha in old_files.items():
        require(path in new_files and new_files[path] == sha,
                "immutable historical blob removed or modified: " + path)
    registered = proposed
    for path in new_files:
        require(path.startswith(prefix), "unregistered file in approved prefix")
    return registered[len(prior):]


def verify_transition(base, head="HEAD"):
    prior_methods = index(base, "governance/stat-methods/index.json")
    newer_methods = index(head, "governance/stat-methods/index.json")
    methods_old = git_blobs(base, "governance/stat-methods/events")
    methods_new = git_blobs(head, "governance/stat-methods/events")
    additions = check_append_only(prior_methods, newer_methods, "eventPaths",
                                  methods_old, methods_new,
                                  "governance/stat-methods/events/")
    expected = {"governance/stat-methods/events/" +
                p.split("/")[-1] for p in additions}
    require(set(methods_new) - set(methods_old) == expected,
            "new method decision missing from append-only index")
    # Packet review is against an exact historical PR HEAD. Once a packet has
    # appeared in repository history its bytes must be immutable as well.
    previous_packets = git_blobs(base, "governance/stat-methods/packets")
    next_packets = git_blobs(head, "governance/stat-methods/packets")
    for path, sha in previous_packets.items():
        require(next_packets.get(path) == sha,
                "reviewed statistical packet modified or removed: " + path)
    for path in next_packets:
        require(path.startswith("governance/stat-methods/packets/") and
                path.endswith(".json") and ".." not in path,
                "unsafe statistical review packet location")
    prior_publications = index(base, "publication/analytics/index.json")
    next_publications = index(head, "publication/analytics/index.json")
    old = git_blobs(base, "publication/analytics/releases")
    new = git_blobs(head, "publication/analytics/releases")
    pub_additions = check_append_only(prior_publications, next_publications,
                                      "releases", old, new,
                                      "publication/analytics/releases/")
    require(all(type(entry) is dict and
                entry.get("artifactPath") ==
                "publication/analytics/releases/" + entry.get("releaseId", "") + "/artifact.json"
                for entry in pub_additions), "new analytic entries need canonical paths")
    require(set(new) - set(old) ==
            {entry["artifactPath"] for entry in pub_additions},
            "unregistered or missing publication artifacts")

    # A founder-reviewed method is a DISTINCT, never independent, approval
    # family. Enforce the same append-only integrity as the independent ledger.
    founder_prior = index(base, "governance/stat-founder/index.json")
    founder_next = index(head, "governance/stat-founder/index.json")
    old_owner_events = git_blobs(base, "governance/stat-founder/events")
    new_owner_events = git_blobs(head, "governance/stat-founder/events")
    new_event_paths = check_append_only(
        founder_prior, founder_next, "eventPaths", old_owner_events,
        new_owner_events, "governance/stat-founder/events/")
    require(set(new_owner_events) - set(old_owner_events) ==
            set(new_event_paths), "founder events were not registered exactly once")
    owner_packets_old = git_blobs(base, "governance/stat-founder/packets")
    owner_packets_new = git_blobs(head, "governance/stat-founder/packets")
    for path, blob in owner_packets_old.items():
        require(owner_packets_new.get(path) == blob,
                "historical founder method packet edited or removed")
    require(all(path.startswith("governance/stat-founder/packets/")
                and path.endswith(".json") and ".." not in path
                for path in owner_packets_new),
            "founder packet located outside reviewed packet directory")
    founder_pub_old = index(base, "publication/analytics/founder-index.json")
    founder_pub_new = index(head, "publication/analytics/founder-index.json")
    old_owner_releases = git_blobs(base, "publication/analytics/founder-releases")
    new_owner_releases = git_blobs(head, "publication/analytics/founder-releases")
    owner_pub = check_append_only(
        founder_pub_old, founder_pub_new, "releases", old_owner_releases,
        new_owner_releases, "publication/analytics/founder-releases/")
    require(all(type(entry) is dict and
                entry.get("artifactPath") ==
                "publication/analytics/founder-releases/" +
                entry.get("releaseId", "") + "/artifact.json"
                for entry in owner_pub),
            "founder release must use canonical immutable path")
    require(set(new_owner_releases) - set(old_owner_releases) ==
            {entry["artifactPath"] for entry in owner_pub},
            "founder release missing exact registry entry")
    return {"newMethodEvents": len(additions), "newAnalyticReleases": len(pub_additions),
            "newFounderReviewEvents": len(new_event_paths),
            "newFounderAnalyticReleases": len(owner_pub),
            "status": "append-only-history-preserved"}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="origin/main")
    args = parser.parse_args()
    require(args.base == "origin/main" or
            bool(re.fullmatch(r"[0-9a-f]{40}", args.base)),
            "only current main or an exact GitHub push-before SHA is admitted")
    if args.base != "origin/main":
        ancestor = subprocess.run(("git", "merge-base", "--is-ancestor",
                                   args.base, "HEAD"), check=False)
        require(ancestor.returncode == 0,
                "push predecessor is not an ancestor of the new main commit")
    print(json.dumps(verify_transition(args.base), sort_keys=True))
