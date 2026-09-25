"""
HayMagnet Simulated Action Execution Engine & Mock APIs.
Implements simulated/stubbed APIs for external actions:
- Sending customer messages / SMS validation
- Freezing accounts / blocking cards
- Refunding customer transactions
- Updating CRM system tickets
- Closing cases with audit traces
"""

import time
import uuid
from typing import Dict, Any, List

def mock_send_customer_message(customer_id: str, message_text: str) -> Dict[str, Any]:
    """Simulates sending an SMS/Email validation or warning message to an account owner."""
    msg_id = f"MSG-{uuid.uuid4().hex[:8].upper()}"
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    return {
        "action": "send_customer_message",
        "status": "delivered",
        "message_id": msg_id,
        "customer_id": customer_id,
        "message_text": message_text,
        "timestamp": timestamp,
        "channel": "SMS_PUSH"
    }

def mock_freeze_account(account_id: str, reason: str) -> Dict[str, Any]:
    """Simulates freezing an account in the core banking system."""
    act_id = f"ACT-FREEZE-{uuid.uuid4().hex[:6].upper()}"
    return {
        "action": "freeze_account",
        "status": "account_frozen",
        "account_id": account_id,
        "action_id": act_id,
        "reason": reason,
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
    }

def mock_block_card(card_id: str, reason: str) -> Dict[str, Any]:
    """Simulates blocking a credit/debit card on the payment gateway."""
    act_id = f"ACT-BLOCK-{uuid.uuid4().hex[:6].upper()}"
    return {
        "action": "block_card",
        "status": "card_blocked",
        "card_id": card_id,
        "action_id": act_id,
        "reason": reason,
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
    }

def mock_refund_customer(transaction_id: str, amount_usd: float) -> Dict[str, Any]:
    """Simulates issuing a chargeback / fraud refund to a customer account."""
    ref_id = f"REF-{uuid.uuid4().hex[:8].upper()}"
    return {
        "action": "refund_customer",
        "status": "refund_processed",
        "transaction_id": transaction_id,
        "refund_amount_usd": amount_usd,
        "refund_id": ref_id,
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
    }

def mock_update_crm_system(customer_id: str, note: str) -> Dict[str, Any]:
    """Simulates creating an audit ticket in Salesforce/Zendesk CRM."""
    ticket_id = f"CRM-TICK-{uuid.uuid4().hex[:6].upper()}"
    return {
        "action": "update_crm_system",
        "status": "ticket_created",
        "customer_id": customer_id,
        "ticket_id": ticket_id,
        "note": note,
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
    }

def mock_close_case(case_id: str, verdict: str) -> Dict[str, Any]:
    """Simulates updating the case status in the fraud operations hub."""
    return {
        "action": "close_case",
        "status": "closed",
        "case_id": case_id,
        "verdict": verdict,
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
    }

def execute_simulated_actions(case_id: str, actions: List[Dict[str, str]], customer_id: str = "CUST-001") -> List[Dict[str, Any]]:
    """Executes a list of policy-approved actions through simulated mock APIs."""
    execution_logs = []
    for item in actions:
        act_name = item.get("action", "")
        reason = item.get("reason", "Policy rule trigger")
        
        if "BLOCK_CARD" in act_name:
            execution_logs.append(mock_block_card(f"CARD-{case_id}", reason))
        elif "FREEZE" in act_name or "BLOCK_ACCOUNT" in act_name:
            execution_logs.append(mock_freeze_account(f"ACC-{case_id}", reason))
        elif "WARN_CUSTOMER" in act_name or "VERIFY" in act_name:
            execution_logs.append(mock_send_customer_message(customer_id, f"Security alert: Please confirm recent activity on case {case_id}."))
        elif "REFUND" in act_name:
            execution_logs.append(mock_refund_customer(case_id, 100.0))
        elif "CRM" in act_name or "REPORT" in act_name:
            execution_logs.append(mock_update_crm_system(customer_id, f"Case {case_id} processed with action {act_name}."))
        
    execution_logs.append(mock_close_case(case_id, "investigation_completed"))
    return execution_logs
