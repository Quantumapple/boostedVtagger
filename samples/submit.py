import os
import argparse
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
Arguments             = {{ input_list }} $(ProcId) {{ dataset }}_$(ClusterId)_$(ProcId).root {{ dataset }}
output                = {{ log_dir }}/{{ dataset }}.$(ClusterId).$(ProcId).stdout
error                 = {{ log_dir }}/{{ dataset }}.$(ClusterId).$(ProcId).stderr
log                   = {{ log_dir }}/mini2nano.log
MY.WantOS             = "el9"
+JobFlavour           = "tomorrow"
Queue {{ total_jobs }}
"""

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Submit jobs to Condor')

    parser.add_argument('--input_list', type=str, required=True, help='Path to the text file containing jobs mapping')
    parser.add_argument('--dryrun', action='store_true')
    args = parser.parse_args()

    with open(args.input_list, 'r') as f:
        total_jobs = len(f.readlines())

    now = datetime.now().strftime("%Y%m%d_%H%M%S")
    dataset_prefix = args.input_list.split('_TuneCP5')[0].replace("batch1_", "")

    script_dir = Path('.') / 'condor_scripts' / f'{dataset_prefix}' / f'job_submission_{now}'
    log_dir = Path('.') / 'condor_logs' / f'{dataset_prefix}' / f'job_submission_{now}'

    script_dir.mkdir(exist_ok=True, parents=True)
    log_dir.mkdir(exist_ok=True, parents=True)

    bash_path = script_dir / 'mini2nano.sh'
    jdl_path = script_dir / 'mini2nano.jdl'

    # dataset example: batch1_Zto2Q-2Jets_Bin-PTQQ-600_TuneCP5_13p6TeV_amcatnloFXFX-pythia8.txt
    # Use "Zto2Q-2Jets_Bin-PTQQ-600" as header

    jdl_content = Template(jdl_template).render({
        'bash_file': bash_path.as_posix(),
        'log_dir': log_dir.as_posix(),
        'dataset': dataset_prefix,
        'input_list': args.input_list,
        'total_jobs': total_jobs
    })

    with open(bash_path, 'w') as f:
        f.write(bash_template)

    with open(jdl_path, 'w') as f:
        f.write(jdl_content)

    if args.dryrun:
        print("\n--- [Dry Run Validation] ---")
        print(f"JDL Output Path: {jdl_path.as_posix()}")
        print(f"Bash Script Path: {bash_path.as_posix()}")

    else:
        submit_command = f"condor_submit {jdl_path.as_posix()}"
        os.system(submit_command)