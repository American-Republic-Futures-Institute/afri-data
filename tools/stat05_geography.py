"""STAT-05: fixed U.S. Census four-region crosswalk for source-bound cohorts.

FIPS identifiers correspond to the published Census/BLS/CDC source releases.
Puerto Rico (72) is a state-equivalent in Census, outside the four standard
regions, and a period-excluded source observation for 2025 BLS LAUS.
"""
STATE_NAMES = {
    "01":"Alabama","02":"Alaska","04":"Arizona","05":"Arkansas",
    "06":"California","08":"Colorado","09":"Connecticut",
    "10":"Delaware","11":"District of Columbia","12":"Florida",
    "13":"Georgia","15":"Hawaii","16":"Idaho","17":"Illinois",
    "18":"Indiana","19":"Iowa","20":"Kansas","21":"Kentucky",
    "22":"Louisiana","23":"Maine","24":"Maryland","25":"Massachusetts",
    "26":"Michigan","27":"Minnesota","28":"Mississippi","29":"Missouri",
    "30":"Montana","31":"Nebraska","32":"Nevada","33":"New Hampshire",
    "34":"New Jersey","35":"New Mexico","36":"New York",
    "37":"North Carolina","38":"North Dakota","39":"Ohio",
    "40":"Oklahoma","41":"Oregon","42":"Pennsylvania","44":"Rhode Island",
    "45":"South Carolina","46":"South Dakota","47":"Tennessee",
    "48":"Texas","49":"Utah","50":"Vermont","51":"Virginia",
    "53":"Washington","54":"West Virginia","55":"Wisconsin",
    "56":"Wyoming","72":"Puerto Rico",
}
REGIONS = {
    "ne":{"name":"Northeast","members":(
        "09","23","25","33","34","36","42","44","50")},
    "mw":{"name":"Midwest","members":(
        "17","18","19","20","26","27","29","31","38","39","46","55")},
    "s":{"name":"South","members":(
        "01","05","10","11","12","13","21","22","24","28",
        "37","40","45","47","48","51","54")},
    "w":{"name":"West","members":(
        "02","04","06","08","15","16","30","32","35","41","49","53","56")},
}
REGION_OF = {
    member: region for region, spec in REGIONS.items()
    for member in spec["members"]
}
assert len(STATE_NAMES)==52 and len(REGION_OF)==51
assert set(REGION_OF)==set(STATE_NAMES)-{"72"}
assert len(REGION_OF)==sum(len(v["members"]) for v in REGIONS.values())
