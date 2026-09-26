"""Export a readable routing map from the reviewed field catalog."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from diagnosis.catalog import CATALOG_VERSION, DIMENSIONS, EXECUTABLE_FIELDS, IMPLEMENTED_FIELD_IDS, load_catalog  # noqa: E402
from diagnosis.priority import load_priority_profile, make_display_plan  # noqa: E402

TARGET = ROOT / "docs" / "question-routing-map.md"
QUESTION_EXAMPLES = {
    "net_profit_status": "净利润是正还是负？",
    "operating_cash_flow_status": "经营活动现金流净额为正吗？",
    "profit_cash_ratio": "经营现金流与净利润的比值是多少？",
    "profit_cash_alignment": "利润和经营现金流匹配吗？",
    "operating_quality": "主营业务经营质量如何？",
    "financial_trend": "财务趋势如何？",
    "valuation": "估值如何？",
    "market": "行情特征如何？",
    "industry": "行业位置如何？",
    "events": "近期重要事件有哪些？",
    "risk": "主要风险有哪些？",
}
INTENT_NAMES = {
    "net_profit_status": "净利润正负",
    "operating_cash_flow_status": "经营现金流正负",
    "profit_cash_ratio": "现金流与净利润比值",
    "profit_cash_alignment": "利润与现金流方向关系",
}
FORMULA_TEXT = {
    "operating_profit_div_operating_income": "营业利润 ÷ 营业收入",
    "rd_expense_div_operating_income": "研发费用 ÷ 营业收入",
    "operating_cash_flow_div_net_profit": "经营现金流净额 ÷ 净利润；净利润须为正",
    "operating_cash_flow_minus_fixed_asset_cash": "经营现金流净额 − 购建长期资产支付现金（近似值）",
    "cash_minus_interest_bearing_debt": "货币资金 − 官方半年报五项有息债务合计",
    "adjusted_close_return_20_60": "前复权收盘价计算 20/60 交易日收益率",
    "volume_vs_n_day_average": "当日成交量与过去 N 个交易日均量比较；N 待定",
    "cash_div_interest_bearing_debt": "货币资金 ÷ 官方半年报五项有息债务合计",
    "profit_cash_sign_alignment": "同期净利润与经营现金流净额的符号比较",
}
SOURCE_NAMES = {
    "fuyao": "扶摇", "ifind": "iFinD", "official_filing": "公告/定期报告原文",
    "peer_group": "同行数据", "price_series": "日线序列", "source_to_verify": "来源待核",
}
CATEGORY_CALC_SUMMARY = {
    "operating_quality": "分业务收入与毛利率、投资收益贡献、锂精矿产量；未披露的量价成本保持缺口",
    "financial_trend": "累计口径同比、现金流/净利润、自由现金流近似值、净现金；报告期与基期对齐",
    "valuation": "iFinD 自身交易日序列分位与正式同行组中位数；亏损期负 PE 分位不适用",
    "market": "前复权区间涨跌、回撤、波动和相对行业表现；交易日与期间对齐",
    "industry": "正式同行组财务、估值与行情比较；四类锂价只作行业环境证据",
    "events": "巨潮官方公告分类、按期披露和预告对照；摘录附 PDF 原文链接与页码",
    "risk": "现金/有息债务、减值与资本开支；锂价敏感性和海外敞口明确列为未知",
}
ADDITIONAL_CALC_NOTES = {
    "f012": "投资收益原值与同报告期归母净利润比较；分母不适用时保留缺口",
    "f013": "官方半年报分业务收入、成本与毛利率；按报告期和单位核对",
    "f039": "只在 iFinD 同口径交易日序列内计算分位；PE(TTM) 含亏损期负倍数时不适用",
    "f040": "赣锋锂业、中矿资源、永兴材料同日同口径估值取中位数",
    "f045": "产品以前复权日线自算区间最大回撤与年化波动率；不混用 iFinD 周频风险指标",
    "f047": "个股前复权区间收益与同期间行业复合收益比较；行业月度口径须一致",
    "f057": "期末与实际披露日分别核准；`report_date_ms` 不直接充当披露日",
    "f070": "需分部经营数据与同品级锂价序列；敏感性模型未核准，不能直接推算利润",
    "f072": "官方项目摘录、购建长期资产支付现金及债务/资金证据；未核准的压力测算不推算",
}


def _cell(value: object) -> str:
    return str(value).replace("|", "\\|").replace("\n", "<br>")


def _ids(fields: list[dict] | tuple[dict, ...]) -> str:
    return "、".join(f"`{field['id']}`" for field in fields)


def _calc(field: dict) -> str:
    if field["id"] in ADDITIONAL_CALC_NOTES:
        return ADDITIONAL_CALC_NOTES[field["id"]]
    formula_id = field.get("formula_id")
    if not formula_id:
        return "原始来源字段；组合项需逐项核对" if field["kind"] == "composite" else "原始来源字段，无产品自算公式"
    inputs = "、".join(f"`{item}`" for item in field["input_fields"])
    return f"{FORMULA_TEXT[formula_id]}<br>输入：{inputs}"


def render() -> str:
    fields = load_catalog()
    profile = load_priority_profile()
    by_id = {field["id"]: field for field in fields}
    lines = [
        "# 问题类别与证据展开对照表",
        "",
        f"配置版本：`{CATALOG_VERSION}`；标的：天齐锂业 `002466.SZ`；观察区间：2025-08-31 至 2026-08-31；数据截止日：2026-08-31。",
        "",
        "本表由 `py scripts/export_question_routing_md.py` 从字段目录和天齐锂业优先级配置生成。**候选字段不等于已核准证据，展示优先级也不是投资评分。**“已取值”仅表示实验阶段接口曾返回字段；运行时仍要检查证据状态、报告期、单位和口径。",
        "",
        "## 展示优先级如何确定",
        "",
        f"配置版本：`{profile['version']}`。研究假设：{profile['business_profile']}",
        "",
        "依据：[2025 年年度报告](https://static.cninfo.com.cn/finalpage/2026-03-28/1225044817.PDF)、[2026 年半年度报告](https://static.cninfo.com.cn/finalpage/2026-08-28/1225522276.PDF)。报告披露矿端与锂化工业务，也讨论锂产品价格、锂精矿定价及成本传导。因此默认先看同品级锂价和分业务量价成本，再看利润现金、库存、债务与项目；研发费用等弱化展示。价格指标不能直接等同公司实现售价。",
        "",
        "四档只用于排序：**核心驱动/风险** → **解释与交叉验证** → **背景或钻取** → **弱化展示**。单维问题默认最多 5 项，多维问题最多 8 项，全面诊断按维度配额最多 12 项；完整候选仍可钻取。用户明确提问某项弱化字段时，该字段会进入默认展示。重要字段即使尚未核准，也应显示为证据缺口，不能拿低优先级字段冒充其结论。",
        "",
        "## 一、当前可执行的问题",
        "",
        "两字段快照只含扶摇年报的净利润和经营活动现金流净额。以下四类窄问题读取该快照；七维诊断另读取完整产品快照。LLM 仅翻译程序结论。",
        "",
        "| 问题类别 | 示例问题 | 展开维度 | 字段 | 来源 | 计算依赖 |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for intent in ("net_profit_status", "operating_cash_flow_status", "profit_cash_ratio", "profit_cash_alignment"):
        selected = [by_id[field_id] for field_id in EXECUTABLE_FIELDS[intent]]
        dimensions = "财务趋势、风险" if intent == "profit_cash_alignment" else "财务趋势"
        sources = "扶摇利润表 `net_profit`" if intent == "net_profit_status" else \
            "扶摇现金流量表 `act_cash_flow_net`" if intent == "operating_cash_flow_status" else \
            "扶摇利润表 `net_profit`；扶摇现金流量表 `act_cash_flow_net`"
        calc = "无；判定单项数值正、负或零" if intent in ("net_profit_status", "operating_cash_flow_status") else \
            "同一期同口径 `act_cash_flow_net / net_profit`；净利润须为正" if intent == "profit_cash_ratio" else \
            "同一期同口径比较两项数值符号；比值仅为辅助证据"
        lines.append(f"| {INTENT_NAMES[intent]} (`{intent}`) | {QUESTION_EXAMPLES[intent]} | {dimensions} | {_ids(selected)} | {sources} | {calc} |")
    lines += [
        "",
        "净利润或经营现金流单项问题只引用对应的一项来源。比值和方向关系问题需要两项来源的报告期、累计/单季口径、合并口径及单位一致。比值分母非正、输入缺失或期次不齐时不产生普通比值。",
        "",
        "## 二、按维度展开的问题",
        "",
        "经营质量、财务趋势、估值、行情特征、行业位置、重要事件、风险七维均读取完整产品快照并生成结论（`implemented`，决策 0016、0018、0022）。未覆盖年份和未核准字段继续显示缺口；新闻只作待核线索。`全部候选` 是可钻取范围；`默认优先字段` 是首屏字段规划，不等于每个字段都已有有效证据。",
        "",
        "| 问题类别 | 示例问题 | 展开维度 | 全部候选 | 默认优先字段 |",
        "| --- | --- | --- | ---: | --- |",
    ]
    for dimension, name in DIMENSIONS.items():
        selected = [field for field in fields if field["dimension"] == dimension]
        plan = make_display_plan(dimension, (dimension,), selected, QUESTION_EXAMPLES[dimension])
        lines.append(f"| {name} (`{dimension}`) | {QUESTION_EXAMPLES[dimension]} | {name} | {len(selected)} | {_ids([by_id[field_id] for field_id in plan['default_field_ids']])} |")
    overview_plan = make_display_plan("overview", tuple(DIMENSIONS), list(fields), "全面诊断一下")
    industry_valuation = [field for field in fields if field["dimension"] in ("valuation", "industry")]
    multi_plan = make_display_plan("multi_dimension", ("valuation", "industry"), industry_valuation, "估值和行业位置如何？")
    lines += [
        f"| 全面诊断 (`overview`) | 全面诊断一下 | 七个维度 | {len(fields)} | {_ids([by_id[field_id] for field_id in overview_plan['default_field_ids']])} |",
        f"| 多维提问 (`multi_dimension`) | 估值和行业位置如何？ | 估值、行业位置 | {len(industry_valuation)} | {_ids([by_id[field_id] for field_id in multi_plan['default_field_ids']])} |",
        "",
        "同比、趋势、指定年份、两项绝对差额等问题不复用上述四个单期窄意图。直接买卖、仓位、收益承诺及确定性股价预测问题为 `unsupported`。",
        "",
        "### 全面诊断默认首屏的 12 项",
        "",
    ]
    for dimension in profile["dimension_order"]:
        selected_ids = [field_id for field_id in overview_plan["default_field_ids"] if by_id[field_id]["dimension"] == dimension]
        names = "、".join(f"`{field_id}` {by_id[field_id]['label']}" for field_id in selected_ids)
        lines.append(f"- **{DIMENSIONS[dimension]}（{len(selected_ids)} 项）**：{names}。")
    lines += [
        "",
        "### 七维来源和计算总览",
        "",
        "| 问题类别 | 主要来源 | 主要计算或对齐依赖 |",
        "| --- | --- | --- |",
    ]
    for dimension, name in DIMENSIONS.items():
        selected = [field for field in fields if field["dimension"] == dimension]
        groups = {group for field in selected for group in field["source_groups"]}
        source_names = "、".join(SOURCE_NAMES[group] for group in SOURCE_NAMES if group in groups)
        lines.append(f"| {name} | {source_names} | {CATEGORY_CALC_SUMMARY[dimension]} |")
    lines += [
        "",
        "## 三、各维度字段、来源与计算依赖",
        "",
        "下表保留当前 72 条候选字段的来源表达、企业相关优先级和取舍理由。`已接入` 指相应窄问题或维度已有产品证据，`待接入 / 待核准` 指尚无正式数值证据；f070/f071 虽没有核准测算，风险维度会以未知结论显示缺口。计算依赖列是目录配方或口径摘要，实际数值以运行对象的公式、输入证据和状态为准。",
        "",
    ]
    for dimension, name in DIMENSIONS.items():
        selected = [field for field in fields if field["dimension"] == dimension]
        lines += [
            f"### {name}（{len(selected)} 项）",
            "",
            "| ID | 字段或指标 | 展示优先级与理由 | 来源 / 原字段 | 计算依赖 | 候选核查状态 | 产品状态 |",
            "| --- | --- | --- | --- | --- | --- | --- |",
        ]
        for field in selected:
            product_state = ("已接入窄问题" if field["id"] in EXECUTABLE_FIELDS["profit_cash_alignment"] else "已接入维度诊断") \
                if field["id"] in IMPLEMENTED_FIELD_IDS else "已展示未知缺口" if field["id"] in ("f070", "f071") else "待接入 / 待核准"
            tier, reason = profile["fields"][field["id"]]
            priority = f"{profile['tier_labels'][tier]}：{reason}"
            lines.append(f"| `{field['id']}` | {_cell(field['label'])} | {_cell(priority)} | {_cell(field['source_ref'])} | {_cell(_calc(field))} | {field['candidate_status']} | {product_state} |")
        lines.append("")
    lines += [
        "## 四、使用边界",
        "",
        "- 运行时证据以 `Evidence.quality.status` 为准；缺失、冲突、错误、超截止期次和不适用均不能补成有效值。",
        "- 优先级只决定默认展示，不替代用户意图、证据质量或行业研究结论；用户点名的弱化字段仍进入首屏。",
        "- 公开页面须展示固定快照 ID、下载时间、财报期次、来源、单位和口径，并提供由结论钻取到证据的路径。",
        "- 正式同行组、公告原文、估值历史序列和行情区间已接入产品；其余候选字段仍可能缺失或待核，不能以本表代替运行时证据与测试结果。",
        "",
    ]
    return "\n".join(lines)


def main() -> None:
    content = render()
    if len(sys.argv) == 2 and sys.argv[1] == "--check":
        if not TARGET.exists() or TARGET.read_text(encoding="utf-8") != content:
            raise SystemExit("question routing map is out of date; run py scripts/export_question_routing_md.py")
        print("question routing map is current")
        return
    if len(sys.argv) != 1:
        raise SystemExit("usage: py scripts/export_question_routing_md.py [--check]")
    TARGET.write_text(content, encoding="utf-8")
    print(f"wrote {len(load_catalog())} candidate fields to {TARGET}")


if __name__ == "__main__":
    main()
