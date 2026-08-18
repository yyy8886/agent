---
name: system-time
description: Use when the user asks for the current system time, date, timezone, or wants to query the local clock. Returns the current date and time in the local timezone, optionally with timezone information and a 24-hour format. Best suited for quick time and date lookups on the host machine.
license: MIT
metadata: {"author":"this application","version":"1.0.0","platforms":["windows","macos","linux"]}
---

# System Time

## Overview

Query the current system date and time on the host machine. Returns the local time, date, and timezone.

## When to use

- User asks "现在几点", "what time is it", "current date/time", "today's date".
- User needs the local timezone or wants to confirm the system clock.

## Usage

Run the bundled script:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/get_time.ps1
```

Or on macOS/Linux:

```bash
bash scripts/get_time.sh
```

## Output

The script prints the current date, time (24-hour), and timezone in a concise format.
