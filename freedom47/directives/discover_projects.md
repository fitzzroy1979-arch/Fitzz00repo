# Directive: Discover crypto projects

## Goal
Surface up-and-coming crypto projects with real use cases from launch platforms, filtered through a strict credibility bar given the high scam rate.

## Sources
ICODrops, CoinList, CryptoRank, DappRadar

## Steps
1. `execution/scan_launch_platforms.py --out .tmp/discover_raw.json`
2. `execution/score_project_credibility.py --in .tmp/discover_raw.json --out output/discover/<date>.md`

## Credibility bar (project level)
- Product reality: working product or verifiable testnet, not just a whitepaper
- Team transparency: named, verifiable team
- Audit status: named auditor, report linked
- Red flags: anonymous team + high APY promises, locked-liquidity theater, copied whitepapers, referral-heavy marketing → auto-fail

## Output
Table of projects with a pass/fail per criterion and a one-line "why it might matter". Nothing here is a buy call.
