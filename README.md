# Nothing Special Studios — Discord Bot

Discord.py bot for **Nothing Special Studios / Slime Store Tycoon**.

## Features
- Private `bot-database` Discord channel created automatically; persistent snapshots stored as messages or JSON attachments (no external DB).
- Persistent button-based ticket panel; private tickets, claim/close, text transcripts to your log channel.
- Welcome embeds, branded `/embed` and `/rules` commands.
- FAQ replies in `#game-help`, `#general`, `#tips-and-tricks`.
- `/warn`, `/warnings`, `/timeout`, `/kick`, `/ban`.
- `/suggest`, `/bug`, `/giveaway` (persistent button entries and automatic winner selection).

## Discord setup
1. Open [Discord Developer Portal](https://discord.com/developers/applications), create an application, then create its bot.
2. Under **Bot**, enable **Server Members Intent** and **Message Content Intent**. Reset/copy the token; **never commit it to GitHub**.
3. Under **OAuth2 → URL Generator**, select `bot` and `applications.commands`. Give the bot permissions: View Channels, Send Messages, Read Message History, Manage Channels, Manage Messages, Embed Links, Attach Files, Add Reactions, Moderate Members, Kick Members, Ban Members. Invite it to your server. Keep its role above members it must moderate.
4. Copy your server ID (Developer Mode → right click server → Copy Server ID). Copy staff role ID, welcome channel ID, and a private log channel ID if desired.
5. Set `GUILD_ID`, `STAFF_ROLE_ID`, `WELCOME_CHANNEL_ID`, `LOG_CHANNEL_ID`, `DISCORD_TOKEN` in environment variables. Use 0 for optional IDs except GUILD_ID (recommended to set).
6. Start bot and run `/setup` in your server. It creates the private database channel and `#open-ticket` panel. Run `/rules` to publish rules, `/embed` for announcements.

## Deploy to Render — Web Service (free tier eligible)
1. Upload the **contents** of this folder to a private GitHub repository (do not upload `.env`).
2. On Render choose **New → Web Service**, connect the repository, choose **Python** and **Free** (if available).
3. Build command: `pip install -r requirements.txt`
4. Start command: `python bot.py`
5. Set environment variables: `DISCORD_TOKEN` (required), `GUILD_ID` (recommended), and optional IDs from `.env.example`.
6. Deploy. Render supplies `PORT` automatically; the HTTP server listens on `0.0.0.0:$PORT` and exposes `/` and `/health`.
7. Invite the bot and run `/setup` in Discord.

**Free service limitation:** Render may spin down an idle free web service. A Discord gateway connection does not necessarily count as inbound HTTP traffic, so the bot **cannot be guaranteed to stay online 24/7** on the free tier. It will reconnect when the web service wakes up. For reliable 24/7 operation, use a paid always-on service or background worker. Do not use artificial keep-alive requests to bypass platform policies.

## Local run
`pip install -r requirements.txt`, copy `.env.example` to `.env`, set values, run `python bot.py`.

## Image
The default image is the Discord CDN image supplied by the owner. Discord CDN links with expiration tokens can stop working. For durable embeds, upload the image to a stable location and set `EMBED_IMAGE_URL` to its permanent URL. Alternatively use a Discord attachment URL you control that remains accessible.

## Important limitations
- A Discord channel is **not a real database**: deletion, permissions, rate limits, API outages, attachment expiration or channel loss can affect persistence. Back up `bot-database` periodically. A 1000-message scan is used on startup; snapshots are pruned to 10.
- **Single-server, single-instance bot**. Don't run two instances against the same channel: updates can race and overwrite one another.
- Ticket transcripts store up to the latest 500 messages. A private log channel is strongly recommended; if none exists, closing a ticket deletes its content without a transcript archive.
- Discord's server admins can still access private channels through administrator privileges. Treat ticket contents and logs as confidential.
- Auto replies are keyword-based, not AI-generated.
- Keep `bot-database` and `mod-logs` private. Avoid sharing secrets or payment information in tickets.


## V2: channel-specific embed commands
Use `/sendrules`, `/sendtickets`, `/sendwelcome`, `/sendfaq`, `/sendupdates`, and `/sendannouncement` **in the exact channel** where the embed should appear. Commands require staff permissions. `/setup` still creates the private database and a default support panel.

Tickets: category dropdown → details modal → private channel → staff claim / add member / transcript / close. The ticket owner can request a transcript or close their own ticket. Configure `STAFF_ROLE_ID` so staff can see tickets. Ticket close sends a transcript to `LOG_CHANNEL_ID` (or `ticket-logs` if it exists).

**Image:** All embeds use `EMBED_IMAGE_URL`. The provided Discord CDN URL has expiring query parameters. Reupload the artwork to a stable public image host and replace this variable if images stop displaying.

**Free Render:** Free web services may sleep and disconnect the bot. HTTP health endpoints alone cannot guarantee uptime. Discord messages are used as a lightweight store, not a transactional database. Back up the private channel.
