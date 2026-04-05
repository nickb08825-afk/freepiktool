# freepiktool

Download Freepik assets **faster and more efficiently** — all formats, all
tiers, all at once.

## Features

| Feature | Detail |
|---|---|
| **Mandatory login** | Every command requires a Freepik account — membership entitlements (premium files, high-res exports) are applied automatically. |
| **Full-tier search** | Searches basic/free files, premium files, **and AI-generated artwork** in a single command. |
| **All formats per file** | For each search result the tool visits the detail page and clicks every download link: **JPEG, PNG, SVG, EPS, and high-resolution photo**. |
| **Concurrent downloads** | Async I/O with configurable concurrency (default 5 simultaneous). |
| **Auto-retry** | Transient failures are retried with exponential back-off. |
| **Zip output** | All downloaded files are bundled into **`<query>.zip`** automatically. |
| **Progress bars** | Per-file and overall progress shown via `tqdm`. |

---

## Installation

```bash
pip install -e .
```

### Requirements

- Python ≥ 3.10
- A [Freepik](https://www.freepik.com) account
- A [Freepik API key](https://www.freepik.com/api) (for the `search` command)

---

## Quick start

### 1 — Set credentials

```bash
# .env file (or export as environment variables)
FREEPIK_EMAIL=you@example.com
FREEPIK_PASSWORD=yourpassword
FREEPIK_API_KEY=your_api_key
```

Or pass them as flags (see below).

### 2 — Search, download everything, and zip

```bash
freepiktool search "sunset landscape" --output ./downloads
```

This will:

1. **Log in** to your Freepik account (prompted interactively if credentials are missing).
2. **Search** for `"sunset landscape"` across free, premium, and AI-generated tiers.
3. For each result, **scrape every download link** on the detail page (JPEG, PNG, SVG, EPS, high-res).
4. **Download all files** concurrently.
5. **Zip** everything into `./downloads/sunset_landscape.zip`.

### 3 — Download explicit URLs

```bash
freepiktool download https://dl.freepik.com/... --output ./downloads
```

Login is still required — you will be prompted if credentials are not set.

---

## Commands

### `freepiktool search`

```
freepiktool search QUERY [options]
```

| Option | Default | Description |
|---|---|---|
| `--output`, `-o` | `.` | Directory to save files and the zip archive. |
| `--api-key`, `-k` | `$FREEPIK_API_KEY` | Freepik API key. |
| `--max-pages` | all | Cap pages fetched per tier. |
| `--concurrency`, `-c` | `5` | Simultaneous downloads. |
| `--retries`, `-r` | `3` | Retry count on failure. |
| `--timeout` | `120` | Per-request timeout (seconds). |
| `--keep-files` | off | Keep individual files after zipping. |
| `--email` | `$FREEPIK_EMAIL` | Account email. |
| `--password` | `$FREEPIK_PASSWORD` | Account password. |
| `-v` | off | Verbose / debug logging. |

### `freepiktool download`

```
freepiktool download URL [URL ...] [options]
freepiktool download --url-file FILE [options]
```

| Option | Default | Description |
|---|---|---|
| `--url-file`, `-f` | — | Text file with one URL per line (`#` lines are comments). |
| `--output`, `-o` | `.` | Destination directory. |
| `--concurrency`, `-c` | `5` | Simultaneous downloads. |
| `--retries`, `-r` | `3` | Retry count. |
| `--timeout` | `120` | Timeout in seconds. |
| `--email` | `$FREEPIK_EMAIL` | Account email. |
| `--password` | `$FREEPIK_PASSWORD` | Account password. |

---

## Authentication

Login is **mandatory** for every command.  Credentials are resolved in this order:

1. `--email` / `--password` flags
2. `FREEPIK_EMAIL` / `FREEPIK_PASSWORD` environment variables
3. A `.env` file in the working directory
4. **Interactive terminal prompt** (password is hidden)

If login fails the tool exits immediately with an error — no files are downloaded.

---

## Development

```bash
# Install with dev extras
pip install -e ".[dev]"

# Run tests
pytest
```

---

## License

MIT
