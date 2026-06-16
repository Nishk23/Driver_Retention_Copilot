from tools.driver_profile_tool import find_driver_by_name, get_driver_profile
from tools.incentive_tool import calculate_retention_options, get_available_incentives
from tools.policy_rag_tool import search_policy
from tools.policy_validator import validate_plan_against_policy
from tools.support_ticket_tool import get_support_tickets, search_support_tickets


TOOLS = {
    "get_driver_profile": get_driver_profile,
    "find_driver_by_name": find_driver_by_name,
    "get_support_tickets": get_support_tickets,
    "search_support_tickets": search_support_tickets,
    "get_available_incentives": get_available_incentives,
    "calculate_retention_options": calculate_retention_options,
    "search_policy": search_policy,
    "validate_plan_against_policy": validate_plan_against_policy,
}


def build_server():
    try:
        from fastmcp import FastMCP
    except ImportError:
        return None

    mcp = FastMCP("driver-retention-copilot")
    for name, func in TOOLS.items():
        mcp.tool(name=name)(func)
    return mcp


def call_tool(name: str, *args, **kwargs):
    """Fallback MCP-ready local interface when FastMCP is not installed."""
    if name not in TOOLS:
        raise ValueError(f"Unknown tool: {name}")
    return TOOLS[name](*args, **kwargs)


server = build_server()


if __name__ == "__main__":
    if server is None:
        print("FastMCP is not installed. Fallback call_tool interface is available for imports.")
    else:
        server.run()
