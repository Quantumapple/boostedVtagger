import time
from coffea import nanoevents, processor
from processor.preprocessor import PreProcessor

fileset = {}
fileset['Wto2Q-2Jets_Bin-PTQQ'] = {
    "treename": "Events",
    "files": ['../samples/Wto2Q-2Jets_Bin-PTQQ-100_0.root'],
    "metadata": {"year": 2024, "is_mc": True},
}

p = PreProcessor()

# nanoevents.PFNanoAODSchema.mixins["SV"] = "PFCand"

tic = time.time()

run = processor.Runner(
    executor=processor.IterativeExecutor(status=True),
    savemetrics=True,
    schema=nanoevents.PFNanoAODSchema,
)

out, metrics = run(fileset, processor_instance=p)

elapsed = time.time() - tic
print(f"Metrics: {metrics}")
print(f"Finished in {elapsed:.1f}s")