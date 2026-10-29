# UConn seat alert — PNB 3253W, Spring 2027

Watches **PNB 3253W (class number 4418)** and attempts to notify your iPhone if a seat opens up.

- UConn section: https://classes.uconn.edu/?details&srcdb=1273&crn=4418
- Checks planned for approximately **every 10 minutes** with GitHub Actions.
- Free setup: public GitHub repository + free ntfy iPhone app.
- Only alerts **once** per opening, then again if the class closes and later reopens.

**Current status: NOT YET LIVE-VERIFIED.** Unit tests pass for sample seat text, but the actual UConn page uses dynamically rendered content, and this environment cannot fetch the section's live page. The script deliberately refuses to claim a seat is open unless it can identify an explicit available-seat count. **Do not rely on alerts until Step 5 shows a real seat count in the logs.**

## Step 1: Make the notification destination

1. Install [ntfy for iPhone](https://apps.apple.com/app/ntfy/id1625396347) and allow notifications.
2. Open the app and subscribe to a new topic. Choose a private, random topic name at least 12 characters long, such as `uconn-pnb-7Q9mK5rX8pL2`. **Create your own; don't reuse this example.**
3. Keep the topic name handy. Topics on ntfy.sh are not private to anyone who guesses the name, so the randomness matters. Do not publish sensitive info through the topic.

## Step 2: Create a free GitHub repository

1. Visit https://github.com/new and sign in / make a free account.
2. Name it `pnb-3253w-alert`. Select **Public** to use standard GitHub Actions runners without monthly usage billing. The project code and seat-status file will be public, but your notification topic will be stored as a repository secret.
3. Create the repository (leave the optional initial README box unchecked if starting empty).
4. Unzip this project on your computer.
5. In the repo, use **Add file > Upload files** to add `tracker.py`, `requirements.txt`, and `README.md` to the top level. Commit the files.
6. Create the workflow file: **Add file > Create new file**. In the filename box type `.github/workflows/seat-alert.yml`; GitHub will create the nested directories. Copy the contents from the included `seat-alert.yml` into it, then **Commit changes**.

## Step 3: Configure only ONE secret

In the repo, visit **Settings > Secrets and variables > Actions > New repository secret**:

- **Name:** `NTFY_TOPIC`
- **Value:** the random topic you subscribed to in ntfy

No UConn login, password, or cookie is needed. The specific UConn class link is **already saved** in `tracker.py`.

## Step 4: Test the iPhone notification

Go to **Actions > PNB 3253W seat alert > Run workflow**. Select the `send_test` option and start the run. The resulting notification should say it's a **test** (no class status was checked). If nothing arrives, check the GitHub run log and iPhone notification permissions.

## Step 5: Test the **real UConn seat check** (required)

Run the same workflow again with `send_test` **unchecked**. Open its **Check seats (or send test)** log.

- **Success:** a line similar to `PNB 3253W: 0 available; previous state: None.` — this confirms the page loaded and the parser extracted an explicit seat count.
- **Needs adjustment:** `Could not read a reliable seats-available number` — send me the displayed `Page text around Seats heading` from the log (not the notification topic). I can adapt the parser to the actual layout.
- **Page load error:** check whether the class details appear in an incognito browser window and share only the error message from the GitHub log.

An opening may cause an **actual** notification during the first live test if the class is already open. There is no guarantee that open seats are eligible for your enrollment if UConn reserves capacity for certain students.

## How it works

The scheduled GitHub job launches a browser, opens UConn's *public* section page, reads its seat text, and sends a notification to your ntfy topic if the seat count goes from closed to open. It writes an open/closed state file into the repository, so future runs won't keep notifying for the same opening. It commits a small heartbeat every two weeks to avoid the 60-day inactivity disablement for scheduled workflows.

The job can be delayed or missed by GitHub's scheduler, and a seat may be filled between checks. This tool does not enroll you automatically. If the page layout changes, the job fails rather than making up a result. To pause/stop the monitor, disable the workflow in the Actions tab.

References: [UConn class-details documentation](https://uconn.atlassian.net/wiki/spaces/SAS/pages/27562344697/Understanding+Class+Details+in+the+Class+Search+at+classes.uconn.edu) · [GitHub Actions scheduling](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax) · [ntfy iOS app](https://docs.ntfy.sh/subscribe/phone/)
