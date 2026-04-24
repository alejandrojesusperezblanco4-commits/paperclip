"""Agente: ad_spy — DiscontrolDrops (Shopify Dropshipping). En construcción."""
import os, sys
sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent.parent))
from api_client import post_issue_result, post_issue_comment, resolve_issue_context
sys.stdout.reconfigure(encoding="utf-8")

def main():
    resolve_issue_context()
    post_issue_comment("🔧 ad_spy — En construcción.")
    post_issue_result("# ad_spy\nEste agente está pendiente de implementación.")

if __name__ == "__main__":
    main()
