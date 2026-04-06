import json
import argparse
import subprocess
import shutil, os
from pathlib import Path
from datetime import datetime

def load_bash_template(outdir):

    # Define the bash script template
    bash_template = """#!/bin/bash

JSON_FILE=$(basename "$1")

# Extract the filename and swap .json for .parquet
OUTPUT_FILE=$(basename "$JSON_FILE" .json).parquet

# Check current directory to make sure that input files are transferred
ls -ltrh
echo ""

echo "Executing: python run.py -s $JSON_FILE"
python run.py -s $JSON_FILE

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
""".format(outdir)

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

## --------------------------------------
if __name__ == "__main__":

    parser = argparse.ArgumentParser(description='Submit condor jobs to pre-process V-jet tagger data')

    parser.add_argument(
        '-s',
        '--sample',
        metavar = 'JSONFILE',
        type = str,
        help = 'input json file including dataset',
        required = True,
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
        '--dryrun',
        action = 'store_true',
        help = 'If set, condor submission will not happen',
        dest = 'dryrun',
    )

    args = parser.parse_args()

    # Make output directory
    # Format as YYYYMMDD
    now = datetime.now()
    formatted_date = now.strftime("%Y%m%d")

    output_dir = f'/store/user/jongho/vjet_preprocess_{formatted_date}'
    mkdir_cmd = ['eos', 'root://cmseos.fnal.gov', 'mkdir', '-p', output_dir]
    subprocess.run(mkdir_cmd)

    # Condor log dir
    log_dir = Path(f'./condor_log_{formatted_date}')
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

    file_split(args.sample, args.year, args.split)

    bash_script = load_bash_template(output_dir)
    with open(f'run.sh','w') as bashfile:
        bashfile.write(bash_script)

    jdl_script = load_jdl_template(condor_log_dir=log_dir, subdir=submit_subdir)
    with open(f'submit.jdl','w') as jdlfile:
        jdlfile.write(jdl_script)

    if args.dryrun:
        pass

    else:
        cmd = 'condor_submit submit.jdl'
        os.system(cmd)
        # subprocess.run(['condor_submit', 'submit.jdl'], shell=True) # LPC cluster doesn't like subprocess to submit condor jobs