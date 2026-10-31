# research-agent

Writes research briefs where every factual claim carries an inline citation. The agent fetches web pages with a `fetch_url` tool, cross-checks what it finds, keeps numbers exactly as the source states them, marks anything it could not confirm as unverified rather than guessing, and ends every brief with a numbered source list including retrieval dates.

**Prompt takeaway:** demand a citation after every claim and an explicit "unverified" label for anything unconfirmed. The label is the point: it gives hallucination a visible failure mode you can check for, instead of hoping the model never guesses.

## Run it

```bash
python3 runner/run.py --agent research-agent \
  --task research-agent/golden/01-model-brief/task.md \
  --mode loop --reasoning-effort high --out /tmp/research-agent-run
```

Loop mode is required for the `fetch_url` tool. A typical brief takes a few minutes and a dozen or so tool calls.

## Golden example

`golden/01-model-brief/` asks for a one-page technical brief on a language model, starting from three seed URLs and expanding with `fetch_url` as needed. The committed `brief.md` cites every claim with `[n](url)` markers that map one-to-one to its source list.

Preview (first lines of the generated brief; text output, so an excerpt stands in for a screenshot):

```markdown
# Solar Open 2 브리프

**작성:** 2026-07-22 기준 공개 정보
**조회일:** 2026-07-24

---

## 1. 요약

Solar Open 2는 업스테이지(Upstage)가 2026년 7월 22일 공개한 **250B-A15B Mixture-of-Experts(MoE) 오픈웨이트 언어모델**로, 장기 수평선(long-horizon) 에이전트 작업을 위해 설계·훈련되었다 [1](https://arxiv.org/abs/2607.20062).
```

## Tips

- Seed URLs matter. Give the agent two or three starting sources you trust and let it expand from there, as the golden task does.
- The agent answers in the language of your task. The golden task is Korean, so its brief is Korean; an English task produces an English brief.
