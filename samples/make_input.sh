##################
for dataset in Wto2Q-2Jets_Bin-PTQQ-100_TuneCP5_13p6TeV_amcatnloFXFX-pythia8 Wto2Q-2Jets_Bin-PTQQ-200_TuneCP5_13p6TeV_amcatnloFXFX-pythia8 Wto2Q-2Jets_Bin-PTQQ-400_TuneCP5_13p6TeV_amcatnloFXFX-pythia8 Wto2Q-2Jets_Bin-PTQQ-600_TuneCP5_13p6TeV_amcatnloFXFX-pythia8
do
    echo "Querying ${dataset}..."
    xrdfs root://cmsdcadisk.fnal.gov/ ls -R /dcache/uscmsdisk/store/mc/RunIII2024Summer24MiniAODv6/${dataset} | grep '\.root$' > ${dataset}.txt
done
##################

##################
for dataset in Zto2Q-2Jets_Bin-PTQQ-100_TuneCP5_13p6TeV_amcatnloFXFX-pythia8 Zto2Q-2Jets_Bin-PTQQ-200_TuneCP5_13p6TeV_amcatnloFXFX-pythia8 Zto2Q-2Jets_Bin-PTQQ-400_TuneCP5_13p6TeV_amcatnloFXFX-pythia8 Zto2Q-2Jets_Bin-PTQQ-600_TuneCP5_13p6TeV_amcatnloFXFX-pythia8
do
    echo "Querying ${dataset}..."
    xrdfs root://cmsdcadisk.fnal.gov/ ls -R /dcache/uscmsdisk/store/mc/RunIII2024Summer24MiniAODv6/${dataset} | grep '\.root$' > ${dataset}.txt
done
##################

##################
# QCD samples aren't all on FNAL disk, so they're resolved via DAS instead
# of browsing FNAL's physical dCache tree -- see make_qcd_input.py.
python3 make_qcd_input.py
##################