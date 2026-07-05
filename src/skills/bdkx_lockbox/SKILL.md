---
name: process_bdkx_lockbox
description: "Instructions for parsing and mapping Bank BDKX lockbox CSV files to JDE F03B13Z1 format using the high-performance dynamic tool."
---

# BDKX Lockbox Parsing Rules

When asked to process a lockbox file originating from Bank BDKX (or generate its JDE CSV), you MUST NOT read the CSV row-by-row yourself.
Instead, immediately pass the raw CSV content and the following JSON mapping object to the `process_dynamic_csv_to_jde` tool.

**Use this exact `mapping_json`**:
```json
{
  "RURMK": {"source_column": "Customer Name", "transform": "none"},
  "RUCKAM": {"source_column": "Check Amount", "transform": "mult_100"},
  "RUDOCM": {"source_column": "Payment ID (Check No.)", "transform": "none"},
  "RUAMTS": {"source_column": "Total Payment Amount", "transform": "mult_100"},
  "RUDMTJ": {"source_column": "Payment Date", "transform": "julian"},
  "RUTNST": {"source_column": "Bank Transit / Routing", "transform": "none"},
  "RUCBNK": {"source_column": "Bank Account Number", "transform": "none"},
  "RUAG": {"source_column": "Amount Applied", "transform": "mult_100"},
  "RUVR02": {"source_column": "Credit Card Number", "transform": "none"},
  "RUVR01": {"source_column": "Authorization Number", "transform": "none"},
  "RUGMFD": {"source_column": "Generic Matching Field", "transform": "none"},
  "RUEDTN": {"source_column": "Deposit ID", "transform": "none"},
  "RUCKNU": {"source_column": "Terminal ID", "transform": "none"},
  "RUEDUS": {"source_column": "Merchant ID", "transform": "none"},
  "RUEDBT": {"source_column": "Bank Lockbox Number", "transform": "none"},
  "RUICUT": {"constant": "9D"},
  "RUEDLN": {"constant": 0}
}
```

Wait for the tool to execute. It will instantly return the 17-column CSV payload formatted specifically for the JDE F03B13Z1 table.

IMPORTANT: If the user explicitly asks for an Excel export or a tabular format, output the resulting JDE structure as a Markdown Table. Otherwise, just output the raw CSV payload returned by the tool inside a code block without explanations.
