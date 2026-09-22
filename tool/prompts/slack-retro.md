Fill the placeholders below from the runner's WIKI_ROOT and SLACK_CHANNEL environment variables. The target project is the current working directory. If a value is missing, send nothing and exit.

Post today's retrospective to Slack, following the `retrospect` skill's steps exactly.

**Write the Slack post itself in Korean.** These instructions are English because you read them; the post is read by the team.

## 1. What happened today — read it

```
python "<WIKI_ROOT>/tool/slack_brief.py" --project . --kind retro
```

It gives today's commits, the size of the changes, and **the list of session
log files touched today**. That last one is step 2's input.

## 2. Count where things went wrong — four kinds

Count corrections, re-entries, partial work and reversals, by the table in the
`retrospect` skill. In the `.jsonl` files step 1 pointed at, a block with
`type=user` that is not a tool result is what a person actually typed.

**Give the counts.** "That happened a lot" is not a retrospective. Then check
whether each one is already a wiki page — if it is written down and was broken
anyway, the problem is not that the sentence is weak but that it is a sentence.
That calls for climbing the ladder, not rewriting the prose.

If a file is large (several MB), do not read it whole; pull out the human
utterances and count those.

## 3. Post it

- Channel: `<SLACK_CHANNEL>`
- Tool: `slack_send_message`

## 4. Put the same body into the channel record

Write the body you posted to Slack into one file (a temporary path such as `.tmp/brief.md`), and put it into the `#retro` channel record with this command. The server does not have to be running.

```
python "<WIKI_ROOT>/tool/chat_post.py" --project . --channel retro --source retro --file <그 파일>
```

## Rules

- **Change no files.** A person picks what becomes a page. This run cannot ask
  with options, so write the candidates under `*제안*` and stop there.
- Do not list what went well. A retrospective's value is in what went wrong.
- Do not propose one page per incident. Something that happened in one
  repository alone usually belongs in that repository's `CLAUDE.md`.
- If nothing went wrong, post one line saying so. Do not go looking for filler.
- Fifteen lines or fewer.
