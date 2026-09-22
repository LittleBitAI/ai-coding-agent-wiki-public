Fill the placeholders below from the runner's WIKI_ROOT and SLACK_CHANNEL environment variables. The target project is the current working directory. If a value is missing, send nothing and exit.

Post the weekday morning progress briefing to Slack.

**Write the Slack post itself in Korean.** These instructions are English because you read them; the post is read by the team.

## 1. Take the facts — use this output, do not invent them

```
python "<WIKI_ROOT>/tool/slack_brief.py" --project .
```

It gives the branch, what was merged with its permalinks, recent decisions, and
whether the plan page is stale. Do not recount the commits. This is that answer.

## 2. What comes next is held by the plan page

Read `.wiki/plan-active.md`. Read the table; do not recompute it. The top one
or two rows of its open table are what comes next.

## 3. Put it together and post it

- Channel: `<SLACK_CHANNEL>`
- Tool: `slack_send_message`
- Use step 1's output as is, and add two `*다음*` lines at the bottom.

## 4. Put the same body into the channel record

Write the body you posted to Slack into one file (a temporary path such as `.tmp/brief.md`), and put it into the `#progress` channel record with this command. The server does not have to be running.

```
python "<WIKI_ROOT>/tool/chat_post.py" --project . --channel progress --source standup --file <그 파일>
```

## Rules

- Do not strip the links out of step 1's output. They are where the original
  can be checked against, and that is this briefing's whole value.
- If the plan page reports as stale, say so at the very top. A next step
  argued from a stale table is the wrong next step.
- Change no files. Only post the briefing.
- If nothing was merged, say nothing was merged. Do not go looking for filler.
- Fifteen lines or fewer.
