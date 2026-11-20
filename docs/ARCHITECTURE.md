# Architecture and design decisions

This is an operational single-section course monitoring tool. The code in \`tracker.py\` currently targets **PNB 3253W (CRN 4418)**.

## System flow

1. An external scheduler triggers the existing GitHub Actions workflow.
2. The workflow installs Python dependencies and a headless Chromium browser.
3. Playwright loads the public UConn section page and extracts visible text.
4. The parser looks for explicit available-seat counts, avoiding reserved-seat figures.
5. If parsing fails, the tool fails closed: it does **not** send an "open seat" alert.
6. A state file remembers whether the section was previously open.
7. On a transition from closed (or unknown initial state) to open, a notification is sent using an ntfy topic kept in a GitHub Actions secret.
8. The workflow commits state changes and occasional heartbeat data.

## Reliability considerations

- **Correctness over availability:** an unfamiliar page layout causes an error rather than a false availability claim.
- **Deduplication:** state is persisted between executions so a continuously open course does not repeatedly notify.
- **Observability:** workflow logs show the detected count and prior state.
- **Limitations:** class pages may change; scheduled runs may be delayed; reserved seats may not be enrollable; the monitor does not register anyone for a course.
- **Security:** the \`NTFY_TOPIC\` secret must never be committed or pasted into logs, screenshots, or issues. Anyone who learns the topic may be able to subscribe to it.

## Tests

The \`tests/test_tracker.py\` suite uses only mocked network/browser calls. It exercises text parsing, URL validation, invalid notification topics, open/closed transitions, duplicate suppression, and fail-closed behavior.

Run locally after installing dependencies:

\`\`\`bash
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
\`\`\`

The separate CI workflow runs unit tests only. It does not trigger the live class check and does not require the notification secret.

## Possible roadmap

Future work could make \`COURSE\`, \`CLASS_URL\`, and the per-course state key configurable, support multiple sections, add structured logging, and improve fixture coverage. Those features are **not implemented here yet**; changes to the live notification workflow should be deployed only after regression testing.
