# Issue tracker: GitHub

Issues and specs for this repository live in GitHub Issues. Use the `gh` CLI for operations.

Repository: `JohanSardar/hermes-bot-fleet`

## Conventions

- Create, read, comment, label, assign, and close issues using `gh issue`.
- The Wayfinder map is labelled `wayfinder:map`.
- Decision and execution tickets are GitHub sub-issues labelled `wayfinder:research`, `wayfinder:prototype`, `wayfinder:grilling`, or `wayfinder:task`.
- Refer to issues by linked title in human-facing text, not by a bare number.

## Wayfinding operations

- Create the map with `gh issue create --label wayfinder:map`.
- Create child tickets, then attach them through GitHub's sub-issues API. If unavailable, use a map task list and `Part of <map URL>` in the child body.
- Express blocking through GitHub's native issue dependencies API. If unavailable, use `Blocked by:` in the child body.
- The frontier is the map's open, unassigned children with no open blocker.
- Claim a ticket by assigning it before work.
- Resolve with a resolution comment, close the ticket, and append a linked one-line context pointer to the map's Decisions so far.

## Pull requests as a triage surface

No. Pull requests are implementation artifacts, not incoming requests.
