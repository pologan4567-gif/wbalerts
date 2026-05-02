#!/usr/bin/env python3
"""
WB Weekly Puller v8 — автоматическая выгрузка отчётов реализации.

Использование:
  python3 wb_weekly_puller.py              → прошлая неделя
  python3 wb_weekly_puller.py --compare    → прошлая неделя + сравнение
  python3 wb_weekly_puller.py --month      → текущий месяц
  python3 wb_weekly_puller.py --from 2026-04-01 --to 2026-04-20

Переменные окружения (задать в .env или экспортировать):
  WB_API_TOKEN   — токен статистики WB
  WB_ADV_TOKEN   — токен рекламного API (опционально)
  TG_BOT_TOKEN   — токен Telegram-бота (опционально)
  TG_CHAT_ID     — ваш Telegram chat_id (опционально)

Требования: pip install requests pandas openpyxl python-dotenv
"""
import time
import requests
import pandas as pd
import os
import json
import sys
from datetime import datetime, timedelta

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# ─── НАСТРОЙКИ ──────────────────────────────────────────────────────────────
API_TOKEN = os.environ.get("WB_API_TOKEN", "")
ADV_TOKEN = os.environ.get("WB_ADV_TOKEN", "")

if not API_TOKEN:
    print(" ✗ WB_API_TOKEN не задан.")
    print("   Создай файл .env и добавь строку: WB_API_TOKEN=твой_токен")
    sys.exit(1)

OUTPUT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEEKS_BACK = 1

# ─── СЕБЕСТОИМОСТЬ ПО АРТИКУЛАМ ─────────────────────────────────────────────
COST_PER_UNIT = {
    "т1":   420,
    "131с": 0,
    # "артикул3": 500,
}
# ────────────────────────────────────────────────────────────────────────────

# ─── ЦВЕТА ──────────────────────────────────────────────────────────────────
class C:
    RESET   = "\033[0m"
    BOLD    = "\033[1m"
    DIM     = "\033[2m"
    WHITE   = "\033[97m"
    GRAY    = "\033[90m"
    GREEN   = "\033[92m"
    YELLOW  = "\033[93m"
    CYAN    = "\033[96m"
    RED     = "\033[91m"
    MAGENTA = "\033[95m"
    BG_DARK = "\033[48;5;235m"

W = 58  # ширина блоков

def line(char="─", color=C.GRAY):
    print(f"{color}{char * W}{C.RESET}")

def header(title, subtitle=""):
    print()
    line("─")
    print(f"{C.BOLD}{C.WHITE} {title}{C.RESET}")
    if subtitle:
        print(f"{C.GRAY} {subtitle}{C.RESET}")
    line("─")

def row(label, value, color=C.WHITE, label_w=22):
    print(f" {C.GRAY}{label:<{label_w}}{C.RESET}{color}{value}{C.RESET}")

def ok(msg):   print(f" {C.GREEN}✓{C.RESET} {msg}")
def info(msg): print(f" {C.CYAN}·{C.RESET} {msg}")
def warn(msg): print(f" {C.YELLOW}!{C.RESET} {C.YELLOW}{msg}{C.RESET}")
def err(msg):  print(f" {C.RED}✗{C.RESET} {C.RED}{msg}{C.RESET}")

def fmt(val):
    return f"{val:,.2f} ₽".replace(",", " ")

# ────────────────────────────────────────────────────────────────────────────

def get_week_range(weeks_back: int = 1):
    today  = datetime.now()
    monday = today - timedelta(days=today.weekday())
    start  = monday - timedelta(weeks=weeks_back)
    end    = start + timedelta(days=6)
    return start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")

def get_month_range():
    today = datetime.now()
    start = today.replace(day=1)
    return start.strftime("%Y-%m-%d"), today.strftime("%Y-%m-%d")

def parse_args():
    args    = sys.argv[1:]
    compare = "--compare" in args

    if "--month" in args:
        d_from, d_to = get_month_range()
        mode = "month"
    elif "--from" in args and "--to" in args:
        d_from = args[args.index("--from") + 1]
        d_to   = args[args.index("--to")   + 1]
        try:
            datetime.strptime(d_from, "%Y-%m-%d")
            datetime.strptime(d_to,   "%Y-%m-%d")
        except ValueError:
            err("Неверный формат даты. Используй ГГГГ-ММ-ДД")
            err("Пример: --from 2026-04-01 --to 2026-04-20")
            sys.exit(1)
        mode = "custom"
    else:
        d_from, d_to = get_week_range(WEEKS_BACK)
        mode = "week"
    return d_from, d_to, mode, compare

def fetch_report(date_from: str, date_to: str, token: str) -> list:
    url     = "https://statistics-api.wildberries.ru/api/v5/supplier/reportDetailByPeriod"
    headers = {"Authorization": token}
    params  = {"dateFrom": date_from, "dateTo": date_to, "limit": 100000, "rrdid": 0}
    all_rows, page = [], 1

    while True:
        info(f"Запрос страницы {page}...")
        resp = requests.get(url, headers=headers, params=params, timeout=60)

        if resp.status_code == 401:
            raise ValueError("Неверный токен. Проверь WB_API_TOKEN.")
        if resp.status_code == 429:
            raise ConnectionError("Превышен лимит запросов. Подожди ~1 минуту.")
        if resp.status_code == 400:
            warn(f"Ошибка 400: {resp.text}")
            break
        resp.raise_for_status()

        data = resp.json()
        if not data:
            break

        all_rows.extend(data)
        ok(f"Получено строк: {len(all_rows)}")

        if len(data) < 100000:
            break

        params["rrdid"] = data[-1].get("rrd_id", 0)
        page += 1

    return all_rows

def fetch_adv_expenses(date_from: str, date_to: str, token: str):
    if not token:
        return None

    headers = {"Authorization": token}
    url     = "https://advert-api.wildberries.ru/adv/v1/upd"
    params  = {"from": date_from, "to": date_to}

    try:
        resp = requests.get(url, headers=headers, params=params, timeout=60)

        if resp.status_code == 401:
            warn("Рекламный API: неверный WB_ADV_TOKEN")
            return None
        if resp.status_code == 429:
            warn("Рекламный API: слишком много запросов")
            return None
        if resp.status_code != 200:
            warn(f"Рекламный API /upd: ошибка {resp.status_code}")
            return None

        data        = resp.json()
        total_spend = 0.0
        for item in data or []:
            total_spend += float(item.get("updSum", 0) or 0)
        return round(total_spend, 2)

    except Exception as e:
        warn(f"Рекламный API недоступен: {e}")
        return None

def load_cached_report(date_from: str, date_to: str, output_dir: str):
    prefix   = f"{date_from}_{date_to}"
    csv_path = os.path.join(output_dir, f"wb_raw_{prefix}.csv")
    if os.path.exists(csv_path):
        df = pd.read_csv(csv_path, encoding="utf-8-sig")
        return df
    return None

def calculate_summary(df: pd.DataFrame, date_from: str, date_to: str):
    if df is None or df.empty:
        return None

    goods    = df["subject_name"].dropna().unique().tolist()
    articles = df["sa_name"].dropna().unique().tolist()
    sales_df = df[df["supplier_oper_name"] == "Продажа"]

    orders_by_article = (
        sales_df.groupby("sa_name")["quantity"].sum().astype(int).to_dict()
    )

    expense_cols = ["delivery_rub", "storage_fee", "rebill_logistic_cost", "acceptance", "penalty"]
    tax_by_article  = {}
    cost_by_article = {}
    net_by_article  = {}

    for art in articles:
        sub        = df[df["sa_name"] == art]
        ppvz       = sub["ppvz_for_pay"].sum()
        expenses   = sum(sub[c].sum() for c in expense_cols if c in sub.columns)
        retail_sum = sub[sub["supplier_oper_name"] == "Продажа"]["retail_price_withdisc_rub"].sum()
        qty        = orders_by_article.get(art, 0)
        tax        = round(float(retail_sum) * 0.06, 2)
        cost       = round(COST_PER_UNIT.get(art, 0) * qty, 2)
        tax_by_article[art]  = tax
        cost_by_article[art] = cost
        net_by_article[art]  = round(float(ppvz - expenses - tax - cost), 2)

    net_total   = sum(net_by_article.values())
    cost_total  = sum(cost_by_article.values())
    gross_total = net_total + cost_total
    tax_total   = sum(tax_by_article.values())

    return {
        "period":             {"from": date_from, "to": date_to},
        "generated_at":       datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "total_rows":         len(df),
        "goods":              goods,
        "articles":           articles,
        "orders_by_article":  orders_by_article,
        "tax_by_article":     tax_by_article,
        "cost_by_article":    cost_by_article,
        "net_by_article":     net_by_article,
        "operations":         df["supplier_oper_name"].value_counts().to_dict(),
        "summary": {
            "qty_sold":      int(sales_df["quantity"].sum()),
            "revenue":       round(float(sales_df["retail_price_withdisc_rub"].sum()), 2),
            "ppvz_for_pay":  round(float(df["ppvz_for_pay"].sum()), 2),
            "delivery_rub":  round(float(df["delivery_rub"].sum()), 2),
            "storage_fee":   round(float(df["storage_fee"].sum()), 2),
            "rebill":        round(float(df["rebill_logistic_cost"].sum()), 2),
            "penalty":       round(float(df["penalty"].sum()), 2),
        },
        "net_total":   net_total,
        "gross_total": gross_total,
        "tax_total":   tax_total,
    }

def save_report(rows: list, date_from: str, date_to: str, output_dir: str):
    os.makedirs(output_dir, exist_ok=True)
    df = pd.DataFrame(rows)

    if df.empty:
        warn("Данных нет — файлы не сохранены.")
        return None

    for col in ["date_from", "date_to", "create_dt", "order_dt", "sale_dt", "rr_dt"]:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors="coerce")

    num_cols = [
        "quantity", "retail_price", "retail_amount", "retail_price_withdisc_rub",
        "ppvz_for_pay", "delivery_rub", "storage_fee", "rebill_logistic_cost",
        "acceptance", "penalty", "deduction", "additional_payment",
        "cashback_discount", "ppvz_vw", "ppvz_vw_nds", "acquiring_fee",
    ]
    for col in num_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

    prefix    = f"{date_from}_{date_to}"
    csv_path  = os.path.join(output_dir, f"wb_raw_{prefix}.csv")
    xlsx_path = os.path.join(output_dir, f"wb_raw_{prefix}.xlsx")
    meta_path = os.path.join(output_dir, f"wb_meta_{prefix}.json")

    df.to_csv(csv_path, index=False, encoding="utf-8-sig")
    ok(f"CSV → {csv_path}")

    df_excel = df.copy()
    for col in df_excel.select_dtypes(include=["datetimetz"]).columns:
        df_excel[col] = df_excel[col].dt.tz_localize(None)
    df_excel.to_excel(xlsx_path, index=False, engine="openpyxl")
    ok(f"Excel → {xlsx_path}")

    goods    = df["subject_name"].dropna().unique().tolist()
    articles = df["sa_name"].dropna().unique().tolist()
    sales_df = df[df["supplier_oper_name"] == "Продажа"]

    orders_by_article = (
        sales_df.groupby("sa_name")["quantity"].sum().astype(int).to_dict()
    )

    expense_cols = ["delivery_rub", "storage_fee", "rebill_logistic_cost", "acceptance", "penalty"]
    tax_by_article  = {}
    cost_by_article = {}
    net_by_article  = {}

    for art in articles:
        sub        = df[df["sa_name"] == art]
        ppvz       = sub["ppvz_for_pay"].sum()
        expenses   = sum(sub[c].sum() for c in expense_cols if c in sub.columns)
        retail_sum = sub[sub["supplier_oper_name"] == "Продажа"]["retail_price_withdisc_rub"].sum()
        qty        = orders_by_article.get(art, 0)
        tax        = round(float(retail_sum) * 0.06, 2)
        cost       = round(COST_PER_UNIT.get(art, 0) * qty, 2)
        tax_by_article[art]  = tax
        cost_by_article[art] = cost
        net_by_article[art]  = round(float(ppvz - expenses - tax - cost), 2)

    meta = {
        "period":             {"from": date_from, "to": date_to},
        "generated_at":       datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "total_rows":         len(df),
        "goods":              goods,
        "articles":           articles,
        "orders_by_article":  orders_by_article,
        "tax_by_article":     tax_by_article,
        "cost_by_article":    cost_by_article,
        "net_by_article":     net_by_article,
        "operations":         df["supplier_oper_name"].value_counts().to_dict(),
        "summary": {
            "qty_sold":     int(sales_df["quantity"].sum()),
            "revenue":      round(float(sales_df["retail_price_withdisc_rub"].sum()), 2),
            "ppvz_for_pay": round(float(df["ppvz_for_pay"].sum()), 2),
            "delivery_rub": round(float(df["delivery_rub"].sum()), 2),
            "storage_fee":  round(float(df["storage_fee"].sum()), 2),
            "rebill":       round(float(df["rebill_logistic_cost"].sum()), 2),
            "penalty":      round(float(df["penalty"].sum()), 2),
        },
    }

    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
    ok(f"Мета → {meta_path}")

    return df, meta

def print_summary(meta: dict):
    p          = meta["period"]
    s          = meta["summary"]
    net_total  = sum(meta["net_by_article"].values())
    cost_total = sum(meta["cost_by_article"].values())
    gross_total = net_total + cost_total
    tax_total  = sum(meta["tax_by_article"].values())
    adv        = meta.get("adv_spend")

    header(
        f"Отчёт {p['from']} → {p['to']}",
        f"{', '.join(meta['goods'])} · артикулы: {', '.join(meta['articles'])}"
    )

    print()
    row("Продано штук",      f"{C.BOLD}{s['qty_sold']} шт{C.RESET}")
    row("Выручка (розница)", fmt(s["revenue"]),      C.WHITE)
    row("К выплате WB",      fmt(s["ppvz_for_pay"]), C.WHITE)
    print()
    row(" Логистика",        fmt(s["delivery_rub"]), C.GRAY)
    row(" Хранение",         fmt(s["storage_fee"]),  C.GRAY)
    row(" Повт. логистика",  fmt(s["rebill"]),        C.GRAY)
    row(" Налог УСН 6%",     fmt(tax_total),          C.GRAY)
    row(" Себестоимость",    fmt(cost_total),          C.GRAY)
    if adv is not None:
        row(" Реклама WB",   fmt(adv),                C.GRAY)
    elif ADV_TOKEN:
        row(" Реклама WB",   "нет данных",            C.GRAY)
    else:
        row(" Реклама WB",   "укажи WB_ADV_TOKEN",   C.GRAY)

    print()
    line()
    print(f" {C.GRAY}{'Артикул':<14} {'Шт':>5} {'Прибыль':>12} {'На руки':>12}{C.RESET}")
    line()

    all_arts = sorted(set(
        list(meta["orders_by_article"].keys()) + list(meta["net_by_article"].keys())
    ))

    for art in all_arts:
        qty   = meta["orders_by_article"].get(art, 0)
        cost  = meta["cost_by_article"].get(art, 0.0)
        net   = meta["net_by_article"].get(art, 0.0)
        gross = net + cost
        if qty == 0:
            continue
        net_color = C.GREEN if net >= 0 else C.RED
        print(
            f" {C.BOLD}{C.WHITE}{art:<14}{C.RESET}"
            f" {C.CYAN}{qty:>4} шт{C.RESET}"
            f" {C.WHITE}{gross:>10,.2f} ₽{C.RESET}"
            f" {net_color}{net:>10,.2f} ₽{C.RESET}"
        )

    line()
    adv_it        = adv or 0.0
    net_after_adv = round(net_total - adv_it, 2)
    print(
        f" {C.BOLD}{C.WHITE}{'ИТОГО':<14}{C.RESET}"
        f" {C.CYAN}{s['qty_sold']:>4} шт{C.RESET}"
        f" {C.BOLD}{C.WHITE}{gross_total:>10,.2f} ₽{C.RESET}"
        f" {C.BOLD}{C.GREEN}{net_total:>10,.2f} ₽{C.RESET}"
    )
    if adv is not None:
        print(f"\n {C.GRAY}{'за вычетом рекламы':<30}{C.RESET}{C.BOLD}{C.MAGENTA}{net_after_adv:>10,.2f} ₽{C.RESET}")

    print()
    line()
    print(f" {C.GRAY}Операции{C.RESET}")
    line()
    for op, cnt in meta["operations"].items():
        if op:
            print(f" {C.GRAY}{cnt:>5}×{C.RESET} {op}")
    line()
    print()

def print_comparison(current_meta: dict, prev_meta: dict):
    if not prev_meta:
        return None

    curr_s = current_meta["summary"]
    prev_s = prev_meta["summary"]
    curr_net = current_meta["net_total"]
    prev_net = prev_meta["net_total"]
    curr_adv = current_meta.get("adv_spend") or 0
    prev_adv = prev_meta.get("adv_spend")   or 0

    def calc_delta(curr, prev):
        if prev == 0:
            return None if curr == 0 else 100.0
        return round(((curr - prev) / abs(prev)) * 100, 1)

    def delta_color(d):
        if d is None: return C.GRAY
        return C.GREEN if d > 0 else C.RED

    def delta_str(d):
        if d is None: return ""
        sign = "+" if d > 0 else ""
        return f" ({sign}{d}%)"

    qty_delta = calc_delta(curr_s["qty_sold"], prev_s["qty_sold"])
    rev_delta = calc_delta(curr_s["revenue"],  prev_s["revenue"])
    net_delta = calc_delta(curr_net,           prev_net)
    adv_delta = calc_delta(curr_adv, prev_adv) if prev_adv or curr_adv else None

    p_curr = current_meta["period"]
    p_prev = prev_meta["period"]

    print()
    header(
        "Прошлая неделя vs Позапрошлая",
        f"{p_curr['from']} → {p_curr['to']}   {p_prev['from']} → {p_prev['to']}"
    )

    print()
    print(f" {C.GRAY}Продано штук:{C.RESET}")
    print(f" {C.BOLD}{C.CYAN}{curr_s['qty_sold']} шт{C.RESET}{delta_str(qty_delta)} "
          f"{delta_color(qty_delta)}{'▲' if qty_delta and qty_delta > 0 else '▼' if qty_delta and qty_delta < 0 else ''}{C.RESET}")
    print(f" {C.GRAY}{prev_s['qty_sold']} шт{C.RESET}")
    print()

    print(f" {C.GRAY}Выручка:{C.RESET}")
    print(f" {C.BOLD}{fmt(curr_s['revenue'])}{C.RESET}{delta_str(rev_delta)} "
          f"{delta_color(rev_delta)}{'▲' if rev_delta and rev_delta > 0 else '▼' if rev_delta and rev_delta < 0 else ''}{C.RESET}")
    print(f" {C.GRAY}{fmt(prev_s['revenue'])}{C.RESET}")
    print()

    print(f" {C.GRAY}Чистая прибыль:{C.RESET}")
    print(f" {C.BOLD}{C.GREEN}{fmt(curr_net)}{C.RESET}{delta_str(net_delta)} "
          f"{delta_color(net_delta)}{'▲' if net_delta and net_delta > 0 else '▼' if net_delta and net_delta < 0 else ''}{C.RESET}")
    print(f" {C.GRAY}{fmt(prev_net)}{C.RESET}")
    print()

    if ADV_TOKEN:
        print(f" {C.GRAY}Реклама WB:{C.RESET}")
        print(f" {C.BOLD}{C.MAGENTA}{fmt(curr_adv)}{C.RESET}{delta_str(adv_delta)} "
              f"{delta_color(adv_delta) if adv_delta else C.GRAY}"
              f"{'▲' if adv_delta and adv_delta > 0 else '▼' if adv_delta and adv_delta < 0 else ''}{C.RESET}")
        print(f" {C.GRAY}{fmt(prev_adv)}{C.RESET}")

    line()
    print()

def get_or_load_report(date_from: str, date_to: str, token: str, mode: str):
    df = load_cached_report(date_from, date_to, OUTPUT_DIR)
    if df is not None:
        info(f"Загружено из кэша: {date_from} → {date_to}")
        return calculate_summary(df, date_from, date_to)

    info(f"Запрашиваю данные из WB API ({mode})...")
    rows = fetch_report(date_from, date_to, token)

    if not rows:
        return None

    info(f"Сохраняю {len(rows)} строк...")
    result = save_report(rows, date_from, date_to, OUTPUT_DIR)

    if result:
        df, meta = result
        if ADV_TOKEN:
            meta["adv_spend"] = fetch_adv_expenses(date_from, date_to, ADV_TOKEN)
        return meta
    return None

def main():
    date_from, date_to, mode, compare = parse_args()
    mode_labels = {"week": "неделя", "month": "месяц", "custom": "свой период"}

    print()
    line("═")
    print(f" {C.BOLD}{C.WHITE}WB Weekly Puller {C.RESET}{C.GRAY}v8 · {mode_labels[mode]}{C.RESET}")
    print(f" {C.GRAY}{date_from} → {date_to}{C.RESET}")
    line("═")
    print()
    print(f" {C.DIM}python3 wb_weekly_puller.py{C.RESET}")
    print(f" {C.DIM}python3 wb_weekly_puller.py --month{C.RESET}")
    print(f" {C.DIM}python3 wb_weekly_puller.py --from ГГГГ-ММ-ДД --to ГГГГ-ММ-ДД{C.RESET}")
    print(f" {C.DIM}python3 wb_weekly_puller.py --compare{C.RESET}")
    print()

    current_meta = get_or_load_report(date_from, date_to, API_TOKEN, mode_labels[mode])

    if not current_meta:
        warn("Нет данных за указанный период.")
        return

    if ADV_TOKEN:
        current_meta["adv_spend"] = fetch_adv_expenses(date_from, date_to, ADV_TOKEN)

    prev_meta = None
    if compare and mode == "week":
        prev_from, prev_to = get_week_range(WEEKS_BACK + 1)
        info("Загружаю данные за позапрошлую неделю...")
        prev_meta = get_or_load_report(prev_from, prev_to, API_TOKEN, "неделя")
        if prev_meta and ADV_TOKEN:
            prev_meta["adv_spend"] = fetch_adv_expenses(prev_from, prev_to, ADV_TOKEN)

    print_summary(current_meta)
    if prev_meta:
        print_comparison(current_meta, prev_meta)

    # ── Telegram-уведомление ─────────────────────────────────────────────────
    try:
        from notifier import notify
        notify(current_meta, prev_meta, mode)
    except Exception as e:
        warn(f"Telegram: {e}")
    # ─────────────────────────────────────────────────────────────────────────

    print(f" {C.GREEN}{C.BOLD}Готово!{C.RESET} {C.GRAY}Файлы в папке: {OUTPUT_DIR}/{C.RESET}")
    print()

if __name__ == "__main__":
    main()
