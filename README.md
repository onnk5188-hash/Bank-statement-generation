# 银行流水自动生成记账凭证工具

一个将银行 CSV 流水自动转换为标准记账凭证 PDF 的命令行工具。支持关键字科目映射、凭证批量排版（A4 一页 2 或 3 张）以及可选的单张凭证导出。

## 功能概览

- 支持 UTF-8 / GBK 等常见编码的银行流水 CSV 导入，自动过滤金额为 0 的记录。
- 通过 `mapping.yaml` 根据摘要关键字匹配借贷科目，可配置默认科目兜底。
- 按模板排版凭证：公司名称、凭证号、日期、摘要、借方/贷方科目金额与签字栏。
- 汇总 PDF 支持每页 2 或 3 张凭证排版，可追加导出单张 PDF。

## 快速开始

1. 安装依赖：
   ```bash
   pip install -r requirements.txt
   ```
2. 准备文件：
   - `mapping.yaml`：摘要关键字与借贷科目映射。
   - `config.yaml`：公司名称、每页凭证数、起始编号、默认科目等基础配置。
   - `input.csv`：银行流水（示例字段：日期、摘要、借方金额、贷方金额）。
3. 运行生成：
   ```bash
   python main.py --input input.csv --output output/vouchers.pdf --single
   ```
   其中 `--single` 参数可选，用于输出单张凭证 PDF 到 `output/single/`。

## 常用参数

| 参数 | 说明 | 默认值 |
| --- | --- | --- |
| `--input` | 输入银行 CSV 路径 | 必填 |
| `--output` | 汇总 PDF 输出路径 | `output/vouchers.pdf` |
| `--mapping` | 摘要与科目映射文件 | `mapping.yaml` |
| `--config` | 基础配置文件 | `config.yaml` |
| `--single` | 是否同时导出单张凭证 | 关闭 |
| `--start-number` | 凭证起始编号（覆盖配置） | 配置文件中的 `start_number` |
| `--vouchers-per-page` | 每页凭证数量（2 或 3，覆盖配置） | 配置文件中的 `vouchers_per_page` |

## 配置示例

- `config.yaml`
  ```yaml
  company_name: "海口首桥商贸有限公司"
  vouchers_per_page: 3
  start_number: 1
  currency_symbol: "¥"
  amount_precision: 2
  spacing_mm: 6
  margin_mm: 12
  fallback_debit_account: "1002 银行存款"
  fallback_credit_account: "6602 管理费用-其他"
  filter_zero_amounts: true
  ```

- `mapping.yaml`
  ```yaml
  - keyword: "工资"
    debit_account: "2211.01 应付职工薪酬-工资"
    credit_account: "1002 银行存款"
  - keyword: "手续费"
    debit_account: "6602 管理费用-手续费"
    credit_account: "1002 银行存款"
  - keyword: "房贷"
    debit_account: "2203 应付利息"
    credit_account: "1002 银行存款"
  - keyword: "转账"
    debit_account: "1001 库存现金"
    credit_account: "1002 银行存款"
  ```

## 开发提示

- 代码入口：`main.py`。主要流程：读取配置/映射 → 解析 CSV → 构建凭证数据 → 生成 PDF。
- CSV 列名兼容多种常见字段：日期/交易日期、摘要/附言/用途、借方金额/收入、贷方金额/支出。
- PDF 由 ReportLab 绘制，排版参数（页边距、凭证间距、每页张数）可通过配置或命令行调整，程序会尝试自动注册系统中的中文字体（如未找到则提示警告）。

## 许可证

MIT
