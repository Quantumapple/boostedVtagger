import random
import argparse
from pathlib import Path

parser = argparse.ArgumentParser(description='Submit jobs to Condor')

parser.add_argument('--batch', type=int, required=True, help='batch set')
args = parser.parse_args()

dataset_configs = [
    "Wto2Q-2Jets_Bin-PTQQ-100_TuneCP5_13p6TeV_amcatnloFXFX-pythia8.txt",
    "Wto2Q-2Jets_Bin-PTQQ-200_TuneCP5_13p6TeV_amcatnloFXFX-pythia8.txt",
    "Wto2Q-2Jets_Bin-PTQQ-400_TuneCP5_13p6TeV_amcatnloFXFX-pythia8.txt",
    "Wto2Q-2Jets_Bin-PTQQ-600_TuneCP5_13p6TeV_amcatnloFXFX-pythia8.txt",
    "Zto2Q-2Jets_Bin-PTQQ-100_TuneCP5_13p6TeV_amcatnloFXFX-pythia8.txt",
    "Zto2Q-2Jets_Bin-PTQQ-200_TuneCP5_13p6TeV_amcatnloFXFX-pythia8.txt",
    "Zto2Q-2Jets_Bin-PTQQ-400_TuneCP5_13p6TeV_amcatnloFXFX-pythia8.txt",
    "Zto2Q-2Jets_Bin-PTQQ-600_TuneCP5_13p6TeV_amcatnloFXFX-pythia8.txt",
    "QCD-4Jets_Bin-HT-100to200_TuneCP5_13p6TeV_madgraphMLM-pythia8.txt",
    "QCD-4Jets_Bin-HT-200to400_TuneCP5_13p6TeV_madgraphMLM-pythia8.txt",
    "QCD-4Jets_Bin-HT-400to600_TuneCP5_13p6TeV_madgraphMLM-pythia8.txt",
    "QCD-4Jets_Bin-HT-600to800_TuneCP5_13p6TeV_madgraphMLM-pythia8.txt",
    "QCD-4Jets_Bin-HT-800to1000_TuneCP5_13p6TeV_madgraphMLM-pythia8.txt",
    "QCD-4Jets_Bin-HT-1000to1200_TuneCP5_13p6TeV_madgraphMLM-pythia8.txt",
    "QCD-4Jets_Bin-HT-1200to1500_TuneCP5_13p6TeV_madgraphMLM-pythia8.txt",
    "QCD-4Jets_Bin-HT-1500to2000_TuneCP5_13p6TeV_madgraphMLM-pythia8.txt",
    "QCD-4Jets_Bin-HT-2000_TuneCP5_13p6TeV_madgraphMLM-pythia8.txt",
    # WH/ZH signal samples (test only). Appended at the END so the shared
    # random.shuffle sequence of the samples above is unchanged.
    "WplusH-Wto2Q-Hto2Wto4Q_Par-M-125_TuneCP5_13p6TeV_powhegMINLO-jhugen-pythia8.txt",
    "WplusH-Wto2Q-Hto2WtoLNu2Q_Par-M-125_TuneCP5_13p6TeV_powhegMINLO-jhugen-pythia8.txt",
    "WplusH_Wto2Q_Hto2Wto2L2Nu_M-125_Par-M-125_TuneCP5_13p6TeV_powhegMINLO-jhugen-pythia8.txt",
    "WminusH-Wto2Q-Hto2Wto4Q_Par-M-125_TuneCP5_13p6TeV_powhegMINLO-jhugen-pythia8.txt",
    "WminusH-Wto2Q-Hto2WtoLNu2Q_Par-M-125_TuneCP5_13p6TeV_powhegMINLO-jhugen-pythia8.txt",
    "WminusH-Wto2Q-Hto2Wto2L2Nu_Par-M-125_TuneCP5_13p6TeV_powhegMINLO-jhugen-pythia8.txt",
    "ZH-Zto2Q-Hto2Wto4Q_Par-M-125_TuneCP5_13p6TeV_powhegMINLO-jhugen-pythia8.txt",
    "ZH-Zto2Q-Hto2WtoLNu2Q_Par-M-125_TuneCP5_13p6TeV_powhegMINLO-jhugen-pythia8.txt",
    "ZH-Zto2Q-Hto2Wto2L2Nu_Par-M-125_TuneCP5_13p6TeV_powhegMINLO-jhugen-pythia8.txt",
    "GluGluZH-Zto2Q-Hto2Wto4Q_Par-M-125_TuneCP5_13p6TeV_powhegMINLO-jhugen-pythia8.txt",
    "GluGluZH-Zto2Q-Hto2WtoLNu2Q_Par-M-125_TuneCP5_13p6TeV_powhegMINLO-jhugen-pythia8.txt",
    "GluGluZH-Zto2Q-Hto2Wto2L2Nu_Par-M-125_TuneCP5_13p6TeV_powhegMINLO-jhugen-pythia8.txt",
]

batch_number = args.batch
FNAL_REDIRECTOR = "root://cmsdcadisk.fnal.gov/"
GLOBAL_REDIRECTOR = "root://cms-xrd-global.cern.ch/"

# CRITICAL: Never change this seed. It ensures the shuffle order remains identical across runs!
random.seed(12345)

for filename in dataset_configs:
    if not Path(filename).exists():
        print(f"Warning: File {filename} not found. Skipping...")
        continue

    with open(filename, 'r') as f:
        all_files = [line.strip() for line in f if line.strip()]

    # 1. Sort first to guarantee identical starting order on any machine
    all_files.sort()

    # 2. Shuffle deterministically using our fixed seed
    random.shuffle(all_files)

    total_available = len(all_files)

    if "QCD" in filename:
        chunk_size = 50
    elif "WplusH" in filename or "WminusH" in filename or "ZH" in filename:
        # WH/ZH are test-only and have far fewer files (161-362) than W/Z/QCD
        chunk_size = 20
    else:
        chunk_size = 100

    # Calculate index boundaries based on the current batch
    start_idx = (batch_number - 1) * chunk_size
    end_idx = batch_number * chunk_size

    # Safety check to make sure we don't overrun the total file list
    if start_idx >= total_available:
        print(f"Error for {filename[:15]}: Batch {batch_number} exceeds total available files!")
        continue
    if end_idx > total_available:
        end_idx = total_available

    selected_files = all_files[start_idx:end_idx]

    output_filename = f"batch{batch_number}_{filename}"
    with open(output_filename, 'w') as f_out:
        for file_path in selected_files:

            clean_path = file_path

            # If the line already carries its own redirector, keep it as-is.
            if clean_path.startswith("root://"):
                f_out.write(f"{clean_path}\n")
                continue

            # Enforce leading forward-slash format for XRootD appending
            if clean_path.startswith("store/"):
                clean_path = "/" + clean_path

            # /dcache paths are FNAL's physical dCache namespace (only that
            # site's door resolves them); plain /store LFNs go through the
            # CMS global redirector so xrootd can find whichever site holds
            # the file (e.g. QCD samples resolved to a non-FNAL site).
            if clean_path.startswith("/dcache"):
                redirector = FNAL_REDIRECTOR
            else:
                redirector = GLOBAL_REDIRECTOR

            f_out.write(f"{redirector}{clean_path}\n")

    print(f"Batch {batch_number} for {filename[:25]}... -> Kept indices [{start_idx}:{end_idx}] ({len(selected_files)} files)")
