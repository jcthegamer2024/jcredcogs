# JC's Redbot Cogs
A collection of custom Redbot cogs — all **vibe coded by JC** — designed for fun, interactive server games with clean logic, turn‑enforcement, and smooth gameplay loops.

---

## 📦 Included Cogs

### **1. WordChain**
A flexible word‑chain game that supports full sentences, enforces turn order, and tracks round performance.

**Features**
- Sentence support (uses first and last alphabetic characters)
- Turn enforcement (no user can play twice in a row)
- Automatic round scoring and end announcements
- ❌ reaction on invalid plays
- Infinite chaining with clean resets
- Fully configurable channel

---

### **2. Counting**
A dynamic, direction‑switching counting game with milestones, scoring, and bot‑driven restarts.

**Features**
- UP/DOWN counting modes that flip on failure
- Bot posts the restart number after each failed round
- Round scoring (highest number + chain length)
- Turn enforcement (no double posts)
- Milestones every 100 numbers (🎉 + pinned)
- Channel topic updates showing next number, mode, and chain length
- Infinite gameplay loop with smooth transitions

---

### 3. BirthdayTracker

A feature-rich birthday tracking system with a dynamic auto-updating list and automatic daily birthday announcements.

**Features**

* Vertical dynamic list updating live from January to December
* Flexible date inputs (`MM/DD/YYYY` or `MM/DD` for optional year)
* Automatic ordinal age calculation (e.g., 21st, 22nd, 23rd)
* Embed-based birthday announcements in a designated channel
* Non-pinging mention formatted display
* Fully configurable update and announcement channels

--

### 4. TempVoice

A dynamic temporary voice channel generator with interactive UI controls and automated inactivity cleanup.

**Features**

* Interactive "VC Creation Panel" button to generate personal channels
* Modal popup interface for customizable user limits (0–99 capacity)
* Member selector menu to explicitly grant permissions to allowed users
* One-click general Lock/Unlock access toggle
* Dedicated control dashboard sent directly inside the new channel's chat
* Automated background cleanup loop deleting channels empty for 5+ minutes
## 🛠 Installation

Add the repo to your Redbot:
p]repo add jcredcogs https://github.com/jcthegamer2024/jcredcogs
