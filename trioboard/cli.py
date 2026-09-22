"""`trio`: the command line for the mailbox, for people and for scripts.

    trio init [--agents claude,codex,agy] [--apply]   create the folder; --apply registers the MCP server with the
                                                       CLIs found on this machine and installs the Claude Code hook
    trio status                                        unread counts, open jobs, reservations
    trio send <to> <subject> <body> [--job J-...] [--ack] [--from AGENT | --owner]
    trio inbox --agent NAME [--keep]
    trio ack <id> [note] --agent NAME
    trio history [--count N] [--job J-...]
    trio search <query>
    trio reserve <path>... --reason TEXT --agent NAME [--minutes N] [--job J-...]
    trio release [<path>...] --agent NAME
    trio reservations
    trio job new <title> [--request TEXT] [--coordinator NAME]
    trio job list
    trio mcp [--agent NAME]                            run the MCP server on stdio (the CLIs call this)
    trio hook <agent> [--format claude|text]           next-turn delivery for hooks

Identity for inbox/ack/reserve comes from --agent or TRIO_AGENT. A human sends as the owner by default.
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from . import __version__
from .store import DEFAULT_AGENTS, OWNER, Store, TrioError


def agent_from(args):
    name = getattr(args, "agent", None) or os.environ.get("TRIO_AGENT", "")
    return name.strip().lower()


def trio_command():
    """The absolute path of this `trio`, so registrations survive PATH differences between shells and CLIs."""
    found = shutil.which("trio")
    if found:
        return os.path.abspath(found)
    return f"{sys.executable} -m trioboard"


def registration_plan(agents, trio):
    """What `trio init --apply` would run: one MCP registration per CLI that exists on this machine."""
    plan = []
    for agent in agents:
        if agent == "claude" and shutil.which("claude"):
            plan.append(("claude", ["claude", "mcp", "add", "--scope", "user", "-e", "TRIO_AGENT=claude", "trioboard", "--"] + trio.split() + ["mcp"]))
        elif agent == "codex" and shutil.which("codex"):
            plan.append(("codex", ["codex", "mcp", "add", "trioboard", "--env", "TRIO_AGENT=codex", "--"] + trio.split() + ["mcp"]))
        elif agent == "agy" and shutil.which("agy"):
            plan.append(("agy", ["agy", "mcp", "add", "-e", "TRIO_AGENT=agy", "trioboard"] + trio.split() + ["mcp"]))
        else:
            plan.append((agent, None))
    return plan


def claude_hook_entry(trio):
    return {"type": "command", "command": f"{trio} hook claude"}


def install_claude_hook(settings_path, trio):
    """Add the inbox hook to Claude Code's settings.json (UserPromptSubmit + PostToolUse), with a backup. Idempotent."""
    settings_path = Path(settings_path)
    data = {}
    if settings_path.exists():
        data = json.loads(settings_path.read_text(encoding="utf-8") or "{}")
        backup = settings_path.with_name(settings_path.name + ".bak-trioboard")
        shutil.copyfile(settings_path, backup)
    hooks = data.setdefault("hooks", {})
    command = claude_hook_entry(trio)["command"]
    changed = False
    for event, matcher in (("UserPromptSubmit", None), ("PostToolUse", "*")):
        groups = hooks.setdefault(event, [])
        present = any(h.get("command") == command for g in groups for h in g.get("hooks", []))
        if not present:
            group = {"hooks": [claude_hook_entry(trio)]}
            if matcher is not None:
                group["matcher"] = matcher
            groups.append(group)
            changed = True
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    settings_path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return changed


def cmd_init(args):
    agents = [a.strip().lower() for a in (args.agents or ",".join(DEFAULT_AGENTS)).split(",") if a.strip()]
    store = Store()
    root = store.init(agents)
    print(f"trioboard folder ready: {root}")
    print(f"agents: {', '.join(store.agents)}")
    trio = trio_command()
    plan = registration_plan(store.agents, trio)
    print("\nMCP registration:")
    for agent, command in plan:
        if command is None:
            print(f"  {agent}: no CLI named '{agent}' on PATH; register by hand: {trio} mcp  (env TRIO_AGENT={agent})")
        elif args.apply:
            result = subprocess.run(command, capture_output=True, text=True)
            status = "ok" if result.returncode == 0 else f"failed ({(result.stderr or result.stdout).strip()[:200]})"
            print(f"  {agent}: {' '.join(command)}  ->  {status}")
        else:
            print(f"  {agent}: {' '.join(command)}")
    settings = Path.home() / ".claude" / "settings.json"
    if "claude" in store.agents:
        if args.apply:
            changed = install_claude_hook(settings, trio)
            print(f"\nClaude Code hook: {'installed' if changed else 'already present'} in {settings} "
                  f"(backup: {settings.name}.bak-trioboard)")
        else:
            print(f"\nClaude Code hook (next-turn delivery): add to {settings}:")
            print(json.dumps({"hooks": {"UserPromptSubmit": [{"hooks": [claude_hook_entry(trio)]}],
                                        "PostToolUse": [{"matcher": "*", "hooks": [claude_hook_entry(trio)]}]}}, indent=2))
    if not args.apply:
        print("\nNothing was changed outside the trioboard folder. Run `trio init --apply` to register and install the hook.")
    else:
        print("\nRestart the CLIs so they pick up the new server. Then ask each agent to call trio_whoami.")
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(prog="trio", description="three coding agents, one folder of plain text files")
    parser.add_argument("--version", "-V", action="version", version=f"trioboard {__version__}")
    sub = parser.add_subparsers(dest="command")

    p = sub.add_parser("init", help="create the folder; --apply registers the MCP server and installs the Claude Code hook")
    p.add_argument("--agents", help="comma-separated agent names (default claude,codex,agy)")
    p.add_argument("--apply", action="store_true", help="run the registrations and write the hook (with backups)")

    sub.add_parser("status", help="unread counts, open jobs, reservations")

    p = sub.add_parser("send", help="send a message")
    p.add_argument("to"); p.add_argument("subject"); p.add_argument("body")
    p.add_argument("--from", dest="sender", help="agent name; default: owner (the human)")
    p.add_argument("--job"); p.add_argument("--importance", choices=["normal", "high", "owner"])
    p.add_argument("--ack", action="store_true")

    p = sub.add_parser("inbox", help="read and mark read"); p.add_argument("--agent"); p.add_argument("--keep", action="store_true")
    p = sub.add_parser("ack", help="acknowledge a message"); p.add_argument("id"); p.add_argument("note", nargs="?", default=""); p.add_argument("--agent")
    p = sub.add_parser("history", help="the shared timeline"); p.add_argument("--count", type=int, default=15); p.add_argument("--job", default="")
    p = sub.add_parser("search", help="search all messages"); p.add_argument("query"); p.add_argument("--count", type=int, default=10)
    p = sub.add_parser("reserve", help="reserve paths"); p.add_argument("paths", nargs="+"); p.add_argument("--minutes", type=int, default=60)
    p.add_argument("--reason", required=True); p.add_argument("--job", default=""); p.add_argument("--agent")
    p = sub.add_parser("release", help="release reservations"); p.add_argument("paths", nargs="*"); p.add_argument("--agent")
    sub.add_parser("reservations", help="list active reservations")

    p = sub.add_parser("job", help="job records"); js = p.add_subparsers(dest="job_command")
    q = js.add_parser("new"); q.add_argument("title"); q.add_argument("--request", default=""); q.add_argument("--coordinator", default="")
    js.add_parser("list")

    p = sub.add_parser("mcp", help="run the MCP server on stdio"); p.add_argument("--agent")
    p = sub.add_parser("hook", help="next-turn delivery for hooks"); p.add_argument("agent"); p.add_argument("--format", choices=["claude", "text"], default="claude")

    args = parser.parse_args(argv)
    if not args.command:
        parser.print_help()
        return 0
    try:
        if args.command == "init":
            return cmd_init(args)
        store = Store()
        if args.command == "status":
            print(store.status())
        elif args.command == "send":
            sender = (args.sender or OWNER).strip().lower()
            importance = args.importance or ("owner" if sender == OWNER else "normal")
            print(store.send(sender, args.to, args.subject, args.body, job=args.job or "", importance=importance, ack=args.ack))
        elif args.command == "inbox":
            print(store.inbox(agent_from(args), keep=args.keep))
        elif args.command == "ack":
            print(store.acknowledge(agent_from(args), args.id, args.note))
        elif args.command == "history":
            print(store.timeline(max(1, min(100, args.count)), job=args.job))
        elif args.command == "search":
            print(store.search(args.query, max(1, min(50, args.count))))
        elif args.command == "reserve":
            print(store.reserve(agent_from(args), args.paths, args.minutes, args.reason, args.job))
        elif args.command == "release":
            print(store.release(agent_from(args), args.paths))
        elif args.command == "reservations":
            print(store.list_reservations())
        elif args.command == "job":
            if args.job_command == "new":
                job = store.new_job(args.title, args.request, args.coordinator)
                print(f"{job}  {store.jobs_dir / (job + '.md')}")
            else:
                jobs = store.open_jobs()
                print("\n".join(f"{j[0]}  {j[1]}  ({j[2]})" for j in jobs) if jobs else "No open jobs.")
        elif args.command == "mcp":
            if args.agent:
                os.environ["TRIO_AGENT"] = args.agent.strip().lower()
            from .server import serve
            serve(store)
        elif args.command == "hook":
            from .hook import main as hook_main
            return hook_main(args.agent.strip().lower(), args.format, store=store)
        return 0
    except TrioError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
