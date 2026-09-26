# Three AI judges, four rounds, and the one change Smriti kept

*Cover image: `0-cover.png`*

Smriti is a memory layer for AI agents. It runs on your machine, in one SQLite file. When your agent asks something, Smriti searches its memories and packs the best ones into the model's context.

That context is small. If the right memory doesn't make it in, the model answers without it.

So we asked a simple question. Could a small, fast "judge" model look at each memory and tell Smriti which ones matter? We tested three of them in public over four rounds, and posted every win and loss as it happened.

Here is the whole story, and what Smriti now does by default because of it.

## Why we ran it

*Image: `1-the-prize.png`*

First we measured what a perfect judge would be worth.

We used 232 LongMemEval questions that Smriti had never been tuned on. With room for 1,500 characters of memories, Smriti gets every needed memory into the context 65.6% of the time. A perfect judge re-ranking Smriti's top 20 memories would reach 87.1%.

That 21.5-point gap was the prize.

## The contenders

We tested three "System One" models. Each one reads a short text and answers a yes/no or multiple-choice question in a single pass.

- **Laya**: open weights, runs on your machine. We tried a 322M community fine-tune and the official 421M English model.
- **Jev**: a hosted API from TypeSafe.
- **CLM-8B**: open weights from Contrastive-LM, built on an 8B model. It needs a 24 GB GPU.

## The rules

- Every judge scored the same 10,000 question and memory pairs: 500 questions, and Smriti's top 20 memories for each.
- We tuned settings on 256 questions and tested once on 244 others.
- A judge had to beat Smriti's own ranking, or it stayed off.
- We posted every result as it landed, including the bad ones.

## Four rounds

*Image: `2-four-rounds.png`*

**Round 1: a coin flip.** A community fine-tune of Laya judged memories with no training for our task. It ranked them no better than chance (a ranking score, AUC, of 0.47; a coin flip scores 0.50). Plugged into Smriti, it cut the evidence reaching the model from 82.8% to 8.0%.

**Round 2: the judge taught us something.** We kept that model frozen and trained a small layer on top, using our labelled questions. It started ranking well: AUC 0.928, against 0.890 for Smriti's own order, on questions it had never seen.

Then we looked at what it had learned. Its biggest weight said one thing. The assistant's own replies are rarely the evidence. The user's statements are.

**Round 3: the hosted judge.** Jev, with no training, put the right memory first 72.5% of the time. Smriti's own order does that 63.8% of the time. Blended with Smriti's score, Jev raised the evidence in a 1,500-character context from 65.6% to 74.8%. It cost $0.37 per 1,000 questions and took 1.4 seconds per question. But every candidate memory is sent to a hosted API to get there.

**Round 4: on a GPU.** The official Laya model, with a small layer trained on our labels, put the right memory first 74.2% of the time. That is level with Jev; the difference is not significant. It raised the evidence at 1,500 characters to 72.6%. It costs nothing and nothing leaves your machine. It needs a GPU to be fast: 0.8 seconds per question on an NVIDIA L4, and 15 to 20 seconds on a 4-core CPU.

CLM-8B, with no training, ranked memories well below Smriti in all three prompt formats we tried, including the one its own docs recommend. Blended in, it helped a little at 1,500 characters and not at all at 3,000.

## The change we kept

*Image: `3-the-free-win.png`*

Smriti already ranked the assistant's replies a little lower than the user's statements. Round 2's judge said to push that further. We changed one number, from 0.55 to 0.2, chose it on the tuning questions, and tested it once on the unseen ones.

- At 3,000 characters, evidence reaching the model went from 78.5% to 83.2%: 23 questions better, 1 worse.
- At 9,000 characters it went from 87.6% to 93.0%: 26 questions better, none worse.
- At 1,500 characters the change was too small to count.

No model is involved. It shipped as the default in Smriti 0.4.1. It adds no latency, costs nothing and sends nothing anywhere. Questions that ask what the assistant said are not affected.

## Where each judge landed

*Image: `4-scoreboard.png`*

Hosted Jev closes about 43% of the gap to a perfect judge at 1,500 characters. The trained local Laya closes about a third. CLM-8B, as released, doesn't beat Smriti's own ranking.

## What we got wrong

Midway through, we found a bug in our own test harness. It gave the variants we tested about 150 extra characters of room, which flattered them at tight budgets. We fixed it, re-ran everything and corrected the Smriti 0.4.1 release notes in public. The gain we first reported at 1,500 characters did not survive. The gains at 3,000 and 9,000 held.

## What Smriti ships now

*Image: `5-what-ships.png`*

- **On by default:** assistant replies ranked lower. +4.7 points at 3,000 characters and +5.4 at 9,000. No model, 8 to 14 ms per query on a CPU, $0, and nothing leaves your machine.
- **Optional, off by default:** a judge hook. It speaks the same protocol as Jev, laya-serve and clm-serve. Jev gives the biggest boost at small budgets, but your memories leave your machine to get it.
- **Next:** the trained local Laya judge as an add-on for people with a GPU.
- **Not shipping:** CLM-8B as released.

## The takeaway

The biggest change to Smriti's default didn't come from running a judge. It came from reading what a judge had learned. For a private memory layer, that's the best kind of win. It's free, it's fast, and your memories never leave your machine.

The code, the data and every number are at github.com/vn-envy/Smriti, in `audit/2026-09-25/decision-models`.
