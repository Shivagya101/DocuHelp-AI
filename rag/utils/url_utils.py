import urllib.parse
from url_normalize import url_normalize

def clean_url(raw_url: str) -> str:
    """
    Industry standard URL normalization.
    1. Runs url-normalize to fix syntax (lowercase scheme, remove default ports, resolve paths).
    2. Strips out URL fragments (#anchors) because RAG chunks text anyway.
    3. Strips out common tracking query parameters to prevent duplicate hashes.
    """
    if not raw_url:
        return raw_url
        
    # 1. Base syntax normalization
    try:
        normalized = url_normalize(raw_url)
    except Exception:
        # Fallback if the library fails on a completely malformed string
        normalized = raw_url
        
    # 2. Parse for component stripping
    parsed = urllib.parse.urlparse(normalized)
    
    # Strip Fragment completely
    parsed = parsed._replace(fragment="")
    
    # Strip tracking query parameters
    if parsed.query:
        query_params = urllib.parse.parse_qs(parsed.query, keep_blank_values=True)
        # Common tracking prefixes
        tracking_prefixes = ("utm_", "fbclid", "gclid", "msclkid")
        
        filtered_params = {
            k: v for k, v in query_params.items() 
            if not any(k.startswith(prefix) for prefix in tracking_prefixes)
        }
        
        # Re-encode query
        new_query = urllib.parse.urlencode(filtered_params, doseq=True)
        parsed = parsed._replace(query=new_query)
        
    return urllib.parse.urlunparse(parsed)
