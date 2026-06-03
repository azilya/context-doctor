## **Evaluation Criteria for Text-to-SQL Rules**

### Tier 1 – Structural Form (Concrete Requirements)

1. **Rule Structure and Keyword Usage**
    - Every rule must follow the **Predicate-First structure**:
        *WHEN <condition>, THEN <action>* (or equivalent *IF… THEN*)
        OR
        *ALWAYS/NEVER <action>*
    - The rule must use the prescribed **structural keywords** to enforce clarity and consistency: `WHEN`, `IF`, `THEN`, `ALWAYS`, `NEVER` (uppercase or lowercase).
    - The rule must not substitute these with alternative or weaker expressions (e.g., “whenever,” “sometimes,” “maybe”).

2. **Strength and Framing**
    - The rule must use direct, positive, and unambiguous wording.
    - Avoid hedging or weak phrasing (e.g., “you should probably,” “it would be good to”).
    - Express actions in positive form whenever possible (e.g., *“ALWAYS use `product_display_name`”* instead of *“Do not use `product_id`”*).
    - The only acceptable negative forms are strong, categorical prohibitions such as `NEVER` or `MUST NOT`.

3. **Formatting for Complex Rules**
    - If the rule describes a multi-step or complex (involving several actions) instruction, it must be broken into paragraphs, a list, or structured format (e.g., `Trigger`, `Action`, `Calculation`).
    - Each step or action of a complex instruction must be presented as a new paragraph, list item, or part of a titled section.

    Example 1:

    ```
    When user asks about budget or income always use v_tb_ForwardingBudget table.

    Trigger - When asked about "income" or "budget".
    Action - Query the v_tb_ForwardingBudget table. Always apply the filter WHERE RecordType = 'ATA’.
    Calculation
    - To find the budget, calculate SUM(ExpectedIncome).
    - To find the income, calculate SUM(Income).
    ```

    Example 2:

    ```
    **Global M : N Safety Rule:**
    If two (or more) tables being joined can each contain multiple rows for the same logical entity (identified by a shared key such as `employee_id`, `order_id`, or `project_id`):

    1. Before joining collapse each table to one row per key using a CTE.
    2. Pick the collapse method that matches the metric:
        - `GROUP BY <key>` + aggregate (`SUM`, `MIN`, `MAX`, `AVG`, `COUNT`) when you must combine numeric values.
        - `SELECT DISTINCT <key>` when you only need a unique list (no numeric roll-up).
    3. Join the CTEs on the key and perform the final calculation.
    ```

### **Tier 2 – Content Logic (Abstract Requirements)**

4. **Atomicity**
    - The rule must be atomic, expressing only one distinct concept or instruction.

5. **Clarity and Specificity**
    - The rule must be clear, direct, and actionable, with precise syntax or formulas.
    - The rule must not be a vague goal like “write efficient queries.”

    5a. **Explicit Definitions**
    - The rule must explicitly define all **client-specific business concepts** that can't be understood without context (e.g., “active user,” “eligible revenue,” “Tier-2 partner”) using precise SQL logic or references to database schema.
    - Explicit references to database elements (e.g. "EBELN column", "v_tb_ForwardingBudget table") **do not** require additional explanations.
    - **Do not** require definitions for:
        - Common technical or general-language terms with widely understood meanings (e.g., “abbreviation,” “special characters,” “date,” “string length”).
        - Natural-language phrases describing a user’s question intent (e.g., *“When asked about total budget”*). These are surface-level triggers and do not require SQL explanations.
    - The rule may assume knowledge of SQL syntax and common data concepts, but not client-specific institutional knowledge.

    5b. **Contextual Sufficiency**
    - The rule must provide sufficient context and relevant examples when needed, so the intended meaning and required action(s) are fully clear.
