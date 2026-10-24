# Installing ApexCompanion (no coding needed)

ApexCompanion is a focus coach that runs on your Mac. Every 10 seconds it looks at your screen, and if you drift onto something distracting, a coach character calls you out in a notification and out loud. Everything stays on your Mac: screenshots are deleted right after each check, and nothing is uploaded.

## What you need

- **A Mac with Apple Silicon** (M1, M2, M3, M4 or newer). Intel Macs won't work.
- **macOS 14 (Sonoma) or newer.**
- **About 10 GB of free disk space.** Most of it is the coach's "brain" (an AI model, 8.3 GB), downloaded once.
- **16 GB of memory or more is recommended.** The coach uses about 11 GB while it runs. It will still try on smaller Macs, but other apps may slow down.
- **Internet for the first setup only.** After that it works offline.

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

ApexCompanion has no window. It talks to you through small pop-up boxes and notifications.

1. **Setup (one time).** If your Mac doesn't have it yet, it asks to install a small free helper called **uv** that sets up its engine. Click **Install**. Then it sets itself up (a few minutes).
2. **Coach download (one time, about 8.3 GB).** It asks before downloading. This can take 10 to 40 minutes depending on your internet. Keep the Mac plugged in. You'll get a notification when it's done.
3. **Pick your coach:**
   - **The Closer**: an arrogant big-shot dealmaker.
   - **The Whip**: a cold, slow-talking Southern political operator.
4. **Tell it your sites.** Two quick questions:
   - *Sites or apps you NEVER want to get lost in*: type them with commas, for example `reddit, instagram, steam`.
   - *Anything that should ALWAYS count as work?*: optional, for example `figma`. Click **Skip** if nothing comes to mind.
5. **Let it see your screen.** macOS asks for permission, and ApexCompanion opens the right Settings page for you:
   - Find **ApexCompanion** in the **Screen & System Audio Recording** list.
   - Turn its switch **on**. If macOS offers **Quit & Reopen**, choose it.
   - **Open ApexCompanion again.**
6. A notification says **"Watching as The Closer. Stay sharp."** It's running. Get to work.

Each time you open it after that, it just asks which coach you want and starts.

## While it's running: stop, switch coach, edit your sites

**Open ApexCompanion again** (from Applications, Launchpad or Spotlight). A small menu appears:

- **Stop**: the coach stops.
- **Switch persona**: pick the other coach.
- **Edit my sites**: your list opens in TextEdit. Put each site or app on its own line under `[distracting]` (always call me out) or `[ok]` (never call me out). If something is in both lists, **ok wins**. Save the file (⌘S). Changes apply within 10 seconds, with no restart. Lines starting with `#` are just notes and are ignored.
- **Keep going**: closes the menu.

Restarting or logging out of your Mac also stops the coach. Open the app to start it again.

## Uninstall

1. Stop the coach first (open the app → **Stop**).
2. Drag **ApexCompanion** from Applications to the Bin.
3. Delete its data folder: in Finder, choose **Go → Go to Folder…**, paste `~/Library/Application Support/ApexCompanion`, press Return, and move the **ApexCompanion** folder to the Bin. That removes its engine, settings, site list and logs.
4. If you already had the AI model on your Mac before installing (developers only), it lives in `~/.cache/huggingface` and is shared with other tools. Leave it unless you know you don't need it.
5. Optional: remove ApexCompanion from **System Settings → Privacy & Security → Screen & System Audio Recording** (select it, click **–**).
6. Optional: the **uv** helper lives in your home folder at `~/.local/bin/uv`. You can delete it if nothing else uses it.

## If something goes wrong

- **"The coach stopped unexpectedly"**: open the app again. If it keeps happening, the details are in `~/Library/Application Support/ApexCompanion/logs/`.
- **It never calls you out, even on YouTube**: Screen Recording is probably off. Check the switch in System Settings (step 5 above), then open the app again.
- **No notifications show up**: check **System Settings → Notifications** and allow notifications for **Script Editor** (macOS shows ApexCompanion's notifications under that name).
- **The download stopped halfway**: open the app again. It picks up where it left off.
