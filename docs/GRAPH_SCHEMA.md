# TigerGraph Schema Specification (`FraudGraph`)

The HayMagnet knowledge graph is provisioned in TigerGraph Cloud under the graph name **`FraudGraph`**.

---

## 1. Vertex Definitions

| Vertex Type | Primary ID | Attributes | Description |
| :--- | :--- | :--- | :--- |
| **`Customer`** | `customer_id` (`STRING`) | `customer_id` (`STRING`) | Account holder entity. |
| **`Card`** | `card_id` (`STRING`) | `card_id` (`STRING`) | Credit/debit card used for transactions. |
| **`Transaction`** | `transaction_id` (`STRING`) | `risk_score` (`FLOAT`), `ts` (`DATETIME`), `amount` (`FLOAT`), `channel` (`STRING`) | Individual financial transaction event. |
| **`DeviceProfile`** | `device_id` (`STRING`) | `device_id` (`STRING`) | Device fingerprint or hardware info (from `DeviceInfo`). |
| **`EmailDomain`** | `email` (`STRING`) | `email` (`STRING`) | Purchaser or account email domain. |
| **`BillingRegion`** | `region_code` (`STRING`) | `region_code` (`STRING`) | Geographical billing region code (`addr1`). |
| **`ClosedCase`** | `case_id` (`STRING`) | `case_id` (`STRING`), `outcome` (`STRING`), `pattern` (`STRING`), `exposure_usd` (`FLOAT`) | Historical resolved investigation case. |

---

## 2. Edge Relationships

```text
 (Customer) -------[ OWNS ]-------> (Card)
                                      |
                                  [ MADE ]
                                      |
                                      v
                              (Transaction)
                             /      |      \
              [ FROM_DEVICE ]  [ BILLED_IN ]  [ PURCHASER_EMAIL ]
                   /                |                \
                  v                 v                 v
          (DeviceProfile)   (BillingRegion)     (EmailDomain)

 (Transaction) -------[ NEXT_TXN ]-------> (Transaction)

 (ClosedCase) -------[ INVOLVES ]-------> (Transaction)
 (ClosedCase) -------[ ON_CARD ]--------> (Card)
 (ClosedCase) -------[ CONNECTED_TO ]---> (Card)
```

| Edge Type | Source Vertex | Target Vertex | Directed? | Description |
| :--- | :--- | :--- | :--- | :--- |
| **`OWNS`** | `Customer` | `Card` | Directed | Identifies which customer owns a payment card. |
| **`MADE`** | `Card` | `Transaction` | Directed | Associates a card with a transaction. |
| **`FROM_DEVICE`** | `Transaction` | `DeviceProfile` | Directed | Links transaction to device hardware fingerprint. |
| **`PURCHASER_EMAIL`**| `Transaction` | `EmailDomain` | Directed | Links transaction to purchaser email domain. |
| **`BILLED_IN`** | `Transaction` | `BillingRegion` | Directed | Geographic region where billing was authorized. |
| **`NEXT_TXN`** | `Transaction` | `Transaction` | Directed | Chronological sequence between transactions on same account. |
| **`INVOLVES`** | `ClosedCase` | `Transaction` | Directed | Historical investigation tied to a transaction. |
| **`ON_CARD`** | `ClosedCase` | `Card` | Directed | Historical case associated with a card. |
| **`CONNECTED_TO`** | `ClosedCase` | `Card` | Directed | Cross-case entity linkages for syndicates. |

---

## 3. GSQL Schema Declaration

The schema is defined and initialized in `setup_graph.py` as:

```sql
USE GLOBAL

CREATE VERTEX Customer (PRIMARY_ID customer_id STRING) WITH primary_id_as_attribute="true"
CREATE VERTEX Card (PRIMARY_ID card_id STRING) WITH primary_id_as_attribute="true"
CREATE VERTEX Transaction (PRIMARY_ID transaction_id STRING, risk_score FLOAT, ts DATETIME, amount FLOAT, channel STRING) WITH primary_id_as_attribute="true"
CREATE VERTEX DeviceProfile (PRIMARY_ID device_id STRING) WITH primary_id_as_attribute="true"
CREATE VERTEX EmailDomain (PRIMARY_ID email STRING) WITH primary_id_as_attribute="true"
CREATE VERTEX BillingRegion (PRIMARY_ID region_code STRING) WITH primary_id_as_attribute="true"
CREATE VERTEX ClosedCase (PRIMARY_ID case_id STRING, outcome STRING, pattern STRING, exposure_usd FLOAT) WITH primary_id_as_attribute="true"

CREATE DIRECTED EDGE OWNS (FROM Customer, TO Card)
CREATE DIRECTED EDGE MADE (FROM Card, TO Transaction)
CREATE DIRECTED EDGE FROM_DEVICE (FROM Transaction, TO DeviceProfile)
CREATE DIRECTED EDGE PURCHASER_EMAIL (FROM Transaction, TO EmailDomain)
CREATE DIRECTED EDGE BILLED_IN (FROM Transaction, TO BillingRegion)
CREATE DIRECTED EDGE NEXT_TXN (FROM Transaction, TO Transaction)
CREATE DIRECTED EDGE INVOLVES (FROM ClosedCase, TO Transaction)
CREATE DIRECTED EDGE ON_CARD (FROM ClosedCase, TO Card)
CREATE DIRECTED EDGE CONNECTED_TO (FROM ClosedCase, TO Card)

CREATE GRAPH FraudGraph(
  Customer, Card, Transaction, DeviceProfile, EmailDomain, BillingRegion, ClosedCase,
  OWNS, MADE, FROM_DEVICE, PURCHASER_EMAIL, BILLED_IN, NEXT_TXN, INVOLVES, ON_CARD, CONNECTED_TO
)
```

---

## 4. Key Investigation Traversal Queries

### Card Velocity & Device Inspection
```sql
INTERPRET QUERY () FOR GRAPH FraudGraph {
  Cards = {Card.*};
  Txns = SELECT t FROM Cards:c -(MADE:e)-> Transaction:t
         WHERE c.card_id == "TARGET_CARD_ID";
  Devices = SELECT d FROM Txns:t -(FROM_DEVICE:e)-> DeviceProfile:d;
  PRINT Txns, Devices;
}
```

### Syndicate / Shared Device Ring Detection
```sql
INTERPRET QUERY () FOR GRAPH FraudGraph {
  Dev = {DeviceProfile.*};
  Txns = SELECT t FROM Dev:d <-(FROM_DEVICE:e)- Transaction:t
         WHERE d.device_id == "TARGET_DEVICE";
  Cards = SELECT c FROM Txns:t <-(MADE:e)- Card:c;
  PRINT Cards;
}
```
