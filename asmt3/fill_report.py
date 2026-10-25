"""Fill the Assignment 3 template with the completed solution."""
import copy, json, os
import docx
from docx.shared import Pt, Cm, RGBColor
from docx.oxml.ns import qn
from docx.oxml import OxmlElement

BASE = os.path.dirname(os.path.abspath(__file__))
d = docx.Document(os.path.join(BASE, "template.docx"))
S = json.load(open(os.path.join(BASE, "results", "summary.json")))["experiments"]
med = lambda e, k: S[e][k]["median"]
p95 = lambda e, k: S[e][k]["p95"]
P = d.paragraphs
T = d.tables


# ---------------------------------------------------------------- helpers
def set_cell(cell, text, bold_prefix=None):
    """Replace cell text; '\n\n' starts a new paragraph. Optional bold lead-in."""
    for p in cell.paragraphs[1:]:
        p._element.getparent().remove(p._element)
    paras = text.split("\n\n")
    first = cell.paragraphs[0]
    for r in list(first.runs):
        r._element.getparent().remove(r._element)
    for i, chunk in enumerate(paras):
        p = first if i == 0 else cell.add_paragraph()
        if i == 0 and bold_prefix:
            p.add_run(bold_prefix).bold = True
        p.add_run(chunk)


def fill_table(t, rows, start_col=1, start_row=1):
    for ri, vals in enumerate(rows):
        for ci, v in enumerate(vals):
            set_cell(t.rows[start_row + ri].cells[start_col + ci], v)


def _move_after(anchor_el, new_el):
    anchor_el.addnext(new_el)
    return new_el


class After:
    """Insert content in document order after an anchor element."""
    def __init__(self, anchor):
        self.el = anchor._element if hasattr(anchor, "_element") else anchor

    def para(self, text="", style=None, bold=False, italic=False, size=None):
        p = d.add_paragraph(style=style)
        if text:
            r = p.add_run(text); r.bold = bold; r.italic = italic
            if size: r.font.size = Pt(size)
        self.el = _move_after(self.el, p._element)
        return p

    def rich(self, parts, style=None):
        """parts: list of (text, bold)"""
        p = d.add_paragraph(style=style)
        for txt, b in parts:
            p.add_run(txt).bold = b
        self.el = _move_after(self.el, p._element)
        return p

    def image(self, path, width_cm, caption=None):
        p = d.add_paragraph()
        p.alignment = 1
        p.add_run().add_picture(path, width=Cm(width_cm))
        self.el = _move_after(self.el, p._element)
        if caption:
            c = self.para(caption, italic=True, size=9)
            c.alignment = 1
        return p

    def table(self, header, rows, widths_cm=None):
        t = d.add_table(rows=1 + len(rows), cols=len(header))
        t.style = d.tables[0].style
        t.alignment = 1
        for i, h in enumerate(header):
            c = t.rows[0].cells[i]
            set_cell(c, h)
            c.paragraphs[0].runs[0].bold = True
            tcPr = c._tc.get_or_add_tcPr()
            shd = OxmlElement("w:shd"); shd.set(qn("w:val"), "clear"); shd.set(qn("w:fill"), "D9EAF7"); tcPr.append(shd)
        for r, vals in enumerate(rows):
            for i, v in enumerate(vals):
                set_cell(t.rows[r + 1].cells[i], v)
        if widths_cm:
            for row in t.rows:
                for i, w in enumerate(widths_cm):
                    row.cells[i].width = Cm(w)
        self.el = _move_after(self.el, t._element)
        return t

    def code(self, text, size=7.5):
        """Monospace block in a shaded 1-cell table."""
        t = d.add_table(rows=1, cols=1)
        t.style = d.tables[0].style
        c = t.rows[0].cells[0]
        c.width = Cm(17.5)
        tcPr = c._tc.get_or_add_tcPr()
        shd = OxmlElement("w:shd"); shd.set(qn("w:val"), "clear"); shd.set(qn("w:fill"), "F4F4F2"); tcPr.append(shd)
        lines = text.rstrip("\n").split("\n")
        p = c.paragraphs[0]
        for i, line in enumerate(lines):
            if i:
                p = c.add_paragraph()
            pf = p.paragraph_format
            pf.space_before = Pt(0); pf.space_after = Pt(0); pf.line_spacing = 1.0
            r = p.add_run(line if line else " ")
            r.font.name = "Consolas"; r.font.size = Pt(size)
            r._element.rPr.rFonts.set(qn("w:eastAsia"), "Consolas")
        self.el = _move_after(self.el, t._element)
        return t


def answer_after_list_item(p, text):
    """Bold answer paragraph right after a numbered question."""
    a = After(p)
    a.rich([("Answer: ", True), (text, False)])


# ================================================================ PART A
fill_table(T[2], [
    ["Load-balancer node crashes, its zone goes offline, or the TLS certificate expires / listener is misconfigured.",
     "Total outage: it is the single entry point, so no student can reach timetable, courses, login or registration even though every backend is healthy.",
     "Managed LB with two instances in two zones (active-active) behind one DNS name; health checks remove dead gateways; certificate auto-renewal with expiry alert at 21 days."],
    ["Gateway process crashes, is overloaded at the 500 req/s peak, or a bad routing-rule release is deployed.",
     "Total outage: all API calls fail or time out, although Auth, Course and Registration are running. Its 99.90% is the lowest series value (see Part B).",
     "Run ≥2 stateless gateway replicas behind the LB; per-route timeout 450 ms and 1 retry only for refused connections / idempotent calls; rate limit per student; circuit breaker per backend; routing config in Git with canary release."],
    ["Auth pod crashes or hangs; signing key/secret misconfigured; Auth cannot reach the database.",
     "New logins fail. Students who already have a valid JWT keep working because the gateway checks the token signature locally with a cached public key.",
     "2 replicas on different nodes, liveness + readiness probes, stateless JWT sessions (any replica can serve any student), signing key from secret manager, short token TTL with refresh."],
    ["Course pod crashes, or slow DB queries make the timetable page exceed 500 ms.",
     "Timetable / course pages slow or unavailable — high-traffic read path at the start of each semester.",
     "2 replicas, readiness probe, read-through cache for timetable/course data (serve last good copy for up to 10 min if DB is down), query timeout, HPA for semester start."],
    ["Pod crashes (bug, OOM kill), memory leak, deadlock, overload during the registration window, or a bad release.",
     "Students cannot submit or confirm course registration — the most time-critical function in registration week. A naive retry could create a duplicate registration.",
     "2 replicas spread across nodes/zones, liveness (restart if stuck) + readiness (stop traffic if not ready), rolling update with maxUnavailable 0, PodDisruptionBudget, HPA 2–6, idempotency key on every registration request so retries are safe."],
    ["Primary node crashes or loses its disk; network partition; data corruption or accidental DELETE.",
     "All writes (registration) fail; reads fail unless cached; new logins fail. Corruption is replicated to the standby, so HA alone cannot fix it.",
     "Primary + synchronous standby with automatic failover (≈30 s, RPO 0); connect timeout 2 s so services fail fast; nightly full backup + 1-minute WAL archive to another region for point-in-time restore (Part E)."],
])

a = After(T[2])
a.para("Architecture after the resilience changes (components added by this design are outlined in green):", italic=True, size=9)
a.image(os.path.join(BASE, "figures", "architecture.png"), 17.5,
        "Figure 1 – Resilient architecture of the synthetic AITU Digital Student Services Platform")

# ================================================================ PART B
fill_table(T[3], [
    ["2 replicas", "1 − (1 − 0.995)² = 1 − 0.005² = 1 − 0.000025 = 0.999975 → 99.9975%"],
    ["2 replicas", "1 − (0.005)² = 0.999975 → 99.9975%"],
    ["2 replicas", "1 − (0.005)² = 0.999975 → 99.9975%"],
    ["2 nodes", "1 − (1 − 0.997)² = 1 − 0.003² = 1 − 0.000009 = 0.999991 → 99.9991%"],
    ["Series", "0.9995 × 0.9990 × 0.999975³ × 0.999991 = 0.998417 → ≈ 99.84%  (≈ 13.9 h downtime/year)"],
], start_col=1)

a = After(T[3])
a.para("Working (series = every block must work, so availabilities multiply):", bold=True)
a.code(
"Step 1  LB × Gateway            = 0.9995 × 0.9990              = 0.9985005\n"
"Step 2  Auth × Course × Reg     = 0.999975³                    = 0.9999250\n"
"Step 3  × Database pair         = 0.9999250 × 0.999991         = 0.9999160\n"
"Step 4  End-to-end              = 0.9985005 × 0.9999160        = 0.9984166  (99.842%)\n"
"\n"
"Downtime/year = (1 − A) × 8760 h\n"
"  target 99.9%  → 0.001    × 8760 = 8.76 h allowed\n"
"  design        → 0.001583 × 8760 = 13.87 h  → 5.1 h/year OVER budget\n"
"\n"
"Sensitivity (change one thing, recompute):\n"
"  2nd API Gateway (0.9990 → 0.999999)            → 99.942%   5.1 h/yr   MEETS target\n"
"  2nd Load Balancer only (0.9995 → 0.99999975)   → 99.892%   9.5 h/yr   still misses\n"
"  2nd Gateway + 2nd LB                           → 99.991%   0.7 h/yr\n"
"  3rd replica of every service                   → 99.850%   ≈ no change\n"
"  No redundancy at all (reference)               → 98.065%   169.5 h/yr", size=8)
a.image(os.path.join(BASE, "figures", "rbd.png"), 16.5,
        "Figure 2 – Reliability block diagram of the given design (red = single points of failure)")
a.image(os.path.join(BASE, "figures", "availability_comparison.png"), 15.5,
        "Figure 3 – Expected yearly downtime for each design option")

answer_after_list_item(P[11],
    "No. The given design reaches ≈ 99.84%, below the 99.9% target (13.9 h/year of expected downtime against 8.76 h allowed). "
    "The duplicated services are not the problem — each pair is already 99.997% or better.")
answer_after_list_item(P[12],
    "The API Gateway. It is a single instance at 99.90%: on its own it already uses the whole 0.1% downtime budget, so the chain can never exceed 99.9% while it stays single. "
    "The Load Balancer (99.95%, also single) is the second bottleneck. Together these two cause ≈ 99% of all expected downtime.")
answer_after_list_item(P[13],
    "Adding a second API Gateway instance (stateless, behind the LB): 99.842% → 99.942%, the only single change that meets the target. "
    "Adding a second LB as well gives 99.991%. Adding more service replicas changes almost nothing (99.850%).")

# ================================================================ PART C
yaml_text = open(os.path.join(BASE, "k8s", "registration-service.yaml")).read()
a = After(P[22])
a.rich([("File: ", True), ("k8s/registration-service.yaml", False),
        ("  — validated with kubeconform v0.6.7 against Kubernetes 1.30 schemas (strict): 7 resources, 7 valid, 0 invalid.", False)])
a.code(yaml_text, size=7)
a.para("")

fill_table(T[4], [
    ["Yes — spec.replicas: 2 (HPA keeps 2–6)", "Two identical copies; if one dies the other keeps serving. topologySpreadConstraints puts them on different nodes/zones so one machine cannot take both."],
    ["Yes — GET /health/live every 10 s, restart after 3 failures (~30 s)", "Detects a process that is running but stuck (deadlock, infinite loop) and restarts it. Checks the process only — not the DB — to avoid restart storms (Exp. 3)."],
    ["Yes — GET /health/ready every 5 s, out after 2 failures (~10 s); startupProbe 60 s", "Pod gets traffic only when it can actually serve; a starting, overloaded or draining pod is removed from the Service endpoints without being killed."],
    ["Yes — requests 250m CPU / 256Mi; limits 1 CPU / 512Mi", "Requests let the scheduler place pods on nodes with real capacity; limits stop one leaking pod from starving others (over 512Mi → OOM-kill → automatic restart)."],
    ["Yes — RollingUpdate, maxSurge 1, maxUnavailable 0, minReadySeconds 10", "New version replaces old one pod at a time; a new pod must be ready before an old one is removed, so capacity never drops below 2 and a broken release stops the rollout."],
    ["Yes — ClusterIP Service 'registration' (registration.student-services.svc.cluster.local)", "The gateway calls one stable DNS name; Kubernetes keeps the list of ready pod IPs behind it current, so pod restarts/IP changes are invisible to callers."],
])
a = After(T[4])
a.rich([("Automatic restart: ", True),
        ("implemented by restartPolicy: Always (kubelet restarts a crashed container in place, with back-off 10 s → 20 s → … → 5 min if it keeps crashing) "
         "and by the Deployment's ReplicaSet, which creates a replacement pod if a pod or its node disappears. "
         "Additional safety: PodDisruptionBudget minAvailable 1 (a node drain can never evict both replicas) and preStop sleep 5 s (Service stops routing before the process exits).", False)])

# ================================================================ PART D
E = S
fill_table(T[5], [
    ["One Registration replica: Process in pod 1 killed with SIGKILL (kubectl exec … kill -9 1) at peak registration load, 300 req/s",
     f"≈ {med('E1_one_replica_fails','detection_s'):.1f} s (max 1.0 s) — kubelet sees container exit; pod removed from Service endpoints within ≈ 1.5 s",
     f"≈ {med('E1_one_replica_fails','full_recovery_s'):.0f} s (p95 {p95('E1_one_replica_fails','full_recovery_s'):.1f} s) until the restarted pod is Ready again",
     f"None visible: 0 failed requests in 30 trials (gateway retried refused connections on pod 2). Latency 64 → 165 ms while one pod carried all load (< 500 ms). "
     f"Baseline with 1 replica: ≈ {med('E1_baseline_single_replica','outage_s'):.0f} s outage, ≈ {med('E1_baseline_single_replica','failed_requests'):,.0f} failed requests."],
    ["All Registration replicas: Both pods deleted at the same time (kubectl delete pod -l app=registration --force)",
     f"≈ {med('E2_all_replicas_fail','detection_s'):.1f} s — both pods NotReady, Service has 0 endpoints, gateway answers 503 immediately",
     f"≈ {med('E2_all_replicas_fail','outage_s'):.0f} s until first pod Ready (p95 {p95('E2_all_replicas_fail','outage_s'):.1f} s); both Ready after ≈ {med('E2_all_replicas_fail','full_recovery_s'):.0f} s",
     f"Registration unavailable for ≈ 10 s, ≈ {med('E2_all_replicas_fail','failed_requests'):,.0f} requests got a fast 503 “try again” (Retry-After). Timetable, course info and login unaffected (partial degradation, not total outage). Well inside RTO 15 min."],
    ["Database unavailable: Primary DB node stopped (StatefulSet scaled to 0 / node powered off)",
     f"≈ {med('E3_db_unavailable','detection_s'):.0f} s (20–30 s) — failover manager leader lease expires; app sees connection errors within 2 s",
     f"≈ {med('E3_db_unavailable','outage_s'):.0f} s (p95 {p95('E3_db_unavailable','outage_s'):.0f} s): standby promoted, primary Service repointed, connection pools reconnect. RPO = 0 (synchronous replica)",
     f"Registration writes fail fast (< 450 ms, 503) for ≈ 33 s ≈ {med('E3_db_unavailable','failed_requests'):,.0f} requests; course pages served from cache; new logins fail, existing sessions continue; 0 pod restarts. "
     f"Baseline (liveness checks DB): median {med('E3_baseline_liveness_checks_db','outage_s'):.0f} s, p95 {p95('E3_baseline_liveness_checks_db','outage_s'):.0f} s, up to 4 pod restarts."],
], start_col=1)

a = After(T[5])
a.rich([("Method. ", True),
        ("No real AITU or cloud cluster was used. The three experiments were run as a time-stepped simulation (sim/failure_sim.py, 0.1 s steps, 30 trials each, seed 2026) "
         "whose timings come directly from the probe, timeout and rollout settings in k8s/registration-service.yaml plus stated assumptions "
         "(registration load 300 req/s, one pod handles 400 req/s, app start-up 6–10 s, endpoint propagation 0.5–1.5 s, DB failover detection 20–30 s). "
         "Every “before/after” pair uses the same random seed per trial, so the only difference is the design. The same experiments can be repeated on a kind/minikube cluster with k8s/chaos-test.sh.", False)])
a.image(os.path.join(BASE, "figures", "e1_timeline.png"), 15, "Figure 4 – Experiment 1 (median trial): service stays at 100% while one pod restarts")
a.image(os.path.join(BASE, "figures", "e2_timeline.png"), 15, "Figure 5 – Experiment 2 (median trial): ≈ 10 s Registration outage until the first pod is Ready")
a.image(os.path.join(BASE, "figures", "e3_timeline.png"), 15, "Figure 6 – Experiment 3: outage per trial, liveness probe with vs without a DB check")
a.para("Simulation log (results/simulation_log.txt):", bold=True)
a.code(open(os.path.join(BASE, "results", "simulation_log.txt")).read(), size=7)

# ================================================================ PART E
fill_table(T[6], [
    ["Full snapshot nightly at 02:00 Astana time + continuous WAL archiving (archive_timeout = 60 s) to object storage in a second region; kept 14 days",
     "≤ 1 min (only the WAL segment not yet shipped is at risk) — meets 5 min",
     "≈ 8–12 min point-in-time restore (snapshot + WAL replay, synthetic 20 GB DB)",
     "Protects against data corruption, accidental DELETE, ransomware and loss of both DB nodes — problems that replication copies instead of preventing."],
    ["Continuous synchronous streaming replication primary → standby (every commit)",
     "0 — a commit is confirmed only after the standby has it",
     "≈ 30 s automatic failover (Exp. 3: median 33 s, p95 37 s)",
     "High availability against node/disk failure. Does NOT protect against bad data: a wrong DELETE reaches the standby within milliseconds."],
    ["Every change committed to Git (GitOps); daily Velero backup of the namespace; Secrets kept in an external secret manager",
     "0 for manifests in Git; ≤ 24 h for cluster objects not kept in Git",
     "≈ 3–5 min to re-apply all manifests to an empty cluster (kubectl apply -f k8s/)",
     "Rebuild Deployments, Services, ConfigMaps, HPA, PDB exactly as they were; roll back a bad change with git revert / kubectl rollout undo."],
    ["DR runbook rehearsed each semester (before registration week); warm standby cluster in a second region",
     "≤ 1 min (from WAL archive)",
     "≈ 13 min: detect + decide 3, apply manifests 3, restore/promote DB 5, DNS switch (TTL 60 s) 1, smoke tests 1 — within 15 min RTO",
     "Recover the whole platform after losing the primary region or cluster; proves RTO ≤ 15 min and RPO ≤ 5 min are achievable, not just assumed."],
], start_col=1)

a = After(P[26])
a.rich([("Answer. ", True),
        ("High availability (HA) and disaster recovery (DR) answer different questions. HA asks: “how do we keep serving while a part fails?” — it uses redundancy "
         "(2 replicas, 2 DB nodes, health probes, automatic failover) to hide small, frequent failures in seconds, and is measured by availability % (here 99.9%). "
         "DR asks: “how do we get back after something destroys the system or its data?” — it uses backups, a second region and a rehearsed runbook, and is measured by RTO (time to recover, ≤ 15 min) and RPO (data lost, ≤ 5 min).", False)])
a.para("The two can fail independently. Our synchronous replica gives RPO 0 for a crashed node, but if an administrator runs a wrong DELETE on the registration table, the replica deletes the same rows "
       "immediately — HA faithfully copies the disaster. Only the backup + WAL archive can restore the data to 10:41, one minute before the mistake. "
       "Conversely, a backup in another region is useless for a pod crash: restoring would take ~10 minutes, while the second replica hides the crash in under one second. "
       "A system therefore needs both: HA for frequent, local, short failures; DR for rare, large failures that take out everything HA relies on.")

# ================================================================ RECORD SECTIONS
set_cell(T[7].rows[8].cells[1], "k8s/registration-service.yaml, k8s/chaos-test.sh, k8s/kind-2nodes.yaml, sim/failure_sim.py, sim/make_figures.py, sim/*.dot, results/*")
fill_table(T[8], [
    ["(to be filled by student)"],
    ["(to be filled by student)"],
    ["Resilient architecture, availability analysis, Kubernetes manifest and failure simulation for the synthetic Registration Service"],
    ["Kubernetes 1.30 YAML, kubeconform v0.6.7, Python 3 (simulation, matplotlib), Graphviz, Word"],
    ["k8s/registration-service.yaml (validated), sim/failure_sim.py + results/, architecture & RBD diagrams, RPO/RTO plan"],
])

R = {
 9: ["The platform has six components in a chain. LB and API Gateway are single instances, so each one can take down every student service; Auth, Course and Registration have 2 replicas; the database has a primary and a standby. "
     "For every component the main failure modes, the effect on students and the chosen mechanism are listed in the Part A table.",
     "Part A table; Figure 1 (architecture after changes). Effects are classified as total outage (LB, Gateway), partial degradation (Auth, Course, Registration) or data risk (Database).",
     "I treat the database differently from the stateless services: replication solves node failure but copies data corruption, so the DB gets both a standby (HA) and backups with WAL archive (DR). "
     "I also made Registration requests idempotent, because retries are only safe if a duplicate request cannot register a student twice."],
 10: ["Each replicated pair is 99.997% or better, but the end-to-end series availability is only 99.842% (13.9 h downtime/year), so the 99.9% target is not met. "
      "The bottleneck is the single API Gateway (99.90%), followed by the single LB (99.95%).",
      "Rparallel = 1 − (1 − 0.995)² = 0.999975; DB = 1 − 0.003² = 0.999991; End-to-end = 0.9995 × 0.9990 × 0.999975³ × 0.999991 = 0.998417. Sensitivity table and Figures 2–3 in Part B.",
      "Adding a second Gateway raises availability to 99.942% (meets target); adding a 3rd service replica only reaches 99.850%. Redundancy helps most where the system currently has none. "
      "Limitation: the formula assumes independent failures — two replicas on the same node would fail together, which is why I added topology spread constraints."],
 11: ["The Registration Service runs as a Deployment with 2 replicas, startup/readiness/liveness probes, CPU/memory requests and limits, a zero-downtime rolling update, automatic restart, a ClusterIP Service for discovery, a PodDisruptionBudget and an HPA.",
      "k8s/registration-service.yaml (7 resources). kubeconform --strict against Kubernetes 1.30: “7 resources found – Valid: 7, Invalid: 0, Errors: 0”.",
      "I set maxUnavailable: 0 / maxSurge: 1 so a deploy never reduces capacity below 2 pods, and I deliberately kept the database out of the liveness probe (only the process is checked) — Experiment 3 shows why."],
 12: [f"Exp. 1: one replica killed → detected in ≈ 0.6 s, pod Ready again in ≈ 10 s, 0 failed requests. Exp. 2: both replicas killed → Registration outage ≈ 10 s, other services unaffected. "
      f"Exp. 3: DB primary down → failover in ≈ 33 s, RPO 0, no pod restarts.",
      "sim/failure_sim.py (30 trials per experiment, seed 2026), results/summary.json, results/per_trial.csv, results/simulation_log.txt, Figures 4–6; k8s/chaos-test.sh to repeat on a real cluster.",
      f"Experiment 3 compared two liveness designs. When liveness also checked the DB, pods were killed during the DB outage and then crash-looped: p95 outage rose from {p95('E3_db_unavailable','outage_s'):.0f} s to {p95('E3_baseline_liveness_checks_db','outage_s'):.0f} s with up to 4 extra restarts. "
      "Restarting a healthy process cannot fix a missing database."],
 13: ["RPO ≤ 1 min (WAL archive) and RTO ≈ 13 min for a full regional recovery meet the 5 min / 15 min limits. Node-level failures are handled by the synchronous standby (RPO 0, ≈ 30 s).",
      "Part E table: four mechanisms with frequency, RPO, recovery time and purpose; recovery time budget 3 + 3 + 5 + 1 + 1 = 13 min.",
      "A nightly backup alone would give RPO up to 24 h; WAL archiving every 60 s is what makes the 5-minute RPO achievable. The 13-minute estimate must be proven by a DR drill before registration week."],
 14: ["The most important change is adding a second API Gateway instance (and a second LB in another zone). Without it the target is mathematically impossible, because the single gateway alone is exactly 99.9%.",
      "99.842% → 99.942% with a second Gateway; 99.991% with both. Expected downtime falls from 13.9 h/year to 5.1 h and 0.7 h (Figure 3).",
      "At the Kubernetes level, the most important change is the probe design: liveness checks only the process, readiness controls traffic, and maxUnavailable 0 protects capacity during deploys — confirmed by Experiments 1 and 3."],
}
for ti, (summ, evid, obs) in R.items():
    fill_table(T[ti], [[summ], [evid], [obs]])

fill_table(T[15], [
    ["Liveness probe checks only the process (/health/live), never the database; DB problems are handled by fail-fast timeouts and readiness. Plus maxUnavailable 0 for deploys."],
    ["Availability calculation with sensitivity table (Part B); 30-trial paired simulation comparing liveness-with-DB vs process-only (results/per_trial.csv)."],
    ["k8s/registration-service.yaml; sim/failure_sim.py; sim/make_figures.py; results/simulation_log.txt; (add Git commit hash here)"],
    ["My first Exp. 3 chart compared trial 0 of each design, and the 'before' design looked better because the two runs had different random failover times. "
     "I fixed it by giving trial i of both designs the same seed (paired comparison) and reporting median and p95 over 30 trials."],
    ["Results come from a model, not a live cluster: start-up time, failover time and load are assumptions. The availability formula assumes independent failures; a shared node, zone or bad release can break both replicas at once."],
])

# evidence checklist: tick completed items
for p in P[62:70]:
    if p.text.startswith("☐"):
        for r in p.runs:
            if "☐" in r.text:
                r.text = r.text.replace("☐", "☑")
                break

def widths(t, cms):
    for row in t.rows:
        for i, w in enumerate(cms):
            row.cells[i].width = Cm(w)
    grid = t._tbl.tblGrid
    for i, gc in enumerate(grid.findall(qn("w:gridCol"))):
        gc.set(qn("w:w"), str(int(cms[i] * 567)))
widths(T[5], [2.1, 3.3, 3.2, 3.3, 5.9])
widths(T[6], [2.6, 3.6, 2.8, 3.3, 5.5])
widths(T[3], [3.0, 3.0, 11.8])
widths(T[4], [3.2, 6.0, 8.6])
out = os.path.join(BASE, "Assignment_3_Resilience_Report_Completed.docx")
d.save(out)
print("saved", out)
