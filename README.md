# Live Ticker

A small, always-on-top score crawl that sits in a corner of your screen (upper right by default), in the spirit of the old My Yahoo! desktop ticker. Plain white text on black; the only motion is the scroll.

- **Only games in progress.** No finals, no upcoming games, no news.
- **Grouped by sport, then by time remaining.** College and pro count as separate sports, as do men's and women's college games. The group name (e.g. COLLEGE FOOTBALL) appears once at the start of its group. Within a group, the game closest to ending comes first. Order: college football, men's and women's college basketball, college baseball, college softball, men's and women's college lacrosse, men's college hockey, then pro football (NFL/CFL/UFL), pro basketball (NBA/WNBA), MLB, NHL, soccer, pro lacrosse.
- **Each loop starts with the time of the last refresh**, e.g. "Updated 11:17:18 PM".
- **Every Division I college football game** (FBS and FCS) and **every Division I men's and women's college basketball game**, not just the Top 25. AP rankings appear next to ranked teams. College baseball, softball, men's/women's lacrosse and men's hockey are included too.
- **Pro leagues:** NFL, CFL, UFL, NBA, WNBA, MLB, NHL, PLL, MLS, NWSL, the big European soccer leagues, Champions/Europa League and Liga MX.
- **US pro teams are shown by city** (Boston, not Celtics). Where a city has more than one team in the same league, the team name is used instead: Giants/Jets, Chargers/Rams, Yankees/Mets, Cubs/White Sox, Rangers/Islanders, Clippers/Lakers. The list of shared cities is checked against ESPN's team lists each time the app starts, so relocations are picked up automatically.
- **TV / streaming channel** after each score (e.g. `8:28 1st ESPN+`). For college football and men's college basketball, channels come from Matt Sarzyniak's [College Sports on TV](https://www.mattsarzsports.com/), which includes small-conference streams and local stations; the app checks it every 15 minutes. All other sports use ESPN's listings (the national channel when there is one, otherwise the teams' regional channels). Turn it off under Display > Show TV / streaming channel.
- **Near real time.** College football and basketball are polled every 3 seconds while games are live, everything else every 6 seconds, and the app asks ESPN's CDN for a fresh copy each time rather than an up-to-8-second-old cached one. Leagues with nothing live are checked less often until a game is about to start.

## Run it

**Download (no Python needed):** grab `LiveTicker-windows.zip` or `LiveTicker-macos.zip` from this repo's Releases page, unzip, and open.
On macOS the app isn't signed, so the first time right-click it and choose **Open**.

**Or with Python 3.9+** (nothing to install, it uses only the standard library):

```
python live_ticker.py
```

`python live_ticker.py --once` prints the current live list to the terminal (with the refresh time at the top) without opening a window, and also saves it as a web page, `live_scores.html`, in the current folder. Use `--once --html some/other/name.html` to save it somewhere else.

## Start it automatically when you log in

Right-click the ticker (or click ≡) and check **Start automatically when I log in**. Uncheck it to turn it off. On Windows this adds Live Ticker to your startup apps, and it starts without a console window. You can also see or switch it off in **Settings > Apps > Startup**.

From the command line, `python live_ticker.py --startup-on` and `--startup-off` do the same thing.

If you move the project folder later, turn the option off and back on so it points to the new location.

## Using it

| Do this | To |
|---|---|
| Drag anywhere on the bar | Move it |
| Drag the bar's right edge | Resize it |
| Hover over the crawl | Pause it so you can read |
| Double-click a game | Open that game on ESPN |
| Scroll wheel | Speed up / slow down |
| Right-click, or the ≡ button at the right end | Settings menu |
| × button at the right end | Quit |

The settings menu has scroll speed, text size, position (any of the four screen corners) and width, league on/off switches (including a "college football + basketball only" shortcut), team names vs. abbreviations, TV channel on/off, baseball outs/runners on/off, always-on-top, and opacity. Settings and window position are saved to `~/.live_ticker.json`.

**Reading the bar:** the number after LIVE is how many games are in progress. The dot after it is lit while data is fresh (updated in the last 20 seconds) and goes dark if updates stall. A number like #12 before a team is its AP ranking.

## How "time remaining" is estimated

Within each sport, each game's remaining time is converted to **estimated real-world minutes** using typical game lengths: game clock left × that sport's real-time-per-clock-minute ratio, plus any halftime or intermissions still to come. Baseball uses half-innings and outs and soccer uses the running match clock. A college football game at kickoff sorts at about 3 hours 25 minutes; one at halftime at about 1 hour 45 minutes.

## Notes

Scores come from ESPN's public scoreboard feeds; college football and men's basketball channels come from mattsarzsports.com. Neither is an official API, so if either site changes, the app may need an update (scores keep working if the channel lookup fails). It's for personal use.

## Building the downloads

The workflow in `.github/workflows/build.yml` builds the Windows and macOS apps with PyInstaller. Push a version tag (for example `git tag v1.0.0 && git push --tags`) and the builds are attached to a new Release, or run the workflow by hand from the Actions tab.
