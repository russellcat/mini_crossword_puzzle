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
GRID_SIZE = 6
WORD_MIN = 4
WORD_MAX = 6

# Detect if running as PyInstaller bundle or as a normal script
if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
    BASE_DIR = sys._MEIPASS
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

WORDLIST_PATH = os.path.join(BASE_DIR, "wordlist.txt")
LOG_PATH = os.path.join(BASE_DIR, "debug.log")

# Pattern for blocks:
# '.' = white (letter) cell
# '#' = black (blocked) cell
PATTERN = [
    "....##",
    "......",
    "......",
    "......",
    "......",
    "#.....",
]

# ------------------------------
# LOGGING
# ------------------------------
def log(msg: str) -> None:
    try:
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(msg + "\n")
    except Exception:
        pass

# ------------------------------
# WORDLIST LOADING
# ------------------------------
def load_words(min_len=WORD_MIN, max_len=WORD_MAX):
    if not os.path.exists(WORDLIST_PATH):
        raise FileNotFoundError(f"wordlist.txt not found at: {WORDLIST_PATH}")

    words = []
    with open(WORDLIST_PATH, "r", encoding="utf-8") as f:
        for line in f:
            w = line.strip().lower()
            if w.isalpha() and min_len <= len(w) <= max_len:
                words.append(w)

    if not words:
        raise RuntimeError(
            f"wordlist.txt has no usable words in range {min_len}–{max_len} letters."
        )
    return words

def build_wordlists(words):
    by_len = {}
    for w in words:
        by_len.setdefault(len(w), []).append(w)
    return by_len

# ------------------------------
# DICTIONARY API (CLUE FETCHING)
# ------------------------------
definition_cache = {}

def get_definition(word: str) -> str:
    """
    Fetch the first definition using dictionaryapi.dev.

    In a PyInstaller exe (frozen), we skip network calls and just
    return a placeholder clue to avoid hangs / SSL issues.
    """
    # If running as a bundled exe, avoid network calls to keep it snappy
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return f"Clue for '{word}'"

    if word in definition_cache:
        return definition_cache[word]

    url = f"https://api.dictionaryapi.dev/api/v2/entries/en/{word}"
    try:
        r = requests.get(url, timeout=5)
        if r.status_code == 200:
            data = r.json()
            if isinstance(data, list) and data and "meanings" in data[0]:
                meanings = data[0]["meanings"]
                if (
                    meanings
                    and "definitions" in meanings[0]
                    and meanings[0]["definitions"]
                ):
                    definition = meanings[0]["definitions"][0].get("definition", "")
                    if definition:
                        definition_cache[word] = definition
                        return definition
    except Exception as e:
        print(f"Error fetching definition for {word}: {e}")

    definition_cache[word] = "No clue available."
    return "No clue available."

# ------------------------------
# BUILD MASK AND SLOTS FROM PATTERN
# ------------------------------
def build_slots_from_pattern(pattern):
    """Create mask (True=white) and list of slots from pattern."""
    grid_size = len(pattern)
    mask = [[ch == "." for ch in row] for row in pattern]
    slots = []

    # Across slots
    for r in range(grid_size):
        c = 0
        while c < grid_size:
            if mask[r][c] and (c == 0 or not mask[r][c - 1]):
                start = c
                while c < grid_size and mask[r][c]:
                    c += 1
                length = c - start
                slots.append(
                    {"dir": "across", "row": r, "col": start, "length": length}
                )
            else:
                c += 1

    # Down slots
    for c in range(grid_size):
        r = 0
        while r < grid_size:
            if mask[r][c] and (r == 0 or not mask[r - 1][c]):
                start = r
                while r < grid_size and mask[r][c]:
                    r += 1
                length = r - start
                slots.append(
                    {"dir": "down", "row": start, "col": c, "length": length}
                )
            else:
                r += 1

    return mask, slots

def assign_numbers(mask, slots):
    """Number slots like a real crossword (1, 2, 3...) shared across Across/Down."""
    grid_size = len(mask)
    number_grid = [[0] * grid_size for _ in range(grid_size)]

    # Map from (row,col,dir) to slot index
    start_map = {}
    for idx, slot in enumerate(slots):
        start_map[(slot["row"], slot["col"], slot["dir"])] = idx

    num = 1
    for r in range(grid_size):
        for c in range(grid_size):
            if not mask[r][c]:
                continue
            starts_across = (c == 0 or not mask[r][c - 1])
            starts_down = (r == 0 or not mask[r - 1][c])
            if starts_across or starts_down:
                number_grid[r][c] = num
                if starts_across:
                    idx = start_map[(r, c, "across")]
                    slots[idx]["number"] = num
                if starts_down:
                    idx = start_map[(r, c, "down")]
                    slots[idx]["number"] = num
                num += 1

    return number_grid, slots

# ------------------------------
# BACKTRACKING FILL ALGORITHM
# ------------------------------
def fill_crossword(mask, slots, words_by_length, max_attempts_per_slot=200):
    """
    Backtracking fill: assign a word to each slot so crossings match.

    IMPORTANT:
    - We DO allow reusing the same word in multiple slots (no 'used' set),
      to make a solution much more likely with a small wordlist.
    """
    grid_size = len(mask)
    # solution grid: '' for empty white, None for block, letter for filled
    grid = [
        [None if not mask[r][c] else "" for c in range(grid_size)]
        for r in range(grid_size)
    ]
    slot_count = len(slots)

    def fits(slot, word):
        r, c, dirn = slot["row"], slot["col"], slot["dir"]
        for i, ch in enumerate(word):
            rr = r + (i if dirn == "down" else 0)
            cc = c + (i if dirn == "across" else 0)
            cell = grid[rr][cc]
            if cell not in ("", ch):
                return False
        return True

    def place(slot, word):
        r, c, dirn = slot["row"], slot["col"], slot["dir"]
        changed = []
        for i, ch in enumerate(word):
            rr = r + (i if dirn == "down" else 0)
            cc = c + (i if dirn == "across" else 0)
            if grid[rr][cc] == "":
                grid[rr][cc] = ch
                changed.append((rr, cc))
        slot["word"] = word
        return changed

    def unplace(changed, slot):
        for rr, cc in changed:
            grid[rr][cc] = ""
        slot.pop("word", None)

    # Heuristic: shorter slots first
    order = sorted(range(slot_count), key=lambda i: slots[i]["length"])

    def backtrack(idx):
        if idx == slot_count:
            return True

        slot_index = order[idx]
        slot = slots[slot_index]
        length = slot["length"]
        candidates = words_by_length.get(length, [])
        if not candidates:
            return False

        r, c, dirn = slot["row"], slot["col"], slot["dir"]
        known = [None] * length
        for i in range(length):
            rr = r + (i if dirn == "down" else 0)
            cc = c + (i if dirn == "across" else 0)
            if grid[rr][cc] not in ("", None):
                known[i] = grid[rr][cc]

        # filter candidates by known letters (we allow repeats)
        filtered = [
            w
            for w in candidates
            if all(known[i] is None or known[i] == w[i] for i in range(length))
        ]

        random.shuffle(filtered)
        for w in filtered[:max_attempts_per_slot]:
            if fits(slot, w):
                changed = place(slot, w)
                if backtrack(idx + 1):
                    return True
                unplace(changed, slot)
        return False

    ok = backtrack(0)
    return ok, grid, slots

# ------------------------------
# GUI BUILDING
# ------------------------------
def build_gui(solution_grid, number_grid, words_info):
    grid_size = len(solution_grid)

    root = tk.Tk()
    root.title("Mini Crossword 6x6")

    frame = tk.Frame(root)
    frame.pack(padx=10, pady=10)

    entry_grid = [[None for _ in range(grid_size)] for _ in range(grid_size)]

    CELL_SIZE = 35  # for placing numbers nicely

    for r in range(grid_size):
        for c in range(grid_size):
            is_block = solution_grid[r][c] is None
            bg_color = "black" if is_block else "white"
            e = tk.Entry(
                frame,
                width=2,
                font=("Consolas", 18),
                justify="center",
                bg=bg_color,
                disabledbackground="black",
                disabledforeground="black",
            )
            if is_block:
                e.config(state="disabled")
            e.grid(row=r, column=c, padx=1, pady=1)
            entry_grid[r][c] = e

            if number_grid[r][c] and not is_block:
                lbl = tk.Label(
                    frame,
                    text=str(number_grid[r][c]),
                    font=("Consolas", 8),
                    bg=bg_color,
                )
                lbl.place(x=c * CELL_SIZE + 2, y=r * CELL_SIZE + 0)

    def check_all():
        for r in range(grid_size):
            for c in range(grid_size):
                if solution_grid[r][c] is None:
                    continue
                e = entry_grid[r][c]
                guess = e.get().strip().lower()
                correct = solution_grid[r][c].lower()
                if not guess:
                    continue
                if guess == correct:
                    e.config(bg="green")
                else:
                    e.config(bg="white")

    def reveal_solution():
        for r in range(grid_size):
            for c in range(grid_size):
                if solution_grid[r][c] is None:
                    continue
                e = entry_grid[r][c]
                e.delete(0, tk.END)
                e.insert(0, solution_grid[r][c])
                e.config(bg="lightblue")

    button_frame = tk.Frame(root)
    button_frame.pack(pady=10)

    tk.Button(button_frame, text="Check All", command=check_all).pack(
        side="left", padx=5
    )
    tk.Button(button_frame, text="Reveal Solution", command=reveal_solution).pack(
        side="left", padx=5
    )

    clues_frame = tk.Frame(root)
    clues_frame.pack(pady=10)

    tk.Label(clues_frame, text="Across:", font=("Arial", 10, "bold")).pack(anchor="w")
    for w in sorted(
        words_info, key=lambda x: (x["dir"] != "across", x["number"], x["word"])
    ):
        if w["dir"] == "across":
            tk.Label(
                clues_frame, text=f"{w['number']}. {w['clue']}"
            ).pack(anchor="w")

    tk.Label(clues_frame, text="Down:", font=("Arial", 10, "bold")).pack(anchor="w")
    for w in sorted(
        words_info, key=lambda x: (x["dir"] != "down", x["number"], x["word"])
    ):
        if w["dir"] == "down":
            tk.Label(
                clues_frame, text=f"{w['number']}. {w['clue']}"
            ).pack(anchor="w")

    root.mainloop()

# ------------------------------
# MAIN (WITH ERROR HANDLING)
# ------------------------------
def main():
    # Start fresh log each run
    try:
        with open(LOG_PATH, "w", encoding="utf-8") as f:
            f.write("=== Mini crossword starting ===\n")
    except Exception:
        pass

    try:
        log(f"BASE_DIR = {BASE_DIR}")
        log(f"WORDLIST_PATH = {WORDLIST_PATH}")

        log("Loading words...")
        words = load_words()
        words_by_length = build_wordlists(words)
        log(f"Loaded {len(words)} total words.")

        mask, slots = build_slots_from_pattern(PATTERN)
        number_grid, slots_with_numbers = assign_numbers(mask, slots)

        needed_lengths = sorted({slot["length"] for slot in slots_with_numbers})
        log(f"Slot lengths needed: {needed_lengths}")
        for L in needed_lengths:
            log(f"Length {L}: {len(words_by_length.get(L, []))} candidates")

        log("Starting fill_crossword...")
        success, solution_grid, filled_slots = fill_crossword(
            mask, slots_with_numbers, words_by_length
        )
        log(f"fill_crossword success = {success}")
        if not success:
            raise RuntimeError(
                "Failed to fill crossword with the given wordlist. "
                "Try adding more words or changing the pattern."
            )

        log("Fetching clues...")
        words_info = []
        for slot in filled_slots:
            w = slot["word"]
            clue = get_definition(w)
            words_info.append(
                {
                    "word": w,
                    "row": slot["row"],
                    "col": slot["col"],
                    "dir": slot["dir"],
                    "number": slot["number"],
                    "clue": clue,
                }
            )
        log("Clues fetched. Building GUI...")

        build_gui(solution_grid, number_grid, words_info)
        log("GUI closed normally.")

    except Exception as e:
        # Print to console (helpful when running .py)
        traceback.print_exc()

        # Show in GUI (so .exe doesn't just vanish)
        messagebox.showerror(
            "Error",
            f"The crossword app crashed:\n\n{e}\n\n"
            f"See error.log for more details (if it could be written).",
        )

        # Try to write a log file next to exe/script
        try:
            if getattr(sys, "frozen", False):
                log_dir = os.path.dirname(sys.executable)
            else:
                log_dir = os.path.dirname(os.path.abspath(__file__))
            log_path = os.path.join(log_dir, "error.log")
            with open(log_path, "w", encoding="utf-8") as f:
                traceback.print_exc(file=f)
        except Exception:
            pass

if __name__ == "__main__":
    main()
