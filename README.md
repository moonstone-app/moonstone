<div align="center">
  <img src="data/moonstone.svg" alt="Moonstone Logo" width="120">
  <h1>Moonstone</h1>
  <p><strong>Notes-as-a-Service. A standalone, headless PKM engine that absorbs your existing vaults and turns them into a programmable platform.</strong></p>

  <p>
    <a href="https://github.com/moonstone-pkm/moonstone/blob/main/LICENSE"><img src="https://img.shields.io/badge/License-GPL_v3-blue.svg" alt="License: GPL v3"></a>
    <img src="https://img.shields.io/badge/Python-3.8+-blue.svg" alt="Python Version">
    <img src="https://img.shields.io/badge/Zero-Dependencies_GUI-success.svg" alt="Zero Dependencies GUI">
  </p>
</div>

---

## 🛑 The Desktop Jail

Let's be brutally honest: **every modern Personal Knowledge Management (PKM) tool is a walled garden even if it's built on top of your local files.**

* **Obsidian** traps your markdown inside a heavy desktop app. Want an API or mobile access? Pay $50/year or compile a complex TypeScript/Electron plugin that only runs when the app is open.
* **Logseq** does the exact same thing in ClojureScript.
* **Zim Wiki** is nailed to D-Bus and Linux.
* **Notion** holds your data hostage in the cloud entirely.

Most of them work with plain text files on your local drive, yet they stubbornly pretend that **they are the only software in the world allowed to read them.** The result is vendor lock-in, zero proper server-side capabilities, and over-engineered plugin ecosystems.

---

## Welcome to Notes-as-a-Service

**Moonstone** is a fundamentally different approach. It is a powerful, standalone **headless PKM server (no GUI)**. 

Point Moonstone at an empty directory, and it will instantly bootstrap a fully functioning, high-performance knowledge base with a 70+ endpoint REST API and a built-in web editor. 

Already have notes? Point Moonstone at your **Obsidian**, **Logseq**, or **Zim** folder, and it will effortlessly digest them, translating their unique dialects into a unified API on the fly. 

```bash
pipx install git+https://github.com/moonstone-app/moonstone
moonstone ~/my-vault
```

---

## Core Architecture

### 1. Universal Knowledge Bridge
Moonstone isn't just a parasite attached to {Obsidian,Logseq,Zim}. It’s an independent engine that *understands* other formats. It auto-detects your vault type and normalizes tags, internal links (`[[...]]`), and metadata. A simple HTTP request works identically whether Moonstone is serving its own native markdown format, an Obsidian vault, or a Zim wiki.

### 2. Truly Headless (Access Anywhere)
Run Moonstone on your home server, NAS, Raspberry Pi, or quietly in the background on your work laptop. 
**Want to access it securely from the internet?** Just expose the port via Cloudflare Tunnels, Tailscale, or ngrok, and boom — you have your own secure, private "Obsidian Sync" accessible from any browser or phone on the planet. For free.

### 3. Zero-Build Applets 
Want to build a Kanban board or a custom dashboard for your notes? Forget about Node.js, `npm run build`, and Electron. An applet in Moonstone is just a folder containing an `index.html` file. Pure HTML, CSS, and Vanilla JS talking directly to Moonstone's API. Drop the folder in, and it's live.

### 4. OS-Native Reactive Filesystem
Edited a note via SSH using `Vim`? Synced a file via Dropbox? The Moonstone Web Editor open in your browser will update **instantly**. We use native, OS-level file watching (FSEvents on macOS, ReadDirectoryChangesW on Windows, inotify on Linux) to track disk changes and push them to clients via SSE/WebSocket with 0% CPU overhead.

### 5. Background Services
Moonstone provides a powerful Python SDK (`moonstone_sdk.py`) for background services that run 24/7 alongside your server. This isn't just a cron job. Write background workers that act as Telegram bridges (saving messages straight to your inbox note), LLM summarizers, webhooks for external integrations, or automated broken-link checkers. Your knowledge base becomes a living, breathing ecosystem.

### 6. Rich Toolset 
WebSockets, SSE, KV-store, OpenAPI specs, AI-ready `dev-bundle` and all the things on top of your directory of notes.

---

## Who is this for?

* **You need** 100% ownership of your data, hosted on your own hardware, with zero subscriptions, but you still demand a modern API and web access.
* **You want** to build cool UIs, custom AI agents, or automations on top of your notes, but you refuse to learn Electron or wrestle with bloated plugin APIs.
* **You use** Obsidian for daily logs and Logseq for research. Moonstone acts as the ultimate unifier, giving you a single scripting and query interface for both.

---

## 🛠 Quickstart

### Installation

The recommended way to install Moonstone globally is using `pipx` (so it doesn't pollute your Python environment):

#### Linux:

```bash
pipx install git+https://github.com/moonstone-app/moonstone --force --system-site-packages
```

#### Win/MacOS:

```bash
pipx install git+https://github.com/moonstone-app/moonstone
```

After that you can add desktop file with `--install-shortcut` flag.

*(If you are contributing to the project, you can use `pipx install .` from the cloned repository).*

### Running the Server

Point Moonstone to any folder. If it's empty, Moonstone will initialize it. If it's an existing vault, Moonstone will read it.

```bash
moonstone ~/Documents/Notes
```

Open `http://localhost:8090` in your browser. By default, Moonstone serves the Workspace UI — a blazing fast, zero-dependency PWA editor for your notes.

---

## Contributing

Moonstone is an ambitious open-source project aimed at tearing down the walls of the current PKM landscape. 

- **Star ⭐️ this repository** — it's the strongest signal that you like this project.
- Join the discussion on GitHub Issues to propose API endpoints.
- Build and share your Zero-Build Applets.

---

## 📄 License and Acknowledgement

Moonstone tooks some logic and ideas from the brilliant and robust [Zim Wiki](https://github.com/zim-desktop-wiki/zim-desktop-wiki) and is distributed under the free **GPL-3.0** license. You own your notes, and you should own the code that manages them.
