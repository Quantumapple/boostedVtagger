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

##################
# VH signal samples
datasets=(
  # GluGluZH
  GluGluZH-Zto2Q-Hto2Wto2L2Nu_Par-M-125_TuneCP5_13p6TeV_powhegMINLO-jhugen-pythia8
  GluGluZH-Zto2Q-Hto2Wto4Q_Par-M-125_TuneCP5_13p6TeV_powhegMINLO-jhugen-pythia8
  GluGluZH-Zto2Q-Hto2WtoLNu2Q_Par-M-125_TuneCP5_13p6TeV_powhegMINLO-jhugen-pythia8
  # WminusH
  WminusH-Wto2Q-Hto2Wto2L2Nu_Par-M-125_TuneCP5_13p6TeV_powhegMINLO-jhugen-pythia8
  WminusH-Wto2Q-Hto2Wto4Q_Par-M-125_TuneCP5_13p6TeV_powhegMINLO-jhugen-pythia8
  WminusH-Wto2Q-Hto2WtoLNu2Q_Par-M-125_TuneCP5_13p6TeV_powhegMINLO-jhugen-pythia8
  # WplusH
  WplusH-Wto2Q-Hto2Wto4Q_Par-M-125_TuneCP5_13p6TeV_powhegMINLO-jhugen-pythia8
  WplusH-Wto2Q-Hto2WtoLNu2Q_Par-M-125_TuneCP5_13p6TeV_powhegMINLO-jhugen-pythia8
  WplusH_Wto2Q_Hto2Wto2L2Nu_M-125_Par-M-125_TuneCP5_13p6TeV_powhegMINLO-jhugen-pythia8
  # ZH
  ZH-Zto2Q-Hto2Wto2L2Nu_Par-M-125_TuneCP5_13p6TeV_powhegMINLO-jhugen-pythia8
  ZH-Zto2Q-Hto2Wto4Q_Par-M-125_TuneCP5_13p6TeV_powhegMINLO-jhugen-pythia8
  ZH-Zto2Q-Hto2WtoLNu2Q_Par-M-125_TuneCP5_13p6TeV_powhegMINLO-jhugen-pythia8
)

for dataset in "${datasets[@]}"; do
    echo "Querying ${dataset}..."
    das_name=$(dasgoclient -query="dataset=/${dataset}/RunIII2024Summer24MiniAODv6*/MINIAODSIM")
    n=$(echo "$das_name" | grep -c .)
    if [ "$n" -ne 1 ]; then
        echo "  !! expected 1 dataset, got ${n}:"; echo "$das_name"
        continue
    fi
    echo "  -> ${das_name}"
    dasgoclient -query="file dataset=${das_name}" | sed 's|^|/dcache/uscmsdisk|' > ${dataset}.txt
    echo "  $(wc -l < ${dataset}.txt) files"
done
##################

