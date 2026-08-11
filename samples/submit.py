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

# QCD events are busier (more jets/PF candidates) and pushed the default 2-thread
# config over the 2048 Mb Docker memory limit; run QCD single-threaded to lower
# peak memory instead of raising request_memory for every sample.
NUM_THREADS=2
if [[ "${DATASET}" == QCD* ]]; then
    NUM_THREADS=1
fi

echo "cmsRun MC_allPF_2024_NANO.py inputFiles=${INPUT_FILE} outputFile=${OUTPUT_FILE} numThreads=${NUM_THREADS}"

# Retry cmsRun a few times: transient xrootd read failures against the input file
# (e.g. dCache pool timeouts / "Operation expired") are common under load and usually
# clear up on a later attempt, so retry here instead of relying on a manual resubmit.
# Attempt 1 uses the plain LFN, which CMSSW resolves to the local site's PFN first
# (fastest path when it works). If that fails, later attempts prefix the LFN with the
# CMS global redirector so xrootd can fail over to another site's disk copy (e.g. CERN)
# instead of retrying the same unresponsive local pool.
MAX_CMSRUN_ATTEMPTS=3
LOCAL_REDIRECTOR="root://cmsdcadisk.fnal.gov/"
GLOBAL_REDIRECTOR="root://cms-xrd-global.cern.ch/"
for ATTEMPT in $(seq 1 $MAX_CMSRUN_ATTEMPTS); do
    if [ $ATTEMPT -eq 1 ]; then
        CMSRUN_INPUT=${INPUT_FILE}
    else
        # INPUT_FILE already carries the local redirector (see prepare_dataset.py); strip
        # it so we don't end up prefixing the global redirector onto a full root:// URL.
        CMSRUN_INPUT=${GLOBAL_REDIRECTOR}${INPUT_FILE#$LOCAL_REDIRECTOR}
        echo "Retrying via global redirector: ${CMSRUN_INPUT}"
    fi
    cmsRun MC_allPF_2024_NANO.py inputFiles=${CMSRUN_INPUT} outputFile=${OUTPUT_FILE} numThreads=${NUM_THREADS}
    CMSRUN_EXIT=$?
    if [ $CMSRUN_EXIT -eq 0 ]; then
        break
    fi
    echo "cmsRun attempt ${ATTEMPT}/${MAX_CMSRUN_ATTEMPTS} failed with exit code ${CMSRUN_EXIT}"
    if [ $ATTEMPT -eq $MAX_CMSRUN_ATTEMPTS ]; then
        echo "cmsRun failed after ${MAX_CMSRUN_ATTEMPTS} attempts, giving up"
        exit $CMSRUN_EXIT
    fi
    sleep 60
done

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

# Used to resubmit any number of failed jobs together as one shared cluster: Condor's
# "queue jobid from (...)" assigns $(jobid) from our list, one per line, in order, while
# ProcId is still its own separate 0..N-1 counter -- so $(jobid) is what maps a slot back
# to the correct line in the original input_list.
# {{ output_name }} is precomputed in Python (not $(ClusterId)-based) so that resubmitting
# an already-succeeded job overwrites the same EOS filename instead of creating a duplicate
# under a new ClusterId -- see parse_batch_number() / resubmit_timeouts().
resubmit_jdl_template="""universe              = vanilla
executable            = {{ bash_file }}
should_Transfer_Files = YES
whenToTransferOutput  = ON_EXIT
transfer_input_files  = {{ input_list }}
Arguments             = {{ input_list }} $(jobid) {{ output_name }} {{ dataset }}
output                = {{ log_dir }}/{{ dataset }}.$(ClusterId).$(jobid).stdout
error                 = {{ log_dir }}/{{ dataset }}.$(ClusterId).$(jobid).stderr
log                   = {{ log_dir }}/{{ dataset }}.$(jobid).log
MY.WantOS             = "el9"
+JobFlavour           = "workday"
{% if request_memory %}request_memory        = {{ request_memory }}
{% endif %}
queue jobid from (
{% for j in jobids %}{{ j }}
{% endfor %})
"""

# Used for the initial batch: one shared cluster, ProcId 0..total_jobs-1 via Condor's own macro.
# Output filename is keyed by (batch, ProcId) rather than ClusterId: batch+jobid uniquely and
# stably identifies a specific input file (see parse_batch_number()), so a resubmission of the
# same job -- which gets a new ClusterId but the same jobid -- overwrites rather than duplicates.
batch_jdl_template="""universe              = vanilla
executable            = {{ bash_file }}
should_Transfer_Files = YES
whenToTransferOutput  = ON_EXIT
transfer_input_files  = {{ input_list }}
Arguments             = {{ input_list }} $(ProcId) {{ dataset }}_{{ batch }}_$(ProcId).root {{ dataset }}
output                = {{ log_dir }}/{{ dataset }}.$(ClusterId).$(ProcId).stdout
error                 = {{ log_dir }}/{{ dataset }}.$(ClusterId).$(ProcId).stderr
log                   = {{ log_dir }}/{{ dataset }}.$(ProcId).log
MY.WantOS             = "el9"
+JobFlavour           = "workday"
{% if request_memory %}request_memory        = {{ request_memory }}
{% endif %}
Queue {{ total_jobs }}
"""

# QCD jobs run single-threaded (see bash_template) but still need more than the site
# default; a few jobs still spiked past 2560 on their first attempt, so resubmissions
# ask for more headroom than the initial try. W/Z jobs stay on the site default by
# leaving request_memory unset (Jinja omits the line when None).
QCD_REQUEST_MEMORY = 2560
QCD_RESUBMIT_REQUEST_MEMORY = 3072


def request_memory_for(dataset, mb):
    return mb if dataset.startswith("QCD") else None


CLUSTER_ID_RE = re.compile(r"submitted to cluster (\d+)")
SCHEDD_RE = re.compile(r"submit jobs to (\S+)")

# Must match the OUTDIR built in bash_template above.
EOS_SERVER = "cmseos.fnal.gov"
EOS_OUTPUT_BASE = "/store/user/jongho/NanoAOD4Tagger"


def parse_batch_number(input_list):
    """Extract the batch number prepare_dataset.py encodes as the first '_'-delimited
    token of its output filename (e.g. 'batch3_QCD-...txt' -> '3'). Combined with jobid
    (the input file's line number), this is a stable, unique identifier for a specific
    physical input file -- unlike ClusterId, it doesn't change across resubmission
    attempts of the same job.
    """
    first_token = Path(input_list).name.split('_', 1)[0]
    if not first_token.startswith('batch'):
        raise ValueError(
            f"Expected {input_list!r} to start with 'batchN_' (as prepare_dataset.py "
            f"writes), got {first_token!r} instead"
        )
    return first_token[len('batch'):]


def submit_job(jdl_path):
    """condor_submit a single-job JDL, returning (ClusterId, schedd_name) it was assigned.

    LPC's condor_submit auto-picks one of several schedds and prints which one
    ("Attempting to submit jobs to lpcschedd4.fnal.gov") -- condor_history later
    refuses to run without being told explicitly which schedd to query via -name,
    so that name has to be captured here and carried along in retry_state.json.
    """
    # shell=True: LPC's condor_submit is a Python wrapper script, not a native binary;
    # invoking it via execve directly (shell=False) can raise "Exec format error" that
    # doesn't happen when run from an interactive shell (bash silently retries through
    # /bin/sh on that error, which subprocess with shell=False does not).
    result = subprocess.run(
        f"condor_submit {shlex.quote(str(jdl_path))}",
        shell=True, capture_output=True, text=True, check=True,
    )
    output = result.stdout + result.stderr
    cluster_match = CLUSTER_ID_RE.search(output)
    schedd_match = SCHEDD_RE.search(output)
    if not cluster_match or not schedd_match:
        raise RuntimeError(f"Could not parse ClusterId/schedd from condor_submit output:\n{output}")
    return int(cluster_match.group(1)), schedd_match.group(1)


def cluster_history(cluster_id, schedd):
    """Return {proc_id: (JobStatus, RemoveReason, ExitCode)} for every ProcId under cluster_id on schedd.

    condor_history isn't indexed -- it scans the schedd's history file per call -- and
    every job from the initial submission (and every resubmission round) shares one
    cluster_id, so one call per cluster here replaces what used to be one call per job.
    -af:t (tab-delimited) keeps RemoveReason safely splittable even if it contains spaces
    (e.g. condor_rm's default reason text).
    """
    result = subprocess.run(
        f"condor_history -name {shlex.quote(schedd)} "
        f"-constraint {shlex.quote(f'ClusterId=={cluster_id}')} "
        f"-af:t ProcId JobStatus RemoveReason ExitCode",
        shell=True, capture_output=True, text=True, check=True,
    )
    statuses = {}
    for line in result.stdout.strip().splitlines():
        parts = line.split('\t')
        proc_id = int(parts[0])
        status = int(parts[1])
        reason = parts[2] if len(parts) > 2 and parts[2] != 'undefined' else ""
        exit_code = int(parts[3]) if len(parts) > 3 and parts[3] != 'undefined' else None
        statuses[proc_id] = (status, reason, exit_code)
    return statuses


def eos_file_exists(remote_path):
    """Check via xrdfs stat whether remote_path (server-relative, e.g. /store/...) exists on EOS."""
    result = subprocess.run(
        ["xrdfs", EOS_SERVER, "stat", remote_path],
        capture_output=True, text=True,
    )
    return result.returncode == 0


def resubmit_timeouts(script_dir):
    """Check retry_state.json in script_dir and resubmit any job that isn't confirmed to have produced good output.

    No timeout logic of our own here: the site's +JobFlavour wall-time cap (see batch_jdl_template)
    kills a job that runs too long, and that just shows up below as a job that stopped
    running without a completed/verified output -- same as a crash or a hold, so it's
    handled the same way: resubmit it.
    """
    script_dir = Path(script_dir)
    state_path = script_dir / 'retry_state.json'
    with open(state_path, 'r') as f:
        state = json.load(f)

    max_retries = state['max_retries']
    dataset = state['dataset']
    # 'batch' is absent in retry_state.json files written before the (batch, jobid)
    # naming fix -- fall back to the old ClusterId-based naming for those so we don't
    # mismatch against files that already exist on EOS under the old scheme.
    batch = state.get('batch')
    n_gave_up = n_ok = n_untouched = 0
    to_resubmit = []  # [(jobid, cause), ...]

    # Jobs already confirmed ok (output verified on EOS) or given up on (retries
    # exhausted) are terminal: their outcome can't change, so skip them here rather
    # than re-querying condor_history for their cluster on every future --resubmit
    # call just to re-derive the same answer.
    pending = {jobid: entry for jobid, entry in state['jobs'].items() if not entry.get('done')}
    n_done = len(state['jobs']) - len(pending)

    unique_clusters = {(entry['schedd'], entry['cluster_id']) for entry in pending.values()}
    print(f"Querying condor_history for {len(unique_clusters)} cluster(s) covering {len(pending)} pending job(s) "
          f"({n_done} already confirmed done, skipped)...", flush=True)
    history = {}  # (schedd, cluster_id) -> {proc_id: (status, reason, exit_code)}
    for i, (schedd, cid) in enumerate(sorted(unique_clusters), start=1):
        print(f"[{i}/{len(unique_clusters)}] condor_history for cluster {cid} on {schedd}...", flush=True)
        history[(schedd, cid)] = cluster_history(cid, schedd)

    for jobid, entry in pending.items():
        status, reason, exit_code = history[(entry['schedd'], entry['cluster_id'])].get(entry['proc_id'], (None, None, None))

        if status in (None, 1, 2):
            n_untouched += 1
            continue
        elif status == 4:
            if exit_code != 0:
                cause = f'exited with code {exit_code}'
            else:
                if batch is not None:
                    output_file = f"{dataset}_{batch}_{jobid}.root"
                else:
                    output_file = f"{dataset}_{entry['cluster_id']}_{jobid}.root"
                remote_path = f"{EOS_OUTPUT_BASE}/{dataset}/{output_file}"
                if eos_file_exists(remote_path):
                    n_ok += 1
                    entry['done'] = True
                    continue
                cause = 'completed but output missing on EOS'
        else:
            cause = f'status={status}' + (f' ({reason})' if reason else '')

        if entry['retries'] >= max_retries:
            print(f"job {jobid}: gave up after {entry['retries']} retries ({cause})", flush=True)
            n_gave_up += 1
            entry['done'] = True
            continue

        print(f"job {jobid}: needs resubmission ({cause})", flush=True)
        to_resubmit.append((jobid, cause))

    if to_resubmit:
        # state['bash_path'] is the worker script frozen at the original submission
        # time; refresh it from the current bash_template so fixes made since then
        # (e.g. the cmsRun retry/redirector-fallback logic) take effect on resubmission
        # instead of silently reusing whatever script version was in place back then.
        with open(state['bash_path'], 'w') as f:
            f.write(bash_template)

        if batch is not None:
            output_name = f"{dataset}_{batch}_$(jobid).root"
        else:
            output_name = f"{dataset}_$(ClusterId)_$(jobid).root"

        print(f"\nSubmitting {len(to_resubmit)} job(s) for resubmission...", flush=True)
        jdl_content = Template(resubmit_jdl_template).render({
            'bash_file': state['bash_path'],
            'log_dir': state['log_dir'],
            'dataset': dataset,
            'output_name': output_name,
            'input_list': state['input_list'],
            'jobids': [int(jobid) for jobid, _ in to_resubmit],
            'request_memory': request_memory_for(dataset, QCD_RESUBMIT_REQUEST_MEMORY),
        })
        jdl_path = script_dir / f"resubmit_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jdl"
        with open(jdl_path, 'w') as f:
            f.write(jdl_content)

        new_cluster_id, new_schedd = submit_job(jdl_path)
        for proc_id, (jobid, cause) in enumerate(to_resubmit):
            entry = state['jobs'][jobid]
            entry['cluster_id'] = new_cluster_id
            entry['proc_id'] = proc_id
            entry['schedd'] = new_schedd
            entry['retries'] += 1
            print(f"job {jobid}: {cause}, resubmitted to cluster {new_cluster_id} "
                  f"(ProcId {proc_id}, retry {entry['retries']}/{max_retries})", flush=True)

    with open(state_path, 'w') as f:
        json.dump(state, f, indent=2)
    print(f"\n{len(to_resubmit)} resubmitted, {n_gave_up} gave up, {n_ok} confirmed ok, {n_untouched} still running/other, "
          f"{n_done} previously confirmed done (skipped)")


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
    batch_number = parse_batch_number(args.input_list)

    script_dir = Path('.') / 'condor_scripts' / f'{dataset_prefix}' / f'job_submission_{now}'
    log_dir = Path('.') / 'condor_logs' / f'{dataset_prefix}' / f'job_submission_{now}'

    script_dir.mkdir(exist_ok=True, parents=True)
    log_dir.mkdir(exist_ok=True, parents=True)

    bash_path = script_dir / 'mini2nano.sh'
    with open(bash_path, 'w') as f:
        f.write(bash_template)

    # dataset example: batch1_Zto2Q-2Jets_Bin-PTQQ-600_TuneCP5_13p6TeV_amcatnloFXFX-pythia8.txt
    # Use "Zto2Q-2Jets_Bin-PTQQ-600" as header

    batch_jdl_path = script_dir / 'mini2nano.jdl'
    batch_jdl_content = Template(batch_jdl_template).render({
        'bash_file': bash_path.as_posix(),
        'log_dir': log_dir.as_posix(),
        'dataset': dataset_prefix,
        'batch': batch_number,
        'input_list': args.input_list,
        'total_jobs': total_jobs,
        'request_memory': request_memory_for(dataset_prefix, QCD_REQUEST_MEMORY),
    })
    with open(batch_jdl_path, 'w') as f:
        f.write(batch_jdl_content)

    if args.dryrun:
        print("\n--- [Dry Run Validation] ---")
        print(f"Bash Script Path: {bash_path.as_posix()}")
        print(f"Batch JDL Path: {batch_jdl_path.as_posix()}")

    else:
        cluster_id, schedd = submit_job(batch_jdl_path)
        print(f"{total_jobs} jobs submitted to cluster {cluster_id} on {schedd}")

        jobs_state = {
            str(jobid): {'cluster_id': cluster_id, 'proc_id': jobid, 'schedd': schedd, 'retries': 0}
            for jobid in range(total_jobs)
        }

        state_path = script_dir / 'retry_state.json'
        with open(state_path, 'w') as f:
            json.dump({
                'dataset': dataset_prefix,
                'batch': batch_number,
                'input_list': args.input_list,
                'bash_path': bash_path.as_posix(),
                'log_dir': log_dir.as_posix(),
                'max_retries': args.max_retries,
                'jobs': jobs_state,
            }, f, indent=2)
        print(f"\nRetry state written to {state_path.as_posix()}")
        print(f"Run 'python submit.py --resubmit {script_dir.as_posix()}' later to resubmit any that failed.")
