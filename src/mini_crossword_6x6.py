import tkinter as tk
from tkinter import messagebox
import random
import os
import sys
import requests
import traceback
from openai import OpenAI

# ------------------------------
# CONFIGURATION
# ------------------------------
GRID_SIZE = 6
WORD_MIN = 5
WORD_MAX = 5


if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
    BASE_DIR = sys._MEIPASS
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

WORDLIST_PATH = os.path.join(BASE_DIR, "wordlist.txt")
LOG_PATH = os.path.join(BASE_DIR, "debug.log")

# Base pattern: 6x6, '.' = white, '#' = block
# This one has 4 slots, all length 5:
#  - Across: row1, row3
#  - Down:   col0, col1
BASE_PATTERN = [
    "##....",
    ".....#",
    "..####",
    ".....#",
    "..####",
    ".....#",
]

# ------------------------------
# PATTERN TRANSFORMS (RANDOM LAYOUTS)
# ------------------------------
def rotate_clockwise(pattern):
    """Rotate NxN pattern 90 degrees clockwise."""
    n = len(pattern)
    return [
        "".join(pattern[n - 1 - r][c] for r in range(n))
        for c in range(n)
    ]


def flip_horizontal(pattern):
    """Flip pattern left-right."""
    return [row[::-1] for row in pattern]


def flip_vertical(pattern):
    """Flip pattern top-bottom."""
    return list(reversed(pattern))


def random_pattern(base_pattern):
    """Return a randomized variant of base_pattern (rotations + flips)."""
    p = list(base_pattern)

    # Random rotation: 0, 90, 180, or 270 degrees
    k = random.randint(0, 3)
    for _ in range(k):
        p = rotate_clockwise(p)

    # Random horizontal flip
    if random.random() < 0.5:
        p = flip_horizontal(p)

    # Random vertical flip
    if random.random() < 0.5:
        p = flip_vertical(p)

    return p


# ------------------------------
# LOGGING
# ------------------------------
def log(msg: str):
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(msg + "\n")


# ------------------------------
# WORDLIST LOADING
# ------------------------------
def load_words(min_len=WORD_MIN, max_len=WORD_MAX):
    words = []
    with open(WORDLIST_PATH, "r", encoding="utf-8") as f:
        for line in f:
            w = line.strip().lower()
            if w.isalpha() and min_len <= len(w) <= max_len:
                words.append(w)
    if not words:
        raise RuntimeError(f"No words of length {min_len}–{max_len} found in wordlist.txt")
    return words


def build_wordlists(words):
    by_len = {}
    for w in words:
        by_len.setdefault(len(w), []).append(w)
    return by_len


# ------------------------------
# DICTIONARY LOOKUP FOR CLUES
# ------------------------------
definition_cache = {}

def get_definition(word: str) -> str:
    # For exe builds, avoid network (just show placeholder clue)
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return f"Clue for '{word}'"

    if word in definition_cache:
        return definition_cache[word]

    url = f"https://api.dictionaryapi.dev/api/v2/entries/en/{word}"
    try:
        r = requests.get(url, timeout=5)
        if r.status_code == 200:
            data = r.json()
            if isinstance(data, list) and data:
                meanings = data[0].get("meanings", [])
                if meanings:
                    defs = meanings[0].get("definitions", [])
                    if defs:
                        d = defs[0].get("definition", "")
                        if d:
                            definition_cache[word] = d
                            return d
    except Exception as e:
        print(f"Error fetching definition for {word}: {e}")

    return "No clue available."

# ------------------------------
# LLM-BASED CLUE GENERATION
# ------------------------------

def get_llm_clue(word: str, base_definition: str | None = None) -> str:
    """
    Use OpenAI to generate a fun crossword-style clue.

    - Uses the Responses API via the OpenAI Python SDK.
    - If anything fails (no key, quota, network), falls back to base_definition
      or a generic safe clue.
    """
    try:
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            # No key -> we cannot call OpenAI
            return base_definition or f"A word related to '{word}'."

        client = OpenAI()  # Reads OPENAI_API_KEY from environment

        # You can customise this "profile" if you like later
        user_profile = "The solver likes fantasy, and nature, and puzzles."

        if base_definition:
            prompt = (
                f"You are writing clues for a small, friendly crossword puzzle.\n"
                f"{user_profile}\n\n"
                f"Target word: {word}\n"
                f"Dictionary-style definition: {base_definition}\n\n"
                f"Write ONE fun, concise crossword clue, in the style of the new york times mini crossword clues (max 12 words).\n"
                f"- Do NOT include the word itself or obvious rhymes.\n"
                f"- Keep it easy, not too cryptic.\n"
                f"- Slightly playful tone is okay.\n"
                f"- Output only the clue text, no quotes, no extra commentary."
            )
        else:
            prompt = (
                f"You are writing clues for a small, friendly crossword puzzle.\n"
                f"{user_profile}\n\n"
                f"Target word: {word}\n\n"
                f"Write ONE fun, concise crossword clue, in the style of the new york times mini crossword clues (max 12 words).\n"
                f"- Do NOT include the word itself or obvious rhymes.\n"
                f"- Keep it easy, not too cryptic.\n"
                f"- Slightly playful tone is okay.\n"
                f"- Output only the clue text, no quotes, no extra commentary."
            )

        response = client.responses.create(
            model="gpt-4o-mini",  # or another model you've enabled
            input=prompt,
        )

        # New SDK gives you a convenience helper:
        clue_text = response.output_text.strip()

        if not clue_text:
            return base_definition or f"A word related to '{word}'."

        return clue_text

    except Exception as e:
        # Never crash the app because of AI issues; just log and fall back
        log(f"LLM clue error for {word}: {e}")
        return base_definition or f"A word related to '{word}'."

# ------------------------------
# BUILD MASK AND SLOTS
# ------------------------------
def build_slots(pattern):
    """
    Build mask and slots from a pattern, then
    remove any 'orphan' white cells that do not belong
    to a valid slot (length between WORD_MIN and WORD_MAX).
    """
    grid_size = len(pattern)
    mask = [[c == "." for c in row] for row in pattern]

    def slots_from_mask(mask_in):
        slots_out = []

        # Across
        for r in range(grid_size):
            c = 0
            while c < grid_size:
                if mask_in[r][c] and (c == 0 or not mask_in[r][c - 1]):
                    start = c
                    while c < grid_size and mask_in[r][c]:
                        c += 1
                    length = c - start
                    if WORD_MIN <= length <= WORD_MAX:
                        slots_out.append({
                            "dir": "across",
                            "row": r,
                            "col": start,
                            "length": length,
                        })
                else:
                    c += 1

        # Down
        for c in range(grid_size):
            r = 0
            while r < grid_size:
                if mask_in[r][c] and (r == 0 or not mask_in[r - 1][c]):
                    start = r
                    while r < grid_size and mask_in[r][c]:
                        r += 1
                    length = r - start
                    if WORD_MIN <= length <= WORD_MAX:
                        slots_out.append({
                            "dir": "down",
                            "row": start,
                            "col": c,
                            "length": length,
                        })
                else:
                    r += 1

        return slots_out

    # 1) First pass: find slots from the raw mask
    initial_slots = slots_from_mask(mask)

    # 2) Mark which cells are actually used by at least one valid slot
    used = [[False] * grid_size for _ in range(grid_size)]
    for s in initial_slots:
        r, c, d, length = s["row"], s["col"], s["dir"], s["length"]
        for i in range(length):
            rr = r + (i if d == "down" else 0)
            cc = c + (i if d == "across" else 0)
            used[rr][cc] = True

    # 3) Any white cell not used by any slot becomes a block
    for r in range(grid_size):
        for c in range(grid_size):
            if mask[r][c] and not used[r][c]:
                mask[r][c] = False  # turn into black cell

    # 4) Recompute slots based on the cleaned mask
    final_slots = slots_from_mask(mask)

    return mask, final_slots

def assign_numbers(mask, slots):
    """Number only *real* slots, no stray numbers."""
    grid_size = len(mask)
    number_grid = [[0] * grid_size for _ in range(grid_size)]

    # Map from real slot starts to slot index
    start_map = {}
    for idx, s in enumerate(slots):
        start_map[(s["row"], s["col"], s["dir"])] = idx

    num = 1
    for r in range(grid_size):
        for c in range(grid_size):
            if not mask[r][c]:
                continue

            has_across = (r, c, "across") in start_map
            has_down   = (r, c, "down")   in start_map

            if has_across or has_down:
                number_grid[r][c] = num
                if has_across:
                    slots[start_map[(r, c, "across")]]["number"] = num
                if has_down:
                    slots[start_map[(r, c, "down")]]["number"] = num
                num += 1

    return number_grid, slots


# ------------------------------
# FILL ALGORITHM (MULTI-RESTART)
# ------------------------------
def fill_crossword(mask, slots, words_by_length,
                   max_restarts=2000, max_attempts_per_slot=300):
    grid_size = len(mask)

    def make_blank():
        return [
            [None if not mask[r][c] else "" for c in range(grid_size)]
            for r in range(grid_size)
        ]

    def fits(grid, slot, word):
        r, c, d = slot["row"], slot["col"], slot["dir"]
        for i, ch in enumerate(word):
            rr = r + (i if d == "down" else 0)
            cc = c + (i if d == "across" else 0)
            existing = grid[rr][cc]
            if existing not in ("", None, ch):
                return False
        return True

    def place(grid, slot, word):
        r, c, d = slot["row"], slot["col"], slot["dir"]
        for i, ch in enumerate(word):
            rr = r + (i if d == "down" else 0)
            cc = c + (i if d == "across" else 0)
            grid[rr][cc] = ch
        slot["word"] = word

    slots_copy = [dict(s) for s in slots]

    for attempt in range(max_restarts):
        grid = make_blank()
        for s in slots_copy:
            s.pop("word", None)

        order = list(range(len(slots_copy)))
        random.shuffle(order)
        ok = True

        for idx in order:
            slot = slots_copy[idx]
            L = slot["length"]
            candidates = words_by_length.get(L, [])
            if not candidates:
                ok = False
                break

            tries = 0
            word = random.choice(candidates)

            while not fits(grid, slot, word):
                word = random.choice(candidates)
                tries += 1
                if tries > max_attempts_per_slot:
                    ok = False
                    break

            if not ok:
                break

            place(grid, slot, word)

        if ok:
            return True, grid, slots_copy

    return False, None, slots_copy


# ------------------------------
# GUI
# ------------------------------
def build_gui(grid, number_grid, slots_with_clues, pattern_used):
    root = tk.Tk()
    root.title("Mini Crossword 6×6")

    # Optional: show which pattern index was used (for debugging)
    # root.title(f"Mini Crossword 6×6 – pattern variant")

    frame = tk.Frame(root)
    frame.pack(padx=10, pady=10)

    entry_grid = [[None for _ in range(GRID_SIZE)] for _ in range(GRID_SIZE)]

    CELL_SIZE = 40  # total cell size in pixels

    for r in range(GRID_SIZE):
        for c in range(GRID_SIZE):
            is_block = grid[r][c] is None

            cell_bg = "black" if is_block else "white"
            cell = tk.Frame(frame, width=CELL_SIZE, height=CELL_SIZE,
                            bg=cell_bg, bd=1, relief="solid")
            cell.grid(row=r, column=c, padx=1, pady=1)
            cell.grid_propagate(False)

            if is_block:
                continue

            cell.rowconfigure(0, weight=1)
            cell.rowconfigure(1, weight=3)
            cell.columnconfigure(0, weight=1)

            # Number label (small, top-left)
            if number_grid[r][c]:
                num_label = tk.Label(
                    cell,
                    text=str(number_grid[r][c]),
                    font=("Arial", 8),
                    bg=cell_bg,
                    fg="black",
                    anchor="nw"
                )
                num_label.grid(row=0, column=0, sticky="nw", padx=1, pady=0)

            # Entry for the letter
            e = tk.Entry(
                cell,
                width=2,
                font=("Consolas", 18),
                justify="center",
                bd=0,
                highlightthickness=0,
            )
            e.grid(row=1, column=0, sticky="nsew", pady=(0, 2))

            entry_grid[r][c] = e

    solution = grid

    def check_all():
        for r in range(GRID_SIZE):
            for c in range(GRID_SIZE):
                if solution[r][c] is None:
                    continue
                e = entry_grid[r][c]
                if e is None:
                    continue
                guess = e.get().strip().lower()
                correct = solution[r][c].lower()
                if not guess:
                    continue
                if guess == correct:
                    e.config(bg="pale green")
                else:
                    e.config(bg="white")

    def reveal():
        for r in range(GRID_SIZE):
            for c in range(GRID_SIZE):
                if solution[r][c] is None:
                    continue
                e = entry_grid[r][c]
                if e is None:
                    continue
                e.delete(0, tk.END)
                e.insert(0, solution[r][c])
                e.config(bg="light blue")

    button_frame = tk.Frame(root)
    button_frame.pack(pady=10)
    tk.Button(button_frame, text="Check All", command=check_all).pack(side="left", padx=5)
    tk.Button(button_frame, text="Reveal", command=reveal).pack(side="left", padx=5)

    # Clues frame
    clues_frame = tk.Frame(root)
    clues_frame.pack(padx=10, pady=10, anchor="w")

    tk.Label(clues_frame, text="Across:", font=("Arial", 10, "bold")).pack(anchor="w")
    for s in sorted(slots_with_clues, key=lambda x: (x["dir"] != "across", x["number"])):
        if s["dir"] == "across":
            tk.Label(clues_frame, text=f"{s['number']}. {s['clue']}").pack(anchor="w")

    tk.Label(clues_frame, text="Down:", font=("Arial", 10, "bold")).pack(anchor="w")
    for s in sorted(slots_with_clues, key=lambda x: (x["dir"] != "down", x["number"])):
        if s["dir"] == "down":
            tk.Label(clues_frame, text=f"{s['number']}. {s['clue']}").pack(anchor="w")

    root.mainloop()


# ------------------------------
# MAIN
# ------------------------------
def main():

    with open(LOG_PATH, "w", encoding="utf-8") as f:
        f.write("=== Mini crossword starting ===\n")

    try:
        log(f"BASE_DIR = {BASE_DIR}")
        log(f"WORDLIST_PATH = {WORDLIST_PATH}")

        words = load_words()
        words_by_length = build_wordlists(words)
        log(f"Loaded {len(words)} words.")

        # Pick a random pattern variant
        pattern = random_pattern(BASE_PATTERN)
        log(f"Pattern used: {pattern}")

        mask, slots = build_slots(pattern)
        log(f"Slots: {len(slots)}")
        for s in slots:
            log(f"Slot: {s}")

        number_grid, slots = assign_numbers(mask, slots)

        log("Starting fill...")
        success, grid, slots_filled = fill_crossword(mask, slots, words_by_length)
        log(f"Success = {success}")

        if not success:
            messagebox.showerror("Error", "Failed to fill crossword with current wordlist.")
            return

        log("Fetching clues...")
        for s in slots_filled:
            word = s["word"]

            # 1) Get a safe dictionary-style definition
            base_def = get_definition(word)

            # 2) Ask the LLM to jazz it up
            fancy_clue = get_llm_clue(word, base_definition=base_def)

            # 3) Use the LLM clue as the one shown in the UI
            s["clue"] = fancy_clue

        build_gui(grid, number_grid, slots_filled, pattern_used=pattern)

    except Exception as e:
        traceback.print_exc()
        messagebox.showerror("Error", f"Unexpected error:\n\n{e}")


if __name__ == "__main__":
    main()