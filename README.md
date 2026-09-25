# NetSage AI

### AI-Assisted Network Diagnostic Platform

NetSage AI is an AI-assisted network troubleshooting platform designed to help
identify and diagnose common networking problems in Cisco Packet Tracer and
networking lab environments.

The system combines rule-based network analysis with AI-powered diagnostic
reasoning and a Human-in-the-Loop review process.

---

## Overview

Network troubleshooting often requires analyzing symptoms, topology information,
Cisco `show` command outputs, and configuration details to identify the actual
root cause of a problem.

NetSage AI provides a structured workflow that helps analyze these inputs and
generate troubleshooting recommendations.

The platform combines:

- Deterministic rule-based network checks
- LLM-based diagnostic reasoning
- Structured diagnostic output
- Human review of AI recommendations
- Audit and review tracking
- Interactive Streamlit dashboard

The goal is to use AI as a **decision-support tool**, while keeping the final
decision with the human reviewer.

---

## Problem Statement

Network troubleshooting can be time-consuming, especially when multiple
configuration issues can produce similar symptoms.

For example, a connectivity problem may be caused by:

- VLAN configuration
- Routing issues
- ACL rules
- NAT configuration
- Interface failures
- Gateway configuration
- Other network configuration errors

NetSage AI attempts to simplify this process by analyzing available network
evidence and presenting possible causes and recommended troubleshooting steps.

---

## How NetSage AI Works

The system follows a multi-stage workflow:

```text
Network Symptoms / Cisco Output
              │
              ▼
      Input / Evidence Analysis
              │
              ▼
   Deterministic Rule Checker
              │
              ▼
       AI Diagnostic Engine
              │
              ▼
     Structured AI Response
              │
              ▼
       Human Review
        ┌─────┼─────┐
        ▼     ▼     ▼
     Accept  Edit  Reject
              │
              ▼
       Review / Audit Data
