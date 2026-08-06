#!/usr/bin/env python3
"""Resolve QCD MiniAOD file lists via DAS, matching the same era as W/Z.

make_input.sh finds W/Z files by browsing FNAL's physical dCache tree with
xrdfs, but that only works if the dataset actually lives at FNAL disk. QCD
samples aren't all in one place, so instead we go through DAS: find the full
dataset name under the target era, pick the site with the most complete disk
replica, and pull the file list (LFNs) directly -- no physical-path browsing
needed. If the best site is FNAL disk (same as W/Z), paths are rewritten into
FNAL's physical dCache namespace to match what make_input.sh's xrdfs browsing
produces for W/Z; otherwise the plain DAS LFN ("/store/...") is kept.
"""
import json
import subprocess

ERA = "RunIII2024Summer24MiniAODv6"
FNAL_SITE = "T1_US_FNAL_Disk"
FNAL_PHYSICAL_PREFIX = "/dcache/uscmsdisk"

QCD_DATASETS = [
    "QCD-4Jets_Bin-HT-100to200_TuneCP5_13p6TeV_madgraphMLM-pythia8",
    "QCD-4Jets_Bin-HT-200to400_TuneCP5_13p6TeV_madgraphMLM-pythia8",
    "QCD-4Jets_Bin-HT-400to600_TuneCP5_13p6TeV_madgraphMLM-pythia8",
    "QCD-4Jets_Bin-HT-600to800_TuneCP5_13p6TeV_madgraphMLM-pythia8",
    "QCD-4Jets_Bin-HT-800to1000_TuneCP5_13p6TeV_madgraphMLM-pythia8",
    "QCD-4Jets_Bin-HT-1000to1200_TuneCP5_13p6TeV_madgraphMLM-pythia8",
    "QCD-4Jets_Bin-HT-1200to1500_TuneCP5_13p6TeV_madgraphMLM-pythia8",
    "QCD-4Jets_Bin-HT-1500to2000_TuneCP5_13p6TeV_madgraphMLM-pythia8",
    "QCD-4Jets_Bin-HT-2000_TuneCP5_13p6TeV_madgraphMLM-pythia8",
]


def dasgoclient(query, json_output=False):
    cmd = ["dasgoclient", f"--query={query}"]
    if json_output:
        cmd.append("-json")
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    return result.stdout.strip()


def resolve_full_dataset(short_name):
    matches = [m for m in dasgoclient(f"dataset dataset=/{short_name}*/*{ERA}*/MINIAODSIM").splitlines() if m.strip()]
    if not matches:
        return None
    if len(matches) > 1:
        print(f"  Warning: {len(matches)} matches under {ERA}, using first:")
        for m in matches:
            print(f"    {m}")
    return matches[0]


def site_fraction(site):
    # dataset_fraction is unreliable (reads 0.00% even for sites holding every
    # block); block_completion -- fraction of each held block that's fully
    # present, effectively 100% when nfiles == total_files -- is the field
    # that actually reflects whether a site has the whole dataset.
    val = site.get("block_completion", 0)
    if isinstance(val, str):
        val = val.strip().rstrip("%") or "0"
    return float(val)


def best_disk_site(full_dataset):
    """Pick the DISK site with the highest block_completion. TAPE-only sites
    are excluded -- files there aren't directly readable by a running job
    without a separate staging request first."""
    records = json.loads(dasgoclient(f"site dataset={full_dataset}", json_output=True) or "[]")
    sites = [s for rec in records for s in rec.get("site", []) if s.get("kind") == "DISK"]
    if not sites:
        return None, 0.0
    best = max(sites, key=site_fraction)
    return best.get("se"), site_fraction(best)


def list_files(full_dataset):
    return [line for line in dasgoclient(f"file dataset={full_dataset}").splitlines() if line.strip()]


def to_output_path(lfn, se):
    # FNAL's door serves its physical dCache namespace, not the LFN directly
    # (that's why make_input.sh browses /dcache/uscmsdisk/store/mc/... for
    # W/Z instead of the plain /store/... LFN) -- so when QCD also resolves
    # to FNAL disk, rewrite paths the same way for consistency.
    if se == FNAL_SITE and lfn.startswith("/store"):
        return FNAL_PHYSICAL_PREFIX + lfn
    return lfn


def main():
    for short_name in QCD_DATASETS:
        print(f"Querying {short_name}...")

        full_dataset = resolve_full_dataset(short_name)
        if full_dataset is None:
            print(f"  Error: no dataset found for {short_name} under era {ERA}, skipping.")
            continue

        se, fraction = best_disk_site(full_dataset)
        if se is None:
            print(f"  Error: no DISK site found for {full_dataset}, skipping.")
            continue
        if fraction < 100.0:
            print(f"  Warning: best disk site {se} only has {fraction:.2f}% of {full_dataset} -- some files may be inaccessible.")

        files = list_files(full_dataset)
        if not files:
            print(f"  Error: no files found for {full_dataset}, skipping.")
            continue

        with open(f"{short_name}.txt", "w") as f:
            for lfn in files:
                f.write(f"{to_output_path(lfn, se)}\n")

        print(f"  {full_dataset} -> {se} ({fraction:.2f}%), {len(files)} files -> {short_name}.txt")


if __name__ == "__main__":
    main()
