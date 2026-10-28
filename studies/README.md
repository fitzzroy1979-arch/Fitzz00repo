# studies

One-off analyses that back specific claims in `FINDINGS.md`. Unlike
`run_sweep_4h.py` these are not tools — each answers one question once, and
is kept so the numbers in the write-up can be checked rather than retyped.

Run them from anywhere; they resolve the repo root from `__file__`.

| script | question | answer |
|---|---|---|
| `cot_signal.py` | Does CFTC positioning predict BTC weekly returns? | No. Forward correlations inside noise, backward ones significant — it describes the week just past. |
| `sec_signal.py` | Do SEC filing counts predict BTC weekly returns? | No, and they do not describe the past either. Nothing reaches \|t\| = 1.5. |

## Reproducibility differs between the two

`sec_signal.py` ships its data. `data/sec_counts.json` holds 1,380 weekly
EDGAR hit counts; with it the script finishes in under a second, and without
it the run is 1,377 requests and about ten minutes. Delete the file to
re-fetch. Counts come from EDGAR's `total` for a one-week window rather than
from paging and bucketing filings locally — the endpoint refuses offsets past
~10,000, so a bucketed multi-year series would silently be a truncated one.

`cot_signal.py` fetches the CFTC series live each run (it is small and the
endpoint is quick), so its output can move as new weekly reports publish.
The figures recorded in `FINDINGS.md` are as of 2026-10-28, 444 aligned
observations ending 2026-10-20.

Both need BTC daily bars, which come from the shared sweep cache in the
system temp directory. That cache is machine-local and not committed; if it
is cold, the first run pulls the bars through the TradingView bridge, which
must be up.

## Alignment is the whole question

Both scripts measure from a time a trader could actually have acted.
Positions are as of Tuesday and published the Friday after, so the COT study
aligns on the **release** date; aligning on the as-of date would price
Tuesday's positions at Tuesday's close. Filings dated Mon..Sun are public by
Sunday, so the SEC feature is known at the last close ≤ Sunday and the
forward return runs from there.

Look counts are declared in each script's docstring before the results,
because the correction only means something if the count was fixed in
advance.
