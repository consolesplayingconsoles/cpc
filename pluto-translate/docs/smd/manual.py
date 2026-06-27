#!/usr/bin/env python3
"""Manual translation workflow for Mega Drive Buyuu Retsuden.

Interactive CLI for translating one page at a time.
"""

import json
import os
import sys

STATE_FILE = '/tmp/megadrive_extract.json'
WORK_FILE = '/tmp/megadrive_work.json'

def load_state():
    """Load current extraction state."""
    with open(STATE_FILE) as f:
        return json.load(f)

def load_work():
    """Load existing work (translations in progress)."""
    if os.path.exists(WORK_FILE):
        with open(WORK_FILE) as f:
            return json.load(f)
    return {'pages': {}}

def save_work(work):
    """Save work in progress."""
    with open(WORK_FILE, 'w') as f:
        json.dump(work, f, ensure_ascii=False, indent=2)

def show_page(state, page_num):
    """Display a page of blocks."""
    total_pages = (state['total_blocks'] + state['page_size'] - 1) // state['page_size']
    print(f"\n{'='*80}")
    print(f"PAGE {page_num} of {total_pages}")
    print(f"{'='*80}\n")

    blocks = state['blocks']
    for i, block in enumerate(blocks, 1):
        offset = block['offset']
        jp = block['jp'][:50]
        print(f"{i:2d}. [{offset}] {jp}")

    print(f"\n{'='*80}")
    print(f"Commands: [n]ext, [p]rev, [s]ave, [q]uit, or block# to edit")
    print(f"{'='*80}\n")

def edit_block(block):
    """Edit translation for a single block."""
    print(f"\nJapanese: {block['jp']}")
    print(f"Bytes: {block['jpBytes']}")
    ca = input("Catalan translation: ").strip()
    block['ca'] = ca
    return block

def load_page(state, work, page_num):
    """Load blocks for a specific page."""
    total_blocks = state['total_blocks']
    page_size = state['page_size']
    total_pages = (total_blocks + page_size - 1) // page_size

    if page_num < 1 or page_num > total_pages:
        print(f"Invalid page. Range: 1-{total_pages}")
        return None

    start = (page_num - 1) * page_size
    end = min(start + page_size, total_blocks)

    # Re-extract current page (since state.json is paginated)
    print(f"Loading page {page_num} ({start+1}-{end} of {total_blocks})...")
    # For now, just update the state reference
    return page_num

def main():
    """Interactive translation workflow."""
    print("\n🎮 Mega Drive Buyuu Retsuden — Manual Translation\n")

    # Load initial state
    state = load_state()
    work = load_work()

    print(f"Loaded extraction:")
    print(f"  Total blocks: {state['total_blocks']}")
    print(f"  Page size: {state['page_size']}")
    print(f"  Total pages: {(state['total_blocks'] + state['page_size'] - 1) // state['page_size']}")

    current_page = 1
    show_page(state, current_page)

    while True:
        cmd = input("Command: ").strip().lower()

        if cmd == 'q':
            print("Saving work...")
            save_work(work)
            print("✓ Done")
            break

        elif cmd == 'n':
            total_pages = (state['total_blocks'] + state['page_size'] - 1) // state['page_size']
            if current_page < total_pages:
                current_page += 1
                # Would reload page here in full version
                show_page(state, current_page)
            else:
                print("Already on last page")

        elif cmd == 'p':
            if current_page > 1:
                current_page -= 1
                # Would reload page here in full version
                show_page(state, current_page)
            else:
                print("Already on first page")

        elif cmd == 's':
            print("Saving current page...")
            save_work(work)
            print(f"✓ Saved page {current_page}")

        elif cmd.isdigit():
            block_num = int(cmd)
            if 1 <= block_num <= len(state['blocks']):
                block = state['blocks'][block_num - 1]
                edit_block(block)
                print("✓ Updated")
            else:
                print(f"Block {block_num} not on current page")

        else:
            print("Unknown command")

if __name__ == '__main__':
    main()
