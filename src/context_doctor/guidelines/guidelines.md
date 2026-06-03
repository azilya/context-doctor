# **Evaluation Criteria for Text-to-SQL Rules**

## Tier 1 – Structural Form (Concrete Requirements)

1. **Rule Structure and Keyword Usage**
    - Every rule must follow **Condition -> Action structure**:
        *WHEN <condition>, THEN <action>* (or equivalent *IF… THEN*)
        OR
        *ALWAYS/NEVER <action>*
    - The rule must use these **structural keywords** to enforce clarity and consistency: `WHEN`, `IF`, `THEN`, `ALWAYS`, `NEVER` (uppercase or lowercase).
    - The rule must not substitute these with alternative or weaker expressions (e.g., “whenever,” “sometimes,” “maybe”).

2. **Strength and Framing**
    - The rule must use direct, positive, and unambiguous wording.
    - Avoid hedging or weak phrasing (e.g., “you should probably,” “usually”).
    - Express actions in positive form whenever possible (e.g., *“ALWAYS use `product_display_name`”* instead of *“Do not use `product_id`”*).
    - The only acceptable negative forms are strong, categorical prohibitions: `NEVER` or `MUST NOT`.

3. **Formatting for Complex Rules**
    - If the rule describes a multi-step or complex (involving several actions) instruction, these steps or actions must be presented as an ordered list or obvious titles (e.g., `Trigger`, `Action`, `Calculation`).

    Example 1:

    ```
    When user asks about budget or income always use TotalBudget table.

    Trigger - When asked about "income" or "budget".
    Action - Query the TotalBudget table. Always apply the filter WHERE RecordType = '01'.
    Calculation
    - To find the budget, calculate SUM(ExpectedIncome).
    - To find the income, calculate SUM(Income).
    ```

    Example 2:

    ```
    **Global M : N Join Rule:**
    If two (or more) tables being joined can each contain multiple rows for the same logical entity (identified by a shared key such as `employee_id`, `order_id`, or `project_id`):

    1. Before joining collapse each table to one row per key using a CTE.
    2. Pick the collapse method that matches the metric:
        - `GROUP BY <key>` + aggregate (`SUM`, `MIN`, `MAX`, `AVG`, `COUNT`) when you must combine numeric values.
        - `SELECT DISTINCT <key>` when you only need a unique list (no numeric roll-up).
    3. Join the CTEs on the key and perform the final calculation.
    ```

## **Tier 2 – Content Logic (Abstract Requirements)**

1. **Atomicity**
    - The rule must be atomic, expressing only one distinct concept or instruction. It can consist of multiple steps, but must have one concrete goal.

2. **Clarity and Specificity**
    - The rule must be clear, direct, and actionable, with precise syntax or formulas.
    - The rule must not be a vague goal like “write efficient queries.”

    5a. **Explicit Definitions**
    - The rule must explicitly define all **client-specific business concepts** that can't be understood without context (e.g., “active user,” “eligible revenue,” “Tier-2 partner”) using precise SQL logic or references to database schema.
    - Explicit references to database elements (e.g. "COLNAME column", "TotalBudget table") **do not** require additional explanations.
    - **Do not** require definitions for:
        - Common technical or general-language terms with widely understood meanings (e.g., “abbreviation,” “special characters,” “date,” “string length”).
        - Natural-language phrases describing a user’s question intent (e.g., *“When asked about total budget”*). These are surface-level triggers and do not require SQL explanations.
    - The rule may assume knowledge of SQL syntax and common data concepts, but not client-specific institutional knowledge.

    5b. **Contextual Sufficiency**
    - The rule must provide sufficient context and relevant examples when needed, so the intended meaning and required action(s) are fully clear.
