# Live Ticker

A small, always-on-top score crawl for your desktop, in the spirit of the ESPN BottomLine and the old Yahoo! Sports ticker.

- **Only games in progress.** No finals, no upcoming games, no news.
- **Grouped by sport, then by time remaining.** College and pro count as separate sports, and each sport gets a header in the crawl (e.g. COLLEGE FOOTBALL · 24 live). Within a sport, the game with the most time left comes first. Sport order: college football, college basketball (men's and women's together), college baseball, college softball, college lacrosse, then pro football (NFL/CFL/UFL), pro basketball (NBA/WNBA), MLB, NHL, soccer, pro lacrosse.
- **Every Division I college football game** (FBS and FCS) and **every Division I men's and women's college basketball game**, not just the Top 25. AP rankings appear next to ranked teams. College baseball, softball and men's/women's lacrosse are included too.
- **Pro leagues:** NFL, CFL, UFL, NBA, WNBA, MLB, NHL, PLL, MLS, NWSL, the big European soccer leagues, Champions/Europa League and Liga MX.
- **Near real time.** College football and basketball are polled every 3 seconds while games are live, everything else every 6 seconds, and the app asks ESPN's CDN for a fresh copy each time rather than an up-to-8-second-old cached one. Leagues with nothing live are checked less often until a game is about to start.

## Run it

**Download (no Python needed):** grab `LiveTicker-windows.zip` or `LiveTicker-macos.zip` from this repo's Releases page, unzip, and open.
On macOS the app isn't signed, so the first time right-click it and choose **Open**.

**Or with Python 3.9+** (nothing to install, it uses only the standard library):

```
python live_ticker.py
```

`python live_ticker.py --once` prints the current live list to the terminal without opening a window, which is handy for checking that the feeds are working.

## Using it

| Do this | To |
|---|---|
| Drag anywhere on the bar | Move it |
| Drag the bar's right edge | Resize it |
| Hover over the crawl | Pause it so you can read |
| Double-click a game | Open that game on ESPN |
| Scroll wheel | Speed up / slow down |
| Right-click, or the ≡ button | Settings menu |
| × button | Quit |

The settings menu has scroll speed, text size, width and docking (full width at the top or bottom of the screen), league on/off switches (including a "college football + basketball only" shortcut), team names vs. abbreviations, down-and-distance on/off, always-on-top, and opacity. Settings and window position are saved to `~/.live_ticker.json`.

**Reading the bar:** plain white text on black. The dot after the live count is lit while data is fresh (updated in the last 20 seconds) and goes dark if updates stall. In football, a dot next to a team marks possession.

## How "time remaining" is estimated

Within each sport, each game's remaining time is converted to **estimated real-world minutes** using typical game lengths: game clock left × that sport's real-time-per-clock-minute ratio, plus any halftime or intermissions still to come. Baseball uses half-innings and outs and soccer uses the running match clock. A college football game at kickoff sorts at about 3 hours 25 minutes; one at halftime at about 1 hour 45 minutes.

## Notes

Scores come from ESPN's public scoreboard feeds. These are unofficial and undocumented, so if ESPN changes them the app may need an update. It's for personal use.

## Building the downloads

The workflow in `.github/workflows/build.yml` builds the Windows and macOS apps with PyInstaller. Push a version tag (for example `git tag v1.0.0 && git push --tags`) and the builds are attached to a new Release, or run the workflow by hand from the Actions tab.
