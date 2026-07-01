import os
import sqlite3
import pandas as pd
import json

# Paths
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
DB_PATH = os.path.join(BASE_DIR, "olist.db")
OUTPUT_JSON = os.path.join(BASE_DIR, "cohort_data.json")

def load_data_to_sqlite():
    print("Ingesting Olist CSV files into SQLite database...")
    conn = sqlite3.connect(DB_PATH)
    
    csv_files = {
        "olist_customers_dataset": "olist_customers_dataset.csv",
        "olist_orders_dataset": "olist_orders_dataset.csv",
        "olist_order_items_dataset": "olist_order_items_dataset.csv",
        "olist_order_payments_dataset": "olist_order_payments_dataset.csv",
        "olist_products_dataset": "olist_products_dataset.csv",
        "product_category_name_translation": "product_category_name_translation.csv"
    }
    
    for table_name, file_name in csv_files.items():
        file_path = os.path.join(DATA_DIR, file_name)
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Required file {file_name} not found in data directory.")
        
        print(f"Loading {file_name} into table '{table_name}'...")
        # Read in chunks to prevent memory overhead
        chunksize = 20000
        for i, chunk in enumerate(pd.read_csv(file_path, chunksize=chunksize)):
            if i == 0:
                chunk.to_sql(table_name, conn, if_exists="replace", index=False)
            else:
                chunk.to_sql(table_name, conn, if_exists="append", index=False)
                
    # Create indexes for speed
    print("Creating indexes on SQLite database...")
    cursor = conn.cursor()
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_cust_unique ON olist_customers_dataset (customer_id, customer_unique_id);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_orders_cust ON olist_orders_dataset (customer_id, order_id);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_items_order ON olist_order_items_dataset (order_id, product_id);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_payments_order ON olist_order_payments_dataset (order_id);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_products_id ON olist_products_dataset (product_id, product_category_name);")
    conn.commit()
    
    print("Ingestion complete.\n")
    conn.close()

def run_cohort_analysis():
    print("Starting cohort and retention analysis SQL queries...")
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # 1. Create helper tables for cohort analyses
    # Temp customer_orders mapping customer_unique_id and dates
    cursor.execute("DROP TABLE IF EXISTS customer_orders;")
    cursor.execute("""
        CREATE TABLE customer_orders AS
        SELECT
            c.customer_unique_id,
            o.order_id,
            strftime('%Y-%m', o.order_purchase_timestamp) AS order_month,
            o.order_purchase_timestamp,
            c.customer_state,
            c.customer_city
        FROM olist_orders_dataset o
        JOIN olist_customers_dataset c ON o.customer_id = c.customer_id
        WHERE o.order_status NOT IN ('canceled', 'unavailable');
    """)
    
    # Temp customer_cohorts mapping first purchase month
    cursor.execute("DROP TABLE IF EXISTS customer_cohorts;")
    cursor.execute("""
        CREATE TABLE customer_cohorts AS
        SELECT
            customer_unique_id,
            MIN(order_month) AS cohort_month
        FROM customer_orders
        GROUP BY customer_unique_id;
    """)
    conn.commit()
    
    # 2. Query Retention Matrix
    print("Executing retention matrix SQL query...")
    retention_query = """
        WITH cohort_sizes AS (
            SELECT cohort_month, COUNT(DISTINCT customer_unique_id) as cohort_size
            FROM customer_cohorts
            GROUP BY cohort_month
        ),
        order_cohort_indices AS (
            SELECT
                o.customer_unique_id,
                co.cohort_month,
                o.order_month,
                (cast(substr(o.order_month, 1, 4) as integer) - cast(substr(co.cohort_month, 1, 4) as integer)) * 12 +
                (cast(substr(o.order_month, 6, 2) as integer) - cast(substr(co.cohort_month, 6, 2) as integer)) AS cohort_index
            FROM customer_orders o
            JOIN customer_cohorts co ON o.customer_unique_id = co.customer_unique_id
        )
        SELECT
            oci.cohort_month,
            cs.cohort_size,
            oci.cohort_index,
            COUNT(DISTINCT oci.customer_unique_id) AS active_customers
        FROM order_cohort_indices oci
        JOIN cohort_sizes cs ON oci.cohort_month = cs.cohort_month
        WHERE oci.cohort_index >= 0
        GROUP BY oci.cohort_month, oci.cohort_index
        ORDER BY oci.cohort_month, oci.cohort_index;
    """
    df_retention = pd.read_sql_query(retention_query, conn)
    
    # 3. Query Financial Cohorts (Revenue, AOV, Cumulative Spend per Customer)
    print("Executing financial metrics SQL query...")
    financials_query = """
        WITH cohort_sizes AS (
            SELECT cohort_month, COUNT(DISTINCT customer_unique_id) as cohort_size
            FROM customer_cohorts
            GROUP BY cohort_month
        ),
        order_payments AS (
            SELECT order_id, SUM(payment_value) as order_payment_val
            FROM olist_order_payments_dataset
            GROUP BY order_id
        ),
        order_financial_indices AS (
            SELECT
                o.customer_unique_id,
                o.order_id,
                co.cohort_month,
                o.order_month,
                p.order_payment_val,
                (cast(substr(o.order_month, 1, 4) as integer) - cast(substr(co.cohort_month, 1, 4) as integer)) * 12 +
                (cast(substr(o.order_month, 6, 2) as integer) - cast(substr(co.cohort_month, 6, 2) as integer)) AS cohort_index
            FROM customer_orders o
            JOIN customer_cohorts co ON o.customer_unique_id = co.customer_unique_id
            JOIN order_payments p ON o.order_id = p.order_id
        )
        SELECT
            ofi.cohort_month,
            cs.cohort_size,
            ofi.cohort_index,
            SUM(ofi.order_payment_val) as total_revenue,
            AVG(ofi.order_payment_val) as avg_order_value,
            COUNT(ofi.order_id) as total_orders
        FROM order_financial_indices ofi
        JOIN cohort_sizes cs ON ofi.cohort_month = cs.cohort_month
        WHERE ofi.cohort_index >= 0
        GROUP BY ofi.cohort_month, ofi.cohort_index
        ORDER BY ofi.cohort_month, ofi.cohort_index;
    """
    df_financials = pd.read_sql_query(financials_query, conn)

    # 4. Query Geographic Insights
    print("Executing geographic distribution SQL query...")
    geo_query = """
        SELECT
            customer_state as state,
            COUNT(DISTINCT customer_unique_id) as total_customers,
            SUM(payment_value) as state_revenue
        FROM customer_orders o
        JOIN olist_order_payments_dataset p ON o.order_id = p.order_id
        GROUP BY state
        ORDER BY total_customers DESC
        LIMIT 10;
    """
    df_geo = pd.read_sql_query(geo_query, conn)

    # 5. Query Category Insights
    print("Executing category metrics SQL query...")
    category_query = """
        SELECT
            COALESCE(t.product_category_name_english, p.product_category_name) as category,
            COUNT(DISTINCT o.customer_unique_id) as repeat_customers,
            COUNT(o.order_id) as total_orders,
            SUM(i.price) as total_sales
        FROM olist_order_items_dataset i
        JOIN customer_orders o ON i.order_id = o.order_id
        JOIN olist_products_dataset p ON i.product_id = p.product_id
        LEFT JOIN product_category_name_translation t ON p.product_category_name = t.product_category_name
        GROUP BY category
        ORDER BY repeat_customers DESC
        LIMIT 10;
    """
    df_category = pd.read_sql_query(category_query, conn)
    
    # 6. Overall Monthly KPI Trends
    print("Executing monthly KPI trends query...")
    trends_query = """
        SELECT
            order_month,
            COUNT(DISTINCT customer_unique_id) as active_customers,
            COUNT(order_id) as total_orders,
            (SELECT SUM(payment_value) FROM olist_order_payments_dataset p WHERE p.order_id = o.order_id) as monthly_revenue
        FROM customer_orders o
        GROUP BY order_month
        ORDER BY order_month;
    """
    # Summing manually in pandas or subquery
    trends_query = """
        SELECT
            o.order_month,
            COUNT(DISTINCT o.customer_unique_id) as active_customers,
            COUNT(o.order_id) as total_orders,
            SUM(p.payment_value) as monthly_revenue
        FROM customer_orders o
        JOIN olist_order_payments_dataset p ON o.order_id = p.order_id
        GROUP BY o.order_month
        ORDER BY o.order_month;
    """
    df_trends = pd.read_sql_query(trends_query, conn)
    
    # Process Cohorts into clean structured output
    print("Formatting cohort matrices...")
    cohort_data = process_cohort_data(df_retention, df_financials, df_geo, df_category, df_trends)
    
    # Write to JSON
    with open(OUTPUT_JSON, "w") as f:
        json.dump(cohort_data, f, indent=4)
        
    print(f"Cohort calculations completed and exported to {OUTPUT_JSON}!\n")
    conn.close()

def process_cohort_data(df_ret, df_fin, df_geo, df_cat, df_trends):
    # Convert retention and financial data into dictionaries indexed by Cohort Month
    cohorts_dict = {}
    
    # Retention processing
    for _, row in df_ret.iterrows():
        month = row['cohort_month']
        size = int(row['cohort_size'])
        idx = int(row['cohort_index'])
        active = int(row['active_customers'])
        
        if month not in cohorts_dict:
            cohorts_dict[month] = {
                "cohort_month": month,
                "cohort_size": size,
                "retention": {},
                "revenue": {},
                "orders": {},
                "aov": {}
            }
        
        # Store percentage and count
        cohorts_dict[month]["retention"][idx] = {
            "count": active,
            "percentage": round((active / size) * 100, 2)
        }
        
    # Financial processing
    for _, row in df_fin.iterrows():
        month = row['cohort_month']
        idx = int(row['cohort_index'])
        rev = float(row['total_revenue'])
        orders = int(row['total_orders'])
        aov = float(row['avg_order_value'])
        
        if month in cohorts_dict:
            cohorts_dict[month]["revenue"][idx] = round(rev, 2)
            cohorts_dict[month]["orders"][idx] = orders
            cohorts_dict[month]["aov"][idx] = round(aov, 2)

    # Sort cohorts by month name
    sorted_cohorts = [cohorts_dict[m] for m in sorted(cohorts_dict.keys())]

    # Overall KPIs
    total_unique_customers = int(df_ret['cohort_size'].sum()) if not df_ret.empty else 0
    # Weighted average retention for Month 1 (first repeat purchase month)
    m1_active = 0
    m1_cohort_total_size = 0
    for c in sorted_cohorts:
        if 1 in c["retention"]:
            m1_active += c["retention"][1]["count"]
            m1_cohort_total_size += c["cohort_size"]
    
    avg_m1_retention = round((m1_active / m1_cohort_total_size) * 100, 2) if m1_cohort_total_size > 0 else 0.0
    
    # Total overall metrics
    total_sales = round(df_fin['total_revenue'].sum(), 2) if not df_fin.empty else 0.0
    total_orders = int(df_fin['total_orders'].sum()) if not df_fin.empty else 0
    overall_aov = round(total_sales / total_orders, 2) if total_orders > 0 else 0.0

    return {
        "kpis": {
            "total_customers": total_unique_customers,
            "avg_month_1_retention": avg_m1_retention,
            "total_revenue": total_sales,
            "overall_aov": overall_aov,
            "total_orders": total_orders
        },
        "cohorts": sorted_cohorts,
        "geo_distribution": df_geo.to_dict(orient="records"),
        "category_performance": df_cat.to_dict(orient="records"),
        "monthly_trends": df_trends.to_dict(orient="records")
    }

if __name__ == "__main__":
    load_data_to_sqlite()
    run_cohort_analysis()
