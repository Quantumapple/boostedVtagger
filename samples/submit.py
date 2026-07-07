import os
import re
import json
import shlex
import argparse
import subprocess
from pathlib import Path
from jinja2 import Template
from datetime import datetime

bash_template="""#!/bin/bash

echo "Starting job on " `date` # Date/time of start of job
echo "Running on: `uname -a`" # Condor job is running on this node
echo "System software: `cat /etc/redhat-release`" # Operating System on that node

LIST_FILE=$1
JOB_ID=$2
OUTPUT_FILE=$3
DATASET=$4

# Convert 0-indexed Condor ProcId to 1-indexed line number for sed
LINE_NUM=$((JOB_ID + 1))

# Extract exactly ONE input file path from the text list
INPUT_FILE=$(sed -n "${LINE_NUM}p" "${LIST_FILE}")

# Safety check: Exit immediately if the line is blank
if [ -z "${INPUT_FILE}" ]; then
    echo "Error: No input file path found at line ${LINE_NUM} in ${LIST_FILE}!"
    exit 1
fi

# bring in the tarball you created before with caches and large files excluded:
xrdcp -s root://cmseos.fnal.gov//store/user/jongho/CMSSW_15_0_19.tgz ./
source /cvmfs/cms.cern.ch/cmsset_default.sh
tar -zxf CMSSW_15_0_19.tgz
cd CMSSW_15_0_19/src/
scramv1 b ProjectRename # this handles linking the already compiled code - do NOT recompile
eval `scramv1 runtime -sh` # cmsenv is an alias not on the workers

cd btvnano-prod

echo "cmsRun MC_allPF_2024_NANO.py inputFiles=${INPUT_FILE} outputFile=${OUTPUT_FILE}"
cmsRun MC_allPF_2024_NANO.py inputFiles=${INPUT_FILE} outputFile=${OUTPUT_FILE}

echo "\n*********"
ls -ltrh
echo "*********"

OUTDIR=root://cmseos.fnal.gov//store/user/jongho/NanoAOD4Tagger/${DATASET}
echo "\nxrdcp output for condor to ${OUTDIR}"

for FILE in *.root
do
    echo "xrdcp -f ${FILE} ${OUTDIR}/${FILE}"
    xrdcp -f ${FILE} ${OUTDIR}/${FILE} 2>&1
    XRDEXIT=$?
    if [[ $XRDEXIT -ne 0 ]]; then
        rm *.root ### note if you do this locally you remove possibly IMPORTANT ROOT FILES
        echo "exit code $XRDEXIT, failure in xrdcp"
        exit $XRDEXIT
    fi
    rm ${FILE} ### note if you do this locally you remove possibly IMPORTANT ROOT FILES
done

# Remove directory
cd ${_CONDOR_SCRATCH_DIR}

echo "\n*********"
ls -ltrh
echo "*********"

rm CMSSW_15_0_19.tgz
rm -rf CMSSW_15_0_19

echo "\n*********"
ls -ltrh
echo "*********"

"""

jdl_template="""universe              = vanilla
executable            = {{ bash_file }}
should_Transfer_Files = YES
whenToTransferOutput  = ON_EXIT
transfer_input_files  = {{ input_list }}
Arguments             = {{ input_list }} {{ jobid }} {{ dataset }}_$(ClusterId)_{{ jobid }}.root {{ dataset }}
output                = {{ log_dir }}/{{ dataset }}.{{ jobid }}.$(ClusterId).stdout
error                 = {{ log_dir }}/{{ dataset }}.{{ jobid }}.$(ClusterId).stderr
log                   = {{ log_dir }}/{{ dataset }}.{{ jobid }}.log
MY.WantOS             = "el9"
+JobFlavour           = "workday"

Queue 1
"""

CLUSTER_ID_RE = re.compile(r"submitted to cluster (\d+)")

# Must match the OUTDIR built in bash_template above.
EOS_SERVER = "cmseos.fnal.gov"
EOS_OUTPUT_BASE = "/store/user/jongho/NanoAOD4Tagger"


def submit_job(jdl_path):
    """condor_submit a single-job JDL and return the new ClusterId it was assigned."""
    # shell=True: LPC's condor_submit is a Python wrapper script, not a native binary;
    # invoking it via execve directly (shell=False) can raise "Exec format error" that
    # doesn't happen when run from an interactive shell (bash silently retries through
    # /bin/sh on that error, which subprocess with shell=False does not).
    result = subprocess.run(
        f"condor_submit {shlex.quote(str(jdl_path))}",
        shell=True, capture_output=True, text=True, check=True,
    )
    match = CLUSTER_ID_RE.search(result.stdout)
    if not match:
        raise RuntimeError(f"Could not parse ClusterId from condor_submit output:\n{result.stdout}")
    return int(match.group(1))


def job_status(cluster_id):
    """Return (JobStatus, HoldReason/RemoveReason, ExitCode) for ProcId 0 of cluster_id, or (None, None, None) if not in condor_history yet."""
    result = subprocess.run(
        f"condor_history -constraint {shlex.quote(f'ClusterId=={cluster_id} && ProcId==0')} "
        f"-af JobStatus RemoveReason ExitCode",
        shell=True, capture_output=True, text=True, check=True,
    )
    line = result.stdout.strip()
    if not line:
        return None, None, None
    parts = line.split()
    status = int(parts[0])
    reason = parts[1] if len(parts) > 1 and parts[1] != 'undefined' else ""
    exit_code = int(parts[2]) if len(parts) > 2 and parts[2] != 'undefined' else None
    return status, reason, exit_code


def eos_file_exists(remote_path):
    """Check via xrdfs stat whether remote_path (server-relative, e.g. /store/...) exists on EOS."""
    result = subprocess.run(
        ["xrdfs", EOS_SERVER, "stat", remote_path],
        capture_output=True, text=True,
    )
    return result.returncode == 0


def resubmit_timeouts(script_dir):
    """Check retry_state.json in script_dir and resubmit any job that isn't confirmed to have produced good output.

    No timeout logic of our own here: the site's +JobFlavour wall-time cap (see jdl_template)
    kills a job that runs too long, and that just shows up below as a job that stopped
    running without a completed/verified output -- same as a crash or a hold, so it's
    handled the same way: resubmit it.
    """
    state_path = Path(script_dir) / 'retry_state.json'
    with open(state_path, 'r') as f:
        state = json.load(f)

    max_retries = state['max_retries']
    dataset = state['dataset']
    n_resubmitted = n_gave_up = n_ok = n_untouched = 0

    for jobid, entry in state['jobs'].items():
        status, reason, exit_code = job_status(entry['cluster_id'])

        if status in (None, 1, 2):
            n_untouched += 1
            continue
        elif status == 4:
            if exit_code != 0:
                cause = f'exited with code {exit_code}'
            else:
                output_file = f"{dataset}_{entry['cluster_id']}_{jobid}.root"
                remote_path = f"{EOS_OUTPUT_BASE}/{dataset}/{output_file}"
                if eos_file_exists(remote_path):
                    n_ok += 1
                    continue
                cause = 'completed but output missing on EOS'
        else:
            cause = f'status={status}' + (f' ({reason})' if reason else '')

        if entry['retries'] >= max_retries:
            print(f"job {jobid}: gave up after {entry['retries']} retries ({cause})")
            n_gave_up += 1
            continue

        new_cluster_id = submit_job(entry['jdl_path'])
        entry['cluster_id'] = new_cluster_id
        entry['retries'] += 1
        print(f"job {jobid}: {cause}, resubmitted to cluster {new_cluster_id} (retry {entry['retries']}/{max_retries})")
        n_resubmitted += 1

    with open(state_path, 'w') as f:
        json.dump(state, f, indent=2)
    print(f"\n{n_resubmitted} resubmitted, {n_gave_up} gave up, {n_ok} confirmed ok, {n_untouched} still running/other")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Submit jobs to Condor')

    parser.add_argument('--input_list', type=str, help='Path to the text file containing jobs mapping')
    parser.add_argument('--dryrun', action='store_true')
    parser.add_argument('--max_retries', type=int, default=3, help='Max resubmissions for a job that fails or times out')
    parser.add_argument('--resubmit', type=str, metavar='SCRIPT_DIR',
                         help='Instead of submitting a new batch, check retry_state.json in this '
                              'job_submission_<timestamp> dir and resubmit any job that failed')
    args = parser.parse_args()

    if args.resubmit:
        resubmit_timeouts(args.resubmit)
        raise SystemExit(0)

    if not args.input_list:
        parser.error('--input_list is required unless --resubmit is given')

    with open(args.input_list, 'r') as f:
        total_jobs = len(f.readlines())

    now = datetime.now().strftime("%Y%m%d_%H%M%S")
    dataset_prefix = re.sub(r"batch\d+_", "", args.input_list.split('_TuneCP5')[0])

    script_dir = Path('.') / 'condor_scripts' / f'{dataset_prefix}' / f'job_submission_{now}'
    log_dir = Path('.') / 'condor_logs' / f'{dataset_prefix}' / f'job_submission_{now}'
    jobs_dir = script_dir / 'jobs'

    script_dir.mkdir(exist_ok=True, parents=True)
    log_dir.mkdir(exist_ok=True, parents=True)
    jobs_dir.mkdir(exist_ok=True, parents=True)

    bash_path = script_dir / 'mini2nano.sh'
    with open(bash_path, 'w') as f:
        f.write(bash_template)

    # dataset example: batch1_Zto2Q-2Jets_Bin-PTQQ-600_TuneCP5_13p6TeV_amcatnloFXFX-pythia8.txt
    # Use "Zto2Q-2Jets_Bin-PTQQ-600" as header

    job_jdl_paths = {}
    for jobid in range(total_jobs):
        jdl_content = Template(jdl_template).render({
            'bash_file': bash_path.as_posix(),
            'log_dir': log_dir.as_posix(),
            'dataset': dataset_prefix,
            'input_list': args.input_list,
            'jobid': jobid,
        })
        jdl_path = jobs_dir / f'job_{jobid}.jdl'
        with open(jdl_path, 'w') as f:
            f.write(jdl_content)
        job_jdl_paths[jobid] = jdl_path

    if args.dryrun:
        print("\n--- [Dry Run Validation] ---")
        print(f"Bash Script Path: {bash_path.as_posix()}")
        print(f"{total_jobs} job JDLs written under: {jobs_dir.as_posix()}")
        print(f"Example: {job_jdl_paths[0].as_posix()}")

    else:
        jobs_state = {}
        for jobid, jdl_path in job_jdl_paths.items():
            cluster_id = submit_job(jdl_path)
            jobs_state[str(jobid)] = {
                'jdl_path': jdl_path.as_posix(),
                'cluster_id': cluster_id,
                'retries': 0,
            }
            print(f"job {jobid}: submitted to cluster {cluster_id}")

        state_path = script_dir / 'retry_state.json'
        with open(state_path, 'w') as f:
            json.dump({
                'dataset': dataset_prefix,
                'max_retries': args.max_retries,
                'jobs': jobs_state,
            }, f, indent=2)
        print(f"\nRetry state written to {state_path.as_posix()}")
        print(f"Run 'python submit.py --resubmit {script_dir.as_posix()}' later to resubmit any that failed.")
