import tkinter as tk
import random
import os
import requests

# ------------------------------
# CONFIGURATION
# ------------------------------
GRID_SIZE = 6
WORD_MIN = 4
WORD_MAX = 6
NUM_WORDS = 8  # number of words to place

BASE_DIR = os.path.dirname(__file__)
WORDLIST_PATH = os.path.join(BASE_DIR, "wordlist.txt")

# ------------------------------
# LOAD WORDLIST
# ------------------------------
def load_words(min_len=WORD_MIN, max_len=WORD_MAX):
    words = []
    with open(WORDLIST_PATH, "r", encoding="utf-8") as f:
        for line in f:
            w = line.strip().lower()
            if w.isalpha() and min_len <= len(w) <= max_len:
                words.append(w)
    return words

words_pool = load_words()

# ------------------------------
# FETCH DEFINITIONS
# ------------------------------
definition_cache = {}

def get_definition(word):
    if word in definition_cache:
        return definition_cache[word]
    try:
        response = requests.get(f"https://api.dictionaryapi.dev/api/v2/entries/en/{word}")
        data = response.json()
        if isinstance(data, list) and 'meanings' in data[0]:
            definition = data[0]['meanings'][0]['definitions'][0]['definition']
            definition_cache[word] = definition
            return definition
    except:
        pass
    return "No clue available"

# ------------------------------
# CROSSWORD GENERATION
# ------------------------------
grid = [[None for _ in range(GRID_SIZE)] for _ in range(GRID_SIZE)]
number_grid = [[0 for _ in range(GRID_SIZE)] for _ in range(GRID_SIZE)]
words_info = []
number_counter = 1

def can_place(word, row, col, direction):
    """Check if word fits at position with overlap rules."""
    if direction == 'across':
        if col + len(word) > GRID_SIZE:
            return False
        for i, letter in enumerate(word):
            cell = grid[row][col+i]
            if cell not in (None, letter):
                return False
        return True
    else:  # down
        if row + len(word) > GRID_SIZE:
            return False
        for i, letter in enumerate(word):
            cell = grid[row+i][col]
            if cell not in (None, letter):
                return False
        return True

def place_word(word, row, col, direction, clue):
    global number_counter
    if direction == 'across':
        if number_grid[row][col] == 0:
            number_grid[row][col] = number_counter
            number = number_counter
            number_counter += 1
        else:
            number = number_grid[row][col]
        for i, letter in enumerate(word):
            grid[row][col+i] = letter
    else:  # down
        if number_grid[row][col] == 0:
            number_grid[row][col] = number_counter
            number = number_counter
            number_counter += 1
        else:
            number = number_grid[row][col]
        for i, letter in enumerate(word):
            grid[row+i][col] = letter

    words_info.append({
        "word": word,
        "row": row,
        "col": col,
        "dir": direction,
        "number": number,
        "clue": clue
    })

def generate_crossword():
    placed_words = 0
    attempts = 0
    max_attempts = 300
    used_words = set()
    while placed_words < NUM_WORDS and attempts < max_attempts:
        word = random.choice([w for w in words_pool if w not in used_words])
        direction = random.choice(['across', 'down'])
        row = random.randint(0, GRID_SIZE-1)
        col = random.randint(0, GRID_SIZE-1)
        if can_place(word, row, col, direction):
            clue = get_definition(word)
            place_word(word, row, col, direction, clue)
            used_words.add(word)
            placed_words += 1
        attempts += 1
    # Fill empty cells with black squares if no letters
    for r in range(GRID_SIZE):
        for c in range(GRID_SIZE):
            if grid[r][c] is None:
                grid[r][c] = None  # explicitly mark as blocked

generate_crossword()

# ------------------------------
# TKINTER GUI
# ------------------------------
root = tk.Tk()
root.title("Mini Crossword 6x6 (NYT-style)")

frame = tk.Frame(root)
frame.pack(padx=10, pady=10)

entry_grid = [[None for _ in range(GRID_SIZE)] for _ in range(GRID_SIZE)]

CELL_SIZE = 35

for r in range(GRID_SIZE):
    for c in range(GRID_SIZE):
        bg_color = "white" if grid[r][c] else "black"
        e = tk.Entry(frame, width=2, font=("Consolas", 18), justify="center",
                     bg=bg_color, disabledbackground="black", disabledforeground="black")
        if not grid[r][c]:
            e.config(state='disabled')
        e.grid(row=r, column=c, padx=1, pady=1)
        entry_grid[r][c] = e

        # show number in top-left corner
        if number_grid[r][c]:
            lbl = tk.Label(frame, text=str(number_grid[r][c]), font=("Consolas", 8), bg=bg_color)
            lbl.place(x=c*CELL_SIZE+2, y=r*CELL_SIZE+0)

# ------------------------------
# CHECK / REVEAL FUNCTIONS
# ------------------------------
def check_all():
    for r in range(GRID_SIZE):
        for c in range(GRID_SIZE):
            e = entry_grid[r][c]
            correct_letter = grid[r][c]
            if not correct_letter or e.get() == '':
                continue
            if e.get().lower() == correct_letter.lower():
                e.config(bg="green")
            else:
                e.config(bg="white")

def reveal_solution():
    for r in range(GRID_SIZE):
        for c in range(GRID_SIZE):
            e = entry_grid[r][c]
            if grid[r][c]:
                e.delete(0, tk.END)
                e.insert(0, grid[r][c])
                e.config(bg="lightblue")

# ------------------------------
# BUTTONS
# ------------------------------
button_frame = tk.Frame(root)
button_frame.pack(pady=10)

check_btn = tk.Button(button_frame, text="Check All", command=check_all)
check_btn.pack(side="left", padx=5)

reveal_btn = tk.Button(button_frame, text="Reveal Solution", command=reveal_solution)
reveal_btn.pack(side="left", padx=5)

# ------------------------------
# CLUES FRAME
# ------------------------------
clues_frame = tk.Frame(root)
clues_frame.pack(pady=10)

tk.Label(clues_frame, text="Across:").pack(anchor="w")
for w in words_info:
    if w['dir'] == 'across':
        tk.Label(clues_frame, text=f"{w['number']}. {w['clue']}").pack(anchor="w")

tk.Label(clues_frame, text="Down:").pack(anchor="w")
for w in words_info:
    if w['dir'] == 'down':
        tk.Label(clues_frame, text=f"{w['number']}. {w['clue']}").pack(anchor="w")

root.mainloop()
