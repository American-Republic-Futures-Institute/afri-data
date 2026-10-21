"""DATA-10C.1 offline security, provenance, resume, and 7/14-day honesty tests."""
from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import io
import json
from pathlib import Path
import tempfile
import unittest
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlsplit

from tools import datagov_discovery as d

CURSOR = "WzY5LjM0NDY5NiwwLCJiYmRhZGNmYi00NDM1LTQzZWUtYjhlMy0yMzZiZjBlZDEwODIiXQ=="
API_KEY = "TEST_PRIVATE_KEY_1234567890"


def result(identifier="11111111-2222-4333-8444-555555555555", *,
           org="Federal Government", access="public", publisher="U.S. Census Bureau",
           title="Federal source example"):
    return {
        "identifier": identifier, "title": title, "publisher": publisher,
        "accessLevel": access, "keyword": ["statistical", "public"],
        "last_harvested_date": "2026-10-20T12:00:00.000001",
        "organization": {"slug": "census", "name": "U.S. Census Bureau",
                         "organization_type": org},
        "dcat": {
            "identifier": identifier, "accessLevel": access,
            "issued": "2026-10-17", "modified": "2026-10-20T03:25:00Z",
            "description": "Public Census sample metadata (synthetic test only)",
            "distribution": [
                {"downloadURL": "https://www.census.gov/data/source.csv"},
                {"accessURL": "https://evil.test/private?api_key=DO_NOT_COMMIT"},
                {"accessURL": "http://api.census.gov/insecure"},
            ],
        },
    }


def page(rows, after=None, sort="last_harvested_date"):
    return {"sort": sort, "results": rows, **({"after": after} if after is not None else {})}


def response(obj):
    raw = json.dumps(obj, separators=(",", ":"), ensure_ascii=False).encode()
    return obj, sha256(raw).hexdigest(), len(raw)


def organizations():
    return {"organizations": [
        {"name": "U.S. Census Bureau", "slug": "census",
         "organization_type": "Federal Government", "dataset_count": 9000},
        {"name": "California", "slug": "ca", "organization_type": "State Government"},
    ]}


def get_two_page(source=None):
    def fake(url, api_key):
        if url == d.ORGANIZATIONS:
            return response(organizations())
        assert api_key == API_KEY
        query = parse_qs(urlsplit(url).query)
        assert query["org_type"] == ["Federal Government"]
        assert query["sort"] == ["last_harvested_date"]
        if "after" in query:
            assert query["after"] == [CURSOR]
            return response(page([result("22222222-2222-4222-8222-222222222222",
                                         title=source or "Federal secondary")]))
        return response(page([result()], CURSOR))
    return fake


class DataGovDiscoveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name)
        self.root = self.home / "publication/discovery/datagov-v4"
        publisher = self.home / "catalog/publishers.json"
        publisher.parent.mkdir(parents=True)
        publisher.write_text(json.dumps({
            "publishers": [{"name": "U.S. Census Bureau", "id": "us-census"}]}),
            encoding="utf-8")

    def run_once(self, *, now="2026-10-21T08:46:00Z", fetch=None, pages=1, recent=1,
                 key=API_KEY):
        return d.run(self.root, api_key=key, repository_root=self.home,
                     page_budget=pages, recent_pages=recent, clock=lambda: now,
                     get=fetch or get_two_page())

    def test_missing_and_demo_keys_record_blocker_without_a_false_catalog(self):
        missing = self.run_once(key=None)
        self.assertEqual(missing["status"], "blocked_missing_key")
        self.assertEqual(missing["pagesFetched"], 0)
        self.assertFalse((self.root / "pages").exists())
        self.assertEqual(d.verify(self.root)["status"], "blocked_missing_key")
        demo = self.run_once(key="DEMO_KEY")
        self.assertEqual(demo["status"], "blocked_demo_key")
        self.assertEqual(self.run_once(key="short")["status"], "blocked_invalid_key")
        self.assertFalse((self.root / "queue.json").exists())

    def test_exact_source_and_pagination_include_only_federal_public_candidates(self):
        first = self.run_once()
        self.assertEqual(first["status"], "partial_checkpointed")
        self.assertEqual(first["pagesFetched"], 2)
        self.assertEqual(first["candidatesAcceptedThisRun"], 2)
        self.assertEqual(first["uniqueCandidateIdentitiesKnown"], 1)
        check = json.loads((self.root / "checkpoint.json").read_text())
        self.assertEqual(check["cursor"], CURSOR)
        self.assertEqual(check["nextPage"], 2)
        self.assertEqual(check["pagesCommitted"], 1)
        self.assertFalse(check["exhausted"])
        shard = next((self.root / "candidates").glob("*.json"))
        records = json.loads(shard.read_text())["records"]
        self.assertEqual(len(records), 1)
        item = next(iter(records.values()))
        self.assertEqual(item["seedPublisherIdExactMatch"], "us-census")
        self.assertFalse(item["sourceIngestionApproved"])
        self.assertFalse(item["sourceOriginalByteAcquired"])
        self.assertIsNone(item["releaseToGitLagDays"])
        self.assertEqual(item["governmentHttpsDistributionCandidates"],
                         ["https://www.census.gov/data/source.csv"])
        self.assertNotIn("DO_NOT_COMMIT", shard.read_text())
        self.assertTrue((self.root / "queue.json").exists())
        self.assertFalse(json.loads((self.root / "queue.json").read_text())
                         ["federalCatalogEnumerationComplete"])
        self.assertEqual(d.verify(self.root)["pageReceipts"], 2)

    def test_resume_persists_all_cursors_and_historical_first_discovered_at(self):
        self.run_once()
        second = self.run_once(now="2026-10-22T08:46:00Z")
        self.assertEqual(second["status"], "catalog_scan_complete")
        check = json.loads((self.root / "checkpoint.json").read_text())
        self.assertTrue(check["exhausted"])
        self.assertIsNone(check["cursor"])
        self.assertEqual(check["pagesCommitted"], 2)
        self.assertEqual(second["uniqueCandidateIdentitiesKnown"], 2)
        self.assertEqual(d.verify(self.root)["pageReceipts"], 4)
        # Next scan edition starts after exhaustion; historical page receipts remain.
        third = self.run_once(now="2026-10-23T08:46:00Z")
        self.assertEqual(third["scanEdition"], 2)
        self.assertEqual(d.verify(self.root)["pageReceipts"], 6)

    def test_metadata_revisions_are_counted_without_replacing_old_page_receipts(self):
        self.run_once()
        first_page = self.root / "pages/backfill/edition-0001/page-000001.json"
        original = first_page.read_bytes()
        altered = get_two_page("Changed")
        self.run_once(now="2026-10-22T08:46:00Z", fetch=altered)
        # A future complete pass observes the revised secondary row and saves a new revision.
        self.assertEqual(first_page.read_bytes(), original)
        self.assertEqual(d.verify(self.root)["pageReceipts"], 4)

    def test_nonfederal_and_restricted_are_not_candidates(self):
        extra = page([result(org="State Government"),
                      result("22222222-2222-4222-8222-222222222222",
                             access="restricted public"),
                      result("33333333-2222-4333-8333-333333333333", access="public")])
        def get(url, key):
            return response(organizations() if url == d.ORGANIZATIONS else extra)
        report = self.run_once(fetch=get)
        self.assertEqual(report["rejected"].get("non_federal"), 2, report)  # recent + backfill
        self.assertEqual(report["rejected"].get("not_public"), 2)
        self.assertEqual(report["uniqueCandidateIdentitiesKnown"], 1)

    def test_single_terminal_catalog_page_without_after_cursor_is_valid(self):
        single = page([result()])
        def get(url, key):
            return response(organizations() if url == d.ORGANIZATIONS else single)
        report = self.run_once(fetch=get)
        self.assertEqual(report["status"], "catalog_scan_complete", report)
        self.assertEqual(report["pagesFetched"], 2)
        self.assertEqual(report["uniqueCandidateIdentitiesKnown"], 1)
        self.assertTrue(json.loads((self.root / "checkpoint.json").read_text())
                        ["exhausted"])

    def test_empty_or_truncated_page_is_rejected_not_marked_exhaustive(self):
        def get(url, key):
            return response(organizations() if url == d.ORGANIZATIONS else page([]))
        state = self.run_once(fetch=get)
        self.assertEqual(state["status"], "degraded_source_or_validation")
        self.assertEqual(state["pagesFetched"], 0)
        self.assertEqual(d.verify(self.root)["pageReceipts"], 0)

    def test_duplicate_source_identity_on_one_page_is_rejected(self):
        def get(url, key):
            return response(organizations() if url == d.ORGANIZATIONS else page([result(), result()]))
        state = self.run_once(fetch=get)
        self.assertEqual(state["status"], "degraded_source_or_validation")
        self.assertEqual(d.verify(self.root)["pageReceipts"], 0)

    def test_nonmatching_sort_and_cyclic_recent_cursor_rejected(self):
        def bad_sort(url, key):
            return response(organizations() if url == d.ORGANIZATIONS else page([result()], sort="relevance"))
        self.assertEqual(self.run_once(fetch=bad_sort)["status"], "degraded_source_or_validation")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "discover"
            def cycle(url, key):
                if url == d.ORGANIZATIONS:
                    return response(organizations())
                return response(page([result()], CURSOR))
            status = d.run(root, api_key=API_KEY, repository_root=self.home,
                           page_budget=0, recent_pages=3,
                           get=cycle, clock=lambda:"2026-10-22T10:00:00Z")
            self.assertEqual(status["status"], "degraded_source_or_validation")

    def test_corrupt_checkpoint_cannot_resume_or_claim_enumeration(self):
        self.run_once()
        path = self.root / "checkpoint.json"
        checkpoint = json.loads(path.read_text())
        checkpoint["cursor"] = "FORGED_CURSOR"
        path.write_text(json.dumps(checkpoint))
        with self.assertRaisesRegex(d.DiscoveryError, "resume cursor"):
            self.run_once(now="2026-10-22T08:46:00Z")

    def test_false_approved_source_candidate_cannot_pass_verification(self):
        self.run_once()
        queue = self.root / "queue.json"
        data = json.loads(queue.read_text())
        data["priorityQueue"][0]["sourceIngestionApproved"] = True
        queue.write_text(json.dumps(data))
        with self.assertRaisesRegex(d.DiscoveryError, "misreported"):
            d.verify(self.root)

    def test_url_allowlisting_refuses_queries_credentials_and_unsafe_sources(self):
        for item in ["https://data.gov/item?api_key=secret",
                     "https://user:password@census.gov/x",
                     "http://www.census.gov/file.csv",
                     "https://census.gov:badport/file.csv",
                     "https://census.gov.evil.example/file.csv",
                     "https://127.0.0.1/a", "javascript:alert(1)"]:
            self.assertIsNone(d.official_distribution(item))
        self.assertEqual(d.official_distribution("https://www.census.gov/file.csv"),
                         "https://www.census.gov/file.csv")

    def test_missing_or_ambiguous_access_not_approved(self):
        item = result()
        item["accessLevel"] = None
        item["dcat"].pop("accessLevel")
        rec, rejection = d.candidate(item, {}, "2026-10-21T08:46:00Z")
        self.assertIsNone(rejection)
        self.assertEqual(rec["catalogAccessReview"], "missing_or_ambiguous_access_review")
        self.assertFalse(rec["sourceIngestionApproved"])
        item["dcat"]["accessLevel"] = "non-public"
        rec, reason = d.candidate(item, {}, "2026-10-21T08:46:00Z")
        self.assertIsNone(rec)
        self.assertEqual(reason, "not_public")

    def test_bad_cursor_and_oversized_metadata(self):
        for value in ("^unsafe", "x" * 600, "value?token=abcdef"):
            with self.assertRaises(d.DiscoveryError):
                d.search_url(value)
        with self.assertRaisesRegex(d.DiscoveryError, "invalid page budget"):
            self.run_once(pages=81, recent=1)


class TransportTests(unittest.TestCase):
    class Response:
        def __init__(self, url, body, mime="application/json", reported=None):
            self.url = url
            self.payload = io.BytesIO(body)
            self.headers = {"Content-Type": mime,
                            "Content-Length": str(reported if reported is not None else len(body))}
            self.status = 200
        def __enter__(self):
            return self
        def __exit__(self, *args):
            self.payload.close()
        def geturl(self):
            return self.url
        def read(self, size):
            return self.payload.read(size)

    class Opener:
        def __init__(self, factory):
            self.factory = factory
            self.requests = []
        def open(self, req, timeout):
            self.requests.append(req)
            return self.factory(req.full_url)

    def test_private_key_only_in_header_and_official_path(self):
        url = d.search_url()
        opener = self.Opener(lambda u: self.Response(u, b'{"results": []}'))
        data, fingerprint, count = d.fetch_json(url, API_KEY, opener=opener)
        self.assertEqual(data["results"], [])
        self.assertEqual(count, len(b'{"results": []}'))
        self.assertRegex(fingerprint, r"^[0-9a-f]{64}$")
        self.assertNotIn(API_KEY, opener.requests[0].full_url)
        self.assertEqual(opener.requests[0].get_header("X-api-key"), API_KEY)
        with self.assertRaises(d.DiscoveryError):
            d.fetch_json("https://example.com/search", API_KEY, opener=opener)

    def test_403_and_429_fail_without_logging_secret_or_treating_as_data(self):
        url = d.search_url()
        def failure(code):
            def open(req, timeout):
                raise HTTPError(url, code, "rate failure", {}, io.BytesIO(b"private"))
            return open
        for code in (403, 429):
            opener = self.Opener(lambda u: self.Response(u, b"{}"))
            opener.open = failure(code)
            with self.assertRaises(d.DiscoveryError) as cm:
                d.fetch_json(url, API_KEY, opener=opener, sleep=lambda n:None)
            self.assertNotIn(API_KEY, str(cm.exception))
            self.assertIn(str(code), str(cm.exception))

    def test_http_payload_ceiling_mime_and_offhost_redirect_are_enforced(self):
        url = d.search_url()
        for factory in (
            lambda u: self.Response(u, b"<html/>", "text/html"),
            lambda u: self.Response(u, b'{"results":[]}', reported=d.MAX_RESPONSE_BYTES+1),
            lambda u: self.Response("https://attacker.example/search", b'{}'),
        ):
            with self.assertRaises(d.DiscoveryError):
                d.fetch_json(url, API_KEY, opener=self.Opener(factory))


if __name__ == "__main__":
    unittest.main()
