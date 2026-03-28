"""DeskSearch — Private semantic search engine for your local files.

Quick start::

    from desksearch import DeskSearch

    ds = DeskSearch()                            # uses ~/.desksearch by default
    results = ds.search("quarterly report")
    for r in results:
        print(r.path, r.score, r.snippet)

    # Index a new folder
    ds.index("~/Documents/Papers")

    # Check stats
    info = ds.info()
    print(info)  # {"documents": 1234, "chunks": 45678, ...}
"""
__version__ = "0.6.0"

from desksearch._sdk import DeskSearch, SearchResult

__all__ = ["DeskSearch", "SearchResult", "__version__"]
