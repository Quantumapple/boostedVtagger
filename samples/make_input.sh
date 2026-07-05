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
for dataset in QCD-4Jets_Bin-HT-1000to1200_TuneCP5_13p6TeV_madgraphMLM-pythia8 QCD-4Jets_Bin-HT-1200to1500_TuneCP5_13p6TeV_madgraphMLM-pythia8 QCD-4Jets_Bin-HT-1500to2000_TuneCP5_13p6TeV_madgraphMLM-pythia8 QCD-4Jets_Bin-HT-2000_TuneCP5_13p6TeV_madgraphMLM-pythia8
do
    echo "Querying ${dataset}..."
    xrdfs root://cmsdcadisk.fnal.gov/ ls -R /dcache/uscmsdisk/store/mc/Run3Winter26MiniAODv6/${dataset} | grep '\.root$' > ${dataset}.txt
done
##################

##################
for dataset in QCD-4Jets_Bin-HT-100to200_TuneCP5_13p6TeV_madgraphMLM-pythia8 QCD-4Jets_Bin-HT-200to400_TuneCP5_13p6TeV_madgraphMLM-pythia8 QCD-4Jets_Bin-HT-400to600_TuneCP5_13p6TeV_madgraphMLM-pythia8 QCD-4Jets_Bin-HT-600to800_TuneCP5_13p6TeV_madgraphMLM-pythia8 QCD-4Jets_Bin-HT-800to1000_TuneCP5_13p6TeV_madgraphMLM-pythia8
do
    echo "Querying ${dataset}..."
    xrdfs root://cmsdcadisk.fnal.gov/ ls -R /dcache/uscmsdisk/store/mc/Run3Winter26MiniAODv6/${dataset} | grep '\.root$' > ${dataset}.txt
done
##################