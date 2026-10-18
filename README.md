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

## Deploy to Render
1. Upload this folder to a **private** GitHub repository (do not upload `.env`).
2. In Render, choose **New → Background Worker** (not Web Service; the bot doesn't serve HTTP).
3. Connect GitHub repository; runtime Python; build `pip install -r requirements.txt`; start `python bot.py`.
4. Set environment variables from `.env.example` in Render's Environment page, especially `DISCORD_TOKEN` and `GUILD_ID`.
5. Deploy. A Render plan supporting background workers is required; check current pricing/availability.

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
