# Variance House — final interview guide (PRISM-Physical)

*Written 3 Sep 2026, interview day. Replaces the Smriti-first prep. Plain language throughout. Everything marked VERIFIED was re-checked today against the primary source or re-run; everything marked NOT RE-CHECKED comes from your brief and should be said as "reported", not as fact.*

---

## 1. What I checked, and what I found

### The math (your `audit.py` and `results.json`)

| Check | Result |
|---|---|
| Re-ran `audit.py` from scratch and compared to your `results.json` | **Identical, byte for byte.** |
| "A fair coin gives 7+ heads in 10 about 17% of the time" | 17.2%. Correct. |
| "A 90% coin gives exactly 7 heads about 6% of the time" | 5.7%. Correct. |
| 7/10 → 34.8%–93.3% (Clopper–Pearson) | Correct. |
| Fisher test, 0/10 vs 7/10 → p = 0.0031 | Correct. Holm bar is 0.05/17 = 0.00294. It misses by 0.00016. |
| bf16 vs int8 (57/80 vs 46/80) → p = 0.098 | Correct. int4 vs int8 → p = 0.068. Neither clears 0.05. |
| Rollouts per side to detect 71.3% vs 58.1% at 80% power → 205 | Correct. |
| ±2 points at 90% → 994 rollouts; NVIDIA says ~1,030 | Both right. You report the wider arm, NVIDIA reports total width. Your reconciliation is correct. |

Your statistics are undergraduate-level and completely sound. Nobody in the room will find an error in them. That is the point: the method is simple; the field just isn't using it.

### The external claims

| Claim | Status |
|---|---|
| OpenVLA: bf16 71.3±4.8, int8 58.1±5.1, int4 71.9±4.7; 8 Bridge tasks; int8 at 1.2 Hz vs 5 Hz controller; int4 at 3 Hz; offline token accuracy unchanged | **VERIFIED** verbatim from the paper (arXiv 2406.09246, §5.4). A5000 GPU. |
| NVIDIA: 90% over 70 rollouts → 80.5%–95.9%; 1,030 rollouts for ±2; ~15× more | **VERIFIED** verbatim from the NVIDIA developer blog (Jul 2026, RoboLab). |
| LIBERO-PRO: >90% on stock LIBERO → ~0% under object-position shifts; models ignore the instruction ("instruction blindness"); 50 episodes/task | **VERIFIED** (arXiv 2510.03827). Note: it tested **three** models — OpenVLA, π₀, π₀.₅. Your brief says four (adds UniVLA). Say three. |
| SmolVLA 87.3% LIBERO vs π₀ 86.0% vs OpenVLA 76.5%; 78.3% on real SO-100 | **VERIFIED**. |
| EU Machinery Regulation 2023/1230 applies 20 Jan 2027; Annex I Part A items 5 & 6 = ML safety components with self-evolving behaviour; third-party notified body mandatory (Art. 25(2)) | **VERIFIED**. Corrigendum moved the date from 14 to 20 Jan 2027 — 20 Jan is right. |
| No harmonised standard for ML/AI in machinery | **VERIFIED**. The only harmonised-standards list in force (Decision 2023/1586, consolidated May 2026) has zero matches for "machine learning", "AI", "neural", "self-evolving". |
| EU AI Act Art. 15(3) and Annex IV 2(g) apply to machinery | **NEEDS CORRECTION — see §2.** |
| Delegated acts bringing AI requirements into machinery apply by 2 Aug 2028 | **VERIFIED**. |
| RoboEval ±11–14 point CIs; top model leads in 34/104 comparisons; TRI 1,800 trials, 2.31%/6.25% scorer discrepancy; LeRobot loss/success decorrelation; VLA-Perf Jetson latencies; Real-Time Chunking +200 ms → protective stop; BATON 38.7%→21.5%; a16z "50 failures a day"; AutoEval thermal drift; Jetson price rise | **NOT RE-CHECKED.** All have arXiv IDs or URLs in your brief. Say "reported by…". Don't quote them to one decimal from memory. |
| Your CV facts (Amazon/Adobe 9 yrs, IIM, Black Belt, Metallurgy), Bitsquish revenue, Narad 1,700 commits, PRISM top-15, 54 tests | Yours to stand behind. |

---

## 2. Two fixes before you open your mouth

### Fix 1 — Cite the Machinery Regulation, not the AI Act

On **27 July 2026** the Digital Omnibus (Regulation 2026/1744) moved machinery out of Section A of the AI Act's Annex I into **Section B**. In plain terms: the AI Act's own high-risk rules (Article 15 accuracy metrics, Annex IV test logs) **no longer apply directly to machinery**. They reach machinery only through delegated acts that amend the Machinery Regulation's Annex III, and those apply by **2 August 2028**.

So if you say "AI Act Article 15(3) requires declared accuracy metrics" about a robot arm, a mentor who follows this will know it's out of date. Drop it.

What to say instead — it's stronger anyway:

- **Machinery Regulation, 20 Jan 2027, Annex I Part A items 5 and 6.** Self-evolving ML safety components need a notified body. No self-certification. **VERIFIED.**
- **Machinery Regulation Annex IV Part A point (g)**: the technical file must contain "the results of tests, inspections and examinations". For a learned policy, that result is a success rate — and the trial count decides what it can honestly claim. That is your whole thesis, written into the file a notified body reads.
- **No standard to test against** until at least 2028. The gap is real and verified.

### Fix 2 — Make your two documents agree on the 13-point drop

Your brief (§3.3) says: *"The 13-point drop was caused by control-loop timing."*
Your audit (Action 7) says: *bf16 vs int8, p = 0.098 — the drop isn't statistically established at n = 80.*

Both can't be said as fact in the same interview. Say it this way, and it becomes your best line:

> "OpenVLA's authors report a 13-point drop at int8 and attribute it to the model running at 1.2 Hz against a 5 Hz controller — a correct brain arriving late. I recomputed their numbers. At 80 rollouts the drop has p = 0.098. It hasn't been measured yet. The mechanism is plausible and probably real. Confirming it needs about 205 rollouts per configuration. That's a two-week experiment, and it's the one I'll run."

---

## 3. One new weapon you didn't have: the law already asks for a flight recorder

Machinery Regulation **Annex III, 1.2.1** has a second block that applies to *any* machine with self-evolving or varying-autonomy control — even ones that escape the notified body. It requires:

- **(b)** recording of data on the safety-related decision-making process, **retained for one year** after collection;
- **(f)** a tracing log of interventions and of **every version of safety software uploaded** after the machine is sold, kept for **five years**;
- **(d)** no self-modification that could reach a hazardous state.

Read that against your stack:

- (b) is **Smriti**: an on-device, append-only, replayable record of what the robot believed when it acted. One SQLite file on the robot. You already built it.
- (f) is **PRISM's SHA stamping and `SubstitutionMonitor`**: every result carries the hash of the model and evaluator that produced it; every model push is a versioned entry.
- (d) is the **locked-evaluator / evolving-improver split**: the part that improves the robot must not touch the part that measures it.

You don't have to argue that regulators *will* want this. The text already requires it, from 20 January 2027. **VERIFIED.**

One honest note: a company called Particula Tech is already selling "evidence chain" infrastructure for Annex I Part A machines (the decision record and tracing log on customer hardware). They do compliance plumbing. They do not do the statistical qualification method. If asked about competitors, name them — it proves the market is real and shows you've looked.

---

## 4. Your story, in plain words (60 seconds, open with this)

> "Robots run on AI models now, and nobody can tell you how often they actually work. A paper runs a task ten times, gets seven, and prints 70%. Ten trials can't tell a 35% robot from a 93% one — that's just arithmetic. Last night I recomputed the most-cited robot results from their own tables: of 17 per-task comparisons in the OpenVLA paper, zero survive correction for multiple testing. The paper's headline is fine; the table people read isn't. The most-cited on-device result — quantization tanks performance — has p = 0.098. Nobody has replicated it.
>
> I spent nine years measuring processes where being wrong cost real money, and six months building a locked, version-stamped evaluator for AI models — 54 tests, but only ever run against a mock. I've never touched a robot. That's why I need a house with an arm in it.
>
> In 30 days: one small policy, one arm, one task, a few hundred logged rollouts. Then the first reliability datasheet for a robot policy with confidence intervals, a variance budget, and a check on the scorer. And one experiment the field hasn't run: is the on-device drop caused by precision or by timing? Either answer is a finding."

---

## 5. Your past, positioned

**The rule: proof of work first, résumé never.** They wrote "not credentials or pedigree" on the website. Danielle Strachman co-founded the Thiel Fellowship. Do not say "Black Belt", "IIM", "Amazon", "Adobe", "PRINCE2", "SAFe", or "Prosci" unless asked. If asked, one sentence each, then back to the work.

**What to say instead, in this order:**

1. **"I ship."** Bitsquish — live and making money. Smriti — open-source memory for agents, one SQLite file, benchmark harness included. Narad — 1,700+ commits, self-scoring eval loop. PRISM — a SHA-locked evaluator with 54 passing tests. Six months, solo, no funding.
2. **"I've done measurement for a living."** *"Nine years applying measurement-systems analysis to processes where a wrong number cost money. Gauge R&R, variance components, acceptance sampling, control charts."* Say the techniques, not the belt. To engineers, the math sounds like engineering; "Six Sigma" sounds like consulting.
3. **"Robotics is rediscovering my old job."** TRI's sequential tests, NVIDIA's Clopper–Pearson intervals, RoboEval's published CIs — that's the quality-engineering literature arriving one paper at a time. You already speak it.
4. **"I studied metallurgy."** B.Tech. Say it in a hardware room. Materials and process control is a native accent there.
5. **Then the weakness, before they find it:** *"I have never touched a robot. Everything I've built is measurement for software models because that's what I could reach from a laptop. The thesis is that reliability breaks at the hardware boundary — and you can't test that without hardware. Day one I'm on an arm."* One breath. Rehearse it.

**Why three projects isn't unfocused — one sentence:** *"PRISM measures. Narad improves. Smriti records. You cannot ship a self-improving robot without a frozen ruler outside the loop and a record of what it did — the Machinery Regulation now says so in writing."*

---

## 6. The 30 days, plain

**Before you arrive (3–14 Sep).** Get PRISM's evaluator into its own repo, under git, pushed — it isn't today. Get SmolVLA (450M) running on your laptop. Reproduce one LIBERO number in sim and put an interval on it. Ask them today whether the lab has an SO-101 arm or you bring one.

**Week 1 — Instrument.** One policy, one arm, one task. Build the logger: every rollout records video, joint trajectory, inference latency per step, achieved control frequency, model weight hash, quantization setting, outcome. *Ship: 100 logged rollouts on real hardware.*

**Week 2 — Measure.** Run the evaluator on the logs. Success rate with a Clopper–Pearson interval. Variance budget: how much of the spread comes from starting position, from the policy's own randomness, from perception, from timing. Gauge R&R on the scorer: does the auto-scorer agree with two humans watching the same videos? *Ship: a one-page reliability datasheet for an on-device robot policy. First of its kind.*

**Week 3 — The experiment.** Same weights, same task, same arm. fp16 / int8 / int4, crossed with throttled and unthrottled control frequency, on a Jetson-class board and a workstation. Question: is the drop caused by precision, or by timing? *Ship: an answer, with intervals, that the literature doesn't have. Either answer is publishable.*

**Week 4 — Control.** A sequential test that accepts or rejects a new policy build in far fewer than ~1,000 trials, with error rates stated up front. A control chart on a running arm that catches drift — a hot motor, a worn gripper, a changed light. Smriti on the device as the decision record. *Ship: the first working "control phase" for a deployed robot policy.*

**Demo Day, 16 Oct — one sentence:**

> "A reliability datasheet for a small robot policy on a real arm — success rate with a confidence interval, a variance budget that says where failures come from, and a check on the person scoring it; a test that accepts or rejects a new build in a fraction of the usual trials, on the device; and one finding about on-device deployment that isn't in the literature."

---

## 7. The questions, and short answers

**"What's the hard problem?"**
Knowing a robot's true failure rate cheaply enough to keep checking it after it ships. Safety standards want one bad failure in ten million hours. You can't run ten million trials. So you decompose the variance, use sequential tests, and are explicit about what you can and can't bound. The honesty about the second half is the signal.

**"What have you built? Show me."**
Bitsquish, Smriti, Narad, PRISM (see §5). Then immediately: *"PRISM has only ever run against a mock. It has never measured a real model. That's the first thing that changes."*

**"What exists on 16 October that doesn't today?"**
The datasheet, the sequential test, the timing-vs-precision result. Under 30 seconds. Then the Demo Day sentence.

**"Why do you need the lab?"**
Because the thesis is that reliability breaks at the hardware boundary — quantization, control frequency, heat, a real table — and none of that exists in simulation. LIBERO-PRO showed models at 98% in sim drop to zero when an object moves a few centimetres. A laptop can't test the claim.

**"NVIDIA's doing this. RoboLab, Isaac Lab-Arena."**
*"They're doing pre-deployment evaluation in simulation, and well. NVIDIA's own blog says most published benchmarks don't run enough rollouts. I'm not competing with that. Nobody has the phase after: a policy that has already shipped, on a device, being watched for drift with valid statistics. That's the gap."*

**"Isn't this a tool, not a company?"**
*"Today it's a tool. On 20 January 2027, EU machinery with self-evolving ML safety functions needs a notified body, and there is no harmonised standard to assess against — I checked the list; zero matches for machine learning. The regulation also already requires a one-year record of safety decisions and a five-year log of software versions on the machine. Whoever has a defensible statistical method and a body of real measurements at that moment helps write the standard."* Twenty seconds. Then back to numbers.

**"You've never built a robot."**
"No. That's why I'm here. Day one I'm on an arm." Then metallurgy and nine years of process control on physical systems.

**"Your audit says the int8 result isn't significant. So is quantization safe?"**
*"No — underpowered is not the same as wrong. The test found nothing; that's not the same as finding absence. The mechanism is plausible. It needs 205 rollouts per arm to confirm. That's the experiment."*

**"Aren't ten trials fine if the effect is big?"**
*"Yes — and that's what the OpenVLA aggregate shows: pooled over 170 rollouts, OpenVLA beats RT-2-X at p = 0.0002. The headline is sound. What's not sound is reading the seventeen per-task rows as seventeen findings. Zero survive correction. Big effects survive small samples; the field's per-task claims aren't big effects."*

**"Can you be in Bengaluru full-time, 15 Sep to 15 Oct?"**
Clean yes. Logistics already handled. Any hesitation here ends it.

---

## 8. Seven numbers to have cold

| Number | Meaning |
|---|---|
| **7/10 → 35%–93%** | Ten trials tells you almost nothing. |
| **10/10 → above 69%** | Even perfect ten-for-ten can't separate a 70% robot from a flawless one. |
| **70 rollouts at 90% → 80.5%–95.9%; ±2 needs ~1,000** | NVIDIA's own arithmetic. Precision costs the square of effort. |
| **0 of 17** | OpenVLA per-task comparisons surviving Holm correction. Headline still holds (p = 0.0002 pooled). |
| **58.1% vs 71.3%, p = 0.098, needs 205/arm** | The most-cited on-device result hasn't been measured yet. |
| **1.2 Hz vs 5 Hz** | A correct brain arriving late is a failure no accuracy metric sees. |
| **20 January 2027** | Machinery Regulation. Part A items 5 & 6. Notified body. No standard exists. |

---

## 9. Questions to ask them

1. What's actually in the hardware lab — is there a manipulator, or do I bring an SO-101?
2. Do the credits cover hardware (a Jetson, an arm), or only cloud and inference?
3. Are any of the other 13 working on robot policies? *(That person is your first user and Demo Day partner.)*
4. Can I get 30 minutes with Shyamal Anadkat in week 1 — before I run anything, not after?
5. What does a bad Demo Day look like to you?

---

## 10. Don't say

- Any credential unprompted. Not one.
- "Nobody does statistics in robotics." False — TRI, Princeton, NVIDIA do. Say: "all of it is pre-deployment comparison; none is post-deployment control."
- "PRISM does this today." It has only run against a mock.
- "The 13-point drop is caused by timing." Say "the authors attribute it to timing; it isn't yet statistically established."
- "AI Act Article 15" about machinery. Out of date since 27 July. Use the Machinery Regulation.
- TAM, pricing, tiers, the business deck. Wrong room. Every minute on market is a minute not on measurement.
- "SigmaFlow." One product, one name: PRISM.
- Numbers you didn't re-check to one decimal. Say "reported".

---

## 11. Last hour

1. Say the 60-second opener out loud three times.
2. Say the "never touched a robot" answer until it's one breath.
3. Say the Demo Day sentence until it's one breath.
4. `git init` and push PRISM. Twenty minutes. Have a link that isn't the April hackathon.
5. Have `results.json` open. If anyone doubts a number, show the script and say "three seconds to re-run."
6. Open with what you've shipped. Let them ask about your background. Never lead with it.
