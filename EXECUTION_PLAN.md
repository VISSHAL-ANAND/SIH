# SIH26143 — End-to-End Execution Plan
*Compiled 2026-09-01. Read this alongside PROJECT_STATUS.md — that document says where things stand; this one says what to actually do, in order, starting now.*

---

## PHASE 0 — File Review (do this first, before writing any new code)

Go through every file below and confirm it's actually in the state described. This catches silent drift (someone edited something and forgot to tell the group) before you build more on top of it.

### `sih26143_slick_detection/`
| File | Check |
|---|---|
| `preprocess.py` | Run it once more. Confirm you still get 5,810/1,615/645 and 24.89% oil pixels. If the numbers differ, someone changed the dataset or the script — find out who/why before continuing. |
| `train_unet.py` | Confirm `data/processed/best_unet.pt` exists and is recent. If you've retrained since, note the new Oil Spill IoU number somewhere — it's not in this doc yet. |
| `shape_classifier.py` | Run it standalone (`python shape_classifier.py`) — should print 3 self-tests, all PASSED. |
| `predict_and_classify.py` | Run it against the real checkpoint. Confirm you still get real linear/blob counts (last known: 1,463 / 1,709). |

### `sih26143_ship_detection/` (RINOSH's)
| File | Check |
|---|---|
| `ship_detection_module.py` | Confirm `runs/detect/sar_hull_detector/weights/best_unet.pt` actually exists on whichever machine will run the demo. This is RINOSH's trained model — if it's only on his laptop, that's a real risk for demo day. |
| `test_geo_conversion.py` | Re-run it. Should still print "All geo-conversion tests passed." |
| `evaluate_by_size.py` | Run it once if you haven't seen the actual small/medium/large recall numbers yet — you'll want these for the pitch ("we found X, so we tuned Y"). |

### `sih26143_ais_matching/` (yours)
| File | Check |
|---|---|
| `ais_matcher.py` | Run it. Confirm the self-test still passes and note which data source it's actually using (GFW or MarineCadastre fallback) right now. |
| `gfw_ais_loader.py` | This is mid-fix. See Phase 1 below — don't consider this file "reviewed," it's actively being worked on. |

### `sih26143_integration/` (yours, absorbed from RATHIMEENA)
| File | Check |
|---|---|
| `pipeline_contracts.py` | Just read it top to bottom once. Confirm the `HullDetection`/`AISMatch` fields still match what RINOSH's and your own code actually return. |
| `integration_pipeline.py` | Run it end to end. Confirm slick→hull→AIS still connects without errors (drift stays mocked, that's expected). |
| `geolocation.py` | Confirm the demo anchor box (lat 20.75–20.95, lon 69.10–69.35) is still the region your team wants — if the demo scenario changed, this needs updating too. |

### Notion Task Tracker
- Update ASHMIL's 4 tasks and RATHIMEENA's integration-related tasks to reflect that VISSHAL built them. This isn't just bookkeeping — whoever presents needs to know honestly who can speak to which part.

**Once Phase 0 is done, you have a real, verified baseline. Everything below builds from that baseline, not from memory of what things used to look like.**

---

## PHASE 1 — Resolve the AIS data blocker (decision point, do this next)

This is the one open technical fight. Time-box it:

1. **Try `fetch_sar_vessel_detections()`** (already built, untested live) — run `ais_matcher.py` with this as the data source. If it works, this might actually be *better* than raw AIS presence, since it comes with GFW's own dark-vessel flag built in.
2. **If that also 403s:** send the access-request email to GFW now (costs nothing to have pending, but don't wait on a reply — assume it won't arrive in time).
3. **Set a hard stop:** give this **30 more minutes, not more**. If it's not working by then, switch to the honest MarineCadastre-validated framing from PROJECT_STATUS.md section 4 and move on. This single API integration should not be allowed to eat the rest of your week — the matcher's *logic* is already proven; the data source is a nice-to-have upgrade, not a blocker.

---

## PHASE 2 — Finish Drift Simulation (SIMI's track — assign or absorb)

**Decide right now:** is SIMI actually going to finish this, or has that track effectively stalled like RATHIMEENA's did?

- **If SIMI's active:** she needs to finish the backward drift simulation using the NOAA HYCOM/GFS data she already pulled, plus wire jurisdiction routing in for real (currently just marked Done in Notion, unverified).
- **If SIMI's stalled too:** you'll need to decide whether to build a simplified version yourself (a genuinely simple version — e.g., straight-line backward projection using average current speed/direction for the region, rather than a full physics simulation, is defensible for a hackathon demo) or cut this stage from the live demo and present it as "designed but not fully implemented — here's the approach" with a diagram instead of working code.

**Either way, this needs a decision today, not another day of silent non-progress.**

---

## PHASE 3 — Full Pipeline Integration (once drift is real or deliberately cut)

1. Wire the real (or simplified) drift simulation into `integration_pipeline.py`, replacing the mock — same pattern as the hull detection and AIS matching swaps you already did.
2. Run the full 4-stage pipeline end to end on your real test images.
3. **Verify the actual output makes sense as a demo narrative**: pick one image where a linear slick → a detected hull → no AIS match → (if drift is real) a plausible origin point, and manually check every number in that chain is sane. This is your dry run for the actual pitch walkthrough.

---

## PHASE 4 — Dashboard (SYLVI's track, or minimum-viable fallback)

You do **not** need a polished dashboard to win — you need something that lets a judge *see* the result instead of reading console text.

**Minimum viable version if SYLVI's behind:**
- A single map image (even a static one) showing: the slick, the detected hull, and a red flag on the unmatched one.
- A simple table: hull ID, matched Y/N, suspicion score.

That's it. Don't let "no dashboard" become a blocker if a simple static visual gets the same point across in the room.

---

## PHASE 5 — Demo Frame Curation (RATHIMEENA's original task, still open)

1. Run the full pipeline across all 645 test images.
2. Pick **2-3 frames** where the story is clearest: a visibly linear slick, a detected hull nearby, and that hull coming back unmatched.
3. Script the exact 60-90 second walkthrough: "Here's the slick. Here's the shape — linear, so likely a moving vessel. Here's the hull our detector found nearby. Here's the AIS check — no broadcast found within our tolerance. That's our suspect."
4. Rehearse this specific walkthrough at least twice before the actual pitch — this is the payload of your entire demo, protect the time for it.

---

## PHASE 6 — Pitch Deck (not started by anyone yet)

Structure that fits everything you've actually built:
1. **Problem** — dark vessels evading detection during oil spills.
2. **Why existing tools miss this** — Cerulean/CleanSeaNet rely on AIS to find the ship; if AIS is off, they can't.
3. **Our approach** — detect hulls independently of AIS; AIS only rules out innocent ships.
4. **Architecture diagram** — the 4-stage pipeline.
5. **What's real** — be honest and specific: trained model, real numbers (1,463/1,709 linear/blob split), validated against 7.3M real AIS records.
6. **Live demo** — the curated walkthrough from Phase 5.
7. **Honest limitations / future work** — no look-alike class in training data (mitigated by shape classifier, not solved), AIS data source still being finalized, drift simulation status (real or designed-not-built, whichever it ends up being).
8. **Validation** — cite Global Fishing Watch's own SAR+AIS dark-vessel detection at global scale as independent proof this approach works.

---

## PHASE 7 — Rehearsal & Final Polish

- Full team run-through, at least twice, with the actual demo (not a description of it).
- Confirm every team member can speak to whichever part they're presenting — given how much got absorbed by one person, make sure the presentation doesn't silently become a one-person show if that's not the plan.

---

## Suggested Order of Operations Starting Right Now

1. Phase 0 file review (today, ~30-45 min)
2. Phase 1 AIS decision, time-boxed (today, ≤30 min)
3. Phase 2 drift decision — get SIMI's real status *today*, don't let this slide another day
4. Phase 3 full integration once Phase 2 resolves
5. Phases 4-6 can run in parallel if you have any team bandwidth left — dashboard, demo curation, and pitch deck don't depend on each other
6. Phase 7 last, once everything above is real

Given today is September 1 and (per the original problem statement) the portal deadline is September 20th, you have runway — but the pattern so far has been long stretches of silent non-progress from most of the team. The biggest risk to this plan isn't technical difficulty, it's the same stall happening again on Phases 2, 4, 5, and 6 the way it did on integration and AIS matching. Worth deciding now, honestly, whether those are staying with their original owners or whether you're planning to absorb them too.
