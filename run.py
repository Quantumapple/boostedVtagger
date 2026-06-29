import time
import json
import argparse
from coffea import nanoevents, processor
from processor.preprocessor import PreProcessor

if __name__ == "__main__":

    parser = argparse.ArgumentParser(description='Run coffea processor!')

    parser.add_argument(
        '-s',
        '--sample',
        metavar = 'JSONFILE',
        type = str,
        help = 'input json file including dataset',
        required = True,
        dest = 'sample',
    )

    args = parser.parse_args()

    with open(args.sample, 'r') as file:
        fileset = json.load(file)

    p = PreProcessor()
    # nanoevents.PFNanoAODSchema.mixins["SV"] = "PFCand"

    tic = time.time()

    run = processor.Runner(
        executor=processor.IterativeExecutor(status=True),
        savemetrics=True,
        schema=nanoevents.PFNanoAODSchema,
        chunksize=1000,
    )

    out, metrics = run(fileset, processor_instance=p)

    elapsed = time.time() - tic
    print(f"Metrics: {metrics}")
    print(f"Finished in {elapsed:.1f}s")
