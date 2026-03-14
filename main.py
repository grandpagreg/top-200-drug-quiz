import sys
import json
import os
import tkinter as tk
from tkinter import messagebox
import random
import csv
import time
import webbrowser

# ============================
# STRING HELPERS
# ============================

def clean_string(s):
    if not s:
        return ""
    return s.replace("\xa0", " ").strip()

def normalize_schedule(s):
    s = clean_string(s).upper()

    if not s:
        return "NCLM"

    if "OTC" in s:
        return "OTC"
    if "III" in s:
        return "III"
    if "IV" in s:
        return "IV"
    if "II" in s:
        return "II"
    if "V" in s:
        return "V"

    return "NCLM"

# ============================
# DATA FILE LOCATION
# ============================

def get_data_file(filename):
    home = os.path.expanduser("~")
    app_folder = os.path.join(home, ".drug_quiz_data")
    os.makedirs(app_folder, exist_ok=True)
    return os.path.join(app_folder, filename)

stats_file = get_data_file("stats.json")

DATASET_VERSION = "Top 200 (2026 Edition)"

# ============================
# LOAD DATA
# ============================

def load_stats():
    if not os.path.exists(stats_file):
        return {}

    try:
        with open(stats_file, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        # Backup corrupted file
        backup_path = stats_file + ".corrupted_backup"
        try:
            os.rename(stats_file, backup_path)
        except OSError:
            pass

        messagebox.showwarning(
            "Stats Reset",
            "Statistics file was corrupted and has been reset.\n\n"
            "A backup was saved as stats.json.corrupted_backup"
        )

        return {}

def load_classifications(filename):
    classifications = {}
    with open(filename, newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        next(reader)
        for row in reader:
            if len(row) >= 2:
                generic = clean_string(row[0])
                category = clean_string(row[1])
                classifications[generic] = category
    return classifications

def load_drugs(filename, classifications):
    drugs = []
    uncategorized = []

    with open(filename, newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        next(reader)

        for row in reader:
            if len(row) >= 5:
                brand = clean_string(row[0])
                generic = clean_string(row[1])
                drug_class = clean_string(row[2])
                treatment = clean_string(row[3])
                schedule = normalize_schedule(row[4])

                category = classifications.get(generic)

                if not category:
                    category = "Uncategorized"
                    uncategorized.append(generic)

                drugs.append({
                    "category": category,
                    "brand": brand,
                    "generic": generic,
                    "class": drug_class,
                    "treatment": treatment,
                    "schedule": schedule
                })

    if uncategorized:
        print("\n⚠️ Uncategorized drugs detected:")
        for drug in uncategorized:
            print(" -", drug)

    return drugs

# ============================
# LOAD FILES
# ============================

if getattr(sys, 'frozen', False):
    base_path = sys._MEIPASS
else:
    base_path = os.path.dirname(os.path.abspath(__file__))

data_path = os.path.join(base_path, "data")

top200_path = os.path.join(data_path, "top200_2026.csv")
classification_path = os.path.join(data_path, "drug_classifications.csv")

classifications = load_classifications(classification_path)
drugs = load_drugs(top200_path, classifications)

unique_values = {
    key: list(set(d[key] for d in drugs if d[key]))
    for key in ["brand", "generic", "class", "treatment", "category", "schedule"]
}

# ============================
# GLOBAL STATE
# ============================

score = 0
total = 0
mode = None
quiz_pool = []
question_index = 0
correct_answer = None
selected_categories = set(d["category"] for d in drugs)
missed_generics = set()

category_stats = load_stats()
session_category_stats = {}

# ============================
# ADAPTIVE LOGIC
# ============================

def build_adaptive_pool(filtered_drugs):
    weighted_pool = []

    for drug in filtered_drugs:
        category = drug["category"]

        lifetime = category_stats.get(category, {"correct": 0, "total": 0})
        session = session_category_stats.get(category, {"correct": 0, "total": 0})

        # Lifetime accuracy
        if lifetime["total"] > 0:
            lifetime_accuracy = lifetime["correct"] / lifetime["total"]
        else:
            lifetime_accuracy = 0.7  # neutral default

        # Session accuracy
        if session["total"] > 0:
            session_accuracy = session["correct"] / session["total"]
        else:
            session_accuracy = lifetime_accuracy

        lifetime_weakness = 1 - lifetime_accuracy
        session_weakness = 1 - session_accuracy

        # Weight recent performance slightly more
        combined_weakness = (lifetime_weakness * 0.6) + (session_weakness * 0.4)

        weight = 1 + (combined_weakness * 4)

        # Hammer if very weak this session
        if session_accuracy < 0.6:
            weight *= 1.5

        weighted_pool.extend([drug] * int(weight))

    random.shuffle(weighted_pool)
    return weighted_pool

# ============================
# QUIZ FUNCTIONS
# ============================

def update_score():
    percent = int((score / total) * 100) if total > 0 else 0
    score_label.config(text=f"Score: {score}/{total} ({percent}%)")

def new_question():
    global correct_answer, question_index

    if question_index >= len(quiz_pool):
        show_summary_screen()
        return

    drug = quiz_pool[question_index]
    question_index += 1

    if mode == "brand_generic":
        question_label.config(text=f"What is the GENERIC name?\n\nBrand: {drug['brand']}")
        correct_answer = drug["generic"]
        field = "generic"

    elif mode == "generic_brand":
        question_label.config(text=f"What is the BRAND name?\n\nGeneric: {drug['generic']}")
        correct_answer = drug["brand"]
        field = "brand"

    elif mode == "class":
        question_label.config(text=f"What is the CLASS?\n\n{drug['brand']} ({drug['generic']})")
        correct_answer = drug["class"]
        field = "class"

    elif mode == "treatment":
        question_label.config(text=f"What is the TREATMENT?\n\n{drug['brand']} ({drug['generic']})")
        correct_answer = drug["treatment"]
        field = "treatment"

    elif mode == "category":
        question_label.config(text=f"What CATEGORY?\n\n{drug['brand']} ({drug['generic']})")
        correct_answer = drug["category"]
        field = "category"

    elif mode == "schedule":
        question_label.config(text=f"What is the SCHEDULE?\n\n{drug['brand']} ({drug['generic']})")
        correct_answer = drug["schedule"]
        field = "schedule"

    else:
        return

    all_choices = [x for x in unique_values[field] if x != correct_answer]
    wrong = random.sample(all_choices, min(3, len(all_choices)))
    options = wrong + [correct_answer]
    random.shuffle(options)

    for b in buttons:
        b.destroy()
    buttons.clear()

    for option in options:
        b = tk.Button(
            answer_frame,
            text=option,
            width=70,
            height=3,
            relief="flat",
            bg="#f0f0f0",
            activebackground="#f0f0f0",
            command=lambda opt=option: answer_click(opt)
        )
        b.pack(pady=8, fill="x", padx=150)
        buttons.append(b)

def answer_click(text):
    global score, total, correct_answer

    total += 1
    category = quiz_pool[question_index - 1]["category"]

    category_stats.setdefault(category, {"correct": 0, "total": 0})
    category_stats[category]["total"] += 1

    # Disable all buttons immediately
    for b in buttons:
        b.config(state="disabled")

    # Highlight answers
    for b in buttons:
        if b["text"] == correct_answer:
            b.config(
                bg="#2ecc71",
                activebackground="#2ecc71",
                fg="white",
                highlightbackground="#2ecc71"
            )
            b.config(font=("Arial", 14))
            root.after(300, lambda btn=b: btn.config(font=("Arial", 12)))

        elif b["text"] == text and text != correct_answer:
            b.config(
                bg="#e74c3c",
                activebackground="#e74c3c",
                fg="white",
                highlightbackground="#e74c3c"
            )

    if text == correct_answer:
        score += 1
        category_stats[category]["correct"] += 1
        feedback_label.config(text="Correct!", fg="green")
    else:
        feedback_label.config(text="Incorrect!", fg="red")
        current_drug = quiz_pool[question_index - 1]
        missed_generics.add(current_drug["generic"])

    update_score()

    def save_stats_safe():
        temp_file = stats_file + ".tmp"
        with open(temp_file, "w") as f:
            json.dump(category_stats, f)
        os.replace(temp_file, stats_file)

    root.after(1500, lambda: feedback_label.config(text=""))
    root.after(2000, new_question)

def set_mode(new_mode):
    global mode, score, total, quiz_pool, question_index

    mode = new_mode
    score = 0
    total = 0
    question_index = 0

    filtered = [d for d in drugs if d["category"] in selected_categories]

    if adaptive_mode_var.get():
        quiz_pool = build_adaptive_pool(filtered)
    else:
        quiz_pool = filtered.copy()
        random.shuffle(quiz_pool)

    


    limit_value = question_limit_var.get()

    if limit_value != "All":
        limit = int(limit_value)
        quiz_pool = quiz_pool[:min(limit, len(quiz_pool))]

    update_score()
    new_question()
    end_session_button.config(state="normal")





def update_category_count():
    category_count_label.config(
        text=f"Selected Categories: {len(selected_categories)}"
    )


def select_categories():
    global selected_categories

    window = tk.Toplevel(root)
    window.title("Select Categories")
    window.geometry("350x500")

    category_vars = {}
    categories = sorted(set(d["category"] for d in drugs))

    frame = tk.Frame(window)
    frame.pack(pady=10)

    for cat in categories:
        var = tk.BooleanVar(value=(cat in selected_categories))
        category_vars[cat] = var
        tk.Checkbutton(frame, text=cat, variable=var).pack(anchor="w")

    def select_all():
        for var in category_vars.values():
            var.set(True)

    def deselect_all():
        for var in category_vars.values():
            var.set(False)

    def apply_selection():
        global selected_categories

        chosen = {cat for cat, var in category_vars.items() if var.get()}

        if not chosen:
            messagebox.showwarning("Warning", "Select at least one category.")
            return

        selected_categories = chosen
        update_category_count()
        window.destroy()

    tk.Button(window, text="Select All", command=select_all).pack(pady=5)
    tk.Button(window, text="Deselect All", command=deselect_all).pack(pady=5)

    tk.Button(
        window,
        text="Apply Selections",
        bg="lightblue",
        font=("Arial", 12),
        command=apply_selection
    ).pack(pady=15)



def show_summary_screen():
    end_session_button.config(state="disabled")
    global missed_drugs

    summary = tk.Toplevel(root)
    summary.title("Session Summary")
    summary.geometry("500x500")

    percent = int((score / total) * 100) if total > 0 else 0

    tk.Label(summary, text="Session Complete!",
             font=("Arial", 18)).pack(pady=10)

    tk.Label(summary,
             text=f"Overall Score: {score}/{total} ({percent}%)",
             font=("Arial", 14)).pack(pady=10)

    tk.Label(summary,
             text="Category Breakdown:",
             font=("Arial", 14)).pack(pady=10)

    for category, data in category_stats.items():
        cat_total = data["total"]
        cat_correct = data["correct"]
        cat_percent = int((cat_correct / cat_total) * 100) if cat_total > 0 else 0

        tk.Label(summary,
                 text=f"{category}: {cat_correct}/{cat_total} ({cat_percent}%)",
                 font=("Arial", 12)).pack(anchor="w", padx=40)

    def restart():
        summary.destroy()
        set_mode(mode)

    def retest():
        summary.destroy()

        if not missed_generics:
            messagebox.showinfo("No Missed Questions",
                            "You didn't miss any questions!")
            return

        global quiz_pool, question_index

        quiz_pool = [
            d for d in drugs
            if d["generic"] in missed_generics
        ]

        random.shuffle(quiz_pool)
        question_index = 0

        missed_generics.clear()   # ✅ instead of reassigning a new set

        update_score()
        new_question()

    tk.Button(summary, text="Restart Quiz",
              bg="lightgreen",
              command=restart).pack(pady=10)

    tk.Button(summary, text="Retest Missed Only",
              bg="#f39c12",
              command=retest).pack(pady=5)

    tk.Button(summary, text="Close",
              bg="red",
              fg="red",
              command=summary.destroy).pack(pady=5)


def open_support():
    webbrowser.open("https://buymeacoffee.com/grandpagreg")


# ============================
# UI SETUP
# ============================

def reset_lifetime_stats():
    confirm = messagebox.askyesno(
        "Confirm Reset",
        "Are you sure you want to reset ALL lifetime statistics?\n\nThis cannot be undone."
    )

    if not confirm:
        return

    global category_stats

    category_stats = {}

    # Overwrite JSON file safely
    def save_stats_safe():
        temp_file = stats_file + ".tmp"
        with open(temp_file, "w") as f:
            json.dump(category_stats, f)
        os.replace(temp_file, stats_file)

    messagebox.showinfo("Reset Complete", "Lifetime statistics have been reset.")



def show_stats():
    stats_window = tk.Toplevel(root)
    stats_window.title("Lifetime Category Performance")
    stats_window.geometry("450x400")

    tk.Label(
        stats_window,
        text="Lifetime Category Performance",
        font=("Arial", 16)
    ).pack(pady=10)

    if not category_stats:
        tk.Label(
            stats_window,
            text="No data yet.",
            font=("Arial", 12)
        ).pack(pady=20)
        return

    for category, data in category_stats.items():
        total = data.get("total", 0)
        correct = data.get("correct", 0)
        percent = int((correct / total) * 100) if total > 0 else 0

        tk.Label(
            stats_window,
            text=f"{category}: {correct}/{total} ({percent}%)",
            font=("Arial", 12)
        ).pack(anchor="w", padx=30)

root = tk.Tk()
root.title("Top 200 Drug Study System")
root.geometry("1000x900")

top_frame = tk.Frame(root)
top_frame.pack(side="top", fill="x")

bottom_frame = tk.Frame(root)
bottom_frame.pack(side="bottom", fill="both", expand=True)

title = tk.Label(top_frame, text="Top 200 Drug Study System", font=("Arial", 20))
title.pack(pady=10)

dataset_label = tk.Label(
    top_frame,
    text=DATASET_VERSION,
    font=("Arial", 10),
    fg="gray"
)
dataset_label.pack()


tk.Button(
    top_frame,
    text="Support Development",
    command=open_support,
    fg="blue",
    relief="flat"
).pack(pady=3)


score_label = tk.Label(top_frame, text="Score: 0/0", font=("Arial", 14))
score_label.pack()

category_count_label = tk.Label(
    top_frame,
    text=f"Selected Categories: {len(selected_categories)}",
    font=("Arial", 12)
)
category_count_label.pack()

question_label = tk.Label(top_frame, text="Choose Mode", font=("Arial", 14))
question_label.pack(pady=20)

feedback_label = tk.Label(top_frame, text="", font=("Arial", 16))
feedback_label.pack(pady=5)

button_frame = tk.Frame(top_frame)
button_frame.pack()

modes = [
    ("Brand → Generic", "brand_generic"),
    ("Generic → Brand", "generic_brand"),
    ("Class", "class"),
    ("Treatment", "treatment"),
    ("Category", "category"),
    ("Schedule", "schedule"),
]

for i, (label, value) in enumerate(modes):
    tk.Button(button_frame, text=label,
              command=lambda v=value: set_mode(v)).grid(row=0, column=i, padx=5)

adaptive_mode_var = tk.BooleanVar(value=False)
tk.Checkbutton(top_frame, text="Adaptive Mode",
               variable=adaptive_mode_var).pack(pady=5)

tk.Button(
    top_frame,
    text="Select Categories",
    command=select_categories,
    bg="lightgreen"
).pack(pady=5)

limit_frame = tk.Frame(top_frame)
limit_frame.pack(pady=5)

tk.Label(limit_frame, text="Questions per Session:").pack(side="left")

question_limit_var = tk.StringVar(value="All")

question_options = ["All", "10", "25", "50", "100"]

limit_menu = tk.OptionMenu(limit_frame, question_limit_var, *question_options)
limit_menu.pack(side="left")


end_session_button = tk.Button(
    top_frame,
    text="End Session",
    bg="orange",
    font=("Arial", 12),
    state="disabled",
    command=show_summary_screen
)

tk.Button(
    top_frame,
    text="View Lifetime Stats",
    command=show_stats,
    bg="lightblue"
).pack(pady=5)


tk.Button(
    top_frame,
    text="Reset Lifetime Stats",
    command=reset_lifetime_stats,
    fg="red",
    font=("Arial", 12, "bold")
).pack(pady=5)




end_session_button.pack(pady=5)


canvas = tk.Canvas(bottom_frame)
scrollbar = tk.Scrollbar(bottom_frame, orient="vertical", command=canvas.yview)

scrollable_frame = tk.Frame(canvas)

scrollable_frame.bind(
    "<Configure>",
    lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
)

canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
canvas.configure(yscrollcommand=scrollbar.set)

canvas.pack(side="left", fill="both", expand=True)
scrollbar.pack(side="right", fill="y")

answer_frame = scrollable_frame

buttons = []

root.mainloop()