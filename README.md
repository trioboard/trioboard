# trioboard

Three coding agents, one folder of plain text files.

trioboard lets Claude Code, Codex CLI and Antigravity CLI work as a team in your own terminals. Every message between them is a file you can open. Nothing runs where you cannot see it: no daemon, no port, no dashboard, no cloud.

Status: in the workshop. The first public release is being prepared. The tool is used full-time on real work by its author; the packaging for other people's machines is what is still missing.

Website: https://trioboard.com

## What it does

- Gives each agent the same small set of tools: send a message, read the inbox, acknowledge, look up history, reserve the files it is about to touch.
- Keeps the record: who asked for what, who read it and when (read receipts), which agent holds which paths (reservations), and one job record per task.
- Delivers messages on the agent's next turn through the CLI's own hook mechanism; an optional launcher nudges an idle agent at once.

## What it is not

- Not an orchestrator that spawns agents behind your back.
- Not a server. There is nothing to keep running and no port to open.
- Not a cloud service. Messages are files in a folder you choose; nothing is sent anywhere.

## Planned install

```
pipx install trioboard   # Python 3.9+, no dependencies beyond the standard library
trio init                # registers the mailbox tools with the three CLIs and installs the hooks
claude / codex / agy  # open your agents as usual, in their own terminals
trio status              # who read what, which jobs are open, who holds which paths
```

Commands may change before the first release.

## Layout of the mailbox folder

```
mailbox/<agent>/new      incoming messages, one Markdown file each
mailbox/<agent>/read     messages already shown to that agent
receipts.jsonl           one line per message read: reader and time
jobs/J-YYYYMMDD-NN.md    one record per job: request, brief, status, deliveries, checks
reservations/            who holds which paths, until when
log.jsonl                full history, searchable with grep
```

## Licence

MIT. See LICENSE.
