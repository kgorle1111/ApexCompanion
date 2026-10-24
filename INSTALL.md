# Installing ApexCompanion (no coding needed)

ApexCompanion is a focus coach that runs on your Mac. Every 10 seconds it looks at your screen, and if you drift onto something distracting, a coach character calls you out in a notification and out loud. Everything stays on your Mac: screenshots are deleted right after each check, and nothing is uploaded. It's built for watching yourself: no accounts, no remote reporting. Install it only on your own Mac.

## What you need

- **A Mac with Apple Silicon** (M1, M2, M3, M4 or newer). Intel Macs won't work.
- **macOS 14 (Sonoma) or newer.**
- **About 12 GB of free disk space.** Most of it is the coach's "brain" (an AI model, 8.3 GB), downloaded once. Setup checks that 10 GB is still free before that download starts.
- **16 GB of memory or more.** The coach uses about 11 GB while it runs. On an 8 GB Mac it will badly slow everything down; not recommended.
- **Internet for the first setup only.** The first run downloads a setup helper (uv), Python with about 850 MB of add-ons, and the 8.3 GB model. After that it makes no network calls and works offline.

## Install

1. **Download** `ApexCompanion.zip`.
2. **Double-click the zip** to unzip it. You'll get **ApexCompanion**.
3. **Drag ApexCompanion into your Applications folder.**
4. **Open it the first time.** Because ApexCompanion isn't from the App Store and isn't registered with Apple (it's a free hackathon project), macOS blocks it the first time. That's normal. To let it through:
   - Double-click ApexCompanion. macOS says it can't verify the app. Click **Done** (or **OK**). Don't move it to the Bin.
   - Open **System Settings → Privacy & Security**. Scroll down until you see *"ApexCompanion" was blocked…* and click **Open Anyway**. Enter your password or use Touch ID if asked.
   - Click **Open** when macOS asks one more time.
   - (On macOS 14 you can instead right-click the app → **Open** → **Open**.)

   You only do this once.

## First run

ApexCompanion has no window. It lives in your menu bar (top right of the screen) and talks to you through small pop-up boxes and notifications.

1. **Setup (one time).** If your Mac doesn't have it yet, it asks to install a small free helper called **uv** that sets up its engine. Click **Install**. Then it sets itself up (a few minutes).
2. **Coach download (one time, about 8.3 GB).** It asks before downloading. This can take 10 to 40 minutes depending on your internet. Keep the Mac plugged in. You'll get a notification when it's done.
3. **Pick your coach:**
   - **The Closer**: an arrogant big-shot dealmaker.
   - **The Whip**: a cold, slow-talking Southern political operator.

   It remembers your pick, so you won't be asked again unless you choose **Switch persona**.
4. **Tell it your sites.** Two quick questions:
   - *Sites or apps you NEVER want to get lost in*: type them with commas, for example `reddit, instagram, steam`.
   - *Anything that should ALWAYS count as work?*: optional, for example `figma`. Click **Skip** if nothing comes to mind.
5. **Let it see your screen.** macOS asks for permission, and ApexCompanion opens the right Settings page for you:
   - Find **ApexCompanion** in the **Screen & System Audio Recording** list.
   - Turn its switch **on**. If macOS offers **Quit & Reopen**, choose it.
   - **Open ApexCompanion again.**
6. **Let it read your browser's address bar (optional).** The first time you use Safari, Chrome, Arc, Brave or Edge while it runs, macOS asks whether ApexCompanion may **control** that browser. That wording is macOS's; ApexCompanion only reads the web address of the tab you're on, on your Mac, so your site list can match it. If you click **Don't Allow**, your list still matches app names and the coach still watches the screen.
7. **Say what you're working on.** It asks *"What are you working on?"* (for example `lab report`) and how long: **25**, **50** or **90 minutes**, or **no limit**. The coach uses your answer when it calls you out ("you said you'd be working on…"). It never changes how your screen is judged.
8. Look at the menu bar: **◉ 0m** means it's watching, and the number counts your focused minutes. Get to work.

When the time is up, the session ends and shows your summary: how long you focused and how often the coach called you out.

Each time you open it after that, it remembers your coach and just asks what you're working on and for how long.

## While it's running: the menu bar

Click **◉** in the menu bar. The title tells you what the coach is doing:

- **◉ 23m**: watching, 23 minutes focused so far.
- **⏸**: paused.
- **in a call**: a call is in front, so it's not watching (see below).
- **🔇**: the voice is muted.
- **◉ Apex**: no session running.

The menu shows **Working on:** your goal and **Focused 23 of 50 min**, then:

- **Pause 15 minutes** / **Resume**: while paused it takes no screenshots and doesn't run the AI model at all.
- **Mute voice** / **Unmute**: the coach stops talking out loud. You still get its notifications.
- **Edit my sites…**: your list opens in TextEdit. Put each site or app on its own line under `[distracting]` (always call me out) or `[ok]` (never call me out). If something is in both lists, **ok wins**. Save the file (⌘S). Changes apply within 10 seconds, with no restart. Lines starting with `#` are just notes and are ignored.
  - Your list is checked against the app's name and the web address only, never against what's on the page. So use a site or app name (`youtube`), not a YouTube channel name.
  - YouTube Shorts always counts as distracting, unless you put it under `[ok]`.
- **Stop session**: ends the session and shows your summary.
- **Start a session…** (when no session is running): asks what you're working on and for how long.
- **Quit ApexCompanion**: closes it completely, menu bar icon included.

Opening ApexCompanion again (from Applications, Launchpad or Spotlight) still works too, and it's where you choose **Switch persona** to change coach.

Restarting or logging out of your Mac also stops the coach. Open the app to start it again.

**Quiet during calls.** While Zoom, Microsoft Teams, FaceTime, Webex, Around or Tuple is in front, or a Google Meet, Zoom or Teams meeting in your browser, it takes no screenshot and says nothing. The menu bar shows **in a call**.

**Quiet while you focus.** The coach doesn't praise you out loud while you work, so it never interrupts a good stretch. Your focus shows in the summary at the end.

The coach speaks out loud and names what's on your screen. In a shared space (a library, an office), choose **Mute voice** in the menu bar.

## What it keeps on your Mac

- **Screenshots: none.** Each one is deleted right after its check.
- **A small log** in `~/Library/Application Support/ApexCompanion/logs`, readable only by your user account. It notes which app you were in, the site's name (for example `youtube.com`, not the full web address), whether you were working, and what the coach said. The model's description of your screen is kept only when the coach called you out.
- **Two small files**, `state.json` and `control.json`, in `~/Library/Application Support/ApexCompanion`, readable only by your user account. They let the menu bar and the coach talk to each other.
- Nothing is sent anywhere. Delete the `logs` folder anytime.

## Uninstall

1. Stop the coach first: menu bar → **Quit ApexCompanion**.
2. Drag **ApexCompanion** from Applications to the Bin.
3. Delete its data folder: in Finder, choose **Go → Go to Folder…**, paste `~/Library/Application Support/ApexCompanion`, press Return, and move the **ApexCompanion** folder to the Bin. That removes its engine, settings, site list and logs.
4. If you already had the AI model on your Mac before installing (developers only), it lives in `~/.cache/huggingface` and is shared with other tools. Leave it unless you know you don't need it.
5. Optional: remove ApexCompanion from **System Settings → Privacy & Security → Screen & System Audio Recording** (select it, click **–**).
6. Optional: the **uv** helper lives in your home folder at `~/.local/bin/uv`. You can delete it if nothing else uses it.

## If something goes wrong

- **"The coach stopped unexpectedly"**: open the app again. If it keeps happening, the details are in `~/Library/Application Support/ApexCompanion/logs/`.
- **It never calls you out, even on YouTube**: check the menu bar first. **⏸** means it's paused (choose **Resume**), and **in a call** means a call app or meeting tab is in front. Otherwise Screen Recording is probably off. Check the switch in System Settings (step 5 above), then open the app again.
- **No notifications show up**: check **System Settings → Notifications** and allow notifications for **Script Editor** (macOS shows ApexCompanion's notifications under that name).
- **Notifications but no voice**: the menu bar shows **🔇** when the voice is muted. Choose **Unmute**.
- **The download stopped halfway**: open the app again. It picks up where it left off.
