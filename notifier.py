#!/usr/bin/env python3
"""
WB Notifier — отправка отчёта в Telegram.
Читает токены из переменных окружения или .env файла.
"""
import os
import requests
from datetime import datetime

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

TG_TOKEN  = os.environ.get("TG_BOT_TOKEN", "")
TG_CHAT_ID = os.environ.get("TG_CHAT_ID", "")


def _arrow(delta):
    if delta is None: return ""
    return "📈" if delta > 0 else "📉"

def _delta(delta):
    if delta is None: return ""
    sign = "+" if delta > 0 else ""
    return f" ({sign}{delta}%)"

def _calc_delta(curr, prev):
    if prev == 0:
        return None if curr == 0 else 100.0
    return round(((curr - prev) / abs(prev)) * 100, 1)

def _fmt(val):
    return f"{val:,.2f} ₽".replace(",", " ")

def _drr(adv, revenue):
    if not adv or not revenue: return None
    return round((adv / revenue) * 100, 1)


def build_message(meta: dict, prev_meta: dict = None, mode: str = "week") -> str:
    p   = meta["period"]
    s   = meta["summary"]
    net_total   = meta.get("net_total", sum(meta.get("net_by_article", {}).values()))
    adv         = meta.get("adv_spend")
    adv_val     = adv or 0.0
    net_after_adv = round(net_total - adv_val, 2)
    tax_total   = sum(meta.get("tax_by_article", {}).values())
    cost_total  = sum(meta.get("cost_by_article", {}).values())

    mode_label = {"week": "Неделя", "month": "Месяц", "custom": "Период"}.get(mode, "Отчёт")
    period_str = f"{p['from']} → {p['to']}"

    L = []
    L.append(f"📊 *WB {mode_label}* · `{period_str}`")
    L.append("")
    L.append("*💰 Финансы*")

    if prev_meta:
        ps  = prev_meta["summary"]
        pn  = prev_meta.get("net_total", 0)
        pa  = prev_meta.get("adv_spend") or 0
        qty_d = _calc_delta(s["qty_sold"],   ps["qty_sold"])
        rev_d = _calc_delta(s["revenue"],    ps["revenue"])
        net_d = _calc_delta(net_total,       pn)
        adv_d = _calc_delta(adv_val, pa) if (adv_val or pa) else None
        L.append(f"  Выручка:       `{_fmt(s['revenue'])}`{_delta(rev_d)} {_arrow(rev_d)}")
        L.append(f"  Продано:       `{s['qty_sold']} шт`{_delta(qty_d)} {_arrow(qty_d)}")
        L.append(f"  К выплате WB:  `{_fmt(s['ppvz_for_pay'])}`")
        L.append("")
        L.append("*📉 Расходы*")
        L.append(f"  Логистика:     `{_fmt(s['delivery_rub'])}`")
        L.append(f"  Хранение:      `{_fmt(s['storage_fee'])}`")
        if s.get("rebill"):
            L.append(f"  Повт. лог.:    `{_fmt(s['rebill'])}`")
        L.append(f"  Налог УСН 6%:  `{_fmt(tax_total)}`")
        L.append(f"  Себестоимость: `{_fmt(cost_total)}`")
        if adv is not None:
            L.append(f"  Реклама WB:    `{_fmt(adv_val)}`{_delta(adv_d)} {_arrow(adv_d)}")
            drr = _drr(adv_val, s["revenue"])
            if drr:
                icon = "🔴" if drr > 15 else "🟡" if drr > 8 else "🟢"
                L.append(f"  ДРР:           `{drr}%` {icon}")
        L.append("")
        L.append("*✅ Итог*")
        L.append(f"  Чистая прибыль:  `{_fmt(net_total)}`{_delta(net_d)} {_arrow(net_d)}")
        if adv is not None:
            L.append(f"  После рекламы:   `{_fmt(net_after_adv)}`")
    else:
        L.append(f"  Выручка:       `{_fmt(s['revenue'])}`")
        L.append(f"  Продано:       `{s['qty_sold']} шт`")
        L.append(f"  К выплате WB:  `{_fmt(s['ppvz_for_pay'])}`")
        L.append("")
        L.append("*📉 Расходы*")
        L.append(f"  Логистика:     `{_fmt(s['delivery_rub'])}`")
        L.append(f"  Хранение:      `{_fmt(s['storage_fee'])}`")
        if s.get("rebill"):
            L.append(f"  Повт. лог.:    `{_fmt(s['rebill'])}`")
        L.append(f"  Налог УСН 6%:  `{_fmt(tax_total)}`")
        L.append(f"  Себестоимость: `{_fmt(cost_total)}`")
        if adv is not None:
            L.append(f"  Реклама WB:    `{_fmt(adv_val)}`")
            drr = _drr(adv_val, s["revenue"])
            if drr:
                icon = "🔴" if drr > 15 else "🟡" if drr > 8 else "🟢"
                L.append(f"  ДРР:           `{drr}%` {icon}")
        L.append("")
        L.append("*✅ Итог*")
        L.append(f"  Чистая прибыль:  `{_fmt(net_total)}`")
        if adv is not None:
            L.append(f"  После рекламы:   `{_fmt(net_after_adv)}`")

    # По артикулам
    articles = meta.get("articles", [])
    orders   = meta.get("orders_by_article", {})
    nets     = meta.get("net_by_article", {})
    if articles:
        L.append("")
        L.append("*📦 По артикулам*")
        for art in sorted(articles):
            qty = orders.get(art, 0)
            if qty == 0: continue
            net = nets.get(art, 0)
            icon = "🟢" if net >= 0 else "🔴"
            L.append(f"  {icon} `{art}` — {qty} шт · `{_fmt(net)}`")

    # Алерты
    alerts = []
    if net_total < 0:
        alerts.append("🚨 Чистая прибыль отрицательная!")
    drr_val = _drr(adv_val, s["revenue"])
    if drr_val and drr_val > 20:
        alerts.append(f"🚨 ДРР критический: {drr_val}% (норма < 15%)")
    if s["qty_sold"] == 0:
        alerts.append("⚠️ Продаж за период не обнаружено.")
    if alerts:
        L.append("")
        L.append("*⚠️ Алерты*")
        for a in alerts:
            L.append(f"  {a}")

    L.append("")
    L.append(f"_Сгенерировано: {datetime.now().strftime('%d.%m.%Y %H:%M')}_")
    return "\n".join(L)


def send_message(text: str, token: str = None, chat_id: str = None) -> bool:
    token   = token   or TG_TOKEN
    chat_id = chat_id or TG_CHAT_ID
    if not token:
        print("  [notifier] ⚠️  TG_BOT_TOKEN не задан — пропускаю отправку")
        return False
    if not chat_id:
        print("  [notifier] ⚠️  TG_CHAT_ID не задан — пропускаю отправку")
        return False
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {"chat_id": chat_id, "text": text,
               "parse_mode": "Markdown", "disable_web_page_preview": True}
    try:
        resp = requests.post(url, json=payload, timeout=15)
        if resp.status_code == 200:
            print("  [notifier] ✓ Сообщение отправлено в Telegram")
            return True
        print(f"  [notifier] ✗ Ошибка Telegram API: {resp.status_code} — {resp.text}")
        return False
    except Exception as e:
        print(f"  [notifier] ✗ Ошибка соединения: {e}")
        return False


def notify(meta: dict, prev_meta: dict = None, mode: str = "week") -> bool:
    msg = build_message(meta, prev_meta, mode)
    return send_message(msg)
