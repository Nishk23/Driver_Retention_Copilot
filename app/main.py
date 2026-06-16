import argparse

from graph.workflow import run_copilot
from state.memory import load_memory, save_memory, update_memory


DEMO_QUERY = (
    "Driver Maria D-456 just called. She waited in the airport queue for two hours only to be given "
    "a 1.5km trip. She's furious as this has happened multiple times. How do we handle this?"
)


def run_once(query: str, session_id: str | None) -> dict:
    memory = load_memory(session_id)
    result = run_copilot(query, conversation_memory=memory)
    save_memory(session_id, update_memory(memory, result))
    print(result.get("final_answer") or "No final answer generated.")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Driver Retention Copilot CLI")
    parser.add_argument("--query", help="Manager query to analyze.")
    parser.add_argument("--session-id", default="default", help="Session ID for persisted memory.")
    parser.add_argument("--interactive", action="store_true", help="Run an interactive multi-turn CLI.")
    parser.add_argument("--demo", action="store_true", help="Run the Maria demo query.")
    args = parser.parse_args()

    if args.interactive:
        print("Driver Retention Copilot interactive mode. Type 'exit' to quit.")
        while True:
            query = input("> ").strip()
            if query.lower() in {"exit", "quit"}:
                break
            if query:
                run_once(query, args.session_id)
        return

    query = args.query or (DEMO_QUERY if args.demo else None)
    if not query:
        parser.error("Provide --query, --demo, or --interactive.")
    run_once(query, args.session_id)


if __name__ == "__main__":
    main()
