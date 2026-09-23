"""Three known open-access DOIs, against the real internet.

Skipped everywhere by default, including CI. Its job is to catch the cascade rotting — an API
changing shape, a host starting to refuse us — which no fake can detect.
"""

import os

import pytest

from claimstone import net, resolve

pytestmark = pytest.mark.skipif(
    os.environ.get("CLAIMSTONE_LIVE") != "1",
    reason="set CLAIMSTONE_LIVE=1 and CLAIMSTONE_CONTACT_EMAIL to run",
)

KNOWN_OA_DOIS = (
    "10.1371/journal.pone.0173461",
    "10.1093/nar/gkw1099",
    "10.1186/s13059-014-0550-8",
)


@pytest.mark.network
@pytest.mark.parametrize("doi", KNOWN_OA_DOIS)
def test_unpaywall_still_knows_where_the_open_copy_is(doi):
    fetcher = net.Fetcher()
    locations, oa_status = resolve.unpaywall_locations(fetcher, doi)
    assert locations, f"Unpaywall returned no open location for {doi}"
    assert oa_status in {"gold", "green", "hybrid", "bronze"}
