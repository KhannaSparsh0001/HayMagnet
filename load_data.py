import os
import pandas as pd
import pyTigerGraph as tg
from dotenv import load_dotenv

load_dotenv()
TG_HOST = os.getenv("TG_HOST")
TG_SECRET = os.getenv("TG_SECRET")

print("Initializing TigerGraph connection...")
conn = tg.TigerGraphConnection(host=TG_HOST, graphname="FraudGraph", gsqlSecret=TG_SECRET)
conn.apiToken = conn.getToken(TG_SECRET)[0] if isinstance(conn.getToken(TG_SECRET), tuple) else conn.getToken(TG_SECRET)

DATA_DIR = "HHGOA_IEEE"

def load_transactions_and_cards():
    print("Loading Transactions, Customers, and Cards (in chunks due to size)...")
    chunk_size = 50000
    for i, raw_chunk in enumerate(pd.read_csv(f"{DATA_DIR}/transactions.csv", chunksize=chunk_size)):
        print(f"Processing transaction chunk {i+1}...")
        chunk = raw_chunk.copy()
        
        # Cast IDs to strings to prevent REST-30200 errors (TigerGraph expects STRING for these)
        chunk['TransactionID'] = chunk['TransactionID'].astype(str)
        chunk['customer_id'] = chunk['customer_id'].astype(str)
        
        # We need to construct card_id since it's not explicitly in the CSV but required by the cases
        # The README implies card IDs look like {customer_id}-K{index}, but without explicit mapping,
        # we will use the unique combination of customer_id and card1 to represent the card.
        # Actually, let's just map it as a generic string for now, or use a simple `{customer_id}-K1` 
        # fallback for simplicity if we can't perfectly reconstruct the Vesta hashing.
        # We'll use `{customer_id}-{card1}` as a reliable unique proxy.
        chunk['card_id'] = chunk['customer_id'].astype(str) + "-" + chunk['card1'].astype(str)
        
        # 1. Upsert Customers
        customers = chunk[['customer_id']].drop_duplicates()
        conn.upsertVertexDataFrame(df=customers, vertexType='Customer', v_id='customer_id', attributes={'customer_id': 'customer_id'})
        
        # 2. Upsert Cards
        cards = chunk[['card_id']].drop_duplicates()
        conn.upsertVertexDataFrame(df=cards, vertexType='Card', v_id='card_id', attributes={'card_id': 'card_id'})
        
        # 3. Upsert Transactions
        txns = chunk[['TransactionID', 'risk_score', 'ts', 'TransactionAmt', 'channel']].rename(
            columns={'TransactionAmt': 'amount'}
        )
        txns['risk_score'] = txns['risk_score'].fillna(0.0)
        conn.upsertVertexDataFrame(df=txns, vertexType='Transaction', v_id='TransactionID', attributes={'transaction_id': 'TransactionID', 'risk_score': 'risk_score', 'ts': 'ts', 'amount': 'amount', 'channel': 'channel'})
        
        # 4. Upsert Edges (OWNS, MADE)
        owns = chunk[['customer_id', 'card_id']].drop_duplicates()
        conn.upsertEdgeDataFrame(df=owns, sourceVertexType='Customer', edgeType='OWNS', targetVertexType='Card', from_id='customer_id', to_id='card_id', attributes={})
        
        made = chunk[['card_id', 'TransactionID']]
        conn.upsertEdgeDataFrame(df=made, sourceVertexType='Card', edgeType='MADE', targetVertexType='Transaction', from_id='card_id', to_id='TransactionID', attributes={})
        
        # 5. Billing Region
        if 'addr1' in chunk.columns:
            chunk['addr1'] = chunk['addr1'].astype(str)
            regions = chunk[['addr1']].dropna().drop_duplicates()
            conn.upsertVertexDataFrame(df=regions, vertexType='BillingRegion', v_id='addr1', attributes={'region_code': 'addr1'})
            billed_in = chunk[['TransactionID', 'addr1']].dropna()
            conn.upsertEdgeDataFrame(df=billed_in, sourceVertexType='Transaction', edgeType='BILLED_IN', targetVertexType='BillingRegion', from_id='TransactionID', to_id='addr1', attributes={})

def load_identities():
    print("Loading Identities...")
    df = pd.read_csv(f"{DATA_DIR}/identity.csv")
    df['TransactionID'] = df['TransactionID'].astype(str)
    df['DeviceInfo'] = df['DeviceInfo'].astype(str)
    
    # Device profiles (using DeviceInfo as a proxy for the profile ID as per the schema)
    devices = df[['DeviceInfo']].dropna().drop_duplicates()
    conn.upsertVertexDataFrame(df=devices, vertexType='DeviceProfile', v_id='DeviceInfo', attributes={'device_id': 'DeviceInfo'})
    
    # Edge: Transaction -> DeviceProfile
    from_device = df[['TransactionID', 'DeviceInfo']].dropna()
    conn.upsertEdgeDataFrame(df=from_device, sourceVertexType='Transaction', edgeType='FROM_DEVICE', targetVertexType='DeviceProfile', from_id='TransactionID', to_id='DeviceInfo', attributes={})

def load_closed_cases():
    print("Loading Closed Cases...")
    df = pd.read_csv(f"{DATA_DIR}/closed_cases_history.csv")
    df['case_id'] = df['case_id'].astype(str)
    df['card_id'] = df['card_id'].astype(str)
    
    # Vertices
    cases = df[['case_id', 'outcome', 'pattern', 'exposure_usd']]
    conn.upsertVertexDataFrame(df=cases, vertexType='ClosedCase', v_id='case_id', attributes={'case_id': 'case_id', 'outcome': 'outcome', 'pattern': 'pattern', 'exposure_usd': 'exposure_usd'})
    
    # Edges: CONNECTED_TO Card
    connected = df[['case_id', 'card_id']].dropna()
    conn.upsertEdgeDataFrame(df=connected, sourceVertexType='ClosedCase', edgeType='CONNECTED_TO', targetVertexType='Card', from_id='case_id', to_id='card_id', attributes={})

if __name__ == "__main__":
    load_transactions_and_cards()
    load_identities()
    load_closed_cases()
    print("Data ingestion complete!")
