# Submitting a bot to the public ladder

1. Fork the repo and add **one file**: `ladder/bots/<your-github-username>.py` (letters, digits, hyphens; one bot per user; at most 50 KB).
2. It must define `act(view)` (see BOT_GUIDE.md), use only the standard library, and **beat the sleepwalker** in 5 of 6 games (seeds 1-3, both seats).
   Check locally: `python tools/validate_bot.py ladder/bots/<you>.py`.
3. Open a pull request. The `ladder` workflow validates the file and posts the result as a job summary. It runs with no secrets and a
   read-only token, and each match runs in an isolated subprocess with time and memory limits. Pull requests may only touch `ladder/bots/*.py`.
4. After a maintainer merges, the `pages` workflow runs the whole ladder (also nightly) and publishes ratings, win matrix and recipes on the Ladder page.

**Submitted bots are public**: the source is published on the site and in the repository under the repository's MIT license. Do not include secrets or personal data.
Bots that try to escape the sandbox, read files, use the network or interfere with other bots are rejected and removed.
Rating is the win rate over every other bot (both seats, ties count half); see DECISIONS.md.
