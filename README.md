# TeraBox Telegram Bot

A Telegram bot that accepts a TeraBox link, uses the configured TeraBox API to
fetch a downloadable video, and sends the video back with a cleaned caption.

Default channel credit: `@CineBuzz3600`

Use this only for content you are authorized to download/repost.

## Setup

1. Create a Telegram bot with BotFather and copy its token.
2. Install Python 3.10+.
3. Install dependencies:

```bash
pip install -r requirements.txt
```

4. Copy `.env.example` to `.env`:

```bash
cp .env.example .env
```

5. Put your BotFather token in `.env`. Never commit `.env`.
6. Run:

```bash
python bot.py
```

## Input behavior

Send a message containing a TeraBox link. If the message also contains a
caption/text, the bot preserves the text, removes the TeraBox URL and other
`@mentions`, and adds `@CineBuzz3600`.

If there is no usable caption, the API filename is used as the fallback title.

## Important: large files

This starter project uses Telegram's standard hosted Bot API setup and includes
a conservative 50 MB upload guard. Large movie files require a Local Telegram
Bot API Server or a different deployment architecture.

## Security

Never put your real bot token in GitHub. `.env` is excluded by `.gitignore`.
