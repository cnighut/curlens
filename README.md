# Curlens

[![PyPI version](https://img.shields.io/pypi/v/curlens.svg)](https://pypi.org/project/curlens/)
[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Cursor CLI](https://img.shields.io/badge/Cursor-CLI-purple.svg)](https://cursor.com/cli)

Search and resume your Cursor CLI chat sessions by description.

![Curlens Demo](demo.gif)

## The Problem

You use Cursor CLI across multiple projects. After a few days, you have dozens of chats scattered across different workspaces. You remember discussing "flink job optimization" somewhere, but:

- Which folder was it in?
- What was the chat called?
- How do you resume it?

**Cursor stores all chats internally like this:**

```
~/.cursor/chats/
├── a14702e33628716ed.../   # MD5 hash of workspace path (not human-readable!)
│   ├── 8616c508-cbce.../   # Chat UUID
│   │   └── store.db        # Messages stored in SQLite
│   └── 2134a03e-7cdb.../
├── 1dd0fd26bc4627ee.../    # Another workspace hash
│   └── ...
└── (dozens more)
```

This is Cursor's internal structure—not your project folders. The hash `a14702e33628...` is actually `MD5("/Users/you/workspace/myproject")`. There's no easy way to:

1. Know which workspace a hash folder belongs to
2. Search chat contents without opening each `store.db`
3. Find the right chat to resume with `cursor agent --resume <id>`

## The Solution

Curlens indexes your chats with AI-generated summaries and lets you search by description:

```
$ curlens -d "flink optimization"

Found 2 matching chat(s):

[1] Flink Job Tuning
    Dir: /Users/you/workspace/data-pipeline
    Optimized Flink checkpointing and parallelism settings for better throughput...

[2] Stream Processing Debug  
    Dir: /Users/you/workspace/analytics
    Fixed watermark issues in Flink streaming job...

Select chat [1-2]: 1
→ Resuming: Flink Job Tuning
→ Directory: /Users/you/workspace/data-pipeline
```

## How It Works

```
┌─────────────────────────────────────────────────────────────────┐
│                        CURSOR CLI                               │
│  cursor agent (shell commands, file edits, MCP calls)          │
└─────────────────────┬───────────────────────────────────────────┘
                      │ hooks fire
                      ▼
┌─────────────────────────────────────────────────────────────────┐
│                     CURLENS HOOK                                │
│  1. Read chat messages from ~/.cursor/chats/<hash>/<id>/        │
│  2. Extract user queries + assistant responses                  │
│  3. Generate summary via LLM (cursor agent -p)                  │
│  4. Store in ~/.cursor/curlens/summary.db                       │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│                     CURLENS SEARCH                              │
│  curlens -d "your query"                                        │
│  1. Load summaries from SQLite                                  │
│  2. Rank by keyword match (or LLM with --smart)                 │
│  3. Display top results                                         │
│  4. Resume selected chat with cursor agent --resume             │
└─────────────────────────────────────────────────────────────────┘
```

## Cursor's Internal Structure

Curlens reads from Cursor's internal storage:

```
~/.cursor/
├── chats/
│   └── <md5(workspace_path)>/      # Hash of workspace path
│       └── <conversation_id>/
│           └── store.db            # SQLite with chat messages
├── projects/
│   └── Users-you-workspace-myproject/  # Encoded workspace path
│       └── worker.log              # Contains workspace mapping
└── curlens/                        # Created by curlens
    ├── config.json
    ├── summary.db
    └── hook.log
```

The hash folders in `chats/` are MD5 hashes of workspace paths. Curlens maps them back using the `projects/` folder names.

## Install

```bash
pip install curlens
```

Or from source:
```bash
git clone https://github.com/cnighut/curlens
cd curlens
pip install -e .
```

## Quick Start

### 1. Backfill Existing Chats (Do This First)

Index your existing chats before setting up hooks:

```bash
# Preview what will be processed
curlens --backfill --dry-run

# Process all chats (creates DB automatically)
curlens --backfill

# Or process in batches
curlens --backfill --limit 50
```

This scans `~/.cursor/chats/`, generates summaries, and stores them. Chats with unknown workspace paths are skipped.

> **⚠️ Backfill is slow** - Each chat requires an LLM call (~10-30 seconds). For 100+ chats, expect 30-60 minutes. Use `--limit` to process in batches. Already-processed chats are skipped on re-runs.

### 2. Setup Hooks (For Auto-Indexing)

Hooks automatically update summaries as you chat. Without hooks, you'd need to re-run backfill manually.

Create/edit `~/.cursor/hooks.json`:

```json
{
  "version": 1,
  "hooks": {
    "afterShellExecution": [
      {"command": "python3 /path/to/curlens/curlens/hooks/session_end.py"}
    ],
    "afterMCPExecution": [
      {"command": "python3 /path/to/curlens/curlens/hooks/session_end.py"}
    ],
    "afterFileEdit": [
      {"command": "python3 /path/to/curlens/curlens/hooks/session_end.py"}
    ]
  }
}
```

**Important**: Replace `/path/to/curlens` with your actual install path.

**Why these hooks?**
- `afterShellExecution` - Fires after terminal commands
- `afterMCPExecution` - Fires after MCP tool calls
- `afterFileEdit` - Fires after file modifications

These are the only hooks that work reliably with Cursor CLI.

### 3. Search & Resume

```bash
# Basic search (fast, keyword-based)
curlens -d "configuring nvim"

# Smart search (LLM-ranked, slower but smarter)
curlens -d "kubernetes deployment issue" --smart
```

## Config

`~/.cursor/curlens/config.json` (created automatically):

```json
{
  "summary_model": "grok",
  "search_model": "grok",
  "summary_max_words": 70,
  "search_window_days": 20,
  "hooks_enabled": true,
  "debug": false
}
```

| Key | Description |
|-----|-------------|
| `summary_model` | Model for generating summaries |
| `search_model` | Model for `--smart` ranking |
| `summary_max_words` | Max words per summary |
| `search_window_days` | How far back to search |
| `hooks_enabled` | Enable/disable hook processing |
| `debug` | Log to `~/.cursor/curlens/hook.log` |

## Cost Considerations

Curlens uses `cursor agent -p` to generate summaries, which consumes API tokens from your Cursor subscription.

**Estimated usage per chat:**
- Summary generation: ~500-1000 tokens
- Smart search (optional): ~200 tokens per search

**To minimize costs:**

1. **Use a cheaper/faster model** in config:
   ```json
   {"summary_model": "grok", "search_model": "grok"}
   ```

2. **Skip smart search** - Default search uses keyword matching (free):
   ```bash
   curlens -d "query"        # Free (keyword match)
   curlens -d "query" --smart  # Uses LLM tokens
   ```

3. **Use self-hosted models** - If you have Ollama or similar:
   ```json
   {"summary_model": "ollama/llama3", "search_model": "ollama/llama3"}
   ```
   (Requires Cursor to be configured with your local model endpoint)

4. **Backfill in batches** to control spend:
   ```bash
   curlens --backfill --limit 20  # Process 20 at a time
   ```

**Note**: Hooks fire frequently during active chats. Each hook only processes *new* messages incrementally, so repeated summaries for the same chat are efficient updates, not full regenerations.

## CLI-Only

This tool is designed for **Cursor CLI** (`cursor agent`). IDE-originated chats are automatically skipped.

**Tested on:** Cursor CLI version `2026.01.23-6b6776e`

```bash
cursor agent --version  # Check your version
```

## Troubleshooting

**No chats found?**
- Run `curlens --backfill --dry-run` to check discovery
- Ensure hooks are configured correctly

**Debug mode:**
```json
{"debug": true}
```
Check `~/.cursor/curlens/hook.log` for hook events.
