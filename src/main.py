# src/main.py
import tkinter as tk
from tkinter import messagebox
import random
import requests
import threading
import os

BASE_DIR=os.path.dirname(os.path.abspath(__file__))
WORDLIST_PATH = os.path.join(BASE_DIR, "wordlist.txt")
def load_wordlist(min_len=4, max_len=6):
    words = []
    with open(WORDLIST_PATH, "r", encoding="utf-8") as f:
        for line in f:
            w = line.strip().lower()
            if w.isalpha() and min_len <= len(w) <= max_len:
                words.append(w)
    return words

def fetch_definition(word):
    #dictionaryapi.dev
    url = f"https://api.dictionaryapi.dev/api/v2/entries/en/{word}"
    try:
        r = requests.get(url, timeout =5)
        if r.status_code == 200:
            data = r.json()
            defs =[]
            for entry in data:
                meanings = entry.get("meanings", [])
                for m in meanings:
                    for d in m.get("definitions", []):
                        defs.append(d.get("definition"))
                if defs:
                    return defs[0]
        return "No definition found."
    except Exception as e:
        return f"Error fetching definition: {e}"

class MiniCrosswordApp:
    def __init__(self, master, words):
        self.master = master
        self.words = words
        master.title("Mini Crossword")

        self.word_var=tk.StringVar()
        self.clue_var=tk.StringVar(value = "Click 'New' to generate a word.")

        label = tk.Label(master, text="Word (guess letters):")
        label.pack(padx=8, pady=(8,0))

        self.entry= tk.Entry(master, textvariable=self.word_var, font=("Consolas", 18), justify="center", width=10)
        self.entry.pack(padx=8, pady=8)

        hb = tk.Frame(master)
        hb.pack(padx=8, pady=8, fill="x")
        tk.Button(hb, text="New", command=self.new_word).pack(side="left")
        tk.Button(hb, text="Show clue (fetch)", command=self.show_clue).pack(side="left", padx=8)
        tk.Button(hb, text="Check", command=self.check).pack(side="left")

        self.clue_label = tk.Label(master, textvariable=self.clue_var, wraplength=300, justify="left")
        self.clue_label.pack(padx=8, pady=(0,8))

        self.status = tk.Label(master, text="", fg="green")
        self.status.pack(padx=8, pady=(0,8))

        self.current_word = None

    def new_word(self):
        self.current_word = random.choice(self.words)
        self.word_var.set("_ " * len(self.current_word))
        self.clue_var.set("Click 'Show clue' to get a definition.")
        self.status.config(text="")
        
    def show_clue(self):
        if not self.current_word:
            messagebox.show_info("Info", "Generate a new word first.")
            return
        def worker():
            self.clue_var.set("Fetching definition...")
            s = fetch_definition(self.current_word)
            self.clue_var.set(s)
        threading.Thread(target=worker, daemon=True).start()
    
    def check(self):
        if not self.current_word:
            messagebox.showinfo("Info", "Generate a new word first.")
            return

        typed = self.entry.get().replace(" ", "").replace("_", "").lower()#print(BASE_DIR)
        cleaned = "".join(ch for ch in typed if ch.isalpha())
        if cleaned == self.current_word:
            self.status.config(text="Correct!", fg="green")
        else:
            self.status.config(text=f"Incorrect (Answer length {len(self.current_word)})", fg="red")

if __name__ == "__main__":
    words = load_wordlist(4,6)
    if not words:
        raise SystemExit("No Words Found in wordlist.txt")
    
    root = tk.Tk()
    app=MiniCrosswordApp(root, words)
    root.mainloop()