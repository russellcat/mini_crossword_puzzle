import tkinter as tk
from tkinter import messagebox
import random
import os
import sys
import requests
import traceback

# ------------------------------
# CONFIGURATION
# ------------------------------
GRID_SIZE = 5
WORD_MIN = 5
WORD_MAX = 5

if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
    BASE_DIR = sys._MEIPASS
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

WORDLIST_PATH = os.path.join(BASE_DIR, "wordlist.txt")
LOG_PATH = os.path.join(BASE_DIR, "debug.log")

PATTERN = [
    ".....",
    ".....",
    ".....",
    ".....",
    "....."
]

# ------------------------------
# LOGGING
# ------------------------------
def log(msg: str):
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(msg + "\n")


# ------------------------------
# WORDLIST LOADING
# ------------------------------
def load_words(min_len=5, max_len=5):
    words = []
    with open(WORDLIST_PATH, "r", encoding="utf-8") as f:
        for w in f:
            w = w.strip().lower()
            if w.isalpha() and min_len <= len(w) <= max_len:
                words.append(w)
    if not words:
        raise RuntimeError("No usable words found.")
    return words


def build_wordlists(words):
    result = {}
    for w in words:
        result.setdefault(len(w), []).append(w)
    return result


# ------------------------------
# DICTIONARY LOOKUP (CLUES)
# ------------------------------
definition_cache = {}

def get_definition(word: str) -> str:
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return f"Clue for {word}"

    if word in definition_cache:
        return definition_cache[word]

    url = f"https://api.dictionaryapi.dev/api/v2/entries/en/{word}"
    try:
        r = requests.get(url, timeout=5)
        if r.status_code == 200:
            data = r.json()
            meanings = data[0].get("meanings", [])
            if meanings:
                defs = meanings[0].get("definitions", [])
                if defs:
                    d = defs[0].get("definition", "")
                    if d:
                        definition_cache[word] = d
                        return d
    except:
        pass

    return "No clue available."


# ------------------------------
# SLOT CREATION
# ------------------------------
def build_slots(pattern):
    grid_size = len(pattern)
    mask = [[c == "." for c in row] for row in pattern]
    slots = []

    # Across
    for r in range(grid_size):
        c = 0
        while c < grid_size:
            if mask[r][c] and (c == 0 or not mask[r][c - 1]):
                start = c
                while c < grid_size and mask[r][c]:
                    c += 1
                L = c - start
                if WORD_MIN <= L <= WORD_MAX:
                    slots.append({"dir": "across", "row": r, "col": start, "length": L})
            else:
                c += 1

    # Down
    for c in range(grid_size):
        r = 0
        while r < grid_size:
            if mask[r][c] and (r == 0 or not mask[r - 1][c]):
                start = r
                while r < grid_size and mask[r][c]:
                    r += 1
                L = r - start
                if WORD_MIN <= L <= WORD_MAX:
                    slots.append({"dir": "down", "row": start, "col": c, "length": L})
            else:
                r += 1

    return mask, slots


# ------------------------------
# GUARANTEED FILL ALGORITHM
# ------------------------------
def fill_crossword(mask, slots, words_by_length,
                   max_restarts=2000, max_attempts_per_slot=200):
    grid_size = len(mask)

    def blank():
        return [[None if not mask[r][c] else "" for c in range(grid_size)]
                for r in range(grid_size)]

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

    for attempt in range(max_restarts):
        grid = blank()
        shuffled = slots[:]
        random.shuffle(shuffled)
        ok = True

        for slot in shuffled:
            L = slot["length"]
            words = words_by_length[L]
            tries = 0
            word = random.choice(words)

            while not fits(grid, slot, word):
                word = random.choice(words)
                tries += 1
                if tries > max_attempts_per_slot:
                    ok = False
                    break
            if not ok:
                break

            place(grid, slot, word)

        if ok:
            return True, grid, shuffled

    return False, None, None


# ------------------------------
# GUI
# ------------------------------
def build_gui(grid, slots):
    root = tk.Tk()
    root.title("Mini Crossword 5×5")

    frame = tk.Frame(root)
    frame.pack(padx=10, pady=10)

    entries = []
    for r in range(GRID_SIZE):
        row = []
        for c in range(GRID_SIZE):
            e = tk.Entry(frame, width=2, font=("Consolas", 18), justify="center")
            e.grid(row=r, column=c, padx=2, pady=2)
            row.append(e)
        entries.append(row)

    solution = [[grid[r][c] for c in range(GRID_SIZE)] for r in range(GRID_SIZE)]

    def check():
        for r in range(GRID_SIZE):
            for c in range(GRID_SIZE):
                guess = entries[r][c].get().lower()
                if guess == solution[r][c].lower():
                    entries[r][c].config(bg="green")
                else:
                    entries[r][c].config(bg="white")

    def reveal():
        for r in range(GRID_SIZE):
            for c in range(GRID_SIZE):
                entries[r][c].delete(0, tk.END)
                entries[r][c].insert(0, solution[r][c])
                entries[r][c].config(bg="lightblue")

    tk.Button(root, text="Check", command=check).pack(side="left", padx=10)
    tk.Button(root, text="Reveal", command=reveal).pack(side="left", padx=10)

    root.mainloop()


# ------------------------------
# MAIN
# ------------------------------
def main():
    with open(LOG_PATH, "w") as f:
        f.write("=== Mini crossword starting ===\n")

    log(f"BASE_DIR = {BASE_DIR}")
    log(f"WORDLIST_PATH = {WORDLIST_PATH}")

    words = load_words()
    words_by_length = build_wordlists(words)

    log(f"Loaded {len(words)} words.")
    mask, slots = build_slots(PATTERN)
    log(f"PATTERN RAW = {PATTERN}")
    for row in PATTERN:
        log(f"ROW:{repr(row)}  LEN={len(row)}")
    log(f"Slots: {len(slots)}")
    log("Starting fill...")

    success, grid, sl = fill_crossword(mask, slots, words_by_length)

    log(f"Success = {success}")

    if not success:
        messagebox.showerror("Fill Failed", "Puzzle could not be filled.")
        return

    # Fetch clues
    log("Fetching clues...")
    for slot in sl:
        slot["clue"] = get_definition(slot["word"])

    build_gui(grid, sl)


if __name__ == "__main__":
    main()
