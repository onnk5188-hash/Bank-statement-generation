import argparse
import os
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional, Tuple

import pandas as pd
import yaml
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas


def mm_to_pt(value: float) -> float:
    """Convert millimeters to points."""
    return value * mm
CH_FONT = "CNFont"


def register_chinese_font():
    """Register a Chinese TrueType font for voucher rendering.

    Prefers Windows SimSun first, then SimHei. Prints a warning if neither
    exists so the caller knows Chinese text might render incorrectly.
    """

    font_paths = [
        r"C:\\Windows\\Fonts\\simsun.ttc",  # 宋体
        r"C:\\Windows\\Fonts\\simhei.ttf",  # 黑体
    ]

    for path in font_paths:
        if os.path.exists(path):
            try:
                pdfmetrics.registerFont(TTFont(CH_FONT, path))
                print(f"Using Chinese font: {path}")
                return
            except Exception as exc:  # pragma: no cover - best-effort font registration
                print(f"注册中文字体失败 {path}: {exc}")

    print("WARNING: no Chinese font file found, Chinese characters may render as squares.")


@dataclass
class Voucher:
    number: str
    date: datetime
    description: str
    debit_account: str
    credit_account: str
    amount: float

    @property
    def formatted_date(self) -> str:
        return self.date.strftime("%Y年%m月%d日")

    @property
    def formatted_amount(self) -> str:
        return f"{self.amount:,.2f}"


def load_yaml_file(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def load_config(path: str) -> dict:
    if not os.path.exists(path):
        return {}
    return load_yaml_file(path)


def load_mapping(path: str) -> list:
    if not os.path.exists(path):
        return []
    data = load_yaml_file(path)
    if not isinstance(data, list):
        raise ValueError("mapping.yaml 内容格式需要是列表")
    return data


def try_read_csv(csv_path: str) -> pd.DataFrame:
    encodings = ["utf-8", "gbk", "gb2312"]
    errors = []
    for enc in encodings:
        try:
            return pd.read_csv(csv_path, encoding=enc)
        except UnicodeDecodeError as exc:
            errors.append(str(exc))
    raise UnicodeDecodeError(
        "无法读取 CSV", "", 0, 0, f"尝试的编码失败：{' | '.join(errors)}"
    )


def parse_csv(csv_path: str, filter_zero: bool = True) -> pd.DataFrame:
    df = try_read_csv(csv_path)
    df.columns = [c.strip() for c in df.columns]

    column_aliases = {
        "date": ["日期", "交易日期", "记账日期", "发生日期"],
        "summary": ["摘要", "附言", "用途", "说明"],
        "debit": ["借方金额", "借方", "收入"],
        "credit": ["贷方金额", "贷方", "支出"],
    }

    def find_column(possible_names: List[str]) -> Optional[str]:
        for name in possible_names:
            if name in df.columns:
                return name
        return None

    date_col = find_column(column_aliases["date"])
    summary_col = find_column(column_aliases["summary"])
    debit_col = find_column(column_aliases["debit"])
    credit_col = find_column(column_aliases["credit"])

    if not date_col or not summary_col or not (debit_col or credit_col):
        raise ValueError("CSV 缺少必要的列：日期/摘要/借方或贷方金额")

    df = df[[col for col in [date_col, summary_col, debit_col, credit_col] if col]]
    df = df.rename(
        columns={
            date_col: "date",
            summary_col: "summary",
            debit_col: "debit" if debit_col else "debit_missing",
            credit_col: "credit" if credit_col else "credit_missing",
        }
    )

    def parse_date(value) -> datetime:
        if pd.isna(value):
            raise ValueError("日期为空")
        if isinstance(value, datetime):
            return value
        for fmt in ("%Y/%m/%d", "%Y-%m-%d", "%Y.%m.%d", "%Y%m%d"):
            try:
                return datetime.strptime(str(value).strip(), fmt)
            except ValueError:
                continue
        # Let pandas try its best
        return pd.to_datetime(value)

    df["date"] = df["date"].apply(parse_date)
    df["summary"] = df["summary"].fillna("").astype(str)

    if "debit" in df.columns:
        df["debit"] = pd.to_numeric(df["debit"], errors="coerce").fillna(0.0)
    if "credit" in df.columns:
        df["credit"] = pd.to_numeric(df["credit"], errors="coerce").fillna(0.0)

    if filter_zero:
        df = df[(df.get("debit", 0) != 0) | (df.get("credit", 0) != 0)]

    return df


def map_entry_to_accounts(summary: str, mapping_rules: list, fallback_debit: str, fallback_credit: str) -> Tuple[str, str]:
    for rule in mapping_rules:
        keyword = rule.get("keyword")
        if keyword and keyword in summary:
            return rule.get("debit_account", fallback_debit), rule.get(
                "credit_account", fallback_credit
            )
    return fallback_debit, fallback_credit


def build_vouchers(df: pd.DataFrame, mapping_rules: list, start_number: int, fallback_debit: str, fallback_credit: str) -> List[Voucher]:
    vouchers: List[Voucher] = []
    for idx, row in df.iterrows():
        amount = row.get("debit", 0.0)
        amount_field = "debit"
        if amount == 0:
            amount = row.get("credit", 0.0)
            amount_field = "credit"
        if amount == 0:
            continue

        debit_account, credit_account = map_entry_to_accounts(
            row.get("summary", ""), mapping_rules, fallback_debit, fallback_credit
        )

        description = row.get("summary", "").strip() or "银行流水"
        number = f"{start_number + len(vouchers):03d}"
        vouchers.append(
            Voucher(
                number=number,
                date=row.get("date"),
                description=description,
                debit_account=debit_account,
                credit_account=credit_account,
                amount=float(abs(amount)),
            )
        )
    return vouchers


def draw_voucher(c: canvas.Canvas, voucher: Voucher, x: float, y: float, width: float, height: float, config: dict):
    c.roundRect(x, y, width, height, 4, stroke=1, fill=0)
    padding = mm_to_pt(6)
    line_height = mm_to_pt(6)

    title_y = y + height - padding
    company = config.get("company_name", "公司名称")

    # Header
    c.setFont(CH_FONT, 14)
    c.drawCentredString(x + width / 2, title_y - mm_to_pt(2), company)
    c.setFont(CH_FONT, 12)
    c.drawCentredString(x + width / 2, title_y - line_height - mm_to_pt(1), "记账凭证")

    info_y = title_y - line_height * 2 - mm_to_pt(2)
    c.setFont(CH_FONT, 10)
    c.drawString(x + padding, info_y, "凭证字：记")
    c.drawRightString(x + width - padding, info_y, f"编号：{voucher.number}")
    c.drawString(x + padding, info_y - line_height, f"日期：{voucher.formatted_date}")

    # Table layout
    table_top = info_y - line_height * 2
    table_left = x + padding
    table_width = width - 2 * padding
    summary_width = table_width * 0.25
    account_width = table_width * 0.38
    amount_width = (table_width - summary_width - account_width) / 2

    table_height = line_height * 4 + mm_to_pt(4)
    table_bottom = table_top - table_height

    c.rect(table_left, table_bottom, table_width, table_height, stroke=1, fill=0)

    # Column separators
    c.line(table_left + summary_width, table_bottom, table_left + summary_width, table_top)
    c.line(table_left + summary_width + account_width, table_bottom, table_left + summary_width + account_width, table_top)
    c.line(table_left + summary_width + account_width + amount_width, table_bottom, table_left + summary_width + account_width + amount_width, table_top)

    # Row separators
    for i in range(1, 4):
        c.line(table_left, table_top - i * line_height, table_left + table_width, table_top - i * line_height)

    # Headers
    c.setFont(CH_FONT, 10)
    header_y = table_top - line_height + mm_to_pt(1)
    c.drawCentredString(table_left + summary_width / 2, header_y, "摘要")
    c.drawCentredString(table_left + summary_width + account_width / 2, header_y, "科目")
    c.drawCentredString(table_left + summary_width + account_width + amount_width / 2, header_y, "借方金额")
    c.drawCentredString(table_left + summary_width + account_width + amount_width * 1.5, header_y, "贷方金额")

    # Debit row
    c.setFont(CH_FONT, 10)
    debit_y = table_top - line_height * 2 + mm_to_pt(1)
    c.drawString(table_left + mm_to_pt(2), debit_y, voucher.description)
    c.drawString(table_left + summary_width + mm_to_pt(2), debit_y, voucher.debit_account)
    c.drawRightString(table_left + summary_width + account_width + amount_width - mm_to_pt(2), debit_y, voucher.formatted_amount)

    # Credit row
    credit_y = debit_y - line_height
    c.drawString(table_left + summary_width + mm_to_pt(2), credit_y, voucher.credit_account)
    c.drawRightString(table_left + summary_width + account_width + 2 * amount_width - mm_to_pt(2), credit_y, voucher.formatted_amount)

    # Total row
    total_y = credit_y - line_height
    c.drawString(table_left + mm_to_pt(2), total_y, "合计")
    c.drawRightString(table_left + summary_width + account_width + amount_width - mm_to_pt(2), total_y, voucher.formatted_amount)

    # Footer signatures
    footer_y = y + padding + mm_to_pt(2)
    c.setFont(CH_FONT, 9)
    positions = ["制单", "审核", "出纳", "记账", "复核"]
    spacing = table_width / len(positions)
    for i, label in enumerate(positions):
        c.drawString(table_left + spacing * i, footer_y, f"{label}：________________")


def render_vouchers_to_pdf(vouchers: List[Voucher], output_path: str, vouchers_per_page: int, config: dict):
    output_dir = os.path.dirname(output_path) or "."
    os.makedirs(output_dir, exist_ok=True)

    page_width, page_height = A4
    margin = mm_to_pt(config.get("margin_mm", 12))
    spacing = mm_to_pt(config.get("spacing_mm", 6))

    c = canvas.Canvas(output_path, pagesize=A4)

    voucher_height = (
        page_height - 2 * margin - spacing * (vouchers_per_page - 1)
    ) / vouchers_per_page
    voucher_width = page_width - 2 * margin

    x = margin
    y = page_height - margin - voucher_height

    for idx, voucher in enumerate(vouchers):
        draw_voucher(c, voucher, x, y, voucher_width, voucher_height, config)
        if (idx + 1) % vouchers_per_page == 0 and idx + 1 != len(vouchers):
            c.showPage()
            y = page_height - margin - voucher_height
        else:
            y -= voucher_height + spacing

    c.save()


def render_single_vouchers(vouchers: List[Voucher], output_dir: str, config: dict):
    os.makedirs(output_dir, exist_ok=True)
    for voucher in vouchers:
        path = os.path.join(output_dir, f"voucher_{voucher.number}.pdf")
        c = canvas.Canvas(path, pagesize=A4)
        width, height = A4
        margin = mm_to_pt(config.get("margin_mm", 12))
        voucher_width = width - 2 * margin
        voucher_height = height - 2 * margin
        draw_voucher(c, voucher, margin, height - margin - voucher_height, voucher_width, voucher_height, config)
        c.save()


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="银行流水生成记账凭证")
    parser.add_argument("--input", required=True, help="输入银行 CSV 文件路径")
    parser.add_argument("--output", default="output/vouchers.pdf", help="汇总 PDF 输出路径")
    parser.add_argument("--mapping", default="mapping.yaml", help="摘要到科目的映射文件")
    parser.add_argument("--config", default="config.yaml", help="基础配置文件")
    parser.add_argument("--single", action="store_true", help="同时生成单张凭证 PDF")
    parser.add_argument("--start-number", type=int, help="凭证号起始编号（覆盖配置）")
    parser.add_argument("--vouchers-per-page", type=int, choices=[2, 3], help="每页几张凭证（覆盖配置）")
    return parser


def main(argv: Optional[List[str]] = None):
    parser = build_argument_parser()
    args = parser.parse_args(argv)

    register_chinese_font()

    config = load_config(args.config)
    mapping_rules = load_mapping(args.mapping)

    start_number = args.start_number if args.start_number is not None else config.get("start_number", 1)
    vouchers_per_page = args.vouchers_per_page if args.vouchers_per_page else config.get("vouchers_per_page", 3)
    filter_zero = bool(config.get("filter_zero_amounts", True))

    fallback_debit = config.get("fallback_debit_account", "")
    fallback_credit = config.get("fallback_credit_account", "")

    df = parse_csv(args.input, filter_zero=filter_zero)
    vouchers = build_vouchers(df, mapping_rules, start_number, fallback_debit, fallback_credit)

    if not vouchers:
        print("没有需要生成的凭证，检查 CSV 内容或过滤规则。")
        return

    render_vouchers_to_pdf(vouchers, args.output, vouchers_per_page, config)
    print(f"已生成汇总 PDF：{args.output}")

    if args.single:
        output_dir = os.path.join(os.path.dirname(args.output), "single")
        render_single_vouchers(vouchers, output_dir, config)
        print(f"已生成单张凭证 PDF 至：{output_dir}")


if __name__ == "__main__":
    main()
