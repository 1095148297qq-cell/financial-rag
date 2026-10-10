# 财报收录准确性核查

重新查询巨潮资讯当前年度报告全文清单；重新下载全部24份官方PDF并对照本地SHA256；核对封面、年度、公司和全文身份。
将参考数据中的营收、归母净利润和经营现金流与原始主要指标页及合并报表交叉核对。文字检索到金额是一致性检查，不等于审计全部单元格。

| 公司 | 年度 | 官方文件字节一致 | 公司/年度/全文 | 三项关键数据合并报表核对 | 可疑表头块 |
|---|---:|---|---|---|---:|
| 贵州茅台 | 2024 | 一致 | 通过 | revenue:matched、net_profit:matched、operating_cash_flow:matched | 115 |
| 贵州茅台 | 2025 | 一致 | 通过 | revenue:matched、net_profit:matched、operating_cash_flow:matched | 52 |
| 五粮液 | 2024 | 一致 | 通过 | revenue:matched、net_profit:matched、operating_cash_flow:matched | 116 |
| 五粮液 | 2025 | 一致 | 通过 | revenue:matched、net_profit:matched、operating_cash_flow:matched | 85 |
| 泸州老窖 | 2024 | 一致 | 通过 | revenue:matched、net_profit:matched、operating_cash_flow:matched | 52 |
| 泸州老窖 | 2025 | 一致 | 通过 | revenue:matched、net_profit:matched、operating_cash_flow:matched | 81 |
| 山西汾酒 | 2024 | 一致 | 通过 | revenue:matched、net_profit:matched、operating_cash_flow:matched | 66 |
| 山西汾酒 | 2025 | 一致 | 通过 | revenue:matched、net_profit:matched、operating_cash_flow:matched | 63 |
| 洋河股份 | 2024 | 一致 | 通过 | revenue:matched、net_profit:matched、operating_cash_flow:matched | 102 |
| 洋河股份 | 2025 | 一致 | 通过 | revenue:matched、net_profit:matched、operating_cash_flow:matched | 83 |
| 古井贡酒 | 2024 | 一致 | 通过 | revenue:matched、net_profit:matched、operating_cash_flow:matched | 49 |
| 古井贡酒 | 2025 | 一致 | 通过 | revenue:matched、net_profit:matched、operating_cash_flow:matched | 52 |
| 今世缘 | 2024 | 一致 | 通过 | revenue:matched、net_profit:matched、operating_cash_flow:matched | 101 |
| 今世缘 | 2025 | 一致 | 通过 | revenue:matched、net_profit:matched、operating_cash_flow:matched | 76 |
| 口子窖 | 2024 | 一致 | 通过 | revenue:matched、net_profit:matched、operating_cash_flow:matched | 44 |
| 口子窖 | 2025 | 一致 | 通过 | revenue:matched、net_profit:matched、operating_cash_flow:matched | 86 |
| 舍得酒业 | 2024 | 一致 | 通过 | revenue:matched、net_profit:matched、operating_cash_flow:matched | 67 |
| 舍得酒业 | 2025 | 一致 | 通过 | revenue:matched、net_profit:matched、operating_cash_flow:matched | 60 |
| 水井坊 | 2024 | 一致 | 通过 | revenue:matched、net_profit:matched、operating_cash_flow:matched | 59 |
| 水井坊 | 2025 | 一致 | 通过 | revenue:matched、net_profit:matched、operating_cash_flow:matched | 46 |
| 老白干酒 | 2024 | 一致 | 通过 | revenue:matched、net_profit:matched、operating_cash_flow:matched | 44 |
| 老白干酒 | 2025 | 一致 | 通过 | revenue:matched、net_profit:matched、operating_cash_flow:matched | 44 |
| 金徽酒 | 2024 | 一致 | 通过 | revenue:matched、net_profit:matched、operating_cash_flow:matched | 96 |
| 金徽酒 | 2025 | 一致 | 通过 | revenue:matched、net_profit:matched、operating_cash_flow:matched | 105 |

已修正23条发布日期：原先按UTC记录，现在按中国时区记录。文件及金额没有因日期修正而改变。

注意：续页表格存在将第一条数据行识别为表头的风险。可疑表头计数是风险扫描，不代表每块都错误；因此不能声称整个提取库100%准确。
原始财报、提取文本、参考数字和模型回答应分别评价。已有评测中的母公司/合并口径混淆、净资产误作营收、现金净流出误称亏损，属于检索/解释错误，不能据此判定官方下载文件错误。

已确认的提取错误示例：泸州老窖2025年PDF第84页，续表第一条数据行“处置固定资产、无形资产和其他长期资产收回的现金净额 / 115,575.89 / 10,363,496.03”被作为列名。年度/本期上期列头没有正确继承，后续行的数值列名因此不可靠。金额原文仍可在PDF核对，但当前表格结构不能视为完全准确。
