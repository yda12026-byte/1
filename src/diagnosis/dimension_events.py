"""Important-events dimension from the official announcement list (decision 0022).

Facts only: counts per category, statutory-deadline checks for periodic reports,
earnings forecasts checked against the later reported figure, and verbatim
program excerpts with page numbers. Events are never linked to price moves.
"""

from __future__ import annotations

import re
from datetime import date
from decimal import Decimal

from .dimensions import BASE_CANNOT_SAY, D, Run, _statement_evidence, max_drawdown, q
from .events import CATEGORIES
from .models import CannotSay, DiagnosisRun, Evidence
from .product_snapshot import SUBJECT

EVENT_CANNOT_SAY = BASE_CANNOT_SAY + [
    CannotSay("NO_EVENT_PRICE_LINK", "不能把公告事件说成股价涨跌的原因或利好利空", "事件与股价只做时间并列，没有做归因分析"),
]
LIST_SOURCE = "cninfo_announcements.json"
INCIDENT = re.compile(r"火情|事故|停产|停工")
FIELD = {"project": "f058", "dividend": "f059", "buyback": "f059"}
NUMERALS = "零一二三四五六七八九十"
SPOT = {"consistent": "人工抽查一致", "inconsistent": "人工抽查不一致", "pending": "待人工抽查", "not_sampled": "未抽中"}


def _source(events: dict, item: dict, **extra) -> dict:
    return {"provider": "巨潮资讯 · 公司公告", "endpoint": item["url"], "url": item["url"], **extra}


def _excerpt(run: Run, item: dict) -> Evidence:
    events = run.snapshot["events"]
    check = item["spot_check"]["status"]
    status, reason = ("conflict", "人工抽查发现摘录与原文不一致") if check == "inconsistent" else ("valid", None)
    return run.source(f"announcement:{item['id']}", "announcement_excerpt", FIELD.get(item["category"], "f056"),
                      f"{item['date']} {item['title']}", item["text"], "文本", time={"date": item["date"]},
                      scope={"basis": f"公告原文第 {item['page']} 页，程序摘录"},
                      source=_source(events, item, field=events["categories"][item["category"]], page=item["page"],
                                     query_ref=f"第 {item['page']} 页 · 程序摘录 · {SPOT.get(check, check)}"),
                      status=status, reason=reason)


def _excerpts(run: Run, categories: tuple[str, ...]) -> list[Evidence]:
    return [_excerpt(run, item) for item in run.snapshot["events"]["excerpts"] if item["category"] in categories]


def events_run(snapshot: dict, question: str, route: dict, run_id: str) -> DiagnosisRun:
    run = Run(snapshot, "events", run_id)
    events = snapshot["events"]
    listed = events["announcements"]
    window = {"start": listed[0]["date"], "end": listed[-1]["date"]}
    total = run.source("announcement_list", "announcement_list", "f055", "巨潮资讯公告清单（观察区间）", len(listed), "份",
                       time=window, scope={"basis": "深交所指定披露网站的全部公告及附件"},
                       source={"provider": events["source"]["provider"], "endpoint": events["source"]["endpoint"],
                               "field": "announcementTitle / announcementTime / adjunctUrl",
                               "query_ref": f"{LIST_SOURCE}；{events['source']['query']}"})
    # Fixed order from the rules module: canonical snapshot JSON sorts the stored labels by key.
    ordered = [(key, events["categories"][key]) for key in CATEGORIES]
    counts = {key: run.computed(f"announcement_count:{key}", "announcement_count", "f055", f"{label}公告数",
                                sum(item["category"] == key for item in listed), "份", formula_id="title_rule_count",
                                formula=f"按标题规则归入“{label}”的公告数；制度、法律意见书、可行性报告等附件不计入事项类别",
                                inputs=[total], time=window)
              for key, label in ordered}
    table = {"columns": ["公告数"], "rows": [{"label": label, "cells": [counts[key].id]} for key, label in ordered]}
    kinds = NUMERALS[len([key for key in CATEGORIES if key != "other"])]
    anchor = f"观察区间内的官方公告已按{kinds}类重要事项归类"
    run.conclude("event_overview", "f055", "fact", "neutral", anchor,
                 f"{anchor}，各类数量见表；其余为治理制度、股东会决议、H股例行报表等常规披露。",
                 supports=[total] + [counts[key] for key in CATEGORIES if key != "other"],
                 context=[counts["other"]], table=table, cannot_say=EVENT_CANNOT_SAY,
                 limitations=["分类按标题关键词规则进行，未逐份判断重要性", "清单取自巨潮资讯，公告时间为披露时间"],
                 highlights=[total, counts["periodic"], counts["forecast"], counts["project"]])

    periodic = [item for item in listed if item.get("periodic")]
    rows, gaps = [], []
    for item in periodic:
        disclosed = run.source(f"disclosed:{item['id']}", "disclosure_date", "f057", f"{item['title']} 实际披露日",
                               item["date"], None, time={"date": item["date"]}, scope={"basis": "巨潮资讯公告时间"},
                               source=_source(events, item, field="announcementTime",
                                              query_ref=f"{LIST_SOURCE} · 公告编号 {item['id']}"))
        deadline = date.fromisoformat(item["periodic"]["deadline"])
        gap = run.computed(f"deadline_margin:{item['id']}", "deadline_margin", "f057", f"{item['title']} 早于法定截止日",
                           (deadline - date.fromisoformat(item["date"])).days, "天", formula_id="statutory_deadline_margin",
                           formula=f"法定截止日（{item['periodic']['kind']}：{deadline.isoformat()}）− 实际披露日；负数表示逾期",
                           inputs=[disclosed], time={"date": item["date"]})
        gaps.append(gap)
        rows.append({"label": item["title"], "cells": [disclosed.id, gap.id]})
    if gaps:
        late = [item for item in gaps if Decimal(item.value) < 0]
        spec = ("fact", "negative", "观察区间内有定期报告晚于法定期限披露", "观察区间内有定期报告晚于法定期限披露，见表。") if late else \
            ("fact", "neutral", "观察区间内定期报告均在法定期限内披露", "观察区间内定期报告均在法定期限内披露；各报告实际披露日与截止日见表。")
        run.conclude("periodic_disclosure", "f057", *spec, supports=gaps,
                     table={"columns": ["实际披露日", "早于截止日"], "rows": rows}, cannot_say=EVENT_CANNOT_SAY,
                     limitations=["法定期限：年报与一季报为四月三十日，半年报为八月三十一日，三季报为十月三十一日",
                                  "实际披露日以巨潮资讯公告时间为准；扶摇 report_date_ms 不作披露日（决策 0013）"],
                     highlights=gaps)

    checks, forecast_rows = [], []
    for item in events["forecasts"]:
        unit_note = {"unit_conversion": "万元 ÷ 1e4，保留四位小数"}
        spot = SPOT.get(item["spot_check"]["status"], item["spot_check"]["status"])
        bounds = [run.source(f"forecast_{side}:{item['id']}", f"forecast_{side}", "f055", f"{item['title']} 归母净利润预告{name}",
                             q(D(value) / Decimal(10000), "0.0001"), "亿元", time={"period_end": item["period_end"]},
                             scope={"basis": f"业绩预告（{item['type']}）", **unit_note},
                             source=_source(events, item, field=item["metric"], page=item["page"],
                                            query_ref=f"第 {item['page']} 页 · 程序解析 · {spot} · 原文：{item['quote']}"))
                  for side, name, value in (("low", "下限", item["low"]), ("high", "上限", item["high"]))]
        actual = _statement_evidence(run, SUBJECT, item["period_end"], "parent_holder_net_profit", "parent_net_profit",
                                     "f018", "归母净利润")
        low, high = D(bounds[0].value), D(bounds[1].value)
        position = q((D(actual.value) - low) / (high - low) * 100) if actual.value is not None and high > low else None
        check = run.computed(f"forecast_position:{item['id']}", "forecast_position", "f055", f"{item['title']}：实际值在预告区间中的位置",
                             position, "%", formula_id="forecast_range_position",
                             formula="(定期报告归母净利润 − 预告下限) ÷ (预告上限 − 预告下限) × 100；0 至 100 表示落在区间内",
                             inputs=[actual, bounds[0], bounds[1]], time={"period_end": item["period_end"]})
        checks.append(check)
        forecast_rows.append({"label": f"{item['title']}（{item['type']}）",
                              "cells": [bounds[0].id, bounds[1].id, actual.id, check.id]})
    if checks:
        usable = [item for item in checks if item.value is not None]
        inside = usable and len(usable) == len(checks) and all(Decimal(0) <= D(item.value) <= Decimal(100) for item in usable)
        types = "、".join(dict.fromkeys(item["type"] for item in events["forecasts"]))
        spec = ("fact", "neutral", "已披露的业绩预告与随后定期报告的归母净利润一致",
                f"已披露的业绩预告（{types}）与随后定期报告的归母净利润一致，实际值均落在预告区间内。") if inside else \
            ("fact", "negative", "有业绩预告与随后定期报告的归母净利润不一致",
             "有业绩预告与随后定期报告的归母净利润不一致，实际值落在预告区间之外，见表。")
        run.conclude("forecast_accuracy", "f055", *spec, supports=checks, cannot_say=EVENT_CANNOT_SAY,
                     table={"columns": ["预告下限", "预告上限", "报告实际值", "区间位置"], "rows": forecast_rows},
                     limitations=["实际值取扶摇累计利润表（合并口径），预告区间由程序从公告原文解析",
                                  "区间位置只说明预告与结果是否一致，不代表后续业绩"],
                     highlights=checks)

    project = _excerpts(run, ("project",))
    if project:
        incident = any(INCIDENT.search(item.label) for item in project)
        anchor = "观察区间内披露了项目或扩产进展，另有一起工厂局部火情" if incident else "观察区间内披露了项目或扩产进展"
        run.conclude("project_progress", "f058", "fact", "neutral", anchor,
                     f"{anchor}；各公告的原文摘录与页码见证据。", supports=project, cannot_say=EVENT_CANNOT_SAY,
                     limitations=["摘录为公告原文的一句，完整情况以公告全文为准", "项目进度不代表产能已达产或利润已实现"],
                     highlights=project[:3])

    legal = _excerpts(run, ("litigation", "guarantee"))
    if legal:
        kinds = [label for key, label in (("litigation", "诉讼进展"), ("guarantee", "对外担保"))
                 if any(item["category"] == key for item in events["excerpts"])]
        anchor = f"观察区间内有{'与'.join(kinds)}事项披露"
        run.conclude("legal_guarantee", "f055", "fact", "neutral", anchor, f"{anchor}；原文摘录见证据。", supports=legal,
                     cannot_say=EVENT_CANNOT_SAY, highlights=legal[:3],
                     limitations=["诉讼与担保的财务影响以公司定期报告为准", "摘录为公告原文的一句，完整情况以公告全文为准"])

    capital = _excerpts(run, ("dividend", "buyback"))
    if capital:
        no_cash = any("不派发现金红利" in (item.value or "") for item in capital)
        anchor = "最近一个会计年度的利润分配预案为不派发现金红利，另有股份回购注销" if no_cash else "观察区间内有利润分配或股份回购注销事项"
        run.conclude("capital_return", "f059", "fact", "neutral", anchor, f"{anchor}；原文摘录见证据。", supports=capital,
                     cannot_say=EVENT_CANNOT_SAY, highlights=capital[:3],
                     limitations=["回购注销多为股权激励未达条件股份，规模较小，不等同于市场回购"])

    capital_ops = _excerpts(run, ("capital",))
    if capital_ops:
        titles = " ".join(item.label for item in capital_ops)
        kinds = [word for word, pattern in (("股权融资", r"配售|可转换"), ("对外投资", r"对外投资|共同投资|增资"),
                                            ("参股股权处置", r"处置")) if re.search(pattern, titles)]
        anchor = f"观察区间内有{'、'.join(kinds)}等资本运作事项披露"
        run.conclude("capital_operations", "f055", "fact", "neutral", anchor, f"{anchor}；原文摘录见证据。",
                     supports=capital_ops, cannot_say=EVENT_CANNOT_SAY, highlights=capital_ops[:3],
                     limitations=["“择机处置”为董事会授权，不代表已经完成交易", "摘录为公告原文的一句，完整情况以公告全文为准"])

    hedging = _excerpts(run, ("hedging",))
    if hedging:
        run.conclude("hedging", "f055", "fact", "neutral", "公司开展外汇与商品期货套期保值业务",
                     "公司开展外汇与商品期货套期保值业务；额度与进展公告的原文摘录见证据。", supports=hedging,
                     cannot_say=EVENT_CANNOT_SAY, highlights=hedging[:3],
                     limitations=["套期保值损益随市场变化，摘录只反映公告日的统计"])
    return run.finish(question, route)


def price_chart(snapshot: dict) -> dict:
    """Subject and peers indexed to 100 on the first trading day, max-drawdown span, official event dates.

    Indices use Decimal (close ÷ first close × 100, two decimals); the drawdown span comes from the same
    routine as the market dimension's evidence. Juxtaposition only: no trend lines, no attribution.
    """
    events = snapshot.get("events")
    order = [SUBJECT, *snapshot["peer_group"]]
    rows = {code: snapshot["daily"][code]["rows"] for code in order}
    dates = [row["date"] for row in rows[SUBJECT]]
    series = []
    for code in order:
        closes = [D(row["close"]) for row in rows[code]]
        if [row["date"] for row in rows[code]] != dates:
            raise ValueError(f"daily series not aligned for chart: {code}")
        series.append({"code": code, "label": snapshot["names"][code], "role": "subject" if code == SUBJECT else "peer",
                       "values": [float(q(close / closes[0] * 100)) for close in closes],
                       "closes": [float(close) for close in closes],
                       "evidence_id": f"daily_series:{SUBJECT}" if code == SUBJECT else f"return:{code}:{dates[0]}:{dates[-1]}"})
    worst, (peak_i, trough_i) = max_drawdown([D(row["close"]) for row in rows[SUBJECT]])
    markers = [{"date": item["date"], "category": events["categories"][item["category"]], "title": item["title"],
                "url": item["url"]}
               for item in (events or {}).get("announcements", []) if item["category"] != "other"]
    daily = snapshot["daily"][SUBJECT]
    return {"kind": "indexed_price", "dates": dates, "base_date": dates[0], "series": series,
            "drawdown": {"start": dates[peak_i], "end": dates[trough_i], "pct": float(q(worst * 100)),
                         "evidence_id": f"max_drawdown:{SUBJECT}"},
            "markers": markers, "adjust": "forward",
            "source": f"{daily['source']['provider']} 前复权日线（四家同源）；事件：巨潮资讯公告清单",
            "note": "指数 = 当日前复权收盘价 ÷ 首个交易日收盘价 × 100；事件日期与股价只做时间并列，不表示因果关系；历史走势不预示未来"}
