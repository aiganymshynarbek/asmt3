"""
Assignment 3 - Part D failure simulation (synthetic, educational).

No real cluster was available, so this is a time-stepped model of how
Kubernetes + the API Gateway behave with the probe/timeout settings in
k8s/registration-service.yaml. Every timing constant below comes from
that YAML or is a stated assumption (see ASSUMPTIONS).

Runs each experiment N_TRIALS times with random jitter (probe phase,
start-up time, endpoint propagation) and reports median / p95.

Usage:  python3 failure_sim.py   -> writes ../results/*
"""
import csv, json, os, random, statistics

DT = 0.1                    # simulation step, seconds
N_TRIALS = 30
SEED = 2026
OUT = os.path.join(os.path.dirname(__file__), "..", "results")

ASSUMPTIONS = {
    "registration_load_rps": 300,      # registration-week share of the 500 req/s peak
    "pod_capacity_rps": 400,           # one pod saturates at 400 req/s
    "base_latency_ms": 40,
    "app_start_s": (6, 10),            # process start until /health/live answers
    "kubelet_crash_detect_s": (0.2, 1.0),   # container exit noticed by kubelet
    "endpoint_propagation_s": (0.5, 1.5),   # EndpointSlice -> kube-proxy / gateway
    "startup_period_s": 2,             # startupProbe.periodSeconds
    "readiness_period_s": 5,           # readinessProbe.periodSeconds
    "liveness_period_s": 10, "liveness_failure_threshold": 3,
    "crashloop_backoff_s": [0, 10, 20, 40, 80],   # kubelet back-off between restarts
    "db_failover_detect_s": (20, 30),  # failover manager (Patroni-style, ttl=30 s, loop 10 s)
    "db_promote_s": (3, 8),            # promote synchronous standby
    "db_reconnect_s": (0.5, 1.5),      # connection pool retries every 1 s
    "request_timeout_ms": 450,         # app/gateway timeout (fail fast < 500 ms)
}
A = ASSUMPTIONS


def u(rng, lo_hi):
    return rng.uniform(*lo_hi)


def latency_ms(ready_pods):
    """M/M/1-style latency estimate for the load spread over ready pods."""
    if ready_pods == 0:
        return None
    rho = A["registration_load_rps"] / (ready_pods * A["pod_capacity_rps"])
    if rho >= 0.98:
        return A["request_timeout_ms"]
    return min(A["base_latency_ms"] / (1 - rho), A["request_timeout_ms"])


def next_tick(t, period, phase):
    """First probe tick at or after t, for a probe with given period/phase."""
    k = int((t - phase) // period) + 1
    return phase + k * period


def restart_ready_time(rng, t_detect, backoff=0.0):
    """Time a restarted container passes startup + readiness and is READY."""
    t_start = t_detect + backoff
    t_live = t_start + u(rng, A["app_start_s"])
    t_startup_ok = next_tick(t_live, A["startup_period_s"], t_start)
    # readiness probe starts right after startup succeeds; first check passes
    return t_startup_ok + 0.1


# --------------------------------------------------------------------------
# Experiment 1 / 2: Registration replicas crash (SIGKILL of the process)
# --------------------------------------------------------------------------
def run_crash(rng, n_pods, n_failed, retries=True, horizon=120.0):
    t_fail = 30.0 + rng.uniform(0, 5)
    pods = []
    for i in range(n_pods):
        p = {"in_endpoints": [(0.0, float("inf"))]}   # intervals in Service endpoints
        p["alive"] = [(0.0, float("inf"))]
        pods.append(p)
    detect_times, ready_times = [], []
    for i in range(n_failed):
        t_det = t_fail + u(rng, A["kubelet_crash_detect_s"])
        t_removed = t_det + u(rng, A["endpoint_propagation_s"])
        t_ready = restart_ready_time(rng, t_det)
        t_added = t_ready + u(rng, A["endpoint_propagation_s"])
        pods[i]["alive"] = [(0.0, t_fail), (t_ready - 0.1, float("inf"))]
        pods[i]["in_endpoints"] = [(0.0, t_removed), (t_added, float("inf"))]
        detect_times.append(t_det)
        ready_times.append(t_added)

    def inside(iv, t):
        return any(a <= t < b for a, b in iv)

    timeline, failed_req, total_req = [], 0.0, 0.0
    lat_samples = []
    t = 0.0
    while t < horizon:
        eps = [p for p in pods if inside(p["in_endpoints"], t)]
        ready_alive = [p for p in eps if inside(p["alive"], t)]
        load = A["registration_load_rps"] * DT
        total_req += load
        if not eps:
            ok_frac = 0.0                       # no endpoints -> gateway 503 at once
        else:
            dead_share = 1 - len(ready_alive) / len(eps)
            if retries and ready_alive:
                ok_frac = 1.0                   # refused connection retried on other pod
            else:
                ok_frac = 1 - dead_share
        failed_req += load * (1 - ok_frac)
        lat = latency_ms(len(ready_alive))
        if lat is not None and ok_frac > 0:
            # a retried request pays ~1 extra connect attempt (~5 ms)
            extra = 5 if (retries and len(ready_alive) < len(eps)) else 0
            lat_samples.append(lat + extra)
        timeline.append((round(t, 1), len(ready_alive), round(ok_frac * 100, 2),
                         None if lat is None else round(lat, 1)))
        t += DT

    t_detect = max(detect_times) - t_fail
    t_service_back = (min(ready_times) - t_fail) if n_failed == n_pods else 0.0
    t_full = max(ready_times) - t_fail
    return {
        "detection_s": t_detect,
        "outage_s": t_service_back,          # time with ZERO working pods
        "full_recovery_s": t_full,           # until all replicas ready again
        "failed_requests": failed_req,
        "max_latency_ms": max(lat_samples) if lat_samples else None,
        "timeline": timeline, "t_fail": t_fail,
    }


def run_single_replica_baseline(rng):
    """'Before' design: replicas: 1, no retry."""
    return run_crash(rng, n_pods=1, n_failed=1, retries=False)


# --------------------------------------------------------------------------
# Experiment 3: primary database node becomes unavailable
# --------------------------------------------------------------------------
def run_db(rng, naive_liveness=False, horizon=200.0):
    t_fail = 30.0 + rng.uniform(0, 5)
    t_detect = t_fail + u(rng, A["db_failover_detect_s"])
    t_promoted = t_detect + u(rng, A["db_promote_s"])
    t_db_back = t_promoted + u(rng, A["endpoint_propagation_s"])  # primary Service -> new node
    t_app_ok = t_db_back + u(rng, A["db_reconnect_s"])           # pool reconnects

    restarts = 0
    if naive_liveness:
        # 'Before' design: liveness probe also checks the DB.
        # Each pod is killed after 3 failed checks, then crash-loops while DB is down.
        pod_back = []
        for _ in range(2):
            phase = rng.uniform(0, A["liveness_period_s"])
            first_fail = next_tick(t_fail, A["liveness_period_s"], phase)
            t_kill = first_fail + (A["liveness_failure_threshold"] - 1) * A["liveness_period_s"]
            if t_kill >= t_app_ok:
                pod_back.append(t_app_ok)
                continue
            t, n = t_kill, 0
            while True:
                restarts += 1
                t_ready_try = restart_ready_time(rng, t, A["crashloop_backoff_s"][min(n, 4)])
                if t_ready_try >= t_app_ok:          # DB reachable when it starts -> OK
                    pod_back.append(t_ready_try + u(rng, A["endpoint_propagation_s"]))
                    break
                # start-up fails because DB still down -> another crash
                t = t_ready_try
                n += 1
        t_recovered = min(pod_back)
        t_full = max(pod_back)
    else:
        t_recovered = t_full = t_app_ok

    timeline = []
    t = 0.0
    while t < horizon:
        working = (t < t_fail) or (t >= t_recovered)
        timeline.append((round(t, 1), 100.0 if working else 0.0))
        t += DT
    outage = t_recovered - t_fail
    return {
        "detection_s": t_detect - t_fail,
        "outage_s": outage,
        "full_recovery_s": t_full - t_fail,
        "failed_requests": A["registration_load_rps"] * outage,
        "pod_restarts": restarts,
        "rpo_s": 0.0,                       # synchronous standby: committed data kept
        "timeline": timeline, "t_fail": t_fail,
    }


# --------------------------------------------------------------------------
def summarize(runs, keys):
    out = {}
    for k in keys:
        vals = sorted(r[k] for r in runs if r.get(k) is not None)
        if not vals:
            continue
        out[k] = {"median": round(statistics.median(vals), 2),
                  "p95": round(vals[int(0.95 * (len(vals) - 1))], 2),
                  "min": round(vals[0], 2), "max": round(vals[-1], 2)}
    return out


def main():
    os.makedirs(OUT, exist_ok=True)
    # Common random numbers: trial i of every experiment uses the same seed,
    # so "before" vs "after" designs see identical failure timings.
    R = lambda i: random.Random(SEED * 1000 + i)
    exps = {
        "E1_one_replica_fails": [run_crash(R(i), 2, 1) for i in range(N_TRIALS)],
        "E1_baseline_single_replica": [run_single_replica_baseline(R(i)) for i in range(N_TRIALS)],
        "E2_all_replicas_fail": [run_crash(R(i), 2, 2) for i in range(N_TRIALS)],
        "E3_db_unavailable": [run_db(R(i)) for i in range(N_TRIALS)],
        "E3_baseline_liveness_checks_db": [run_db(R(i), naive_liveness=True) for i in range(N_TRIALS)],
    }
    keys = ["detection_s", "outage_s", "full_recovery_s", "failed_requests",
            "max_latency_ms", "pod_restarts"]
    summary = {"seed": SEED, "trials": N_TRIALS, "assumptions": ASSUMPTIONS,
               "experiments": {name: summarize(runs, keys) for name, runs in exps.items()}}
    with open(os.path.join(OUT, "summary.json"), "w") as f:
        json.dump(summary, f, indent=2)

    # representative timeline = the trial closest to the median recovery time
    for name, runs in exps.items():
        med = statistics.median(x["full_recovery_s"] for x in runs)
        idx = min(range(len(runs)), key=lambda i: abs(runs[i]["full_recovery_s"] - med))
        if name == "E3_db_unavailable":      # plot the same trial as the baseline (paired)
            b = exps["E3_baseline_liveness_checks_db"]
            bm = statistics.median(x["full_recovery_s"] for x in b)
            idx = min(range(len(b)), key=lambda i: abs(b[i]["full_recovery_s"] - bm))
        if name == "E3_baseline_liveness_checks_db":
            idx = min(range(len(runs)), key=lambda i: abs(runs[i]["full_recovery_s"] - med))
        r = runs[idx]
        with open(os.path.join(OUT, f"timeline_{name}.csv"), "w", newline="") as f:
            w = csv.writer(f)
            if name.startswith("E3"):
                w.writerow(["t_s", "registration_success_pct"])
            else:
                w.writerow(["t_s", "ready_pods", "success_pct", "latency_ms"])
            w.writerows(r["timeline"])
        with open(os.path.join(OUT, f"failtime_{name}.txt"), "w") as f:
            f.write(str(r["t_fail"]))

    # per-trial results (all experiments) for evidence / plotting
    with open(os.path.join(OUT, "per_trial.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["experiment", "trial", "detection_s", "outage_s", "full_recovery_s",
                    "failed_requests", "pod_restarts"])
        for name, runs in exps.items():
            for i, r in enumerate(runs):
                w.writerow([name, i, round(r["detection_s"], 2), round(r["outage_s"], 2),
                            round(r["full_recovery_s"], 2), round(r["failed_requests"]),
                            r.get("pod_restarts", "")])

    # human-readable log
    with open(os.path.join(OUT, "simulation_log.txt"), "w") as f:
        f.write(f"Part D failure simulation  seed={SEED} trials={N_TRIALS}\n")
        for name, s in summary["experiments"].items():
            f.write(f"\n== {name}\n")
            for k, v in s.items():
                f.write(f"  {k:18s} median={v['median']:>9}  p95={v['p95']:>9}  "
                        f"min={v['min']:>9}  max={v['max']:>9}\n")
    print(open(os.path.join(OUT, "simulation_log.txt")).read())


if __name__ == "__main__":
    main()
