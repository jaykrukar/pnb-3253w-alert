"""Read availability for one UConn class section and notify when it becomes open.

UConn's live class page can change.  This script deliberately fails closed when it
cannot identify an explicit seat count (rather than guessing and sending an alert).
"""
from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
from urllib.request import Request, urlopen

from playwright.sync_api import sync_playwright

STATE_PATH = Path(__file__).with_name('.tracker_state.json')
COURSE = 'PNB 3253W'
CLASS_URL = 'https://classes.uconn.edu/?details&srcdb=1273&crn=4418'
HEARTBEAT_DAYS = 14


def check_section_url(url: str) -> None:
    parsed = urlsplit(url)
    q = parse_qs(parsed.query, keep_blank_values=True)
    if parsed.scheme != 'https' or parsed.hostname != 'classes.uconn.edu':
        raise ValueError('CLASS_URL must be a https://classes.uconn.edu/ link.')
    if 'crn' not in q or 'srcdb' not in q or 'details' not in q:
        raise ValueError('CLASS_URL must be the SECTION details link copied from UConn (contains ?details&srcdb=...&crn=...).')
    if not re.fullmatch(r'\d{3,8}', q['crn'][0]):
        raise ValueError('CLASS_URL contains an invalid class number (crn).')


def seats_from_text(body: str) -> int | None:
    """Return explicitly reported free-seat count, otherwise None.

    Only inspect the first Seats section, not the Reserved Seats or Waitlist
    sections that also sometimes display 'available' counts.
    """
    lines = [re.sub(r'\s+', ' ', x).strip() for x in body.splitlines()]
    start = next((i for i, x in enumerate(lines) if re.fullmatch(r'Seats(?:\s+Information)?', x, re.I)), None)
    if start is None:
        # A page with 'Seats Available: N' as one line is also possible.
        for line in lines:
            m = re.fullmatch(r'(?:Seats\s+Available|Available\s+Seats)\s*:?\s*(\d+)', line, re.I)
            if m:
                return int(m.group(1))
        return None

    region_lines = []
    for line in lines[start + 1:start + 31]:
        if re.match(r'^(?:Reserved Seats|Waitlist|Registration Restrictions|Required Linked Sections|Section Attributes|Meeting Info|All Sections)\b', line, re.I):
            break
        if line:
            region_lines.append(line)
    region = '\n'.join(region_lines)

    for pattern in (
        r'(?:Seats\s+Available|Available\s+Seats|Seats\s+Remaining|Remaining\s+Seats)\s*:?\s*(\d+)',
        r'(?m)^Available\s*:?\s*(\d+)\s*$',
        r'(?m)^Available\s*:?\s*\n\s*(\d+)\s*$',
    ):
        match = re.search(pattern, region, re.I)
        if match:
            return int(match.group(1))

    # If UConn presents enrollment & capacity rather than available seats,
    # perform subtraction only when both fields are explicitly identified.
    cap = re.search(r'(?:Enrollment\s+Capacity|Seat\s+Capacity|Capacity)\s*:?\s*(\d+)', region, re.I)
    enr = re.search(r'(?:Currently\s+Enrolled|Total\s+Enrolled|Enrollment\s+Total|Enrolled)\s*:?\s*(\d+)', region, re.I)
    if cap and enr:
        return max(0, int(cap.group(1)) - int(enr.group(1)))
    return None


def section_is_explicitly_full(body: str) -> bool:
    """Recognize UConn's selected-section registration note 'This section is full'.

    Only read section-specific notes BEFORE the Description/All Sections list;
    other sections in the course may be full even when our target is open.
    """
    lines = [re.sub(r'\s+', ' ', x).strip() for x in body.splitlines()]
    try:
        notes_start = next(i for i, line in enumerate(lines)
                           if line.lower() == 'registration notes')
    except StopIteration:
        return False
    for line in lines[notes_start + 1: notes_start + 14]:
        if line.lower() in ('description', 'registration restrictions',
                            'section attributes', 'all sections', 'seats',
                            'waitlist', 'reserved seats'):
            break
        if re.fullmatch(r'This section is full\.?', line, re.I):
            return True
    return False


def fetch_page_text(url: str) -> str:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            page = browser.new_page(user_agent='PNBSeatAlert/1.0 (student personal low-frequency monitor)')
            page.goto(url, wait_until='domcontentloaded', timeout=45000)
            try:
                page.get_by_text(COURSE, exact=False).first.wait_for(timeout=20000)
            except Exception:
                pass  # Error below includes page excerpt for debugging.
            page.wait_for_timeout(3500)
            return page.locator('body').inner_text(timeout=15000)
        finally:
            browser.close()


def publish(topic: str, message: str, title: str, click_url: str) -> None:
    if not re.fullmatch(r'[A-Za-z0-9_-]{12,128}', topic):
        raise ValueError('NTFY_TOPIC must be an unguessable 12+ character topic (letters, numbers, underscores, hyphens).')
    request = Request(
        url=f'https://ntfy.sh/{topic}',
        data=message.encode('utf-8'),
        method='POST',
        headers={'Title': title, 'Priority': 'high', 'Tags': 'rotating_light', 'Click': click_url},
    )
    with urlopen(request, timeout=20) as response:
        if response.status not in (200, 201, 202):
            raise RuntimeError(f'ntfy returned HTTP {response.status}')


def main() -> int:
    topic = os.environ.get('NTFY_TOPIC', '').strip()
    url = CLASS_URL
    if not topic:
        raise RuntimeError('Set the NTFY_TOPIC in the GitHub repository Actions secrets.')
    check_section_url(url)

    if os.environ.get('TEST_NOTIFICATION') == 'true':
        publish(topic, 'The PNB 3253W notification channel works! This is only a test.',
                'PNB 3253W: test notification', url)
        print('Test notification sent. No availability check performed.')
        return 0

    body = fetch_page_text(url)
    if not re.search(r'PNB\s*3253W', body, re.I):
        print('Page is missing PNB 3253W; not sending an alert. First 120 lines:')
        print('\n'.join(body.splitlines()[:120]))
        raise RuntimeError('Class details did not render / wrong term or section URL. See logs.')

    seats = seats_from_text(body)
    # UConn sometimes says 'This section is full' without showing a numeric
    # available-seat count. Accept that explicit section-level message as zero.
    # Do not infer an OPEN seat from the absence of this message.
    if seats is None and section_is_explicitly_full(body):
        seats = 0
        print('UConn explicitly reports that this section is full (0 available).')
    if seats is None:
        lines = body.splitlines()
        hits = [i for i, s in enumerate(lines) if re.search(r'\bSeats\b', s, re.I)]
        print('Could not read a reliable seats-available number. No alert sent.')
        if hits:
            i = hits[0]
            print('Page text around Seats heading (for troubleshooting):\n' + '\n'.join(lines[max(0, i-5):i+30]))
        else:
            print('\n'.join(lines[:120]))
        raise RuntimeError('UConn page layout differs from expected format; update seats_from_text().')

    opened = seats > 0
    prior = json.loads(STATE_PATH.read_text()) if STATE_PATH.exists() else {}
    previously_open = prior.get('open')
    print(f'PNB 3253W: {seats} available; previous state: {previously_open}.')

    if opened and previously_open is not True:
        publish(topic, f'{seats} seat(s) available in PNB 3253W! Open UConn Class Search and enroll now.',
                'PNB 3253W HAS AN OPEN SEAT!', url)
        print('Opening notification sent.')

    # Update on opening/closing, and every 14 days even if unchanged.
    # A periodic commit prevents GitHub from disabling this scheduled workflow
    # after 60 days with no repository activity.
    now = datetime.now(timezone.utc)
    previous_recorded = prior.get('last_checked_utc')
    try:
        previous_dt = datetime.fromisoformat(previous_recorded) if previous_recorded else None
    except (ValueError, TypeError):
        previous_dt = None
    if previous_dt and previous_dt.tzinfo is None:
        previous_dt = None
    changed = previously_open is None or opened != previously_open
    heartbeat_due = previous_dt is None or now - previous_dt >= timedelta(days=HEARTBEAT_DAYS)
    if changed or heartbeat_due:
        STATE_PATH.write_text(json.dumps({
            'course': COURSE,
            'crn': '4418',
            'open': opened,
            'last_seen_seats': seats,
            'last_change_utc': now.isoformat() if changed else prior.get('last_change_utc', now.isoformat()),
            'last_checked_utc': now.isoformat(),
        }, indent=2) + '\n')
        print('State/heartbeat changed; GitHub workflow will commit updated state.')
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except Exception as exc:
        print(f'ERROR: {exc}', file=sys.stderr)
        sys.exit(1)
