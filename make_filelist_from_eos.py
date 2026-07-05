import argparse
import json
import re
import subprocess

EOS_REDIRECTOR = "root://cmseos.fnal.gov"


def eos_ls(path):
    result = subprocess.run(
        ["eos", EOS_REDIRECTOR, "ls", path],
        capture_output=True, text=True, check=True,
    )
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def qcd_subcategory(dataset_dir):
    """QCD-4Jets_Bin-HT-100to200 -> QCD_HT-100to200"""
    match = re.search(r"HT-[A-Za-z0-9]+", dataset_dir)
    return f"QCD_{match.group()}" if match else None


def classify(dataset_dir):
    """
    Maps an EOS dataset directory name to (big_category, subcategory_key).
    VJets keep the directory name as-is; QCD gets shortened to QCD_HT-<bin>
    to match the existing nanoAODv15_for_Vjet_tagger.json convention.
    """
    if dataset_dir.startswith("Wto2Q") or dataset_dir.startswith("Zto2Q"):
        return "VJets_had_NLO", dataset_dir
    if dataset_dir.startswith("QCD"):
        sub = qcd_subcategory(dataset_dir)
        return ("QCD", sub) if sub else (None, None)
    return None, None


def build_filelist(base_path, year):
    dataset_dirs = eos_ls(base_path)
    result = {year: {}}

    for dataset_dir in sorted(dataset_dirs):
        category, subkey = classify(dataset_dir)
        if category is None:
            print(f"Skipping unrecognized directory '{dataset_dir}' (doesn't match Wto2Q/Zto2Q/QCD)")
            continue

        dataset_path = f"{base_path}/{dataset_dir}"
        files = sorted(f for f in eos_ls(dataset_path) if f.endswith(".root"))
        if not files:
            print(f"Warning: no .root files found under '{dataset_dir}'")
            continue

        urls = [f"{EOS_REDIRECTOR}/{dataset_path}/{fname}" for fname in files]
        result[year].setdefault(category, {})[subkey] = urls
        print(f"{dataset_dir} -> [{category}][{subkey}]: {len(urls)} files")

    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build a submit.py-compatible file list JSON from EOS")

    parser.add_argument(
        "--eos-path",
        help="EOS directory containing one subdirectory per dataset",
    )
    parser.add_argument(
        "-y", "--year",
        help="year key for the output JSON",
    )
    parser.add_argument(
        "-o", "--output",
        help="output JSON path",
    )

    args = parser.parse_args()

    result = build_filelist(args.eos_path, args.year)

    with open(args.output, "w") as f:
        json.dump(result, f, indent=4)

    print(f"\nWrote {args.output}")
