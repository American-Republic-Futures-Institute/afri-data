"""GSA Data.gov v4 federal catalog metadata discovery — deterministic offline tests."""
import copy
import json
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlsplit
import unittest

from tools.federal_catalog_discovery import (
    BASE, DiscoveryError, PER_PAGE, api_url, empty, get_page, merge, project,
)

A="00000000-0000-4000-8000-000000000001"
B="00000000-0000-4000-8000-000000000002"
CHECK="2026-10-21T15:00:00Z"
LATER="2026-10-22T15:00:00Z"


def official(ident=A, **overrides):
    row={
        "identifier":ident,"title":"Official public water observations",
        "publisher":"National Oceanic and Atmospheric Administration",
        "accessLevel":"public","last_harvested_date":"2026-10-19T01:02:03Z",
        "organization":{"id":"11111111-1111-4111-8111-111111111111",
          "name":"NOAA","slug":"noaa","organization_type":"Federal Government"},
        "dcat":{"identifier":ident,"accessLevel":"public",
          "modified":"2026-10-19","issued":"2021-01-01",
          "distribution":[{"downloadURL":"https://www.noaa.gov/files/data.csv"},
                          {"accessURL":"http://example.net/restricted.csv"}]}
    }
    row.update(overrides)
    return row


def page(items=None, after=None):
    return {"sort":"last_harvested_date","results":items if items is not None else [official()],
            "after":after}


def page_fetch(pages):
    seen=[]
    def go(cursor, api_key):
        self_page=pages[cursor]
        seen.append(cursor)
        return (copy.deepcopy(self_page), "a"*64, len(json.dumps(self_page)))
    go.seen=seen
    return go


class FakeResponse:
    def __init__(self, response, url, code=200, headers=None):
        self.content=json.dumps(response).encode("utf-8") if isinstance(response,dict) else response
        self.url=url
        self.status=code
        self.headers=headers or {"Content-Length":str(len(self.content))}
    def geturl(self): return self.url
    def read(self,n): return self.content[:n]
    def __enter__(self): return self
    def __exit__(self,*a): return False


class FakeOpener:
    def __init__(self,response,redirect=None,code=200,headers=None):
        self.response=response
        self.redirect=redirect
        self.code=code
        self.headers=headers
        self.requests=[]
    def open(self,req,timeout):
        self.requests.append(req)
        assert timeout>0
        if self.code==403 or self.code==429:
            raise HTTPError(req.full_url,self.code,"API key / rate limit",None,None)
        return FakeResponse(self.response,self.redirect or req.full_url,
                            self.code,self.headers)


class FederalDiscoveryTests(unittest.TestCase):
    def test_exact_gsa_api_v4_endpoint_and_federal_cursor_filter(self):
        url=api_url()
        u=urlsplit(url)
        self.assertEqual(u.scheme,"https")
        self.assertEqual(u.netloc,"api.gsa.gov")
        self.assertEqual(url.split("?")[0],BASE)
        q=parse_qs(u.query)
        self.assertEqual(q["org_type"],["Federal Government"])
        self.assertEqual(q["sort"],["last_harvested_date"])
        self.assertEqual(q["per_page"],[str(PER_PAGE)])
        self.assertNotIn("after",q)
        self.assertEqual(parse_qs(urlsplit(api_url("Y3Vyc29yLTE=")).query)["after"],
                         ["Y3Vyc29yLTE="])
        for cursor in ["../../etc/passwd","a" * 2049,"cursor&org_type=Tribal","",
                       "evil%0aInjected: x","space token"]:
            with self.subTest(cursor=cursor[:30]):
                with self.assertRaisesRegex(DiscoveryError,"unsafe Data.gov cursor"):
                    api_url(cursor)

    def test_official_first_page_has_sha256_bound_original_response_metadata(self):
        fake=FakeOpener(page([official()], "cursor-2"))
        payload,hash_,count=get_page(None,"personal-api-key",opener=fake)
        self.assertEqual(payload["after"],"cursor-2")
        self.assertEqual(len(hash_),64)
        self.assertEqual(count,len(json.dumps(page([official()],"cursor-2")).encode()))
        request=fake.requests[0]
        self.assertEqual(request.full_url,api_url())
        self.assertEqual(request.get_header("X-api-key"),"personal-api-key")
        self.assertEqual(request.get_header("Accept"),"application/json")
        self.assertNotIn("personal-api-key",request.full_url)

    def test_reject_missing_or_demo_key(self):
        for key in (None, "", "DEMO_KEY"):
            with self.subTest(key=key):
                with self.assertRaisesRegex(DiscoveryError,"non-demo API key"):
                    get_page(None,key,opener=FakeOpener(page()))

    def test_api_errors_and_official_only_source(self):
        for code in (403,429):
            with self.subTest(code=code):
                with self.assertRaisesRegex(DiscoveryError,"HTTP "+str(code)):
                    get_page(None,"real-key",opener=FakeOpener(page(),code=code))
        with self.assertRaisesRegex(DiscoveryError,"untrusted Data.gov response"):
            get_page(None,"real-key",opener=FakeOpener(
                page(),redirect="https://evil.example/v4/search"))
        for data in (b"<!doctype html><html>error",b"not-json"):
            with self.assertRaisesRegex(DiscoveryError,"invalid JSON"):
                get_page(None,"real-key",opener=FakeOpener(data))
        with self.assertRaisesRegex(DiscoveryError,"byte limit"):
            get_page(None,"real-key",opener=FakeOpener(
                page(),headers={"Content-Length":"8000001"}))

    def test_api_rejects_unbounded_or_malformed_response(self):
        with self.assertRaisesRegex(DiscoveryError,"unrecognized federal dataset page"):
            get_page(None,"real-key",opener=FakeOpener({"foo":"bar"}))
        with self.assertRaisesRegex(DiscoveryError,"unrecognized federal dataset page"):
            get_page(None,"real-key",opener=FakeOpener(page([official()]*101)))
        with self.assertRaisesRegex(DiscoveryError,"malformed pagination cursor"):
            get_page(None,"real-key",opener=FakeOpener(page([official()],"../unsafe")))
        with self.assertRaisesRegex(DiscoveryError,"empty page"):
            get_page(None,"real-key",opener=FakeOpener(page([],"still-paging")))

    def test_federal_public_candidate_is_metadata_only_not_original_source(self):
        c,reason=project(official())
        self.assertIsNone(reason)
        self.assertEqual(c["catalogId"],A)
        self.assertEqual(c["organizationSlug"],"noaa")
        self.assertEqual(c["distributionCandidatesNotFetched"],
                         ["https://www.noaa.gov/files/data.csv"])
        self.assertEqual(c["catalogHarvestedAtUnverified"],"2026-10-19T01:02:03Z")
        self.assertEqual(c["publisherModifiedAtRawUnverified"],"2026-10-19")
        self.assertFalse(c["approvedForSourceIngestion"])
        self.assertFalse(c["licenseAndReuseReviewComplete"])
        self.assertFalse(c["sourceBytesAcquired"])
        self.assertIsNone(c["sourceReleaseTimestampVerified"])

    def test_disallow_state_tribal_restricted_and_ambiguous_access(self):
        for organization in ("State Government","Tribal","City Government",None):
            item=official()
            item["organization"]["organization_type"]=organization
            self.assertEqual(project(item)[1],"non_federal_or_unknown_organization")
        for status in ("non-public","restricted public"):
            item=official(accessLevel=status)
            self.assertEqual(project(item)[1],"restricted_source_not_ingestible")
        item=official()
        item["dcat"]["accessLevel"]="non-public"
        self.assertEqual(project(item)[1],"restricted_source_not_ingestible")
        item=official()
        item["dcat"]["rights"]="This resource contains restricted-use respondent files."
        self.assertEqual(project(item)[1],"restricted_source_not_ingestible")
        item=official()
        item["dcat"]["accessRights"]="Confidential internal files"
        self.assertEqual(project(item)[1],"restricted_source_not_ingestible")
        item=official()
        item["dcat"]["accessRights"]={"uninterpreted":"metadata"}
        self.assertEqual(project(item)[1],"unresolved_publisher_access_rights")
        item=official()
        del item["accessLevel"]
        del item["dcat"]["accessLevel"]
        self.assertEqual(project(item)[1],"unresolved_publisher_access_rights")

    def test_require_official_organization_slug_and_catalog_identifier(self):
        item=official(identifier="nasa/open_data")
        self.assertEqual(project(item)[1],"missing_valid_catalog_identifier")
        item=official()
        item["organization"]["slug"]="https://example.com"
        self.assertEqual(project(item)[1],"missing_title_or_official_organization_slug")
        item=official(title=None)
        self.assertEqual(project(item)[1],"missing_title_or_official_organization_slug")
        self.assertEqual(project(None)[1] if False else project({})[1],
                         "non_federal_or_unknown_organization")

    def test_first_scan_checkpoint_and_resume_are_bounded(self):
        call=page_fetch({None:page([official(A)],"cursor-2"),
                         "cursor-2":page([official(B)],"cursor-3"),
                         "cursor-3":page([official(A)],None)})
        first=merge(empty(),"real",fetcher=call,pages_limit=2,now=CHECK)
        self.assertEqual(call.seen,[None,"cursor-2"])
        self.assertEqual(first["status"],"bounded_discovery_in_progress")
        self.assertEqual(first["after"],"cursor-3")
        self.assertEqual(len(first["candidates"]),2)
        self.assertEqual(first["pagesExamined"],2)
        self.assertEqual(first["rowsExamined"],2)
        self.assertEqual(first["candidates"][0]["firstDiscoveredAt"],CHECK)
        self.assertFalse(first["candidates"][0]["sourceBytesAcquired"])
        call.seen.clear()
        second=merge(first,"real",fetcher=call,pages_limit=2,now=LATER)
        self.assertEqual(call.seen,[None,"cursor-3"])
        self.assertEqual(second["after"],None)
        self.assertEqual(second["status"],
                         "cursor_exhausted_at_check_not_complete_federal_data_census")
        self.assertEqual(second["scanBoundaryReachedAt"],LATER)
        self.assertEqual(second["pagesExamined"],4)
        self.assertEqual(len(second["candidates"]),2)
        self.assertEqual(second["candidates"][0]["firstDiscoveredAt"],CHECK)
        self.assertFalse(second["candidates"][0]["approvedForSourceIngestion"])

    def test_cursor_resume_with_one_page_budget_rejected_instead_of_losing_backfill(self):
        call=page_fetch({None:page([official()],"cursor-2"),
                         "cursor-2":page([official(B)],"cursor-3")})
        previous=merge(empty(),"real",fetcher=call,pages_limit=1,now=CHECK)
        self.assertEqual(previous["after"],"cursor-2")
        with self.assertRaisesRegex(DiscoveryError,"checkpoint continuation"):
            merge(previous,"real",fetcher=call,pages_limit=1,now=LATER)

    def test_repeated_cursor_cannot_silently_loop_or_claim_full_scan(self):
        call=page_fetch({None:page([official()],"cursor-2"),
                         "cursor-2":page([official(B)],"cursor-2")})
        with self.assertRaisesRegex(DiscoveryError,"repeated cursor"):
            merge(empty(),"real",fetcher=call,pages_limit=3,now=CHECK)

    def test_catalog_metadata_revision_keeps_original_first_discovered(self):
        call=page_fetch({None:page([official()],None)})
        initial=merge(empty(),"real",fetcher=call,pages_limit=2,now=CHECK)
        revised=official(title="Revised NOAA title in Data.gov catalog")
        call2=page_fetch({None:page([revised],None)})
        updated=merge(initial,"real",fetcher=call2,pages_limit=2,now=LATER)
        item=updated["candidates"][0]
        self.assertEqual(item["title"],"Revised NOAA title in Data.gov catalog")
        self.assertEqual(item["firstDiscoveredAt"],CHECK)
        self.assertEqual(item["lastCatalogMetadataChangeObservedAt"],LATER)
        self.assertNotEqual(item["catalogFingerprint"],
                            initial["candidates"][0]["catalogFingerprint"])
        self.assertNotIn("publisherReleaseToGitLag",item)

    def test_quarantine_candidate_count_does_not_inflate_verified_sources(self):
        call=page_fetch({None:page([official(A),
            official(B,accessLevel="restricted public"),
            official("00000000-0000-4000-8000-000000000003",
              organization={**official()["organization"],
                            "organization_type":"County Government"})],None)})
        result=merge(empty(),"real",fetcher=call,pages_limit=2,now=CHECK)
        self.assertEqual(len(result["candidates"]),1)
        self.assertEqual(result["rejectedByReason"]["restricted_source_not_ingestible"],1)
        self.assertEqual(result["rejectedByReason"]["non_federal_or_unknown_organization"],1)
        self.assertNotIn("sourceMirror",result)
        self.assertNotIn("publisherReleaseToGitLag",result)


if __name__ == "__main__":
    unittest.main()
