# mywant-smartgolf-book-plugin

MyWant custom type plugin for SmartGolf booking. Navigates to the confirmation screen without confirming the reservation.

## Installation

```bash
cd ~/.mywant/custom-types
git clone https://github.com/onelittlenightmusic/mywant-smartgolf-book-plugin
```

## Usage

```yaml
metadata:
  name: book_room02
  type: smartgolf_book
spec:
  params:
    room: "中野新橋店/打席予約(Room02)"
    date: "2026-04-13"
    time: "20:00"
```

## Requirements

- Python 3, Playwright, Chrome with remote debugging (port 9222)
