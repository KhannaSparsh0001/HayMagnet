import os
import pyTigerGraph as tg
from dotenv import load_dotenv

# Load credentials from .env
load_dotenv()

TG_HOST = os.getenv("TG_HOST")
TG_SECRET = os.getenv("TG_SECRET")

print(f"Connecting to TigerGraph at {TG_HOST} using Secret...")

# Initialize connection by passing the secret directly to the constructor
conn = tg.TigerGraphConnection(host=TG_HOST, gsqlSecret=TG_SECRET)
token_response = conn.getToken(TG_SECRET)
conn.apiToken = token_response[0] if isinstance(token_response, tuple) else token_response

schema_gsql = '''
USE GLOBAL

# Create Vertices
CREATE VERTEX Customer (PRIMARY_ID customer_id STRING) WITH primary_id_as_attribute="true"
CREATE VERTEX Card (PRIMARY_ID card_id STRING) WITH primary_id_as_attribute="true"
CREATE VERTEX Transaction (PRIMARY_ID transaction_id STRING, risk_score FLOAT, ts DATETIME, amount FLOAT, channel STRING) WITH primary_id_as_attribute="true"
CREATE VERTEX DeviceProfile (PRIMARY_ID device_id STRING) WITH primary_id_as_attribute="true"
CREATE VERTEX EmailDomain (PRIMARY_ID email STRING) WITH primary_id_as_attribute="true"
CREATE VERTEX BillingRegion (PRIMARY_ID region_code STRING) WITH primary_id_as_attribute="true"
CREATE VERTEX ClosedCase (PRIMARY_ID case_id STRING, outcome STRING, pattern STRING, exposure_usd FLOAT) WITH primary_id_as_attribute="true"

# Create Edges
CREATE DIRECTED EDGE OWNS (FROM Customer, TO Card)
CREATE DIRECTED EDGE MADE (FROM Card, TO Transaction)
CREATE DIRECTED EDGE FROM_DEVICE (FROM Transaction, TO DeviceProfile)
CREATE DIRECTED EDGE PURCHASER_EMAIL (FROM Transaction, TO EmailDomain)
CREATE DIRECTED EDGE BILLED_IN (FROM Transaction, TO BillingRegion)
CREATE DIRECTED EDGE NEXT_TXN (FROM Transaction, TO Transaction)
CREATE DIRECTED EDGE INVOLVES (FROM ClosedCase, TO Transaction)
CREATE DIRECTED EDGE ON_CARD (FROM ClosedCase, TO Card)
CREATE DIRECTED EDGE CONNECTED_TO (FROM ClosedCase, TO Card)

# Create Graph
CREATE GRAPH FraudGraph(Customer, Card, Transaction, DeviceProfile, EmailDomain, BillingRegion, ClosedCase, OWNS, MADE, FROM_DEVICE, PURCHASER_EMAIL, BILLED_IN, NEXT_TXN, INVOLVES, ON_CARD, CONNECTED_TO)
'''

print("Executing Schema Creation (this might take a minute)...")
result = conn.gsql(schema_gsql)
print(result)
print("Schema creation complete!")
