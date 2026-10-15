#!/usr/bin/env python3
"""
Currency converter - desktop app.
Standard library only: no pip installs required.

Run:  python currency_app.py
"""

import json
import threading
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
import tkinter as tk
from tkinter import ttk

RATES_URL = "https://open.er-api.com/v6/latest/USD"
STATE_PATH = Path.home() / ".currency_app" / "state.json"

CURRENCIES = [
    "USD", "EUR", "GBP", "JPY", "CHF", "CAD", "AUD", "NZD", "CNY", "HKD",
    "SGD", "INR", "KRW", "SEK", "NOK", "DKK", "PLN", "CZK", "TRY", "ZAR",
    "MXN", "BRL", "ARS", "CLP", "COP", "PEN", "AED", "SAR", "ILS", "EGP",
    "NGN", "THB", "IDR", "PHP", "MYR", "VND", "PKR", "BDT", "RUB",
]

FALLBACK = {
    "USD": 1, "EUR": 0.894425, "GBP": 0.756165, "JPY": 158.305497,
    "CHF": 0.833623, "CAD": 1.422795, "AUD": 1.433021, "NZD": 1.784407,
    "CNY": 6.706494, "HKD": 7.848465, "SGD": 1.283055, "INR": 95.252751,
    "KRW": 1339.811585, "SEK": 9.994434, "NOK": 9.501535, "DKK": 6.677204,
    "PLN": 3.91007, "CZK": 21.778949, "TRY": 49.45021, "ZAR": 16.579734,
    "MXN": 18.464303, "BRL": 5.035924, "ARS": 1514.5655, "CLP": 981.815969,
    "COP": 3182.996886, "PEN": 3.440036, "AED": 3.6725, "SAR": 3.75,
    "ILS": 3.095708, "EGP": 53.095404, "NGN": 1331.826337, "THB": 33.627869,
    "IDR": 17907.815096, "PHP": 62.922028, "MYR": 4.082359,
    "VND": 25890.201508, "PKR": 276.883421, "BDT": 123.47684, "RUB": 83.931439,
}

SYMBOLS = {
    "USD": "$", "EUR": "\u20ac", "GBP": "\u00a3", "JPY": "\u00a5", "CNY": "\u00a5",
    "INR": "\u20b9", "KRW": "\u20a9", "RUB": "\u20bd", "TRY": "\u20ba",
    "NGN": "\u20a6", "PHP": "\u20b1", "THB": "\u0e3f", "VND": "\u20ab",
    "BRL": "R$", "ZAR": "R", "AUD": "A$", "CAD": "C$", "NZD": "NZ$",
    "HKD": "HK$", "SGD": "S$", "MXN": "MX$",
}

BG      = "#111318"
CARD    = "#171a21"
INPUT   = "#1d2129"
BORDER  = "#262b35"
FG      = "#e8eaed"
MUTED   = "#8b93a1"
ACCENT  = "#3b82f6"
ACCENT2 = "#2563eb"
SUCCESS = "#22c55e"
ERROR   = "#ef4444"

FONT      = ("Segoe UI", 11)
FONT_SM   = ("Segoe UI", 9)
FONT_BIG  = ("Segoe UI", 30, "bold")
FONT_BTN  = ("Segoe UI", 10, "bold")


def fmt(value, code):
    """Format a number with the currency's symbol when we know it."""
    decimals = 4 if 0 < abs(value) < 1 else 2
    body = f"{value:,.{decimals}f}"
    sym = SYMBOLS.get(code)
    return f"{sym}{body}" if sym else f"{body} {code}"


def parse_amount(text):
    cleaned = "".join(c for c in text if c.isdigit() or c in ".-")
    try:
        return float(cleaned)
    except ValueError:
        return 0.0


class CurrencyApp:
    def __init__(self, root):
        self.root = root
        self.rates = dict(FALLBACK)
        self.rate_at = None
        self.next_at = None
        self.refresh_job = None
        self.history_job = None
        self.state = {
            "from": "USD", "to": "EUR", "amount": "100",
            "favs": [], "history": [],
        }
        self._load_state()

        root.title("Currency converter")
        root.configure(bg=BG)
        root.geometry("440x720")
        root.minsize(400, 640)

        self._style()
        self._build()
        self._render_favs()
        self._render_history()
        self._convert()
        self._stamp_status()

        self.fetch_rates()
        root.protocol("WM_DELETE_WINDOW", self._on_close)

    # ---------- persistence ----------

    def _load_state(self):
        try:
            data = json.loads(STATE_PATH.read_text())
        except Exception:
            return
        self.state.update({k: v for k, v in data.items() if k in self.state})
        if self.state.get("rates"):
            self.rates = self.state["rates"]
        self.rate_at = self.state.get("rate_at")
        self.next_at = self.state.get("next_at")
        self.state["favs"] = [f for f in self.state.get("favs", [])
                              if f[0] in CURRENCIES and f[1] in CURRENCIES][:8]
        self.state["history"] = self.state.get("history", [])[:5]

    def save_state(self):
        payload = dict(self.state)
        payload.update(rate_at=self.rate_at, next_at=self.next_at, rates=self.rates)
        try:
            STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
            STATE_PATH.write_text(json.dumps(payload))
        except Exception:
            pass

    # ---------- styling ----------

    def _style(self):
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure(
            "TCombobox",
            fieldbackground=INPUT, background=CARD, foreground=FG,
            arrowcolor=FG, bordercolor=BORDER, lightcolor=BORDER,
            darkcolor=BORDER, padding=6, relief="flat",
        )
        style.map(
            "TCombobox",
            fieldbackground=[("readonly", INPUT), ("focus", INPUT)],
            foreground=[("readonly", FG)],
            selectbackground=[("readonly", INPUT)],
            selectforeground=[("readonly", FG)],
            bordercolor=[("focus", ACCENT)],
        )
        self.root.option_add("*TCombobox*Listbox.background", INPUT)
        self.root.option_add("*TCombobox*Listbox.foreground", FG)
        self.root.option_add("*TCombobox*Listbox.selectBackground", ACCENT)
        self.root.option_add("*TCombobox*Listbox.selectForeground", "#ffffff")

    def _label(self, parent, text, font=FONT, fg=FG, bg=BG, **kw):
        return tk.Label(parent, text=text, font=font, fg=fg, bg=bg, **kw)

    def _button(self, parent, text, command, bg=CARD, fg=FG, font=FONT):
        btn = tk.Button(
            parent, text=text, command=command, font=font, bg=bg, fg=fg,
            activebackground=bg, activeforeground=fg, relief="flat",
            borderwidth=0, highlightthickness=0, cursor="hand2", padx=10, pady=6,
        )
        btn.bind("<Enter>", lambda e: btn.configure(bg=self._lighten(bg)))
        btn.bind("<Leave>", lambda e: btn.configure(bg=bg))
        return btn

    @staticmethod
    def _lighten(hex_color):
        table = {CARD: "#1e222b", ACCENT: ACCENT2, INPUT: "#242832", BG: "#171a21"}
        return table.get(hex_color, hex_color)

    # ---------- layout ----------

    def _build(self):
        pad = tk.Frame(self.root, bg=BG)
        pad.pack(fill="both", expand=True, padx=18, pady=16)

        self._label(pad, "Converted amount", font=FONT_SM, fg=MUTED).pack(anchor="w")
        self.result_var = tk.StringVar(value="\u2014")
        self._label(pad, "", font=FONT_BIG, bg=BG).pack(anchor="w")
        self.result_lbl = pad.winfo_children()[-1]
        self.result_lbl.configure(textvariable=self.result_var)

        self.rate_var = tk.StringVar(value="\u2014")
        self._label(pad, "", font=FONT_SM, fg=MUTED).pack(anchor="w", pady=(2, 16))
        pad.winfo_children()[-1].configure(textvariable=self.rate_var)

        self._label(pad, "Amount", font=FONT_SM, fg=MUTED).pack(anchor="w")
        vcmd = (self.root.register(self._validate), "%P")
        self.amount_var = tk.StringVar(value=self.state["amount"])
        self.amount_var.trace_add("write", self._on_amount_change)
        amount_entry = tk.Entry(
            pad, textvariable=self.amount_var, font=FONT, bg=INPUT, fg=FG,
            insertbackground=FG, relief="flat", highlightthickness=1,
            highlightbackground=BORDER, highlightcolor=ACCENT, validate="key",
            validatecommand=vcmd,
        )
        amount_entry.pack(fill="x", ipady=7, pady=(4, 14))

        row = tk.Frame(pad, bg=BG)
        row.pack(fill="x")

        left = tk.Frame(row, bg=BG)
        left.pack(side="left", fill="x", expand=True)
        self._label(left, "From", font=FONT_SM, fg=MUTED).pack(anchor="w")
        self.from_var = tk.StringVar(value=self.state["from"])
        self.from_box = ttk.Combobox(left, textvariable=self.from_var,
                                     values=CURRENCIES, state="readonly",
                                     font=FONT, width=8)
        self.from_box.pack(fill="x", pady=(4, 0))
        self.from_box.bind("<<ComboboxSelected>>", self._on_pair_change)

        swap = self._button(row, "\u21c5", self._swap, bg=CARD, font=("Segoe UI", 13))
        swap.pack(side="left", padx=8, pady=(18, 0), ipadx=4, ipady=3)

        right = tk.Frame(row, bg=BG)
        right.pack(side="left", fill="x", expand=True)
        self._label(right, "To", font=FONT_SM, fg=MUTED).pack(anchor="w")
        self.to_var = tk.StringVar(value=self.state["to"])
        self.to_box = ttk.Combobox(right, textvariable=self.to_var,
                                   values=CURRENCIES, state="readonly",
                                   font=FONT, width=8)
        self.to_box.pack(fill="x", pady=(4, 0))
        self.to_box.bind("<<ComboboxSelected>>", self._on_pair_change)

        quick = tk.Frame(pad, bg=BG)
        quick.pack(fill="x", pady=(14, 0))
        for value in (1, 10, 100, 1000, 10000):
            chip = self._button(quick, f"{value:,}", lambda v=value: self._set_amount(v),
                                bg=INPUT, font=FONT_SM)
            chip.pack(side="left", padx=(0, 6), ipady=2)

        self._button(pad, "Save this pair", self._save_pair,
                     bg=ACCENT, fg="#ffffff", font=FONT_BTN).pack(fill="x", pady=(16, 0), ipady=5)

        self.fav_frame = tk.Frame(pad, bg=BG)
        self.fav_frame.pack(fill="x", pady=(16, 0))

        self.hist_frame = tk.Frame(pad, bg=BG)
        self.hist_frame.pack(fill="x", pady=(16, 0))

        status = tk.Frame(self.root, bg=BG)
        status.pack(fill="x", side="bottom", padx=18, pady=(0, 12))
        self.status_var = tk.StringVar(value="Loading\u2026")
        self._label(status, "", font=FONT_SM, fg=MUTED).pack(side="left")
        status.winfo_children()[-1].configure(textvariable=self.status_var)
        self._button(status, "Refresh", lambda: self.fetch_rates(manual=True),
                     bg=BG, fg=MUTED, font=FONT_SM).pack(side="right")

    @staticmethod
    def _validate(proposed):
        if proposed == "":
            return True
        if proposed.count(".") > 1:
            return False
        return all(c.isdigit() or c in ".-" for c in proposed)

    # ---------- behaviour ----------

    def _set_amount(self, value):
        self.amount_var.set(str(value))
        self._record_history()

    def _on_amount_change(self, *_):
        self._convert()
        self.state["amount"] = self.amount_var.get()
        self.save_state()
        if self.history_job:
            self.root.after_cancel(self.history_job)
        self.history_job = self.root.after(1100, self._record_history)

    def _on_pair_change(self, *_):
        self.state["from"] = self.from_var.get()
        self.state["to"] = self.to_var.get()
        self._convert()
        self.save_state()
        self._record_history()

    def _swap(self):
        f, t = self.from_var.get(), self.to_var.get()
        self.from_var.set(t)
        self.to_var.set(f)
        self._on_pair_change()

    def _rate_of(self, frm, to):
        return self.rates.get(to, 1.0) / self.rates.get(frm, 1.0)

    def _convert(self):
        frm, to = self.from_var.get(), self.to_var.get()
        amount = parse_amount(self.amount_var.get())
        rate = self._rate_of(frm, to)
        self.result_var.set(fmt(amount * rate, to) if amount else fmt(0, to))
        self.rate_var.set(f"1 {frm} = {rate:.4f} {to}")

    def _record_history(self):
        self.history_job = None
        amount = parse_amount(self.amount_var.get())
        if not amount:
            return
        frm, to = self.from_var.get(), self.to_var.get()
        entry = {"f": frm, "t": to, "a": amount, "r": self._rate_of(frm, to)}
        history = self.state["history"]
        if history and history[0]["f"] == frm and history[0]["t"] == to and history[0]["a"] == amount:
            history[0] = entry
        else:
            history.insert(0, entry)
        self.state["history"] = history[:5]
        self.save_state()
        self._render_history()

    def _save_pair(self):
        pair = [self.from_var.get(), self.to_var.get()]
        if pair not in self.state["favs"]:
            self.state["favs"].insert(0, pair)
            self.state["favs"] = self.state["favs"][:8]
            self.save_state()
            self._render_favs()

    def _render_favs(self):
        for child in self.fav_frame.winfo_children():
            child.destroy()
        favs = self.state["favs"]
        if not favs:
            return
        self._label(self.fav_frame, "Saved pairs", font=FONT_SM, fg=MUTED).pack(anchor="w", pady=(0, 6))
        holder = tk.Frame(self.fav_frame, bg=BG)
        holder.pack(fill="x")
        for index, pair in enumerate(favs):
            chip = tk.Frame(holder, bg=INPUT, highlightthickness=1,
                            highlightbackground=BORDER)
            chip.pack(side="left", padx=(0, 6), pady=2)
            name = self._label(chip, f"{pair[0]} \u2192 {pair[1]}", font=FONT_SM, bg=INPUT)
            name.pack(side="left", padx=(8, 4), pady=3)
            name.bind("<Button-1>", lambda e, p=pair: self._load_pair(p))
            close = self._label(chip, "\u00d7", font=FONT_SM, fg=MUTED, bg=INPUT)
            close.pack(side="left", padx=(0, 7))
            close.bind("<Button-1>", lambda e, i=index: self._drop_fav(i))
            close.bind("<Enter>", lambda e, w=close: w.configure(fg=ERROR))
            close.bind("<Leave>", lambda e, w=close: w.configure(fg=MUTED))

    def _load_pair(self, pair):
        self.from_var.set(pair[0])
        self.to_var.set(pair[1])
        self._on_pair_change()

    def _drop_fav(self, index):
        self.state["favs"].pop(index)
        self.save_state()
        self._render_favs()

    def _render_history(self):
        for child in self.hist_frame.winfo_children():
            child.destroy()
        history = self.state["history"]
        if not history:
            return
        head = tk.Frame(self.hist_frame, bg=BG)
        head.pack(fill="x", pady=(0, 6))
        self._label(head, "Recent", font=FONT_SM, fg=MUTED).pack(side="left")
        self._button(head, "clear", self._clear_history, bg=BG, fg=MUTED,
                     font=FONT_SM).pack(side="right")

        for index, item in enumerate(history):
            row = tk.Frame(self.hist_frame, bg=BG)
            row.pack(fill="x")
            text = f"{fmt(item['a'], item['f'])}  \u2192  {fmt(item['a'] * item['r'], item['t'])}"
            lbl = self._label(row, text, font=FONT_SM)
            lbl.pack(side="left", pady=5)
            lbl.bind("<Button-1>", lambda e, h=item: self._restore(h))
            close = self._label(row, "\u00d7", font=FONT_SM, fg=MUTED)
            close.pack(side="right", pady=5)
            close.bind("<Button-1>", lambda e, i=index: self._drop_history(i))
            close.bind("<Enter>", lambda e, w=close: w.configure(fg=ERROR))
            close.bind("<Leave>", lambda e, w=close: w.configure(fg=MUTED))
            tk.Frame(self.hist_frame, bg=BORDER, height=1).pack(fill="x")

    def _restore(self, item):
        self.amount_var.set(str(item["a"]))
        self.from_var.set(item["f"])
        self.to_var.set(item["t"])
        self._on_pair_change()

    def _drop_history(self, index):
        self.state["history"].pop(index)
        self.save_state()
        self._render_history()

    def _clear_history(self):
        self.state["history"] = []
        self.save_state()
        self._render_history()

    # ---------- rates ----------

    def fetch_rates(self, manual=False):
        if manual:
            self.status_var.set("Refreshing\u2026")
        threading.Thread(target=self._fetch_worker, daemon=True).start()

    def _fetch_worker(self):
        try:
            with urllib.request.urlopen(RATES_URL, timeout=12) as response:
                payload = json.loads(response.read().decode())
            if not payload.get("rates", {}).get("EUR"):
                raise ValueError("incomplete payload")
            self.root.after(0, lambda: self._apply_rates(payload))
        except Exception:
            self.root.after(0, lambda: self._apply_rates(None))

    def _apply_rates(self, payload):
        if payload:
            self.rates = payload["rates"]
            self.rate_at = payload.get("time_last_update_unix")
            self.next_at = payload.get("time_next_update_unix")
            self._source = "live"
        else:
            self._source = "cached" if self.rate_at else "offline"
        self._convert()
        self.save_state()
        self._stamp_status()
        self._schedule_refresh()

    def _schedule_refresh(self):
        if self.refresh_job:
            self.root.after_cancel(self.refresh_job)
        now = datetime.now(timezone.utc).timestamp()
        if self.next_at and self.next_at > now:
            wait_ms = int((self.next_at - now + 60) * 1000)
        else:
            wait_ms = 5 * 60 * 1000
        self.refresh_job = self.root.after(min(wait_ms, 5 * 60 * 1000), self.fetch_rates)

    def _stamp_status(self):
        if not self.rate_at:
            self.status_var.set("Offline \u2014 built-in rate table")
            return
        as_of = datetime.fromtimestamp(self.rate_at, timezone.utc)
        text = "Daily rates \u00b7 as of " + as_of.strftime("%d %b %Y %H:%M UTC")
        now = datetime.now(timezone.utc).timestamp()
        if self.next_at and self.next_at > now:
            minutes = int((self.next_at - now) / 60)
            left = f"{minutes // 60}h {minutes % 60}m" if minutes > 90 else f"{minutes}m"
            text += f" \u00b7 next in {left}"
        self.status_var.set(text)

    def _on_close(self):
        self.save_state()
        self.root.destroy()


if __name__ == "__main__":
    root = tk.Tk()
    CurrencyApp(root)
    root.mainloop()