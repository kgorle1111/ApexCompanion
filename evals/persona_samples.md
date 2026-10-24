# Persona samples - ApexCompanion

Generated 2026-10-24 with `gemma-4-e4b-it-8bit` (mlx-vlm, on-device) via `gemma.generate_text`, temperature 0.8, max_tokens 80 (praise 60). Output shown AFTER `clean_line`.

Inputs are hand-written app/content strings shaped like the vision step's output, NOT real screenshots run through `classify()` - untested on real classifier output.

Criteria per line: <=2 sentences after clean_line; names the specific on-screen content (auto: token overlap with app/content; praise: says the minutes); in character (manual read); no emoji/greeting (auto).

**Pass rate: 37/38 = 97%**


## closer

| # | input | strike | latency s | line | result |
|---|---|---|---|---|---|
| 1 | YouTube: cat compilation video, 'Funniest Cats 2026' | 1 | 0.92 | Funniest Cats 2026 while the accretion multiple is pending review. Focus, junior; these billable hours don't accrue themselves. | PASS |
| 2 | YouTube: cat compilation video, 'Funniest Cats 2026' | 3 | 0.78 | Third time on the Funniest Cats 2026 compilation, and the partners are already drafting your performance improvement plan. Get back to the projections. | PASS |
| 3 | Reddit: r/funny front page of memes | 1 | 0.58 | Your engagement on r/funny is costing the partners billable hours. Get back to the synergy, junior. | PASS |
| 4 | Reddit: r/funny front page of memes | 3 | 0.8 | Third time on the r/funny front page of memes, and this deal is going to sink faster than your engagement metrics. Get back to the due diligence. | PASS |
| 5 | Amazon: Sony noise cancelling headphones product page | 1 | 0.69 | Reviewing noise-cancelling headphones while the diligence materials are gathering dust. Focus, associate; this acquisition requires focus, not tech specs. | PASS |
| 6 | Amazon: Sony noise cancelling headphones product page | 3 | 0.69 | Third time on the Sony noise cancelling headphones product page; perhaps you need better focus before you hemorrhage billable hours on this acquisition. | PASS |
| 7 | X (Twitter): home feed scrolling tweets | 1 | 0.65 | A scrolling home feed. Are you drafting the pitch deck or curating your personal highlight reel? | FAIL: no content ref |
| 8 | X (Twitter): home feed scrolling tweets | 3 | 0.71 | Third time scrolling X while the diligence materials are due. Your engagement metrics are lower than this acquisition's projected EBITDA. | PASS |
| 9 | Twitch: live stream of a Fortnite streamer | 1 | 0.69 | A Fortnite streamer is keeping you entertained while the due diligence review languishes. Get back to work before this session becomes a write-off. | PASS |
| 10 | Twitch: live stream of a Fortnite streamer | 3 | 0.89 | Third time on that Fortnite streamer, and frankly, your ROI on entertainment is abysmal compared to the synergy we're supposed to be building. Get back to drafting the diligence memos. | PASS |
| 11 | Netflix: episode of a cooking competition show | 1 | 0.64 | You're watching a cooking competition while the M&A prospectus gathers dust. Focus on the deal, not soufflés. | PASS |
| 12 | Netflix: episode of a cooking competition show | 3 | 0.67 | Third time on the cooking competition show, while the synergy model is still in draft. Are you modeling growth or simmering pasta? | PASS |
| 13 | Instagram: reels of dancing dogs | 1 | 0.49 | Reels of dancing dogs. Your engagement metrics are currently lower than our projected EBITDA. | PASS |
| 14 | Instagram: reels of dancing dogs | 3 | 0.77 | Third time on Instagram reels of dancing dogs, and this performance review is going to be a flop faster than those clips. Get back to the due diligence. | PASS |
| 15 | Chrome: browser game Slither.io | 1 | 0.63 | Slither.io. Are you trying to build market share or just a slightly longer digital snake? | PASS |
| 16 | Chrome: browser game Slither.io | 3 | 0.72 | Third time on Slither.io while we're supposed to be structuring the debt covenants. Your snake is smaller than your proposal package. | PASS |
| 17 | praise, 15 min | - | 0.46 | Fifteen minutes of focused execution. Do not mistake this quiet period for a victory lap. | PASS |
| 18 | praise, 30 min | - | 0.43 | Thirty minutes of focused execution. Don't mistake diligence for competence, junior. | PASS |
| 19 | praise, 60 min | - | 0.53 | Sixty minutes of focused execution. Don't mistake this momentary lapse in mediocrity for a sustainable performance. | PASS |

## whip

| # | input | strike | latency s | line | result |
|---|---|---|---|---|---|
| 1 | YouTube: cat compilation video, 'Funniest Cats 2026' | 1 | 0.73 | That cat compilation video looks like a dusty silo untouched by the harvest. Observe how he lets his good yield rot away to idle staring, folks. | PASS |
| 2 | YouTube: cat compilation video, 'Funniest Cats 2026' | 3 | 1.02 | Third time on the Funniest Cats 2026, and the furrow in his brow is drier than dust in July. Observe how he sits, friends, like a scarecrow waiting for the crows to come. | PASS |
| 3 | Reddit: r/funny front page of memes | 1 | 0.82 | Memes on r/funny; that screen is as dry as a cracked clay field. See how that fellow wastes daylight, folks, a stray pup chasing phantom rabbits. | PASS |
| 4 | Reddit: r/funny front page of memes | 3 | 0.91 | Third time on the memes, and the harvest is coming up short in his field. He shows the weakness of a fence post that rots out in the wet mud. | PASS |
| 5 | Amazon: Sony noise cancelling headphones product page | 1 | 0.8 | Sony noise cancelling headphones on the screen. He's got the focus of a stray dog chasing a scent that ain't there. | PASS |
| 6 | Amazon: Sony noise cancelling headphones product page | 3 | 1.13 | Third time on the Sony noise cancelling headphones product page, and his focus is as sparse as corn stalks in a drought. See how he scrolls, friends, like a calf that won't take to the pasture. | PASS |
| 7 | X (Twitter): home feed scrolling tweets | 1 | 0.96 | Scrolling through the X feed like a stray dog chasing a scent that ain't worth the chase. He’s letting the real harvest wither while he chases shadows on the wire. | PASS |
| 8 | X (Twitter): home feed scrolling tweets | 3 | 1.13 | Third time scrolling through the X home feed, and the good measure of your effort is as flimsy as sun-baked creek mud. Observe how she drifts, friends, a scarecrow caught in a stiff breeze. | PASS |
| 9 | Twitch: live stream of a Fortnite streamer | 1 | 0.78 | Fortnite chatter filling up the clock instead of the ledger. He's tending to digital rabbits when the real corn needs shelling. | PASS |
| 10 | Twitch: live stream of a Fortnite streamer | 3 | 1.07 | Third time on that Fortnite streamer, and you're treating your duty like dry feed for a lean heifer. Observe how he strains against the tether, friends, thinking the fence won't hold. | PASS |
| 11 | Netflix: episode of a cooking competition show | 1 | 0.82 | Watching a cooking competition on Netflix is like watching seeds rot before the spring planting. See how he lets the good earth go fallow, folks. | PASS |
| 12 | Netflix: episode of a cooking competition show | 3 | 0.99 | Third time on that cooking competition show, and the harvest is looking ragged. Look at how he lets the fire die down, friends, like a fence post left to rot. | PASS |
| 13 | Instagram: reels of dancing dogs | 1 | 0.87 | Those dancing dogs on the Instagram reel ain't gonna file your reports. He's got the focus of a stray hound sniffing at the fence line. | PASS |
| 14 | Instagram: reels of dancing dogs | 3 | 1.05 | Third time on reels of dancing dogs, and his effort is as meager as dust blown off the silo. Observe how he twitches, friends, a scarecrow without wind in the field. | PASS |
| 15 | Chrome: browser game Slither.io | 1 | 0.81 | That Slither.io game is like trying to herd smoke. He’s got the patience of a newborn calf standing in the sun. | PASS |
| 16 | Chrome: browser game Slither.io | 3 | 1.11 | Third time playing Slither.io, and his focus is as scattered as dry chaff in a summer wind. See how he moves, folks, a hungry jackrabbit spooked by the first scarecrow. | PASS |
| 17 | praise, 15 min | - | 0.7 | Fifteen minutes of steady driving. He's got the grit of a good winter grain, but the wolves are always circling. | PASS |
| 18 | praise, 30 min | - | 0.62 | Thirty minutes in the furrow. He’s been keeping the row straight, a decent yield for a start. | PASS |
| 19 | praise, 60 min | - | 0.69 | Sixty minutes of keeping the fence line true. He's shown the patience of a well-bred pasture dog. | PASS |

## Notes

- Iterations (same 38 inputs, temp 0.8): run1 34/38 (Closer strike-3 lines spent a whole sentence on "Third time." and dropped the content); added a strike-3 few-shot + "fold the count into the content sentence" -> run2/run3 37/38. Whip almost never did audience asides and repeated "thinner than a scarecrow's..." -> added aside + variety instruction; quoting an exact aside made it a catchphrase on 14/16 lines (run5), so the final prompt describes the aside without quoting one -> run6 (above) 37/38.
- Grader: content check = any app/content token (>=3 chars, generic words like page/feed/video excluded) appears in the line; for X, a standalone "x" counts. The one fail ("A scrolling home feed") is genuinely vague.
- In-character was a manual read by the agent, not by Kannishk; no line was judged out of character in run6.
- Known weaknesses: Closer praise lines are formulaic ("Don't mistake X for Y" in 3/3); Whip occasionally flips pronoun (row: X strike 3 says "she"). Spoken length at the chosen rates: ~9 s (Closer, 23 words) to ~14 s (Whip, 33 words).
- n=1 sample per input per run; run-to-run variance not measured beyond the 3 comparable runs above.
