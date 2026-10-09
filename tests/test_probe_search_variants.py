"""Provider result identities in a frozen search comparison."""

import json

from tools.probe_search_variants import _records


def test_openalex_and_crossref_doi_formats_compare_as_one_identity():
    openalex = json.dumps({'results': [{
        'id': 'https://openalex.org/W1',
        'doi': 'https://doi.org/10.1234/SAME', 'title': 'A news study'}]}).encode()
    crossref = json.dumps({'message': {'items': [{
        'DOI': '10.1234/same', 'title': ['A news study'],
        'URL': 'https://doi.org/10.1234/same'}]}}).encode()
    assert _records('openalex', openalex)[0]['key'] == 'doi:10.1234/same'
    assert _records('crossref', crossref)[0]['key'] == 'doi:10.1234/same'
