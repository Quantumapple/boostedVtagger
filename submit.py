import json
import argparse
import subprocess
import shutil, os
from pathlib import Path
from datetime import datetime

def load_bash_template(outdir, timeout):

    # Define the bash script template
    bash_template = """#!/bin/bash

JSON_FILE=$(basename "$1")

# Extract the filename and swap .json for .parquet
OUTPUT_FILE=$(basename "$JSON_FILE" .json).parquet

# Check current directory to make sure that input files are transferred
ls -ltrh
echo ""

# Wrap in `timeout` so a job that's stuck (condor issue, hung xrootd read, etc.)
# fails fast instead of silently sitting in "running" state for the full
# +JobFlavour wall time. A timeout exit is just another failure mode from the
# resubmission script's point of view: no output on EOS -> gets resubmitted.
echo "Executing: timeout {1}s python run.py -s $JSON_FILE"
timeout {1}s python run.py -s $JSON_FILE
RC=$?
if [ $RC -eq 124 ]; then
    echo "Error: job timed out after {1}s"
    exit $RC
elif [ $RC -ne 0 ]; then
    echo "Error: run.py failed with exit code $RC"
    exit $RC
fi

# 3. Transfer the specific output file to EOS
echo "Transferring $OUTPUT_FILE to EOS..."
xrdcp "$OUTPUT_FILE" "root://cmseos.fnal.gov/{0}/"

# 4. Safety check: ensure transfer was successful
if [ $? -eq 0 ]; then
    echo "Transfer successful. Cleaning up local output."
    rm "$OUTPUT_FILE"
else
    echo "Error: xrdcp transfer failed!"
    exit 1
fi
""".format(outdir, timeout)

    return bash_template


def load_jdl_template(condor_log_dir, subdir):

    ### Condor Job Flavour = Maximum wall time
    ### espresso     = 20 minutes
    ### microcentury = 1 hour
    ### longlunch    = 2 hours
    ### workday      = 8 hours
    ### tomorrow     = 1 day
    ### testmatch    = 3 days
    ### nextweek     = 1 week

    # Extract the filename (e.g., QCD_HT-600to800_0) from the path using $Fn(path)

    jdl = """universe              = vanilla
executable            = run.sh
should_Transfer_Files = YES
whenToTransferOutput  = ON_EXIT
sample_name           = $Fn(input_json)
arguments             = $(input_json)
transfer_Input_Files  = processor, run.py, $(input_json)
output                = {0}/{1}/$(sample_name).stdout
error                 = {0}/{1}/$(sample_name).stderr
log                   = {0}/{1}/condor.log
+JobFlavour           = "workday"
+SingularityImage = "/cvmfs/unpacked.cern.ch/registry.hub.docker.com/coffeateam/coffea-dask-almalinux9:2025.12.0-py3.12"
queue input_json matching files job_configs/*.json
""".format(condor_log_dir, subdir)

    return jdl

def get_balanced_sequential_groups(files, target_size):
    """
    Distributes leftovers across the first few groups to maintain
    uniformity and strict sequential order.
    """
    total_files = len(files)
    if total_files == 0:
        return []
    if total_files <= target_size:
        return [files]

    # Calculate how many groups to create based on the target size
    num_groups = total_files // target_size

    # Use divmod to get the base size and how many groups need +1 file
    base_size, remainder = divmod(total_files, num_groups)

    groups = []
    start = 0
    for i in range(num_groups):
        # The first 'remainder' groups get one extra file
        current_size = base_size + (1 if i < remainder else 0)
        groups.append(files[start : start + current_size])
        start += current_size

    return groups

def file_split(input_json, year, size):

    outdir = Path('./job_configs')

    if outdir.exists():
        print(f"Cleaning up old directory in {outdir}...")
        shutil.rmtree(outdir)

    outdir.mkdir(exist_ok=True)

    with open(input_json, 'r') as file:
        data = json.load(file)

    # Use .get() to avoid KeyErrors and .items() for faster iteration
    year_data = data.get(year, {})
    if not year_data:
        print(f"Warning: No data found for year {year}")
        return []

    # Iterate using .items() to avoid repeated lookups
    for process, subprocesses in year_data.items():

        if process.endswith('_LO'):
            # This is your general condition to avoid NLO overlap
            continue

        for sub, files in subprocesses.items():
            # The balancing logic remains the most efficient way to partition
            groups = get_balanced_sequential_groups(files, size)

            for idx, group in enumerate(groups):
                job_key = f"{sub}_{idx}"

                # Directly write the JSON to minimize memory residency of large dicts
                output_path = outdir / f"{job_key}.json"

                with open(output_path, "w") as f:
                    json.dump({
                        job_key: {
                            "treename": "Events",
                            "files": group,
                            "metadata": {"year": int(year), "is_mc": True},
                        }
                    }, f, indent=4)

def persist_submission_record(sub_log_dir, output_dir, args):
    """
    Copy the exact job_configs used for this submission, plus the EOS
    destination, into the submission's own log dir. This makes each
    submit_N dir self-contained so a later --resubmit only needs that one
    path: no need to re-derive the same file split from -s/-y/-n again.
    """
    shutil.copytree('job_configs', sub_log_dir / 'job_configs')

    meta = {
        "output_dir": output_dir,
        "sample": args.sample,
        "year": args.year,
        "split": args.split,
        "timeout": args.timeout,
    }
    with open(sub_log_dir / 'meta.json', 'w') as f:
        json.dump(meta, f, indent=4)


def resolve_missing_jobs(resubmit_log_dir):
    """
    Compare the job_configs persisted for a prior submission against what's
    actually landed on EOS, and rebuild the local ./job_configs/ directory
    to contain only the missing (failed/timed-out/never-ran) ones.

    Returns (output_dir, parent_log_dir) so the caller can reuse the same
    EOS destination and place the resubmission's logs alongside the
    original run's.
    """
    resubmit_log_dir = Path(resubmit_log_dir)
    persisted_dir = resubmit_log_dir / 'job_configs'
    meta_path = resubmit_log_dir / 'meta.json'

    if not persisted_dir.is_dir() or not meta_path.is_file():
        raise FileNotFoundError(
            f"{resubmit_log_dir} doesn't look like a submission log dir "
            f"(missing job_configs/ or meta.json)"
        )

    with open(meta_path, 'r') as f:
        meta = json.load(f)
    output_dir = meta["output_dir"]

    expected_keys = {p.stem for p in persisted_dir.glob('*.json')}

    result = subprocess.run(
        ['eos', 'root://cmseos.fnal.gov', 'ls', output_dir],
        capture_output=True, text=True,
    )
    existing_keys = {
        Path(line).stem for line in result.stdout.splitlines() if line.endswith('.parquet')
    }

    missing_keys = sorted(expected_keys - existing_keys)

    print(f"Expected {len(expected_keys)} jobs, found {len(existing_keys)} outputs on EOS.")
    print(f"Resubmitting {len(missing_keys)} missing job(s): {missing_keys}")

    outdir = Path('./job_configs')
    if outdir.exists():
        shutil.rmtree(outdir)
    outdir.mkdir(exist_ok=True)

    for key in missing_keys:
        shutil.copy(persisted_dir / f"{key}.json", outdir / f"{key}.json")

    return output_dir, resubmit_log_dir.parent, meta


## --------------------------------------
if __name__ == "__main__":

    parser = argparse.ArgumentParser(description='Submit condor jobs to pre-process V-jet tagger data')

    parser.add_argument(
        '-s',
        '--sample',
        metavar = 'JSONFILE',
        type = str,
        help = 'input json file including dataset (required unless --resubmit is given)',
        default = None,
        dest = 'sample',
    )

    parser.add_argument(
        '-y',
        '--year',
        metavar = 'YEAR',
        help = 'year',
        type = str,
        default = '2024',
        dest = 'year',
    )

    parser.add_argument(
        '-n',
        '--split',
        metavar = 'NUM',
        help = 'number of files for each job',
        type = int,
        default = '10',
        dest = 'split',
    )

    parser.add_argument(
        '--timeout',
        metavar = 'SECONDS',
        help = 'per-job timeout (kills a hung run.py so the job fails fast instead of sitting idle)',
        type = int,
        default = 7200,
        dest = 'timeout',
    )

    parser.add_argument(
        '--resubmit',
        metavar = 'LOGDIR',
        help = 'path to a prior submission log dir (e.g. condor_log_20260326/submit_0); '
               'resubmits only the jobs whose output is missing on EOS',
        type = str,
        default = None,
        dest = 'resubmit',
    )

    parser.add_argument(
        '--dryrun',
        action = 'store_true',
        help = 'If set, condor submission will not happen',
        dest = 'dryrun',
    )

    args = parser.parse_args()

    if args.resubmit is None and args.sample is None:
        parser.error("either -s/--sample or --resubmit is required")

    # -------------------------------------------------------------
    if args.resubmit is not None:
        output_dir, parent_log_dir, prior_meta = resolve_missing_jobs(args.resubmit)

        if not any(Path('./job_configs').glob('*.json')):
            print("Nothing to resubmit — all jobs already have output on EOS.")
            raise SystemExit(0)

        # -s/-y/-n aren't meaningfully re-passed on a --resubmit call; carry
        # forward the original run's provenance for the persisted meta.json.
        args.sample = prior_meta.get("sample")
        args.year = prior_meta.get("year")
        args.split = prior_meta.get("split")

        log_dir = parent_log_dir

    else:
        # Make output directory
        # Format as YYYYMMDD
        now = datetime.now()
        formatted_date = now.strftime("%Y%m%d")

        output_dir = f'/store/user/jongho/vjet_preprocess_{formatted_date}'
        mkdir_cmd = ['eos', 'root://cmseos.fnal.gov', 'mkdir', '-p', output_dir]
        subprocess.run(mkdir_cmd)

        log_dir = Path(f'./condor_log_{formatted_date}')

        file_split(args.sample, args.year, args.split)

    # Condor log dir (shared by fresh submissions and resubmissions alike)
    log_dir.mkdir(exist_ok=True)

    counter = 0
    while True:
        sub_log_dir = log_dir / f"submit_{counter}"
        if not sub_log_dir.exists():
            sub_log_dir.mkdir()
            submit_subdir = f"submit_{counter}"
            break
        counter += 1

    print(f"Job logs will be saved to: {sub_log_dir}")
    # -------------------------------------------------------------

    bash_script = load_bash_template(output_dir, args.timeout)
    with open(f'run.sh','w') as bashfile:
        bashfile.write(bash_script)

    jdl_script = load_jdl_template(condor_log_dir=log_dir, subdir=submit_subdir)
    with open(f'submit.jdl','w') as jdlfile:
        jdlfile.write(jdl_script)

    persist_submission_record(sub_log_dir, output_dir, args)

    if args.dryrun:
        pass

    else:
        cmd = 'condor_submit submit.jdl'
        os.system(cmd)
        # subprocess.run(['condor_submit', 'submit.jdl'], shell=True) # LPC cluster doesn't like subprocess to submit condor jobs