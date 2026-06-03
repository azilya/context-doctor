Rule #1: ALWAYS join `orders` to `customers` using `orders.customer_id = customers.customer_id` when customer attributes are needed.

Rule #2: WHEN the user asks for revenue, THEN calculate `SUM(orders.revenue)` and do not count rows as revenue.

Rule #3: WHEN the user asks for regional revenue, THEN group by `customers.region` after joining `orders` to `customers`.

Rule #4: ALWAYS filter order-date questions using `orders.order_date`.
