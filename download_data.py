import os
import urllib.request
import time

# Directory settings
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")

# Create data directory if not exists
os.makedirs(DATA_DIR, exist_ok=True)

# Dataset URLs from public mirror
FILES_TO_DOWNLOAD = {
    "olist_customers_dataset.csv": "https://raw.githubusercontent.com/vishalkirtaniya/e-com-data-analysis/main/olist_customers_dataset.csv",
    "olist_orders_dataset.csv": "https://raw.githubusercontent.com/vishalkirtaniya/e-com-data-analysis/main/olist_orders_dataset.csv",
    "olist_order_items_dataset.csv": "https://raw.githubusercontent.com/vishalkirtaniya/e-com-data-analysis/main/olist_order_items_dataset.csv",
    "olist_order_payments_dataset.csv": "https://raw.githubusercontent.com/vishalkirtaniya/e-com-data-analysis/main/olist_order_payments_dataset.csv",
    "olist_products_dataset.csv": "https://raw.githubusercontent.com/vishalkirtaniya/e-com-data-analysis/main/olist_products_dataset.csv",
    "product_category_name_translation.csv": "https://raw.githubusercontent.com/vishalkirtaniya/e-com-data-analysis/main/product_category_name_translation.csv"
}

def download_file(file_name, url):
    target_path = os.path.join(DATA_DIR, file_name)
    print(f"Downloading {file_name}...")
    start_time = time.time()
    
    try:
        # User-agent header to avoid blocked requests
        req = urllib.request.Request(
            url, 
            headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
        )
        with urllib.request.urlopen(req) as response, open(target_path, 'wb') as out_file:
            # Buffer reading
            block_size = 1024 * 256  # 256KB blocks
            downloaded = 0
            while True:
                buffer = response.read(block_size)
                if not buffer:
                    break
                downloaded += len(buffer)
                out_file.write(buffer)
                
        elapsed = time.time() - start_time
        print(f"Successfully downloaded {file_name} ({downloaded / (1024 * 1024):.2f} MB) in {elapsed:.2f} seconds.\n")
    except Exception as e:
        print(f"Error downloading {file_name}: {e}")
        if os.path.exists(target_path):
            os.remove(target_path)
        raise e

if __name__ == "__main__":
    print("Starting Olist dataset download pipeline...\n")
    for file_name, url in FILES_TO_DOWNLOAD.items():
        download_file(file_name, url)
    print("All files downloaded successfully and stored in project data/ directory!")
