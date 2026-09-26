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
    "cash_minus_total_debt": "货币资金 − 总债务",
    "adjusted_close_return_20_60": "前复权收盘价计算 20/60 交易日收益率",
    "volume_vs_n_day_average": "当日成交量与过去 N 个交易日均量比较；N 待定",
    "cash_div_total_debt": "货币资金 ÷ 总债务；须核准债务范围",
    "profit_cash_sign_alignment": "同期净利润与经营现金流净额的符号比较",
}
SOURCE_NAMES = {
    "fuyao": "扶摇", "ifind": "iFinD", "official_filing": "公告/定期报告原文",
    "peer_group": "同行数据", "price_series": "日线序列", "source_to_verify": "来源待核",
}
CATEGORY_CALC_SUMMARY = {
    "operating_quality": "营业利润率、研发费用率；分业务/产能口径待核",
    "financial_trend": "现金流/净利润、自由现金流近似值、净现金；同比与累计/单季须对齐",
    "valuation": "历史估值分位、同行估值中位数；需确定采样和负值处理",
    "market": "区间涨跌幅、量能变化、相对行业表现；需对齐交易日与复权",
    "industry": "同行财务及估值比较；需固定同行组和同日/同期间口径",
    "events": "事件筛选与报告期/披露日核对；公告片段须定位原文",
    "risk": "现金/总债务、利润现金流背离；敏感性模型和项目压力尚未确定",
}
ADDITIONAL_CALC_NOTES = {
    "f012": "投资收益原值来自 iFinD；利润贡献的分母与同一期次待确定",
    "f013": "分业务收入/成本/毛利率需逐列核对单位；如自算毛利率，依赖同一分部收入与成本",
    "f039": "历史 PE/PB 分位需历史同口径序列、交易日采样及负 PE 处理；算法待定",
    "f040": "同行估值中位数需固定同行组、同日同口径估值及负值处理",
    "f045": "可直接取 iFinD 风险指标；如改用日 K 自算，需固定窗口、复权和年化口径",
    "f047": "需个股与行业指数同区间收益率，交易日和行业分类对齐后比较",
    "f057": "期末与实际披露日分别核准；`report_date_ms` 不直接充当披露日",
    "f070": "需分部经营数据与同品级锂价序列；敏感性模型未核准，不能直接推算利润",
    "f072": "需项目原公告、购建长期资产支付现金及债务/资金证据；综合规则待定",
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
        "现有固定快照只含扶摇年报的净利润和经营活动现金流净额。以下四类问题会读取这份快照并生成证据与结论；LLM 仅翻译程序结论。",
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
        "## 二、已规划但尚不能生成结论的问题",
        "",
        "这些类别目前只返回字段需求清单（`planned`），不会读取快照或生成金融结论。`全部候选` 是可钻取范围；`默认优先字段` 是未来有限首屏输出的规划，不代表已取得有效证据。",
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
        "### 规划类别的来源和计算总览",
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
        "下表保留当前 72 条候选字段的来源表达、企业相关优先级和取舍理由。`已接入` 指可在上述四类窄问题中使用；`待接入` 指目前尚无产品结论。计算公式列是候选配方，除当前比值和符号比较外，尚需核准输入、单位与报告期后才能执行。",
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
            product_state = "已接入窄问题" if field["id"] in IMPLEMENTED_FIELD_IDS else "待接入 / 待核准"
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
        "- 同行组、公告原文、估值历史序列、行情区间以及多数计算公式仍待核准；本表不能代替最终发布快照或测试结果。",
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
