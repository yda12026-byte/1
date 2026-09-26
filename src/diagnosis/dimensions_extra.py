"""Operating quality and risk dimensions, built on the official half-year extracts (decision 0018)."""

from __future__ import annotations

from decimal import Decimal

from .dimensions import (BASE, PERIOD, D, Run, _indicator_evidence, _net_cash, _official, _pct_change,
                         _statement_evidence, q)
from .models import DiagnosisRun
from .product_snapshot import SUBJECT

SEGMENTS = ("锂矿", "锂化合物及衍生品")
PROJECTS = ("格林布什化学级锂精矿工厂三期", "雅江锂辉石矿采选一期工程", "苏州年产3万吨氢氧化锂项目")


def operating_quality_run(snapshot: dict, question: str, route: dict, run_id: str) -> DiagnosisRun:
    run = Run(snapshot, "operating_quality", run_id)
    t = {"period_end": PERIOD, "base_period_end": BASE}
    rev = {(seg, p): _official(run, f"{seg}·营业收入", p, f"segment_revenue_{i}", "f013", f"{seg}营业收入")
           for i, seg in enumerate(SEGMENTS) for p in (PERIOD, BASE)}
    margin = {(seg, p): _official(run, f"{seg}·毛利率", p, f"segment_margin_{i}", "f013", f"{seg}毛利率")
              for i, seg in enumerate(SEGMENTS) for p in (PERIOD, BASE)}
    current_rev = [rev[(seg, PERIOD)] for seg in SEGMENTS]
    total = sum((D(item.value) for item in current_rev), Decimal(0)) if all(i.value is not None for i in current_rev) else None
    shares = {seg: run.computed(f"segment_share_{i}:{PERIOD}", f"segment_share_{i}", "f004", f"{seg}占两项业务收入比重",
                                q(D(rev[(seg, PERIOD)].value) / total * 100) if total else None, "%",
                                formula_id="segment_revenue_share", formula="该业务营业收入 ÷（锂矿 + 锂化合物及衍生品营业收入）",
                                inputs=current_rev, time={"period_end": PERIOD})
              for i, seg in enumerate(SEGMENTS)}
    growth = [_pct_change(run, f"segment_revenue_yoy_{i}:{PERIOD}", f"segment_revenue_yoy_{i}", "f013", f"{seg}营业收入同比",
                          rev[(seg, PERIOD)], rev[(seg, BASE)], t) for i, seg in enumerate(SEGMENTS)]
    now_margin = [margin[(seg, PERIOD)] for seg in SEGMENTS]
    if all(item.value is not None for item in list(shares.values()) + now_margin):
        bigger = max(SEGMENTS, key=lambda seg: D(shares[seg].value))
        richer = max(SEGMENTS, key=lambda seg: D(margin[(seg, PERIOD)].value))
        anchor = f"{bigger}收入占比较高，{richer}毛利率较高"
        spec = ("fact", "neutral", anchor, f"按半年报分产品口径，{anchor}；两项业务收入同比变化见证据。")
    else:
        spec = ("unknown", "unknown", "业务结构证据不足", "业务结构证据不足，暂不形成结论。")
    run.conclude("segment_structure", "f004", *spec, supports=list(shares.values()) + now_margin,
                 context=growth + list(rev.values()),
                 limitations=["分产品数据取自半年报“占营业收入百分之十以上”的产品表，两项合计约占总营收的绝大部分"],
                 highlights=[shares[SEGMENTS[0]], now_margin[0], shares[SEGMENTS[1]], now_margin[1]])

    changes = [run.computed(f"segment_margin_change_{i}:{PERIOD}", f"segment_margin_change_{i}", "f013", f"{seg}毛利率同比变动",
                            q(D(margin[(seg, PERIOD)].value) - D(margin[(seg, BASE)].value))
                            if margin[(seg, PERIOD)].value is not None and margin[(seg, BASE)].value is not None else None,
                            "个百分点", formula_id="margin_change_pp", formula="本期毛利率 − 上年同期毛利率",
                            inputs=[margin[(seg, PERIOD)], margin[(seg, BASE)]], time=t)
               for i, seg in enumerate(SEGMENTS)]
    ups = [D(item.value) > 0 for item in changes if item.value is not None]
    if len(ups) == 2 and all(ups):
        spec = ("fact", "positive", "两项业务毛利率均较上年同期上升", "两项业务毛利率均较上年同期上升（锂矿与锂化合物及衍生品）。")
    elif len(ups) == 2 and not any(ups):
        spec = ("fact", "negative", "两项业务毛利率均较上年同期下降", "两项业务毛利率均较上年同期下降（锂矿与锂化合物及衍生品）。")
    else:
        spec = ("fact", "mixed", "两项业务毛利率变动方向不一致", "两项业务毛利率变动方向不一致。")
    run.conclude("segment_margin", "f013", *spec, supports=changes, highlights=changes,
                 limitations=["毛利率变动为报表口径，不能据此拆分价格与成本各自的贡献"])

    income = _official(run, "投资收益", PERIOD, "investment_income", "f012", "投资收益")
    assoc = _official(run, "其中：对联营企业和合营企业的投资收益", PERIOD, "associate_income", "f012", "对联营、合营企业的投资收益")
    parent = _official(run, "归属于母公司股东的净利润", PERIOD, "parent_net_profit_official", "f012", "归母净利润")
    usable = income.value is not None and parent.value is not None and D(parent.value) > 0
    share = run.computed("investment_income_share:" + PERIOD, "investment_income_share", "f012", "投资收益 ÷ 归母净利润",
                         q(D(income.value) / D(parent.value) * 100) if usable else None, "%",
                         formula_id="investment_income_div_parent_profit",
                         formula="投资收益 ÷ 归母净利润；低于百分之十记为“较小”，百分之十至三十为“一定”，三十及以上为“较大”",
                         inputs=[income, parent], time={"period_end": PERIOD}, reason="归母净利润不大于零，比重不适用")
    if share.value is not None:
        level = "较小" if D(share.value) < 10 else "较大" if D(share.value) >= 30 else "一定"
        spec = ("fact", "neutral", f"投资收益占同期归母净利润的比重{level}",
                f"投资收益占同期归母净利润的比重{level}；其中对联营、合营企业的投资收益见证据。")
    else:
        spec = ("unknown", "unknown", "投资收益的利润贡献无法计算", "投资收益的利润贡献无法计算。")
    run.conclude("investment_income", "f012", *spec, supports=[share], context=[income, assoc, parent],
                 limitations=["投资收益属于非主营来源，其持续性需结合被投资企业情况判断"], highlights=[share, income, assoc])

    output, output_b = (_official(run, "锂精矿产量", p, "concentrate_output", "f014", "锂精矿产量") for p in (PERIOD, BASE))
    change = _pct_change(run, "concentrate_output_yoy:" + PERIOD, "concentrate_output_yoy", "f014", "锂精矿产量同比",
                         output, output_b, t)
    undisclosed = [_official(run, item, PERIOD, f"undisclosed_{i}", "f014", item)
                   for i, item in enumerate(("锂精矿销量", "锂化合物及衍生品·销量", "锂化合物及衍生品·产量"))]
    if change.value is not None:
        word = "增加" if D(change.value) > 0 else "减少"
        spec = ("fact", "positive" if word == "增加" else "negative", f"锂精矿产量较上年同期{word}",
                f"锂精矿产量较上年同期{word}；销量与锂化合物产销量报告未披露。")
    else:
        spec = ("unknown", "unknown", "锂精矿产量变化无法计算", "锂精矿产量变化无法计算。")
    run.conclude("output", "f014", *spec, supports=[change], context=[output, output_b] + undisclosed,
                 limitations=["产量为格林布什项目报告期累计约数", "销量、均价与单位成本未披露，不能推算量价"],
                 highlights=[output, change])
    return run.finish(question, route)


def risk_run(snapshot: dict, question: str, route: dict, run_id: str) -> DiagnosisRun:
    run = Run(snapshot, "risk", run_id)
    t = {"period_end": PERIOD, "base_period_end": BASE}
    cur, cur_b = (_indicator_evidence(run, SUBJECT, p, "current_ratio", "current_ratio", "f063", "流动比率", "倍") for p in (PERIOD, BASE))
    quick = _indicator_evidence(run, SUBJECT, PERIOD, "quick_ratio", "quick_ratio", "f063", "速动比率", "倍")
    cash_ratio = _indicator_evidence(run, SUBJECT, PERIOD, "cash_ratio", "cash_ratio", "f063", "现金比率")
    if cur.value is not None and cur_b.value is not None:
        word = "上升" if D(cur.value) >= D(cur_b.value) else "下降"
        spec = ("fact", "neutral", f"流动比率较上年同期{word}", f"流动比率较上年同期{word}；速动比率与现金比率见证据。")
    else:
        spec = ("unknown", "unknown", "短期偿债指标证据不足", "短期偿债指标证据不足。")
    run.conclude("liquidity", "f063", *spec, supports=[cur, cur_b], context=[quick, cash_ratio],
                 limitations=["指标取扶摇财务指标接口，现金比率口径以该接口为准"], highlights=[cur, quick, cash_ratio])

    cash = _statement_evidence(run, SUBJECT, PERIOD, "cash", "cash", "f065", "货币资金")
    net_cash, debt = _net_cash(run, cash)
    usable = debt.value is not None and cash.value is not None and D(debt.value) > 0
    cover = run.computed("cash_cover_debt:" + PERIOD, "cash_cover_debt", "f065", "货币资金 ÷ 有息债务",
                         q(D(cash.value) / D(debt.value)) if usable else None, "倍",
                         formula_id="cash_div_interest_bearing_debt", formula="货币资金 ÷ 有息债务合计",
                         inputs=[cash, debt], time={"period_end": PERIOD}, reason="有息债务为零或缺失")
    if cover.value is not None:
        anchor = "货币资金可覆盖有息债务" if D(cover.value) >= 1 else "货币资金不足以覆盖有息债务"
        spec = ("fact", "positive" if D(cover.value) >= 1 else "negative", anchor, f"{anchor}；差额即净现金，见证据。")
    else:
        spec = ("unknown", "unknown", "现金对有息债务的覆盖无法计算", "现金对有息债务的覆盖无法计算。")
    run.conclude("debt_cover", "f065", *spec, supports=[cover], context=[net_cash, debt, cash],
                 limitations=["未考虑受限货币资金与债务到期结构"], highlights=[cover, net_cash, debt])

    reserve, reserve_b = (_official(run, "存货跌价准备期末余额", p, "inventory_reserve", "f069", "存货跌价准备余额") for p in (PERIOD, BASE))
    impair, impair_b = (_official(run, "资产减值损失", p, "asset_impairment", "f069", "资产减值损失（负数为损失）") for p in (PERIOD, BASE))
    credit = _official(run, "信用减值损失", PERIOD, "credit_impairment", "f069", "信用减值损失（负数为损失）")
    change = _pct_change(run, "inventory_reserve_change:" + PERIOD, "inventory_reserve_change", "f069", "存货跌价准备余额同比变化",
                         reserve, reserve_b, t)
    if change.value is not None:
        word = "下降" if D(change.value) < 0 else "上升"
        spec = ("fact", "positive" if word == "下降" else "negative", f"存货跌价准备余额较上年同期末{word}",
                f"存货跌价准备余额较上年同期末{word}；本期资产减值与信用减值损失见证据。")
    else:
        spec = ("unknown", "unknown", "存货跌价准备变化无法计算", "存货跌价准备变化无法计算。")
    run.conclude("impairment", "f069", *spec, supports=[change], context=[reserve, reserve_b, impair, impair_b, credit],
                 limitations=["减值为会计估计，受锂价与存货结构影响"], highlights=[change, reserve, impair])

    capex = _official(run, "购建固定资产、无形资产和其他长期资产支付的现金", PERIOD, "capex_official", "f072", "购建长期资产支付现金")
    ocf = _statement_evidence(run, SUBJECT, PERIOD, "act_cash_flow_net", "operating_cash_flow", "f022", "经营活动现金流净额")
    usable = capex.value is not None and ocf.value is not None and D(ocf.value) > 0
    ratio = run.computed("capex_to_ocf:" + PERIOD, "capex_to_ocf", "f072", "资本开支 ÷ 经营现金流",
                         q(D(capex.value) / D(ocf.value)) if usable else None, "倍", formula_id="capex_div_operating_cash_flow",
                         formula="购建长期资产支付现金 ÷ 经营活动现金流净额（半年累计）", inputs=[capex, ocf],
                         time={"period_end": PERIOD}, reason="经营现金流不大于零，比值不适用")
    projects = [_official(run, f"在建项目·{name}·工程进度", PERIOD, f"project_{i}", "f072", f"在建项目：{name}")
                for i, name in enumerate(PROJECTS)]
    if ratio.value is not None:
        anchor = "资本开支低于同期经营现金流" if D(ratio.value) <= 1 else "资本开支高于同期经营现金流"
        spec = ("fact", "positive" if D(ratio.value) <= 1 else "negative", anchor, f"{anchor}；主要在建项目进度见证据。")
    else:
        spec = ("unknown", "unknown", "资本开支压力无法计算", "资本开支压力无法计算。")
    run.conclude("capex_pressure", "f072", *spec, supports=[ratio], context=[capex, ocf] + projects,
                 limitations=["半年累计口径；项目进度为报告原文，未包含后续投资计划金额"], highlights=[ratio, capex])
    return run.finish(question, route)
