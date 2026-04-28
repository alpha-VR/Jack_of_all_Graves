# Jack of All Graves

An Elden Ring Season 6 lockout bingo companion app with an AI-powered route planner.

> **Vibe coded with [Claude](https://claude.ai) (Anthropic) — from game mechanics to RL training to packaged .exe.**

---

## What it does

- **5×5 lockout bingo board** generated from S6 rules with weapon randomization
- **Interactive map** — Overworld + underground layers (Siofra, Ainsel, Deeproot, etc.)
- **AI route planner** — a trained PPO reinforcement learning agent suggests optimal stop order for your build
- **Save / load** game states mid-run
- **1v1 mode** — track both players' marks in real time

## Download & Run

1. Go to [Releases](../../releases) and download the latest `JackOfAllGraves-vX.X.X-Windows.zip`
2. Unzip anywhere
3. Run `JackOfAllGraves.exe`
4. Your browser opens automatically at `http://localhost:8000`

No Python install needed. Everything is bundled.

> Saves are stored in a `saves/` folder next to the `.exe` and persist across updates.

## For Developers

**Run from source:**
```
pip install -r requirements.txt
python jack/server.py
```

**Build the .exe:**
```
build.bat
```
Output goes to `dist/JackOfAllGraves/`. Share the whole folder.

**Train the RL agent:**
```
python -m jack.rl.train --timesteps 5_000_000
```

## Stack

| Layer | Tech |
|-------|------|
| UI | Vanilla JS + Leaflet.js |
| Server | Python `http.server` |
| RL Agent | Stable Baselines 3 — `MaskablePPO` |
| Packaging | PyInstaller |
| CI/Releases | GitHub Actions |

## Credits

Vibe coded with **[Claude Sonnet](https://claude.ai)** by Anthropic.

The RL agent was trained via self-play on a Python simulation of the bingo ruleset, reaching ~5M timesteps.

---

*Elden Ring is a trademark of FromSoftware / Bandai Namco. This project is unofficial and unaffiliated.*
