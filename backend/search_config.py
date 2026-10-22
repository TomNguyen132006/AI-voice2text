"""Web search configuration (S3-2 to S3-4): the ONE place with provider, limits, timeouts and cache settings.

The provider can be overridden with the environment variable SEARCH_PROVIDER ("tavily" or "fake"),
the query mode with SEARCH_QUERY_MODE ("term", "title" or "model").
The API key is NOT here: it is read from the environment (TAVILY_API_KEY for Tavily).
"""
DEFAULT_PROVIDER = "tavily"  # "tavily" | "fake" (fake = no network, for tests and dry runs)

TAVILY_URL = "https://api.tavily.com/search"
TAVILY_KEY_ENV = "TAVILY_API_KEY"

SEARCH_MAX_RESULTS = 5
SEARCH_DEPTH = "basic"  # Tavily: basic = 1 credit per search, advanced = 2
SEARCH_TIMEOUT_SEC = 20.0
SEARCH_INCLUDE_USAGE = True  # Tavily then reports the credits of each search; summed in search_report.json

SEARCH_MAX_RETRIES = 2  # after the first call, for timeouts, connection errors and 5xx
RETRY_WAIT_BASE_SEC = 1.0  # wait 1 s, then 2 s
RATE_LIMIT_DEFAULT_WAIT_SEC = 2.0  # 429 without a usable Retry-After header
RETRY_AFTER_CAP_SEC = 30.0  # never wait longer than this, even if Retry-After says so

SEARCH_CACHE_TTL_DAYS = 7  # a cached answer older than this is fetched again
SEARCH_CAP_PER_JOB = 15  # real provider calls per job; cache hits do not count
# What is searched for each gap: "term" = the term alone, "title" = "<term> <section title>",
# "model" = the query Super wrote in gaps.json (the term when the gap has none).
SEARCH_QUERY_MODE = "model"
QUERY_MODES = ("term", "title", "model")
SEARCH_QUERY_WITH_TITLE = SEARCH_QUERY_MODE == "title"  # old name, kept as a read-only alias
