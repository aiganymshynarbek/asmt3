"""Figures for the report: availability comparison + Part D timelines."""
import csv, os, subprocess
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = os.path.dirname(os.path.abspath(__file__))
RES = os.path.join(HERE, "..", "results")
FIG = os.path.join(HERE, "..", "figures")
os.makedirs(FIG, exist_ok=True)

BLUE, ORANGE, AQUA = "#2a78d6", "#eb6834", "#1baf7a"
CRIT = "#d03b3b"
GRID, AXIS, INK, MUTED = "#e1e0d9", "#c3c2b7", "#1f1f1d", "#6b6a63"

plt.rcParams.update({
    "font.family": "DejaVu Sans", "font.size": 9, "axes.edgecolor": AXIS,
    "axes.labelcolor": INK, "xtick.color": MUTED, "ytick.color": MUTED,
    "axes.spines.top": False, "axes.spines.right": False,
    "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.6,
    "axes.axisbelow": True, "savefig.dpi": 200,
})

# ---------------- availability comparison ----------------
LB, GW, I, D = 0.9995, 0.9990, 0.995, 0.997
par = lambda r: 1 - (1 - r) ** 2
designs = [
    ("No redundancy\n(1 of everything)", LB * GW * I**3 * D),
    ("Given design\n(2× services, 2× DB)", LB * GW * par(I)**3 * par(D)),
    ("+ 2nd API Gateway", LB * par(GW) * par(I)**3 * par(D)),
    ("+ 2nd Gateway\n+ 2nd Load Balancer", par(LB) * par(GW) * par(I)**3 * par(D)),
]
fig, ax = plt.subplots(figsize=(6.6, 3.0))
names = [d[0] for d in designs]
hours = [(1 - a) * 8760 for _, a in designs]
colors = [CRIT if a < 0.999 else BLUE for _, a in designs]
bars = ax.barh(names[::-1], hours[::-1], color=colors[::-1], height=0.55)
ax.axvline(8.76, color=INK, lw=1, ls="--")
ax.text(10, -0.55, "99.9% target = max 8.76 h/yr", color=INK, fontsize=8, va="center")
for b, (n, a) in zip(bars, designs[::-1]):
    ax.text(max(b.get_width(), 9.5) + 2, b.get_y() + b.get_height() / 2,
            f"{a*100:.3f}%  ({(1-a)*8760:.1f} h/yr)", va="center", fontsize=8, color=INK)
ax.set_xlabel("Expected downtime per year (hours)")
ax.set_xlim(0, 240)
ax.set_ylim(-0.8, 3.5)
ax.grid(axis="y", visible=False)
ax.set_title("End-to-end availability by design (red = misses 99.9%)", loc="left", fontsize=10, color=INK)
fig.tight_layout()
fig.savefig(os.path.join(FIG, "availability_comparison.png"))
plt.close(fig)


# ---------------- Part D timelines ----------------
def load(name):
    with open(os.path.join(RES, f"timeline_{name}.csv")) as f:
        rows = list(csv.DictReader(f))
    tf = float(open(os.path.join(RES, f"failtime_{name}.txt")).read())
    return rows, tf


def crash_fig(name, title, fname):
    rows, tf = load(name)
    t = [float(r["t_s"]) - tf for r in rows]
    ok = [float(r["success_pct"]) for r in rows]
    pods = [int(r["ready_pods"]) for r in rows]
    fig, (a1, a2) = plt.subplots(2, 1, figsize=(6.6, 3.4), sharex=True)
    a1.plot(t, ok, color=BLUE, lw=2)
    a1.set_ylabel("Requests OK (%)")
    a1.set_ylim(-5, 105)
    a2.step(t, pods, color=AQUA, lw=2, where="post")
    a2.set_ylabel("Ready pods")
    a2.set_yticks([0, 1, 2])
    a2.set_ylim(-0.2, 2.3)
    a2.set_xlabel("Seconds since failure injected")
    for a in (a1, a2):
        a.axvline(0, color=CRIT, lw=1, ls="--")
        a.set_xlim(-10, 30)
    a1.text(0.3, 50, "failure", color=CRIT, fontsize=8)
    a1.set_title(title, loc="left", fontsize=10, color=INK)
    fig.tight_layout()
    fig.savefig(os.path.join(FIG, fname))
    plt.close(fig)


crash_fig("E1_one_replica_fails", "Experiment 1 — one Registration replica killed", "e1_timeline.png")
crash_fig("E2_all_replicas_fail", "Experiment 2 — both Registration replicas killed", "e2_timeline.png")

with open(os.path.join(RES, "per_trial.csv")) as f:
    pt = list(csv.DictReader(f))
import statistics, random as _r
series = [("Before: liveness probe\nalso checks the DB", "E3_baseline_liveness_checks_db", ORANGE),
          ("After: liveness checks\nthe process only", "E3_db_unavailable", BLUE)]
fig, ax = plt.subplots(figsize=(6.6, 2.4))
jit = _r.Random(1)
for y, (lab, key, col) in enumerate(series):
    vals = [float(r["outage_s"]) for r in pt if r["experiment"] == key]
    ax.scatter(vals, [y + jit.uniform(-0.12, 0.12) for _ in vals], s=22, color=col,
               edgecolors="white", linewidths=0.8, zorder=3)
    m = statistics.median(vals); p95 = sorted(vals)[int(0.95 * (len(vals) - 1))]
    ax.plot([m, m], [y - 0.28, y + 0.28], color=INK, lw=2, zorder=4)
    ax.text(58.5, y, f"median {m:.0f} s · p95 {p95:.0f} s", va="center", fontsize=8, color=INK)
ax.set_yticks([0, 1]); ax.set_yticklabels([s[0] for s in series])
ax.set_ylim(-0.6, 1.6); ax.set_xlim(20, 78)
ax.grid(axis="y", visible=False)
ax.set_xlabel("Registration outage per trial (s), 30 paired trials; bar = median")
ax.set_title("Experiment 3 — database primary unavailable", loc="left", fontsize=10, color=INK)
fig.tight_layout()
fig.savefig(os.path.join(FIG, "e3_timeline.png"))
plt.close(fig)

# ---------------- graphviz diagrams ----------------
for g in ("architecture", "rbd"):
    subprocess.run(["dot", "-Tpng", "-Gdpi=200", os.path.join(HERE, f"{g}.dot"),
                    "-o", os.path.join(FIG, f"{g}.png")], check=True)
print("figures written to", os.path.abspath(FIG))
