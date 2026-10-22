"""DATA-23A bounded publisher-original NASS archive probe. NO ingestion/publication."""
from __future__ import annotations
import csv, io, json, re, zlib
from datetime import datetime, timezone
from hashlib import sha256
from urllib.parse import urlsplit
from urllib.request import Request, HTTPRedirectHandler, build_opener
from urllib.error import URLError, HTTPError

LISTING="https://www.nass.usda.gov/datasets/"
MAX_PREFIX=262144
MAX_EXPANDED=4000000
REQUIRED={"SOURCE_DESC","SECTOR_DESC","COMMODITY_DESC","STATISTICCAT_DESC","UNIT_DESC","DOMAIN_DESC","AGG_LEVEL_DESC","YEAR","FREQ_DESC","REFERENCE_PERIOD_DESC","STATE_ALPHA","COUNTY_CODE","VALUE"}
PATH=re.compile(r"/datasets/qs\.(crops|animals_products)_(20\d{6})\.txt\.gz")

class ProbeError(ValueError): pass

def source_url(kind,edition):
    if kind not in ("crops","animals_products") or not re.fullmatch(r"20\d{6}",edition):
        raise ProbeError("Unapproved NASS source identity")
    return f"https://www.nass.usda.gov/datasets/qs.{kind}_{edition}.txt.gz"

def safe_url(url):
    try: p=urlsplit(url)
    except ValueError: return False
    return bool(p.scheme=="https" and p.netloc=="www.nass.usda.gov" and
                PATH.fullmatch(p.path) and not p.query and not p.fragment and
                p.username is None and p.password is None)

class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,headers,newurl):
        raise ProbeError("Publisher redirect not approved")

def inspect_prefix(data):
    if not isinstance(data,bytes) or not 16<=len(data)<=MAX_PREFIX or data[:3]!=b"\x1f\x8b\x08":
        raise ProbeError("Gzip prefix missing or oversized")
    z=zlib.decompressobj(31)
    try: out=z.decompress(data,MAX_EXPANDED+1)
    except zlib.error as exc: raise ProbeError("Invalid gzip") from exc
    if len(out)>MAX_EXPANDED or z.unconsumed_tail:
        raise ProbeError("Decompression budget exceeded")
    if z.eof: raise ProbeError("Only partial publisher originals are permitted")
    try: lines=out.decode("utf8").split("\n")[:-1]
    except UnicodeDecodeError as exc: raise ProbeError("Invalid UTF-8") from exc
    if len(lines)<2 or any(len(line)>131072 for line in lines):
        raise ProbeError("Truncated or excessively wide rows")
    try:
        reader=csv.reader(io.StringIO("\n".join(lines)),delimiter="\t",strict=True)
        header=next(reader)
        if not (REQUIRED <= set(header)) or len(header)>128 or len(header)!=len(set(header)):
            raise ProbeError("Unknown or duplicate source header")
        rows=[]
        for row in reader:
            if len(row)!=len(header): raise ProbeError("Source row shape drift")
            if len(rows)>=2000: break
            rows.append(dict(zip(header,row)))
    except (csv.Error,StopIteration) as exc: raise ProbeError("Malformed source TSV") from exc
    if not rows: raise ProbeError("No complete rows")
    examples=[{k:r[k] for k in ("SOURCE_DESC","COMMODITY_DESC","STATISTICCAT_DESC","UNIT_DESC","AGG_LEVEL_DESC","YEAR","STATE_ALPHA","VALUE")} for r in rows[:3]]
    return {"observedHeader":header,"observedFieldCount":len(header),"completePreviewRows":len(rows),
            "previewExamples":examples,"compressedPrefixBytes":len(data),
            "compressedPrefixSha256":sha256(data).hexdigest(),"expandedPrefixBytes":len(out),
            "gzipPrefixOnly":True,"fullOriginalSha256Verified":False,
            "fullGzipCRCVerified":False,"fullCoverageDetermined":False,
            "valueAndSuppressionPreservedAsStrings":True}

def probe(kind,edition,prefix_bytes=65536):
    if not 1024<=prefix_bytes<=MAX_PREFIX: raise ProbeError("Unsafe HTTP range")
    url=source_url(kind,edition)
    opener=build_opener(NoRedirect())
    headers={"User-Agent":"ARFI-NASS-Source-Feasibility/1.0","Accept-Encoding":"identity"}
    try:
        with opener.open(Request(url,headers=headers,method="HEAD"),timeout=25) as r:
            if r.status!=200 or r.geturl()!=url: raise ProbeError("HEAD source changed")
            declared=r.headers.get("Content-Length","")
            if not declared.isdecimal() or not 1<=int(declared)<=2000000000: raise ProbeError("Unsafe source length")
            length=int(declared)
            meta={k:r.headers.get(k) for k in ("Content-Type","Content-Length","Last-Modified","ETag","Accept-Ranges")}
            if "gzip" not in (meta["Content-Type"] or ""): raise ProbeError("Unexpected MIME")
        with opener.open(Request(url,headers={**headers,"Range":f"bytes=0-{prefix_bytes-1}"}),timeout=35) as r:
            if r.status!=206 or r.geturl()!=url or r.headers.get("Content-Range")!=f"bytes 0-{prefix_bytes-1}/{length}":
                raise ProbeError("Publisher refused bounded range")
            if r.headers.get("Last-Modified")!=meta["Last-Modified"]: raise ProbeError("Publisher revision drift")
            data=r.read(prefix_bytes+1)
            if len(data)!=prefix_bytes: raise ProbeError("Short/oversized range")
    except (URLError,HTTPError,TimeoutError,OSError) as exc:
        raise ProbeError("Official NASS archive unavailable") from exc
    return {"format":"arfi-data23a-nass-probe-v1","publisher":"USDA NASS",
            "publisherPage":LISTING,"requestUrl":url,
            "checkedAt":datetime.now(timezone.utc).isoformat(),
            "head":meta,"originalDeclaredBytes":length,
            "noDataRegistered":True,"noDataPublished":True,**inspect_prefix(data)}

def main():
    import argparse
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--edition",required=True)
    p.add_argument("--kind",action="append",choices=("crops","animals_products"))
    p.add_argument("--prefix-bytes",default=65536,type=int)
    a=p.parse_args()
    for kind in a.kind or ("crops","animals_products"):
        print(json.dumps(probe(kind,a.edition,a.prefix_bytes),sort_keys=True))
if __name__=="__main__":main()
