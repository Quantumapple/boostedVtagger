import awkward as ak
import numpy as np
import pandas as pd

import time

from coffea.processor import ProcessorABC
from coffea.nanoevents.methods import candidate
from coffea.analysis_tools import PackedSelection
from .tagger_gen_matching import match_Wplus, match_Wminus, match_Z, match_QCD
from .tagger_input import get_pfcands_features

### Warning ignorance
import warnings
warnings.filterwarnings("ignore", message="Missing cross-reference index ")


class PreProcessor(ProcessorABC):
    """
    Produces a flat training ntuple from PFNano.
    Targets hadronic V boson decays: W+/W-/Z -> qq
    """

    def __init__(self):

        # Define the full list of gen-level variables to keep in the output ntuple.
        # This serves as the output schema and ensures a consistent set of columns
        # across all sample types (W+, W-, Z, QCD). If a variable is not applicable
        # to a given sample (e.g. fj_isZ_2q for a QCD sample), it will be
        # automatically zero-filled in the process() method, so all output files
        # have the same structure and can be merged for training.

        self.GenPartvars = [
            # "fj_genjetmass",
            # W boson (hadronic)
            "fj_isWplus",
            "fj_isWplus_ud",
            "fj_isWplus_cs",
            "fj_isWminus",
            "fj_isWminus_ud",
            "fj_isWminus_cs",
            # Z boson (hadronic)
            "fj_isZ",
            "fj_isZ_bb",
            "fj_isZ_cc",
            "fj_isZ_qq",
            # QCD
            "fj_isQCD_Matched",
        ]

    @property
    def accumulator(self):
        return self._accumulator

    def process(self, events: ak.Array):

        start = time.time()

        dataset = events.metadata["dataset"]
        print(f'Process {dataset}')

        def build_p4(obj):
            return ak.zip(
                {
                    "pt": obj.pt,
                    "eta": obj.eta,
                    "phi": obj.phi,
                    "mass": obj.mass,
                    "charge": obj.charge,
                },
                with_name="PtEtaPhiMCandidate",
                behavior=candidate.behavior,
            )

        #### Reference processor: https://github.com/jennetd/hbb-coffea/blob/master/boostedhiggs/vhbbprocessor.py
        #### Reference: HIG-24-017-paper-v23
        #### The relative isolation variable for electrons (muons) is defined as the scalar sum pT of charged hadrons and neutral particles within
        #### a cone of radius ∆R = 0.3 (0.4) around the lepton, corrected for pileup and divided by the lepton pT

        #### electrons must have pT > 10 GeV, |η| < 2.5, pass loose identification criteria, and have relative isolation less than 0.15
        electrons = events.Electron
        ele_selections = (electrons.pt > 10) & (abs(electrons.eta) < 2.5) & (electrons.cutBased >= 2) # & (electrons.pfRelIso03_all < 0.15)
        electrons = electrons[ele_selections]

        #### Muons must have pT > 10 GeV, |η | < 2.4, pass loose identification criteria, and have relative isolation less than 0.25
        muons = events.Muon
        mu_selections = (muons.pt > 10) & (abs(muons.eta) < 2.4) & (muons.looseId) & (muons.pfRelIso03_all < 0.25)
        muons = muons[mu_selections]

        #### Hadronically decaying tau leptons must have pT > 20 GeV, |η| < 2.3, and pass the DEEP TAU algorithm identification requirements
        #### In the analysisn note, (Decay Mode != 5,6,7) and tightidDeepTau
        #### taus: defined but not included in jet cleaning for now
        # taus = events.Tau
        # tau_selections = (
        #     (taus.pt > 20)
        #     & (abs(taus.eta) < 2.3)
        #     & (abs(taus.dz) < 0.2)
        #     & (taus.decayMode >= 0)
        #     & (taus.decayMode != 5)
        #     & (taus.decayMode != 6)
        #     & (taus.decayMode != 7)
        #     # Run 3: updated from DeepTau2017v2p1 to DeepTau2018v2p5
        #     & (taus.idDeepTau2018v2p5VSe >= 2)    # VVLoose
        #     & (taus.idDeepTau2018v2p5VSmu >= 4)   # Tight
        #     & (taus.idDeepTau2018v2p5VSjet >= 5)  # Medium
        # )
        # taus = taus[tau_selections]

        leptons = ak.concatenate([electrons, muons], axis=1)
        leptons = leptons[ak.argsort(leptons.pt, ascending=False)]
        candidatelep_p4 = build_p4(leptons)

        def tight_jet_id(jets):
            """
            Manual Tight Jet ID for Run 3 NanoAOD v15+
            (isTight no longer available as a precomputed branch)
            Reference: https://twiki.cern.ch/twiki/bin/viewauth/CMS/JetID13p6TeV
            """
            abs_eta = abs(jets.eta)
            return (
                ak.where(abs_eta <= 2.6,
                    (jets.neHEF < 0.99) & (jets.neEmEF < 0.9) &
                    ((jets.chMultiplicity + jets.neMultiplicity) > 1) &
                    (jets.chHEF > 0.01) & (jets.chMultiplicity > 0),
                ak.where(abs_eta <= 2.7,
                    (jets.neHEF < 0.90) & (jets.neEmEF < 0.99),
                ak.where(abs_eta <= 3.0,
                    (jets.neHEF < 0.99),
                    # abs_eta > 3.0
                    (jets.neMultiplicity >= 2) & (jets.neEmEF < 0.4)
                )))
            )

        #### Ak8 jets
        #### be separated from any isolated leptons or photons by ∆R > 0.8
        fatjets = events.FatJet
        is_good = (fatjets.pt > 200) & (abs(fatjets.eta) < 2.5) & tight_jet_id(fatjets)

        #### We only keep jets where ALL leptons are DeltaR > 0.8 away
        dr_table = fatjets.metric_table(candidatelep_p4)
        is_clean = ak.all(dr_table > 0.8, axis=-1)
        total_mask = is_good & is_clean

        #### Use ak.mask to find the index relative to the ORIGINAL collection
        # ak.mask turns 'False' entries into 'None' but keeps the array length the same.
        # argmax will ignore 'None' and return the index in the original FatJet list.
        leading_fj_idx = ak.argmax(ak.mask(fatjets.pt, total_mask), axis=1, keepdims=True)

        candidatefj = fatjets[total_mask]
        candidatefj = candidatefj[ak.argsort(candidatefj.pt, ascending=False)]
        leadingfj = ak.firsts(candidatefj)

        # =========== AK8 jet-level variables ===========
        FatJetVars = {
            f"fj_{var}": leadingfj[var]
            for var in ["pt", "eta", "phi", "mass", "msoftdrop"]
        }
        FatJetVars["fj_numFatjets"] = ak.num(candidatefj)

        ###### =========== Gen-level matching ===========
        genparts = events.GenPart
        GenVars = {}

        if "Wto2Q" in dataset:
            wplus_genvars, _ = match_Wplus(genparts, leadingfj)
            wminus_genvars, _ = match_Wminus(genparts, leadingfj)
            GenVars = {**wplus_genvars, **wminus_genvars}
        elif "Zto2Q" in dataset:
            z_genvars, _ = match_Z(genparts, leadingfj)
            GenVars = {**z_genvars}
        elif "QCD" in dataset:
            qcd_genvars, _ = match_QCD(genparts, leadingfj)
            GenVars = {**qcd_genvars}

        AllGenVars = {
            **GenVars,
            # **{"fj_genjetmass": leadingfj.matched_gen.mass},
        }

        # Fill missing variables with zeros if not applicable to this sample
        GenVars = {
            key: AllGenVars[key] if key in AllGenVars else np.zeros(len(genparts))
            for key in self.GenPartvars
        }

        for key in GenVars:
            try:
                GenVars[key] = ak.to_numpy(GenVars[key])
            except Exception as e:
                raise RuntimeError(f"Failed to convert {key} to numpy: {e}")

        # =========== Combine all variables ===========
        skimmed_vars = {**FatJetVars, **GenVars}

        # =========== Event selection ===========
        selection = PackedSelection()
        # Require at least one good fat jet per event
        selection.add("fjselection", ak.num(candidatefj) >= 1)

        if np.sum(selection.all(*selection.names)) == 0:
            return {}

        skimmed_vars = {
            key: np.squeeze(np.array(value[selection.all(*selection.names)]))
            for key, value in skimmed_vars.items()
        }

        pfcands_dict = get_pfcands_features(
            events[selection.all(*selection.names)],
            leading_fj_idx[selection.all(*selection.names)]
        )

        # =========== Convert and save ===========
        for key in skimmed_vars:
            skimmed_vars[key] = skimmed_vars[key].squeeze().tolist()

        df = pd.DataFrame(skimmed_vars)
        df = df.dropna()  # drop events with NaN genjetmass

        if not df.empty:
            df.to_parquet(f'{dataset}.parquet')

        print(f"Processed {len(df)} events in {time.time() - start:.1f}s")
        return {}

    def postprocess(self, accumulator):
        pass